from app.sql_object_extractor import extract_objects_from_sql


def _extract(sql, component_type="SqlTaskData"):
    return extract_objects_from_sql(
        project_name="p",
        package_name="pkg",
        task_path="task",
        component_type=component_type,
        component_name="component",
        connection_name="d64v38i.sa_licenciamento",
        sql_text=sql,
        source_file="x.dtsx",
        ignore_sql_comments_for_objects=True,
    )


def test_exec_is_procedure_not_table():
    objs = _extract("exec p_upd_ad0000_aprova_digital_atualiza_destino")
    assert len(objs) == 1
    assert objs[0].object_type == "procedure"
    assert objs[0].object_name == "p_upd_ad0000_aprova_digital_atualiza_destino"


def test_sqltask_literal_p_prefix_is_procedure():
    objs = _extract("p_ins_ouro_olho_obra_consulta")
    assert len(objs) == 1
    assert objs[0].object_type == "procedure"


def test_destination_literal_is_table():
    objs = _extract("[dbo].[bronze_ul0108_boleto]", component_type="Microsoft.OLEDBDestination")
    assert len(objs) == 1
    assert objs[0].object_type == "table"


def test_commented_sql_is_ignored_for_objects():
    objs = _extract("""
        -- truncate table tabela_comentada
        truncate table tabela_ativa
        /* truncate table outra_comentada */
    """)
    names = {obj.object_name for obj in objs}
    assert "tabela_ativa" in names
    assert "tabela_comentada" not in names
    assert "outra_comentada" not in names
