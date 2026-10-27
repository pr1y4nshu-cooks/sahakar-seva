#!/usr/bin/env sh
# Start SAHAKAR–SEVA locally against the LOCAL Docker PostgreSQL, apply migrations, seed taxonomy,
# and check health. Safe to re-run: non-destructive, keeps the persistent volume.
#
# Why the explicit exports: compose.yml builds the API's DATABASE_URL from POSTGRES_* and the db
# container is initialised with them. If your root .env points POSTGRES_* at a remote database,
# a plain `docker compose up` would point the API at the wrong credentials. These exports win over
# .env for this command only; your .env is not modified.
#
# Usage (from the repository root):  sh scripts/dev_up.sh
set -eu

export POSTGRES_USER="${LOCAL_POSTGRES_USER:-sahakar}"
export POSTGRES_PASSWORD="${LOCAL_POSTGRES_PASSWORD:-sahakar}"
export POSTGRES_DB="${LOCAL_POSTGRES_DB:-sahakar_seva}"

docker compose up -d
echo "Waiting for the API..."
i=0
until curl -fsS -m 3 http://localhost:8000/api/v1/health >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -gt 60 ]; then
    echo "API did not become healthy; see: docker compose logs api" >&2
    exit 1
  fi
  sleep 2
done

docker compose exec -T api alembic upgrade head
docker compose exec -T api python -m app.db.seed
docker compose exec -T api alembic current
curl -fsS http://localhost:8000/api/v1/health && echo
curl -fsS http://localhost:8000/api/v1/health/db && echo
echo "Web: http://localhost:5173   API: http://localhost:8000   Swagger: http://localhost:8000/docs"
