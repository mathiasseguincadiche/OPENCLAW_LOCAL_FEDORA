"""Exercise both managed graphic profiles through the real worker."""
from __future__ import annotations

import json

import pytest
from test_daily_worker import ROOT
from test_daily_worker import planned as planned

from clawfedora import editorial_cycle as ec
from clawfedora import editorial_graphics as eg
from clawfedora.agent_tools import diagram, invoke
from clawfedora.editorial_identity import from_json
from clawfedora.project_common import read_json
from clawfedora.project_worker import run_project_tasks

DRAWIO = "diagrams/graphic/flow.drawio"
SVG = "diagrams/graphic/flow.svg"
IDENTITY = "diagrams/graphic/flow.json"
TASK = {
    "id": "graphic", "role": "architecte-solutions",
    "title": "Flux", "objective": "Expliquer les flux",
    "depends_on": [], "expected_outputs": [DRAWIO, SVG],
    "acceptance_criteria": ["[revue éditoriale] Lisibilité et exactitude"],
}
SPEC = {
    "project": "Atlas", "tagline": "Comprendre le service", "variant": "hero",
    "motif": "network", "palette": "ocean", "section": "Architecture",
}


def test_pair_rejects_divergent_or_free_svg():
    source, svg = from_json(json.dumps(SPEC))
    task = {**TASK, "expected_outputs": [IDENTITY, SVG]}
    assert eg.profile(task) == "identity"
    assert set(eg.verify_pair(task, "identity", {IDENTITY: source, SVG: svg})) == {
        IDENTITY, SVG,
    }
    with pytest.raises(ValueError, match="SVG divergent"):
        eg.verify_pair(task, "identity", {IDENTITY: source, SVG: svg + " "})
    with pytest.raises(ValueError, match="même outil"):
        eg.verify_refs(task, "identity", {"files": {IDENTITY: source, SVG: svg}})
    with pytest.raises(ValueError, match="même outil"):
        eg.verify_refs(TASK, "diagram", {"files": {
            DRAWIO: "@tool-drawio:a", SVG: "@tool-svg:b",
        }})


def test_geometry_blocks_model_pass():
    first = diagram({"nodes": ["A", "B", "C"], "edges": [[0, 2]], "layout": "timeline"})
    second = diagram({"nodes": ["A", "B", "C"], "edges": [[0, 2]], "layout": "column"})
    def audit(content, _issues):
        return "session", {"checks": {
            key: {"state": "PASS", "quote": content[:15], "reason": "Test",
                  "action": "Conserver"} for key in eg.CRITERIA
        }}
    _, report = ec.run(
        first["drawio"], audit, lambda *_: second["drawio"], profile="diagram",
    )
    assert report["state"] == "MODEL_REVIEW_PASSED"
    assert report["rounds"][0]["structure_issues"]
    assert not report["rounds"][1]["structure_issues"]


@pytest.mark.parametrize("planned", [[TASK]], indirect=True)
def test_worker_corrects_managed_diagram_before_collecting(planned):
    runtime, project = planned
    calls = []

    def runner(role, prompt, session):
        calls.append(role)
        assert not (project / SVG).exists()
        if role == "auditeur-qualite":
            payload = json.loads(prompt.split("\n", 1)[1])
            assert payload["profile"] == "diagram"
            assert (runtime / "workspaces/auditeur-qualite/projects/editorial-reviews"
                    / session / "editorial-candidate.svg").is_file()
            return {"checks": {
                key: {"state": "PASS", "quote": payload["document"][:15],
                      "reason": "Test", "action": "Conserver"}
                for key in eg.CRITERIA
            }}
        output = invoke(
            runtime, role, runtime / "workspaces" / role, "clawfedora_diagram",
            {"nodes": ["A", "B", "C"], "edges": [[0, 2]],
             "layout": "timeline" if len(calls) == 1 else "column"},
        )
        return {"files": {DRAWIO: output["drawio_reference"], SVG: output["svg_reference"]},
                "summary": "Schéma de test"}

    result = run_project_tasks(ROOT, runtime, project, runner=runner)
    assert result[0]["status"] == "PASS", result
    assert calls == ["architecte-solutions", "auditeur-qualite",
                     "architecte-solutions", "auditeur-qualite"]
    receipt = read_json(next((project / "evidence/graphic").glob("editorial-cycle-*.json")))
    assert receipt["profile"] == "diagram"
    assert receipt["files_sha256"] == eg.verify_pair(TASK, "diagram", {
        DRAWIO: (project / DRAWIO).read_text(), SVG: (project / SVG).read_text(),
    })
    assert read_json(project / "project.json")["status"] == "VALIDATING"


@pytest.mark.parametrize("planned", [[{**TASK, "expected_outputs": [IDENTITY, SVG]}]], indirect=True)
def test_worker_accepts_managed_identity_pair(planned):
    runtime, project = planned
    def runner(role, prompt, _session):
        if role == "auditeur-qualite":
            payload = json.loads(prompt.split("\n", 1)[1])
            assert payload["profile"] == "identity"
            return {"checks": {
                key: {"state": "PASS", "quote": "Atlas", "reason": "Test",
                      "action": "Conserver"} for key in eg.CRITERIA
            }}
        result = invoke(runtime, role, runtime / "workspaces" / role, "clawfedora_artifact",
                        {"format": "identity", "content": json.dumps(SPEC)})
        refs = result["references"]
        return {"files": {IDENTITY: refs["json"], SVG: refs["svg"]},
                "summary": "Identité de test"}
    result = run_project_tasks(ROOT, runtime, project, runner=runner)
    assert result[0]["status"] == "PASS", result
    assert (project / IDENTITY).is_file() and (project / SVG).is_file()
