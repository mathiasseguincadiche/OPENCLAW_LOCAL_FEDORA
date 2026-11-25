# Discuter dans ClawFedora

[← Guide](../GUIDE.md) · [Les sept rôles](07-roles-et-outils.md) · [Atelier natif](../ATELIER_UNIQUE_CHAT_OLLAMA.md)

Ouvre `http://127.0.0.1:18890/discussions.html` après installation.
ClawFedora est l'interface native unique. Aucun compte Open WebUI,
abonnement cloud ou choix de fournisseur n'est nécessaire.

## Choisir à qui tu parles

Choisis un projet existant (ou **Sans projet**), un agent et crée le fil.
Le mentor est proposé par défaut lorsqu'il est disponible. L'aide sous le
sélecteur indique le modèle et la mission ; le fil vide montre un exemple
de demande. Rien n'est envoyé à ta place. Le rôle et le projet sont figés :
pour en changer, crée un autre fil.

| Besoin | Rôle / modèle |
| --- | --- |
| Comprendre, pratiquer, débloquer | Mentor / Qwen |
| Vérifier une version, une source | Recherche / Qwen |
| Concevoir, justifier, dessiner | Architecte / Qwen |
| Écrire ou corriger le code | DevOps / Ornith |
| Vérifier risques et accès | Sécurité / Qwen |
| Rédiger un guide | Rédacteur / Qwen |
| Contrôler les preuves | Auditeur / Qwen |

## Bien demander

Donne ton besoin, tes acquis et une contrainte. Par exemple : « Je connais
systemd et SSH. Explique comment Terraform crée une VM libvirt, puis
propose une vérification que je peux effectuer moi-même. »
Demande une réponse directe ou des indices ; aucun exercice n'est imposé.
Pour une information récente, demande les sources officielles et la version.

## Chat ou atelier ?

Une question ou un exemple : reste en discussion. Pour des fichiers à
produire, corriger et valider en plusieurs étapes, crée un projet depuis
le tableau de bord et approuve le plan. L'[atelier Projets](04-atelier-projets.md)
centralise les sources, les tâches et les preuves.
Pour utiliser des documents de référence, passe par les imports du projet ;
les pièces jointes de l'ancienne interface ne sont pas promises dans le chat natif.

Dans un fil lié au bon projet, utilise les commandes humaines `!etat`,
`!sources`, `!planifier` pour les opérations documentées par
l'[atelier natif](../ATELIER_UNIQUE_CHAT_OLLAMA.md). Toute approbation
reste séparée et explicite. Un contrôle sandbox exige une tâche DevOps
active et une image locale approuvée : voir la [boucle Ornith](../BOUCLE_ORNITH_EDIT_TEST.md).

## Obtenir un fichier

Les fichiers gérés produits par les outils sont téléchargeables depuis
les réponses qui contiennent des références valides. Voir
[téléchargements natifs](../TELECHARGEMENTS_DISCUSSIONS.md).
Un fichier, un schéma ou un PASS statique ne prouve pas un déploiement.

## Ce qu'il faut savoir

- Une seule génération à la fois ; aucun repli automatique vers un modèle distant.
- Le streaming dépend de l'activation du canary ; voir
  [streaming natif](../STREAMING_DISCUSSIONS_NATIVES.md).
- Si un tour est incertain, vérifier les effets réels avant de l'archiver
  explicitement. Aucune relance automatique.
- L'historique est privé et conservé dans le runtime
  `state/atelier-chats/` ; suivre les [sauvegardes](09-entretenir.md).
- Les modèles peuvent se tromper : demander des sources et vérifier sur la cible.

## Limites du contexte natif

Le message est limité à 8 000 octets. Le sélecteur d'historique dispose
d'un budget de 20 000 caractères, message courant inclus : jusqu'à six
échanges récents et trois échanges plus anciens pertinents, selon la place
disponible. Les échanges omis restent enregistrés localement. Ce budget
n'est pas le nombre de tokens du modèle.

## Anciennes interfaces

Les procédures Open WebUI et les routes cloud des anciennes versions sont
historiques. Dans l'ancien pont Open WebUI, les limites documentées étaient
de 32 000 octets d'historique local, quatre pièces jointes texte pour
12 000 octets cumulés et environ 3 Mio d'historique transmis sur l'ancienne
route cloud. Ces valeurs ne décrivent pas les fonctions du chat natif.
La route cloud a été retirée ; aucun historique n'est envoyé à un modèle distant.

Consulter le [retrait du cloud](12-cloud.md) et
l'[atelier natif](../ATELIER_UNIQUE_CHAT_OLLAMA.md) pour les limites de migration.
L'ancienne fiche complète reste accessible dans l'[historique Git](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/blob/623a4c4ff58db4ce26a6cc6b62969b350e5285fe/docs/fiches/03-discuter.md).
Ne pas purger les anciennes conversations sans sauvegarde et test de restauration.
