from app.models import ComponentUsage
from app.ssis_component_parser import _objects_from_usage


def _usage(sql):
    return ComponentUsage(
        project_name="p",
        package_name="pkg",
        task_path="task",
        component_type="SqlTaskData",
        component_name="component",
        connection_name="conn",
        sql_text=sql,
        source_file="pkg.dtsx",
    )


def test_ignores_objects_inside_sql_comments():
    usage = _usage("/* SELECT * FROM dbo.tabela_comentada */ SELECT * FROM dbo.tabela_real")
    objects = _objects_from_usage(usage, ignore_sql_comments_for_objects=True)
    names = {obj.full_object_name for obj in objects}

    assert "dbo.tabela_real" in names
    assert "dbo.tabela_comentada" not in names


def test_exec_is_classified_as_procedure_not_table():
    usage = _usage("exec dbo.p_upd_ad0000_aprova_digital_atualiza_destino")
    objects = _objects_from_usage(usage, ignore_sql_comments_for_objects=True)

    assert len(objects) == 1
    assert objects[0].object_type == "procedure"
    assert objects[0].full_object_name == "dbo.p_upd_ad0000_aprova_digital_atualiza_destino"
