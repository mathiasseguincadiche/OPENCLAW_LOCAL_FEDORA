# Audit complémentaire après OpenClaw 2026.10.2

Cet audit distingue les **défauts prouvés dans le code** des **risques à qualifier sur Fedora**. Les tests CI verts du dépôt n'attestent pas que les installateurs distants, la migration WebUI, la B580 ou une restauration ont été éprouvés de bout en bout.

## Défaut corrigé : dépendances de production manquantes

- `src/clawfedora/chat_document_preview.py` et `src/clawfedora/local_vision.py` importent `pypdf` pour les PDF.
- Avant ce correctif, `pypdf==6.19.0` était seulement dans `[project.optional-dependencies].dev` ; `scripts/linux/00_bootstrap.sh` installe `pip install -e .` hors option de développement.
- La suite pytest installait `.[dev]` ; elle ne vérifiait pas les imports d'une installation réelle de production.
- `pypdf` est maintenant une dépendance de production explicite, ainsi que `Pillow` pour l'analyse d'images. La CI `native-openclaw` installe `pip install -e .`, puis exécute `pip check` et une lecture réelle de PDF généré et d'image sans dépendances dev.

## Amélioration prioritaire restante : intégrité des installateurs

**Constat confirmé :** `scripts/linux/06_install.sh` télécharge `https://ollama.com/install.sh` et `https://openclaw.ai/install-cli.sh`, puis exécute directement les scripts distants téléchargés. Le contrôle de version **après** installation vérifie la version résultante, mais ne vérifie pas l'empreinte SHA-256 préalablement approuvée des scripts. `scripts/linux/00_bootstrap.sh` utilise aussi `pip install --upgrade pip setuptools wheel` sans version exacte.

**Travail proposé avant la prochaine installation réelle :** remplacer les installateurs exécutés à distance par un flux d'artefacts audités avec URLs et empreintes figées dans un manifeste de release, vérifier l'intégrité *avant exécution*, exiger des sources officielles et refuser si le manifeste est absent ou incohérent. Une empreinte obtenue dynamiquement au même endroit que l'artefact n'établit pas une vérification indépendante. Ne pas affaiblir SELinux ni déplacer les secrets.

**Statut : à réaliser séparément**, avec essais d'installation vierge et de migration. Il n'est pas prudent de fabriquer une empreinte ou de déclarer les téléchargements déjà vérifiés.

## Qualifications restant indispensables (non prouvées par GitHub)

1. **Fedora réel / B580 :** GPU Intel Arc, 32K de contexte, latence, pression VRAM, cinq cycles de veille/reprise et fonctionnement sans réseau.
2. **Open WebUI :** canary isolé 0.12 avec copie SQLite et test navigateur de la préservation des conversations et des plugins ; production toujours épinglée en 0.11.4.
3. **Vision :** requêtes PNG/JPEG/WebP et PDF scanné via navigateur, qualité visuelle, refus de cloud, état de verrouillage et performance.
4. **Restaurations :** restauration d'une archive dans une destination vide *distincte*, contrôle des permissions et de la récupération des données ; ne pas considérer la seule création d'une archive comme preuve.
5. **Sécurité et qualité :** tests d'intégration réels sur le Gateway avec la nouvelle version, gestion des secrets et suivi de consommation cloud dans la limite prévue.

## Critère de fin

Le projet sera **prêt à installer sur Fedora** lorsque la chaîne de téléchargements sera vérifiée et que la CI restera verte. Il ne sera **qualifié en production** qu'après l'exécution documentée des essais réels. Aucune affirmation « plus aucune amélioration » n'est justifiée en l'absence de ces preuves.
