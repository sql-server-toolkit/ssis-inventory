from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable

from app.models import ConnectionInfo


NON_CONNECTION_CREATION_NAMES = {
    "Microsoft.Pipeline",
    "Microsoft.ExecuteSQLTask",
    "Microsoft.ScriptTask",
    "Microsoft.Package",
    "Microsoft.LogProviderSQLServer",
    "STOCK:SEQUENCE",
}

ACTIONABLE_CONNECTION_TYPES = {
    "OLEDB",
    "ADO.NET",
    "ADONET",
    "ODBC",
    "ORACLE",
    "FLATFILE",
    "FILE",
    "EXCEL",
    "SMTP",
}


def _local_name(name: str | None) -> str:
    if not name:
        return ""
    if "}" in name:
        return name.rsplit("}", 1)[-1]
    if ":" in name:
        return name.rsplit(":", 1)[-1]
    return name


def _get_attr(element: ET.Element, *candidate_names: str) -> str | None:
    expected = {name.lower() for name in candidate_names}
    for key, value in element.attrib.items():
        if _local_name(key).lower() in expected and value not in (None, ""):
            return str(value).strip()
    return None


def _all_text_values(element: ET.Element) -> list[str]:
    values: list[str] = []
    for node in element.iter():
        if node.text and node.text.strip():
            values.append(node.text.strip())
        if node.tail and node.tail.strip():
            values.append(node.tail.strip())
        for value in node.attrib.values():
            if value and str(value).strip():
                values.append(str(value).strip())
    return values


def _looks_like_connection_string(value: str | None) -> bool:
    if not value:
        return False
    text = value.lower()
    markers = [
        "data source=",
        "server=",
        "initial catalog=",
        "provider=",
        "user id=",
        "integrated security=",
        "password=",
        "database=",
        "dsn=",
        "host=",
        "smtpserver=",
    ]
    return ";" in value and any(marker in text for marker in markers)


def _find_connection_string(element: ET.Element) -> str | None:
    """Find a connection string anywhere inside a SSIS ConnectionManager node.

    SSIS can store the value in different places depending on version/provider, e.g.:
    - DTS:ConnectionString attribute
    - nested DTS:Property DTS:Name="ConnectionString"
    - nested DTS:ObjectData/DTS:ConnectionManager DTS:ConnectionString="..."
    """
    # 1) Attribute explicitly called ConnectionString/ConnectString.
    for node in element.iter():
        for key, value in node.attrib.items():
            lname = _local_name(key).lower()
            if lname in {"connectionstring", "connectstring"} and value:
                return str(value).strip()

    # 2) Property node whose Name indicates ConnectionString/ConnectString.
    for node in element.iter():
        node_name = _local_name(node.tag).lower()
        prop_name = _get_attr(node, "Name", "PropertyName")
        if node_name == "property" and prop_name:
            if prop_name.lower() in {"connectionstring", "connectstring"}:
                if node.text and node.text.strip():
                    return node.text.strip()
                value_attr = _get_attr(node, "Value")
                if value_attr:
                    return value_attr

    # 3) Any value that looks like a connection string.
    for value in _all_text_values(element):
        if _looks_like_connection_string(value):
            return value.strip()

    return None


def parse_connection_string(connection_string: str | None) -> tuple[str | None, str | None, str | None]:
    if not connection_string:
        return None, None, None

    parts: dict[str, str] = {}
    for item in connection_string.split(";"):
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        key = key.strip().lower()
        value = value.strip()
        if key:
            parts[key] = value

    provider = parts.get("provider")
    server = (
        parts.get("data source")
        or parts.get("server")
        or parts.get("address")
        or parts.get("addr")
        or parts.get("network address")
        or parts.get("host")
        or parts.get("dsn")
        or parts.get("smtpserver")
    )
    database = parts.get("initial catalog") or parts.get("database")
    return provider, server, database


def infer_server_database_from_connection_name(connection_name: str | None) -> tuple[str | None, str | None]:
    """Infer server/database from logical names like d64v38i.sa_licenciamento.

    This is intentionally conservative and used only as fallback when the real
    ConnectionString was not available in the .dtsx XML.
    """
    if not connection_name:
        return None, None

    text = connection_name.strip()
    if not text or text.upper() == "UNKNOWN_CONNECTION":
        return None, None

    # Common package naming convention observed in the generated inventory:
    # d64v38i.sa_licenciamento, d64v38i.dm_licenciamento
    match = re.fullmatch(r"([A-Za-z0-9_-]+)\.([A-Za-z0-9_$#-]+)", text)
    if match:
        return match.group(1), match.group(2)

    return None, None


def normalize_connection_type(creation_name: str | None) -> str | None:
    if not creation_name:
        return None

    text = creation_name.upper().replace(" ", "")

    if "OLEDB" in text:
        return "OLEDB"
    if "ADO.NET" in text or "ADONET" in text:
        return "ADO.NET"
    if "ODBC" in text:
        return "ODBC"
    if "ORACLE" in text:
        return "ORACLE"
    if "FLATFILE" in text:
        return "FLATFILE"
    if "EXCEL" in text:
        return "EXCEL"
    if "SMTP" in text:
        return "SMTP"
    if "FILE" in text:
        return "FILE"

    return creation_name


