from __future__ import annotations

import base64
import json
import zlib
from pathlib import Path
from typing import Any
from urllib.parse import quote
from xml.etree import ElementTree as ET

import pytest
from test_daily_worker import planned as planned

from clawfedora.agent_tools import diagram, invoke
from clawfedora.agents import deploy_workspaces
from clawfedora.drawio import inspect_diagram, native_diagram, normalize_diagram
from clawfedora.learning import awaiting, submit
from clawfedora.project_common import read_json
from clawfedora.project_engine import (
    ANALYSIS_FIELDS,
    create_assignments,
    create_clarifications,
    store_analysis,
    store_plan,
    transition_project,
)
from clawfedora.project_intake import create_project
from clawfedora.project_worker import _collect, run_project_tasks

ROOT = Path(__file__).resolve().parents[1]


def compressed_diagram(xml: str, *, trailing: bytes = b"") -> str:
    compressor = zlib.compressobj(wbits=-15)
    encoded = quote(xml, safe="~()*!.'-").encode()
    compressed = compressor.compress(encoded) + compressor.flush() + trailing
    return (
        '<mxfile><diagram id="page" name="Infrastructure">'
        + base64.b64encode(compressed).decode()
        + "</diagram></mxfile>"
    )


def test_editor_saves_are_normalized_locally_without_changing_graph_content() -> None:
    original = native_diagram(["Réseau & OPS", "CI"], [[0, 1]])
    tree = ET.fromstring(original)
    model = tree.find("diagram/mxGraphModel")
    assert model is not None
    imported = normalize_diagram(compressed_diagram(ET.tostring(model, encoding="unicode")))
    assert 'compressed="false"' in imported and "Réseau &amp; OPS" in imported
    assert inspect_diagram(imported)["links"] == 1
    assert normalize_diagram(original) == original


@pytest.mark.parametrize(
    "content",
    [
        "<mxfile><diagram>not-base64!</diagram></mxfile>",
        "<mxfile><diagram>ééé</diagram></mxfile>",
        "<mxfile><diagram>eA==</diagram></mxfile>",
        compressed_diagram("x" * 180001),
        compressed_diagram("<!DOCTYPE mxGraphModel><mxGraphModel/>"),
        compressed_diagram("<mxGraphModel/>", trailing=b"second-stream"),
        compressed_diagram("<svg/>"),
        "<mxfile/>",
    ],
)
def test_invalid_editor_saves_and_decompression_bombs_are_rejected(content: str) -> None:
    with pytest.raises(ValueError, match="Draw.io"):
        normalize_diagram(content)


def create_drawio_project(runtime: Path) -> Path:
    deploy_workspaces(ROOT, runtime)
    project = create_project(ROOT, runtime, "drawio-learning", "Mon schéma Draw.io")
    store_analysis(
        ROOT,
        project,
        {
            **{key: [] for key in ANALYSIS_FIELDS},
            "summary": "Comprendre un flux de déploiement",
            "source_coverage": [],
        },
    )
    create_clarifications(ROOT, project)
    transition_project(ROOT, project, "ANALYZED", actor="chef-operations", reason="cadrage")
    store_plan(
        ROOT,
        project,
        {
            "workstreams": ["architecture"],
            "tasks": [
                {
                    "id": "design",
                    "role": "architecte-solutions",
                    "title": "Schéma du flux",
                    "objective": "Expliquer et compléter le schéma",
                    "depends_on": [],
                    "expected_outputs": ["diagrams/design/infra.drawio"],
                    "acceptance_criteria": ["Flux motivé et choix expliqué"],
                }
            ],
        },
    )
    transition_project(ROOT, project, "PLANNED", actor="chef-operations", reason="plan")
    create_assignments(ROOT, project)
    transition_project(ROOT, project, "ASSIGNED", actor="chef-operations", reason="affectation")
    return project


def diagram_starter(runtime: Path, role: str, prompt: str, _session: str) -> dict[str, Any]:
    task = json.loads(prompt.split("\n", 1)[1])
    generated = invoke(
        runtime,
        role,
        runtime / "workspaces" / role,
        "clawfedora_diagram",
        {
            "nodes": ["Git", "TODO : préciser le contrôle"],
            "edges": [[0, 1]],
        },
    )
    return {
        "files": {task["expected_outputs"][0]: generated["drawio_reference"]},
        "summary": "Compléter le contrôle du flux et justifier le choix.",
    }


