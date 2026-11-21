# Actualiser GitHub dans un projet long sans remplacer ses sources initiales

Cette procédure accompagne les projets évolutifs, comme OpsDesk. Elle conserve
un historique de révisions GitHub à SHA complet au sein **du même projet
ClawFedora**. Elle ne modifie ni le dépôt distant ni les fichiers de l'intake.

## Préparation : lier le dépôt une première fois

Le projet doit déjà avoir importé une version GitHub en utilisant
'clawfedora-sources --project-id ... --github propriétaire/dépôt
--commit SHA40 --apply', **avant la première analyse**.
Le dépôt est lié par les métadonnées du snapshot initial, pas par un nom
approximatif ou par l'URL insérée dans un prompt.

Une fois le projet analysé, les sources initiales restent scellées.
Ne pas modifier 'intake/', 'sources/' ou 'project.json' pour essayer
d'actualiser le dépôt.

## Prévisualiser un nouveau commit

~~~bash
# Interroge GitHub en lecture seule et télécharge un snapshot TEXTUEL en zone temporaire.
# La prévisualisation n'écrit rien dans le dossier du projet et n'envoie rien au cloud.
clawfedora-github-refresh \
  --project-id mon-projet \
  --github mathiasseguincadiche/OpsDesk \
  --commit <SHA_COMPLET_40_CARACTÈRES>
~~~

L'outil compare les fichiers admissibles avec le snapshot déjà enregistré.
Il retourne la version de base, la nouvelle version et les fichiers
'added', 'modified' ou 'removed', sans afficher leur contenu.

La réponse comporte 'approve_sha256'. Après lecture du rapport, recopier
**exactement** son empreinte pour l'enregistrement :

~~~bash
# La commande recharge le même commit et revérifie la prévisualisation.
# Un décalage de SHA, de contenu ou de version initiale entraîne un refus.
clawfedora-github-refresh \
  --project-id mon-projet \
  --github mathiasseguincadiche/OpsDesk \
  --commit <SHA_COMPLET_40_CARACTÈRES> \
  --approve <EMPREINTE_SHA256_DE_LA_PRÉVISUALISATION> \
  --apply
~~~

Une autorisation cloud encore enregistrée doit être retirée avant une
mise à jour. Même après enregistrement, le nouvel état ne réautorise
aucun transfert cloud : il faudra approuver séparément les sources
utilisées dans une prochaine étape.

Le mécanisme reprend les limites de l'importeur GitHub (240 fichiers
textuels admissibles, 1 Mo par fichier, 6 Mo au total), refuse les
chemins et types dangereux et recherche les secrets courants dans les
fichiers téléchargés. Un fichier exclu ou une source non textuelle ne
devient **pas** une preuve d'absence de vulnérabilité ou de changement.

## Ce qui est conservé

- Les anciennes versions restent dans leur répertoire original.
- La nouvelle version est rangée sous
  'projects/<projet>/context/github-updates/<cle-depot>/<sha>/files/'.
- Le registre 'ledger.json' conserve les SHAs successifs, la provenance,
  les empreintes, le diff et les risques de requalification.
- Le tableau de bord Projets et la réponse '!etat' d'Open WebUI affichent
  le SHA courant ainsi que les changements recensés.
- Les tâches, décisions, preuves personnelles et états des exercices
  ne sont jamais modifiés ni déclarés automatiquement vérifiés.

**IMPORTANT : la révision enregistrée est un snapshot conservé pour revue,
pas encore un changement automatique des sources du plan multi-agent.**
Le moteur de tâches et sa recherche restent sur le snapshot initial.
Il faut encore une étape séparée d'approbation/requalification de
l'usage de cette nouvelle version par les agents. Cela évite de faire
passer une ancienne analyse ou une ancienne preuve pour une validation
du nouveau code.

Après chaque mise à jour, vérifier manuellement si les objectifs,
configurations et preuves antérieurs couvrent toujours le nouveau SHA.
Des jalons du parcours sont listés comme « à revoir », sans que leur
statut d'acquisition ou les pages Notion ne soient réécrits.

## Qualification

Tests attendus : GitHub simulé, premier snapshot, changements multiples,
fichier supprimé, refus de secret, tentative d'écriture sans empreinte,
empreinte périmée, stockage modifié, lien symbolique, arbre tronqué,
accord cloud existant, non-régression des preuves et des états.

**Le test réel sur Fedora et sur un compte GitHub demeure distinct
des contrôles CI.**
