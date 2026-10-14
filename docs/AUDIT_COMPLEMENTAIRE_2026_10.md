# Audit complémentaire après OpenClaw 2026.10.2

Cet audit distingue les **défauts prouvés dans le code** des **risques à qualifier sur Fedora**. Les tests CI verts du dépôt n'attestent pas que les installateurs distants, la migration WebUI, la B580 ou une restauration ont été éprouvés de bout en bout.

## Défaut corrigé : dépendances de production manquantes

- `src/clawfedora/chat_document_preview.py` et `src/clawfedora/local_vision.py` importent `pypdf` pour les PDF.
- Avant ce correctif, `pypdf==6.19.0` était seulement dans `[project.optional-dependencies].dev` ; `scripts/linux/00_bootstrap.sh` installe `pip install -e .` hors option de développement.
- La suite pytest installait `.[dev]` ; elle ne vérifiait pas les imports d'une installation réelle de production.
- `pypdf` est maintenant une dépendance de production explicite, ainsi que `Pillow` pour l'analyse d'images. La CI `native-openclaw` installe `pip install -e .`, puis exécute `pip check` et une lecture réelle de PDF généré et d'image sans dépendances dev.

## Intégrité des installateurs — corrigée dans le code, non qualifiée sur Fedora

Les anciennes commandes exécutant directement `https://ollama.com/install.sh` ou `https://openclaw.ai/install-cli.sh` ont été **remplacées** en PR #106 par le téléchargement d'archives de versions exactes, avec empreintes figées et vérification avant installation. La PR #108 a corrigé une deuxième anomalie prouvée : le mode `npm install --prefix` local ne créait pas l'exécutable à l'emplacement attendu ; l'installation utilise désormais `--global --prefix` dans le répertoire de l'utilisateur. Le smoke npm utilise une archive synthétique sans réseau et confirme la disposition attendue.

**Les limites demeurent :** une archive vérifiée ne suffit pas à valider ses dépendances npm transitives ; `00_bootstrap.sh` fait encore `pip install --upgrade pip setuptools wheel` sans verrouillage exact, et le projet n'a pas exécuté l'installation vierge/upgrade réelle Fedora, les contrôles de service Ollama ni les essais B580. Ces opérations feront partie de la réception finale, sans annoncer un succès avant la mesure.

## Arrêt de l'interface pendant la maintenance — correction du cycle de vie

Le démarrage d'Open WebUI active quatre services (`clawfedora-webui`, `clawfedora-webui-bridge`, `clawfedora-speech` et `clawfedora-dashboard`), mais la branche `stop` oubliait `clawfedora-dashboard`. Ce service pouvait donc rester accessible pendant une sauvegarde dite hors ligne. Le script arrête maintenant les quatre services, et un test avec `systemctl` simulé vérifie la symétrie sans toucher aux services de l'hôte.

La commande `webui-stop` n'arrête toujours **pas** le Gateway OpenClaw ni Ollama ; la réception réelle devra contrôler l'absence d'opération concurrente pendant la sauvegarde.

## Qualifications restant indispensables (non prouvées par GitHub)

1. **Fedora réel / B580 :** GPU Intel Arc, 32K de contexte, latence, pression VRAM, cinq cycles de veille/reprise et fonctionnement sans réseau.
2. **Open WebUI :** canary isolé 0.12 avec copie SQLite et test navigateur de la préservation des conversations et des plugins ; production toujours épinglée en 0.11.4.
3. **Vision :** requêtes PNG/JPEG/WebP et PDF scanné via navigateur, qualité visuelle, refus de cloud, état de verrouillage et performance.
4. **Restaurations :** restauration d'une archive dans une destination vide *distincte*, contrôle des permissions et de la récupération des données ; ne pas considérer la seule création d'une archive comme preuve.
5. **Sécurité et qualité :** tests d'intégration réels sur le Gateway avec la nouvelle version, gestion des secrets et suivi de consommation cloud dans la limite prévue.

## Critère de fin

Le projet sera **prêt à installer sur Fedora** lorsque la chaîne de téléchargements sera vérifiée et que la CI restera verte. Il ne sera **qualifié en production** qu'après l'exécution documentée des essais réels. Aucune affirmation « plus aucune amélioration » n'est justifiée en l'absence de ces preuves.
