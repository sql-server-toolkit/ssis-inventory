import pandas as pd

from app.report_generator import build_promotable_objects


def test_build_promotable_objects_ignores_table_aliases():
    objects_df = pd.DataFrame(
        [
            {
                "project_name": "p",
                "package_name": "pkg",
                "task_path": "flow",
                "component_type": "Microsoft.OLEDBSource",
                "component_name": "src",
                "connection_name": "sd0241_sisacoe",
                "sql_text": "SELECT * FROM SD0241O.T5008_REQUERIMENTO T5008",
                "object_type": "table",
                "database_name": None,
                "schema_name": None,
                "object_name": "T5008",
                "full_object_name": "T5008",
                "detection_method": "SQL_PATTERN",
                "confidence_level": "Low",
                "source_file": "pkg.dtsx",
            },
            {
                "project_name": "p",
                "package_name": "pkg",
                "task_path": "flow",
                "component_type": "Microsoft.OLEDBSource",
                "component_name": "src",
                "connection_name": "sd0241_sisacoe",
                "sql_text": "SELECT * FROM SD0241O.T5008_REQUERIMENTO T5008",
                "object_type": "table",
                "database_name": None,
                "schema_name": "SD0241O",
                "object_name": "T5008_REQUERIMENTO",
                "full_object_name": "SD0241O.T5008_REQUERIMENTO",
                "detection_method": "SQL_PATTERN",
                "confidence_level": "Medium",
                "source_file": "pkg.dtsx",
            },
        ]
    )

    bi_df, origem_df, review_df = build_promotable_objects(
        objects_df,
        {"sd0241_sisacoe": "ORIGEM_SISTEMA"},
    )

    assert "T5008" not in set(origem_df["Objeto"])
    assert "T5008_REQUERIMENTO" in set(origem_df["Objeto"])
    assert "ALIAS_SQL_IGNORADO" in set(review_df["TipoAchado"])
