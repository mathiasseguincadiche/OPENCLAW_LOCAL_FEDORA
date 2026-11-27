"""Exercise the C01 Notion workflow on a synthetic Atlas wiki."""
from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from test_daily_worker import planned as planned

from clawfedora import notion_duplicates as duplicates
from clawfedora import notion_inventory_diff as nd
from clawfedora import notion_native_inventory as ni
from clawfedora import notion_non_regression as regression
from clawfedora import notion_premium_tools as premium
from clawfedora import notion_rationalization as rational
from clawfedora import notion_references as refs
from clawfedora import notion_source_truth as truth
from clawfedora import notion_worker_audit as worker_audit
from clawfedora import notion_write as nw
from clawfedora.agent_tools import invoke
from clawfedora.project_common import read_json
from clawfedora.project_worker import run_project_tasks

REPO = Path(__file__).resolve().parents[1]
SPACES = ("Comprendre", "Préparer", "Pratiquer", "Suivre", "Ressources")
OLD = "Version 0.9"
NEW = "Version 1.0"


def _id(number: int) -> str:
    return f"{number:032x}"


ROOT, LEARN, PREPARE, PRACTICE, TRACK, RESOURCES = map(_id, range(1, 7))
CANONICAL, COPY, ARCHIVE, SETUP, EXERCISE, SYNC, CLONE = map(_id, range(11, 18))
LINKS, FILE, DATABASE, DATA_SOURCE, VIEW, MISSING = map(_id, range(18, 24))


def _parent(key: str, ident: str) -> dict[str, str]:
    return {"type": key, key: ident}


def _block(ident: str, kind: str, parent: str, **payload: Any) -> dict[str, Any]:
    return {"object": "block", "id": ident, "type": kind, kind: payload, "has_children": False,
            "parent": _parent("page_id", parent)}


def _paragraph(ident: str, parent: str, content: str) -> dict[str, Any]:
    return _block(ident, "paragraph", parent, rich_text=[{
        "type": "text", "text": {"content": content, "link": None},
        "plain_text": content, "href": None,
    }])


def _list(items: list[dict[str, Any]], cursor: str | None = None) -> dict[str, Any]:
    return {"results": items, "has_more": cursor is not None, "next_cursor": cursor}


