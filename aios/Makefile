.PHONY: install dev test lint typecheck fmt compose-up compose-down

install:            ## 依存関係の同期(uv workspace)
	uv sync

test: install       ## 全テスト実行(CIと同一)
	uv run pytest -q

lint: install       ## ruffによる静的検査
	uv run ruff check .

fmt: install        ## フォーマット
	uv run ruff format .

typecheck: install  ## mypy strict
	uv run mypy packages/core/src packages/common/src

dev: install        ## APIをローカル起動
	uv run uvicorn aios_api.main:app --reload --port 8080

migrate: install    ## スキーマ適用(本番経路)。AIOS_ALEMBIC_URL=<同期ドライバURL> を指定
	uv run alembic -c packages/storage/alembic.ini upgrade head

compose-up:         ## 評価用スタック起動(postgres+pgvector, redis, minio, api)
	docker compose -f infra/docker-compose.yml up -d --build

compose-down:
	docker compose -f infra/docker-compose.yml down -v
