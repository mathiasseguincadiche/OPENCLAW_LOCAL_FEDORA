from __future__ import annotations

import json
from typing import Any

import pytest

from clawfedora.ci_reports import summarize


def test_imported_report_never_claims_execution_or_exposes_log_secrets() -> None:
    content = json.dumps(
        {
            "checks": [
                {"tool": "terraform", "exit_code": 0, "log": "MYSECRET"},
                {"tool": "restore", "exit_code": 1},
            ],
            "runtime_tested": True,
            "verification": "VERIFIED",
        }
    )
    result = summarize({"format": "ci-checks", "content": content})
    assert result["checks"][0]["reported_status"] == "PASS"
    assert result["checks"][1]["reported_status"] == "FAIL"
    assert result["verification"] == "UNVERIFIED" and result["runtime_tested"] is False
    assert "MYSECRET" not in json.dumps(result)


@pytest.mark.parametrize("valid", [True, False])
def test_terraform_reports_keep_declared_status(valid: bool) -> None:
    result = summarize(
        {
            "format": "terraform-validate",
            "content": json.dumps(
                {"valid": valid, "diagnostics": [{"detail": "secret not returned"}]}
            ),
        }
    )
    assert result["checks"][0]["finding_count"] == 1
    assert result["checks"][0]["reported_status"] == ("PASS" if valid else "FAIL")
    assert result["runtime_tested"] is False


@pytest.mark.parametrize(
    "format_, value",
    [
        ("wrong", {}),
        ("terraform-validate", {"valid": 1}),
        ("terraform-validate", {"valid": True, "diagnostics": "bad"}),
        ("ci-checks", {"checks": []}),
        ("ci-checks", {"checks": ["bad"]}),
        ("ci-checks", {"checks": [{"tool": "exec", "exit_code": 0}]}),
        ("ci-checks", {"checks": [{"tool": "docker", "exit_code": True}]}),
        ("ci-checks", {"checks": [{"tool": "docker", "exit_code": 0}] * 21}),
    ],
)
def test_invalid_reports_are_not_interpreted(format_: str, value: Any) -> None:
    with pytest.raises(ValueError):
        summarize({"format": format_, "content": json.dumps(value)})


@pytest.mark.parametrize("content", [None, "", "é" * 6001, "invalid json"])
def test_report_payload_is_bounded(content: Any) -> None:
    with pytest.raises(ValueError):
        summarize({"format": "ci-checks", "content": content})
