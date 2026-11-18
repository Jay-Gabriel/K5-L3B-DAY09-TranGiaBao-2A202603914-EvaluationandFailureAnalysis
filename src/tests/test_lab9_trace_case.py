"""Regression for the first wrong step documented in docs/trace_case.md."""
import json
import time
from pathlib import Path

import pytest

from lab8.db import connect, init_store
from lab8.metrics import trial_pass
from lab9 import variants
from lab8.shapes import SHAPES
from tests.conftest import BY_ID, CLAIMS, WORLD


@pytest.mark.student
@pytest.mark.parametrize("shape,expected_pass,has_override", [
    ("seeded_regression", False, True),
    ("fixed", True, False),
])
def test_trace_case_ticket_does_not_replace_db(tmp_path, shape, expected_pass, has_override):
    variants.register()
    store = tmp_path / f"{shape}.sqlite"
    init_store(store, WORLD, CLAIMS).close()
    started_at = time.time()
    result = SHAPES[shape]("C-002", seed=11, store_path=str(store))
    conn = connect(store)
    try:
        passed, _ = trial_pass(result.as_dict(), BY_ID["C-002"]["expected"], conn, started_at=started_at)
    finally:
        conn.close()
    events = json.loads(Path(result.trace_path).read_text(encoding="utf-8"))["events"]
    assert passed is expected_pass
    assert any(event.get("kind") == "model_override" for event in events) is has_override
