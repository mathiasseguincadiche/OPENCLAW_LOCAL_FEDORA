"""Keep the learning guide navigable and grounded in the real project contracts."""

from __future__ import annotations

import re
from pathlib import Path
from xml.etree import ElementTree

import yaml

ROOT = Path(__file__).resolve().parents[1]
GUIDES = (
    "README.md",
    "STATUS.md",
    "docs/GUIDE.md",
    "docs/ARCHITECTURE_HYBRIDE.md",
    "docs/LABORATOIRE_DEVOPS.md",
    "docs/EVALUATION_AGENTS.md",
    "docs/PROGRAMME_AMELIORATION_2026.md",
    "docs/EXEMPLE_PARCOURS_DEVOPS.md",
    "docs/PLAN_QUALITE_2026.md",
    "docs/DECISION_MODELE.md",
    "docs/fiches/01-installer.md",
    "docs/fiches/02-premier-essai.md",
    "docs/fiches/03-discuter.md",
    "docs/fiches/04-atelier-projets.md",
    "docs/fiches/05-apprendre.md",
    "docs/fiches/06-fichiers-et-schemas.md",
    "docs/fiches/07-roles-et-outils.md",
    "docs/fiches/08-reglages.md",
    "docs/fiches/09-entretenir.md",
    "docs/fiches/10-depanner.md",
    "docs/fiches/11-comment-ca-marche.md",
    "docs/fiches/12-cloud.md",
)


def test_every_learning_link_points_to_a_real_local_file() -> None:
    links = re.compile(r"!?\[[^\]\n]+\]\(([^)]+)\)")
    for name in GUIDES:
        doc = ROOT / name
        assert doc.is_file(), name
        for target in links.findall(doc.read_text(encoding="utf-8")):
            target = target.split("#", 1)[0]
            if not target or "://" in target or target.startswith(("mailto:", "data:")):
                continue
            assert (doc.parent / target).is_file(), f"{name} → {target}"


def test_seven_agents_explained_match_canonical_policy() -> None:
    config = yaml.safe_load((ROOT / "config/core/agents.yaml").read_text(encoding="utf-8"))
    agents = config["agents"]
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    roles = (ROOT / "docs/fiches/07-roles-et-outils.md").read_text(encoding="utf-8")
    assert len(agents) == config["policy"]["exact_agent_count"] == 7
    for agent in agents.values():
        assert agent["name"] in readme
        assert agent["name"] in roles
    for tool in (
        "clawfedora_diagram",
        "clawfedora_search",
        "clawfedora_check",
        "clawfedora_lint",
        "clawfedora_artifact",
        "clawfedora_ci_report",
    ):
        assert tool in roles
    assert "même modèle" in roles or "même moteur" in roles
    assert "pas" in roles.lower() and "exécut" in roles.lower()


def test_architecture_figures_are_valid_accessible_svg() -> None:
    ns = {"svg": "http://www.w3.org/2000/svg"}
    for name in ("atelier-architecture.svg", "atelier-roles.svg"):
        path = ROOT / "docs/diagrams" / name
        picture = ElementTree.parse(path).getroot()
        assert picture.tag == "{http://www.w3.org/2000/svg}svg"
        assert picture.get("viewBox")
        assert picture.find("svg:title", ns) is not None
        assert picture.find("svg:desc", ns) is not None
        assert len(picture.findall(".//svg:rect", ns)) >= 7


def test_readme_architecture_mentions_really_pinned_webui() -> None:
    policy = yaml.safe_load((ROOT / "config/webui_policy.yaml").read_text(encoding="utf-8"))
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    architecture = (ROOT / "docs/fiches/11-comment-ca-marche.md").read_text(
        encoding="utf-8"
    )
    release = str(policy["release"]).removeprefix("v")
    assert f"Open WebUI {release}" in readme
    assert release in architecture
    assert "B580" in readme and "B580" in architecture
    assert "streaming" in architecture.lower()
    assert "cloud" in architecture.lower()
    assert "approbation" in architecture.lower()


def test_hybrid_documentation_describes_both_configured_engines() -> None:
    models = yaml.safe_load(
        (ROOT / "config/model_catalog.yaml").read_text(encoding="utf-8")
    )["models"]
    routing = yaml.safe_load(
        (ROOT / "config/core/model_routing.yaml").read_text(encoding="utf-8")
    )
    cloud = yaml.safe_load(
        (ROOT / "config/core/cloud_policy.yaml").read_text(encoding="utf-8")
    )
    assert models["qwen-max"]["provider"] == "ollama"
    assert models["cloud-main"]["provider"] == "cloud-gateway"
    assert models["cloud-main"]["runtime_id"] == cloud["model"]["upstream_id"]
    assert cloud["model"]["upstream_id"] == "deepseek/deepseek-v4.1-flash"
    assert routing["policy"]["cloud_enabled_by_default"] is False
    assert routing["policy"]["local_to_cloud_fallback"] == "forbidden"
    assert set(routing["agents"]) == set(
        yaml.safe_load((ROOT / "config/core/agents.yaml").read_text(encoding="utf-8"))[
            "agents"
        ]
    )
    for spec in routing["agents"].values():
        assert spec["local_primary"] == "qwen-max"
        assert spec["cloud_primary"] == "cloud-main"

    docs = [
        "README.md",
        "docs/GUIDE.md",
        "docs/ARCHITECTURE_HYBRIDE.md",
        "docs/fiches/07-roles-et-outils.md",
        "docs/fiches/11-comment-ca-marche.md",
        "docs/fiches/12-cloud.md",
    ]
    for name in docs:
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "Qwen" in text, name
        assert "DeepSeek" in text, name
        assert "cloud" in text.lower(), name
    strategy = (ROOT / "docs/ARCHITECTURE_HYBRIDE.md").read_text(
        encoding="utf-8"
    )
    assert "automatique" in strategy.lower()
    assert "consentement" in strategy.lower()
    assert "25 €/mois" in strategy
    assert str(cloud["model"]["context_tokens"]) in strategy.replace(" ", "")


def test_hybrid_social_preview_contains_both_models() -> None:
    cover = ROOT / ".github/social-preview.svg"
    picture = ElementTree.parse(cover).getroot()
    assert picture.find("{http://www.w3.org/2000/svg}title") is not None
    content = cover.read_text(encoding="utf-8")
    assert "hybride" in content
    assert "Qwen" in content
    assert "DeepSeek" in content
