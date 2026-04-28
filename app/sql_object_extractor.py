from __future__ import annotations

import re
from typing import Optional

from app.models import DatabaseObjectReference

# Identificador SQL Server / Oracle em ate 3 partes:
# tabela | schema.tabela | database.schema.tabela | [schema].[tabela]
IDENTIFIER = r"(?:\[[^\]]+\]|\"[^\"]+\"|[A-Za-z_#][\w$#@]*)(?:\s*\.\s*(?:\[[^\]]+\]|\"[^\"]+\"|[A-Za-z_#][\w$#@]*)){0,2}"

SQL_KEYWORDS = {
    "select", "from", "where", "join", "inner", "left", "right", "full", "outer", "cross",
    "on", "group", "order", "by", "having", "union", "all", "distinct", "case",
    "when", "then", "else", "end", "as", "and", "or", "not", "null", "is",
    "insert", "into", "update", "delete", "truncate", "table", "exec", "execute",
    "merge", "using", "values", "set", "declare", "begin", "commit", "rollback",
    "go", "create", "alter", "drop", "with", "nolock", "top", "cast", "convert",
    "isnull", "coalesce", "max", "min", "sum", "count", "avg", "char", "replace",
    "sysobjects", "sys", "objects", "type", "name", "xtype",
}

# Itens de metadados SSIS/.NET/XML que nao sao objetos de banco.
NON_DATABASE_OBJECTS = {
    "openrowset", "sqlcommand", "sqlcommands", "sqlstatementsource", "commandtext",
    "string", "system.string", "system", "objectdata", "scriptproject", "scriptmain",
    "microsoft.package", "executables", "properties", "property", "connections", "connection",
    "connectionmanager", "connectionmanagerid", "input", "output", "inputs", "outputs",
    "columns", "column", "externalmetadata", "externalmetadatacolumn", "component",
    "components", "package", "pipeline", "path", "layout", "xml", "dts", "stock", "ole",
    "oledb", "sqltaskdata", "parameters", "parameter", "variables", "variable",
    # aliases curtos que estavam aparecendo como objetos
    "s", "t", "x", "a", "b", "c", "i", "j", "d",
}

PROCEDURE_NAME_PREFIXES = ("p_", "sp_", "usp_", "pr_", "proc_")


def strip_sql_comments(sql: str | None) -> str:
    """Remove comentarios SQL de bloco e linha, preservando strings simples."""
    if not sql:
        return ""

    text = str(sql)
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)

    cleaned_lines: list[str] = []
    for line in text.splitlines():
        in_single_quote = False
        i = 0
        out: list[str] = []
        while i < len(line):
            ch = line[i]
            nxt = line[i + 1] if i + 1 < len(line) else ""
            if ch == "'":
                out.append(ch)
                if nxt == "'":
                    out.append(nxt)
                    i += 2
                    continue
                in_single_quote = not in_single_quote
                i += 1
                continue
            if not in_single_quote and ch == "-" and nxt == "-":
                break
            out.append(ch)
            i += 1
        cleaned_lines.append("".join(out))

    return "\n".join(cleaned_lines)


def _clean_identifier_token(token: str | None) -> str:
    if not token:
        return ""
    value = str(token).strip()
    value = value.strip("[]")
    value = value.strip('"')
    value = value.strip("'")
    return value.strip()


def normalize_identifier(identifier: str | None) -> tuple[str | None, str | None, str | None, str]:
    raw = str(identifier or "").strip().rstrip(";,")
    parts = [_clean_identifier_token(part) for part in re.split(r"\s*\.\s*", raw) if part.strip()]
    parts = [p for p in parts if p]

    if len(parts) >= 3:
        database_name, schema_name, object_name = parts[-3], parts[-2], parts[-1]
    elif len(parts) == 2:
        database_name, schema_name, object_name = None, parts[0], parts[1]
    elif len(parts) == 1:
        database_name, schema_name, object_name = None, None, parts[0]
    else:
        database_name, schema_name, object_name = None, None, ""

    full_name = ".".join(part for part in [database_name, schema_name, object_name] if part)
    return database_name, schema_name, object_name, full_name


