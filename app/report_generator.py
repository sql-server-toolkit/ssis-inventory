"""Geração do relatório Excel/JSON do projeto ssis-inventory.

Este módulo transforma a saída bruta do parser SSIS em um relatório operacional
para comunicação entre BI, Desenvolvimento e Infraestrutura.

Regras preservadas nesta versão:
- conexões de destino BI: databases com prefixo sa_, dm_, dw_ e cn_smtp_corporativo;
- conexões de origem: todas as demais, incluindo FLATFILE;
- conexões FLATFILE são preservadas individualmente por caminho;
- objetos falsos como OpenRowset, SqlCommand e System.String não entram nas abas operacionais;
- objetos de tabela iniciados com prefixos parametrizados, como "#", podem ser ignorados;
- objetos são deduplicados por chave lógica normalizada;
- JSON compacto por padrão, respeitando application_parameters.json.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

try:
    from app.models import AnalysisResult
except Exception:  # pragma: no cover - mantém execução em testes isolados
    AnalysisResult = Any  # type: ignore


BI_DATABASE_PREFIXES = ("sa_", "dm_", "dw_")
BI_SPECIAL_CONNECTION_NAMES = {"cn_smtp_corporativo"}

BI_DESTINATION_ROLE = "DESTINO_BI"
SOURCE_CONNECTION_ROLE = "ORIGEM_SISTEMA"

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

TABLE_TYPE_ALIASES = {
    "table_or_view",
    "view_or_table",
    "object_literal",
}

EDITABLE_COLUMNS = {
    "Servidor_HOM_Ajustar",
    "Database_HOM_Ajustar",
    "Servidor_PRD_Ajustar",
    "Database_PRD_Ajustar",
    "Status_HOM",
    "Status_PRD",
    "Observacao",
}

OPERATIONAL_SHEET_NAMES = {
    "Resumo",
    "Conexões_BI_Destino",
    "Conexões_BI_Origem",
    "Objetos_BI_Destino",
    "Objetos_BI_Origem",
    "Warnings",
}


# =========================================================
# Conversão e normalização básica
# =========================================================

def _to_plain_dict(value: Any) -> dict[str, Any]:
    """Converte dataclass, dict ou objeto simples para dicionário.

    O projeto passou por várias versões de contrato entre módulos. Esta função
    evita que o relatório quebre quando recebe dataclasses, dicts ou objetos
    com método ``to_dict``.
    """
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "to_dict"):
        return dict(value.to_dict())
    if hasattr(value, "__dict__"):
        return dict(vars(value))
    return {"value": value}


def _safe_list(values: Any) -> list[Any]:
    """Normaliza uma coleção opcional para lista."""
    if values is None:
        return []
    if isinstance(values, list):
        return values
    if isinstance(values, tuple):
        return list(values)
    return [values]


def _to_frame(rows: Iterable[Any] | None) -> pd.DataFrame:
    """Transforma registros heterogêneos em DataFrame."""
    return pd.DataFrame([_to_plain_dict(row) for row in _safe_list(rows)])


def _get_result_value(result: Any, name: str, default: Any = None) -> Any:
    """Obtém atributo tanto de objeto quanto de dicionário."""
    if isinstance(result, dict):
        return result.get(name, default)
    return getattr(result, name, default)


def _first_existing(row: Mapping[str, Any], *names: str, default: str = "") -> str:
    """Retorna o primeiro campo preenchido entre vários nomes possíveis."""
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return default


def _normalize_text(value: Any) -> str:
    """Normaliza texto para exibição.

    Regra importante:
    - valores nulos do pandas, como NaN, não devem virar texto "nan";
    - isso evita que o relatório trate objeto sem schema/database como
      literalmente pertencente ao schema "nan".
    """
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        # Listas/dicts não são esperados aqui, mas mantemos fallback seguro.
        pass

    text = str(value).strip()
    if text.casefold() in {"nan", "none", "null"}:
        return ""
    return " ".join(text.split())


def _normalize_key(value: Any) -> str:
    """Normaliza texto para comparação case-insensitive."""
    return _normalize_text(value).casefold()


def _sanitize_filename(value: str | None) -> str:
    """Sanitiza nome do projeto para gerar arquivos."""
    value = (value or "projeto_ssis").strip().lower()
    value = re.sub(r"[^a-zA-Z0-9_-]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "projeto_ssis"


def _clean_object_name(name: Any) -> str:
    """Remove delimitadores SQL comuns e pontuação final."""
    value = _normalize_text(name)
    value = value.replace("[", "").replace("]", "")
    value = value.strip(".;")
    return value


# =========================================================
# Configuração
# =========================================================

def _config_value(config: Any, name: str, default: Any) -> Any:
    """Lê configuração sem acoplar o relatório à implementação de AppConfig."""
    if config is None:
        return default
    return getattr(config, name, default)


def _ignore_temp_tables_enabled(config: Any) -> bool:
    """Indica se tabelas temporárias devem ser removidas do relatório."""
    return bool(_config_value(config, "ignore_temp_tables", True))


def _temp_table_prefixes(config: Any) -> tuple[str, ...]:
    """Retorna prefixos configurados para tabelas temporárias."""
    prefixes = _config_value(config, "temp_table_prefixes", ["#"])
    if not prefixes:
        return ("#",)
    return tuple(str(prefix).casefold() for prefix in prefixes)


# =========================================================
# Classificação e consolidação de conexões
# =========================================================

def _is_bi_destination_connection(row: Mapping[str, Any]) -> bool:
    """Classifica se a conexão pertence ao destino BI.

    Regra de negócio:
    - database iniciando com sa_, dm_ ou dw_ é destino BI;
    - cn_smtp_corporativo também entra como dependência corporativa do BI;
    - todo o restante, incluindo FLATFILE, é origem/dependência externa.
    """
    connection_name = _first_existing(row, "connection_name", "ConexaoRepresentativa").casefold()
    database = _first_existing(row, "initial_catalog", "Database_DEV_Atual").casefold()

    if connection_name in BI_SPECIAL_CONNECTION_NAMES:
        return True
    return database.startswith(BI_DATABASE_PREFIXES)


def _connection_role(row: Mapping[str, Any]) -> str:
    """Retorna o papel operacional da conexão."""
    return BI_DESTINATION_ROLE if _is_bi_destination_connection(row) else SOURCE_CONNECTION_ROLE


def _connection_action(row: Mapping[str, Any], role: str) -> str:
    """Define a ação esperada para Infra/BI conforme o tipo de conexão."""
    connection_type = _first_existing(row, "connection_type", "TipoConexao").upper()
    connection_name = _first_existing(row, "connection_name", "ConexaoRepresentativa").casefold()

    if connection_name == "cn_smtp_corporativo" or connection_type == "SMTP":
        return "Validar SMTP corporativo no ambiente destino"
    if connection_type == "FLATFILE":
        return "Validar caminho do arquivo, permissões e disponibilidade no servidor de execução"
    if role == BI_DESTINATION_ROLE:
        return "Ajustar connection manager para servidor/database correspondente em HOM e PRD"
    return "Validar acesso ao sistema fonte, servidor, usuário/permissões e firewall"


def _connection_group_key(row: Mapping[str, Any], role: str) -> tuple[str, ...]:
    """Monta chave lógica de deduplicação de conexões.

    FLATFILE fica separado por nome lógico e caminho, pois cada arquivo pode
    exigir ajuste próprio no servidor de execução.
    """
    connection_type = _first_existing(row, "connection_type", "TipoConexao").upper()
    provider = _first_existing(row, "provider", "Provider")
    server = _first_existing(row, "server_or_data_source", "Servidor_DEV_Atual")
    database = _first_existing(row, "initial_catalog", "Database_DEV_Atual")
    connection_name = _first_existing(row, "connection_name", "ConexaoRepresentativa", default="UNNAMED_CONNECTION")
    raw = _first_existing(row, "connection_string_raw", "ConnectionStringsExemplo")

    if connection_type == "FLATFILE":
        return (
            role,
            "FLATFILE",
            _normalize_key(connection_name),
            _normalize_key(raw),
        )

    return (
        role,
        _normalize_key(connection_type),
        _normalize_key(provider),
        _normalize_key(server),
        _normalize_key(database),
    )


def _remove_redundant_unnamed_connections(connections_df: pd.DataFrame) -> pd.DataFrame:
    """Remove UNNAMED_CONNECTION quando há conexão nomeada com mesma string.

    O parser pode retornar uma conexão FLATFILE nomeada e outra UNNAMED com o
    mesmo caminho. Para a planilha operacional, isso vira ruído.
    """
    if connections_df.empty or "connection_name" not in connections_df.columns:
        return connections_df

    df = connections_df.copy()
    df["__name"] = df["connection_name"].fillna("").astype(str).str.strip().str.upper()
    df["__raw"] = df.get("connection_string_raw", "").fillna("").astype(str).str.strip()

    named_raw_values = set(df.loc[df["__name"] != "UNNAMED_CONNECTION", "__raw"])
    mask_redundant = (df["__name"] == "UNNAMED_CONNECTION") & df["__raw"].isin(named_raw_values)
    df = df.loc[~mask_redundant].drop(columns=["__name", "__raw"])
    return df


def _short_join(values: Iterable[Any], limit: int = 10) -> str:
    """Concatena valores únicos com limite para manter o Excel legível."""
    unique: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in unique:
            unique.append(text)
    if len(unique) <= limit:
        return ", ".join(unique)
    return ", ".join(unique[:limit]) + " ..."


def _build_connection_adjustments(connections_df: pd.DataFrame, project_name: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Gera abas operacionais de conexões BI Destino e BI Origem."""
    if connections_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    df = _remove_redundant_unnamed_connections(connections_df)
    records: dict[tuple[str, ...], dict[str, Any]] = {}

    for raw_row in df.to_dict("records"):
        row = dict(raw_row)
        role = _connection_role(row)
        key = _connection_group_key(row, role)

        connection_name = _first_existing(row, "connection_name", default="UNNAMED_CONNECTION")
        connection_type = _first_existing(row, "connection_type")
        provider = _first_existing(row, "provider")
        server = _first_existing(row, "server_or_data_source")
        database = _first_existing(row, "initial_catalog")
        package_name = _first_existing(row, "package_name")
        raw_connection = _first_existing(row, "connection_string_raw")

        if key not in records:
            records[key] = {
                "Projeto": project_name,
                "PapelConexao": role,
                "ConexaoRepresentativa": connection_name,
                "TipoConexao": connection_type,
                "Provider": provider,
                "Servidor_DEV_Atual": server,
                "Database_DEV_Atual": database,
                "Servidor_HOM_Ajustar": "",
                "Database_HOM_Ajustar": "",
                "Servidor_PRD_Ajustar": "",
                "Database_PRD_Ajustar": "",
                "QtdOcorrencias": 0,
                "QtdPacotes": 0,
                "Status_HOM": "",
                "Status_PRD": "",
                "Observacao": "",
                "PacotesOndeAparece": "",
                "NomesConexaoEncontrados": "",
                "ConnectionStringsExemplo": "",
                "AcaoEsperada": _connection_action(row, role),
                "_pacotes": [],
                "_nomes": [],
                "_strings": [],
            }

        item = records[key]
        item["QtdOcorrencias"] += 1
        item["_pacotes"].append(package_name)
        item["_nomes"].append(connection_name)
        item["_strings"].append(raw_connection)

        if item["ConexaoRepresentativa"] == "UNNAMED_CONNECTION" and connection_name != "UNNAMED_CONNECTION":
            item["ConexaoRepresentativa"] = connection_name

    rows: list[dict[str, Any]] = []
    for item in records.values():
        pacotes = [value for value in item.pop("_pacotes") if value]
        nomes = [value for value in item.pop("_nomes") if value]
        strings = [value for value in item.pop("_strings") if value]

        item["QtdPacotes"] = len(set(pacotes))
        item["PacotesOndeAparece"] = _short_join(pacotes)
        item["NomesConexaoEncontrados"] = _short_join(nomes, limit=20)
        item["ConnectionStringsExemplo"] = " | ".join(dict.fromkeys(strings[:2]))
        rows.append(item)

    output = pd.DataFrame(rows)
    if output.empty:
        return pd.DataFrame(), pd.DataFrame()

    columns = [
        "Projeto",
        "PapelConexao",
        "ConexaoRepresentativa",
        "TipoConexao",
        "Provider",
        "Servidor_DEV_Atual",
        "Database_DEV_Atual",
        "Servidor_HOM_Ajustar",
        "Database_HOM_Ajustar",
        "Servidor_PRD_Ajustar",
        "Database_PRD_Ajustar",
        "QtdOcorrencias",
        "QtdPacotes",
        "Status_HOM",
        "Status_PRD",
        "Observacao",
        "PacotesOndeAparece",
        "NomesConexaoEncontrados",
        "ConnectionStringsExemplo",
        "AcaoEsperada",
    ]
    output = output.reindex(columns=columns)
    output = output.sort_values(
        ["PapelConexao", "TipoConexao", "Servidor_DEV_Atual", "Database_DEV_Atual", "ConexaoRepresentativa"],
        na_position="last",
    )

    return (
        output[output["PapelConexao"] == BI_DESTINATION_ROLE].copy(),
        output[output["PapelConexao"] == SOURCE_CONNECTION_ROLE].copy(),
    )


