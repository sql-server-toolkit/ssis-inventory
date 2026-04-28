from app.sql_object_extractor import extract_database_objects


def test_does_not_extract_ssis_metadata_as_objects():
    for token in ["OpenRowset", "SqlCommand", "System.String", "s", "t"]:
        assert extract_database_objects(token) == []


def test_exec_is_procedure():
    objs = extract_database_objects("exec dbo.p_processa_carga")
    assert len(objs) == 1
    assert objs[0].object_type == "procedure"
    assert objs[0].object_name == "p_processa_carga"


def test_from_alias_is_not_object():
    objs = extract_database_objects("SELECT * FROM dbo.Cliente c JOIN dbo.Pedido p ON p.IdCliente = c.Id")
    names = {o.object_name for o in objs}
    assert "Cliente" in names
    assert "Pedido" in names
    assert "c" not in names
    assert "p" not in names
