"""Exercise the complete C02 flow using real local Git objects and a simulated GitHub."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

from clawfedora import github_document_boundaries as boundaries
from clawfedora import github_document_ci as ci
from clawfedora import github_document_coherence as coherence
from clawfedora import github_document_corrections as corrections
from clawfedora import github_document_inventory as inventory
from clawfedora import github_document_links as links
from clawfedora import github_document_verification as verification
from clawfedora import github_pr as publisher
from clawfedora import source_connectors as sources
from clawfedora.notion_write import _digest

REPO = "example/atlas-c02"
API = f"/repos/{REPO}"
BRANCH = "atelier/atlas-c02"
WORKFLOW = ".github/workflows/ci.yml"
PRIVATE = "private/repere-operateur.md"
MARKER = "repere prive de l operateur atlas"
TOKEN = "synthetic-c02-token"
SCOPES = ["README.md", "docs"]
POLICY = {"schema": 1, "private_paths": [PRIVATE], "literals": [MARKER]}
GUIDE = (
    "# Installation\n\n"
    "Prepare an isolated workspace and collect the observed result before documenting "
    "the service startup and the validation procedure for the support team.\n"
)
TITLE = "Documenter l'installation Atlas"
BODY = "Corrections Atlas validées dans la revue synthétique."


def _write(folder: Path, files: dict[str, str]) -> None:
    for name, value in files.items():
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value.encode("utf-8"))


def _readme(version: str, anchor: str) -> str:
    return (
        f"# Atelier Atlas\n\n## Versions\n\n| Composant | Version |\n| --- | --- |\n"
        f"| Service | {version} |\n\n[Guide](docs/guide.md#{anchor})\n"
    )


def _run(ident: int, commit: str) -> dict[str, Any]:
    return {"id": ident, "head_sha": commit, "repository": {"full_name": REPO},
            "path": WORKFLOW, "workflow_id": 7, "event": "push", "run_attempt": 1,
            "status": "completed", "conclusion": "success"}


class Forge:
    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir()
        self.git("init", "-q", "--object-format=sha1")
        self.commits: dict[str, str] = {}
        self.trees: dict[str, list[dict[str, str]]] = {}
        self.reads: list[str] = []
        self.writes: list[str] = []
        self.uploads: list[str] = []
        self.ref: str | None = None

    def git(self, *args: str) -> str:
        env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                   GIT_AUTHOR_DATE="2026-01-01T00:00:00Z", GIT_COMMITTER_DATE="2026-01-01T00:00:00Z")
        return subprocess.run(
            ["git", "-C", str(self.root), "-c", "user.email=atlas@example.invalid",
             "-c", "user.name=Atlas", "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false",
             *args],
            check=True, capture_output=True, text=True, env=env, timeout=20,
        ).stdout.strip()

    def commit(self, message: str, changes: dict[str, str]) -> str:
        _write(self.root, changes)
        self.git("add", "--", *changes)
        self.git("commit", "-qm", message)
        sha = self.git("rev-parse", "HEAD")
        tree, entries = inventory._local_tree(self.root, sha)
        self.commits[sha] = tree
        self.trees[tree] = entries
        return sha

    def get(self, path: str) -> dict[str, Any]:
        self.reads.append(path)
        if path.startswith(f"{API}/commits/"):
            sha = path.rsplit("/", 1)[1]
            return {"sha": sha, "commit": {"tree": {"sha": self.commits[sha]}}}
        if path.startswith(f"{API}/git/trees/") and path.endswith("?recursive=1"):
            tree = path.rsplit("/", 1)[1].partition("?")[0]
            return {"sha": tree, "truncated": False, "tree": self.trees[tree]}
        if path.startswith(f"{API}/git/blobs/"):
            sha = path.rsplit("/", 1)[1]
            assert sha != self.private_blob, "le blob privé doit rester fermé"
            raw = inventory._local_git(self.root, "cat-file", "blob", sha)
            return {"sha": sha, "size": len(raw), "encoding": "base64",
                    "content": base64.b64encode(raw).decode("ascii")}
        if path == f"{API}/actions/runs/10":
            return _run(10, self.history)
        if path.startswith(f"{API}/actions/runs?head_sha="):
            rest = path.split("=", 1)[1]
            sha, query = rest.split("&", 1)
            assert query == "per_page=100&page=1"
            return {"total_count": 1, "workflow_runs": [_run(self.runs[sha], sha)]}
        raise AssertionError(path)

    def publication(
        self, path: str, *, method: str, token: str, payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        assert token == TOKEN
        if method == "GET":
            assert payload is None
            reads = {
                API: {"default_branch": "main", "archived": False},
                f"{API}/git/ref/heads/main": {"object": {"sha": self.main}},
                f"{API}/git/commits/{self.base}": {"tree": {"sha": self.commits[self.base]}},
            }
            return reads[path]
        assert method == "POST" and payload is not None
        self.writes.append(path)
        if path == f"{API}/git/blobs":
            assert payload["encoding"] == "utf-8"
            raw = payload["content"].encode("utf-8")
            sha = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw, usedforsecurity=False).hexdigest()
            self.uploads.append(sha)
            return {"sha": sha}
        if path == f"{API}/git/trees":
            assert payload["base_tree"] == self.commits[self.base]
            tree = self.commits[self.fixed]
            expected_entries = [
                item for item in self.trees[tree] if item["path"] in self.changed_paths
            ]
            entries = payload["tree"]
            assert sorted(entries, key=lambda item: item["path"]) == expected_entries
            assert self.uploads == [item["sha"] for item in entries]
            return {"sha": tree}
        if path == f"{API}/git/commits":
            assert payload["tree"] == self.commits[self.fixed] and payload["parents"] == [self.base]
            return {"sha": self.fixed}
        if path == f"{API}/git/refs":
            assert payload == {"ref": f"refs/heads/{BRANCH}", "sha": self.fixed}
            self.ref = self.fixed
            return {}
        if path == f"{API}/pulls":
            assert self.ref == self.fixed
            assert payload == {"title": TITLE, "body": BODY, "head": BRANCH, "base": "main",
                               "draft": True, "maintainer_can_modify": False}
            return {"html_url": f"https://github.com/{REPO}/pull/1", "draft": True}
        raise AssertionError(path)

    def init_scenario(self) -> dict[str, str]:
        self.history = self.commit("Revue historique", {"README.md": "# Atelier Atlas\n"})
        contract = {
            "schema": 1, "checks": [{"id": "service", "kind": "version",
                "authority": {"path": "VERSION", "format": "text", "select": []},
                "declarations": [{"path": "README.md", "format": "markdown_table",
                                  "select": ["Versions", "Service"]}]}],
        }
        original = (
            _readme("1.0.0", "absente") + f"\n{MARKER}.\n\n"
            f"[Preuve de la révision](https://github.com/{REPO}/actions/runs/10)\n"
        )
        self.base = self.commit("Etat audité", {
            "README.md": original, "VERSION": "2.0.0\n",
            "docs/guide.md": GUIDE, "docs/copie.md": GUIDE,
            PRIVATE: "# Notes opérateur\n\nContenu réservé à la simulation.\n",
            coherence.DEFAULT_CONTRACT: json.dumps(contract),
            WORKFLOW: "name: CI\non: [push]\njobs:\n  smoke: {}\n",
        })
        self.main = self.base
        fixed = {"README.md": _readme("2.0.0", "installation"),
                 "docs/copie.md": "# Renvoi\n\n[Guide de référence](guide.md#installation)\n"}
        self.fixed = self.commit("Corrections approuvées", fixed)
        self.changed_paths = set(fixed)
        self.private_blob = self.git("rev-parse", f"{self.base}:{PRIVATE}")
        self.runs = {self.base: 11, self.fixed: 12}
        return fixed


def _audits(commit: str, expected: str) -> dict[str, dict[str, Any]]:
    return {
        "links": links.audit_github(REPO, commit, SCOPES, expected_inventory=expected),
        "coherence": coherence.audit_github(REPO, commit, expected_inventory=expected),
        "ci": ci.audit_github(REPO, commit, ["README.md"], expected_inventory=expected),
        "boundaries": boundaries.audit_github(
            REPO, commit, SCOPES, policy=POLICY, expected_inventory=expected,
        ),
    }


def _publication(
    forge: Forge, stage: Path, approval: str, monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    monkeypatch.setenv("GITHUB_TOKEN", TOKEN)
    monkeypatch.setattr(publisher, "_api_request", forge.publication)
    request = dict(repo=REPO, base="main", base_sha=forge.base, branch=BRANCH, changes=stage,
                   title=TITLE, body=BODY, approve_repo=REPO)
    with pytest.raises(publisher.PublicationError, match="empreinte"):
        publisher.publish_draft(**request, approve_manifest="0" * 64)
    assert not forge.writes
    draft = publisher.publish_draft(**request, approve_manifest=approval)
    assert draft["draft"] and draft["commit_sha"] == forge.fixed and draft["files_count"] == 2
    assert forge.main == forge.base and forge.writes.count(f"{API}/pulls") == 1
    return {"draft": True, "draft_commit": draft["commit_sha"], "files_count": draft["files_count"],
            "wrong_approval_refused": True}


def test_github_documentary_acceptance_campaign(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    forge = Forge(tmp_path / "atlas")
    fixed = forge.init_scenario()
    monkeypatch.setattr(sources, "_github", forge.get)
    before = inventory.inventory_github(REPO, forge.base)
    local = inventory.inventory_local(forge.root, forge.base)
    assert local["files"] == before["files"] and local["git_tree"] == before["git_tree"]
    assert before["excluded_entries"]["confidential_path"] >= 1
    assert not any("/git/blobs/" in path for path in forge.reads)

    original = _audits(forge.base, before["inventory_sha256"])
    assert original["links"]["broken_count"] == 1
    assert original["coherence"]["counts_by_status"] == {"version_drift": 1}
    assert original["ci"]["reference_counts"] == {"different_revision": 1}
    assert original["ci"]["run_counts"] == {"observed_success": 1}
    assert original["boundaries"]["counts_by_code"] == {
        "identical_documents": 1, "private_literal_in_public_document": 1,
        "repeated_normalized_passage": 1,
    }

    stage = tmp_path / "proposal"
    _write(stage, fixed)
    selections = ["links:1", "coherence:1", "ci:1"] + [
        f"boundaries:{index}" for index, _ in enumerate(original["boundaries"]["findings"], 1)
    ]
    review = corrections.prepare(
        repo=REPO, base="main", base_sha=forge.base, branch=BRANCH, changes=stage,
        inventory=before, reports=list(original.values()), selections=selections,
    )
    approved = review["publication_preview"]["manifest_sha256"]
    draft = _publication(forge, stage, approved, monkeypatch)

    # Advancing the fixture models the operator's merge. No network or real repository is modified.
    forge.main = forge.fixed
    after = inventory.inventory_github(REPO, forge.main)
    observed = _audits(forge.main, after["inventory_sha256"])
    assert observed["ci"]["run_counts"] == {"observed_success": 1}
    args = dict(
        repo=REPO, commit=forge.main, expected_review=review["report_sha256"], review=review,
        before_inventory=before, after_inventory=after, before_reports=list(original.values()),
        boundary_scopes=SCOPES, boundary_policy=POLICY,
    )
    partial = verification.verify(**args, after_reports=[observed["links"], observed["coherence"]])
    assert partial["status"] == "review_required"
    pending = {item["reference"] for item in partial["findings"] if item["status"] == "not_verified"}
    assert pending == {"ci:1"}
    verified = verification.verify(
        **args, after_reports=[observed[name] for name in ("links", "coherence", "ci")],
    )
    assert verified["status"] == "verified"
    assert all(row["status"] == "exact_blob_present" for row in verified["files"])
    assert all(row["status"] == "confirmed" for row in verified["findings"])
    assert f"{API}/git/blobs/{forge.private_blob}" not in forge.reads

    tested = os.environ.get("GITHUB_SHA")
    assert tested is None or re.fullmatch(r"[a-f0-9]{40}", tested)
    digests = [
        before["inventory_sha256"], original["links"]["report_sha256"],
        original["coherence"]["report_sha256"], original["ci"]["report_sha256"],
        original["boundaries"]["report_sha256"], review["report_sha256"], verified["report_sha256"],
    ]
    evidence = {
        "schema": 1, "assessment": "C02_SYNTHETIC_ACCEPTANCE_PASSED", "campaign_verdict": "CONFORME",
        "synthetic": True, "tested_commit": tested, "fixture_base": forge.base,
        "fixture_target": forge.fixed, "real_remote_write": False,
        "cases": [{"lot": number, "status": "CONFORME", "proof_sha256": proof}
                  for number, proof in enumerate(digests, 1)],
        "draft_simulation": draft, "verification": verified,
        "partial_verification": partial["status"],
        "private_blob_read": False,
    }
    serialized = json.dumps({**evidence, "report_sha256": _digest(evidence)}, indent=2) + "\n"
    assert all(value not in serialized for value in (MARKER, PRIVATE, TOKEN, "https://"))
    if output := os.environ.get("GITHUB_DOCUMENTARY_ACCEPTANCE_EVIDENCE"):
        Path(output).write_text(serialized, encoding="utf-8")