def _connection_lookup(connections_df: pd.DataFrame) -> dict[str, str]:
    """Cria mapa connection_name -> papel operacional da conexão."""
    lookup: dict[str, str] = {}
    if connections_df.empty:
        return lookup

    for row in connections_df.to_dict("records"):
        name = _first_existing(row, "connection_name")
        if name:
            lookup[_normalize_key(name)] = _connection_role(row)

    return lookup


# =========================================================
# Normalização e consolidação de objetos
# =========================================================

def _normalize_object_type(object_type: Any) -> str:
    """Normaliza tipo de objeto para as abas operacionais."""
    value = _normalize_key(object_type)
    if value in TABLE_TYPE_ALIASES:
        return "table"
    if value in {"proc", "stored_procedure", "stored procedure"}:
        return "procedure"
    return value or "unknown"


def _is_false_object_name(object_name: Any, full_name: Any = "") -> bool:
    """Retorna True quando o objeto capturado é ruído técnico do SSIS."""
    candidates = {
        _normalize_key(_clean_object_name(object_name)),
        _normalize_key(_clean_object_name(full_name)),
    }
    candidates.discard("")

    if not candidates:
        return True

    for candidate in candidates:
        if candidate in FALSE_OBJECT_NAMES:
            return True
        if len(candidate) == 1 and candidate.isalpha():
            return True

    return False


