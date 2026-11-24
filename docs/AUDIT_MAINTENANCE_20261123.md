# Revue de cohérence de l'installation et de la maintenance

Référence auditée : `fdb670b80761b8c9919bcd61fbdcc257d65712de` (PR #261
fusionnée ; 15 contrôles verts, 1 445 tests réussis, un ignoré).

## Constats et corrections

- Le bootstrap créait `state` en 0750, incompatible avec les rapports
  GPU privés qui exigent 0700. Création et remise en cohérence en 0700.
- Les archives sont constituées de fichiers, sans conserver les modes
  des répertoires parents. Restaurer dans une destination privée et
  remettre les répertoires en 0700 permet de relire les discussions
  et rapports GPU restaurés avec les mêmes contrôles de confidentialité.
- La configuration OpenClaw, les profils, le déploiement des agents,
  le téléchargement et l'adoption des modèles pouvaient être engagés
  sans conserver le verrou commun pendant la modification. Les chemins
  de maintenance passent maintenant par le verrou partagé et réutilisent
  le descripteur hérité du script parent. Les refus précèdent la mutation.
- Le fichier de verrou n'est plus tronqué par les scripts ; les liens
  et fichiers spéciaux sont refusés. Le verrou est maintenu privé.

## Vérification

Des tests synthétiques couvrent une restauration réelle dans une
destination isolée, l'accès aux deux lecteurs natifs, la contention
Bash/Python, le verrou hérité, les fichiers spéciaux et le refus des
commandes mutantes durant une génération. Les essais sur le PC restent
à faire. Aucun changement de modèle, de politique Web, de rôle ou
d'autorisation GitHub/Notion n'est introduit.

Le laboratoire DevOps reste limité à des outils autorisés dans une
copie temporaire, avec image locale épinglée, Podman sans réseau,
et sans écriture sur le projet d'origine. L'autonomie réelle d'Ornith
et la qualité pédagogique nécessitent les essais de réception.

Voir [la recette globale](RECETTE_GLOBALE.md).
