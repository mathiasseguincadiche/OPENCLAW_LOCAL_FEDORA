"""Summarize C08 regressions already executed by the quality job."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from defusedxml.ElementTree import fromstring

CONTROLS = {
    "preparation": {
        "test_daily_worker": (
            "test_bad_document_index_is_reported_and_can_resume_without_spending_attempts",
            "test_worker_blocks_unverifiable_handoff_before_inference",
        ),
    },
    "interruption_and_replay": {
        "test_project_pause": (
            "test_interrupted_task_is_detected_and_retried_with_fresh_session",
            "test_resume_finishes_publication_without_running_the_producer_again",
            "test_resume_refuses_modified_output_of_an_interrupted_publication",
        ),
    },
    "invalid_outputs_and_concurrency": {
        "test_daily_worker": (
            "test_failed_model_output_is_recorded_without_promoting_files",
            "test_exhausted_local_attempts_require_operator_intervention",
            "test_worker_refuses_concurrent_jobs_and_gaming",
        ),
        "test_structured_response": ("test_duplicate_json_keys_fail_closed",),
    },
    "local_protection": {
        "test_usage_view": (
            "test_corrupt_worker_status_respects_lock_and_recovers_on_next_real_update",
            "test_worker_progress_refuses_linked_status",
        ),
        "test_daily_worker": ("test_guard_rejects_protected_snapshot_modification",),
        "test_project_resume": ("test_continuity_distinguishes_current_audit_and_stale_deliverable",),
    },
    "remote_boundaries": {
        "test_github_remote": ("test_read_only_settings_audit_distinguishes_unavailable",),
        "test_notion_write": ("test_exact_approval_and_single_use", "test_remote_drift_refuses_write",
                             "test_no_redirect_and_no_unscoped_http"),
    },
}


def report(junit: Path, output: Path, commit: str) -> None:
    if re.fullmatch(r"[a-f0-9]{40}", commit) is None:
        raise ValueError("SHA Git testé invalide")
    data = junit.read_bytes()
    root = fromstring(data, forbid_dtd=True)
    cases: dict[tuple[str, str], list[bool]] = {}
    for case in root.findall(".//testcase"):
        module = case.get("classname", "").rsplit(".", 1)[-1]
        name = case.get("name", "").split("[", 1)[0]
        passed = all(child.tag not in {"failure", "error", "skipped"} for child in case)
        cases.setdefault((module, name), []).append(passed)

    controls = {}
    for label, modules in CONTROLS.items():
        tests = {}
        for module, names in modules.items():
            for name in names:
                instances = cases.get((module, name), [])
                if not instances or not all(instances):
                    raise ValueError(f"{label} : contrôle manquant ou en échec ({name})")
                tests[f"{module}.{name}"] = len(instances)
        controls[label] = {"verdict": "PASS", "tests": tests}
    result = {
        "schema": 1, "campaign": "C08_RESILIENCE_SYNTHETIC", "verdict": "PASS",
        "tested_commit": commit, "junit_sha256": hashlib.sha256(data).hexdigest(),
        "controls": controls,
    }
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"ATLAS_C08=PASS commit={commit} controls={len(controls)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("junit", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("commit")
    args = parser.parse_args()
    report(args.junit, args.output, args.commit)
