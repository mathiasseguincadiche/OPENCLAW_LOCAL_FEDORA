# Découvrir l'Atelier IA **hybride** Fedora — guide pas à pas

[← Accueil du dépôt](../README.md)

**Objectif de ce guide :** comprendre **pourquoi Qwen local et DeepSeek cloud coexistent**, savoir à qui poser une question, comment choisir une route d'inférence et distinguer ce qui est **proposé** de ce qui est **réellement vérifié**. Pas besoin de connaître OpenClaw pour commencer.

**Pour mesurer ta progression dans la qualité des réponses** : [scénarios multi-tours et notation clarté/profondeur/interactivité/exactitude sur 20](EVALUATION_PEDAGOGIE.md). C'est une grille humaine, pas une note calculée par l'IA ni une garantie de supériorité face à Gemini.

## 1. Pourquoi un atelier plutôt qu'un simple chatbot ?

Tu peux utiliser l'IA de deux façons :

- **Pour une question rapide** : « Pourquoi Terraform a-t-il un fichier d'état ? ». Tu choisis un rôle, tu lis la réponse et tu peux demander un exemple.
- **Pour un vrai travail DevOps** : « Prépare l'architecture, les fichiers, les contrôles et le guide d'un déploiement ». Tu crées un projet avec des étapes, des rôles et des validations.

L'atelier est conçu pour apprendre **en comprenant**. Tu peux demander une réponse complète : **aucun exercice ni questionnaire n'est obligatoire**. Si tu souhaites pratiquer, il existe un mode guidé sur consentement.

### Les trois choses à retenir

1. **C'est une architecture hybride à deux moteurs.** Qwen local est le socle du quotidien ; DeepSeek cloud apporte une **capacité supplémentaire** sur des problèmes complexes ou de longs contextes, quand ce choix est utile et autorisé.
2. **Les sept agents sont sept métiers, pas sept moteurs supplémentaires.** Un même agent (mentor, DevOps, auditeur…) travaille sur Qwen **ou** DeepSeek avec **les mêmes outils autorisés**. Le modèle propose, le moteur contrôle et l'humain valide.
3. **Le cloud est une décision, pas une bascule magique.** Il faut l'activer ; un projet exige son accord. Il n'existe pas de sélection automatique du meilleur modèle pour chaque tâche. Une recherche Web est une sortie réseau distincte.