def _should_ignore_temp_table(object_type: str, object_name: str, config: Any) -> bool:
    """Aplica regra configurável para ignorar tabelas temporárias."""
    if object_type != "table":
        return False
    if not _ignore_temp_tables_enabled(config):
        return False

    object_key = _normalize_key(_clean_object_name(object_name))
    return any(object_key.startswith(prefix) for prefix in _temp_table_prefixes(config))


def _split_full_object_name(row: Mapping[str, Any]) -> tuple[str, str, str, str]:
    """Obtém database, schema, object_name e full_name normalizados."""
    database = _clean_object_name(_first_existing(row, "database_name", "database", "Database"))
    schema = _clean_object_name(_first_existing(row, "schema_name", "schema", "Schema"))
    obj = _clean_object_name(_first_existing(row, "object_name", "Objeto"))
    full = _clean_object_name(_first_existing(row, "full_object_name", "full_name", "NomeCompleto"))

    if not obj and full:
        parts = [part for part in full.split(".") if part]
        if len(parts) >= 3:
            database, schema, obj = parts[-3], parts[-2], parts[-1]
        elif len(parts) == 2:
            schema, obj = parts[-2], parts[-1]
        elif len(parts) == 1:
            obj = parts[0]

    if not full:
        full = ".".join(part for part in [database, schema, obj] if part)

    return database, schema, obj, full or obj


