"""Local repository skeleton without automatic licensing, code or forged results."""

from pathlib import Path

import pytest

from clawfedora.github_scaffold import ScaffoldError, apply_scaffold, scaffold_plan


def test_dry_run_does_not_touch_files(tmp_path: Path) -> None:
    root = tmp_path / "future-repository"
    result = scaffold_plan("BankFlow", "bankflow", root)
    assert result["mode"] == "OFFLINE_SCAFFOLD_PLAN"
    assert result["remote_repository_created"] is False
    assert not root.exists()
    assert len(result["files"]) >= 12


def test_explicit_approval_creates_reusable_professional_skeleton(tmp_path: Path) -> None:
    root = tmp_path / "bankflow"
    with pytest.raises(ScaffoldError, match="approbation"):
        apply_scaffold("BankFlow", "bankflow", root, approval="another-name")
    result = apply_scaffold("BankFlow", "bankflow", root, approval="BankFlow")
    assert result["mode"] == "LOCAL_SCAFFOLD_CREATED"
    readme = (root / "README.md").read_text(encoding="utf-8")
    assert "BankFlow" in readme
    assert "Non vérifié" in (root / "STATUS.md").read_text(encoding="utf-8")
    assert "installer" in (root / "docs/installation.md").read_text(encoding="utf-8")
    assert "rollback" in (root / "docs/exploitation.md").read_text(encoding="utf-8")
    assert (root / ".github/pull_request_template.md").exists()
    assert (root / ".gitignore").exists()
    assert not (root / "LICENSE").exists()
    assert not (root / ".github/workflows/ci.yml").exists()
    assert not (root / ".git").exists()
    assert not (root / "evidence/test-success.md").exists()


def test_existing_repository_is_never_overwritten(tmp_path: Path) -> None:
    root = tmp_path / "already"
    root.mkdir()
    (root / "README.md").write_text("ORIGINAL\n", encoding="utf-8")
    with pytest.raises(ScaffoldError, match="non vide"):
        apply_scaffold("BankFlow", "bankflow", root, approval="BankFlow")
    assert (root / "README.md").read_text(encoding="utf-8") == "ORIGINAL\n"


def test_symlink_target_is_refused(tmp_path: Path) -> None:
    existing = tmp_path / "existing"
    existing.mkdir()
    link = tmp_path / "linked"
    link.symlink_to(existing, target_is_directory=True)
    with pytest.raises(ScaffoldError, match="symbolique"):
        scaffold_plan("BankFlow", "bankflow", link)


@pytest.mark.parametrize("name,slug", [
    ("X", "bankflow"), ("<injection>", "bankflow"),
    ("BankFlow", "Bad Flow"), ("BankFlow", "bankflow-"),
])
def test_invalid_projects_are_refused(
    tmp_path: Path, name: str, slug: str,
) -> None:
    with pytest.raises(ScaffoldError):
        scaffold_plan(name, slug, tmp_path / "target")


def test_existing_empty_directory_can_be_used(tmp_path: Path) -> None:
    root = tmp_path / "empty"
    root.mkdir()
    assert scaffold_plan("BankFlow", "bankflow", root)["files"]
    assert apply_scaffold(
        "BankFlow", "bankflow", root, approval="BankFlow",
    )["mode"] == "LOCAL_SCAFFOLD_CREATED"
