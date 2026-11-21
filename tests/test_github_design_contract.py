"""Contract checks for the seven universal GitHub document templates."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_seven_distinct_github_templates_are_available() -> None:
    folder = ROOT / "templates/github"
    expected = {
        "readme-projet.md", "architecture-adr.md", "runbook.md", "preuve.md",
        "pull-request.md", "issue.md", "release-notes.md",
    }
    assert {path.name for path in folder.glob("*.md")} == expected
    for filename in expected:
        content = (folder / filename).read_text(encoding="utf-8")
        assert content.startswith("# ")
        assert len(content) >= 150


def test_public_and_private_sources_are_not_merged() -> None:
    charter = (ROOT / "docs/GITHUB_REPOSITORY_DESIGN_SYSTEM.md").read_text(
        encoding="utf-8",
    )
    for key in (
        "GitHub", "Notion", "README", "Draw.io", "CI/CD", "STATUS",
        "rendu", "installation",
    ):
        assert key.lower() in charter.lower()
    evidence = (ROOT / "templates/github/preuve.md").read_text(encoding="utf-8")
    assert "NON VÉRIFIÉ" in evidence
    assert "Non exécuté" in evidence
    assert "L2/L3" in evidence
    for path in (ROOT / "templates/github").glob("*.md"):
        content = path.read_text(encoding="utf-8")
        assert "Voici ma preuve réelle" not in content


def test_read_only_auditor_has_no_remote_git_commands() -> None:
    source = (ROOT / "src/clawfedora/github_quality.py").read_text(encoding="utf-8")
    assert "urllib.request" not in source
    assert "subprocess" not in source
    assert "requests.get" not in source
    assert "GitHub API" not in source
    assert "READ_ONLY_DOCUMENTARY_INVENTORY_NOT_A_RUNTIME_PROOF" in source
