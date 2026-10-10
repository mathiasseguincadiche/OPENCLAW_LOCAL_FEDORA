from __future__ import annotations

from pathlib import Path

import pytest

from clawfedora import chat_files
from clawfedora.project_common import read_json, write_json
from clawfedora.project_intake import create_project

ROOT = Path(__file__).resolve().parents[1]


def _upload(runtime: Path, name: str, content: bytes) -> dict[str, object]:
    path = runtime / "state/webui/data/uploads" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return {
        "id": "file-" + name,
        "filename": name,
        "path": "/app/backend/data/uploads/" + name,
        "size": len(content),
    }


def test_chat_upload_enters_the_canonical_intake_before_analysis(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    brief = tmp_path / "brief.md"
    brief.write_text("objectif", encoding="utf-8")
    project = create_project(
        ROOT,
        runtime,
        "upload-project",
        "Upload",
        intake_items=[brief],
    )
    descriptor = _upload(runtime, "architecture.yaml", b"service: api\n")
    assert chat_files.import_files(ROOT, runtime, project, [descriptor]) == ["architecture.yaml"]
    assert (project / "intake/architecture.yaml").read_text() == "service: api\n"
    index = read_json(project / "context/ingestion/index.json")
    assert {Path(item["path"]).name for item in index["documents"]} == {
        "brief.md",
        "architecture.yaml",
    }


def test_upload_cannot_escape_openwebui_storage_or_change_sources_late(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    brief = tmp_path / "brief.md"
    brief.write_text("objectif", encoding="utf-8")
    project = create_project(ROOT, runtime, "locked-project", "Locked", intake_items=[brief])
    outside = tmp_path / "outside.txt"
    outside.write_text("non", encoding="utf-8")
    with pytest.raises(ValueError, match="hors"):
        chat_files.import_files(
            ROOT,
            runtime,
            project,
            [{"filename": "outside.txt", "path": str(outside), "size": 3}],
        )
    manifest = read_json(project / "project.json")
    manifest["status"] = "ANALYZED"
    write_json(project / "project.json", manifest)
    descriptor = _upload(runtime, "late.txt", b"trop tard")
    with pytest.raises(ValueError, match="avant l'analyse"):
        chat_files.import_files(ROOT, runtime, project, [descriptor])


def test_guided_submission_maps_uploaded_names_to_expected_paths(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    brief = tmp_path / "brief.md"
    brief.write_text("objectif", encoding="utf-8")
    project = create_project(ROOT, runtime, "guided-project", "Guided", intake_items=[brief])
    task_dir = project / "context/tasks"
    task_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        task_dir / "deploy.json",
        {
            "task": {
                "id": "deploy",
                "expected_outputs": [
                    "deliverables/deploy/main.tf",
                    "deliverables/deploy/README.md",
                ],
            }
        },
    )
    first = _upload(runtime, "main.tf", b'resource "null_resource" "x" {}\n')
    second = _upload(runtime, "README.md", b"# Explication\n")
    files = chat_files.practice_files(runtime, project, "deploy", [first, second])
    assert files["deliverables/deploy/main.tf"].startswith("resource")
    assert files["deliverables/deploy/README.md"] == "# Explication\n"
    with pytest.raises(ValueError, match="inattendu"):
        chat_files.practice_files(
            runtime,
            project,
            "deploy",
            [_upload(runtime, "wrong.txt", b"x")],
        )


def test_upload_rejects_wrong_sha256(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    brief = tmp_path / "brief.md"
    brief.write_text("objectif", encoding="utf-8")
    project = create_project(ROOT, runtime, "digest-project", "Digest", intake_items=[brief])
    descriptor = _upload(runtime, "tampered.txt", b"contenu")
    descriptor["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="SHA-256"):
        chat_files.import_files(ROOT, runtime, project, [descriptor])
    assert not (project / "intake/tampered.txt").exists()


def test_fallback_inbox_is_consumed_after_success(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    brief = tmp_path / "brief.md"
    brief.write_text("objectif", encoding="utf-8")
    project = create_project(ROOT, runtime, "fallback-project", "Fallback", intake_items=[brief])
    inbox = runtime / "state/chat-import/inbox/fallback-project"
    inbox.mkdir(parents=True)
    (inbox / "source.txt").write_text("source locale", encoding="utf-8")
    assert chat_files.import_inbox(ROOT, runtime, project) == ["source.txt"]
    assert not list(inbox.iterdir())
    assert (project / "intake/source.txt").read_text() == "source locale"


def test_guided_submission_rejects_traversal_id(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    brief = tmp_path / "brief.md"
    brief.write_text("objectif", encoding="utf-8")
    project = create_project(ROOT, runtime, "guided-safe", "Safe", intake_items=[brief])
    with pytest.raises(ValueError, match="task id invalide"):
        chat_files.practice_files(runtime, project, "../../outside", [{"id": "dummy"}])


def test_upload_rejects_project_outside_runtime(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    real_runtime = tmp_path / "elsewhere"
    brief = tmp_path / "brief.md"
    brief.write_text("objectif", encoding="utf-8")
    project = create_project(ROOT, real_runtime, "elsewhere-project", "Unsafe", intake_items=[brief])
    descriptor = _upload(runtime, "poison.txt", b"not allowed")
    with pytest.raises((ValueError, FileNotFoundError)):
        chat_files.import_files(ROOT, runtime, project, [descriptor])
    assert not (project / "intake/poison.txt").exists()
