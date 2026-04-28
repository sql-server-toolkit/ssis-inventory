PYTHON := python
VENV := .venv

.PHONY: setup test run clean

setup:
	$(PYTHON) -m venv $(VENV)
	$(VENV)/Scripts/python -m pip install --upgrade pip
	$(VENV)/Scripts/python -m pip install -r requirements.txt

test:
	$(VENV)/Scripts/pytest

run:
	$(VENV)/Scripts/python -m app.main --project-folder "$(PROJECT_FOLDER)" --output-folder "./output"

clean:
	python -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in ['.pytest_cache', 'output']]; [p.unlink() for p in pathlib.Path('.').rglob('*.pyc')]"
