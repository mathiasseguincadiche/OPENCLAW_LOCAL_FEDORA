"""Review new Notion specifications offline, including the real worker."""
from __future__ import annotations

import copy
import hashlib
import json

import pytest
from test_daily_worker import ROOT
from test_daily_worker import planned as planned

from clawfedora import editorial_cycle as ec
from clawfedora import editorial_notion as en
from clawfedora import notion_studio as ns
from clawfedora.project_common import read_json
from clawfedora.project_worker import run_project_tasks

OUTPUT = "deliverables/wiki/studio.notion.json"
TASK = {
    "id": "wiki", "role": "redacteur-pedagogique", "title": "Wiki",
    "objective": "Expliquer le service", "depends_on": [],
    "expected_outputs": [OUTPUT],
    "acceptance_criteria": ["[revue éditoriale] Parcours et installation"],
}


def sample():
    return json.loads((ROOT / "docs/editorial-demo/curriculum-spec.json").read_text())


def serialize(spec):
    return json.dumps(spec, ensure_ascii=False, separators=(",", ":"))


def verdict(content):
    return {"checks": {
        key: {"state": "PASS", "quote": "Atelier Atlas", "reason": "Test simulé",
              "action": "Conserver"} for key in en.CRITERIA
    }}


def test_offline_preview_and_missing_media(monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("aucun appel distant")
    monkeypatch.setattr(ns, "_request", no_network)
    spec = sample()
    spec["home"]["cover_file"] = "cover.png"
    spec["home"]["images"] = [{"file": "proof.png", "caption": "<script>test</script>"}]
    spec["curriculum"]["modules"][0]["cover_file"] = "card.jpg"
    content = serialize(spec)
    assert en.inspect(content) == []
    html = en.preview(content)
    assert "cover.png" in html and "card.jpg" in html and "proof.png" in html
    assert "Média privé à vérifier lors du plan" in html
    assert "&lt;script&gt;" in html and "<script>" not in html
    assert "data:image/" not in html
    assert "aucune publication" in html


@pytest.mark.parametrize("bad_name", ["../secret.png", "data.svg", "/tmp/photo.jpg"])
def test_media_paths_refused(bad_name):
    spec = sample()
    spec["home"]["cover_file"] = bad_name
    with pytest.raises(ValueError, match="nom simple"):
        en.parse(serialize(spec))


def test_invalid_schema_and_duplicates_refused():
    spec = sample()
    spec["parent"] = "f" * 32
    with pytest.raises(ValueError):
        en.parse(serialize(spec))
    with pytest.raises(ValueError, match="dupliquée"):
        en.parse('{"home":{},"home":{}}')


def test_model_pass_cannot_remove_curriculum_or_installation():
    initial = sample()
    broken = copy.deepcopy(initial)
    del broken["curriculum"]
    broken["pages"][1]["blocks"][0]["text"] = "Autre titre"
    issues = en.inspect(serialize(broken), preserve_installation=True, preserve_curriculum=True)
    assert len(issues) == 2
    def audit(content, _issues):
        answer = verdict(content)
        if content == serialize(initial):
            answer["checks"]["writing"]["state"] = "REVISE"
        return "session", answer
    _, report = ec.run(
        serialize(initial), audit, lambda *_: serialize(broken), profile="notion",
    )
    assert report["state"] == "NO_PROGRESS"
    assert report["rounds"][1]["structure_issues"]


def test_reformatting_is_not_progress():
    spec = sample()
    def audit(content, _issues):
        answer = verdict(content)
        answer["checks"]["writing"]["state"] = "REVISE"
        return "session", answer
    _, report = ec.run(serialize(spec), audit, lambda *_: json.dumps(spec, indent=2),
                       profile="notion")
    assert report["state"] == "NO_PROGRESS"


@pytest.mark.parametrize("planned", [[TASK]], indirect=True)
def test_worker_repairs_wiki_before_collection(planned, monkeypatch):
    runtime, project = planned
    initial = sample()
    initial["pages"][1]["blocks"][0]["text"] = "Préparation"
    original, revised = serialize(initial), serialize(sample())
    calls = []

    def no_network(*args, **kwargs):
        raise AssertionError("aucun appel Notion")
    monkeypatch.setattr(ns, "_request", no_network)

    def runner(role, prompt, session):
        calls.append(role)
        assert not (project / OUTPUT).exists()
        if role == "auditeur-qualite":
            payload = json.loads(prompt.split("\n", 1)[1])
            assert payload["profile"] == "notion"
            snapshot = (runtime / "workspaces/auditeur-qualite/projects/editorial-reviews"
                        / session)
            assert (snapshot / "editorial-candidate.html").is_file()
            assert (snapshot / "context/notion-studio-example.json").is_file()
            return verdict(payload["document"])
        assert "context/notion-studio-example.json" in prompt
        return {"files": {OUTPUT: original if len(calls) == 1 else revised},
                "summary": "Spécification de test"}

    result = run_project_tasks(ROOT, runtime, project, runner=runner)
    assert result[0]["status"] == "PASS", result
    assert calls == ["redacteur-pedagogique", "auditeur-qualite",
                     "redacteur-pedagogique", "auditeur-qualite"]
    assert (project / OUTPUT).read_text() == revised
    receipt = read_json(next((project / "evidence/wiki").glob("editorial-cycle-*.json")))
    assert receipt["profile"] == "notion"
    assert receipt["candidate_sha256"] == hashlib.sha256(revised.encode()).hexdigest()
    assert read_json(project / "project.json")["status"] == "VALIDATING"
