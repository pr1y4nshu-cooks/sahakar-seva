FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"
# Fail the image build (not container start) if a runtime dependency is missing (SEC-01).
RUN python -c "import fastapi, sqlalchemy, psycopg, alembic, pydantic_settings, httpx, jose, rfc8785, asn1crypto" && openssl version
COPY . .
EXPOSE 8000
# Production start. Render injects $PORT; locally it defaults to 8000. No --reload in the image.
# --proxy-headers/--forwarded-allow-ips let uvicorn honor Render's TLS-terminating proxy.
# (docker compose overrides this command for local development.)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
