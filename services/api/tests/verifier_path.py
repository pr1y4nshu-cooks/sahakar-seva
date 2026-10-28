"""Locate the standalone offline verifier (repo-root scripts/verify_receipt.py).

Inside the API container only services/api is mounted, so the verifier is absent there; tests that need it
skip with an explicit reason. Run the full suite from the host (or set SAHAKAR_VERIFIER).
"""

import os
from pathlib import Path

import pytest


def verifier_path() -> Path:
    env = os.environ.get("SAHAKAR_VERIFIER")
    if env and Path(env).is_file():
        return Path(env)
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "scripts" / "verify_receipt.py"
        if candidate.is_file():
            return candidate
    pytest.skip("scripts/verify_receipt.py not available (API container mounts only services/api); run on the host", allow_module_level=True)
