from app.object_normalizer import clean_and_deduplicate_objects, is_false_object, normalize_object_type


def test_table_or_view_is_normalized_to_table():
    assert normalize_object_type("table_or_view") == "table"
    assert normalize_object_type("view_or_table") == "table"


def test_false_objects_are_filtered():
    assert is_false_object("OpenRowset")
    assert is_false_object("SqlCommand")
    assert is_false_object("System.String")
    assert is_false_object("s")
    assert is_false_object("t")


def test_same_table_from_different_detection_methods_is_single_object():
    rows = [
        {
            "PapelConexao": "DESTINO_BI",
            "object_type": "table_or_view",
            "object_name": "[dbo].[MinhaTabela]",
            "connection_name": "d64v38i.sa_licenciamento",
            "detection_method": "OBJECT_LITERAL",
            "package_name": "pkg1",
        },
        {
            "PapelConexao": "DESTINO_BI",
            "object_type": "table",
            "schema": "dbo",
            "object_name": "MinhaTabela",
            "connection_name": "d64v38i.sa_licenciamento",
            "detection_method": "TRUNCATE_TABLE",
            "package_name": "pkg1",
        },
    ]

    result = clean_and_deduplicate_objects(rows)

    assert len(result) == 1
    assert result[0]["TipoObjeto"] == "table"
    assert result[0]["Objeto"] == "MinhaTabela"
    assert result[0]["QtdOcorrenciasParser"] == 2
