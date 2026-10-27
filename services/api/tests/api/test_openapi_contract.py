from pathlib import Path
import yaml
from app.main import app


def test_openapi_contract_conformance() -> None:
    """Assert that the live FastAPI application includes all endpoints from the contract."""
    contract_path = (
        Path(__file__).resolve().parents[4] / "docs" / "contracts" / "phase2.openapi.yaml"
    )
    assert contract_path.exists(), f"Contract file not found at {contract_path}"

    with open(contract_path, encoding="utf-8") as f:
        contract_data = yaml.safe_load(f)

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
