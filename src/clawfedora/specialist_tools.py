"""Real static linters with fixed arguments, isolated config and bounded input."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

FORMATS = {
    "ingenieur-devops": {"shell", "yaml", "markdown"},
    "ingenieur-securite": {"shell", "yaml", "secrets"},
    "redacteur-pedagogique": {"markdown"},
    "auditeur-qualite": {"shell", "yaml", "markdown", "secrets"},
}


def _version(distribution: str) -> str | None:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None


def available() -> dict[str, Any]:
    return {
        "shellcheck": Path("/usr/bin/shellcheck").is_file(),
        "graphviz": Path("/usr/bin/dot").is_file(),
        "gitleaks": Path("/usr/bin/gitleaks").is_file(),
        "yamllint": _version("yamllint"),
        "pymarkdownlnt": _version("pymarkdownlnt"),
        "scope": "outils statiques à la demande; aucun service ni modèle supplémentaire",
    }


def run_fixed(command: list[str], content: str) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory(prefix="clawfedora-lint-") as temporary:
        # No project config, credentials, search path, Python plugin or network URL forwarded.
        env = {
            "PATH": "/usr/bin:/bin",
            "HOME": temporary,
            "LANG": "C.UTF-8",
            "PYTHONNOUSERSITE": "1",
            "PYTHONUTF8": "1",
        }
        return subprocess.run(
            command,
            input=content,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
            cwd=temporary,
            env=env,
        )


def lint(role: str, data: dict[str, Any]) -> dict[str, Any]:
    content, kind = data.get("content"), data.get("format")
    if kind not in FORMATS.get(role, set()):
        raise ValueError("contrôle métier interdit pour ce rôle")
    if not isinstance(content, str) or not 0 < len(content.encode()) <= 12000:
        raise ValueError("contenu limité à 12000 octets requis")
    digest = hashlib.sha256(content.encode()).hexdigest()
    if kind == "secrets":
        return _gitleaks(content, digest)
    if kind == "yaml":
        from yamllint.config import YamlLintConfig  # type: ignore[import-untyped]
        from yamllint.linter import run  # type: ignore[import-untyped]

        if _version("yamllint") != "1.38.0":
            return {"tool": "yamllint", "status": "UNAVAILABLE", "runtime_tested": False}
        config = YamlLintConfig("extends: default\nrules:\n  document-start: disable\n")
        checked = re.sub(r"(?m)#\s*yamllint\b[^\n]*", "# directive ignored", content)
        problems = list(run(checked, config))
        findings = [
            {"line": p.line, "column": p.column, "rule": p.rule, "message": p.desc}
            for p in problems[:20]
        ]
        return {
            "tool": "yamllint",
            "version": _version("yamllint"),
            "input_sha256": digest,
            "checked_sha256": hashlib.sha256(checked.encode()).hexdigest(),
            "status": "PASS" if not problems else "FAIL",
            "findings": findings,
            "finding_count": len(problems),
            "runtime_tested": False,
        }
    if kind == "shell":
        command = ["/usr/bin/shellcheck", "--norc", "--format=json", "--shell=bash", "-"]
        if not Path(command[0]).is_file():
            return {"tool": "shellcheck", "status": "UNAVAILABLE", "runtime_tested": False}
        # Do not let inline directives request reading arbitrary host sources.
        checked = re.sub(r"(?m)^\s*#\s*shellcheck\b[^\n]*", "# directive ignored", content)
        version = run_fixed([command[0], "--version"], "").stdout[:300]
    else:
        if _version("pymarkdownlnt") != "0.9.40":
            return {"tool": "pymarkdownlnt", "status": "UNAVAILABLE", "runtime_tested": False}
        command = [sys.executable, "-I", "-m", "pymarkdown", "--disable-rules", "MD013", "scan-stdin"]
        # Markdown comments can disable rules: ignore those lint directives explicitly.
        checked = re.sub(
            r"<!--\s*(?:pyml|pymarkdown|markdownlint).*?-->", "", content, flags=re.S | re.I
        )
        version = str(_version("pymarkdownlnt"))
    try:
        result = run_fixed(command, checked)
    except subprocess.TimeoutExpired:
        return {"tool": kind, "status": "ERROR", "reason": "timeout", "runtime_tested": False}
    expected_codes = {0, 1} if kind == "shell" else {0, 1}
    return {
        "tool": "shellcheck" if kind == "shell" else "pymarkdownlnt",
        "version": version,
        "command": command,
        "input_sha256": digest,
        "checked_sha256": hashlib.sha256(checked.encode()).hexdigest(),
        "status": "PASS"
        if result.returncode == 0
        else "FAIL"
        if result.returncode in expected_codes
        else "ERROR",
        "returncode": result.returncode,
        "stdout": result.stdout[:6000],
        "stderr": result.stderr[:1000],
        "truncated": len(result.stdout) > 6000 or len(result.stderr) > 1000,
        "runtime_tested": False,
        "scope": "forme/syntaxe; directives de désactivation ignorées; aucune solution exécutée",
    }


def _gitleaks(content: str, digest: str) -> dict[str, Any]:
    binary = "/usr/bin/gitleaks"
    if not Path(binary).is_file():
        return {"tool": "gitleaks", "status": "UNAVAILABLE", "runtime_tested": False}
    with tempfile.TemporaryDirectory(prefix="clawfedora-secrets-") as temporary:
        report = Path(temporary) / "report.json"
        command = [
            binary,
            "stdin",
            "--redact=100",
            "--no-banner",
            "--report-format=json",
            "--report-path",
            str(report),
        ]
        try:
            result = run_fixed(command, content)
            version = run_fixed([binary, "version"], "").stdout.strip()[:100]
        except subprocess.TimeoutExpired:
            return {
                "tool": "gitleaks",
                "status": "ERROR",
                "reason": "timeout",
                "runtime_tested": False,
            }
        findings = json.loads(report.read_text()) if report.is_file() else []
        if not isinstance(findings, list):
            raise ValueError("rapport Gitleaks invalide")
        # Never return secrets, matching lines, raw stderr or the unfiltered report to the model.
        return {
            "tool": "gitleaks",
            "version": version,
            "input_sha256": digest,
            "status": "PASS"
            if result.returncode == 0 and not findings
            else "FAIL"
            if result.returncode == 1 and findings
            else "ERROR",
            "returncode": result.returncode,
            "finding_count": len(findings),
            "findings": [
                {"rule": f.get("RuleID"), "line": f.get("StartLine")} for f in findings[:20]
            ],
            "runtime_tested": False,
            "scope": "secrets du texte fourni; pas l’historique Git ni toutes les vulnérabilités",
        }


def receipt(workspace: Path, tool: str, result: dict[str, Any], svg: str | None = None) -> str:
    from uuid import uuid4

    from clawfedora.project_common import assert_no_symlinks, now, write_json

    directory = workspace / ".clawfedora-tool-evidence"
    assert_no_symlinks(directory, label="preuves outils")
    directory.mkdir(exist_ok=True)
    directory.chmod(0o750)
    identifier = uuid4().hex
    path = directory / f"{identifier}.json"
    if svg is not None:
        artifact = directory / f"{identifier}.svg"
        artifact.write_text(svg)
        artifact.chmod(0o440)
        result["artifact_sha256"] = hashlib.sha256(svg.encode()).hexdigest()
        result["svg_reference"] = f"@tool-svg:{identifier}"
    write_json(path, {"origin": "managed-tool-runner", "at": now(), "tool": tool, **result})
    path.chmod(0o440)
    return path.relative_to(workspace).as_posix()