def _object_action(object_type: str, role: str) -> str:
    """Define orientação operacional por tipo e papel da conexão."""
    if object_type == "procedure":
        return "Validar/publicar procedure e permissões de execução"
    if object_type == "function":
        return "Validar/publicar função e permissões de execução"
    if object_type == "view":
        return "Validar/publicar view e dependências"
    if role == SOURCE_CONNECTION_ROLE:
        return "Validar existência/acesso ao objeto no sistema fonte"
    return "Validar existência da tabela, estrutura, índices e permissões"


def _format_object_row(row: Mapping[str, Any], role_lookup: dict[str, str], config: Any) -> dict[str, Any] | None:
    """Converte objeto bruto do parser em objeto operacional limpo."""
    connection_name = _first_existing(row, "connection_name", "ConexaoAssociada")
    role = role_lookup.get(_normalize_key(connection_name), SOURCE_CONNECTION_ROLE)

    object_type = _normalize_object_type(_first_existing(row, "object_type", "TipoObjeto"))
    database, schema, obj, full = _split_full_object_name(row)

    if _is_false_object_name(obj, full):
        return None
    if _should_ignore_temp_table(object_type, obj, config):
        return None

    package_name = _first_existing(row, "package_name", "PacotesExemplo")
    component_name = _first_existing(row, "component_name", "ComponentesExemplo")
    detection_method = _first_existing(row, "detection_method", "MetodosDeteccao")
    sql_text = _first_existing(row, "sql_text", "EvidenciaSQL")

    return {
        "PapelConexao": role,
        "TipoObjeto": object_type,
        "Database": database,
        "Schema": schema,
        "Objeto": obj,
        "NomeCompleto": full,
        "ConexaoAssociada": connection_name,
        "QtdOcorrenciasParser": 1,
        "QtdPacotes": 1 if package_name else 0,
        "Status_HOM": "",
        "Status_PRD": "",
        "Observacao": "Objeto consolidado por chave lógica normalizada.",
        "PacotesExemplo": package_name,
        "ComponentesExemplo": component_name,
        "MetodosDeteccao": detection_method,
        "EvidenciaSQL": sql_text[:300] if sql_text else "",
        "AcaoEsperada": _object_action(object_type, role),
    }


