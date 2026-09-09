"""Stable versioned JSON document from the shared result model."""

import json
from dataclasses import asdict


def document(run):
    return {
        "schema_version": 1,
        **asdict(run),
        "status": run.diagnosis.status,
        "summary": run.diagnosis.summary,
    }


def render(run):
    return json.dumps(document(run), indent=2, ensure_ascii=True, allow_nan=False)