def _is_probably_connection_manager(element: ET.Element) -> bool:
    lname = _local_name(element.tag).lower()
    if lname != "connectionmanager":
        return False

    creation_name = _get_attr(element, "CreationName")
    object_name = _get_attr(element, "ObjectName")
    connection_string = _find_connection_string(element)

    if creation_name in NON_CONNECTION_CREATION_NAMES:
        return False

    if object_name and object_name.upper() == "UNKNOWN_CONNECTION":
        return False

    normalized_type = normalize_connection_type(creation_name)
    if normalized_type and normalized_type.upper() in ACTIONABLE_CONNECTION_TYPES:
        return True

    if connection_string:
        return True

    # In SSIS, package connection managers often have only ObjectName and a
    # nested object data element. Keep named nodes, but skip empty generic ones.
    if object_name and object_name.strip():
        return True

    return False


def _extract_connection_info(
    element: ET.Element,
    *,
    project_name: str,
    package_name: str | None,
    scope: str,
    source_file: str,
) -> ConnectionInfo | None:
    connection_name = _get_attr(element, "ObjectName", "Name")
    creation_name = _get_attr(element, "CreationName")
    connection_type = normalize_connection_type(creation_name)
    connection_string_raw = _find_connection_string(element)

    if not connection_name or connection_name.upper() == "UNKNOWN_CONNECTION":
        # Try to keep useful connection strings even when the XML lacks ObjectName.
        if connection_string_raw:
            _, inferred_server, inferred_db = parse_connection_string(connection_string_raw)
            connection_name = ".".join([x for x in [inferred_server, inferred_db] if x]) or "UNNAMED_CONNECTION"
        else:
            return None

    if creation_name in NON_CONNECTION_CREATION_NAMES:
        return None

    provider, server, database = parse_connection_string(connection_string_raw)

    inferred_server, inferred_database = infer_server_database_from_connection_name(connection_name)
    server = server or inferred_server
    database = database or inferred_database

    # If the type is absent but the name looks like server.database, treat as OLEDB.
    if not connection_type and server and database:
        connection_type = "OLEDB"

    return ConnectionInfo(
        project_name=project_name,
        package_name=package_name,
        scope=scope,
        connection_name=connection_name,
        connection_type=connection_type,
        provider=provider,
        connection_string_raw=connection_string_raw,
        server_or_data_source=server,
        initial_catalog=database,
        expression_based=False,
        source_file=source_file,
    )


def _deduplicate_connections(connections: Iterable[ConnectionInfo]) -> list[ConnectionInfo]:
    unique: dict[tuple[str | None, str | None, str | None, str | None], ConnectionInfo] = {}
    for conn in connections:
        key = (
            conn.package_name,
            conn.connection_name,
            conn.connection_type,
            conn.source_file,
        )
        # Prefer richer rows with server/database/connection string.
        existing = unique.get(key)
        if existing is None:
            unique[key] = conn
            continue
        existing_score = sum(bool(x) for x in [existing.connection_string_raw, existing.server_or_data_source, existing.initial_catalog])
        new_score = sum(bool(x) for x in [conn.connection_string_raw, conn.server_or_data_source, conn.initial_catalog])
        if new_score > existing_score:
            unique[key] = conn
    return list(unique.values())


def parse_package_connections(
    package_file: str | Path,
    project_name: str,
    package_name: str | None = None,
) -> list[ConnectionInfo]:
    package_path = Path(package_file)
    if package_path.suffix.lower() != ".dtsx":
        raise ValueError(f"parse_package_connections recebeu package_file inválido: {package_file}")

    tree = ET.parse(package_path)
    root = tree.getroot()

    results: list[ConnectionInfo] = []
    for element in root.iter():
        if not _is_probably_connection_manager(element):
            continue
        conn = _extract_connection_info(
            element,
            project_name=project_name,
            package_name=package_name or package_path.stem,
            scope="Package",
            source_file=str(package_path),
        )
        if conn is not None:
            results.append(conn)

    return _deduplicate_connections(results)


def parse_project_connection_file(connection_file: str | Path, project_name: str) -> list[ConnectionInfo]:
    connection_path = Path(connection_file)
    tree = ET.parse(connection_path)
    root = tree.getroot()

    results: list[ConnectionInfo] = []
    for element in root.iter():
        if not _is_probably_connection_manager(element):
            continue
        conn = _extract_connection_info(
            element,
            project_name=project_name,
            package_name=None,
            scope="Project",
            source_file=str(connection_path),
        )
        if conn is not None:
            results.append(conn)
    return _deduplicate_connections(results)


def parse_project_connection_files(connection_files: Iterable[str | Path], project_name: str) -> list[ConnectionInfo]:
    results: list[ConnectionInfo] = []
    for connection_file in connection_files:
        results.extend(parse_project_connection_file(connection_file, project_name))
    return _deduplicate_connections(results)


def parse_conmgr_file(connection_file: str | Path, project_name: str) -> list[ConnectionInfo]:
    """Backward-compatible public contract expected by main.py."""
    return parse_project_connection_file(connection_file, project_name)


def build_connection_lookup(connections: Iterable[ConnectionInfo]) -> dict[str, ConnectionInfo]:
    """Build a lookup by common identifiers available in the current model.

    The current ConnectionInfo model does not expose DTSID, so this lookup is by
    logical connection name and normalized lower-case name. Component parsers can
    still use it to resolve references that contain the visible connection name.
    """
    lookup: dict[str, ConnectionInfo] = {}
    for conn in connections:
        if not conn.connection_name:
            continue
        lookup[conn.connection_name] = conn
        lookup[conn.connection_name.lower()] = conn
    return lookup
