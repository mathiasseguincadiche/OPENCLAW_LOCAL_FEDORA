from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from clawfedora.agent_tools import invoke
from clawfedora.agents import deploy_workspaces
from clawfedora.project_common import read_json
from clawfedora.project_worker import _resolve_tool_files
from clawfedora.specialist_tools import lint

ROOT = Path(__file__).resolve().parents[1]


def test_real_lints_report_errors_without_running_proposed_shell(tmp_path: Path) -> None:
    marker = tmp_path / "must-not-exist"
    content = f"#!/bin/bash\ntouch {marker}\necho $undefined\n"
    shell = lint("ingenieur-devops", {"format": "shell", "content": content})
    if Path("/usr/bin/shellcheck").is_file():
        assert shell["status"] == "FAIL" and shell["returncode"] == 1
    else:
        assert shell["status"] == "UNAVAILABLE"
    assert not marker.exists()
    yaml = lint("ingenieur-devops", {"format": "yaml", "content": "a: 1\na: 2\n"})
    assert yaml["status"] == "FAIL" and yaml["findings"][0]["rule"] == "key-duplicates"
    markdown = lint("redacteur-pedagogique", {"format": "markdown", "content": "hello\n"})
    assert markdown["status"] == "FAIL" and "MD041" in markdown["stdout"]


def test_plugin_receipt_contains_actual_result_hash_and_permissions(tmp_path: Path) -> None:
    deploy_workspaces(ROOT, tmp_path)
    workspace = tmp_path / "workspaces/redacteur-pedagogique"
    text = "# Guide\n\nUn exemple court.\n"
    result = invoke(
        tmp_path,
        "redacteur-pedagogique",
        workspace,
        "clawfedora_lint",
        {"format": "markdown", "content": text},
    )
    assert result["status"] == "PASS"
    receipt = workspace / result["receipt"]
    saved = read_json(receipt)
    assert saved["origin"] == "managed-tool-runner" and saved["returncode"] == 0
    assert saved["input_sha256"] == hashlib.sha256(text.encode()).hexdigest()
    assert receipt.stat().st_mode & 0o222 == 0
    with pytest.raises(ValueError):
        invoke(
            tmp_path,
            "redacteur-pedagogique",
            workspace,
            "clawfedora_lint",
            {"format": "shell", "content": "true"},
        )


def test_inline_opt_outs_do_not_hide_errors() -> None:
    yaml = lint(
        "ingenieur-securite", {"format": "yaml", "content": "# yamllint disable-file\na: 1\na: 2\n"}
    )
    assert yaml["status"] == "FAIL"
    markdown = lint(
        "redacteur-pedagogique",
        {"format": "markdown", "content": "<!-- pyml disable MD041 -->\nhello\n"},
    )
    assert markdown["status"] == "FAIL"


def test_gitleaks_unavailable_is_explicit_or_real_output_is_redacted() -> None:
    # Synthetic high-entropy fixture: alphabetical examples are allowlisted upstream.
    secret = "ghp_" + "nN78M3GcQv9fZ2pRt6xKj5Ws4Hb8Ld7Ya0Ce"
    result = lint("ingenieur-securite", {"format": "secrets", "content": "token = " + secret})
    if Path("/usr/bin/gitleaks").is_file():
        assert result["status"] == "FAIL" and result["finding_count"] > 0
    else:
        assert result["status"] == "UNAVAILABLE"
    assert secret not in str(result)


@pytest.mark.parametrize("kind", ["svg", "drawio"])
def test_diagram_reference_resolves_only_current_verified_architect_artifact(
    tmp_path: Path,
    kind: str,
) -> None:
    deploy_workspaces(ROOT, tmp_path)
    role = "architecte-solutions"
    workspace = tmp_path / "workspaces" / role
    generated = invoke(
        tmp_path,
        role,
        workspace,
        "clawfedora_diagram",
        {"nodes": ["Git", "CI", "Service"], "edges": [[0, 1], [1, 2]]},
    )
    assert "svg" not in generated and "drawio" not in generated
    reference = generated[f"{kind}_reference"]
    assert reference.startswith(f"@tool-{kind}:")
    proof = workspace / generated["receipt"]
    task = {"role": role}
    filename = f"diagrams/architecture/infra.{kind}"
    response = {"files": {filename: reference}}
    _resolve_tool_files(workspace, set(), task, response)
    assert ("<svg" if kind == "svg" else "<mxfile") in response["files"][filename]
    for before, role_name, invalid_output in [
        ({proof}, role, filename),
        (set(), "redacteur-pedagogique", filename),
        (set(), role, "infra.md"),
    ]:
        with pytest.raises(ValueError, match="cette tâche"):
            _resolve_tool_files(
                workspace,
                before,
                {"role": role_name},
                {"files": {invalid_output: reference}},
            )
    artifact = proof.with_suffix(f".{kind}")
    artifact.chmod(0o640)
    artifact.write_text("<svg>changed</svg>")
    with pytest.raises(ValueError, match="invalide"):
        _resolve_tool_files(workspace, set(), task, {"files": {filename: reference}})