def _object_dedup_key(row: Mapping[str, Any]) -> tuple[str, ...]:
    """Chave lógica para deduplicar objetos operacionais."""
    return (
        _normalize_key(row.get("PapelConexao")),
        _normalize_key(row.get("TipoObjeto")),
        _normalize_key(row.get("Database")),
        _normalize_key(row.get("Schema")),
        _normalize_key(row.get("Objeto")),
        _normalize_key(row.get("ConexaoAssociada")),
    )


def _merge_unique_text(existing: str, new_value: str, limit: int = 5) -> str:
    """Mescla textos separados por vírgula, preservando valores únicos."""
    values: list[str] = []
    for source in [existing, new_value]:
        for item in str(source or "").split(","):
            text = item.strip()
            if text and text not in values:
                values.append(text)
    if len(values) <= limit:
        return ", ".join(values)
    return ", ".join(values[:limit]) + " ..."


def _is_missing_object_part(value: Any) -> bool:
    """Indica se database/schema está ausente ou foi capturado como nulo textual."""
    return _normalize_key(value) in {"", "nan", "none", "null"}


def _schema_values_are_compatible(left: Any, right: Any) -> bool:
    """Compara schemas permitindo ausência e default dbo.

    Muitos componentes SSIS informam apenas `[Tabela]`, enquanto comandos SQL
    podem informar `dbo.Tabela`. Para inventário operacional, esses registros
    representam o mesmo objeto quando conexão e nome da tabela são iguais.
    """
    left_key = _normalize_key(left)
    right_key = _normalize_key(right)

    if left_key == right_key:
        return True
    if _is_missing_object_part(left_key) or _is_missing_object_part(right_key):
        return True

    # Em SQL Server, dbo é o schema padrão mais comum.
    return {left_key, right_key} <= {"", "dbo"}


def _database_values_are_compatible(left: Any, right: Any) -> bool:
    """Compara databases permitindo ausência em um dos lados."""
    left_key = _normalize_key(left)
    right_key = _normalize_key(right)

    if left_key == right_key:
        return True
    return _is_missing_object_part(left_key) or _is_missing_object_part(right_key)


def _weak_object_dedup_key(row: Mapping[str, Any]) -> tuple[str, ...]:
    """Chave auxiliar para encontrar duplicidades com database/schema incompletos."""
    return (
        _normalize_key(row.get("PapelConexao")),
        _normalize_key(row.get("TipoObjeto")),
        _normalize_key(row.get("Objeto")),
        _normalize_key(row.get("ConexaoAssociada")),
    )


def _choose_best_object_part(existing: Any, candidate: Any) -> str:
    """Escolhe o valor mais informativo entre database/schema atuais e novos."""
    existing_text = _normalize_text(existing)
    candidate_text = _normalize_text(candidate)

    if not existing_text:
        return candidate_text
    if not candidate_text:
        return existing_text

    # Preferimos schema explícito diferente de dbo quando existir.
    if existing_text.casefold() == "dbo" and candidate_text.casefold() != "dbo":
        return candidate_text

    return existing_text


def _refresh_object_full_name(row: dict[str, Any]) -> None:
    """Recalcula NomeCompleto após mesclar database/schema/objeto."""
    full_name = ".".join(
        part
        for part in [
            _normalize_text(row.get("Database")),
            _normalize_text(row.get("Schema")),
            _normalize_text(row.get("Objeto")),
        ]
        if part
    )
    row["NomeCompleto"] = full_name or _normalize_text(row.get("Objeto"))


