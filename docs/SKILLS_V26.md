# Skills V26 — intégration isolée pour les sept agents ClawFedora

## Objet

Cette bibliothèque regroupe **11 Skills autonomes** dérivés des huit modules canoniques des prompts V26. Elle conserve les comportements essentiels sans réinjecter les quatre prompts de lancement à chaque tour.

La version enrichie avec toutes les références et gabarits Draw.io/SVG/PNG reste disponible dans le pack V26 original fourni séparément par l'utilisateur. Les Skills de ce dépôt sont **autonomes et allégés**, sans dépendance à une archive externe lors du chargement.

## Architecture existante conservée

- ClawFedora : interface et workflow des projets.
- OpenClaw : agents, découverte des Skills et politique d'outils.
- Ollama : inférence locale.
- GitHub : source technique / portfolio ; Notion : progression pédagogique.
- Aucun changement du routage cloud, des versions verrouillées, des permissions d'exécution ou de la configuration Open WebUI/ClawFedora.
- Aucun remplacement des fichiers AGENTS.md ou de la charte partagée.

## Installation à blanc, par agent

Les espaces de travail sont créés par la procédure native `agents deploy`. Exécuter ensuite, avec la **racine runtime réellement configurée** (contenant le dossier workspaces/) :

```bash
python3 scripts/linux/20_deploy_v26_skills.py --runtime-root "/chemin/runtime/ClawFedora"
```

Examiner les 28 copies prévues. Si chaque chemin correspond au bon agent et si le risque de collision est nul, l'utilisateur peut choisir d'appliquer :

```bash
python3 scripts/linux/20_deploy_v26_skills.py --runtime-root "/chemin/runtime/ClawFedora" --apply
```

Le script n'écrase aucun dossier existant, refuse les workspaces non gérés, les liens symboliques et les marqueurs incohérents. Prévoir une nouvelle session et vérifier les Skills réellement chargés avec `openclaw skills list`.

Les copies sont rangées dans `<runtime>/workspaces/<id-agent>/skills/<nom>/SKILL.md`. Cela limite la découverte des Skills aux rôles concernés, **sans modifier l'allowlist actuelle ni élargir les droits système**. Un appel d'outil reste toujours soumis à la politique OpenClaw/ClawFedora.

La réinstallation n'est pas une mise à jour automatique : elle s'arrête si un Skill est déjà en place, pour éviter toute écriture non vérifiée. La maintenance et les mises à jour futures devront disposer d'un plan diff/backup/revue séparé.

## Contrôles

```bash
pytest -q tests/test_v26_skills.py
openclaw skills list
```

Vérifier en session réelle les déclenchements mentor, architecture, IaC, preuve, README GitHub, cours Notion, schéma Draw.io et audit. Comparer le comportement avec l'absence d'exécution et d'écriture autonome. Une CI verte ne certifie ni un chargement OpenClaw, ni un rendu Fedora/Notion/Draw.io.

## Attestations

- Bibliothèque versionnée : oui, dans cette PR.
- Tests automatiques : à lire dans les résultats CI de la PR.
- Installation sur le poste Fedora : **non réalisée**.
- Connexion d'agent à un Skill et validation comportementale : **non vérifiée en conditions réelles**.
- Rendu graphique natif, synchronisation GitHub/Notion : **non vérifiés**.
