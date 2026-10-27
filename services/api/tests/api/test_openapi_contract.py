from pathlib import Path
import pytest
import yaml
from app.main import app


CONTRACT_RELATIVE_PATH = Path("docs") / "contracts" / "phase2.openapi.yaml"


def _load_contract() -> dict:
    """Locate the frozen contract by walking up from this file (repo checkout layout).

    Inside the API container only services/api is mounted, so the repo-level contract is
    absent there; skip explicitly instead of crashing. The host/CI run enforces it.
    """
    for parent in Path(__file__).resolve().parents:
        candidate = parent / CONTRACT_RELATIVE_PATH
        if candidate.exists():
            with open(candidate, encoding="utf-8") as f:
                return yaml.safe_load(f)
    pytest.skip(f"{CONTRACT_RELATIVE_PATH} not available in this environment (e.g. API container)")


def test_openapi_contract_conformance() -> None:
    """Assert that the live FastAPI application includes all endpoints from the contract."""
    contract_data = _load_contract()

    app_openapi = app.openapi()

    contract_paths = contract_data.get("paths", {})
    app_paths = app_openapi.get("paths", {})

    # Check each path in the contract exists in the live app
    for path, path_item in contract_paths.items():
        assert path in app_paths, f"Expected endpoint path '{path}' missing from live application."
        for method in path_item.keys():
            if method in ["get", "post", "patch", "delete", "put"]:
                assert method in app_paths[path], (
                    f"Expected HTTP method '{method.upper()}' for '{path}' missing in live application."
                )


PROTECTED_ROUTES = [
    ("/api/v1/users/me", "get"),
    ("/api/v1/users/me", "patch"),
    ("/api/v1/worker-profiles", "post"),
    ("/api/v1/worker-profiles/me", "get"),
    ("/api/v1/worker-profiles/me", "patch"),
    ("/api/v1/organizations", "post"),
    ("/api/v1/organizations/mine", "get"),
]




def test_protected_routes_document_contract_error_responses() -> None:
    """DOC-01: generated OpenAPI declares exactly the contract's status codes for protected routes,
    and every error response uses the normalized ErrorResponse envelope."""
    contract = _load_contract()
    generated = app.openapi()

    for path, method in PROTECTED_ROUTES:
        expected = set(contract["paths"][path][method]["responses"])
        actual_responses = generated["paths"][path][method]["responses"]
        assert set(actual_responses) == expected, f"{method.upper()} {path}: {sorted(actual_responses)} != {sorted(expected)}"

        for code, response in actual_responses.items():
            if code.startswith("2"):
                continue
            schema = response["content"]["application/json"]["schema"]
            assert schema == {"$ref": "#/components/schemas/ErrorResponse"}, f"{method.upper()} {path} {code}"


def test_error_response_schema_matches_runtime_envelope() -> None:
    schemas = app.openapi()["components"]["schemas"]
    assert "HTTPValidationError" not in schemas, "FastAPI default 422 schema leaked into Phase 2 routes"
    error_response = schemas["ErrorResponse"]
    assert error_response["required"] == ["error"]
    detail = schemas["ErrorDetail"]
    assert set(detail["required"]) == {"code", "message"}
    assert {"code", "message", "details"} <= set(detail["properties"])


def test_success_contracts_unchanged() -> None:
    generated = app.openapi()["paths"]
    expected_success = {
        ("/api/v1/users/me", "get"): ("200", "UserRead"),
        ("/api/v1/users/me", "patch"): ("200", "UserRead"),
        ("/api/v1/worker-profiles", "post"): ("201", "WorkerProfileRead"),
        ("/api/v1/worker-profiles/me", "get"): ("200", "WorkerProfileRead"),
        ("/api/v1/worker-profiles/me", "patch"): ("200", "WorkerProfileRead"),
        ("/api/v1/organizations", "post"): ("201", "OrganizationWithMyRole"),
    }
    for (path, method), (code, model) in expected_success.items():
        schema = generated[path][method]["responses"][code]["content"]["application/json"]["schema"]
        assert schema == {"$ref": f"#/components/schemas/{model}"}
    listing = generated["/api/v1/organizations/mine"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert listing["type"] == "array"
    assert listing["items"] == {"$ref": "#/components/schemas/OrganizationWithMyRole"}


def test_runtime_error_payloads_match_documented_envelope(client) -> None:
    from app.schemas.error import ErrorResponse

    missing = client.get("/api/v1/users/me")
    ErrorResponse.model_validate(missing.json())
    assert missing.status_code == 401
