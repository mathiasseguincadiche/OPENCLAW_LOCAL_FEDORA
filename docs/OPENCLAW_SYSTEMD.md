# OpenClaw sous Fedora : cycle de vie systemd

## Repères de progression

| Repère | Valeur |
|---|---|
| **Pour qui** | Toute personne qui suit le parcours et veut comprendre comment OpenClaw vit réellement comme service Linux. |
| **Position dans le parcours** | 8/14 |
| **Prérequis** | Avoir lu [`PROJECT_ENGINE.md`](PROJECT_ENGINE.md) et connaître le rôle du Gateway. |
| **Objectif** | Comprendre `systemd --user`, le cycle de vie du Gateway, les logs et les choix explicites comme le lingering. |
| **Résultat attendu** | Savoir relier les commandes OpenClaw aux primitives systemd et diagnostiquer un service utilisateur. |
| **Critère d’arrêt** | Si le Gateway ou la distinction service utilisateur/service système reste floue, revenir aux sections pratiques d’exploitation. |
| **Continuer avec** | [`LIFECYCLE.md`](LIFECYCLE.md) |
| **Source de vérité** | Les contrats OpenClaw du projet, les scripts Linux gérés et la documentation amont OpenClaw citée ici. |

OpenClaw supporte nativement Linux et installe par défaut un service systemd utilisateur pour le Gateway.

Documentation amont :

- https://docs.openclaw.ai/platforms/linux
- https://docs.openclaw.ai/gateway
- https://docs.openclaw.ai/install/node

## Politique du projet

1. Utiliser le mécanisme `openclaw gateway install` / onboarding lorsqu'il suffit.
2. Ne pas maintenir une unité systemd manuelle concurrente pour le même profil/port.
3. Le Gateway reste loopback-only par défaut.
4. Le code de sortie de configuration invalide `78` doit empêcher une boucle de restart.
5. L'activation de lingering est un choix explicite de l'opérateur, pas un effet caché du bootstrap.

## Node

Au 2026-09-03, OpenClaw documente comme supportés :

- Node 22.22.3+ ;
- Node 24.15+ ;
- Node 25.9+ ;
- Node 26 recommandé.

La première qualification Fedora verrouille une version OpenClaw exacte. Les upgrades runtime interviennent ensuite, une variable à la fois, avec requalification obligatoire.

## Commandes opérateur futures

Après intégration OpenClaw :

```bash
openclaw gateway install
systemctl --user status openclaw-gateway.service
journalctl --user -u openclaw-gateway.service
openclaw gateway status
```

Si la machine doit faire tourner le Gateway après logout :

```bash
sudo loginctl enable-linger "$USER"
```

Cette opération doit rester explicitement demandée.
