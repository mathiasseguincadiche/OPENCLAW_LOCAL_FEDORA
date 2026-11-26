# Campagne de qualification éditoriale Premium — Atelier Atlas

## Conditions d'entrée

Après installation et précontrôles Fedora 45, utiliser un projet fictif
**Atelier Atlas** (service de suivi de demandes internes). Ne pas utiliser
OpsDesk ni les wikis et dépôts de production comme banc d'essai.
Créer un espace Notion privé dédié et un dépôt GitHub de test, avec les
permissions minimales. Les actions distantes exigent les approbations
opérateur existantes. Aucun modèle cloud, aucun secret réel dans les
documents, aucun changement de progression d'un projet utilisateur.

Sources de départ : [démonstrations Atlas](../editorial-demo/README.md).
Brief : service fictif de suivi des demandes, stockage relationnel,
déploiement automatisé, supervision, sauvegarde et restauration à
expliquer. Les versions et choix sont des hypothèses à expliciter ;
aucun test réel du service ne doit être inventé. Produire une
présentation, une architecture détaillée, un parcours de préparation
et un exercice de diagnostic. Utiliser des données synthétiques.
Le public découvre le projet ; le wiki privé approfondit l'apprentissage.

## Scénarios et conditions de réussite

| Cas | Action et résultat attendu | Preuve à examiner |
| --- | --- | --- |
| roles | Observer les sept rôles, routage local Qwen/Ornith, outils autorisés ; tester un refus | Sessions et inventaire local |
| markdown | Faire produire README et fiche, avec mécanisme, exemple, exercice, contrôle ; demander une correction réelle | Sources, diff et reçu de boucle |
| diagrams | Deux vues distinctes, sources Draw.io et SVG concordants ; corriger un chevauchement | Paires et rapport géométrique |
| identity | Deux directions distinctes, sources JSON conservées ; vérifier régénération | JSON, SVG et reçu |
| notion-spec | Revue de la structure, installation, navigation et parcours préservés | JSON, HTML local et reçu |
| notion-native | Créer un wiki privé, images, relation, galerie et rollup ; cocher une activité fictive | Reçu API et observation de la progression |
| navigation | Original et copies liées ; modifier manuellement le titre du bloc original sur le wiki de test | Observation réelle avant/après |
| enrichment | Ajouter une section après approbation, conserver les blocs et le suivi | Aperçu, reçu, comparaison de la page |
| coherence | Deux références alignées, puis divergence et exposition d'une valeur privée fictive | Rapports de revue sans valeur privée |
| github-native | Créer une PR documentaire dans le dépôt de test ; vérifier le diff et la CI, ne fusionner que volontairement | URL/commit et preuve de CI |
| visual | Utiliser la recette Premium sur README GitHub et page Notion réelle ; six vues de chaque et revue humaine | Deux reçus visuels et captures privées |
| negative | Introduire source altérée, paire divergente, doublon, rejeu et allégation de preuve inexistante ; vérifier les refus | Rapports d'échec, absence de publication |
| learning | Exécuter un exercice de diagnostic séparément de l'exemple ; expliquer le résultat et les aides reçues | Journal de pratique et résultat observé |

Pour la revue réelle, suivre les procédures existantes :
[cycle](../EDITORIAL_CYCLE.md), [studio](../NOTION_STUDIO.md),
[parcours](../NOTION_CURRICULUM.md), [enrichissement](../NOTION_ENRICH.md),
[cohérence](../EDITORIAL_COHERENCE.md) et
[réception visuelle](VISUAL_RECEPTION_NATIVE.md).
Ne pas attribuer PASS à une simulation ou à un test unitaire.
Examiner les preuves, le contenu et les limites de chaque cas ;
un résultat de modèle favorable n'est pas une validation humaine.

## Journal de réception privé

Depuis le dépôt installé (environnement Python activé) :

~~~bash
python -m clawfedora.editorial_acceptance plan
install -d -m 700 "$HOME/.local/state/clawfedora-atlas-reception"
RECEPTION="$HOME/.local/state/clawfedora-atlas-reception"
REVISION="$(git rev-parse HEAD)"
python -m clawfedora.editorial_acceptance template \
  --commit "$REVISION" --output "$RECEPTION/observations.json"
~~~

Le formulaire initial ne contient aucun PASS. Après chaque essai réel,
copier au plus quatre preuves privées par cas dans le dossier (fichiers
réguliers chmod 600, 20 Mo maximum chacun, noms simples, distincts).
Pour une série de preuves, utiliser un rapport de synthèse référant
aux fichiers conservés et les inspecter manuellement. Calculer leurs
empreintes avec `sha256sum`. Inscrire les références dans
`evidence` sous la forme `{"file":"preuve.json","sha256":"..."}`.
États : NOT_RUN, PASS, FAIL, BLOCKED. Un PASS ou FAIL exige une
preuve et l'attestation opérateur d'exécution native. Ne pas déclarer
cette attestation avant les essais réels.

~~~bash
python -m clawfedora.editorial_acceptance review \
  --commit "$REVISION" --form "$RECEPTION/observations.json" \
  --output "$RECEPTION/reception.json"
~~~

Codes : 0 dossier déclaré complet ; 1 incomplet ou échec déclaré ;
2 entrée refusée. Un reçu n'est pas une certification : le moteur
vérifie la structure, le commit déclaré et les empreintes des fichiers,
pas l'authenticité ni le sens des preuves. Ne pas publier le dossier,
ne pas réutiliser une preuve pour plusieurs cas et ne pas confondre
ce journal avec la recette globale du poste. Toute nouvelle tentative
utilise un nouveau reçu ; les fichiers existants ne sont pas écrasés.

**Statut initial : NOT_RUN.** L'installation, la qualification des modèles,
les actions distantes et le rendu réel restent à exécuter par l'opérateur.
