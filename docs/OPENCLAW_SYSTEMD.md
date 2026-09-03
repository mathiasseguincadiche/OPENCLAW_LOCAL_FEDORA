# OpenClaw sous Fedora : cycle de vie systemd

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
