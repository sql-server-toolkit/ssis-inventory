from pathlib import Path

from app.ssis_package_parser import _resolve_package_args


def test_resolve_package_args_accepts_both_orders():
    p1, proj1 = _resolve_package_args("a.dtsx", "meu_projeto")
    assert str(p1).endswith(".dtsx")
    assert proj1 == "meu_projeto"

    p2, proj2 = _resolve_package_args("meu_projeto", "a.dtsx")
    assert str(p2).endswith(".dtsx")
    assert proj2 == "meu_projeto"
