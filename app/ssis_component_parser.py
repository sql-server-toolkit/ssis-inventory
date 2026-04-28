from __future__ import annotations

import re
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from lxml import etree

from app.models import ComponentUsage, WarningItem
from app.sql_object_extractor import extract_objects_from_sql


SQL_PROPERTY_NAMES = {
    "sqlcommand",
    "sqlcommandsource",
    "sqlstatementsource",
    "commandtext",
    "opensqlcommand",
    "sqlstatement",
}

OBJECT_PROPERTY_NAMES = {
    "openrowset",
    "tablename",
    "table",
}

CONNECTION_PROPERTY_NAMES = {
    "connection",
    "connectionmanager",
    "connectionmanagerid",
    "connectionmanagerrefid",
    "connectionmanagername",
    "oleDbConnection",
    "adoNetConnection",
}

SQL_HINTS = (
    "select ",
    "insert ",
    "update ",
    "delete ",
    "merge ",
    "exec ",
    "execute ",
    "truncate ",
    "from ",
)

IGNORED_TEXT_FRAGMENTS = (
    "scriptproject",
    "publickeytoken",
    "assemblyinfo",
    "<layout",
    "<objects>",
    "<objectdata",
    ".resx",
    "microsoft.sqlserver.scriptTask",
)


def _local_name(value: str | None) -> str:
    if not value:
        return ""
    if "}" in value:
        return value.rsplit("}", 1)[-1]
    if ":" in value:
        return value.rsplit(":", 1)[-1]
    return value


def _attr(elem: etree._Element, *names: str) -> str | None:
    wanted = {name.lower() for name in names}
    for key, value in elem.attrib.items():
        if _local_name(key).lower() in wanted:
            return value
    return None


def _iter_attrs(elem: etree._Element):
    for key, value in elem.attrib.items():
        yield _local_name(key), value


def _text(elem: etree._Element) -> str:
    parts = []
    if elem.text:
        parts.append(elem.text)
    for child in elem:
        if child.text:
            parts.append(child.text)
        if child.tail:
            parts.append(child.tail)
    return " ".join(p.strip() for p in parts if p and p.strip())


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _canonical(value: Any) -> str:
    text = _clean(value)
    if not text:
        return ""
    text = text.strip("{}")
    text = text.replace("\\", "/")
    text = re.sub(r"\s+", " ", text)
    return text.lower()


def _is_disabled(elem: etree._Element) -> bool:
    value = _attr(elem, "Disabled", "disabled")
    return str(value).strip().lower() in {"true", "1"}


def _has_disabled_ancestor(elem: etree._Element) -> bool:
    current = elem
    while current is not None:
        if _is_disabled(current):
            return True
        current = current.getparent()
    return False


