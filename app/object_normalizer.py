"""Normalização e deduplicação de objetos de banco para o ssis-inventory.

Este módulo existe para concentrar as regras de negócio que transformam a saída
bruta do parser em uma visão operacional mais limpa para equipes de BI e Infra.

Por que separar este código?
- O parser tende a gerar várias ocorrências técnicas do mesmo objeto.
- O relatório precisa mostrar uma única linha por objeto lógico.
- Regras como "table_or_view vira table" devem ficar explícitas e testáveis.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import asdict, is_dataclass
from typing import Any, Iterable


# Tokens que aparecem no XML/metadata do SSIS, mas não representam objetos de banco.
# Mantemos em minúsculo para comparação case-insensitive.
FALSE_OBJECT_NAMES = {
    "openrowset",
    "sqlcommand",
    "system.string",
    "string",
    "s",
    "t",
    "objectdata",
    "externalmetadataoutputcolumns",
    "inputcolumns",
    "outputcolumns",
}

# Tipos ambíguos do parser que, para uso operacional de implantação, devem ser
# tratados como tabela. Caso o projeto passe a diferenciar views no futuro, essa
# regra pode virar parâmetro de configuração.
TABLE_ALIASES = {
    "table_or_view",
    "view_or_table",
    "object_literal",
}


def to_plain_dict(item: Any) -> dict[str, Any]:
    """Converte dataclass, dict ou objeto simples para dict.

    O projeto passou por várias versões de contrato entre módulos. Esta função
    reduz fragilidade ao permitir que o relatório consuma tanto dataclasses
    quanto dicionários sem quebrar.
    """
    if item is None:
        return {}
    if isinstance(item, dict):
        return dict(item)
    if is_dataclass(item):
        return asdict(item)
    if hasattr(item, "__dict__"):
        return dict(vars(item))
    return {"value": item}


def first_present(row: dict[str, Any], *names: str, default: str = "") -> str:
    """Retorna o primeiro campo preenchido entre vários nomes possíveis.

    Isso ajuda a manter compatibilidade quando um mesmo conceito aparece com
    nomes diferentes, por exemplo `object_name`, `Objeto` ou `full_object_name`.
    """
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return default


def normalize_text(value: Any) -> str:
    """Normaliza texto para uso em chaves de deduplicação."""
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def normalize_key(value: Any) -> str:
    """Normaliza texto para comparação case-insensitive."""
    return normalize_text(value).lower()


def normalize_object_type(object_type: Any) -> str:
    """Normaliza o tipo de objeto usado nas abas operacionais.

    Regra atual:
    - `table_or_view`, `view_or_table` e `object_literal` são tratados como `table`.
    - `procedure`, `function`, `view` e demais tipos explícitos são preservados.
    """
    value = normalize_key(object_type)
    if value in TABLE_ALIASES:
        return "table"
    if value in {"proc", "stored_procedure", "stored procedure"}:
        return "procedure"
    return value or "unknown"


def normalize_object_name(name: Any) -> str:
    """Remove delimitadores comuns e normaliza nome de objeto.

    Exemplos:
    - `[dbo].[Tabela]` deve ser tratado como `dbo.Tabela`.
    - espaços excedentes são removidos.
    """
    value = normalize_text(name)
    value = value.replace("[", "").replace("]", "")
    value = value.strip(".;")
    return value


def is_false_object(row_or_name: Any) -> bool:
    """Indica se o objeto é ruído técnico e não deve aparecer no relatório.

    A lista bloqueia metadados do SSIS e aliases SQL muito curtos, como `s` e `t`,
    que estavam superestimando a contagem de objetos.
    """
    if isinstance(row_or_name, dict):
        name = first_present(row_or_name, "object_name", "Objeto", "full_object_name", "NomeCompleto", "value")
    else:
        name = str(row_or_name or "")

    normalized = normalize_key(normalize_object_name(name))
    if not normalized:
        return True
    if normalized in FALSE_OBJECT_NAMES:
        return True
    if len(normalized) == 1 and normalized.isalpha():
        return True
    return False


def split_full_object_name(row: dict[str, Any]) -> tuple[str, str, str, str]:
    """Retorna database, schema, object_name e full_name normalizados.

    A função aceita campos explícitos, mas também tenta decompor `full_object_name`
    quando necessário.
    """
    database = normalize_object_name(first_present(row, "database", "Database"))
    schema = normalize_object_name(first_present(row, "schema", "Schema"))
    obj = normalize_object_name(first_present(row, "object_name", "Objeto"))
    full = normalize_object_name(first_present(row, "full_object_name", "NomeCompleto"))

    if not obj and full:
        parts = [p for p in full.split(".") if p]
        if len(parts) >= 3:
            database, schema, obj = parts[-3], parts[-2], parts[-1]
        elif len(parts) == 2:
            schema, obj = parts[-2], parts[-1]
        elif len(parts) == 1:
            obj = parts[0]

    if not full:
        full_parts = [p for p in [database, schema, obj] if p]
        full = ".".join(full_parts) if full_parts else obj

    return database, schema, obj, full


def build_object_dedup_key(row: dict[str, Any]) -> tuple[str, str, str, str, str, str]:
    """Monta a chave lógica usada para deduplicar objetos no relatório.

    Chave escolhida:
    - papel da conexão: destino BI ou origem;
    - tipo normalizado: table, procedure, function etc.;
    - database;
    - schema;
    - nome do objeto;
    - conexão real associada.

    Essa chave evita duplicar o mesmo objeto quando ele aparece por métodos de
    detecção diferentes, por exemplo `OBJECT_LITERAL` e `TRUNCATE_TABLE`.
    """
    database, schema, obj, _full = split_full_object_name(row)
    return (
        normalize_key(first_present(row, "PapelConexao", "connection_role")),
        normalize_key(normalize_object_type(first_present(row, "TipoObjeto", "object_type", "object_kind"))),
        normalize_key(database),
        normalize_key(schema),
        normalize_key(obj),
        normalize_key(first_present(row, "ConexaoAssociada", "connection_name")),
    )


def clean_and_deduplicate_objects(rows: Iterable[Any]) -> list[dict[str, Any]]:
    """Limpa falsos objetos e consolida registros repetidos.

    Esta função é usada pelo `report_generator.py` antes de publicar as abas
    operacionais. Ela preserva rastreabilidade por meio de contadores e listas
    resumidas de pacotes, componentes, métodos de detecção e evidências SQL.
    """
    grouped: "OrderedDict[tuple[str, str, str, str, str, str], dict[str, Any]]" = OrderedDict()

    for item in rows:
        row = to_plain_dict(item)
        if is_false_object(row):
            continue

        database, schema, obj, full = split_full_object_name(row)
        object_type = normalize_object_type(first_present(row, "TipoObjeto", "object_type", "object_kind"))

        normalized = dict(row)
        normalized["Database"] = database
        normalized["Schema"] = schema
        normalized["Objeto"] = obj
        normalized["NomeCompleto"] = full
        normalized["TipoObjeto"] = object_type

        key = build_object_dedup_key(normalized)

        if key not in grouped:
            grouped[key] = {
                "PapelConexao": first_present(normalized, "PapelConexao", "connection_role"),
                "TipoObjeto": object_type,
                "Database": database,
                "Schema": schema,
                "Objeto": obj,
                "NomeCompleto": full,
                "ConexaoAssociada": first_present(normalized, "ConexaoAssociada", "connection_name"),
                "QtdOcorrenciasParser": 0,
                "_packages": set(),
                "_components": set(),
                "_methods": set(),
                "_evidence": [],
                "Status_HOM": "",
                "Status_PRD": "",
                "Observacao": "Objeto consolidado por chave lógica normalizada.",
            }

        target = grouped[key]
        target["QtdOcorrenciasParser"] += int(row.get("QtdOcorrenciasParser") or 1)

        package_name = first_present(row, "package_name", "PacotesExemplo")
        component = first_present(row, "component_name", "ComponentesExemplo")
        method = first_present(row, "detection_method", "MetodosDeteccao")
        evidence = first_present(row, "sql_text", "EvidenciaSQL")

        if package_name:
            target["_packages"].add(package_name)
        if component:
            target["_components"].add(component)
        if method:
            target["_methods"].add(method)
        if evidence and evidence not in target["_evidence"]:
            target["_evidence"].append(evidence[:180])

    output: list[dict[str, Any]] = []
    for row in grouped.values():
        packages = sorted(row.pop("_packages"))
        components = sorted(row.pop("_components"))
        methods = sorted(row.pop("_methods"))
        evidence = row.pop("_evidence")

        row["QtdPacotes"] = len(packages)
        row["PacotesExemplo"] = ", ".join(packages[:5])
        row["ComponentesExemplo"] = ", ".join(components[:5])
        row["MetodosDeteccao"] = ", ".join(methods[:8])
        row["EvidenciaSQL"] = " | ".join(evidence[:2])
        row["AcaoEsperada"] = action_for_object_type(row["TipoObjeto"])
        output.append(row)

    return sorted(output, key=lambda r: (r.get("PapelConexao", ""), r.get("TipoObjeto", ""), r.get("NomeCompleto", "")))




def is_temp_table_object(row_or_name: Any, config: Any | None = None) -> bool:
    """Indica se o objeto é uma tabela temporária configurada para exclusão.

    Regra de negócio:
    - por padrão, tabelas cujo nome começa com ``#`` são temporárias do SQL Server;
    - o comportamento pode ser desligado via ``ignore_temp_tables``;
    - os prefixos podem ser ampliados via ``temp_table_prefixes``.

    A função valida o tipo do objeto para evitar remover procedures ou outros
    artefatos que por acaso usem caracteres semelhantes no nome.
    """
    if config is not None and not getattr(config, "ignore_temp_tables", True):
        return False

    prefixes = getattr(config, "temp_table_prefixes", ("#",)) if config is not None else ("#",)
    prefixes = tuple(str(prefix).strip().lower() for prefix in prefixes if str(prefix).strip())
    if not prefixes:
        return False

    if isinstance(row_or_name, dict):
        object_type = normalize_object_type(first_present(row_or_name, "TipoObjeto", "object_type", "object_kind"))
        # A regra pedida deve atingir apenas objetos do tipo tabela.
        if object_type != "table":
            return False
        name = first_present(row_or_name, "object_name", "Objeto", "full_object_name", "NomeCompleto", "value")
    else:
        name = str(row_or_name or "")

    normalized_name = normalize_key(normalize_object_name(name))
    return any(normalized_name.startswith(prefix) for prefix in prefixes)


def should_publish_object(row: dict[str, Any], config: Any | None = None) -> bool:
    """Decide se um objeto deve aparecer nas abas operacionais.

    Centraliza filtros para evitar que o relatório publique ruídos técnicos,
    aliases ou tabelas temporárias configuradas para exclusão.
    """
    if is_false_object(row):
        return False
    if is_temp_table_object(row, config=config):
        return False
    return True


def deduplicate_operational_objects(rows: Iterable[Any], config: Any | None = None) -> list[dict[str, Any]]:
    """Compatibilidade usada pelo ``report_generator.py``.

    Aplica os filtros configuráveis antes de chamar a consolidação principal.
    """
    publishable_rows = []
    for item in rows:
        row = to_plain_dict(item)
        if should_publish_object(row, config=config):
            publishable_rows.append(row)
    return clean_and_deduplicate_objects(publishable_rows)

def action_for_object_type(object_type: str) -> str:
    """Define a orientação operacional exibida na planilha."""
    if object_type == "procedure":
        return "Validar/publicar procedure e permissões de execução no ambiente destino"
    if object_type == "function":
        return "Validar/publicar função e permissões de execução no ambiente destino"
    if object_type == "view":
        return "Validar/publicar view e permissões de leitura no ambiente destino"
    return "Validar existência da tabela, estrutura, índices e permissões no ambiente destino"
