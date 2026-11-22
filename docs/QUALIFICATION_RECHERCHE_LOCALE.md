# Qualification locale de la recherche GitHub / Notion

## Finalité et périmètre

Cette recette répond à une question pratique : **les passages retournés par
ClawFedora correspondent-ils aux fichiers attendus, à la dernière révision
GitHub approuvée, et aux documents Notion du même projet local ?**

Elle complète le [moteur de recherche locale](RECHERCHE_LOCALE_SOURCES.md)
et réutilise strictement \`clawfedora.project_retrieval.retrieve\`.
Ce n'est pas un autre moteur de recherche et elle ne modifie **ni** les
snapshots GitHub **ni** l'index SQLite FTS5 **ni** les pages Notion.

### Prérequis sur Fedora

1. Installer la version de ClawFedora contenant cette commande dans le
   même environnement Python que l'atelier. Ne pas faire d'installation
   \`pip\` globale sur le système Fedora ; utiliser l'environnement isolé
   ou le processus d'installation standard du projet.
2. Avoir déjà importé GitHub et, si nécessaire, Notion dans le **même**
   projet ClawFedora, avec la politique locale applicable.
3. Pour tester la dernière version du code, avoir enregistré un
   snapshot approuvé par \`clawfedora-github-refresh\`. La commande
   de recette **ne télécharge aucune mise à jour**.
4. S'assurer que \`clawfedora-source-search\` fournit des résultats
   et que l'index FTS5 a été construit après l'import initial.
5. Copier l'[exemple JSON](exemples/recette-recherche-opsdesk.example.json)
   dans un dossier local temporaire et remplacer les questions et
   attentes par les **vraies sources observées**. L'exemple n'est ni
   un résultat de validation ni un contrat de contenu d'OpsDesk.

### Exécution

~~~bash
# Inspecter d'abord les chemins exacts dans la sortie locale.
clawfedora-source-search --project-id opsdesk \
  --query "Terraform Ansible configuration déploiement"

# Exécuter la qualification sur les questions adaptées à tes sources.
# Aucun appel à GitHub, Notion, OpenRouter ou aux VM.
clawfedora-retrieval-acceptance \
  --project-id opsdesk --cases /chemin/vers/recette-opsdesk.json
~~~

Valeur de retour : \`0\` pour \`PASS\` ou \`PASS_WITH_LIMITATIONS\`,
\`1\` lorsqu'au moins une attente échoue, \`2\` si la configuration ou
l'intégrité du projet empêchent la qualification.

Le rapport JSON est envoyé sur la sortie standard, **sans texte brut des
extraits**. Il contient les chemins documentaires, les versions et les
empreintes de preuve ; ces métadonnées peuvent elles-mêmes contenir des
identifiants privés, notamment des identifiants de pages Notion. **Ne pas
publier le JSON tel quel sur GitHub.** Expurger les chemins et identifiants
si le rapport doit devenir une capture publique du portfolio.

## Contrôles inclus

| Contrôle | Portée |
| --- | --- |
| Couverture des sources attendues | Chaque fragment de chemin attendu apparaît dans au moins un résultat |
| Absence de sources interdites | Aucun chemin exclu par le scénario ne figure dans les résultats |
| Diversité documentaire | Nombre minimal de fichiers différents dans les quatre résultats |
| Fraîcheur GitHub | Le SHA des extraits correspond à la dernière version approuvée et à ses fichiers |
| Intégrité des citations | SHA du fichier, empreinte de l'extrait, page, ligne et décalage dans la représentation textuelle |
| Stabilité | Deux exécutions consécutives donnent les mêmes références et empreintes |
| Budget de contexte | Quatre extraits au plus, 4 000 caractères maximum |
| Recherche négative | Une question volontairement obsolète ne doit retourner aucun résultat |
| Temps de réponse | Durée observée en millisecondes, **sans seuil universel inventé** |

Une recherche positive doit déclarer au moins un fragment de chemin
\`required_paths_contain\` et éventuellement
\`forbidden_paths_contain\`, \`minimum_hits\` et
\`minimum_distinct_sources\` (tous bornés entre 0 et 4).

Pour tester la disparition d'un **terme unique d'un ancien fichier GitHub**,
utiliser \`"expect_empty": true\`, \`"minimum_hits": 0\` et
\`"minimum_distinct_sources": 0\`. Le terme doit réellement être absent
des autres sources du projet, sinon le scénario est mal choisi.

L'outil contrôle les empreintes avant chaque qualification. Il revérifie
aussi la position des extraits dans la représentation textuelle ; pour un
PDF indexé directement sans représentation textuelle disponible, seul le
hash source peut être revérifié : le statut global devient alors
\`PASS_WITH_LIMITATIONS\` et non un \`PASS\` plein.

## Recette fonctionnelle sur la vraie installation Fedora

Après validation des tests automatisés de la PR, compléter la qualification
sur l'atelier installé :

1. Dans Open WebUI, ouvrir un chat enregistré dans le dossier natif du projet.
   Vérifier que ClawFedora active **le bon contexte**, et refuser un fil
   contenant un marqueur d'un autre projet.
2. Interroger localement la recherche sur une configuration réelle
   Terraform, un fichier Ansible et une page Notion privée du même projet.
   Vérifier les SHA, chemins et lignes remontés dans la CLI.
3. Actualiser un dépôt **de test** avec un SHA approuvé, puis vérifier
   que les anciens extraits ne remplacent pas les nouveaux. Ne pas
   modifier OpsDesk simplement pour exécuter ce contrôle.
4. Tenter une consultation en mode cloud sur le projet contenant Notion
   privé : elle doit être **refusée**. Le succès de la recette locale
   n'implique aucune autorisation de transfert.
5. Vérifier les logs et la configuration réseau réellement déployée
   pour qualifier l'absence d'envoi non autorisé. Les tests unitaires ne
   démontrent **pas** à eux seuls l'absence d'egress de la machine.
6. Contrôler un cas de réponse pédagogique : la présence de bons extraits
   n'implique pas que Qwen/DeepSeek explique correctement les fichiers.
   Cette évaluation doit être menée séparément, par observation.

### Interprétation honnête

\`PASS\` = les **scénarios du corpus, sur cette exécution**, satisfont les
conditions mesurées. Ce statut ne signifie **ni** que toutes les sources
sont couvertes **ni** qu'un modèle donne de bonnes réponses **ni** que
Terraform, K3s, les VM ou les compétences humaines sont validés.

\`FAIL\` = une attente du scénario n'a pas été remplie ; examiner les
sources avant de modifier le moteur. Une question trop générale ou une
attente de chemin irréaliste peut suffire à provoquer un échec.

\`PASS_WITH_LIMITATIONS\` = les contrôles attendus passent, mais la
position de certains extraits PDF n'a pas pu être revérifiée sans
une représentation textuelle.

La validation réelle sur Fedora ne peut pas être déduite de la seule CI.