def _merge_object_rows(target: dict[str, Any], row: Mapping[str, Any]) -> None:
    """Mescla duas linhas que representam o mesmo objeto lógico."""
    target["Database"] = _choose_best_object_part(target.get("Database"), row.get("Database"))
    target["Schema"] = _choose_best_object_part(target.get("Schema"), row.get("Schema"))
    _refresh_object_full_name(target)

    target["QtdOcorrenciasParser"] += int(row.get("QtdOcorrenciasParser") or 1)
    target["QtdPacotes"] = max(int(target.get("QtdPacotes") or 0), int(row.get("QtdPacotes") or 0), 1)
    target["PacotesExemplo"] = _merge_unique_text(target.get("PacotesExemplo", ""), row.get("PacotesExemplo", ""))
    target["ComponentesExemplo"] = _merge_unique_text(target.get("ComponentesExemplo", ""), row.get("ComponentesExemplo", ""))
    target["MetodosDeteccao"] = _merge_unique_text(target.get("MetodosDeteccao", ""), row.get("MetodosDeteccao", ""), limit=8)

    evidence = str(row.get("EvidenciaSQL") or "").strip()
    if evidence and evidence not in str(target.get("EvidenciaSQL") or ""):
        target["EvidenciaSQL"] = " | ".join([x for x in [target.get("EvidenciaSQL", ""), evidence] if x])[:600]


def _find_compatible_existing_key(
    grouped: Mapping[tuple[str, ...], dict[str, Any]],
    row: Mapping[str, Any],
) -> tuple[str, ...] | None:
    """Localiza linha já agrupada que seja o mesmo objeto com metadados incompletos."""
    weak_key = _weak_object_dedup_key(row)

    for existing_key, existing_row in grouped.items():
        if _weak_object_dedup_key(existing_row) != weak_key:
            continue
        if not _database_values_are_compatible(existing_row.get("Database"), row.get("Database")):
            continue
        if not _schema_values_are_compatible(existing_row.get("Schema"), row.get("Schema")):
            continue
        return existing_key

    return None


