from app.ssis_connection_parser import (
    infer_server_database_from_connection_name,
    parse_connection_string,
    normalize_connection_type,
)


def test_parse_connection_string_sql_server():
    provider, server, database = parse_connection_string(
        "Provider=SQLNCLI11.1;Data Source=d64v38i;Initial Catalog=sa_licenciamento;Integrated Security=SSPI;"
    )
    assert provider == "SQLNCLI11.1"
    assert server == "d64v38i"
    assert database == "sa_licenciamento"


def test_infer_server_database_from_logical_name():
    server, database = infer_server_database_from_connection_name("d64v38i.sa_licenciamento")
    assert server == "d64v38i"
    assert database == "sa_licenciamento"


def test_normalize_connection_type_oledb():
    assert normalize_connection_type("OLEDB") == "OLEDB"
