"""Program catalog data access.

Two backends behind one interface, selected by PROGRAM_CATALOG_SOURCE env var:
  - "local"    (default): reads infra/seed-data/programs.json — no AWS needed,
                used for local dev/tests.
  - "dynamodb": scans the sahayogi-programs table. Wired in once AWS access
                is available (Phase 3 — External integrations).
"""

import json
import os
from pathlib import Path
from typing import Any

_SEED_PATH = Path(__file__).resolve().parents[2] / "infra" / "seed-data" / "programs.json"


def load_programs() -> list[dict[str, Any]]:
    source = os.environ.get("PROGRAM_CATALOG_SOURCE", "local")
    if source == "dynamodb":
        return _load_from_dynamodb()
    return _load_from_local()


def _load_from_local() -> list[dict[str, Any]]:
    return json.loads(_SEED_PATH.read_text(encoding="utf-8"))


def _load_from_dynamodb() -> list[dict[str, Any]]:
    import boto3  # local import: keeps boto3 off the hot path for local/test runs

    table_name = os.environ.get("PROGRAM_TABLE_NAME", "sahayogi-programs")
    table = boto3.resource("dynamodb").Table(table_name)

    items: list[dict[str, Any]] = []
    resp = table.scan()
    items.extend(resp.get("Items", []))
    while "LastEvaluatedKey" in resp:
        resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
        items.extend(resp.get("Items", []))
    return items
