from __future__ import annotations

import argparse
import logging
from pathlib import Path

from app.app_config import load_config
from app.logger_config import configure_logging
from app.models import AnalysisResult, ProjectInfo, WarningItem
from app.project_discovery import discover_project_files
from app.report_generator import export_analysis
from app.ssis_connection_parser import parse_conmgr_file
from app.ssis_package_parser import parse_package
from app.ssis_project_parser import parse_project_file

logger = logging.getLogger(__name__)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Lê um projeto SSIS e gera inventário de conexões e objetos de banco."
    )
    parser.add_argument("--project-folder", required=True, help="Pasta raiz do projeto SSIS")
    parser.add_argument("--output-folder", required=True, help="Pasta de saída dos relatórios")
    parser.add_argument("--config-file", default="config/application_parameters.json", help="Arquivo JSON de parâmetros da aplicação")
    parser.add_argument("--log-level", default="INFO", help="INFO, DEBUG, WARNING...")
    return parser


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    configure_logging(args.log_level)
    config = load_config(args.config_file)
    logger.info("Parâmetros carregados: ignore_disabled=%s, ignore_sql_comments_for_objects=%s, json_output_mode=%s", config.ignore_disabled, config.ignore_sql_comments_for_objects, config.json_output_mode)

    files = discover_project_files(args.project_folder)

    dtproj_files = files["dtproj"]
    dtsx_files = files["dtsx"]
    conmgr_files = files["conmgr"]

    if dtproj_files:
        project = parse_project_file(dtproj_files[0], dtsx_files, conmgr_files)
    else:
        project = ProjectInfo(
            project_name=Path(args.project_folder).name,
            project_file="",
            package_files=[str(path) for path in dtsx_files],
            connection_manager_files=[str(path) for path in conmgr_files],
        )

    connections = []
    component_usages = []
    database_objects = []
    warnings: list[WarningItem] = []

    for conmgr_file in conmgr_files:
        try:
            connections.extend(parse_conmgr_file(project.project_name, conmgr_file))
        except Exception as exc:
            warnings.append(
                WarningItem(
                    project_name=project.project_name,
                    package_name=None,
                    source_file=str(conmgr_file),
                    warning_type="CONMGR_PARSE_ERROR",
                    message=str(exc),
                )
            )

    for dtsx_file in dtsx_files:
        try:
            _, package_connections, usages, objects, package_warnings = parse_package(
                project.project_name,
                dtsx_file,
                config=config,
            )
            connections.extend(package_connections)
            component_usages.extend(usages)
            database_objects.extend(objects)
            warnings.extend(package_warnings)
        except Exception as exc:
            warnings.append(
                WarningItem(
                    project_name=project.project_name,
                    package_name=dtsx_file.stem,
                    source_file=str(dtsx_file),
                    warning_type="PACKAGE_PARSE_ERROR",
                    message=str(exc),
                )
            )

    result = AnalysisResult(
        project=project,
        connections=connections,
        component_usages=component_usages,
        database_objects=database_objects,
        warnings=warnings,
    )

    excel_file, json_file = export_analysis(result, args.output_folder, config=config)
    logger.info("Relatório Excel gerado em: %s", excel_file)
    logger.info("Relatório JSON gerado em: %s", json_file)


if __name__ == "__main__":
    main()
