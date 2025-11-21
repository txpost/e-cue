.PHONY: dev install enrich enrich-all search venv chroma-server

VENV = .venv
PYTHON = $(VENV)/bin/python3
PIP = $(VENV)/bin/pip

venv:
	@if [ ! -d "$(VENV)" ]; then \
		echo "Creating virtual environment..."; \
		python3 -m venv $(VENV); \
	fi

install: venv
	@echo "Installing dependencies..."
	@$(PIP) install --upgrade pip
	@$(PIP) install -r requirements.txt

dev: venv
	@$(PYTHON) e-cue.py

enrich: venv
	@$(PYTHON) e-cue.py enrich $(ID)

enrich-all: venv
	@$(PYTHON) e-cue.py enrich-all

search: venv
	@$(PYTHON) e-cue.py search "$(QUERY)" --limit $(LIMIT)

chroma-server: venv
	@echo "Starting ChromaDB server on localhost:8000..."
	@echo "Press Ctrl+C to stop the server."
	@$(PYTHON) start_chroma_server.py localhost 8000

