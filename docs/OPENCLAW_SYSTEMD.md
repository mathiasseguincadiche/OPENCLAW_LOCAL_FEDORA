# OpenClaw sous Fedora : cycle de vie systemd

## Repères de lecture

| Repère | Valeur |
|---|---|
| **Public cible** | Opérateurs Fedora et mainteneurs du Gateway OpenClaw. |
| **Niveau** | Intermédiaire |
| **Prérequis** | OpenClaw installé et session `systemd --user` fonctionnelle. |
| **Objectif** | Comprendre le mécanisme de service utilisateur retenu pour le Gateway et les règles qui évitent les unités concurrentes ou les boucles de restart. |
| **Résultat attendu** | Savoir installer, observer et diagnostiquer le Gateway avec les primitives OpenClaw et systemd supportées. |
| **Critère d’arrêt** | Si `systemd --user` ne fonctionne pas ou si la configuration sort avec le code `78`, diagnostiquer avant tout restart répété via [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md). |
| **À lire ensuite** | [`OPERATIONS.md`](OPERATIONS.md) pour le runbook quotidien et [`UPGRADE.md`](UPGRADE.md) avant un changement de version OpenClaw. |
| **Source de vérité** | `config/core/openclaw_policy.yaml`, `config/runtime_versions.yaml` et le comportement du CLI OpenClaw vivant. |

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
