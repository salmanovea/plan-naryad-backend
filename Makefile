run:
	uvicorn src.main:app --reload --port 8090

lint-ruff:
	pre-commit run --all-files ruff
	pre-commit run --all-files ruff-format

lint-mypy:
	pre-commit run --all-files mypy

lint: lint-ruff lint-mypy

test:
	pytest

migrate:
	.venv/bin/alembic revision --autogenerate -m ${msg}

upgrade:
	.venv/bin/alembic upgrade head

downgrade:
	.venv/bin/alembic downgrade -1

history:
	.venv/bin/alembic history
