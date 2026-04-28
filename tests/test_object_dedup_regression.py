from app.report_generator import (
    _deduplicate_objects,
    _normalize_text,
)


def test_normalize_text_treats_nan_as_empty():
    assert _normalize_text("nan") == ""
    assert _normalize_text(None) == ""


def test_deduplicate_objects_merges_missing_schema_with_dbo():
    rows = [
        {
            "PapelConexao": "DESTINO_BI",
            "TipoObjeto": "table",
            "Database": "",
            "Schema": "",
            "Objeto": "bronze_ad0000_aprova_digital",
            "NomeCompleto": "bronze_ad0000_aprova_digital",
            "ConexaoAssociada": "d64v38i.sa_licenciamento",
            "QtdOcorrenciasParser": 5,
            "QtdPacotes": 1,
            "PacotesExemplo": "pkg_a",
            "ComponentesExemplo": "comp_a",
            "MetodosDeteccao": "TRUNCATE_TABLE",
            "EvidenciaSQL": "truncate table bronze_ad0000_aprova_digital",
        },
        {
            "PapelConexao": "DESTINO_BI",
            "TipoObjeto": "table",
            "Database": "",
            "Schema": "dbo",
            "Objeto": "bronze_ad0000_aprova_digital",
            "NomeCompleto": "dbo.bronze_ad0000_aprova_digital",
            "ConexaoAssociada": "d64v38i.sa_licenciamento",
            "QtdOcorrenciasParser": 1,
            "QtdPacotes": 1,
            "PacotesExemplo": "pkg_b",
            "ComponentesExemplo": "comp_b",
            "MetodosDeteccao": "OBJECT_LITERAL",
            "EvidenciaSQL": "[dbo].[bronze_ad0000_aprova_digital]",
        },
    ]

    result = _deduplicate_objects(rows)

    assert len(result) == 1
    assert result[0]["QtdOcorrenciasParser"] == 6
    assert result[0]["Schema"] == "dbo"


def test_deduplicate_objects_merges_missing_oracle_schema_when_same_connection():
    rows = [
        {
            "PapelConexao": "ORIGEM_SISTEMA",
            "TipoObjeto": "table",
            "Database": "",
            "Schema": "SD0241O",
            "Objeto": "t5046_texto_docum",
            "NomeCompleto": "SD0241O.t5046_texto_docum",
            "ConexaoAssociada": "sd0241_sisacoe",
            "QtdOcorrenciasParser": 3,
            "QtdPacotes": 1,
        },
        {
            "PapelConexao": "ORIGEM_SISTEMA",
            "TipoObjeto": "table",
            "Database": "",
            "Schema": "",
            "Objeto": "t5046_texto_docum",
            "NomeCompleto": "t5046_texto_docum",
            "ConexaoAssociada": "sd0241_sisacoe",
            "QtdOcorrenciasParser": 3,
            "QtdPacotes": 1,
        },
    ]

    result = _deduplicate_objects(rows)

    assert len(result) == 1
    assert result[0]["Schema"] == "SD0241O"
    assert result[0]["QtdOcorrenciasParser"] == 6
