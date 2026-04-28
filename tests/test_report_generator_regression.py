from app.report_generator import _normalize_object_type, _is_false_object_name, _should_ignore_temp_table


class MockConfig:
    ignore_temp_tables = True
    temp_table_prefixes = ["#"]


def test_table_or_view_is_normalized_to_table():
    assert _normalize_object_type("table_or_view") == "table"


def test_false_objects_are_not_published():
    assert _is_false_object_name("OpenRowset")
    assert _is_false_object_name("SqlCommand")
    assert _is_false_object_name("System.String")
    assert _is_false_object_name("s")


def test_temp_tables_are_ignored_when_enabled():
    assert _should_ignore_temp_table("table", "#tmp", MockConfig())
    assert not _should_ignore_temp_table("table", "clientes", MockConfig())
