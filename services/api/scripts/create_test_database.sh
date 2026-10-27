#!/usr/bin/env sh
# Create the isolated integration-test database inside the existing Docker PostgreSQL service.
#
# Idempotent and non-destructive: it only CREATEs the role/database if they are missing.
# It never touches the development database (sahakar_seva) or the persistent volume.
#
# Usage (from the repository root, with `docker compose up -d db` running):
#   sh services/api/scripts/create_test_database.sh
#
# Then run the DB tests with:
#   cd services/api
#   TEST_DATABASE_URL=postgresql+psycopg://sahakar_test:sahakar_test@localhost:55432/sahakar_seva_test pytest tests/db
set -eu

ADMIN_USER="${POSTGRES_USER:-sahakar}"
TEST_DB="sahakar_seva_test"
TEST_ROLE="sahakar_test"
TEST_PASSWORD="${TEST_DB_PASSWORD:-sahakar_test}"   # local-only credential, not a secret

case "$TEST_DB" in
  *test*) ;;
  *) echo "Refusing: test database name must contain 'test'" >&2; exit 1 ;;
esac

docker compose exec -T db psql -U "$ADMIN_USER" -d postgres -v ON_ERROR_STOP=1 \
  -v test_role="$TEST_ROLE" -v test_password="$TEST_PASSWORD" -v test_db="$TEST_DB" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'test_role', :'test_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'test_role') \gexec
SELECT format('CREATE DATABASE %I OWNER %I', :'test_db', :'test_role')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'test_db') \gexec
SQL

# PostGIS must be created by a superuser; migration 0001's CREATE EXTENSION IF NOT EXISTS then no-ops.
docker compose exec -T db psql -U "$ADMIN_USER" -d "$TEST_DB" -v ON_ERROR_STOP=1 \
  -c "CREATE EXTENSION IF NOT EXISTS postgis"

echo "Test database '$TEST_DB' (owner '$TEST_ROLE') is ready."
