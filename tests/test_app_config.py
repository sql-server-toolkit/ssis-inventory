import json

from app.app_config import load_config


def test_load_config_from_json(tmp_path):
    config_file = tmp_path / "application_parameters.json"
    config_file.write_text(json.dumps({
        "ignore_disabled": True,
        "ignore_sql_comments_for_objects": True,
    }), encoding="utf-8")

    config = load_config(config_file)

    assert config.ignore_disabled is True
    assert config.ignore_sql_comments_for_objects is True
