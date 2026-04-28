from __future__ import annotations

from pathlib import Path


class DiscoveryError(Exception):
    pass


def discover_project_files(project_folder: str) -> dict[str, list[Path]]:
    root = Path(project_folder)
    if not root.exists() or not root.is_dir():
        raise DiscoveryError(f"Pasta do projeto não encontrada: {project_folder}")

    dtproj_files = sorted(root.rglob("*.dtproj"))
    dtsx_files = sorted(root.rglob("*.dtsx"))
    conmgr_files = sorted(root.rglob("*.conmgr"))

    if not dtproj_files and not dtsx_files:
        raise DiscoveryError(
            "Nenhum arquivo .dtproj ou .dtsx foi encontrado na pasta informada."
        )

    return {
        "dtproj": dtproj_files,
        "dtsx": dtsx_files,
        "conmgr": conmgr_files,
    }
