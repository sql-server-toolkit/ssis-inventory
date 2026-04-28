from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any


@dataclass
class ProjectInfo:
    project_name: str
    project_file: str
    package_files: list[str] = field(default_factory=list)
    connection_manager_files: list[str] = field(default_factory=list)


@dataclass
class ConnectionInfo:
    project_name: str
    package_name: str | None
    scope: str
    connection_name: str
    connection_type: str | None
    provider: str | None
    connection_string_raw: str | None
    server_or_data_source: str | None
    initial_catalog: str | None
    expression_based: bool
    source_file: str


@dataclass
class ComponentUsage:
    project_name: str
    package_name: str
    task_path: str
    component_type: str
    component_name: str
    connection_name: str | None
    sql_text: str | None
    source_file: str


@dataclass
class DatabaseObjectReference:
    project_name: str
    package_name: str
    task_path: str
    component_type: str
    component_name: str
    connection_name: str | None
    sql_text: str | None
    object_type: str | None
    database_name: str | None
    schema_name: str | None
    object_name: str | None
    full_object_name: str
    detection_method: str
    confidence_level: str
    source_file: str


@dataclass
class WarningItem:
    project_name: str
    package_name: str | None
    source_file: str
    warning_type: str
    message: str


@dataclass
class PackageParseResult:
    project_name: str
    package_name: str
    source_file: str
    connections: list[ConnectionInfo] = field(default_factory=list)
    component_usages: list[ComponentUsage] = field(default_factory=list)
    database_objects: list[DatabaseObjectReference] = field(default_factory=list)
    warnings: list[WarningItem] = field(default_factory=list)

    def as_legacy_tuple(self) -> tuple[str, list[ConnectionInfo], list[ComponentUsage], list[DatabaseObjectReference], list[WarningItem]]:
        return (
            self.package_name,
            self.connections,
            self.component_usages,
            self.database_objects,
            self.warnings,
        )


@dataclass
class AnalysisResult:
    project: ProjectInfo
    connections: list[Any] = field(default_factory=list)
    component_usages: list[Any] = field(default_factory=list)
    database_objects: list[Any] = field(default_factory=list)
    warnings: list[Any] = field(default_factory=list)

    @staticmethod
    def _serialize_item(item: Any) -> dict[str, Any]:
        if is_dataclass(item):
            return asdict(item)
        if isinstance(item, dict):
            return dict(item)
        if isinstance(item, str):
            return {"warning_type": "GENERIC_WARNING", "message": item}
        if item is None:
            return {"warning_type": "GENERIC_WARNING", "message": ""}
        return {"warning_type": type(item).__name__, "message": str(item)}

    def to_dict(self) -> dict[str, Any]:
        return {
            "project": self._serialize_item(self.project),
            "connections": [self._serialize_item(item) for item in self.connections],
            "component_usages": [self._serialize_item(item) for item in self.component_usages],
            "database_objects": [self._serialize_item(item) for item in self.database_objects],
            "warnings": [self._serialize_item(item) for item in self.warnings],
        }
