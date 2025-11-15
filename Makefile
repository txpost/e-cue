.PHONY: install chat practice learn

VENV_DIR := .venv
PYTHON := $(VENV_DIR)/bin/python
PIP := $(VENV_DIR)/bin/pip

$(PYTHON): requirements.txt
	@python3 -m venv $(VENV_DIR)
	@$(PYTHON) -m pip install --upgrade pip --quiet
	@$(PIP) install -r requirements.txt --quiet --disable-pip-version-check

install: $(PYTHON)

chat: $(PYTHON)
	@$(PYTHON) chat.py

practice: $(PYTHON)
	@$(PYTHON) practice.py

learn: $(PYTHON)
	@$(PYTHON) learn.py

