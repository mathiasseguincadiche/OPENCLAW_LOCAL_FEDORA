# Security Policy

## Principes obligatoires

- SELinux reste **Enforcing**.
- Les providers modèles locaux écoutent uniquement sur loopback par défaut.
- Aucun fallback cloud implicite.
- Une escalade cloud exige une action explicite et un budget/gate humain quand elle sera réintroduite.
- Les secrets et preuves de runtime ne sont jamais committés.
- Aucun script d'installation ne peut utiliser `--nogpgcheck`, désactiver SELinux ou ouvrir le firewall globalement.
- Les promotions kernel/backend sont manuelles après preuves.

## Signalement

Ne publiez pas de secret, token, dump de mémoire modèle ou preuve contenant des données privées dans une issue publique. Utilisez les mécanismes privés de sécurité GitHub lorsqu'ils sont disponibles.

## Périmètre actuel

La version 0.1.x est un socle de migration. Les fonctionnalités encore absentes ne doivent pas être présentées comme sécurisées ou qualifiées avant leur gate correspondant.
