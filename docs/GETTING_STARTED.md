# Premiers pas

## Repères de progression

| Repère | Valeur |
|---|---|
| **Pour qui** | Toute personne qui découvre le projet, y compris sans expérience préalable de Fedora, OpenClaw ou DevOps. |
| **Position dans le parcours** | 1/14 |
| **Prérequis** | Aucun prérequis technique ; commencer par le README racine puis ce guide. |
| **Objectif** | Comprendre l’état du dépôt, les commandes de base, les modèles, les agents et la différence entre validation logicielle et qualification réelle. |
| **Résultat attendu** | Savoir lancer les contrôles non destructifs et comprendre ce que chaque état prouve réellement. |
| **Critère d’arrêt** | Un échec de `validate` doit être compris et résolu avant d’aller plus loin. |
| **Continuer avec** | [`INSTALLATION.md`](INSTALLATION.md) |
| **Source de vérité** | Les contrats `config/*.yaml`; ce guide les explique sans les remplacer. |

Ce guide suppose que l'installation Fedora est terminée ou que le dépôt est disponible pour des dry-runs. Il donne un parcours court pour comprendre l'état du produit sans lancer immédiatement une qualification matérielle longue.

## 1. Vérifier le dépôt

Depuis la racine du dépôt :

```bash
./menu.sh --action validate
```

Cette commande valide les contrats L0–L8 et le cycle de vie. Un échec doit être traité avant de poursuivre.

## 2. Vérifier l'état de la machine et du produit

```bash
./menu.sh --action status
```

`status` combine les contrats, le cycle de vie et un audit non bloquant de la plateforme.

Si le produit est déjà installé :

```bash
./menu.sh --action health
```

Le health-check est la commande de référence pour savoir si OpenClaw, Ollama, les modèles et les workspaces attendus sont présents et cohérents.

## 3. Connaître les trois modèles nominaux

La flotte opérationnelle contient exactement trois alias :

| Alias | Usage principal |
|---|---|
| `qwen-max` | orchestration, recherche, sécurité, release |
| `gemma-deep` | architecture, documentation, revue indépendante |
| `devstral-devops` | DevOps, code, réparation et tool-calling |

Les identités runtime exactes sont définies uniquement dans `config/model_catalog.yaml`.

Le challenger Granite appartient à L6 et reste hors routage tant qu'aucune décision humaine post-qualification n'a modifié les contrats.

## 4. Connaître les huit agents

Les rôles sont :

- `chef-operations` ;
- `expert-recherche` ;
- `architecte-solutions` ;
- `ingenieur-devops` ;
- `ingenieur-securite` ;
- `ingenieur-release-forges` ;
- `redacteur-technique` ;
- `auditeur-qualite`.

Leurs missions sont décrites dans [`MULTI_AGENT_CORE.md`](MULTI_AGENT_CORE.md) et leurs contrats détaillés sont versionnés sous `agents/`.

## 5. Vérifier les workspaces

Pour déployer ou remettre en cohérence les huit workspaces gérés :

```bash
./menu.sh --action agents
```

Le déploiement refuse d'écraser silencieusement un workspace non géré.

## 6. Tester le moteur projet sans matériel

```bash
./menu.sh --action project-selftest
```

Ce test exerce un cycle projet synthétique. Il vérifie le moteur logiciel, pas la B580 ni OpenClaw E2E.

## 7. Prévisualiser les gates lourds

Avant tout E2E réel :

```bash
./menu.sh --action e2e-dry-run --backend ollama-vulkan
```

Avant HARD-40M :

```bash
./menu.sh --action qualification-dry-run
```

Avant L8 :

```bash
./menu.sh --action release-readiness-dry-run
```

Ces dry-runs doivent rester sans revendication matérielle.

## 8. Commandes opérateur essentielles

```bash
./menu.sh --action health
./menu.sh --action backup
./menu.sh --action repair
./menu.sh --action repair --apply
```

Pour le Gateway :

```bash
systemctl --user status openclaw-gateway.service
journalctl --user -u openclaw-gateway.service -n 100 --no-pager
openclaw gateway status
```

Pour Ollama :

```bash
ollama --version
ollama list
systemctl status ollama.service
```

## 9. Où aller ensuite ?

Le parcours principal continue avec [`INSTALLATION.md`](INSTALLATION.md). Les autres guides seront introduits ensuite, dans un ordre qui augmente progressivement la profondeur technique.

## Règle de lecture des états

Ne pas confondre :

```text
CONTRATS PASS
    ≠ INSTALLATION PASS
    ≠ E2E OPENCLAW PASS
    ≠ B580/VULKAN QUALIFIÉE
    ≠ HARD-40M PASS
    ≠ L8 READY
    ≠ V1 APPROUVÉE
```

Chaque niveau possède ses propres preuves et ses propres gates.
