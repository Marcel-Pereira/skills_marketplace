PYTHON := .venv/bin/python

.PHONY: dev setup test

dev:
	$(PYTHON) run.py

setup:
	python3 -m venv .venv
	$(PYTHON) -m pip install -r requirements.txt

test:
	$(PYTHON) -m pytest
