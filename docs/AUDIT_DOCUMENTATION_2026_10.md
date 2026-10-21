# Audit documentaire transversal — 20 octobre 2026

[← Documentation](README.md) · [État logiciel](../STATUS.md) · [Références](reference/README.md) · [Validation](validation/README.md)

## Objet et méthode

Cette revue part de **43 fichiers Markdown préexistants dans `docs/`** au commit
`3766d7b8d8e6c00d5f15494ab8685894274173e6` (fusion de la PR #148).
Le présent rapport est une **44e page** ajoutée par cette révision.
Les fichiers `README.md`, `STATUS.md`, `CHANGELOG.md` et `CONTRIBUTING.md`
ont également été relus et ajustés lorsque pertinent.

Contrôles : inventorier toutes les pages, examiner leur organisation et leurs
liens Markdown internes, repérer versions et références historiques, confronter
les guides fonctionnels aux politiques YAML, au menu CLI et aux modules Python,
puis mettre à jour les passages qui diffèrent. La CI couvre déjà les liens
internes et les versions principales ; cette PR ajoute des tests sur les
**actions réellement disponibles dans `menu.sh`** et l'accès à l'évaluation
pédagogique, ainsi que sur la typographie du guide d'installation.

**Périmètre vérifié, pas à surdéclarer :** contrôles documentaires statiques et
revue des contrats du dépôt. Pas de navigation ou test des **URL externes**,
pas d'installation sur Fedora, pas de commande Terraform/AWS exécutée, pas de
modèle Qwen/DeepSeek sollicité et pas de facture OpenRouter constatée.
Les exemples restent des procédures à vérifier sur la machine réelle.

## Références de vérité et cohérence des versions

| Domaine | Référence dans le dépôt | Valeur contractuelle |
| --- | --- | --- |
| OS cible | `config/platform.yaml`, `config/runtime_versions.yaml` | Fedora 45 / GNOME 51 |
| OpenClaw et Parallel | `config/runtime_versions.yaml` | 2026.10.4, mises à jour non automatiques |
| Ollama | `config/runtime_versions.yaml` | 0.40.6 |
| Open WebUI | `config/webui_policy.yaml` | v0.12.3-slim |
| Modèle local | `config/model_catalog.yaml` | `qwen3.5:9b-q4_K_M` |
| Cloud facultatif | `config/core/cloud_policy.yaml` | `deepseek/deepseek-v4.1-flash-1017`, accord et filtre |
| Budget | `config/core/cloud_policy.yaml` | 25 €/mois, réserve prudente |
| WebUI et historique | `config/webui_policy.yaml` + `src/clawfedora/webui_bridge.py` | local 32 000 octets ; route cloud bornée séparément |
| Profil mentor | `src/clawfedora/mentor.py` | sept champs facultatifs, accord humain |
| Qualité pédagogique | `src/clawfedora/pedagogy_eval.py` + `config/evals/pedagogy_conversations.yaml` | quatre dimensions /5, quatre dialogues de trois tours, sans modèle appelé |
| Ligne de commande | `menu.sh` | seules les actions de son `case "$ACTION"` sont publiques |
| Dépendances de build | `config/python-build-constraints.txt` et `config/python-build-hashes.txt` | setuptools/wheel verrouillés ; wheel-only et `--no-build-isolation` |

## Corrections effectuées

- **État :** remplacer l'ancienne CI #143 et le CodeQL daté par une référence
  explicite et datée à la PR #148 et au commit fusionné ; ne pas présenter le
  succès CI comme une réception Fedora.
- **Installation :** retirer les deux séquences `\\n` affichées littéralement
  au début de la procédure Fedora.
- **Intégrité :** corriger la description PEP 517 pour refléter les contraintes
  et hashes du build actuel et les limites restantes (RPM, extras de dev).
- **Pédagogie :** clarifier les **sept champs** de la fiche mentor (cinq notes
  de suivi + deux préférences), l'approbation humaine et l'absence de mémoire
  automatique ou de certification de compétences.
- **Réception :** ajouter un chemin concret pour vérifier les quatre dialogues
  pédagogiques à trois tours, tout en distinguant revue humaine et test automatisé.
- **Navigation :** raccorder la grille /20 depuis le sommaire, le guide, les
  fiches discussion/cloud/réglages, les références et les diagnostics.
- **Contributions :** documenter la règle de mise à jour **dans la même PR**
  que les modifications du code ; ajout de contrôles de non-régression.

## Inventaire des 43 documents contrôlés

« Examiné » signifie que la navigation, les versions repérables et les références
principales ont été contrôlées et qu'aucun changement pertinent n'était requis ;
cela ne signifie pas que chaque exemple a été exécuté. Les six plans historiques
portent déjà la mention **« Archive de conception 2026 »** : leurs versions
anciennes ne sont pas remplacées par les nouvelles.

| Chemin | Décision |
| --- | --- |
| `docs/ARCHITECTURE_HYBRIDE.md` | Examiné, sans correction requise dans le périmètre |
| `docs/ASSEMBLAGE_DOCUMENTS.md` | Examiné, sans correction requise dans le périmètre |
| `docs/AUDIT_COMPLEMENTAIRE_2026_10.md` | Archive conservée |
| `docs/DECISION_MODELE.md` | Examiné, sans correction requise dans le périmètre |
| `docs/EVALUATION_AGENTS.md` | Examiné, sans correction requise dans le périmètre |
| `docs/EVALUATION_PEDAGOGIE.md` | Actualisé |
| `docs/EXEMPLE_PARCOURS_DEVOPS.md` | Examiné, sans correction requise dans le périmètre |
| `docs/GUIDE.md` | Actualisé |
| `docs/INSTALLATION_INTEGRITE.md` | Actualisé |
| `docs/INSTALLATION_SIMPLE_FEDORA45.md` | Actualisé |
| `docs/LABORATOIRE_DEVOPS.md` | Examiné, sans correction requise dans le périmètre |
| `docs/LIVE_USB_FEDORA45_PREQUALIFICATION.md` | Examiné, sans correction requise dans le périmètre |
| `docs/MIGRATION_OPENCLAW_2026_10_2.md` | Archive conservée |
| `docs/PASSERELLE_CLOUD.md` | Examiné, sans correction requise dans le périmètre |
| `docs/PLAN_INTEGRATION_WEBUI.md` | Archive conservée |
| `docs/PLAN_MIGRATION_HYBRIDE.md` | Archive conservée |
| `docs/PLAN_QUALITE_2026.md` | Archive conservée |
| `docs/PREUVES_CI_GITHUB_GITLAB.md` | Examiné, sans correction requise dans le périmètre |
| `docs/PROGRAMME_AMELIORATION_2026.md` | Archive conservée |
| `docs/PROMPTS.md` | Actualisé |
| `docs/PYTHON_RUNTIME_LOCK.md` | Examiné, sans correction requise dans le périmètre |
| `docs/QUALIFICATION_FINALE_FEDORA.md` | Actualisé |
| `docs/README.md` | Actualisé |
| `docs/RECHERCHE_LOCALE_SOURCES.md` | Actualisé |
| `docs/SMOKE_TEST_WEBUI.md` | Actualisé |
| `docs/STREAMING_SSE_PREPARATION.md` | Examiné, sans correction requise dans le périmètre |
| `docs/VISION_LOCALE_CANARY.md` | Examiné, sans correction requise dans le périmètre |
| `docs/WEB_ACCESS_PRIVATE_MODE.md` | Examiné, sans correction requise dans le périmètre |
| `docs/archives/2026/README.md` | Examiné, sans correction requise dans le périmètre |
| `docs/fiches/01-installer.md` | Examiné, sans correction requise dans le périmètre |
| `docs/fiches/02-premier-essai.md` | Examiné, sans correction requise dans le périmètre |
| `docs/fiches/03-discuter.md` | Actualisé |
| `docs/fiches/04-atelier-projets.md` | Examiné, sans correction requise dans le périmètre |
| `docs/fiches/05-apprendre.md` | Actualisé |
| `docs/fiches/06-fichiers-et-schemas.md` | Examiné, sans correction requise dans le périmètre |
| `docs/fiches/07-roles-et-outils.md` | Examiné, sans correction requise dans le périmètre |
| `docs/fiches/08-reglages.md` | Actualisé |
| `docs/fiches/09-entretenir.md` | Examiné, sans correction requise dans le périmètre |
| `docs/fiches/10-depanner.md` | Examiné, sans correction requise dans le périmètre |
| `docs/fiches/11-comment-ca-marche.md` | Examiné, sans correction requise dans le périmètre |
| `docs/fiches/12-cloud.md` | Actualisé |
| `docs/reference/README.md` | Actualisé |
| `docs/validation/README.md` | Actualisé |

## Limites connues et règles de maintenance

1. Le dépôt décrit l'installation prévue, **pas** une installation déjà
   qualifiée sur la B580 sous Fedora 45. La réception réelle reste à faire.
2. OpenRouter/DeepSeek V4.1 Flash 1017 doit toujours subir un appel volontaire
   de qualification : disponibilité compatible avec `data_collection: deny`,
   effort de raisonnement, prix, facturation et confidentialité.
3. L'objectif de qualité 20/20 est une **grille humaine d'acceptation** ;
   le code n'a pas atteint ni démontré cette note par ses seuls tests.
4. Les plans historiques restent accessibles à leur ancienne URL pour ne pas
   rompre les liens publics. L'état courant est défini par `STATUS.md` et
   `config/`, jamais par une ancienne PR.
5. À chaque modification contractuelle : synchroniser les guides touchés,
   mettre à jour `CHANGELOG.md`, relancer `clawfedora validate` puis la CI,
   et inspecter les liens et les preuves déclarées. Les tests ne prouvent
   pas la validité d'une page Web externe.
