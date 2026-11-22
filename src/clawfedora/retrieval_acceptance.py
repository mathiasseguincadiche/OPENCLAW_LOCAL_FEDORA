"""Local, read-only acceptance checks for cross-source retrieval.

Benchmark cases are user-defined. A PASS qualifies only retrieval on the
specified corpus and machine; it never certifies an agent, deployment,
cloud boundary, or personal InfraOps skill. Private passages are not printed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

from clawfedora import github_refresh
from clawfedora.core_config import resolve_runtime_root
from clawfedora.project_common import (
    assert_no_symlinks,
    project_path,
    read_json,
    sha256_file,
)
from clawfedora.project_intake import validate_input_integrity
from clawfedora.project_retrieval import retrieve

SHA256 = re.compile(r"[a-f0-9]{64}\Z")
CASE_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")
MAX_CASES = 25
MAX_CASE_FILE = 64 * 1024
MAX_HITS = 4
MAX_CHARS = 4000


def _safe_terms(value: Any, *, max_count: int) -> list[str]:
    if (
        not isinstance(value, list) or len(value) > max_count
        or any(not isinstance(term, str) or not 1 <= len(term) <= 160
               or "\n" in term or "\x00" in term for term in value)
    ):
        raise ValueError("liste de références attendues invalide")
    return value


def _cases(path: Path) -> list[dict[str, Any]]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_CASE_FILE:
        raise ValueError("fichier de recette absent, lié ou trop volumineux")
    body = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(body, dict) or body.get("schema_version") != 1:
        raise ValueError("schéma de recette inconnu")
    cases = body.get("cases")
    if not isinstance(cases, list) or not 1 <= len(cases) <= MAX_CASES:
        raise ValueError("prévoir entre 1 et 25 questions de référence")
    known: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or set(case) - {
            "id", "query", "required_paths_contain", "forbidden_paths_contain",
            "minimum_hits", "minimum_distinct_sources", "expect_empty",
        }:
            raise ValueError("champs de scénario inconnus")
        name, query = case.get("id"), case.get("query")
        if (not isinstance(name, str) or not CASE_ID.fullmatch(name)
                or name in known or not isinstance(query, str)
                or not 3 <= len(query) <= 1000):
            raise ValueError("identifiant ou requête de scénario invalide")
        known.add(name)
        required = _safe_terms(case.get("required_paths_contain", []), max_count=4)
        _safe_terms(case.get("forbidden_paths_contain", []), max_count=12)
        empty = case.get("expect_empty", False)
        if type(empty) is not bool:
            raise ValueError("expect_empty doit être booléen")
        min_hits = case.get("minimum_hits", 1)
        min_sources = case.get("minimum_distinct_sources", 1)
        if (type(min_hits) is not int or type(min_sources) is not int
                or not 0 <= min_hits <= MAX_HITS or not 0 <= min_sources <= MAX_HITS):
            raise ValueError("seuils de résultats hors limites")
        if (empty and (required or min_hits > 0 or min_sources > 0)
                or not empty and not required):
            raise ValueError("une question positive exige au moins une source attendue")
    return cases


def _citation(
    project: Path, hit: dict[str, Any], commits: dict[str, str],
) -> tuple[bool, str]:
    """Verify identity and exact text position if an available representation allows."""
    relative = hit.get("representation_path")
    path = hit.get("path")
    source_hash = hit.get("source_sha256")
    representation_hash = hit.get("representation_sha256")
    excerpt = hit.get("text")
    offset = hit.get("start_char")
    page = hit.get("page")
    line = hit.get("line")
    if (
        not isinstance(relative, str) or not isinstance(path, str)
        or not isinstance(source_hash, str) or not SHA256.fullmatch(source_hash)
        or not isinstance(representation_hash, str)
        or not SHA256.fullmatch(representation_hash)
        or not isinstance(excerpt, str)
        or not isinstance(offset, int) or offset < 0
        or type(page) is not int or page < 1
        or type(line) is not int or line < 1
        or hit.get("excerpt_sha256") != hashlib.sha256(excerpt.encode()).hexdigest()
    ):
        return False, "CITATION_FIELDS_INVALID"
    safe = Path(relative)
    if not relative or safe.is_absolute() or ".." in safe.parts:
        return False, "CITATION_PATH_UNSAFE"
    actual = project / safe
    if not actual.is_file() or actual.is_symlink():
        return False, "CITATION_SOURCE_MISSING"
    if sha256_file(actual) != representation_hash:
        return False, "CITATION_REPRESENTATION_CHANGED"

    if hit.get("kind") == "github-approved-revision":
        repository, sha = hit.get("repository"), hit.get("commit")
        if (not isinstance(repository, str) or not isinstance(sha, str)
                or commits.get(repository) != sha
                or not path.startswith(f"github:{repository}@{sha}/")
                or source_hash != representation_hash):
            return False, "GITHUB_VERSION_OR_PROVENANCE_INVALID"
        source_path = path.split(f"github:{repository}@{sha}/", 1)[1]
        if safe != (
            Path(github_refresh.STORE)
            / github_refresh._directory(project, repository).name
            / sha / "files" / source_path
        ):
            return False, "GITHUB_SOURCE_PATH_MISMATCH"
    else:
        source = Path(path)
        if path.startswith("github:") or source.is_absolute() or ".." in source.parts:
            return False, "FTS_SOURCE_PATH_UNSAFE"
        document = project / source
        if (not document.is_file() or document.is_symlink()
                or sha256_file(document) != source_hash):
            return False, "FTS_ORIGINAL_SOURCE_CHANGED"

    # For PDFs without a separately extracted text representation, only hashes
    # are verifiable without invoking an external converter or OCR.
    if actual.suffix.lower() == ".pdf":
        return True, "SOURCE_HASH_ONLY_PDF"
    if actual.suffix.lower() == ".json" and hit.get("kind") in {"decision", "research"}:
        note = read_json(actual)
        data = str(note["title"]) + "\n" + str(note["text"])
    else:
        data = actual.read_text(encoding="utf-8")
    pages = data.split("\f")
    if page > len(pages):
        return False, "CITATION_PAGE_INVALID"
    part = pages[page - 1]
    if (
        offset + len(excerpt) > len(part)
        or part[offset:offset + len(excerpt)] != excerpt
        or part.count("\n", 0, offset) + 1 != line
    ):
        return False, "CITATION_POSITION_INVALID"
    return True, "TEXT_AND_POSITION_VERIFIED"


def evaluate(repo_root: Path, project: Path, scenario_file: Path) -> dict[str, Any]:
    """Read-only acceptance: no persistent project files or remote calls."""
    cases = _cases(scenario_file)
    assert_no_symlinks(project, label="projet à qualifier")
    if validate_input_integrity(project):
        raise ValueError("intake du projet altéré, qualification refusée")
    current = {
        item["repository"]: item["current_commit"]
        for item in github_refresh.inspect(project)
    }
    results: list[dict[str, Any]] = []
    for case in cases:
        beginning = time.perf_counter()
        hits = retrieve(repo_root, project, case["query"])
        elapsed_ms = round((time.perf_counter() - beginning) * 1000, 2)
        # The second retrieval must yield identical reference identities, not
        # identical performance. It is not a benchmark of model answers.
        repeat = retrieve(repo_root, project, case["query"])
        identity = [
            (h["path"], h["excerpt_sha256"], h["source_sha256"]) for h in hits
        ]
        again = [
            (h["path"], h["excerpt_sha256"], h["source_sha256"]) for h in repeat
        ]
        paths = [str(item["path"]) for item in hits]
        expected = case.get("required_paths_contain", [])
        forbidden = case.get("forbidden_paths_contain", [])
        checked = [_citation(project, hit, current) for hit in hits]
        wrong = [reason for valid, reason in checked if not valid]
        present = sum(any(fragment in path for path in paths) for fragment in expected)
        empty = bool(case.get("expect_empty", False))
        size = sum(len(str(hit["text"])) for hit in hits)
        conditions = {
            "expected_coverage": present == len(expected),
            "no_forbidden_paths": all(
                fragment not in path for fragment in forbidden for path in paths
            ),
            "min_hits": len(hits) >= case.get("minimum_hits", 1),
            "min_sources": len(set(paths)) >= case.get("minimum_distinct_sources", 1),
            "within_bounds": len(hits) <= MAX_HITS and size <= MAX_CHARS,
            "fresh_citations": all(not hit.get("stale") for hit in hits),
            "source_integrity": not wrong,
            "stable_ranking": identity == again,
            "expected_emptiness": not hits if empty else True,
        }
        if empty:
            conditions["min_hits"] = True
            conditions["min_sources"] = True
        passed = all(conditions.values())
        results.append({
            "id": case["id"], "status": "PASS" if passed else "FAIL",
            "elapsed_ms": elapsed_ms, "hit_count": len(hits),
            "distinct_sources": len(set(paths)),
            "expected_coverage": (
                round(present / len(expected), 3) if expected else None
            ),
            "character_count": size, "paths": paths,
            "citation_checks": [reason for _ok, reason in checked],
            "conditions": conditions, "errors": wrong,
        })
    passed_count = sum(result["status"] == "PASS" for result in results)
    partial = any(
        "SOURCE_HASH_ONLY_PDF" in result["citation_checks"] for result in results
    )
    return {
        "schema_version": 1, "project_id": project.name,
        "status": (
            "FAIL" if passed_count < len(results)
            else "PASS_WITH_LIMITATIONS" if partial else "PASS"
        ),
        "passed": passed_count, "total": len(results),
        "backend": "local-only", "sent_to_cloud": False,
        "agent_answer_graded": False, "operator_skill_certified": False,
        "environment_certified": False,
        "note": (
            "Valide seulement les scénarios de recherche de ce corpus à cette date. "
            "Ne prouve ni transfert réseau absent sur l'hôte, ni véracité documentaire, "
            "ni bon comportement d'un LLM; recette Fedora réelle distincte."
        ),
        "cases": results,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clawfedora-retrieval-acceptance",
        description="Contrôles reproductibles, locaux et sans extraits de la recherche croisée",
    )
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--cases", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        runtime = resolve_runtime_root(str(args.runtime_root) if args.runtime_root else None)
        project = project_path(runtime, args.project_id)
        root = Path(__file__).resolve().parents[2]
        result = evaluate(root, project, args.cases)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] != "FAIL" else 1
    except (OSError, ValueError, TypeError, KeyError, UnicodeError) as exc:
        print(json.dumps({
            "status": "REFUSED", "reason": str(exc),
        }, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
