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
    "docs/ARCHITECTURE_LOCALE_QWEN_ORNITH.md",
    "docs/LABORATOIRE_DEVOPS.md",
    "docs/PREUVES_CI_GITHUB_GITLAB.md",
    "docs/RECHERCHE_LOCALE_SOURCES.md",
    "docs/STREAMING_SSE_PREPARATION.md",
    "docs/EVALUATION_AGENTS.md",
    "docs/archives/2026/PROGRAMME_AMELIORATION_2026.md",
    "docs/EXEMPLE_PARCOURS_DEVOPS.md",
    "docs/archives/2026/PLAN_QUALITE_2026.md",
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
    assert "deux modèles" in roles.lower() and "Ornith" in roles
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


def test_local_documentation_matches_seven_agents_and_two_models() -> None:
    models = yaml.safe_load((ROOT / "config/model_catalog.yaml").read_text())["models"]
    routing = yaml.safe_load((ROOT / "config/core/model_routing.yaml").read_text())
    agents = yaml.safe_load((ROOT / "config/core/agents.yaml").read_text())["agents"]
    cloud = yaml.safe_load((ROOT / "config/core/cloud_policy.yaml").read_text())
    assert set(models) == {"qwen-max", "ornith-code"}
    assert all(spec["provider"] == "ollama" for spec in models.values())
    assert cloud["policy"]["retired"] is True
    assert routing["policy"]["local_only"] is True
    assert routing["policy"]["local_to_cloud_fallback"] == "forbidden"
    assert set(routing["agents"]) == set(agents)
    assert routing["agents"]["ingenieur-devops"]["local_primary"] == "ornith-code"
    assert all(spec["local_primary"] == "qwen-max" for role, spec in routing["agents"].items()
               if role != "ingenieur-devops")
    for name in ("README.md", "docs/GUIDE.md",
                 "docs/ARCHITECTURE_LOCALE_QWEN_ORNITH.md",
                 "docs/fiches/07-roles-et-outils.md"):
        content = (ROOT / name).read_text()
        assert "Qwen" in content and "Ornith" in content, name


def test_local_social_preview_contains_the_two_models() -> None:
    cover = ROOT / ".github/social-preview.svg"
    picture = ElementTree.parse(cover).getroot()
    assert picture.find("{http://www.w3.org/2000/svg}title") is not None
    content = cover.read_text(encoding="utf-8")
    assert "local" in content and "Qwen" in content and "Ornith" in content
    assert "DeepSeek" not in content and "OpenRouter" not in content


def test_fedora_is_native_host_and_rocky_validation_is_only_optional() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "docs/archives/2026/PROGRAMME_AMELIORATION_2026.md").read_text(
        encoding="utf-8"
    )
    lab = (ROOT / "docs/LABORATOIRE_DEVOPS.md").read_text(encoding="utf-8")
    assert "Fedora est le système hôte du projet IA" in readme
    assert "Aucune installation de Rocky" in readme
    assert "l'Atelier natif se lance comme service utilisateur" in readme
    assert "Open WebUI sous Podman reste facultatif" in readme
    assert "aucun prérequis Rocky pour OpenClaw" in roadmap
    assert "Streaming canary prêt en code" in roadmap
    assert "Pilotage visuel des projets" in roadmap
    assert roadmap.index("Streaming canary prêt en code") < roadmap.index(
        "Option hors cœur IA uniquement si utile"
    )
    assert "Ce module ne sert pas à faire fonctionner OpenClaw" in lab
    assert "n'a pas besoin" in lab and "Rocky Linux" in lab


def test_current_guides_and_editable_diagrams_are_local_only() -> None:
    for name in ("README.md", "docs/GUIDE.md",
                 "docs/fiches/07-roles-et-outils.md",
                 "docs/ARCHITECTURE_LOCALE_QWEN_ORNITH.md"):
        content = (ROOT / name).read_text(encoding="utf-8")
        assert "Qwen" in content and "Ornith" in content, name
    for stem in ("atelier-architecture", "atelier-roles"):
        svg = ROOT / "docs/diagrams" / (stem + ".svg")
        drawio = ROOT / "docs/diagrams" / (stem + ".drawio")
        ElementTree.parse(svg)
        ElementTree.parse(drawio)
        for path in (svg, drawio):
            content = path.read_text(encoding="utf-8")
            assert "Qwen" in content and "Ornith" in content, path
            assert "DeepSeek" not in content and "OpenRouter" not in content, path

