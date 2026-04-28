from app.report_generator import build_promotable_objects
import pandas as pd


def test_build_promotable_objects_deduplicates_parser_occurrences():
    df = pd.DataFrame([
        {"project_name":"p","package_name":"pkg1","task_path":"t1","component_type":"SqlTaskData","component_name":"c1","connection_name":"d64v38i.sa_licenciamento","sql_text":"truncate table dbo.Clientes","object_type":"table","database_name":None,"schema_name":"dbo","object_name":"Clientes","full_object_name":"dbo.Clientes","detection_method":"TRUNCATE_TABLE","confidence_level":"High","source_file":"a.dtsx"},
        {"project_name":"p","package_name":"pkg1","task_path":"t2","component_type":"Microsoft.OLEDBDestination","component_name":"c2","connection_name":"d64v38i.sa_licenciamento","sql_text":"[dbo].[Clientes]","object_type":"table","database_name":None,"schema_name":"dbo","object_name":"Clientes","full_object_name":"dbo.Clientes","detection_method":"OBJECT_LITERAL","confidence_level":"High","source_file":"a.dtsx"},
    ])
    role_lookup = {"d64v38i.sa_licenciamento":"DESTINO_BI"}
    valid_lookup = {"d64v38i.sa_licenciamento":"d64v38i.sa_licenciamento"}
    bi, source, review = build_promotable_objects(df, role_lookup, valid_lookup)
    assert len(bi) == 1
    assert int(bi.iloc[0]["QtdOcorrenciasParser"]) == 2


def test_build_promotable_objects_reclassifies_procedure_by_name():
    df = pd.DataFrame([
        {"project_name":"p","package_name":"pkg1","task_path":"t1","component_type":"SqlTaskData","component_name":"c1","connection_name":"d64v38i.sa_licenciamento","sql_text":"p_ins_ouro_olho_obra_consulta","object_type":"table","database_name":None,"schema_name":None,"object_name":"p_ins_ouro_olho_obra_consulta","full_object_name":"p_ins_ouro_olho_obra_consulta","detection_method":"OBJECT_LITERAL","confidence_level":"High","source_file":"a.dtsx"},
    ])
    role_lookup = {"d64v38i.sa_licenciamento":"DESTINO_BI"}
    valid_lookup = {"d64v38i.sa_licenciamento":"d64v38i.sa_licenciamento"}
    bi, source, review = build_promotable_objects(df, role_lookup, valid_lookup)
    assert bi.iloc[0]["TipoObjeto"] == "procedure"
