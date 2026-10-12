# Vérifier une CI GitHub ou GitLab publique sans croire un texte « PASS »

[← Guide](GUIDE.md) · [Évaluation des agents](EVALUATION_AGENTS.md) · [Laboratoire DevOps](LABORATOIRE_DEVOPS.md)

## Pourquoi cet outil ?

Un pipeline GitHub Actions ou GitLab CI déclaré « réussi » dans un message peut être une
erreur, une copie d'un ancien résultat ou une simple invention. Il faut examiner
**le statut officiel associé à un dépôt, un identifiant d'exécution et le commit
exact** avant de s'y fier.

La commande `clawfedora-ci-proof` interroge **en lecture seule** les API publiques
de GitHub et GitLab, en HTTPS, avec des destinations codées en dur.
Elle **ne lit ni ne télécharge** les journaux (ils peuvent contenir des secrets),
n'envoie aucune requête à Qwen ou DeepSeek, n'utilise aucune clé, et ne modifie
aucun dépôt, projet ni paramètre.

## Exemple GitHub

```bash
clawfedora-ci-proof \
  --provider github \
  --repo owner/repository \
  --run-id 12345678 \
  --commit 0123456789abcdef0123456789abcdef01234567
```

Remplacer les valeurs ci-dessus par les **vrais** identifiants. Aucune chaîne
fictive n'est une preuve du projet.

Pour examiner également les **métadonnées publiques des jobs**, ajouter
`--jobs`. Cette option interroge la liste officielle des jobs **après** avoir
vérifié l'identité et le SHA du pipeline ; elle retourne uniquement les
identifiants, noms, statuts et conclusions des jobs, jamais leurs journaux,
étapes, variables, artefacts ou secrets. Un résultat paginé ou ambigu est
**refusé** plutôt que présenté comme une liste complète.

Pour GitLab, fournir `--provider gitlab`, un chemin tel que
`group/subgroup/repository`, l'identifiant numérique du pipeline et le SHA
complet du commit.

## Ce que le rapport affirme — et ce qu'il n'affirme pas

| Verdict | Signification vérifiée |
|---|---|
| `VERIFIED_RUN_SUCCESS` | L'API officielle indique que **cette exécution** est réussie et porte le **SHA attendu** |
| `PENDING` | Le pipeline correspondant existe, mais n'a pas terminé |
| `RUN_NOT_SUCCESSFUL` | Le pipeline officiel ne rapporte pas un succès |
| `REFUSED` | Source non accessible, inconnue ou contradictoire ; aucune preuve acceptable |

Le rapport contient `provider`, `repository`, `run_id`, `commit`,
`official_url`, `observed_at_utc`, `remote_status` et un périmètre :
`pipeline_result_only`.

**Un pipeline vert n'atteste pas :** que le logiciel fonctionne sur Fedora,
que Terraform a fait `apply`, que l'API est déployée, que le rollback marche,
que les tests sont complets ou qu'un opérateur sait exécuter ces opérations.
Pour cela, le runbook doit collecter les preuves distinctes adaptées.

## Dépôts privés : consultation exclusivement opérateur

Une commande **distincte** `clawfedora-ci-private-proof` permet maintenant de
consulter en lecture seule une CI privée GitHub ou GitLab :

```bash
# Sur Fedora, en tant qu'utilisateur du runtime — jamais dans Git.
install -m 0600 /dev/null ~/.private-forge-ci.token
# Écrire le jeton hors historique du shell avec un éditeur approprié.
clawfedora-ci-private-proof \\
  --provider github --repo org/depot-prive \\
  --run-id 123456 --commit 0123456789abcdef0123456789abcdef01234567 \\
  --token-file ~/.private-forge-ci.token --jobs
```

Créer un jeton **personnel de lecture seule**, limité au seul dépôt concerné et
aux métadonnées CI nécessaires. Il n'est **jamais** passé en argument texte, en
URL, dans un prompt OpenClaw ni imprimé dans le JSON. Le fichier doit être
ordinaire, appartenir à l'utilisateur courant, avoir les permissions `0600`
(ou plus strictes), ne pas être un lien symbolique et rester hors du dépôt.

L'appel HTTPS n'autorise que les deux hôtes officiels et les chemins de lecture
pipeline/jobs exacts. Redirections, routes vers artefacts/logs, URL externes et
réponses dépassant 256 Kio sont refusées. Le rapport renvoie seulement une
preuve de statut associée à l'ID et au SHA, ainsi que les métadonnées des jobs
si demandées. **Les agents n'ont pas accès à cette commande** : un opérateur
doit volontairement l'exécuter.

Ce connecteur CLI n'est pas un connecteur GitHub/GitLab intégré à Open WebUI.
Il ne lit pas les logs, ne télécharge pas d'artefacts et n'assure pas la
preuve qu'un déploiement a effectivement réussi. Les essais avec de vrais
jetons et les droits minimaux doivent être qualifiés sur Fedora.

## Limites et règles de confidentialité

- La commande **publique** n'accepte toujours aucun jeton. Pour les dépôts privés,
  utiliser exclusivement la commande opérateur séparée documentée ci-dessus.
- **Aucun historique de chat n'est envoyé** : commande CLI hors OpenClaw.
- **Aucun accès par l'IA** à cette fonction ; le résultat peut être relu comme
  un document de preuve mais ne donne pas de permissions supplémentaires.
- Pas de redirection externe acceptée, pas d'URL libre et taille JSON bornée ;
  des champs inattendus ne sont pas reproduits dans le rapport.
- Par défaut, le résultat constate uniquement le **statut global du pipeline**.
  `--jobs` peut fournir les métadonnées publiques d'une liste complète et
  bornée (au maximum 99 jobs), mais ne valide ni les artefacts ni leurs journaux.
- Les API officielles publiques peuvent appliquer des limites de débit ;
  si l'API est indisponible, le contrôle doit **refuser** au lieu d'inventer PASS.
- Les tests unitaires simulés du dépôt prouvent les refus et les vérifications
  de SHA/ID, mais **pas la connectivité réelle** à GitHub ou GitLab depuis Fedora.

## Séparation des responsabilités

L'**agent DevOps** propose le travail et l'**auditeur** examine les preuves ;
ni l'un ni l'autre ne transforme un rapport non authentifié en réussite.
C'est l'opérateur qui décide quelles sources publiques vérifier et qui exécute
la commande. L'intégration à l'Atelier Projets devra ajouter une collecte de
preuves contrôlée, une date d'observation et une validation de provenance
**avant** de rendre le rapport disponible à un rôle.

Le projet reste soumis à l'approbation humaine, avec Qwen local par défaut et
DeepSeek seulement si ses sources sont autorisées.

**Statut actuel :** vérification du run et option `--jobs` codées ; essais contre
les vraies API publiques reportés à la phase finale.
