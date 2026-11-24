from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from runtime.state.store import INTERNAL_FILES, Feature

SCHEMAS_DIR = Path(__file__).resolve().parents[1] / "schemas"
SCHEMA_FOR = {
    "state": "state.schema.json",
    "requirements": "requirements.schema.json",
    "task_graph": "task-graph.schema.json",
    "test_plan": "test-plan.schema.json",
    "test_results": "test-results.schema.json",
    "failures": "failures.schema.json",
    "findings": "findings.schema.json",
    "split": "split.schema.json",
}


def validate(feature: Feature) -> Optional[List[str]]:
    try:
        import jsonschema
    except ImportError:
        return None
    problems = []
    for key, schema_name in SCHEMA_FOR.items():
        path = feature.path(key)
        if not path.exists():
            continue
        schema = json.loads((SCHEMAS_DIR / schema_name).read_text(encoding="utf-8"))
        data = json.loads(path.read_text(encoding="utf-8"))
        validator = jsonschema.Draft202012Validator(schema)
        for err in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
            loc = "/".join(str(p) for p in err.path) or "(root)"
            problems.append(f"{INTERNAL_FILES[key]} {loc}: {err.message}")
    return problems