def _looks_like_identifier_literal(sql_text: str | None) -> bool:
    text = str(sql_text or "").strip()
    if not text:
        return False
    if re.search(r"\s", text):
        return False
    if re.search(r"[,;()=+\-*/]", text):
        return False
    return bool(re.fullmatch(IDENTIFIER, text, flags=re.IGNORECASE))


def _looks_like_procedure_name(object_name: str | None) -> bool:
    name = (object_name or "").strip().lower()
    return name.startswith(PROCEDURE_NAME_PREFIXES)


def _is_false_object(identifier: str | None) -> bool:
    raw = str(identifier or "").strip()
    if not raw:
        return True

    database_name, schema_name, object_name, full_name = normalize_identifier(raw)
    object_low = (object_name or "").lower()
    schema_low = (schema_name or "").lower()
    full_low = (full_name or raw).strip().strip("[]").lower()
    raw_low = raw.strip().strip("[]").lower()

    if object_low in NON_DATABASE_OBJECTS or full_low in NON_DATABASE_OBJECTS or raw_low in NON_DATABASE_OBJECTS:
        return True
    if object_low in SQL_KEYWORDS or full_low in SQL_KEYWORDS:
        return True
    if schema_low == "system" or full_low.startswith("system."):
        return True
    if len(object_low) == 1 and object_low.isalpha():
        return True
    if object_low.startswith("@"):
        return True
    if object_low.startswith("#") and len(object_low) <= 2:
        return True
    if re.fullmatch(r"\d+", object_low or ""):
        return True
    if "\\" in raw or "://" in raw_low:
        return True
    if any(token in full_low for token in ["openrowset", "sqlcommand", "sqlstatementsource", "commandtext"]):
        return True

    return False


def _add_object(
    results: list[DatabaseObjectReference],
    seen: set[tuple[str, str, str | None]],
    *,
    project_name: str,
    package_name: str,
    task_path: str,
    component_type: str,
    component_name: str,
    connection_name: str | None,
    sql_text: str | None,
    source_file: str,
    object_type: str,
    identifier: str,
    detection_method: str,
    confidence_level: str = "High",
) -> None:
    database_name, schema_name, object_name, full_name = normalize_identifier(identifier)
    if not object_name or not full_name:
        return
    if _is_false_object(identifier) or _is_false_object(object_name):
        return

    # Normaliza o tipo quando o nome claramente indica procedure.
    if object_type in {"table", "table_or_view"} and _looks_like_procedure_name(object_name):
        object_type = "procedure"
        detection_method = "PROCEDURE_LITERAL"
        confidence_level = "Medium"

    key = (object_type.lower(), full_name.lower(), connection_name)
    if key in seen:
        return
    seen.add(key)

    results.append(
        DatabaseObjectReference(
            project_name=project_name,
            package_name=package_name,
            task_path=task_path,
            component_type=component_type,
            component_name=component_name,
            connection_name=connection_name,
            sql_text=sql_text,
            object_type=object_type,
            database_name=database_name,
            schema_name=schema_name,
            object_name=object_name,
            full_object_name=full_name,
            detection_method=detection_method,
            confidence_level=confidence_level,
            source_file=source_file,
        )
    )