class Atlas:
    """Single mutable fixture behind both Notion transports. Never forwards a request."""

    def __init__(self) -> None:
        self.names = {ROOT: "Atelier Atlas", **dict(zip(
            (LEARN, PREPARE, PRACTICE, TRACK, RESOURCES), SPACES, strict=True,
        ))}
        self.calls: list[str] = []
        self.patches: list[str] = []
        self.children = {
            ROOT: [_block(ident, "child_page", ROOT) for ident in self.names if ident != ROOT],
            LEARN: [_paragraph(CANONICAL, LEARN, NEW), _paragraph(ARCHIVE, LEARN, NEW),
                    _block(SYNC, "synced_block", LEARN, synced_from=None)],
            PREPARE: [_paragraph(SETUP, PREPARE, "Installation des outils du laboratoire"),
                      _block(CLONE, "synced_block", PREPARE, synced_from={"block_id": SYNC})],
            PRACTICE: [_paragraph(EXERCISE, PRACTICE, "Vérifier le résultat de l’exercice"),
                       _paragraph(COPY, PRACTICE, OLD)],
            TRACK: [_block(DATABASE, "child_database", TRACK)],
            RESOURCES: [_block(LINKS, "paragraph", RESOURCES, rich_text=[
                {"href": f"https://app.notion.com/p/Pratiquer-{PRACTICE}#{EXERCISE}"},
                {"mention": {"type": "page", "page": {"id": MISSING}}},
                {"href": "https://github.com/example/atlas/actions/runs/123"},
            ]), _block(FILE, "file", RESOURCES, type="file", file={
                "url": "https://example.invalid/atlas?signature=synthetic",
                "expiry_time": "2000-01-01T00:00:00+00:00",
            })],
        }

    def get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        self.calls.append(path)
        _, _, kind, *parts = path.split("/")
        if kind == "pages" and parts[0] in self.names:
            ident = parts[0]
            return {"object": "page", "id": ident,
                    **({"parent": _parent("page_id", ROOT)} if ident != ROOT else {})}
        if kind == "blocks" and len(parts) == 2 and parts[1] == "children":
            items = self.children[parts[0]]
            if parts[0] == ROOT:
                return _list(items[2:]) if "start_cursor" in params else _list(items[:2], "atlas")
            return _list(items)
        if path == f"/v1/databases/{DATABASE}":
            return {"object": "database", "id": DATABASE, "parent": _parent("page_id", TRACK),
                    "data_sources": [{"id": DATA_SOURCE}]}
        if path == f"/v1/data_sources/{DATA_SOURCE}":
            return {"object": "data_source", "id": DATA_SOURCE,
                    "parent": _parent("database_id", DATABASE), "properties": {
                        "Module": {"type": "relation"}, "Progression": {"type": "rollup"},
                    }}
        if path == "/v1/views" and params.get("database_id") == DATABASE:
            return _list([{"id": VIEW}])
        if path == f"/v1/views/{VIEW}":
            return {"object": "view", "id": VIEW, "parent": _parent("database_id", DATABASE),
                    "type": "table"}
        raise AssertionError(f"Lecture imprévue dans le scénario Atlas {path}")

    def request(
        self, method: str, path: str, *, write: bool = False, body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if method == "GET" and not write:
            if path == f"/v1/blocks/{COPY}":
                return deepcopy(self.children[PRACTICE][1])
            return self.get(path, {})
        assert method == "PATCH" and write and path == f"/v1/blocks/{COPY}" and body is not None
        new_text = body["paragraph"]["rich_text"][0]["text"]["content"]
        assert new_text in {OLD, NEW}
        self.children[PRACTICE][1] = _paragraph(COPY, PRACTICE, new_text)
        self.patches.append(COPY)
        return {"id": COPY}


def _member(ident: str) -> dict[str, str]:
    return {"category": "block", "id": ident}


def _case(stage: int, area: str, proof: str, state: str = "CONFORME") -> dict[str, Any]:
    return {"lot": stage, "area": area, "state": state, "proof_sha256": proof}


def _inputs(before: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str]:
    bundle = before["references"]
    inventory = bundle["inventory"]
    binding = {"schema": 1, "root_page": ROOT, "structure_sha256": inventory["structure_sha256"]}
    annotations = {**binding, "entries": [
        {**_member(ARCHIVE), "context": ["archive"]},
        {**_member(SETUP), "context": ["installation"]},
    ]}
    registry = {**binding, "topics": [{
        "key": "version", "comparison": "normalized_text",
        "canonical": [_member(CANONICAL)], "copies": [_member(COPY)],
    }]}
    as_of = (datetime.fromisoformat(inventory["captured_at"]) + timedelta(minutes=1)).isoformat()
    external = next(item for item in bundle["references"] if item["kind"] == "github_ci")
    observations = {"schema": 1, "capture_sha256": bundle["capture_sha256"], "entries": [{
        "reference_id": external["reference_id"], "observed_at": as_of,
        "result": "http", "status_code": 403, "visibility": "unknown",
    }]}
    return annotations, registry, observations, as_of



def _editorial(tmp_path: Path, atlas: Atlas) -> dict[str, Any]:
    spec_path = REPO / "docs/editorial-demo/studio-spec.json"
    spec = premium.studio_check(spec_path.read_text(encoding="utf-8"))
    assert spec["compiler_valid"] and spec["assessment"] == "STRUCTURE_REVIEW_REQUIRED"
    scope = tmp_path / "atlas-import"
    scope.mkdir()
    pages = [{"id": k, "title": v} for k, v in atlas.names.items()]
    (scope / ".source-provenance.json").write_text(json.dumps({
        "provider": "notion", "classification": "private_local_only", "read_only": True,
        "attachments": "excluded", "root_page": ROOT, "page_count": len(pages), "pages": pages,
    }), encoding="utf-8")
    for ident, name in atlas.names.items():
        body = "\n\n## Installation des outils\n" if ident == PREPARE else "\n"
        (scope / f"page-{ident}.md").write_text(f"# {name}{body}", encoding="utf-8")
    imported = premium.inventory(tmp_path, scope.name)
    assert all(imported["spaces_title_present"].values())
    assert imported["installation_locations"] == [{"page_id": PREPARE, "line": 3}]
    return _case(1, "outillage éditorial et inventaire Markdown", nw._digest([spec, imported]))


def _worker(
    planned_project: tuple[Path, Path], bundle: dict[str, Any], annotations: dict[str, Any],
    registry: dict[str, Any], observations: dict[str, Any], as_of: str, direct_plan: dict[str, Any],
) -> dict[str, Any]:
    runtime, project = planned_project
    task_id = "design-choice"
    approval = worker_audit.approve(runtime, project.name, task_id, ROOT, ["plan"], {
        "reference_capture": bundle, "annotations": annotations, "registry": registry,
        "observations": observations, "as_of": as_of,
    })
    report_path: Path | None = None

    def runner(role: str, prompt: str, session: str) -> dict[str, Any]:
        nonlocal report_path
        task = json.loads(prompt.split("\n", 1)[1])
        if task["id"] == task_id:
            workspace = runtime / "workspaces" / role
            scope = f"projects/{project.name}/{task_id}/{session}"
            with pytest.raises(ValueError, match="hors du snapshot"):
                invoke(runtime, role, workspace, worker_audit.TOOL, {
                    "scope": scope.replace(project.name, "foreign-atlas"), "operation": "plan",
                })
            result = invoke(runtime, role, workspace, worker_audit.TOOL, {
                "scope": scope, "operation": "plan",
            })
            assert result["status"] == "REVIEW_REQUIRED" and "report" not in result
            assert result["counts"]["issues"] == len(direct_plan["issues"])
            report_path = worker_audit.verify(
                runtime, project.name, task_id, session, "plan", result["artifact_sha256"],
            )
        return {"files": {task["expected_outputs"][0]: "# Atlas\n"}, "summary": "Recette simulée"}

    results = run_project_tasks(REPO, runtime, project, runner=runner)
    assert len(results) == 2 and all(result["status"] == "PASS" for result in results)
    assert report_path is not None
    artifact = read_json(report_path)
    assert artifact["report"]["plan_sha256"] == direct_plan["plan_sha256"]
    receipts = list((project / "evidence" / task_id).glob("tool-*.json"))
    assert len(receipts) == 1
    proof = read_json(receipts[0])
    assert proof["approval_sha256"] == approval and "report" not in proof
    return {"plan_sha256": direct_plan["plan_sha256"], "artifact_sha256": proof["artifact_sha256"],
            "approval_sha256": approval, "foreign_project_refused": True}


def _exercise_write(
    atlas: Atlas, before: dict[str, Any], annotations: dict[str, Any], tmp_path: Path,
) -> dict[str, Any]:
    plan_path = tmp_path / "atlas-edit.json"
    preview = nw.preview(PRACTICE, COPY, NEW, plan_path)
    manifest = preview["manifest_sha256"]
    expectation = regression.prepare(
        before, root_page=ROOT, page=PRACTICE, plan=json.loads(plan_path.read_text()),
        approved_manifest=manifest, annotations=annotations,
    )
    with pytest.raises(ValueError, match="approbation ou intégrité"):
        nw.apply(plan_path, PRACTICE, "0" * 64)
    assert not atlas.patches
    applied = nw.apply(plan_path, PRACTICE, manifest)
    assert applied["mode"] == "NOTION_BLOCK_UPDATED_VERIFIED" and atlas.patches == [COPY]
    with pytest.raises(ValueError, match="déjà tenté"):
        nw.apply(plan_path, PRACTICE, manifest)
    assert atlas.patches == [COPY]
    after = regression.capture(ROOT)
    report = regression.audit(before, after, expectation, root_page=ROOT)
    assert report["verdict"] == "CONFORME_OBSERVABLE"
    assert report["protected_checked"] == 4 and not report["protected_changes"]
    diff = nd.compare(before["references"]["inventory"], after["references"]["inventory"],
                      root_page=ROOT)
    assert [item["id"] for item in diff["modified"]] == [COPY]

    protected_original = atlas.children[LEARN][1]
    atlas.children[LEARN][1] = _paragraph(ARCHIVE, LEARN, "Archive altérée dans le scénario")
    bad = regression.audit(before, regression.capture(ROOT), expectation, root_page=ROOT)
    atlas.children[LEARN][1] = protected_original
    assert bad["verdict"] == "NON_CONFORME"
    assert [item["id"] for item in bad["protected_changes"]] == [ARCHIVE]

    restore_path = tmp_path / "atlas-restore.json"
    restore = nw.preview(PRACTICE, COPY, OLD, restore_path)
    nw.apply(restore_path, PRACTICE, restore["manifest_sha256"])
    restored = regression.capture(ROOT)
    restored_structure = restored["references"]["inventory"]["structure_sha256"]
    assert restored_structure == before["references"]["inventory"]["structure_sha256"]
    assert atlas.patches == [COPY, COPY]
    return {
        "proposed": {"block_id": COPY, "manifest_sha256": manifest, "action": "align_copy"},
        "applied": {"block_id": COPY, "mode": applied["mode"], "transport": "synthetic"},
        "non_regression": report, "negative": bad, "comparison": diff,
        "rollback": {"block_id": COPY, "original_text_sha256": nw._digest(OLD),
                     "restored_structure_sha256": restored_structure,
                     "restore_manifest_sha256": restore["manifest_sha256"]},
        "wrong_approval_refused": True, "replay_refused": True,
    }


def test_atlas_notion_acceptance_campaign(
    planned: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    atlas = Atlas()
    monkeypatch.setattr(ni, "_get", atlas.get)
    monkeypatch.setattr(ni.time, "sleep", lambda _: None)
    monkeypatch.setattr(nw, "_request", atlas.request)
    editorial_case = _editorial(tmp_path, atlas)

    before = regression.capture(ROOT)
    bundle = before["references"]
    inventory = bundle["inventory"]
    assert atlas.calls.count(f"/v1/blocks/{ROOT}/children") == 2
    assert f"/v1/blocks/{CLONE}/children" not in atlas.calls
    assert inventory["counts"] == {"page": 6, "block": 15, "database": 1,
                                   "data_source": 1, "view": 1}
    _, rows = nd._validated(inventory, ROOT)
    assert rows["data_source", DATA_SOURCE]["property_types"] == {"relation": 1, "rollup": 1}
    assert rows["view", VIEW]["type"] == "table"

    annotations, registry, observations, as_of = _inputs(before)
    captured_calls = list(atlas.calls)
    duplicate_report = duplicates.analyze(inventory, root_page=ROOT, evidence=annotations)
    duplicate = next(item for item in duplicate_report["findings"] if item["family"] == "exact")
    assert duplicate["status"] == "protected_context"
    references = refs.audit(bundle, root_page=ROOT, as_of=refs._utc(as_of), observations=observations)
    assert references["counts_by_status"] == {
        "access_restricted": 1, "outside_observed_inventory": 1, "present_in_inventory": 1,
        "temporary_url_expired": 1,
    }
    sources = truth.audit(inventory, root_page=ROOT, registry=registry, annotations=annotations,
                          reference_capture=bundle)
    assert sources["counts_by_comparison"] == {"divergent_observable_evidence": 1}
    plan = rational.plan(
        inventory, root_page=ROOT, annotations=annotations, registry=registry,
        reference_capture=bundle, observations=observations, as_of=refs._utc(as_of),
    )
    assert not plan["executable"] and not plan["remote_write"]
    worker_proof = _worker(planned, bundle, annotations, registry, observations, as_of, plan)
    assert atlas.calls == captured_calls and not atlas.patches

    edits = _exercise_write(atlas, before, annotations, tmp_path)
    cases = [
        editorial_case,
        _case(2, "inventaire natif paginé", inventory["structure_sha256"]),
        _case(3, "comparaison avant/après", edits["comparison"]["report_sha256"]),
        _case(4, "doublon et répétition protégée", duplicate_report["report_sha256"]),
        _case(5, "liens et pièce jointe", references["report_sha256"]),
        _case(6, "source de vérité et copie divergente", sources["report_sha256"]),
        _case(7, "plan de rationalisation", plan["plan_sha256"]),
        _case(8, "worker local et contrôle de périmètre", worker_proof["artifact_sha256"]),
        _case(9, "non-régression et retour arrière simulé", edits["non_regression"]["report_sha256"]),
    ]
    # This identifies the revision checked out by CI, including the proposed merge on a PR.
    commit = os.environ.get("GITHUB_SHA")
    assert commit is None or re.fullmatch(r"[a-f0-9]{40}", commit)
    report = {
        "schema": 1, "scenario": "atelier-atlas", "tested_commit": commit, "synthetic": True,
        "assessment": "C01_SYNTHETIC_ACCEPTANCE_PASSED", "campaign_verdict": "CONFORME",
        "wiki_qualification": "PARTIELLEMENT_CONFORME", "real_write": False,
        "cases": cases,
        "pages": [{**nd._location(rows["page", ident]), "title": title}
                  for ident, title in atlas.names.items()],
        "scope": {"inventory_counts": inventory["counts"], "limitations": inventory["limitations"]},
        "anomalies": plan["issues"],
        "links": references["references"],
        "changes": edits,
        "worker_proof": worker_proof,
        "follow_up": [
            {"area": "Rendu Notion, droits, lignes de bases, octets des médias et Fedora",
             "state": "NON_VERIFIE"},
            {"area": "Modification d’un wiki utilisateur durant cette campagne synthétique",
             "state": "NON_APPLICABLE"},
        ],
    }
    report["report_sha256"] = nw._digest(report)
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    assert "https://" not in serialized and "signature=synthetic" not in serialized
    if output := os.environ.get("NOTION_ATLAS_EVIDENCE"):
        Path(output).write_text(serialized, encoding="utf-8")
    print(f"ATLAS_C01=PASS cases={len(cases)} sha256={report['report_sha256']}")