def _deduplicate_objects(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Consolida objetos repetidos mantendo contadores e exemplos.

    Chave lógica principal:
    - PapelConexao
    - TipoObjeto
    - Database
    - Schema
    - Objeto
    - ConexaoAssociada

    Complemento de robustez:
    - quando database/schema vierem vazios em uma ocorrência e preenchidos em
      outra, o objeto é mesclado, pois o parser pode capturar `[Tabela]` em um
      componente e `dbo.Tabela` em uma instrução SQL.
    """
    grouped: dict[tuple[str, ...], dict[str, Any]] = {}

    for row in rows:
        normalized_row = dict(row)
        normalized_row["Database"] = _normalize_text(normalized_row.get("Database"))
        normalized_row["Schema"] = _normalize_text(normalized_row.get("Schema"))
        normalized_row["Objeto"] = _clean_object_name(normalized_row.get("Objeto"))
        _refresh_object_full_name(normalized_row)

        exact_key = _object_dedup_key(normalized_row)
        merge_key = exact_key if exact_key in grouped else _find_compatible_existing_key(grouped, normalized_row)

        if merge_key is None:
            grouped[exact_key] = normalized_row
            continue

        _merge_object_rows(grouped[merge_key], normalized_row)

    return sorted(
        grouped.values(),
        key=lambda row: (
            row.get("PapelConexao", ""),
            row.get("TipoObjeto", ""),
            row.get("NomeCompleto", ""),
            row.get("ConexaoAssociada", ""),
        ),
    )


def _build_promotable_objects(objects_df: pd.DataFrame, connections_df: pd.DataFrame, config: Any) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Gera objetos separados entre BI Destino e BI Origem."""
    if objects_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    role_lookup = _connection_lookup(connections_df)
    rows: list[dict[str, Any]] = []

    for row in objects_df.to_dict("records"):
        formatted = _format_object_row(row, role_lookup, config)
        if formatted:
            rows.append(formatted)

    rows = _deduplicate_objects(rows)
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(), pd.DataFrame()

    columns = [
        "PapelConexao",
        "TipoObjeto",
        "Database",
        "Schema",
        "Objeto",
        "NomeCompleto",
        "ConexaoAssociada",
        "QtdOcorrenciasParser",
        "QtdPacotes",
        "Status_HOM",
        "Status_PRD",
        "Observacao",
        "PacotesExemplo",
        "ComponentesExemplo",
        "MetodosDeteccao",
        "EvidenciaSQL",
        "AcaoEsperada",
    ]
    df = df.reindex(columns=columns)

    return (
        df[df["PapelConexao"] == BI_DESTINATION_ROLE].copy(),
        df[df["PapelConexao"] == SOURCE_CONNECTION_ROLE].copy(),
    )


# =========================================================
# Resumo e JSON
# =========================================================

def _summary_frame(
    project_name: str,
    connections_df: pd.DataFrame,
    component_usages_df: pd.DataFrame,
    objects_df: pd.DataFrame,
    bi_connections: pd.DataFrame,
    source_connections: pd.DataFrame,
    bi_objects: pd.DataFrame,
    source_objects: pd.DataFrame,
    warnings_df: pd.DataFrame,
) -> pd.DataFrame:
    """Cria resumo executivo do processamento."""
    rows = [
        ("Projeto", project_name),
        ("Conexões brutas detectadas", len(connections_df)),
        ("Componentes/usos brutos detectados", len(component_usages_df)),
        ("Objetos brutos detectados", len(objects_df)),
        ("Conexões BI Destino consolidadas", len(bi_connections)),
        ("Conexões BI Origem consolidadas", len(source_connections)),
        ("Objetos BI Destino únicos", len(bi_objects)),
        ("Objetos BI Origem únicos", len(source_objects)),
        ("Warnings", len(warnings_df)),
    ]
    return pd.DataFrame(rows, columns=["Métrica", "Valor"])


def _compact_json_payload(
    project_name: str,
    summary_df: pd.DataFrame,
    bi_connections: pd.DataFrame,
    source_connections: pd.DataFrame,
    bi_objects: pd.DataFrame,
    source_objects: pd.DataFrame,
    warnings_df: pd.DataFrame,
) -> dict[str, Any]:
    """Monta JSON compacto para reduzir tamanho do arquivo final."""
    return {
        "project_name": project_name,
        "summary": dict(zip(summary_df["Métrica"], summary_df["Valor"])),
        "connection_adjustments": {
            "bi_destination": bi_connections.to_dict("records"),
            "source": source_connections.to_dict("records"),
        },
        "promotable_objects": {
            "bi_destination": bi_objects.to_dict("records"),
            "source": source_objects.to_dict("records"),
        },
        "warnings": warnings_df.to_dict("records"),
    }


def _full_json_payload(result: Any) -> dict[str, Any]:
    """Monta JSON completo quando solicitado para auditoria."""
    if hasattr(result, "to_dict"):
        return result.to_dict()
    if isinstance(result, dict):
        return result
    return _to_plain_dict(result)


# =========================================================
# Formatação Excel
# =========================================================

def _suggest_column_width(column_name: str, series: pd.Series) -> int:
    """Calcula largura de coluna equilibrando conteúdo e legibilidade."""
    values = [len(str(column_name))]
    if not series.empty:
        values += [len(str(value)) for value in series.head(200).fillna("")]
    max_content = max(values)

    if column_name in {"ConnectionStringsExemplo", "EvidenciaSQL", "PacotesOndeAparece", "PacotesExemplo", "NomesConexaoEncontrados"}:
        return min(max(max_content, 35), 80)
    if column_name in {"AcaoEsperada", "Observacao"}:
        return min(max(max_content, 30), 60)
    return min(max(max_content + 2, 12), 35)


def _apply_workbook_format(writer: pd.ExcelWriter, sheet_frames: dict[str, pd.DataFrame]) -> None:
    """Aplica formatação visual às abas do Excel."""
    workbook = writer.book

    default_header = workbook.add_format({
        "bold": True,
        "font_color": "white",
        "bg_color": "#1F4E78",
        "border": 1,
        "align": "center",
        "valign": "vcenter",
        "text_wrap": True,
    })
    bi_header = workbook.add_format({
        "bold": True,
        "font_color": "white",
        "bg_color": "#548235",
        "border": 1,
        "align": "center",
        "valign": "vcenter",
        "text_wrap": True,
    })
    source_header = workbook.add_format({
        "bold": True,
        "font_color": "white",
        "bg_color": "#5B9BD5",
        "border": 1,
        "align": "center",
        "valign": "vcenter",
        "text_wrap": True,
    })
    warning_header = workbook.add_format({
        "bold": True,
        "font_color": "white",
        "bg_color": "#C00000",
        "border": 1,
        "align": "center",
        "valign": "vcenter",
        "text_wrap": True,
    })

    text_format = workbook.add_format({"text_wrap": True, "valign": "top"})
    editable_format = workbook.add_format({"bg_color": "#FFF2CC", "text_wrap": True, "valign": "top"})
    number_format = workbook.add_format({"num_format": "0", "valign": "top"})

    for sheet_name, df in sheet_frames.items():
        if sheet_name not in writer.sheets:
            continue

        worksheet = writer.sheets[sheet_name]
        worksheet.freeze_panes(1, 0)

        if sheet_name in {"Conexões_BI_Destino", "Objetos_BI_Destino"}:
            header_format = bi_header
        elif sheet_name in {"Conexões_BI_Origem", "Objetos_BI_Origem"}:
            header_format = source_header
        elif sheet_name == "Warnings":
            header_format = warning_header
        else:
            header_format = default_header

        if df.empty:
            worksheet.write(0, 0, "Sem registros", header_format)
            worksheet.set_column(0, 0, 25, text_format)
            continue

        for col_idx, column_name in enumerate(df.columns):
            worksheet.write(0, col_idx, column_name, header_format)
            cell_format = editable_format if column_name in EDITABLE_COLUMNS else text_format
            if column_name.startswith("Qtd") or column_name == "Valor":
                cell_format = number_format
            worksheet.set_column(col_idx, col_idx, _suggest_column_width(column_name, df[column_name]), cell_format)

        worksheet.autofilter(0, 0, max(len(df), 1), max(len(df.columns) - 1, 0))

        if sheet_name in OPERATIONAL_SHEET_NAMES:
            worksheet.set_landscape()
            worksheet.fit_to_pages(1, 0)


# =========================================================
# Exportação principal
# =========================================================

def export_inventory_report(result: Any, output_folder: str | Path, config: Any = None, **_: Any) -> tuple[str, str]:
    """Exporta o inventário SSIS para Excel e JSON.

    Esta assinatura é compatível com ``main.py``, que chama
    ``export_analysis(result, output_folder, config=config)``.
    """
    output_path = Path(output_folder)
    output_path.mkdir(parents=True, exist_ok=True)

    project = _get_result_value(result, "project", {})
    project_dict = _to_plain_dict(project)
    project_name = project_dict.get("project_name") or _get_result_value(result, "project_name", "projeto_ssis")

    connections_df = _to_frame(_get_result_value(result, "connections", []))
    component_usages_df = _to_frame(_get_result_value(result, "component_usages", []))
    objects_df = _to_frame(_get_result_value(result, "database_objects", []))
    warnings_df = _to_frame(_get_result_value(result, "warnings", []))

    bi_connections, source_connections = _build_connection_adjustments(connections_df, project_name)
    bi_objects, source_objects = _build_promotable_objects(objects_df, connections_df, config)

    summary_df = _summary_frame(
        project_name,
        connections_df,
        component_usages_df,
        objects_df,
        bi_connections,
        source_connections,
        bi_objects,
        source_objects,
        warnings_df,
    )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"deployment_inventory_{_sanitize_filename(project_name)}_{timestamp}"
    excel_file = output_path / f"{base_name}.xlsx"
    json_file = output_path / f"{base_name}.json"

    include_raw_sheets = bool(_config_value(config, "include_raw_sheets", True))
    json_output_mode = str(_config_value(config, "json_output_mode", "compact")).casefold()

    sheet_frames: dict[str, pd.DataFrame] = {
        "Resumo": summary_df,
        "Conexões_BI_Destino": bi_connections,
        "Conexões_BI_Origem": source_connections,
        "Objetos_BI_Destino": bi_objects,
        "Objetos_BI_Origem": source_objects,
        "Warnings": warnings_df,
    }

    if include_raw_sheets:
        sheet_frames.update({
            "Connections_Raw": connections_df,
            "ComponentUsages_Raw": component_usages_df,
            "Objects_Raw": objects_df,
        })

    with pd.ExcelWriter(excel_file, engine="xlsxwriter") as writer:
        for sheet_name, frame in sheet_frames.items():
            frame.to_excel(writer, sheet_name=sheet_name[:31], index=False)
        _apply_workbook_format(writer, {name[:31]: frame for name, frame in sheet_frames.items()})

    if json_output_mode == "full":
        payload = _full_json_payload(result)
    else:
        payload = _compact_json_payload(
            project_name,
            summary_df,
            bi_connections,
            source_connections,
            bi_objects,
            source_objects,
            warnings_df,
        )

    json_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return str(excel_file), str(json_file)


def export_analysis(result: Any, output_folder: str | Path, **kwargs: Any) -> tuple[str, str]:
    """Wrapper mantido para compatibilidade com o contrato usado pelo ``main.py``."""
    return export_inventory_report(result, output_folder, **kwargs)