→ **[Pourquoi Qwen + DeepSeek ? Stratégie et exemples d'efficacité](ARCHITECTURE_HYBRIDE.md)**.

![Les sept spécialités autour du même moteur](diagrams/atelier-roles.svg)

→ [Découvrir les sept rôles, leurs outils et des demandes types](fiches/07-roles-et-outils.md).

## 2. L'architecture en image

![Les deux interfaces, le moteur de projet, OpenClaw et les modèles](diagrams/atelier-architecture.svg)

Suis les flèches **de gauche vers la droite**, puis vers le bas : **ta demande → les règles et le rôle → le modèle → la réponse ou les fichiers contrôlés**. Le système comporte deux interfaces mais un seul moteur de projet :

| Partie | Pour toi, c'est… | Ce qu'elle fait |
|---|---|---|
| **Open WebUI** | Le chat de tous les jours | Discuter, choisir un rôle, joindre des fichiers |
| **Atelier Projets** | Le tableau de bord | Créer, organiser, approuver et suivre |
| **Pont / worker** | Les règles du jeu | Limites, étapes, verrous, collecte et confirmations |
| **OpenClaw** | La fiche métier | Appliquer consignes et outils du rôle |
| **Ollama / Qwen** | Le moteur local quotidien | Autonomie, confidentialité et tâches ciblées |
| **OpenRouter / DeepSeek** | Le moteur cloud de capacité | Analyses complexes, grands dossiers publics et raisonnement DevOps |
| **Passerelle cloud locale** | Le contrôleur d'accès | Consentement, filtre des secrets, prix et budget |

→ [Lire le schéma composant par composant](fiches/11-comment-ca-marche.md).

## 3. Premier scénario : une question simple

Tu ouvres **Open WebUI** (`http://127.0.0.1:3000`, une fois installé), sélectionnes **Mentor infrastructure/OPS** et demandes :

> Je connais les services systemd et les scripts Bash. Explique-moi ce qu'Ansible apporte, avec un exemple simple, ce qu'il faut vérifier et ses limites.

Le mentor peut expliquer le vocabulaire et le mécanisme, puis proposer un exemple **non exécuté**. S'il te manque une version précise d'Ansible, tu peux sélectionner **Expert recherche** pour obtenir des sources datées.

**À essayer ensuite :** « Explique chaque ligne du YAML que tu proposes, puis indique ce que tu ne peux pas vérifier depuis cette conversation. »

→ [Discuter](fiches/03-discuter.md) · [Apprendre](fiches/05-apprendre.md).

## 4. Deuxième scénario : un petit projet à plusieurs étapes

Pour une application Linux à déployer, l'intérêt est de ne pas mélanger architecture, scripts, sécurité et relecture.

1. **Tu crées le projet** et joins son objectif et, si besoin, des documents sources.
2. **Le mentor cadre**, recherche les informations manquantes et propose un plan court.
3. **Tu approuves** l'analyse puis les tâches utiles (par exemple architecte et DevOps).
4. **Le worker distribue** les tâches dans l'ordre prévu. Il n'y a pas sept agents en parallèle.
5. **Le spécialiste propose** un résultat et une méthode pour le vérifier. Le collecteur contrôle les fichiers attendus.
6. **L'auditeur relit** les critères et les preuves. S'il manque une preuve, le travail doit être repris.
7. **Tu approuves la livraison**. Si une application doit être réellement installée, c'est **toi** qui exécutes et observes l'opération dans ton laboratoire.

**Règle pratique :** si tu as déjà un fichier `.tf` et veux seulement comprendre son contenu, **ne crée pas un projet**. Un petit fichier texte peut être joint au chat local (4 fichiers, 12 000 octets cumulés).

→ [Parcours DevOps commenté, du besoin au livrable](EXEMPLE_PARCOURS_DEVOPS.md) · [Piloter les projets](fiches/04-atelier-projets.md).

## 5. Quel rôle choisir ?

| Situation | Rôle conseillé |
|---|---|
| Je veux comprendre ou je suis bloqué | **Mentor** |
| Je veux une documentation officielle récente | **Expert recherche** |
| Je dois choisir une architecture et comprendre les flux | **Architecte** |
| Je dois préparer Terraform, Ansible, Bash ou une CI | **DevOps** |
| Je veux vérifier droits, secrets ou exposition réseau | **Sécurité** |
| Je veux un guide clair, lisible et exportable | **Rédacteur** |
| Je veux savoir si une exigence est **prouvée** | **Auditeur** |

→ [Voir les outils exacts et leurs restrictions](fiches/07-roles-et-outils.md).

## 6. Préparer et installer Fedora

**Parcours recommandé :** installer Fedora 45 Workstation stable / GNOME 51 sur le SSD système, puis monter le second disque durablement sous **`/IA`**. Les données de l'atelier sont installées dans **`/IA/Openclaw/`**. La machine cible (Ryzen 7 7700, 48 Go, Arc B580) n'a pas encore fait l'objet d'une réception physique.

```bash
findmnt --mountpoint /IA   # vérifier que le second disque est monté
git clone https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA.git
cd OPENCLAW_LOCAL_FEDORA
./menu.sh --action install                 # aperçu
./menu.sh --action install --apply
```

Après reconnexion à la session Fedora pour prendre en compte les groupes GPU :

```bash
./menu.sh --action webui-install --apply
# Ouvrir http://127.0.0.1:3000 et créer le compte local
./menu.sh --action webui-seal --apply
./menu.sh --action quick-check
```

**Un seul contrôle rapide suffit pour commencer :** vérifier les services, la B580 et une courte réponse Qwen, puis essayer une vraie question dans WebUI et un petit projet. Les benchmarks 8K/16K/32K, stress tests et canaries ne sont pas des prérequis au premier usage.

→ [Installer sans deviner](INSTALLATION_SIMPLE_FEDORA45.md) · [Réception technique facultative](validation/README.md).

## 7. Documents, dessins et validations : ne pas mélanger

- **Markdown** : la source éditable d'un guide. Le PDF et le DOCX sont des exports issus de cette source.
- **Draw.io** : le schéma éditable de l'architecte. Le SVG n'est qu'un aperçu qui ne se resynchronise pas automatiquement.
- **Contrôle statique** : peut signaler des erreurs JSON/YAML/Python, Bash, Markdown ou secrets selon l'agent. Cela **n'exécute ni Terraform ni Ansible**.
- **Preuve d'exécution** : un résultat réellement obtenu sur la plateforme cible, daté et attribuable à la bonne version.
- **Livraison** : fichiers attendus, critères et approbation humaine ; elle ne certifie pas que ton infrastructure externe est en production.

→ [Fichiers, limites et Draw.io](fiches/06-fichiers-et-schemas.md).

## 8. Local ou DeepSeek : optimiser le travail, pas simplement le coût

| Situation | Route recommandée | Pourquoi |
|---|---|---|
| Expliquer `systemd`, documenter un petit playbook, travailler sur des données privées | **Qwen local** | Tâche courte ou sensible, coût API nul |
| Revoir plusieurs modules Terraform **publics**, une CI complexe, un ADR multi-contraintes | **DeepSeek cloud**, sur choix explicite | Contexte et raisonnement supplémentaires, gain de qualité **attendu, pas encore mesuré** |
| Projet avec données professionnelles confidentielles | **Qwen local** | Le filtre de secrets ne détecte pas tous les contenus sensibles |

En chat, tu choisis la **variante locale ou cloud** ; en atelier, un **accord au niveau du projet** permet la route DeepSeek. **Le routage par difficulté ou par agent n'est pas encore automatique.** Les mêmes consignes et restrictions d'outils s'appliquent.

La recherche Web d'un agent peut interroger Internet **même avec Qwen** : elle est distincte de l'envoi d'une conversation à DeepSeek.

→ **[Pourquoi cette architecture hybride ?](ARCHITECTURE_HYBRIDE.md)** · [Activer le cloud](fiches/12-cloud.md) · [Choix du modèle](DECISION_MODELE.md).

## 9. Quel est le vrai niveau de maturité ?

Le code et les tests automatiques existent. Les performances GPU, la vraie compatibilité du conteneur Open WebUI, la voix, les uploads, la restauration et le fournisseur cloud doivent encore être **essayés sur le PC Fedora**. Le streaming SSE est préparé mais désactivé par défaut ; aucune migration WebUI historique n'est requise pour une installation neuve sous **Open WebUI 0.12.3**.

→ [État actuel](../STATUS.md) · [Validation facultative](validation/README.md) · [Historique des plans](archives/2026/README.md).

## La bibliothèque, par besoin

| Pour quoi faire ? | Fiche |
|---|---|
| Installer | [01 — Installer](fiches/01-installer.md) |
| Contrôler le GPU et les performances | [02 — Premier essai](fiches/02-premier-essai.md) |
| Discuter, charger un petit fichier, utiliser les commandes | [03 — Discuter](fiches/03-discuter.md) |
| Gérer les sources, les tâches et les approbations | [04 — Atelier Projets](fiches/04-atelier-projets.md) |
| Comprendre sans exercices imposés | [05 — Apprendre](fiches/05-apprendre.md) |
| Produire PDF, DOCX, Terraform et Draw.io | [06 — Fichiers et schémas](fiches/06-fichiers-et-schemas.md) |
| Choisir un agent et comprendre ses outils | [07 — Rôles et outils](fiches/07-roles-et-outils.md) |
| Configurer les limites | [08 — Réglages](fiches/08-reglages.md) |
| Sauvegarder et mettre à jour | [09 — Entretenir](fiches/09-entretenir.md) |
| Diagnostiquer | [10 — Dépanner](fiches/10-depanner.md) |
| Comprendre les composants et flux | [11 — Comment ça marche](fiches/11-comment-ca-marche.md) |
| Activer ou désactiver le cloud | [12 — Le cloud, facultatif](fiches/12-cloud.md) |

**Pour retenir l'essentiel :** **le modèle propose ; le moteur encadre et collecte ; tu vérifies et approuves.**
