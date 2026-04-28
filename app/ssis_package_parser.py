from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from app.models import WarningItem
from app.ssis_component_parser import extract_component_usages_and_objects, parse_component_usages
from app.ssis_connection_parser import parse_package_connections


def _config_value(config: Any, name: str, default: Any = None) -> Any:
    if config is None:
        return default
    if isinstance(config, dict):
        return config.get(name, default)
    return getattr(config, name, default)


def parse_package_file(
    package_file: Path | str,
    project_name: str,
    *,
    config: Any = None,
):
    """API principal para parse de pacote SSIS.

    Contrato:
    - primeiro extrai Connection Managers reais;
    - depois passa essas conexões ao parser de componentes;
    - o parser de componentes só preenche connection_name quando consegue resolver
      para um Connection Manager real.
    """
    dtsx_file = Path(package_file)
    if dtsx_file.suffix.lower() != ".dtsx":
        raise ValueError(f"parse_package_file esperava um arquivo .dtsx, recebeu: {dtsx_file}")

    package_name = dtsx_file.stem

    # Mantém compatibilidade com versões anteriores do parse_package_connections.
    try:
        connections = parse_package_connections(
            package_file=dtsx_file,
            project_name=project_name,
            package_name=package_name,
        )
    except TypeError:
        try:
            connections = parse_package_connections(project_name, package_name, dtsx_file)
        except TypeError:
            connections = parse_package_connections(dtsx_file, project_name, package_name)

    usages, objects, warnings = extract_component_usages_and_objects(
        project_name=project_name,
        package_name=package_name,
        dtsx_file=dtsx_file,
        connections=connections,
        ignore_disabled=bool(_config_value(config, "ignore_disabled", False)),
        ignore_sql_comments_for_objects=bool(_config_value(config, "ignore_sql_comments_for_objects", True)),
    )

    if not connections:
        warnings.append(
            WarningItem(
                project_name=project_name,
                package_name=package_name,
                source_file=str(dtsx_file),
                warning_type="NO_CONNECTION_DETECTED",
                message="Nenhuma conexão explícita foi detectada no pacote.",
            )
        )

    return {
        "package_name": package_name,
        "connections": connections,
        "component_usages": usages,
        "database_objects": objects,
        "warnings": warnings,
    }


def parse_package(project_name: str, dtsx_file: Path | str, config: Any = None):
    """Wrapper legado usado pelo main.py antigo.

    Retorna a tupla:
    package_name, connections, usages, objects, warnings
    """
    result = parse_package_file(dtsx_file, project_name, config=config)
    return (
        result["package_name"],
        result["connections"],
        result["component_usages"],
        result["database_objects"],
        result["warnings"],
    )
