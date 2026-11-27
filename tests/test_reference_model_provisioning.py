"""Production provisioning must refuse a changed mutable model tag."""
from pathlib import Path

import pytest

from clawfedora import ops_cli
from clawfedora.core_config import root_contract

ROOT = Path(__file__).resolve().parents[1]


def test_reference_digests_are_required_before_adoption(monkeypatch):
    catalog = root_contract(ROOT, "model_catalog.yaml")["models"]
    tags = {"models": [
        {"name": spec["runtime_id"], "digest": spec["reference_digest"],
         "details": {"quantization_level": "Q4_K_M"}}
        for spec in catalog.values()
    ]}
    monkeypatch.setattr(ops_cli.ollama_api, "request_json", lambda *_: tags)
    ops_cli._verify_reference_models(ROOT)
    tags["models"][-1]["digest"] = "0" * 64
    with pytest.raises(ValueError, match="digest de référence divergent"):
        ops_cli._verify_reference_models(ROOT)
