"""Create a local, honest repository documentation skeleton without any GitHub access.

No assumed license, CI, successful execution, image or user skill. Does not
overwrite or modify an existing nonempty directory.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


class ScaffoldError(ValueError):
    """Refuse ambiguous or destructive project scaffolding."""


def _title(value: str) -> str:
    if not 2 <= len(value.strip()) <= 100 or "\n" in value or "<" in value:
        raise ScaffoldError("nom de projet invalide")
    return value.strip()


def _slug(value: str) -> str:
    if re.fullmatch(r"[a-z][a-z0-9-]{1,62}", value) is None or value.endswith("-"):
        raise ScaffoldError("slug de projet invalide")
    return value


def skeleton(name: str, slug: str) -> dict[str, str]:
    """Generate only documentation and governance, never fake application code."""
    name = _title(name)
    slug = _slug(slug)
    return {
        "README.md": f"""# {name}

**Projet technique à construire : [problème métier ou opérationnel à préciser].**

> **État initial :** projet créé, implémentation non vérifiée. Aucune démonstration, capture ou validation de laboratoire n'est présumée.

## Comprendre le projet

[À qui s'adresse-t-il ? Que doit-il résoudre ? Pourquoi ?]

## Architecture

[Insérer une vue de présentation documentée, puis une vue technique sourcée.]
[Architecture et décisions](docs/architecture.md).

## Préparer et démarrer

[Consulter le guide de préparation](docs/installation.md). Aucune commande de
déploiement ne peut être proposée tant que la stack et la cible ne sont pas décidées.

## Statut et preuves

[État réel](STATUS.md) · [Feuille de route](ROADMAP.md) ·
[Contrats et preuves](evidence/README.md).

## Documentation

[Index documentaire](docs/README.md) · [Exploitation](docs/exploitation.md) ·
[Schémas](docs/diagrams/README.md).

## Contribution et sécurité

[Contribuer](CONTRIBUTING.md) · [Sécurité](SECURITY.md).

## Licence et provenance

**Licence non choisie.** Sélectionner volontairement une licence appropriée,
ajouter le fichier LICENSE et préciser l'origine des composants avant publication.

Référence interne : {slug}. Ne pas publier de notes Notion personnelles.
""",
        "STATUS.md": f"""# État réel — {name}

| Élément | Avancement | Contrôle | Preuve |
| --- | --- | --- | --- |
| Structure documentaire | Réalisé dans la proposition locale | Non vérifié sur GitHub | Aucun lien distant |
| Application / infrastructure | Prévu | Non vérifié | Aucune |
| CI/CD applicative | Prévu | Non vérifié | Aucune |
| Exploitation / restauration | Prévu | Non vérifié | Aucune |

Toute évolution exige une preuve datée, sur une cible identifiée, à une révision donnée.
""",
        "ROADMAP.md": f"""# Feuille de route — {name}

1. Définir le contrat et les critères de réussite.
2. Choisir les composants, les contraintes et le schéma d'architecture.
3. Préparer l'environnement : inventaire, installation conditionnelle et vérification.
4. Construire et tester le premier incrément reproductible.
5. Documenter exploitation, sécurité, sauvegarde et retour arrière.
6. Qualifier sur la cible réelle et relier chaque preuve à STATUS.

**Toutes les étapes sont prévues, pas exécutées.**
""",
        "docs/README.md": """# Documentation

- [Accueil du dépôt](../README.md)
- [Architecture et décisions](architecture.md)
- [Préparer et installer](installation.md)
- [Exploitation et reprise](exploitation.md)
- [Schémas et sources graphiques](diagrams/README.md)
- [État et preuves](../STATUS.md)
- [Feuille de route](../ROADMAP.md)

La documentation technique publique reste distincte du journal d'apprentissage Notion.
""",
        "docs/architecture.md": """# Architecture et décisions

## Besoin et exigences

[Utilisateurs, problèmes, interfaces et contraintes.]

## Vue de présentation

[Source .drawio + export .svg à créer. N'inventer aucune topologie.]

## Vue technique

[Flux, protocoles, ports, secrets, accès, stockage, monitoring et reprise.]

## ADR

**Décision :** à établir.

**Alternatives et compromis :** à établir.

## Contrôles attendus

[Définir les tests avant de déclarer l'architecture vérifiée.]
""",
        "docs/installation.md": """# Préparer l'environnement et installer les outils

## Pourquoi et où

[But, système d'exploitation, hôte, droits et versions.]

## Inventaire avant modification

[Identifier les outils présents et leurs versions. Ne rien réinstaller par habitude.]

## Installer seulement ce qui manque

[Commandes exactes à définir après le choix de la stack et de l'OS.]

## Configurer et valider

[Tests non destructifs, SELinux/pare-feu le cas échéant, service, logs et sortie attendue.]

## Diagnostic et rollback

[Écarts possibles, actions sûres, arrêt et retour arrière.]

**Statut initial : non exécuté.**
""",
        "docs/exploitation.md": """# Exploiter et rétablir

## Situations opérationnelles

[Surveillance, métriques, journaux, sécurité, sauvegarde et incidents.]

## Diagnostic

[Symptômes → hypothèses → observations → correction minimale → revalidation.]

## Intervention et restauration

[Préparation, risques, permissions, sauvegarde, étapes, rollback et preuve.]

**Aucune restauration n'est présumée réussie.**
""",
        "docs/diagrams/README.md": """# Schémas professionnels

Créer deux vues différentes quand elles sont justifiées :
1. Présentation — problème et responsabilités.
2. Architecture technique — composants, interfaces, flux, ports et frontières.

Chaque schéma versionné aura une source .drawio et un export .svg
issu de la source, avec légende et contrôle du rendu clair/sombre/mobile.
Une bannière décorative n'est pas un schéma technique.
""",
        "evidence/README.md": """# Preuves datées et reproductibles

Une preuve comporte : date, hôte ou runner, commit/digest, objectif,
commandes exécutées, attendu, observé, résultat, risques et limites.

Ce dossier est initialement vide de preuve technique. Ne créer aucun log
fictif ou capture simulée pour représenter un test accompli.
""",
        "CONTRIBUTING.md": """# Contribuer

1. Décrire la demande dans une issue.
2. Travailler dans une branche courte et traçable.
3. Proposer une PR documentée avec les tests exécutés et les limites.
4. Relire les risques et le retour arrière.
5. Faire valider les changements avant fusion.

Ne jamais publier de secrets, de données réelles ou de notes Notion privées.
""",
        "SECURITY.md": """# Sécurité

Ce dépôt est un projet technique en cours de construction. Ne pas présumer
qu'il peut être exposé publiquement.

Pour une vulnérabilité, utiliser une méthode privée si GitHub l'offre ;
ne pas publier d'exploit ni de jeton dans une issue publique.

Les contrôles de dépendances et de configuration sont à définir, exécuter
et dater selon les composants réellement choisis.
""",
        ".gitignore": """.env
.env.*
!.env.example
*.pem
*.key
*.tfstate
*.tfstate.*
*.tfvars
*.tfplan
.terraform/
.venv/
node_modules/
__pycache__/
backups/
secrets/
""",
        ".github/pull_request_template.md": """## Pourquoi cette modification ?

[Contexte, impact et périmètre.]

## Fichiers modifiés et décisions

[Énumérer les changements sans inventer.]

## Tests réellement exécutés

| Test | Environnement | Résultat / preuve |
| --- | --- | --- |
| […] | […] | Non exécuté |

## Sécurité, limites et rollback

[Évaluer les risques et les étapes de vérification.]

- [ ] Aucun secret ni résultat personnel inventé.
- [ ] Documentation, images et schémas vérifiés.
- [ ] Validation humaine avant fusion.
""",
        ".github/ISSUE_TEMPLATE/bug.md": """---
name: Rapport d'anomalie
about: Décrire une anomalie reproductible sans secret
title: "[Bug] "
labels: bug
---

## Contexte, version et cible

## Comportement attendu

## Observations réelles

## Reproduction sans données sensibles

## Hypothèses, vérifications et preuves

## Risques et proposition de correction
""",
    }


def scaffold_plan(name: str, slug: str, destination: Path) -> dict[str, object]:
    files = skeleton(name, slug)
    if destination.is_symlink():
        raise ScaffoldError("destination symbolique interdite")
    if destination.exists():
        if not destination.is_dir():
            raise ScaffoldError("destination non répertoire")
        if any(destination.iterdir()):
            raise ScaffoldError("destination non vide : aucun écrasement autorisé")
    return {
        "mode": "OFFLINE_SCAFFOLD_PLAN",
        "name": _title(name),
        "slug": _slug(slug),
        "destination": str(destination),
        "files": sorted(files),
        "remote_repository_created": False,
        "warning": "Aucun code applicatif, CI effective, licence, preuve ou dépôt distant créé.",
    }


def apply_scaffold(
    name: str, slug: str, destination: Path, *, approval: str,
) -> dict[str, object]:
    plan = scaffold_plan(name, slug, destination)
    if approval != _title(name):
        raise ScaffoldError("approbation explicite du nom de projet requise")
    destination.mkdir(parents=True, exist_ok=True)
    for relative, content in skeleton(name, slug).items():
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as stream:
            stream.write(content)
    return {**plan, "mode": "LOCAL_SCAFFOLD_CREATED"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="clawfedora-github-scaffold")
    parser.add_argument("--name", required=True)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--approve-name", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        plan = (
            apply_scaffold(args.name, args.slug, args.destination, approval=args.approve_name)
            if args.apply
            else scaffold_plan(args.name, args.slug, args.destination)
        )
    except (ScaffoldError, OSError) as exc:
        print(json.dumps({"mode": "REFUSED", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
