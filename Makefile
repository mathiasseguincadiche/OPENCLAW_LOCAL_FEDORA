.PHONY: install validate test lint shellcheck ci

install:
	python3 -m venv .venv
	.venv/bin/python -m pip install -e ".[dev]"

validate:
	.venv/bin/clawfedora validate

lint:
	.venv/bin/ruff check src tests
	.venv/bin/mypy src

shellcheck:
	bash -n menu.sh
	for file in scripts/linux/*.sh scripts/linux/lib/*.sh; do bash -n "$$file"; done
	shellcheck menu.sh scripts/linux/*.sh scripts/linux/lib/*.sh

test:
	.venv/bin/pytest -q --cov=clawfedora --cov-report=term-missing

ci: validate lint shellcheck test
