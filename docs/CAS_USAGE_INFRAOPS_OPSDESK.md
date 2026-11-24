# Cas de référence InfraOps — enseignements du dépôt OpsDesk

[← Architecture locale](ARCHITECTURE_LOCALE_QWEN_ORNITH.md) · [Sept agents](fiches/07-roles-et-outils.md) · [Laboratoire](LABORATOIRE_DEVOPS.md)

**Source consultée :** dépôt public [OpsDesk](https://github.com/mathiasseguincadiche/OpsDesk),
branche `main`, commit de référence `623fcd69626e78ec856033e4dc82a9b6aec08ad2`.
L'atelier ne synchronise **pas automatiquement** GitHub ou Notion. Cette page
est une étude de cas **datée**, pas une lecture permanente de leur contenu.
Lors d'un vrai projet, importer volontairement un snapshot vérifié et
conserver les notes privées hors des publications et requêtes Web. L'inférence est exclusivement locale.

## Ce qu'OpsDesk exige réellement

OpsDesk est une **application de tickets servant de support à l'apprentissage
et au travail InfraOps**. La v2 du socle utilise FastAPI, React/nginx et
PostgreSQL 17. Le code applicatif et le Compose local sont testés ; les
13 exercices d'infrastructure **ne sont pas des réalisations personnelles
déjà validées**.

| Domaine | Cible ou exercice déclaré | Preuve à attendre |
| --- | --- | --- |
| Hôte et virtualisation | Fedora 45, KVM/QEMU/libvirt | `virsh`, VM démarrée, réseau et accès réels |
| Provisionnement | Terraform libvirt depuis l'hôte Fedora ; administration Ansible depuis la VM dédiée | Plan approuvé, apply observé, state protégé, SSH et second plan |
| Configuration | Ansible sur Rocky Linux 10.2 | Paquets/réseau/SELinux/firewalld contrôlés, seconde passe `changed=0` |
| Service principal | Docker Engine + Compose sur `srv-app`, API/frontend/PostgreSQL | Conteneurs sains, requête métier, persistance et reboot |
| CI/CD | GitHub Actions, Trivy, GHCR privé, images par digest, approbation Ansible | Tests, scan lu, digest déployé identique au digest qualifié |
| Orchestration d'essai | K3s sur `srv-k3s`, **copie distincte** de l'application | Sondes, rollout, rollback, trafic de test, pas de production déplacée |
| Observabilité | Prometheus, Grafana, journaux JSON, k6 sur copie | Scrape, alerte `firing`, diagnostic et mesures réelles |
| Sauvegarde/PRA | `pg_dump` et sauvegarde externe Borg chiffrée, restauration isolée | Checksum, ticket témoin, RPO/RTO calculés et comparés |

La cible V2 impose aussi HTTPS dès la livraison serveur, Ansible Vault pour les secrets,
et Grafana Alerting par e-mail. L'infrastructure reste prévue et non qualifiée.

Les noms et la topologie ici décrivent **le projet de référence**. Les
agents ne doivent pas imposer ces choix à tous les projets futurs. Une
modification de la stack exige une raison, un ADR et un contrôle de compatibilité.

## Deux espaces complémentaires

Le dépôt GitHub contient le code, la preuve technique et la présentation
publique ; la page Notion [OpsDesk — Centre de formation](https://app.notion.com/p/3fc65721fa1881ad8325c8c4619c7223)
contient les cours, les 13 exercices complets, la préparation de Fedora et
le suivi des réalisations. Ne jamais publier ou recopier les notes de travail
personnelles sur GitHub. L'atelier peut désormais importer, sur choix
explicite, un snapshot GitHub versionné et des pages Notion protégées
(voir [l'intégration](INTEGRATION_GITHUB_NOTION.md)).

## Présentation du wiki et parcours réel

Le wiki OpsDesk sert de référence concrète pour la
[charte universelle Notion](NOTION_WIKI_DESIGN_SYSTEM.md) :
accueil illustré, cinq espaces, treize cours/exercices et suivi
des preuves séparé des validations du socle. Les gabarits GitHub
ne doivent **pas recopier les notes privées de l'apprenant**.
La cohérence de structure peut être auditée, mais la recette
graphique réelle et les tests sur Fedora restent distincts.

## Les sept agents sur ce type de mission

| Agent | Quand il est vraiment utile | Contribution attendue |
| --- | --- | --- |
| Mentor | Concept nouveau ou blocage d'apprentissage | Pourquoi, mécanisme, petit exemple, prochaine vérification |
| Recherche | Provider libvirt, versions, Docker sur Rocky ou K3s | Sources officielles, dates, limites et commandes à vérifier |
| Architecte | Réseau privé, séparation des VMs, volumes, flux, choix Compose/K3s | ADR, Draw.io/SVG, compromis, hypothèses et risques |
| DevOps | Terraform, Ansible, Compose, CI, backup, dépannage | Proposition versionnée, contrôles, rollback et résultat attendu |
| Sécurité | SELinux, firewalld face à Docker, secrets, accès privilégiés, scans | Constats prouvables, protections maintenues, tests de refus |
| Rédacteur | Runbooks, incident, recette et dossier de preuve | Prérequis, procédure expliquée, observation, échecs, retour arrière |
| Auditeur | Validation avant de déclarer un livrable ou un exercice réussi | Confrontation des critères et des preuves, refus du PASS fictif |

**Le modèle est choisi après le besoin et le rôle**, non l'inverse.
Qwen 3.5 9B assure six rôles ; Ornith 1.5 9B produit et corrige le code
avec les validateurs autorisés. Aucun repli cloud. Une aide du modèle ne
démontre pas une compétence personnelle.

## Autonomie et modalités d'aide

Le parcours OpsDesk distingue L0 (découvrir), L1 (comprendre et prévoir),
L2 (réaliser personnellement) et L3 (réaliser une tâche nouvelle avec
vérification séparée), ainsi que A0 à A3 pour les niveaux d'aide.
L'atelier sait déjà proposer des travaux guidés par accord explicite.
Il doit **respecter le niveau d'aide choisi** et ne jamais attribuer L2
ou L3 à partir de la génération d'un fichier, d'une note d'IA ou d'une
CI verte.

Pour un exercice : comprendre le problème → préparer la cible →
proposer la commande et ses effets → obtenir l'accord nécessaire →
exécuter sur le bon environnement → conserver la sortie réelle →
diagnostiquer → corriger ou revenir en arrière → expliquer ce qui est acquis.
Un exemple voisin vaut mieux qu'une solution toute faite quand
l'apprenant demande des indices.

## Qualifier les modèles avec les tâches pertinentes

Deux suites coexistent. La suite historique continue de garantir les
sept rôles génériques. La nouvelle suite **InfraOps** est également
composée de sept tâches **synthétiques et publiques**, portant sur
libvirt, la séparation Docker/K3s, SELinux/firewalld, CI/GHCR,
PostgreSQL et les niveaux d'apprentissage.

```bash
# Prépare des scénarios, sans appel IA ni coût.
clawfedora-evals --suite infraops --plan

# N'affiche que les entrées pour comparer les vrais modèles.
clawfedora-evals --suite infraops --inputs-only

# Les réponses et les notes humaines se stockent hors du dépôt.
clawfedora-evals --suite infraops --report ./notes_infraops_local.json
```

Qualifier Qwen et Ornith sur le même SHA de suite et avec les mêmes
contraintes, selon les rôles attribués. Noter la qualité des réponses et les
reprises réellement nécessaires. Aucun verdict de supériorité n'est acquis.
La grille technique note exactitude, clarté, preuve et sécurité, sans se
substituer à un test sur les VM réelles.

## Ce que le système sait faire — et la limite à garder visible

- **Présent dans le code :** spécialités, génération de fichiers,
  contrôles statiques autorisés, preuve opérateur, plans approuvés,
  boucle Ornith édition/test/correction, laboratoire Podman rootless facultatif,
  imports GitHub/Notion sur demande et publication sous approbation.
- **Non démontré sur le PC :** création des VM et liaison libvirt,
  installation/SELinux Docker sur Rocky, K3s, réseau, restauration,
  supervison et performances de la B580.
- **Non implémenté :** synchronisation GitHub/Notion automatique pour
  une tâche complète du dépôt, exécution autonome de Terraform/Ansible
  et récupération des observations du laboratoire réel. L'agent ne
  peut pas certifier ce qu'il ne voit pas.

### Évolutions à envisager après qualification

1. Réceptionner l'import GitHub déjà implémenté, sur un dépôt et un commit
   précis, avec manifeste et filtrage des fichiers sensibles.
2. Une **matrice de preuves opérateur par environnement** : machine,
   version, configuration, commande, attendu, résultat, date et révision,
   avec inventaire de tests réels par cible.
3. Des **recettes KVM/Rocky et Docker/K3s** répétables sur une cible
   d'essai uniquement. Autorisation humaine avant chaque modification
   sensible, isolation des secrets et contrôle du réseau réel.
4. Une évaluation pédagogique InfraOps sur plusieurs tours, puis
   qualification des deux modèles locaux.

Ces évolutions sont **des pistes**, pas des fonctionnalités
déjà livrées par cette adaptation. Ne pas mettre de réponses complètes
aux exercices dans OpsDesk pour faciliter un benchmark.

## Références du cas étudié

- [État et limites](https://github.com/mathiasseguincadiche/OpsDesk/blob/main/STATUS.md)
- [Architecture et décisions](https://github.com/mathiasseguincadiche/OpsDesk/blob/main/docs/architecture.md)
- [Parcours et exercices personnels (Notion)](https://app.notion.com/p/3fc65721fa1881ad8325c8c4619c7223)
- [Contrat applicatif](https://github.com/mathiasseguincadiche/OpsDesk/blob/main/docs/contrat-applicatif.md)
- [Feuille de route](https://github.com/mathiasseguincadiche/OpsDesk/blob/main/ROADMAP.md)

**Statut : analyse documentaire et adaptations préparatoires. La qualité
réelle des modèles et l'utilisation sur Fedora restent à mesurer.**