def test_guided_diagram_is_private_until_review_of_actual_edited_xml(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    project = create_drawio_project(runtime)
    result = run_project_tasks(
        ROOT, runtime, project, runner=lambda *args: diagram_starter(runtime, *args)
    )
    assert result[0]["status"] == "AWAITING_PRACTICE"
    item = awaiting(project)[0]
    path = "diagrams/design/infra.drawio"
    assert item["files"][path].startswith("<mxfile") and not (project / path).exists()
    edited = item["files"][path].replace("TODO : préciser le contrôle", "CI : vérifier la syntaxe")
    model = ET.fromstring(edited).find("diagram/mxGraphModel")
    assert model is not None
    submit(
        ROOT,
        runtime,
        project,
        "design",
        {
            "files": {path: compressed_diagram(ET.tostring(model, encoding="unicode"))},
            "human_approved": True,
            "explanation": "Je vérifie la syntaxe avant le déploiement.",
            "observations": "Schéma documentaire; pas de déploiement réel.",
        },
    )
    assert not (project / path).exists()
    from clawfedora.learning import pending_feedback

    submitted = pending_feedback(project)[0]["files"][path]
    assert "CI : vérifier la syntaxe" in submitted and "<mxGraphModel" in submitted

    def review(_role: str, prompt: str, _session: str) -> dict[str, Any]:
        data = json.loads(prompt.split("\n", 1)[1])
        assert (Path(data["snapshot"]) / path).read_text() == submitted
        assert data["checks"][0]["format"] == "drawio"
        assert data["checks"][0]["runtime_tested"] is False
        return {
            "verdict": "PASS",
            "feedback": "Flux expliqué dans cet exemple simulé.",
            "next_action": "Vérifier la CI réelle dans ton exercice.",
            "criteria": [{"passed": True, "evidence": "Flux présent dans le fichier modifié."}],
        }

    assert run_project_tasks(ROOT, runtime, project, runner=review)[0]["status"] == "REVIEWED"
    assert (project / path).read_text() == submitted
    proof = read_json(project / "evidence/design/learning-feedback.json")
    assert proof["checks"][0]["shapes"] == 2 and proof["runtime_tested"] is False


def test_native_cells_are_editable_with_literal_labels_and_connected_edges() -> None:
    label = '<script>"OPS" & réseau</script>'
    generated = diagram({"nodes": [label, "CI"], "edges": [[0, 1]]})
    tree = ET.fromstring(generated["drawio"])
    root = tree.find("diagram/mxGraphModel/root")
    assert root is not None
    assert [cell.get("id") for cell in root] == ["0", "1", "n0", "n1", "e0"]
    vertex = root.find("mxCell[@id='n0']")
    edge = root.find("mxCell[@id='e0']")
    assert vertex is not None and edge is not None
    assert vertex.get("value") == label and "html=0;" in str(vertex.get("style"))
    assert edge.get("source") == "n0" and edge.get("target") == "n1"
    geometry = vertex.find("mxGeometry")
    assert geometry is not None and geometry.get("x") == "170"
    geometry.set("x", "320")
    vertex.set("value", "Mon choix expliqué")
    edited = ET.tostring(tree, encoding="unicode")
    report = inspect_diagram(edited)
    assert report["shapes"] == 2 and report["links"] == 1
    assert report["runtime_tested"] is False and "Mon choix expliqué" in edited
    assert generated["renderer"] == "drawio-xml"
    assert "<script>" not in generated["svg"] and "marker-end" in generated["svg"]


def test_native_drawio_budgets_and_userobject_ids() -> None:
    labels = ["é" * 60] * 8
    edges = [[i % 7, i % 7 + 1] for i in range(12)]
    assert len(diagram({"nodes": labels, "edges": edges})["drawio"].encode()) < 16000
    document = ET.fromstring(native_diagram(["Service"], []))
    root = document.find("diagram/mxGraphModel/root")
    assert root is not None
    vertex = root.find("mxCell[@id='n0']")
    assert vertex is not None
    root.remove(vertex)
    del vertex.attrib["id"]
    wrapper = ET.SubElement(root, "object", {"id": "n0", "label": "Mon service"})
    wrapper.append(vertex)
    assert inspect_diagram(ET.tostring(document, encoding="unicode"))["shapes"] == 1


@pytest.mark.parametrize(
    "content",
    [
        "",
        "x" * 60001,
        "<mxfile>",
        "<svg/>",
        '<!DOCTYPE mxfile [<!ENTITY x "boom">]><mxfile>&x;</mxfile>',
        "<mxfile><diagram>compressed-base64</diagram></mxfile>",
        "<mxGraphModel/>",
        '<mxGraphModel><root><mxCell id="0"/><mxCell id="0"/></root></mxGraphModel>',
        '<mxGraphModel><root><mxCell/><mxCell id="1"/></root></mxGraphModel>',
        '<mxGraphModel><root><mxCell id="0"/><mxCell id="1"/></root></mxGraphModel>',
    ],
)
def test_invalid_or_compressed_xml_is_rejected(content: str) -> None:
    with pytest.raises(ValueError, match="Draw.io"):
        inspect_diagram(content)


@pytest.mark.parametrize(
    "old,new",
    [
        ('width="330"', 'width="nan"'),
        ('width="330"', 'width="-1"'),
        ('width="330"', 'width="huge"'),
        ('target="n1"', 'target="missing"'),
        ('vertex="1"', 'vertex="1" edge="1"'),
        ('parent="1"', 'parent="missing"'),
        ('<mxGeometry x="170" y="20" width="330" height="48" as="geometry" />', ""),
    ],
)
def test_broken_geometry_or_connections_are_rejected(old: str, new: str) -> None:
    value = native_diagram(["Git", "CI"], [[0, 1]])
    assert old in value
    with pytest.raises(ValueError, match="Draw.io"):
        inspect_diagram(value.replace(old, new, 1))


def test_collection_validates_all_drawio_files_before_publishing(
    planned: tuple[Path, Path],
) -> None:
    from test_daily_worker import ROOT

    _runtime, project = planned
    task = {
        "role": "architecte-solutions",
        "id": "design-choice",
        "expected_outputs": [
            "diagrams/design-choice/infra.drawio",
            "diagrams/design-choice/preview.svg",
        ],
    }
    files = {task["expected_outputs"][0]: "<broken>", task["expected_outputs"][1]: "<svg/>"}
    with pytest.raises(ValueError, match="XML invalide"):
        _collect(ROOT, project, task, {"files": files})
    assert not (project / task["expected_outputs"][1]).exists()
    files[task["expected_outputs"][0]] = native_diagram(["CI"], [])
    _collect(ROOT, project, task, {"files": files})
    assert (project / task["expected_outputs"][0]).read_text() == files[task["expected_outputs"][0]]
