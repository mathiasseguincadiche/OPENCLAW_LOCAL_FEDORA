from __future__ import annotations

import json
from pathlib import Path

import pytest
from defusedxml.ElementTree import fromstring

from clawfedora.agent_tools import invoke
from clawfedora.agents import deploy_workspaces
from clawfedora.editorial_identity import MOTIFS, VARIANTS, render
from clawfedora.file_artifacts import read_artifact
from clawfedora.project_worker import _resolve_tool_files

ROOT = Path(__file__).resolve().parents[1]
SPEC = {
    "project": "Atlas", "tagline": "Concevoir, automatiser, exploiter",
    "variant": "hero", "motif": "network", "palette": "ocean", "section": "Présentation",
}


@pytest.mark.parametrize("variant", sorted(VARIANTS))
@pytest.mark.parametrize("motif", sorted(MOTIFS))
def test_svg_is_offline_valid_deterministic(variant, motif):
    spec = dict(SPEC, variant=variant, motif=motif)
    normalized, svg = render(spec)
    assert render(normalized) == (normalized, svg)
    root = fromstring(svg)
    assert root.tag.endswith("svg")
    assert root.get("role") == "img"
    assert "preuve technique" in svg
    assert "<script" not in svg and "href=" not in svg
    if variant == "cover":
        assert "<text" not in svg


def test_identity_rejects_bad_input_and_escapes_markup():
    for spec in (
        dict(SPEC, palette=["#FFFFFF", "#FFFFFF", "#FFFFFF"]),
        dict(SPEC, project="x" * 27),
        dict(SPEC, motif="custom"),
        dict(SPEC, variant="anything"),
        dict(SPEC, url="https://example.invalid"),
    ):
        with pytest.raises(ValueError):
            render(spec)
    _, svg = render(dict(SPEC, project="<script>"))
    assert "&lt;script&gt;" in svg and "<script>" not in svg
    fromstring(svg)


def test_managed_identity_references_and_permissions(tmp_path):
    deploy_workspaces(ROOT, tmp_path)
    role = "redacteur-pedagogique"
    workspace = tmp_path / "workspaces" / role
    request = {"format": "identity", "content": json.dumps(SPEC), "filename": "atlas.svg"}
    result = invoke(tmp_path, role, workspace, "clawfedora_artifact", request)
    refs = result["references"]
    response = {"files": {f"deliverables/atlas.{ext}": ref for ext, ref in refs.items()}}
    _resolve_tool_files(workspace, set(), {"role": role}, response)
    assert render(json.loads(response["files"]["deliverables/atlas.json"]))[1] == (
        response["files"]["deliverables/atlas.svg"]
    )
    identifier = refs["svg"].split(":")[1]
    with pytest.raises(ValueError):
        read_artifact(workspace, "chef-operations", identifier, "svg")
    with pytest.raises(ValueError):
        invoke(tmp_path, "chef-operations", tmp_path / "workspaces/chef-operations",
               "clawfedora_artifact", request)

def test_gallery_matches_the_renderer():
    for path in sorted((ROOT / "docs/editorial-demo/premium").glob("*.json")):
        _, svg = render(json.loads(path.read_text(encoding="utf-8")))
        assert path.with_suffix(".svg").read_text(encoding="utf-8") == svg, path.name
    assert len(list((ROOT / "docs/editorial-demo/premium").glob("*.svg"))) == 7


def test_identity_requires_its_editable_source(tmp_path):
    deploy_workspaces(ROOT, tmp_path)
    role = "architecte-solutions"
    workspace = tmp_path / "workspaces" / role
    request = {"format": "identity", "content": json.dumps(SPEC)}
    result = invoke(tmp_path, role, workspace, "clawfedora_artifact", request)
    response = {"files": {"deliverables/atlas.svg": result["references"]["svg"]}}
    with pytest.raises(ValueError, match="source JSON"):
        _resolve_tool_files(workspace, set(), {"role": role}, response)
