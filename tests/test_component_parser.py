from lxml import etree

from app.ssis_component_parser import resolve_connection_name, build_connection_aliases


def test_component_path_is_not_connection_name():
    assert resolve_connection_name(
        "Package\\Fluxo\\Componente",
        aliases={"d64v38i.sa_licenciamento": "d64v38i.sa_licenciamento"},
        valid_names={"d64v38i.sa_licenciamento"},
    ) is None


def test_connection_manager_ref_is_resolved():
    xml = """
    <DTS:Executable xmlns:DTS="www.microsoft.com/SqlServer/Dts">
      <DTS:ConnectionManagers>
        <DTS:ConnectionManager DTS:ObjectName="d64v38i.sa_licenciamento" DTS:DTSID="{ABC}" DTS:refId="Package.ConnectionManagers[d64v38i.sa_licenciamento]" />
      </DTS:ConnectionManagers>
    </DTS:Executable>
    """
    root = etree.fromstring(xml.encode("utf-8"))
    aliases = build_connection_aliases(root)
    resolved = resolve_connection_name(
        "Package.ConnectionManagers[d64v38i.sa_licenciamento]",
        aliases=aliases,
        valid_names={"d64v38i.sa_licenciamento"},
    )
    assert resolved == "d64v38i.sa_licenciamento"
