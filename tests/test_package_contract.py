from pathlib import Path

from app.ssis_package_parser import _resolve_package_args, parse_package, parse_package_file


def test_resolve_package_args_accepts_both_orders(tmp_path: Path):
    package = tmp_path / "pkg.dtsx"
    package.write_text("<root />", encoding="utf-8")

    package_file, project_name = _resolve_package_args(package, "meu_projeto")
    assert package_file == package
    assert project_name == "meu_projeto"

    package_file, project_name = _resolve_package_args("meu_projeto", package)
    assert package_file == package
    assert project_name == "meu_projeto"


def test_parse_package_legacy_contract_returns_5_items(tmp_path: Path):
    package = tmp_path / "pkg.dtsx"
    package.write_text("<root />", encoding="utf-8")

    result = parse_package(package, "meu_projeto")
    assert isinstance(result, tuple)
    assert len(result) == 5


def test_parse_package_file_returns_structured_result(tmp_path: Path):
    package = tmp_path / "pkg.dtsx"
    package.write_text("<root />", encoding="utf-8")

    result = parse_package_file(package, "meu_projeto")
    assert result.package_name == "pkg"
    assert isinstance(result.connections, list)
    assert isinstance(result.component_usages, list)
    assert isinstance(result.database_objects, list)
    assert isinstance(result.warnings, list)
