ifeq ($(OS),Windows_NT)
PYTHON := .venv/Scripts/python.exe
BOOTSTRAP_PYTHON := python
else
PYTHON := .venv/bin/python
BOOTSTRAP_PYTHON := python3
endif

.PHONY: dev setup test

dev:
	"$(PYTHON)" run.py

setup:
	$(BOOTSTRAP_PYTHON) -m venv .venv
	"$(PYTHON)" -m pip install -r requirements.txt

test:
	"$(PYTHON)" -m pytest
