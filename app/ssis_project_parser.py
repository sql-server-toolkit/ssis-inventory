from __future__ import annotations

import logging
from pathlib import Path

from lxml import etree

from app.models import ProjectInfo

logger = logging.getLogger(__name__)


def parse_project_file(dtproj_file: Path, discovered_dtsx: list[Path], discovered_conmgr: list[Path]) -> ProjectInfo:
    project_name = dtproj_file.stem

    try:
        etree.parse(str(dtproj_file))
    except Exception as exc:
        logger.warning("Falha ao ler .dtproj %s: %s", dtproj_file, exc)

    return ProjectInfo(
        project_name=project_name,
        project_file=str(dtproj_file),
        package_files=[str(path) for path in discovered_dtsx],
        connection_manager_files=[str(path) for path in discovered_conmgr],
    )
