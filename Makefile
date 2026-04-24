SHELL := /bin/bash

PYTHON ?= python3
VENV := backend/.venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
UVICORN := $(VENV)/bin/uvicorn
PYTEST := $(VENV)/bin/pytest

.PHONY: install install-backend install-frontend backend frontend test eval eval-rank clean check

# --- install ---------------------------------------------------------------

install: install-backend install-frontend

install-backend:
	@test -d $(VENV) || $(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip >/dev/null
	$(PIP) install -e "backend[dev]"

install-frontend:
	cd frontend && npm install

# --- run -------------------------------------------------------------------

backend:
	cd backend && ../$(VENV)/bin/uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

# --- test ------------------------------------------------------------------

test:
	cd backend && ../$(VENV)/bin/pytest -q

check:
	@$(PY) -c "from app.main import app; print('backend import OK')" || (echo "backend import FAILED"; exit 1)
	cd frontend && npm run typecheck

# --- eval ------------------------------------------------------------------

# Usage: make eval FILE=eval/dataset/resumes/jane.pdf TRUTH=eval/dataset/ground_truth/jane.json
# Or:    make eval DATASET=eval/dataset SUBSET=edge_cases
# Or:    make eval DATASET=eval/dataset MODEL=claude-haiku-4-5
eval:
	$(PY) -m eval.harness run \
		$(if $(FILE),--file $(FILE),) \
		$(if $(TRUTH),--truth $(TRUTH),) \
		$(if $(DATASET),--dataset $(DATASET),) \
		$(if $(SUBSET),--subset $(SUBSET),) \
		$(if $(MODEL),--model $(MODEL),)

# Usage: make eval-rank JDPAIR=eval/dataset/jd_pairs/python_ml
eval-rank:
	$(PY) -m eval.harness rank --jd-pair $(JDPAIR) $(if $(MODEL),--model $(MODEL),)

clean:
	rm -rf data/uploads/* data/app.db eval/out
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