def _normalize_row(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    if is_dataclass(row):
        return asdict(row)
    if isinstance(row, Mapping):
        return dict(row)
    return {}


def _connection_name_set(connections: Iterable[Any] | None) -> set[str]:
    names: set[str] = set()
    for item in connections or []:
        data = _normalize_row(item)
        name = _clean(data.get("connection_name"))
        if name:
            names.add(_canonical(name))
    return names


def _add_alias(aliases: dict[str, str], raw_key: Any, connection_name: str | None) -> None:
    key = _canonical(raw_key)
    value = _clean(connection_name)
    if not key or not value:
        return
    aliases[key] = value

    # Formatos comuns no XML SSIS:
    aliases[_canonical(f"Package.ConnectionManagers[{value}]")] = value
    aliases[_canonical(f"$Package.ConnectionManagers[{value}]")] = value
    aliases[_canonical(f"Project.ConnectionManagers[{value}]")] = value
    aliases[_canonical(f"$Project.ConnectionManagers[{value}]")] = value


def build_connection_aliases(root: etree._Element, connections: Iterable[Any] | None = None) -> dict[str, str]:
    r"""Cria mapa de chaves internas do SSIS para nome lógico de conexão.

    Importante: não considera refId de componente como conexão.
    O bug reportado surgiu porque valores do tipo Package\Fluxo\Component eram usados
    como connection_name. Este mapa só aceita ConnectionManagers reais.
    """
    aliases: dict[str, str] = {}

    for item in connections or []:
        data = _normalize_row(item)
        name = _clean(data.get("connection_name"))
        if not name or name.upper() in {"UNNAMED_CONNECTION", "UNKNOWN_CONNECTION"}:
            continue
        _add_alias(aliases, name, name)
        _add_alias(aliases, data.get("connection_string_raw"), name)

    for elem in root.iter():
        local = _local_name(elem.tag).lower()
        creation = _clean(_attr(elem, "CreationName", "creationName"))
        object_name = _clean(_attr(elem, "ObjectName", "name"))
        if local != "connectionmanager" and "connectionmanager" not in local:
            continue
        if not object_name:
            continue

        _add_alias(aliases, object_name, object_name)
        _add_alias(aliases, _attr(elem, "DTSID", "DTSID"), object_name)
        _add_alias(aliases, _attr(elem, "refId", "refid"), object_name)
        _add_alias(aliases, _attr(elem, "ID", "id"), object_name)
        _add_alias(aliases, creation, object_name)

        for child in elem.iter():
            prop_name = _clean(_attr(child, "Name", "name"))
            prop_text = _clean(child.text)
            if prop_name.lower() in {"connectionstring", "server", "databasename", "initialcatalog"} and prop_text:
                _add_alias(aliases, prop_text, object_name)

    return aliases


def _is_component_path(value: str | None) -> bool:
    text = _clean(value)
    if not text:
        return False
    # Caminhos de componente aparecem assim:
    # Package\Fluxo\Componente ou Package/Data Flow/Component
    return bool(re.match(r"^(package|project)[\\/]", text, flags=re.IGNORECASE))


def resolve_connection_name(raw_value: Any, aliases: Mapping[str, str], valid_names: set[str] | None = None) -> str | None:
    text = _clean(raw_value)
    if not text:
        return None

    # Não publicar caminho de componente como conexão.
    if _is_component_path(text):
        # Algumas referências vêm como Package.ConnectionManagers[Nome], que é válido.
        if "connectionmanagers[" not in text.lower():
            return None

    key = _canonical(text)
    if key in aliases:
        return aliases[key]

    # Extrai nome entre ConnectionManagers[...].
    m = re.search(r"ConnectionManagers\[(.*?)\]", text, flags=re.IGNORECASE)
    if m:
        candidate = m.group(1).strip()
        candidate_key = _canonical(candidate)
        if candidate_key in aliases:
            return aliases[candidate_key]
        if not valid_names or candidate_key in valid_names:
            return candidate

    # Só aceita valor literal se for nome de conexão conhecido.
    if valid_names and key in valid_names:
        return text

    return None


def _get_component_name(elem: etree._Element) -> str:
    return (
        _clean(_attr(elem, "name", "ObjectName"))
        or _clean(_attr(elem, "refId", "refid")).split("\\")[-1].split("/")[-1]
        or _local_name(elem.tag)
        or "UNKNOWN_COMPONENT"
    )


def _get_component_type(elem: etree._Element) -> str:
    return (
        _clean(_attr(elem, "componentClassID", "CreationName", "creationName", "type"))
        or _local_name(elem.tag)
        or "UNKNOWN_COMPONENT_TYPE"
    )


def _get_task_path(elem: etree._Element) -> str:
    names: list[str] = []
    current = elem
    while current is not None:
        name = _clean(_attr(current, "ObjectName", "name"))
        if name and name not in names:
            names.append(name)
        current = current.getparent()
    names.reverse()
    if names:
        return "\\".join(names[-3:])
    return _get_component_name(elem)


def _looks_like_noise_text(value: str | None) -> bool:
    text = _clean(value).lower()
    if not text:
        return True
    if len(text) > 20000:
        return True
    return any(fragment in text for fragment in IGNORED_TEXT_FRAGMENTS)


def _looks_like_sql_or_object(value: str | None) -> bool:
    text = _clean(value)
    if not text or _looks_like_noise_text(text):
        return False
    lower = f" {text.lower()} "
    if any(hint in lower for hint in SQL_HINTS):
        return True
    # OLE DB Destination costuma guardar somente [schema].[table] ou [table].
    if re.fullmatch(r"(?:\[[^\]]+\]|\w+)(?:\.(?:\[[^\]]+\]|\w+)){0,2}", text):
        return True
    return False


def _collect_component_connection(elem: etree._Element, aliases: Mapping[str, str], valid_names: set[str]) -> str | None:
    # 1) Procura atributos específicos de conexão no próprio elemento e descendentes.
    for target in [elem, *list(elem.iter())]:
        for attr_name, attr_value in _iter_attrs(target):
            if attr_name.lower() in {x.lower() for x in CONNECTION_PROPERTY_NAMES}:
                resolved = resolve_connection_name(attr_value, aliases, valid_names)
                if resolved:
                    return resolved

        prop_name = _clean(_attr(target, "name", "Name"))
        if prop_name.lower() in {x.lower() for x in CONNECTION_PROPERTY_NAMES}:
            value = _clean(target.text)
            resolved = resolve_connection_name(value, aliases, valid_names)
            if resolved:
                return resolved

    return None


def _collect_sql_texts(elem: etree._Element) -> list[tuple[str, str]]:
    """Retorna pares (metodo, texto SQL/objeto)."""
    texts: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(method: str, value: str | None) -> None:
        text = _clean(value)
        if not _looks_like_sql_or_object(text):
            return
        key = re.sub(r"\s+", " ", text).lower()
        if key in seen:
            return
        seen.add(key)
        texts.append((method, text))

    # Atributos comuns.
    for attr_name, attr_value in _iter_attrs(elem):
        lname = attr_name.lower()
        if lname in SQL_PROPERTY_NAMES or lname in OBJECT_PROPERTY_NAMES:
            add(attr_name, attr_value)

    # Propriedades filhas.
    for child in elem.iter():
        prop_name = _clean(_attr(child, "Name", "name"))
        lname = prop_name.lower()
        if lname in SQL_PROPERTY_NAMES or lname in OBJECT_PROPERTY_NAMES:
            add(prop_name, child.text or _text(child))

        # Alguns XMLs guardam diretamente como atributo value.
        if lname in SQL_PROPERTY_NAMES or lname in OBJECT_PROPERTY_NAMES:
            for _, attr_value in _iter_attrs(child):
                add(prop_name, attr_value)

    return texts


def _iter_operational_components(root: etree._Element):
    for elem in root.iter():
        local = _local_name(elem.tag).lower()
        ctype = _get_component_type(elem).lower()
        if local in {"component", "sqltaskdata"}:
            yield elem
            continue
        if "sqldata" in local or "sqltask" in local:
            yield elem
            continue
        if "oledbsource" in ctype or "oledbdestination" in ctype or "adonet" in ctype:
            yield elem


def parse_component_usages(
    project_name: str,
    package_name: str,
    dtsx_file: Path | str,
    connections: Iterable[Any] | None = None,
    *,
    ignore_disabled: bool = False,
    ignore_sql_comments_for_objects: bool = True,
):
    dtsx_path = Path(dtsx_file)
    tree = etree.parse(str(dtsx_path))
    root = tree.getroot()

    usages: list[ComponentUsage] = []
    objects = []
    warnings: list[WarningItem] = []

    aliases = build_connection_aliases(root, connections)
    valid_names = _connection_name_set(connections)
    if not valid_names:
        valid_names = {_canonical(v) for v in aliases.values() if v}

    for elem in _iter_operational_components(root):
        if ignore_disabled and _has_disabled_ancestor(elem):
            continue

        component_type = _get_component_type(elem)
        component_name = _get_component_name(elem)
        task_path = _get_task_path(elem)
        connection_name = _collect_component_connection(elem, aliases, valid_names)

        sql_texts = _collect_sql_texts(elem)

        # SQL Task pode trazer o statement direto como atributo com namespace.
        if _local_name(elem.tag).lower() == "sqltaskdata":
            for attr_name, attr_value in _iter_attrs(elem):
                if attr_name.lower() in {"sqlstatementsource", "sqlstatement", "sqlcommand"}:
                    if _looks_like_sql_or_object(attr_value):
                        sql_texts.append((attr_name, attr_value))
                if attr_name.lower() in {"connection", "connectionname"} and not connection_name:
                    connection_name = resolve_connection_name(attr_value, aliases, valid_names)

        # Deduplicar textos dentro do componente.
        deduped: list[str] = []
        seen_texts: set[str] = set()
        for _, text in sql_texts:
            key = re.sub(r"\s+", " ", text).lower()
            if key not in seen_texts:
                seen_texts.add(key)
                deduped.append(text)

        for sql_text in deduped:
            usage = ComponentUsage(
                project_name=project_name,
                package_name=package_name,
                task_path=task_path,
                component_type=component_type,
                component_name=component_name,
                connection_name=connection_name,
                sql_text=sql_text,
                source_file=str(dtsx_path),
            )
            usages.append(usage)
            objects.extend(
                extract_objects_from_sql(
                    project_name=project_name,
                    package_name=package_name,
                    task_path=usage.task_path,
                    component_type=usage.component_type,
                    component_name=usage.component_name,
                    connection_name=usage.connection_name,
                    sql_text=usage.sql_text,
                    source_file=usage.source_file,
                    ignore_sql_comments_for_objects=ignore_sql_comments_for_objects,
                )
            )

    if not usages:
        warnings.append(
            WarningItem(
                project_name=project_name,
                package_name=package_name,
                source_file=str(dtsx_path),
                warning_type="NO_SQL_DETECTED",
                message="Nenhum SQL/tabela explícito foi detectado no pacote pelo parser de componentes.",
            )
        )

    return usages, objects, warnings


def extract_component_usages_and_objects(
    project_name: str,
    package_name: str,
    dtsx_file: Path | str,
    connections: Iterable[Any] | None = None,
    *,
    ignore_disabled: bool = False,
    ignore_sql_comments_for_objects: bool = True,
):
    return parse_component_usages(
        project_name=project_name,
        package_name=package_name,
        dtsx_file=dtsx_file,
        connections=connections,
        ignore_disabled=ignore_disabled,
        ignore_sql_comments_for_objects=ignore_sql_comments_for_objects,
    )
