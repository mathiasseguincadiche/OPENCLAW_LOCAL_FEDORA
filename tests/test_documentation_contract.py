"""Prevent stale user-facing capability claims from surviving configuration changes."""

from pathlib import Path

from clawfedora.chat_files import MAX_STANDALONE_TEXT_BYTES, MAX_STANDALONE_TEXT_FILES
from clawfedora.core_config import core_contract, root_contract

ROOT = Path(__file__).resolve().parents[1]


def test_chat_guide_tracks_cloud_context_and_standalone_file_caps() -> None:
    cloud = core_contract(ROOT, "cloud_policy.yaml")
    webui = root_contract(ROOT, "webui_policy.yaml")
    guide = (ROOT / "docs/fiches/03-discuter.md").read_text(encoding="utf-8")
    files = (ROOT / "docs/fiches/06-fichiers-et-schemas.md").read_text(
        encoding="utf-8"
    )
    context = f"{int(cloud['model']['context_tokens']):,}".replace(",", " ")
    assert context in guide
    assert "3 Mio" in guide
    assert int(webui["max_history_bytes"]) == 32_000
    assert str(MAX_STANDALONE_TEXT_BYTES // 1_000) in guide
    assert "quatre" in guide and MAX_STANDALONE_TEXT_FILES == 4
    assert "local" in files and "cloud" in files
    assert "projet" in files and "ingestion" in files


def test_public_readme_is_clear_about_unverified_runtime() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    status = (ROOT / "STATUS.md").read_text(encoding="utf-8")
    assert "PC cible reste à valider" in readme
    assert "À mesurer" in status and "OpenRouter" in status
    assert "sans créer de projet" in readme


def test_october_stabilization_docs_do_not_overclaim_runtime() -> None:
    audit = (ROOT / "docs/AUDIT_COMPLEMENTAIRE_2026_10.md").read_text(encoding="utf-8")
    status = (ROOT / "STATUS.md").read_text(encoding="utf-8")
    programme = (ROOT / "docs/PROGRAMME_AMELIORATION_2026.md").read_text(
        encoding="utf-8"
    )
    assert "fait encore `pip install --upgrade pip setuptools wheel`" not in audit
    for number in range(110, 115):
        assert f"#{number}" in audit
    assert "pas des essais sur le PC cible" in status
    assert "dépendances transitives" in programme
    assert root_contract(ROOT, "webui_policy.yaml")["release"] == "v0.12.1"
