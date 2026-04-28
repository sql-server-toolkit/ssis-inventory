from pathlib import Path

from app.ssis_component_parser import extract_component_usages_and_objects


def test_ignore_disabled_execute_sql_task(tmp_path: Path):
    dtsx = tmp_path / "pkg.dtsx"
    dtsx.write_text(
        """<?xml version='1.0' encoding='utf-8'?>
<DTS:Executable xmlns:DTS="www.microsoft.com/SqlServer/Dts" DTS:ObjectName="Package">
  <DTS:Executables>
    <DTS:Executable DTS:ObjectName="Disabled SQL Task" DTS:Disabled="True">
      <SQLTask:SqlTaskData xmlns:SQLTask="www.microsoft.com/sqlserver/dts/tasks/sqltask"
         SQLTask:SqlStatementSource="truncate table dbo.tabela_desabilitada" />
    </DTS:Executable>
  </DTS:Executables>
</DTS:Executable>
""",
        encoding="utf-8",
    )

    usages_all, objects_all, _ = extract_component_usages_and_objects(
        package_file=dtsx,
        project_name="p",
        package_name="pkg",
        ignore_disabled=False,
    )
    usages_enabled, objects_enabled, _ = extract_component_usages_and_objects(
        package_file=dtsx,
        project_name="p",
        package_name="pkg",
        ignore_disabled=True,
    )

    assert len(usages_all) == 1
    assert len(objects_all) == 1
    assert usages_enabled == []
    assert objects_enabled == []
