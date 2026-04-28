from app.report_generator import sanitize_filename


def test_sanitize_filename():
    assert sanitize_filename("Projeto SSIS Licenciamento") == "projeto_ssis_licenciamento"
