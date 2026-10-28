# Illustrative fee policy definitions

Every file here is an **example** (`"is_example": true`) for demos and sustainability analysis. None is
SAHAKAR–SEVA's commercial pricing, which has not been decided. Load one with:

    docker compose exec api python -m app.cli.fee_policy create --policy-id <id> --file fee_policies/examples/<file>.json
    docker compose exec api python -m app.cli.fee_policy activate --policy-id <id> --version <n>

Activating affects only quotes created afterwards. Format: docs/architecture/FINANCIAL_TRANSPARENCY_AND_ANCHORING.md §3a.
