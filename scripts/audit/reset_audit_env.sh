#!/usr/bin/env sh
# Recreate the THROWAWAY audit database and its isolated API (:8100). Never touches sahakar_seva.
set -eu
cd "$(dirname "$0")/../.."
pkill -f "uvicorn app.main:app --host 127.0.0.1 --port 8100" 2>/dev/null || true
sleep 1
docker compose exec -T db psql -U sahakar -d postgres -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS sahakar_audit_test WITH (FORCE)" -c "CREATE DATABASE sahakar_audit_test OWNER sahakar_test" >/dev/null
docker compose exec -T db psql -U sahakar -d sahakar_audit_test -v ON_ERROR_STOP=1 -c "CREATE EXTENSION IF NOT EXISTS postgis" -c "CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA public" >/dev/null
cd services/api
export DATABASE_URL='postgresql+psycopg://sahakar_test:sahakar_test@localhost:55432/sahakar_audit_test'
.venv/bin/alembic upgrade head >/dev/null 2>&1
.venv/bin/python -m app.db.seed >/dev/null 2>&1
.venv/bin/python -m app.cli.fee_policy bootstrap-example
AUDIT_PASS="$(cat /tmp/sahakar-audit/passcode)"; AUDIT_SECRET="$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')"
APP_ENV=development DEV_AUTH_ENABLED=true DEV_AUTH_SECRET="$AUDIT_SECRET" DEV_AUTH_PASSCODE="$AUDIT_PASS" ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5180,http://localhost:5180 \
TSA_URL=http://timestamp.digicert.com TSA_NAME="DigiCert Timestamp Authority" TSA_CA_FILE=trust/tsa/digicert-trusted-root-g4.pem \
ANCHOR_WORKER_ENABLED=true ANCHOR_WORKER_INTERVAL_SECONDS=5 nohup .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8100 > /tmp/sahakar-audit/api.log 2>&1 &
sleep 4; curl -s http://127.0.0.1:8100/api/v1/health/db; echo
