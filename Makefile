.PHONY: install chat

.PHONY: install chat venv

VENV_DIR := .venv
PYTHON := $(VENV_DIR)/bin/python
PIP := $(VENV_DIR)/bin/pip

venv:
	python3 -m venv $(VENV_DIR)

install: venv
	$(PYTHON) -m pip install --upgrade pip
	$(PIP) install -r requirements.txt

chat: install
	$(PYTHON) chat.py

