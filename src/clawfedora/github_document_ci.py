"""Relate CI definitions, GitHub Actions runs and documented run evidence to a Git SHA."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from clawfedora import github_document_inventory as inv
from clawfedora import github_document_links as links
from clawfedora import source_connectors as sources
from clawfedora.notion_inventory_diff import _private_path, _write_private_report
from clawfedora.notion_write import _digest

DEFAULT_DOCUMENTS = ("README.md", "STATUS.md")
MAX_WORKFLOWS = 60
MAX_DOCUMENTS = 20
MAX_REFERENCES = 500
MAX_HISTORICAL_RUNS = 40
MAX_RUNS = 500
PAGE_SIZE = 100
MAX_READ_BYTES = 10_000_000
WORKFLOW = re.compile(r"\.github/workflows/[^/\\\x00-\x1f]{1,180}\.ya?ml")
SAFE_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_-]{0,99}")
RUN_LINK = re.compile(r"/([^/]+/[^/]+)/actions/runs/([1-9][0-9]{0,18})(?:/[^/]*)*/?")
PENDING = {"queued", "in_progress", "waiting", "pending", "requested"}
CONCLUSIONS = {
    "success", "failure", "cancelled", "timed_out", "action_required", "neutral", "skipped",
    "startup_failure", "stale",
}


def _api(repository: str) -> str:
    return "/repos/" + "/".join(quote(part, safe="") for part in repository.split("/"))


def _observed_run(
    data: object, repository: str, *, expected_sha: str | None = None,
    expected_id: int | None = None,
) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise inv.InventoryError("métadonnées de run invalides")
    run_id, sha = data.get("id"), data.get("head_sha")
    repo = data.get("repository")
    slug = repo.get("full_name") if isinstance(repo, dict) else None
    if (
        type(run_id) is not int or run_id <= 0 or (expected_id is not None and run_id != expected_id)
        or not isinstance(sha, str) or not sources.SHA40.fullmatch(sha)
        or (expected_sha is not None and sha != expected_sha)
        or not isinstance(slug, str) or slug.casefold() != repository.casefold()
    ):
        raise inv.InventoryError("run GitHub d'une autre identité ou révision")
    path, event, attempt = data.get("path"), data.get("event"), data.get("run_attempt")
    workflow_id = data.get("workflow_id")
    if (
        not isinstance(path, str) or not path or len(path) > 280 or inv.CONTROL.search(path)
        or not isinstance(event, str) or not SAFE_NAME.fullmatch(event)
        or type(attempt) is not int or attempt < 1
        or type(workflow_id) is not int or workflow_id < 1
    ):
        raise inv.InventoryError("workflow ou tentative GitHub non vérifiable")
    status, conclusion = data.get("status"), data.get("conclusion")
    if status == "completed" and isinstance(conclusion, str) and conclusion in CONCLUSIONS:
        assessment = "observed_success" if conclusion == "success" else "observed_non_success"
    elif isinstance(status, str) and status in PENDING and conclusion is None:
        assessment = "observed_pending"
    else:
        raise inv.InventoryError("statut de run GitHub non vérifiable")
    # Keep only paths this report is allowed to associate with the versioned tree.
    safe_path = path if WORKFLOW.fullmatch(path) and inv._path(path)[0] is not None else None
    return {"id": run_id, "head_sha": sha, "workflow_id": workflow_id, "path": safe_path,
            "event": event, "attempt": attempt, "status": status, "conclusion": conclusion,
            "observation": assessment}


def _runs(repository: str, commit: str) -> dict[int, dict[str, Any]]:
    results: dict[int, dict[str, Any]] = {}
    count: int | None = None
    for page in range(1, MAX_RUNS // PAGE_SIZE + 1):
        data = sources._github(
            f"{_api(repository)}/actions/runs?head_sha={commit}&per_page={PAGE_SIZE}&page={page}"
        )
        total, rows = data.get("total_count"), data.get("workflow_runs")
        if (
            type(total) is not int or not 0 <= total <= MAX_RUNS or not isinstance(rows, list)
            or len(rows) > PAGE_SIZE or (count is not None and count != total)
            or len(results) + len(rows) > total
        ):
            raise inv.InventoryError("inventaire des runs incomplet, instable ou hors budget")
        count = total
        for row in rows:
            run = _observed_run(row, repository, expected_sha=commit)
            if run["id"] in results:
                raise inv.InventoryError("identifiant de run répété pendant la pagination")
            results[run["id"]] = run
        if len(results) == count:
            return results
        if len(rows) < PAGE_SIZE:
            break
    raise inv.InventoryError("pagination des runs incomplète")


def _names(node: Node) -> list[str]:
    if isinstance(node, MappingNode):
        values = [key for key, _ in node.value]
    elif isinstance(node, SequenceNode):
        values = node.value
    else:
        values = [node]
    names = []
    for value in values:
        if not isinstance(value, ScalarNode) or not SAFE_NAME.fullmatch(value.value):
            raise ValueError("nom de déclencheur ou de job invalide")
        names.append(value.value)
    if not names or len(names) != len(set(names)) or len(names) > 200:
        raise ValueError("liste de déclencheurs ou jobs invalide")
    return sorted(names)


def _definition(content: str | None) -> dict[str, Any]:
    if content is None:
        return {"definition_status": "not_checked"}
    try:
        node = yaml.compose(content, Loader=yaml.SafeLoader)
        if not isinstance(node, MappingNode):
            raise ValueError("structure de workflow invalide")
        fields = [(key.value, val) for key, val in node.value if isinstance(key, ScalarNode)]
        selected = {name: val for name, val in fields if name in {"on", "jobs"}}
        if sum(name in selected for name, _ in fields) != 2:
            raise ValueError("déclencheurs ou jobs absents ou dupliqués")
        if not isinstance(selected.get("jobs"), MappingNode):
            raise ValueError("jobs non structurés")
        triggers, jobs = _names(selected["on"]), _names(selected["jobs"])
    except (KeyError, ValueError, yaml.YAMLError, RecursionError):
        return {"definition_status": "invalid_or_unsupported"}
    return {"definition_status": "readable", "triggers": triggers, "job_ids": jobs}


def _documentation(
    files: dict[str, str], requested: list[str],
) -> tuple[list[str], list[str]]:
    selected = requested or list(DEFAULT_DOCUMENTS)
    if len(selected) > MAX_DOCUMENTS:
        raise inv.InventoryError("trop de documents de preuve demandés")
    valid, missing = set(), set()
    for name in selected:
        path, _ = inv._path(name)
        if path is None or not links._markdown(name):
            raise inv.InventoryError("chemin Markdown de preuve hors périmètre")
        (valid if name in files else missing).add(name)
    return sorted(valid), sorted(missing)


def _reference(href: str, repository: str) -> tuple[int, bool] | None:
    if len(href) > 2048 or inv.CONTROL.search(href):
        return None
    try:
        url = urlsplit(href)
    except ValueError:
        return None
    if url.scheme != "https" or url.netloc.casefold() != "github.com":
        return None
    match = RUN_LINK.fullmatch(url.path)
    if match is None:
        return None
    return int(match[2]), match[1].casefold() == repository.casefold()



class Audit:
    def __init__(self, inventory: dict[str, Any], repository: str) -> None:
        self.inventory = inventory
        self.repository = repository
        self.commit = inventory["commit"]
        self.files = {entry["path"]: entry["git_blob"] for entry in inventory["files"]}
        self.cache: dict[str, str | None] = {}
        self.bytes_read = 0

    def _read(self, path: str) -> str | None:
        sha = self.files[path]
        if sha in self.cache:
            return self.cache[sha]
        raw = links._github_blob(self.repository, sha)
        text = None
        if raw is not None:
            self.bytes_read += len(raw)
            if self.bytes_read > MAX_READ_BYTES:
                raise inv.InventoryError("budget de lecture des preuves dépassé")
            links._check_blob(raw, sha)
            try:
                value = raw.decode("utf-8-sig")
                if "\0" not in value:
                    text = value
            except UnicodeError:
                pass
        self.cache[sha] = text
        return text

    def _workflows(self, runs: dict[int, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[int]]:
        paths = sorted(path for path in self.files if WORKFLOW.fullmatch(path))
        if len(paths) > MAX_WORKFLOWS:
            raise inv.InventoryError("trop de définitions de workflow dans l'arbre")
        grouped: dict[str, list[int]] = defaultdict(list)
        unmatched = []
        for run_id, run in sorted(runs.items()):
            if run["path"] in paths:
                grouped[run["path"]].append(run_id)
            else:
                unmatched.append(run_id)
        workflows = [
            {"path": path, "git_blob": self.files[path], **_definition(self._read(path)),
             "observed_run_ids": grouped[path],
             "run_coverage": "observed" if grouped[path] else "no_run_observed"}
            for path in paths
        ]
        return workflows, unmatched

    def _references(
        self, documents: list[str], runs: dict[int, dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[str], list[str]]:
        rows = []
        read_documents = []
        omitted = []
        additional: dict[int, dict[str, Any] | None] = {}
        for path in documents:
            source = self._read(path)
            if source is None:
                omitted.append(path)
                continue
            read_documents.append(path)
            for line, href in links._document(source).links:
                ref = _reference(href, self.repository)
                if ref is None:
                    continue
                if len(rows) >= MAX_REFERENCES:
                    raise inv.InventoryError("trop de références de runs dans les documents")
                run_id, in_repository = ref
                run = runs.get(run_id)
                if not in_repository:
                    state, run = "other_repository_not_checked", None
                else:
                    if run is None:
                        if run_id not in additional:
                            if len(additional) >= MAX_HISTORICAL_RUNS:
                                raise inv.InventoryError("budget de runs cités dépassé")
                            try:
                                endpoint = f"{_api(self.repository)}/actions/runs/{run_id}"
                                raw = sources._github(endpoint)
                            except sources.SourceImportError:
                                additional[run_id] = None
                            else:
                                additional[run_id] = _observed_run(
                                    raw, self.repository, expected_id=run_id,
                                )
                        run = additional[run_id]
                    if run is None:
                        state = "run_not_verified"
                    elif run["head_sha"] != self.commit:
                        state = "different_revision"
                    elif run_id not in runs:
                        state = "run_list_changed"
                    else:
                        state = run["observation"]
                rows.append({"path": path, "line": line, "run_id": run_id, "status": state,
                             "head_sha": run["head_sha"] if run is not None else None})
        return rows, read_documents, omitted

    def report(self, documents: list[str]) -> dict[str, Any]:
        selected, missing = _documentation(self.files, documents)
        runs = _runs(self.repository, self.commit)
        definitions, unmatched = self._workflows(runs)
        references, inspected, omitted = self._references(selected, runs)
        report = {
            "schema": 1, "classification": inv.CLASSIFICATION,
            "assessment": "GITHUB_CI_EVIDENCE_REVIEW_REQUIRED",
            "repository": self.repository, "commit": self.commit,
            "git_tree": self.inventory["git_tree"],
            "inventory_sha256": self.inventory["inventory_sha256"],
            "observed_at_utc": datetime.now(UTC).isoformat(),
            "workflow_definitions": definitions, "unmatched_run_ids": unmatched,
            "runs": [runs[ident] for ident in sorted(runs)],
            "run_counts": dict(sorted(Counter(run["observation"] for run in runs.values()).items())),
            "document_references": references, "documents_inspected": inspected,
            "documents_missing": missing, "documents_not_checked": omitted,
            "reference_counts": dict(sorted(Counter(ref["status"] for ref in references).items())),
            "limits": [
                "workflow_yaml_top_level_only", "triggers_not_evaluated",
                "run_metadata_only_no_job_log_or_artifact_inspection",
                "absence_of_run_is_not_a_failure", "service_and_deployment_not_verified",
            ],
        }
        return {**report, "report_sha256": _digest(report)}


def audit_github(
    repository: str, commit: str, documents: list[str], *, expected_inventory: str | None = None,
) -> dict[str, Any]:
    repository, commit = sources._safe_repo(repository), sources._safe_sha(commit)
    inventory = inv.inventory_github(repository, commit)
    links._require_inventory(inventory, expected_inventory)
    return Audit(inventory, repository).report(documents)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rattacher les preuves GitHub Actions à un commit")
    parser.add_argument("--github", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--document", action="append", default=[])
    parser.add_argument("--inventory-sha256")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        output = _private_path(args.output)
        if output.exists():
            raise inv.InventoryError("la destination doit être un fichier neuf")
        report = audit_github(
            args.github, args.commit, args.document, expected_inventory=args.inventory_sha256,
        )
        if len(json.dumps(report, ensure_ascii=False, indent=2).encode()) + 1 > inv.MAX_REPORT_BYTES:
            raise inv.InventoryError("rapport de preuves CI trop volumineux")
        _write_private_report(output, report)
    except (inv.InventoryError, sources.SourceImportError) as exc:
        print(f"GITHUB_DOCUMENTARY_CI=REFUSED {exc}")
        return 2
    except (OSError, ValueError, RecursionError):
        print("GITHUB_DOCUMENTARY_CI=REFUSED entrée ou destination illisible")
        return 2
    print(f"GITHUB_DOCUMENTARY_CI=REVIEW_REQUIRED runs={len(report['runs'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
