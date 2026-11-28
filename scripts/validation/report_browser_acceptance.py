"""Produce the C05 report from the existing Chromium job's pytest evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from defusedxml.ElementTree import fromstring

GROUPS = {
    "official_document": (
        "observation.xml", {"test_official_document_real_chromium_observation": 1},
    ),
    "dynamic_panels": ("panels.xml", {"test_read_only_capture_waits_for_dynamic_panel": 4}),
    "network_boundaries": (
        "observation.xml", {"test_offline_document_route_serves_exactly_one_document": 1,
                            "test_panel_scope_blocks_unlisted_requests_and_freezes_local_reads": 1,
                            "test_panel_transport_refuses_redirects_and_attachments": 2},
    ),
    "approved_actions": (
        "rehearsal.xml", {
            "test_real_chromium_applies_one_rehearsal_and_records_dom_and_screenshots": 2,
            "test_approval_is_used_only_once_even_with_concurrent_calls": 1,
            "test_interrupted_attempt_cannot_reuse_approval": 1,
        },
    ),
    "navigation_refusals": (
        "rehearsal.xml", {
            "test_real_chromium_refuses_another_destination_and_another_tab": 1,
            "test_navigation_approval_cannot_bind_a_modified_destination": 1,
            "test_navigation_refuses_a_different_link_before_click": 5,
        },
    ),
    "role_handoff": (
        "rehearsal.xml", {
            "test_browser_proposals_are_read_only_and_restricted_by_role_and_scenario": 1,
            "test_role_proposal_fingerprint_binds_the_scenario_but_cannot_approve_it": 1,
        },
    ),
}


def report(directory: Path, commit: str) -> None:
    if re.fullmatch(r"[a-f0-9]{40}", commit) is None:
        raise ValueError("SHA Git testé invalide")
    filenames = {name for name, _ in GROUPS.values()}
    files = {name: (directory / name).read_bytes() for name in sorted(filenames)}
    cases = {}
    for name, data in files.items():
        root = fromstring(data, forbid_dtd=True)
        collected = root.findall(".//testcase")
        if not collected or any(
            child.tag in {"failure", "error", "skipped"} for case in collected for child in case
        ):
            raise ValueError(f"suite incomplète ou en échec : {name}")
        ids = {(case.attrib["classname"], case.attrib["name"]) for case in collected}
        if len(ids) != len(collected):
            raise ValueError(f"cas dupliqués : {name}")
        cases[name] = sorted(test for _, test in ids)

    results = {}
    for group, (file, required) in GROUPS.items():
        selected = []
        for name, count in required.items():
            matches = [test for test in cases[file] if test.split("[", 1)[0] == name]
            if len(matches) != count:
                raise ValueError(f"{group} : {name} exige {count} cas réussis")
            selected.extend(matches)
        results[group] = {"verdict": "PASS", "source": file, "tests": selected}

    screenshots = {
        f"{panel}-{width}-{scheme}.png"
        for panel in ("projects", "discussions", "github", "notion")
        for width, scheme in ((1440, "light"), (1366, "dark"), (390, "light"))
    }
    payload = {
        "schema": 1, "campaign": "C05_SYNTHETIC_BROWSER", "verdict": "PASS",
        "tested_commit": commit, "environment": "CI_CHROMIUM_SYNTHETIC",
        "controls": results,
        "junit": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
        "screenshots": {
            name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
            for name in sorted(screenshots)
        },
    }
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    (directory / "report.json").write_text(rendered, encoding="utf-8")
    print(f"ATLAS_C05=PASS commit={commit} controls={len(results)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("commit")
    args = parser.parse_args()
    report(args.directory, args.commit)
