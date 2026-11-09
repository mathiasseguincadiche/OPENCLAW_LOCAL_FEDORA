# Commandes de développement du dépôt. Lancer `make` seul affiche cette aide.
# Elles ne touchent ni au système Fedora ni à l'installation : pour l'atelier, utiliser ./menu.sh.

.DEFAULT_GOAL := help
.PHONY: help install validate test docs lint shellcheck ci native-schema native-tools native-prompt native-cloud

help: ## Afficher cette aide
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-14s %s\n", $$1, $$2}'

install: ## Créer .venv et installer le dépôt avec ses outils de développement
	python3 -m venv .venv
	.venv/bin/python -m pip install -e ".[dev]"

validate: ## Vérifier la cohérence des fichiers de configuration
	.venv/bin/clawfedora validate

lint: ## Style (ruff) et typage (mypy) du code Python
	.venv/bin/ruff check src tests scripts/validation plugins
	.venv/bin/mypy src
	.venv/bin/mypy plugins/openwebui

shellcheck: ## Syntaxe et analyse statique des scripts shell
	bash -n menu.sh
	for file in scripts/linux/*.sh scripts/linux/lib/*.sh; do bash -n "$$file"; done
	shellcheck menu.sh scripts/linux/*.sh scripts/linux/lib/*.sh

test: ## Lancer tous les tests avec la couverture
	.venv/bin/pytest -q --cov=clawfedora --cov-report=term-missing

docs: ## Rejouer seulement les contrôles de la documentation (liens, commandes, cohérence)
	.venv/bin/pytest -q tests/test_documentation.py tests/test_documentation_accuracy.py tests/test_documentation_contract.py tests/test_documentation_navigation.py

ci: validate lint shellcheck test ## Enchaîner tous les contrôles avant une PR

native-schema: ## Avec le vrai OpenClaw : la configuration générée est acceptée
	.venv/bin/python scripts/validation/check_openclaw_schema.py

native-tools: ## Avec le vrai OpenClaw : les outils du plugin géré sont chargés
	.venv/bin/python scripts/validation/check_agent_toolkit.py

native-prompt: ## Avec le vrai OpenClaw : les consignes ne sont pas tronquées
	.venv/bin/python scripts/validation/check_prompt_size.py

native-cloud: ## Avec le vrai OpenClaw : un tour cloud passe par la passerelle locale
	.venv/bin/python scripts/validation/check_cloud_route.py