def extract_objects_from_sql(
    *,
    project_name: str = "",
    package_name: str = "",
    task_path: str = "",
    component_type: str = "",
    component_name: str = "",
    connection_name: str | None = None,
    sql_text: str | None = None,
    source_file: str = "",
    ignore_sql_comments_for_objects: bool = True,
    **_: object,
) -> list[DatabaseObjectReference]:
    """Extrai objetos de banco de uma instrucao SQL ou literal de destino SSIS.

    Funcao compativel com o contrato atual do ssis_component_parser.py.
    Aceita metadados do pacote via argumentos nomeados e ignora kwargs extras.
    """
    if not sql_text:
        return []

    original_sql = str(sql_text)
    sql = strip_sql_comments(original_sql) if ignore_sql_comments_for_objects else original_sql
    sql = re.sub(r"\s+", " ", sql).strip()
    if not sql:
        return []

    results: list[DatabaseObjectReference] = []
    seen: set[tuple[str, str, str | None]] = set()

    # 1) Stored procedures explicitas.
    for match in re.finditer(rf"\bexec(?:ute)?\s+(?:@\w+\s*=\s*)?({IDENTIFIER})", sql, flags=re.IGNORECASE):
        _add_object(
            results,
            seen,
            project_name=project_name,
            package_name=package_name,
            task_path=task_path,
            component_type=component_type,
            component_name=component_name,
            connection_name=connection_name,
            sql_text=original_sql,
            source_file=source_file,
            object_type="procedure",
            identifier=match.group(1),
            detection_method="EXEC_STATEMENT",
        )

    # 2) Literal puro em SqlTaskData ou destino OLE DB.
    if _looks_like_identifier_literal(sql):
        _, _, object_name, _ = normalize_identifier(sql)
        if _is_false_object(sql) or _is_false_object(object_name):
            return results

        if _looks_like_procedure_name(object_name) or component_type.lower() == "sqltaskdata":
            _add_object(
                results,
                seen,
                project_name=project_name,
                package_name=package_name,
                task_path=task_path,
                component_type=component_type,
                component_name=component_name,
                connection_name=connection_name,
                sql_text=original_sql,
                source_file=source_file,
                object_type="procedure",
                identifier=sql,
                detection_method="PROCEDURE_LITERAL",
                confidence_level="Medium" if not _looks_like_procedure_name(object_name) else "High",
            )
            return results

        _add_object(
            results,
            seen,
            project_name=project_name,
            package_name=package_name,
            task_path=task_path,
            component_type=component_type,
            component_name=component_name,
            connection_name=connection_name,
            sql_text=original_sql,
            source_file=source_file,
            object_type="table",
            identifier=sql,
            detection_method="OBJECT_LITERAL",
        )
        return results

    # 3) Tabelas/views em comandos SQL.
    patterns: list[tuple[str, str, str]] = [
        ("table_or_view", rf"\bfrom\s+({IDENTIFIER})", "FROM_CLAUSE"),
        ("table_or_view", rf"\bjoin\s+({IDENTIFIER})", "JOIN_CLAUSE"),
        ("table", rf"\binsert\s+into\s+({IDENTIFIER})", "INSERT_INTO"),
        ("table", rf"\bupdate\s+({IDENTIFIER})", "UPDATE_STATEMENT"),
        ("table", rf"\bdelete\s+from\s+({IDENTIFIER})", "DELETE_FROM"),
        ("table", rf"\btruncate\s+table\s+({IDENTIFIER})", "TRUNCATE_TABLE"),
        ("table", rf"\bmerge\s+into\s+({IDENTIFIER})", "MERGE_INTO"),
        ("table", rf"\bmerge\s+({IDENTIFIER})", "MERGE_STATEMENT"),
    ]

    for object_type, pattern, method in patterns:
        for match in re.finditer(pattern, sql, flags=re.IGNORECASE):
            identifier = match.group(1)
            if identifier.strip().startswith("("):
                continue
            _add_object(
                results,
                seen,
                project_name=project_name,
                package_name=package_name,
                task_path=task_path,
                component_type=component_type,
                component_name=component_name,
                connection_name=connection_name,
                sql_text=original_sql,
                source_file=source_file,
                object_type=object_type,
                identifier=identifier,
                detection_method=method,
            )

    return results


# Alias legado mantido para imports antigos.
def extract_database_objects(
    sql_text: str | None,
    ignore_sql_comments: bool = True,
) -> list[DatabaseObjectReference]:
    return extract_objects_from_sql(
        sql_text=sql_text,
        ignore_sql_comments_for_objects=ignore_sql_comments,
    )
