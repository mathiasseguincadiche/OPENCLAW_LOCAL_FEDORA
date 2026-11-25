"""Static editorial preparation is not a native rendering or human review."""
import hashlib
from pathlib import Path

import pytest

from clawfedora.document_review import BLOCKERS, KINDS, RUBRIC, inspect_document

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("kind", sorted(KINDS))
@pytest.mark.parametrize("support", ["markdown", "github", "notion", "document"])
def test_editorial_review_never_invents_verdict(kind, support):
    content = "# Projet\n\n## Architecture\n\nContenu de démonstration."
    result = inspect_document(content, kind, support)
    assert result["assessment"] == "STRUCTURAL_REVIEW_ONLY_NO_EDITORIAL_PASS"
    assert result["content_sha256"] == hashlib.sha256(content.encode()).hexdigest()
    assert result["editorial_score"] is None
    assert sum(row["weight"] for row in result["editorial_rubric"]) == 100
    assert all(row["verdict"] == "NOT_EVALUATED" for row in result["editorial_rubric"])
    assert {row["id"] for row in result["blocking_criteria"]} == set(BLOCKERS)
    assert all(row["verdict"] == "NOT_EVALUATED" for row in result["blocking_criteria"])
    assert result["support_review"]


def test_invalid_support_is_refused():
    with pytest.raises(ValueError, match="support"):
        inspect_document("# Test", "readme", "auto-publish")


def test_public_contract_and_demos_exist():
    assert sum(weight for _, weight, _ in RUBRIC) == 100
    assert (ROOT / "docs/EXCELLENCE_EDITORIALE.md").is_file()
    for name in ("README.md", "github-demo.md", "notion-demo.md"):
        assert (ROOT / "docs/editorial-demo" / name).is_file()
