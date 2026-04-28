from app.object_normalizer import is_temp_table_object, should_publish_object, deduplicate_operational_objects


class ConfigEnabled:
    ignore_temp_tables = True
    temp_table_prefixes = ("#",)


class ConfigDisabled:
    ignore_temp_tables = False
    temp_table_prefixes = ("#",)


def test_temp_table_is_ignored_when_parameter_enabled():
    row = {"TipoObjeto": "table", "Objeto": "#temp_demais_enderecos"}
    assert is_temp_table_object(row, ConfigEnabled()) is True
    assert should_publish_object(row, ConfigEnabled()) is False


def test_temp_table_is_kept_when_parameter_disabled():
    row = {"TipoObjeto": "table", "Objeto": "#temp_demais_enderecos"}
    assert is_temp_table_object(row, ConfigDisabled()) is False
    assert should_publish_object(row, ConfigDisabled()) is True


def test_procedure_starting_with_hash_is_not_filtered_by_table_rule():
    row = {"TipoObjeto": "procedure", "Objeto": "#procedure_name"}
    assert is_temp_table_object(row, ConfigEnabled()) is False


def test_deduplicate_operational_objects_removes_temp_tables():
    rows = [
        {"PapelConexao": "DESTINO_BI", "TipoObjeto": "table", "Objeto": "#temp", "ConexaoAssociada": "conn"},
        {"PapelConexao": "DESTINO_BI", "TipoObjeto": "table", "Objeto": "dbo.Clientes", "ConexaoAssociada": "conn"},
    ]
    result = deduplicate_operational_objects(rows, config=ConfigEnabled())
    assert len(result) == 1
    assert result[0]["Objeto"] == "dbo.Clientes"
