from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import pytest
from test_daily_worker import planned as planned

from clawfedora import project_proofs
from clawfedora.agent_tools import invoke
from clawfedora.agents import deploy_workspaces
from clawfedora.chat_artifacts import links
from clawfedora.ci_reports import summarize
from clawfedora.document_links import check_links
from clawfedora.project_common import read_json, write_json
from clawfedora.project_engine import stale_audits
from clawfedora.project_proofs import collect_operator_proof, resolve_reference
from clawfedora.project_worker import review_project, run_project_tasks

ROOT = Path(__file__).resolve().parents[1]


RESTORE = "deliverables/restore/restore.sh"


@pytest.mark.parametrize(
    "planned",
    [
        [
            {
                "id": "restore",
                "role": "ingenieur-devops",
                "title": "Restauration",
                "objective": "Contrôler",
                "depends_on": [],
                "expected_outputs": [RESTORE],
                "acceptance_criteria": [
                    f"[preuve lab shellcheck {RESTORE}] Le script passe ShellCheck.",
                    f"[preuve observation rocky-test {RESTORE}] Les données témoins sont restaurées.",
                ],
            }
        ]
    ],
    indirect=True,
)
def test_operator_workflow_binds_scope_revision_and_observation(
    planned: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, project = planned
    path = project / "context/project_plan.json"
    plan = read_json(path)
    task = plan["tasks"][0]
    target = RESTORE

    def producer(role: str, prompt: str, session: str) -> dict[str, Any]:
        data = json.loads(prompt.split("\n", 1)[1])
        return {"files": {p: "contenu contrôlé" for p in data["expected_outputs"]}, "summary": "lu"}

    run_project_tasks(ROOT, runtime, project, runner=producer)
    identifier = task["id"]
    request = collect_operator_proof(project, identifier, 1, apply=False)
    assert request["applied"] is False and request["request"]["targets"][target]
    lab_path = project_proofs.receipt_path(identifier, 1)
    obs_path = project_proofs.receipt_path(identifier, 2)
    assert not (project / lab_path).exists()

    def forbidden_audit(*_args: Any) -> dict[str, Any]:
        pytest.fail("aucun appel modèle si une preuve obligatoire manque")

    with pytest.raises(ValueError, match="preuves obligatoires.*critère 1.*critère 2"):
        review_project(ROOT, runtime, project, "validation", runner=forbidden_audit)
    assert not (project / "evidence/validation_report.json").exists()

    def lab(source: Path, tool: str, image: str | None, apply: bool) -> int:
        assert (source / Path(target).name).read_text() == "contenu contrôlé"
        assert tool == "shellcheck" and apply
        return 0

    monkeypatch.setattr(project_proofs.devops_lab, "run_lab", lab)
    collect_operator_proof(project, identifier, 1, apply=True, image="example@sha256:" + "a" * 64)
    with pytest.raises(ValueError, match="opérateur"):
        resolve_reference(project, task, 2, lab_path)
    collect_operator_proof(
        project, identifier, 2, apply=True, observation="cas fictif", outcome="FAIL"
    )
    with pytest.raises(ValueError, match="échec"):
        resolve_reference(project, task, 2, obs_path)
    with pytest.raises(ValueError, match="preuves obligatoires.*critère 2"):
        review_project(ROOT, runtime, project, "validation", runner=forbidden_audit)
    collect_operator_proof(
        project, identifier, 2, apply=True, observation="témoin fictif présent", outcome="PASS"
    )

    def reviewer(role: str, prompt: str, session: str) -> dict[str, Any]:
        rows = {
            t["id"]: [
                {
                    "passed": True,
                    "evidence": "contenu contrôlé",
                    "reference": t["expected_outputs"][0],
                }
            ]
            for t in plan["tasks"]
        }
        rows[identifier] = [
            {"passed": True, "evidence": "preuve correspondante", "reference": p}
            for p in (lab_path, obs_path)
        ]
        return {"verdict": "PASS", "findings": [], "criteria": rows}

    receipt = read_json(project / lab_path)
    receipt["details"]["exit_code"] = 1
    write_json(project / lab_path, receipt)
    with pytest.raises(ValueError, match="preuves obligatoires.*critère 1"):
        review_project(ROOT, runtime, project, "validation", runner=forbidden_audit)
    receipt["details"]["exit_code"] = 0
    write_json(project / lab_path, receipt)
    verdict = review_project(ROOT, runtime, project, "validation", runner=reviewer)
    assert obs_path in read_json(verdict)["proof_hashes"]
    (project / target).write_text("version suivante")
    with pytest.raises(ValueError, match="périmée"):
        resolve_reference(project, task, 1, lab_path)
    assert stale_audits(ROOT, project, ("validation",))


def test_lint_receipt_and_ci_are_bound_to_the_expected_object(tmp_path: Path) -> None:
    path = "deliverables/review/check.sh"
    target = tmp_path / path
    target.parent.mkdir(parents=True)
    target.write_text("true\n")
    task = {
        "id": "review",
        "expected_outputs": [path],
        "acceptance_criteria": [
            f"[preuve lint shellcheck {path}] Script relu",
            "[preuve ci github org/example " + "a" * 40 + "] Pipeline réussi",
        ],
    }
    write_json(tmp_path / "context/project_plan.json", {"tasks": [task]})
    ref = "evidence/review/tool-" + "1" * 32 + ".json"
    write_json(
        tmp_path / ref,
        {
            "tool": "shellcheck",
            "origin": "managed-tool-runner",
            "status": "PASS",
            "input_sha256": hashlib.sha256(b"true\n").hexdigest(),
        },
    )
    assert path in resolve_reference(tmp_path, task, 1, ref)
    with pytest.raises(ValueError):
        resolve_reference(tmp_path, task, 2, ref)
    target.write_text("false\n")
    with pytest.raises(ValueError):
        resolve_reference(tmp_path, task, 1, ref)


def test_source_search_links_and_image_digest(tmp_path: Path) -> None:
    deploy_workspaces(ROOT, tmp_path)
    role = "expert-recherche"
    scope = tmp_path / "workspaces" / role / "projects/demo"
    scope.mkdir()
    (scope / "main.tf").write_text("# exemple\noutput \u0022service\u0022 {}")
    hits = invoke(
        tmp_path,
        role,
        scope.parent.parent,
        "clawfedora_search",
        {"scope": "projects/demo", "query": "service"},
    )["hits"]
    assert hits[0]["line"] == 2 and len(hits[0]["file_sha256"]) == 64
    (scope / "suite.md").write_text("# Après\n")
    text = "# Guide\n[ok](suite.md#après) [faux](suite.md#manque) [externe](https://example.org)"
    report = check_links(scope, {"scope": ".", "document": "guide.md", "content": text})
    assert report["local_links"] == 2 and report["external_unchecked"] == 1
    assert [p["link"] for p in report["findings"]] == ["suite.md#manque"]
    digest = "sha256:" + "f" * 64
    content = {
        "Metadata": {"RepoDigests": ["image@" + digest]},
        "Results": [{"Vulnerabilities": [{"Severity": "HIGH", "Description": "private details"}]}],
    }
    data = {"format": "trivy-image", "image_digest": digest, "content": json.dumps(content)}
    reduced = summarize(data)
    assert reduced["vulnerabilities_by_severity"] == {"HIGH": 1}
    assert reduced["verification"] == "UNVERIFIED" and "private details" not in str(reduced)
    with pytest.raises(ValueError, match="digest"):
        summarize(dict(data, image_digest="sha256:" + "a" * 64))


def test_two_diagram_downloads_match_editable_views(tmp_path: Path) -> None:
    deploy_workspaces(ROOT, tmp_path)
    role = "architecte-solutions"
    workspace = tmp_path / "workspaces" / role
    result = invoke(
        tmp_path,
        role,
        workspace,
        "clawfedora_diagram",
        {
            "nodes": ["Lecteur", "Service"],
            "title": "Présentation",
            "edges": [[0, 1]],
            "edge_labels": ["consulte"],
            "views": [
                {
                    "title": "Technique",
                    "nodes": ["API", "Base"],
                    "boundaries": ["Hôte A", "Hôte B"],
                    "edges": [[0, 1]],
                    "edge_labels": ["écrit"],
                }
            ],
        },
    )
    proof = workspace / result["receipt"]
    pages = ET.fromstring(proof.with_suffix(".drawio").read_bytes()).findall("diagram")
    technical = pages[1].find("mxGraphModel/root")
    assert technical is not None
    assert technical.find("mxCell[@id='n0']").get("parent") == "group0"  # type: ignore[union-attr]
    assert technical.find("mxCell[@edge='1']").get("value") == "écrit"  # type: ignore[union-attr]
    for view, expected in zip(result["views"], ("consulte", "écrit"), strict=True):
        identifier = view["reference"].split(":")[1]
        svg = (proof.parent / (identifier + ".svg")).read_text()
        assert expected in svg and view["title"] in svg
        labels = ET.fromstring(svg).findall("{*}text")
        assert any(label.text == expected and "stroke" not in label.attrib for label in labels)
        assert any(" → " in (label.text or "") for label in labels)
    chat = links(tmp_path, role, set(), 8000, "local")
    assert "vue-1.svg" in chat and "vue-2.svg" in chat and "architecture.drawio" in chat
