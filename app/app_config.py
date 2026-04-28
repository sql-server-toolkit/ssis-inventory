from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AppConfig:
    ignore_disabled: bool = True
    ignore_sql_comments_for_objects: bool = True
    json_output_mode: str = "compact"
    include_raw_sql_in_json: bool = False
    include_raw_sheets: bool = True
    max_sql_preview_chars: int = 180
    # Quando verdadeiro, remove tabelas temporárias SQL Server das abas operacionais.
    ignore_temp_tables: bool = True
    # Prefixos configuráveis para identificar tabelas temporárias.
    temp_table_prefixes: tuple[str, ...] = ("#",)


DEFAULT_CONFIG = AppConfig()


def load_config(config_file: str | Path | None = None) -> AppConfig:
    path = Path(config_file) if config_file else Path("config/application_parameters.json")
    if not path.exists():
        return DEFAULT_CONFIG

    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    json_output_mode = str(data.get("json_output_mode", DEFAULT_CONFIG.json_output_mode)).strip().lower()
    if json_output_mode not in {"compact", "full"}:
        json_output_mode = DEFAULT_CONFIG.json_output_mode

    try:
        max_sql_preview_chars = int(data.get("max_sql_preview_chars", DEFAULT_CONFIG.max_sql_preview_chars))
    except Exception:
        max_sql_preview_chars = DEFAULT_CONFIG.max_sql_preview_chars

    return AppConfig(
        ignore_disabled=bool(data.get("ignore_disabled", DEFAULT_CONFIG.ignore_disabled)),
        ignore_sql_comments_for_objects=bool(data.get("ignore_sql_comments_for_objects", DEFAULT_CONFIG.ignore_sql_comments_for_objects)),
        json_output_mode=json_output_mode,
        include_raw_sql_in_json=bool(data.get("include_raw_sql_in_json", DEFAULT_CONFIG.include_raw_sql_in_json)),
        include_raw_sheets=bool(data.get("include_raw_sheets", DEFAULT_CONFIG.include_raw_sheets)),
        max_sql_preview_chars=max(0, max_sql_preview_chars),
        ignore_temp_tables=bool(data.get("ignore_temp_tables", DEFAULT_CONFIG.ignore_temp_tables)),
        temp_table_prefixes=tuple(str(item) for item in data.get("temp_table_prefixes", list(DEFAULT_CONFIG.temp_table_prefixes))),
    )
