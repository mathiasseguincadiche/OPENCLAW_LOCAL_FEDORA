"""Exercise actual Fedora tools without a model, secrets or infrastructure changes."""

from __future__ import annotations

import tempfile
from pathlib import Path

from clawfedora.agent_tools import invoke
from clawfedora.agents import deploy_workspaces
from clawfedora.project_common import read_json, sha256_file
from clawfedora.specialist_tools import available

repo = Path(__file__).resolve().parents[2]
tools = available()
if not all(
    tools[name] for name in ("shellcheck", "gitleaks", "yamllint", "pymarkdownlnt")
):
    raise SystemExit("Fedora specialist packages and managed Python dependencies required")
with tempfile.TemporaryDirectory(prefix="clawfedora-specialist-check-") as temporary:
    runtime = Path(temporary)
    deploy_workspaces(repo, runtime)
    cases = [
        ("ingenieur-devops", "shell", "#!/bin/bash\necho $undefined\n", "FAIL"),
        ("ingenieur-devops", "yaml", "a: 1\na: 2\n", "FAIL"),
        ("redacteur-pedagogique", "markdown", "# Guide\n\nUne étape.\n", "PASS"),
        (
            "ingenieur-securite",
            "secrets",
            "token=" + "ghp_" + "nN78M3GcQv9fZ2pRt6xKj5Ws4Hb8Ld7Ya0Ce",
            "FAIL",
        ),
    ]
    for role, kind, content, expected in cases:
        result = invoke(
            runtime,
            role,
            runtime / "workspaces" / role,
            "clawfedora_lint",
            {"format": kind, "content": content},
        )
        if result["status"] != expected:
            raise SystemExit(f"Specialist control failed: {kind} status={result['status']}")
        if kind == "secrets" and content.split("=", 1)[1] in str(result):
            raise SystemExit("Secret redaction failed")
        print(f"SPECIALIST_TOOL=PASS format={kind}")
    role = "architecte-solutions"
    result = invoke(
        runtime,
        role,
        runtime / "workspaces" / role,
        "clawfedora_diagram",
        {"nodes": ["Dépôt", "CI", "Service"], "edges": [[0, 1], [1, 2]]},
    )
    if result["renderer"] != "drawio-xml" or "drawio_reference" not in result:
        raise SystemExit("Native Draw.io generator unavailable")
    proof = runtime / "workspaces" / role / result["receipt"]
    if sha256_file(proof.with_suffix(".svg")) != read_json(proof)["artifact_sha256"]:
        raise SystemExit("SVG artifact hash mismatch")
    if sha256_file(proof.with_suffix(".drawio")) != read_json(proof)["drawio_sha256"]:
        raise SystemExit("Draw.io artifact hash mismatch")
    print("SPECIALIST_TOOL=PASS renderer=drawio-xml artifact_references=verified")
