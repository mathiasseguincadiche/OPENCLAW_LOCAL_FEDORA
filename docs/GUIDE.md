# Guide de l'atelier

Ce guide donne la trame. Chaque étape tient en quelques lignes et renvoie vers une fiche qui contient le détail. Tu peux le suivre dans l'ordre la première fois, puis revenir directement à la fiche dont tu as besoin.

## 1. Comprendre ce que fait le projet

Tu as un PC capable de faire tourner un modèle d'IA : Ryzen 7 7700, 48 Go de RAM, Intel Arc B580 de 12 Go. Le projet l'utilise pour remplacer, autant que possible, les abonnements Claude et ChatGPT par une IA qui tourne chez toi. Un cloud facultatif (GLM-5.3 Flash par OpenRouter, 25 € réels par mois au plus) peut compléter le local, seulement si tu l'actives et pour ce que tu choisis d'y envoyer.

Il te donne quatre usages :

| Usage | Où | Fiche |
|---|---|---|
| Discuter, poser n'importe quelle question | Open WebUI, `http://127.0.0.1:3000` | [Discuter](fiches/03-discuter.md) |
| Apprendre le DevOps avec un mentor qui te fait pratiquer | Open WebUI ou l'atelier | [Apprendre](fiches/05-apprendre.md) |
| Mener un projet avec sept rôles spécialisés | Atelier Projets, `http://127.0.0.1:18890` | [Atelier Projets](fiches/04-atelier-projets.md) |
| Obtenir de vrais fichiers : Markdown, PDF, DOCX, YAML, Terraform, schémas | Les deux | [Fichiers et schémas](fiches/06-fichiers-et-schemas.md) |

En local, un seul modèle, Qwen 3.5 9B, sert à tout. Les sept rôles sont sept jeux de consignes pour ce même modèle, pas sept IA chargées en mémoire. Le détail est dans [Rôles et outils](fiches/07-roles-et-outils.md), et le fonctionnement interne dans [Comment ça marche](fiches/11-comment-ca-marche.md).

![Deux interfaces, un même moteur](diagrams/atelier-architecture.svg)

Une limite à garder en tête : un modèle de cette taille aide bien à expliquer, relire, rédiger et structurer. Il se trompe plus souvent qu'un grand modèle cloud sur les tâches longues et complexes. L'atelier est construit autour de cette réalité : petites étapes, sources citées, relecture, et c'est toi qui exécutes et qui valides.

## 2. Installer

Sur Fedora 44, depuis ton compte habituel :

```bash
git clone https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA.git
cd OPENCLAW_LOCAL_FEDORA
./menu.sh --action install            # aperçu, ne modifie rien
./menu.sh --action install --apply
```

Prérequis, détail des étapes et ce que l'installation modifie : [Installer](fiches/01-installer.md).

## 3. Faire le premier essai

L'installation ne dit pas si ta carte graphique travaille vraiment ni à quelle vitesse. Trois commandes le disent :

```bash
./menu.sh --action health
./menu.sh --action check-gpu
./menu.sh --action context-probe --apply
```

Lecture des résultats et quoi faire selon le cas : [Premier essai](fiches/02-premier-essai.md). Tant que cette étape n'est pas faite, rien n'est prouvé sur ta machine.

## 4. Utiliser au quotidien

```bash
./menu.sh --action webui-install --apply   # une seule fois
```

Ensuite, ouvre `http://127.0.0.1:3000` pour discuter et `http://127.0.0.1:18890` pour l'atelier.

- Une question, une notion, un blocage : [Discuter](fiches/03-discuter.md). Le chat peut aussi interroger un projet (`!projets`, `!projet`) et y garder un document (`!garder`, puis `!accepter` avec une phrase de confirmation) : même fiche.
- Un travail avec des documents, un plan et des livrables : [Atelier Projets](fiches/04-atelier-projets.md).
- Progresser en DevOps plutôt que recevoir une réponse toute faite : [Apprendre](fiches/05-apprendre.md).
- Récupérer des fichiers et modifier un schéma dans Draw.io : [Fichiers et schémas](fiches/06-fichiers-et-schemas.md).

Pour jouer, libère la carte graphique puis reprends ensuite :

```bash
./menu.sh --action gaming --apply
./menu.sh --action daily --apply
```

## 5. Régler

La taille du contexte, la longueur des réponses, le modèle, les versions et le budget cloud se règlent dans quelques fichiers de `config/`. Lesquels, pourquoi ces valeurs et comment les changer sans rien casser : [Réglages](fiches/08-reglages.md).

## 6. Utiliser le cloud, si tu le souhaites

Le cloud est désactivé tant que tu ne l'actives pas. Il passe par une passerelle locale qui filtre ce qui part, compte chaque appel et refuse au plafond de 25 € par mois. Dans le chat, tu choisis le modèle « · cloud (GLM) » pour les questions publiques ; dans l'atelier, tu autorises chaque projet un par un, et un projet se met en **pause** plutôt que de basculer en local sans te le dire. Activation, budget, limites du filtre et test de fumée : [Le cloud, facultatif](fiches/12-cloud.md).

## 7. Entretenir

```bash
./menu.sh --action backup
./menu.sh --action upgrade --apply
```

Sauvegarde, restauration, mise à niveau, réparation et désinstallation : [Entretenir](fiches/09-entretenir.md).

## 8. Dépanner

```bash
./menu.sh --action health
./menu.sh --action status
```

Puis cherche ton symptôme dans [Dépanner](fiches/10-depanner.md).

## Les fiches

1. [Installer](fiches/01-installer.md)
2. [Premier essai](fiches/02-premier-essai.md)
3. [Discuter](fiches/03-discuter.md)
4. [Atelier Projets](fiches/04-atelier-projets.md)
5. [Apprendre](fiches/05-apprendre.md)
6. [Fichiers et schémas](fiches/06-fichiers-et-schemas.md)
7. [Rôles et outils](fiches/07-roles-et-outils.md)
8. [Réglages](fiches/08-reglages.md)
9. [Entretenir](fiches/09-entretenir.md)
10. [Dépanner](fiches/10-depanner.md)
11. [Comment ça marche](fiches/11-comment-ca-marche.md)
12. [Le cloud, facultatif](fiches/12-cloud.md)

Une présentation illustrée du projet existe aussi en [PDF](guide-utilisateur.pdf) ([source HTML](guide-utilisateur.html)).
