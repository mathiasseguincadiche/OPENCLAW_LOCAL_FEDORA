# Atelier Projets

[← Guide](../GUIDE.md) · [Exemple de projet de bout en bout](../EXEMPLE_PARCOURS_DEVOPS.md)

L'atelier, à l'adresse `http://127.0.0.1:18890`, sert aux travaux qui dépassent une simple conversation : plusieurs documents en entrée, plusieurs étapes, des fichiers à livrer et une trace de ce qui a été décidé.

Si Open WebUI n'est pas installé, lance l'atelier seul avec `./menu.sh --action dashboard` et garde le terminal ouvert.

## Se repérer dans l’atelier

Le sélecteur **Projet ouvert dans cet atelier** et les boutons **Ouvrir le projet**
affichent le même dossier. Les recherches et les décisions concernent ce projet.
Un changement de projet efface les anciens résultats de recherche affichés ;
une réponse de recherche tardive provenant d’un autre projet est ignorée.
Ce sélecteur ne change pas le projet sélectionné dans une conversation WebUI.

La prochaine étape apparaît sur la carte et dans le dossier. Le suivi en haut
indique l’activité partagée et le temps écoulé connu ; une action indisponible
explique la condition à remplir. Le formulaire de création est replié lorsque
des projets existent ; **Créer un projet** l’ouvre et le conserve pendant la saisie.

## Le parcours d'un projet

**Une façon de s'y retrouver :** le mentor **cadre**, l'architecte **conçoit**, le DevOps **prépare**, la sécurité **relit les risques**, le rédacteur **explique** et l'auditeur **vérifie les preuves**. Ces spécialistes ne sont appelés que si la tâche le justifie ; ce sont des rôles du même modèle, pas sept IA simultanées. [Le détail des rôles](07-roles-et-outils.md).

La différence fondamentale avec une simple discussion est la **traçabilité** : sources d'entrée, plan approuvé, fichiers attendus, contrôles et décisions restent attachés au projet.

1. **Créer le projet.** Donne un titre, un objectif précis et jusqu'à trois documents (8 Mo au total).
2. **Demander le cadrage.** Le mentor lit les documents et propose son analyse : contraintes, informations manquantes, questions. Relis, corrige, puis approuve. Rien n'avance tant que tu n'as pas approuvé.
3. **Approuver un plan court.** Le mentor propose une à quatre tâches, chacune confiée à un rôle, avec ses fichiers attendus et ses critères. Retire les rôles inutiles.
4. **Préparer une étape.** Le rôle concerné travaille. En mode guidé, il t'explique et te laisse une amorce à compléter ; en mode direct, il propose le résultat complet. Voir [Apprendre](05-apprendre.md).
5. **Soumettre et demander le retour.** En mode guidé, tu complètes les fichiers, tu expliques tes choix, puis le rôle relit ton travail.
6. **Valider et relire.** L'auditeur vérifie les critères, puis relit l'ensemble.
7. **Approuver la livraison.** C'est toujours toi qui la déclares terminée.

Les états par lesquels passe un projet :

```text
INTAKE_READY → ANALYZED → PLANNED → ASSIGNED → IN_PROGRESS
             → VALIDATING → REVIEW → PACKAGING → COMPLETE
```

## Pourquoi ces garde-fous

Un modèle de cette taille fait des erreurs, en local comme en cloud. L'atelier limite leurs conséquences :

- **Tes documents d'origine sont en lecture seule.** Les rôles travaillent sur des copies.
- **Les rôles n'écrivent pas directement.** Ils proposent le contenu des fichiers ; un collecteur vérifie les chemins et les formats avant d'écrire.
- **Les rôles n'exécutent rien.** Un script proposé n'est jamais lancé sur ton PC : c'est toi qui l'exécutes, dans ton environnement d'exercice.
- **Une tâche attend celles dont elle dépend.** Elle ne reçoit leur travail qu'une fois relu.
- **Deux tentatives maximum par tâche**, pour ne pas tourner en rond.

## Pourquoi DeepSeek peut être utile à un projet

L'atelier est **hybride** : Qwen prend en charge le travail local ordinaire ou confidentiel, alors que DeepSeek V4.1 Flash peut fournir un raisonnement et un contexte plus grands pour un **projet public difficile** (plusieurs modules IaC, architecture, CI/CD, audit documentaire).

**Le comportement réel est plus simple qu'un routage automatique :** un projet sans accord reste local ; si tu l'autorises au cloud, **l'accord couvre les étapes du projet** et non uniquement celles que le système jugerait difficiles. Les rôles, leurs outils et les règles d'approbation restent les mêmes. [Comprendre le choix des deux modèles](../ARCHITECTURE_HYBRIDE.md).

## Le cloud dans un projet

Par défaut, un projet travaille en local. Si tu as activé le cloud ([Le cloud, facultatif](12-cloud.md)), le panneau **Cloud pour ce projet** te laisse l'autoriser pour ce projet seulement, après lecture d'un texte d'accord.

- L'accord couvre tout le projet (cadrage, plan, tâches, audits) et est lié à ses sources : si elles changent, il faut approuver à nouveau.
- Si une étape cloud ne peut pas s'exécuter (filtre, plafond, fournisseur, passerelle arrêtée), **le projet se met en pause** et la raison s'affiche sur sa carte. Rien n'est refait en local sans ta décision : pour poursuivre en local, clique **Retirer l'accord cloud**, puis **Reprendre**.
- Chaque projet montre le dernier modèle utilisé, le nombre d'appels cloud et un coût estimé ; le pied de page montre la dépense du mois sur 25 €.
- En ligne de commande : `clawfedora project cloud-status`, `cloud-approve --acknowledge`, `cloud-revoke`. Un `run` ou un `resume` interrompu par une pause rend le code de sortie 3.

## Chercher dans tes documents

Dans un projet, clique **Actualiser l'index** puis saisis quelques mots. La recherche indique le fichier et le passage. Elle fonctionne sur le texte, les documents Office et les vingt premières pages des PDF textuels. Un PDF scanné ou une image ne sont pas indexés.

## Garder une décision

Le formulaire **Conserver une décision** enregistre un titre et ses raisons dans le projet. Les rôles peuvent ensuite les retrouver. C'est toi qui écris ces notes ; aucun modèle ne les modifie.

## Modifier un travail déjà fait

Utilise **Demander une modification cohérente du projet** : choisis la tâche à reprendre et regarde son impact. Après ton accord, l'atelier archive les anciennes versions et reprend les tâches qui en dépendaient, documentation et relectures comprises. Modifier un fichier à la main sur ton disque ne déclenche pas cette reprise.

## Mettre en pause

Clique **Mettre en pause**. La tâche en cours se termine, puis le travail s'arrête. Tu peux alors passer en mode jeu, et cliquer **Reprendre** plus tard. Les tâches déjà terminées ne sont pas refaites.

## En ligne de commande

Tout ce que fait l'interface existe aussi dans le terminal. La commande `clawfedora` est installée dans `/data/IA/Openclaw/runtime/venv/bin` ; ajoute ce dossier à ton `PATH` ou donne le chemin complet.

```bash
export PATH="/data/IA/Openclaw/runtime/venv/bin:$PATH"
clawfedora project status --project-id mon-projet
clawfedora project search --project-id mon-projet --query "reverse proxy"
clawfedora project pause  --project-id mon-projet
clawfedora project resume --project-id mon-projet --apply
clawfedora project --help
```


## Travailler sur plusieurs projets (Projet 1, 2, 3, 4)

Tu peux créer et conserver autant de projets distincts que nécessaire dans l'atelier (la liste
dans le chat est bornée à 50 éléments). Chaque projet possède son propre identifiant,
ses documents, son plan, ses tâches, son état et ses preuves.

- `!projets` : afficher les projets existants ;
- `!projet <identifiant>` : sélectionner le projet voulu **dans cette conversation** ;
- `!etat` : consulter le projet courant et la progression du worker ;
- `!quitter` : désélectionner le projet, sans effacer ses données.

Il est possible de garder le projet 1 en pause, de consulter le projet 2,
de revenir plus tard au premier et de reprendre son état enregistré. Les
opérations de pause/reprise suivent leurs propres conditions d'état ; consulter
le tableau de projets et les commandes affichées avant confirmation.

**Limite matérielle volontaire :** plusieurs projets peuvent exister et être
consultés en alternance, mais le worker est **unique** pour la B580 12 Go.
Une deuxième génération lancée alors qu'une première tourne reçoit un refus
explicite ; les travaux ne sont pas exécutés en parallèle et ne sont pas encore
placés dans une file d'attente durable. Ne pas confondre multi-projets et
multi-inférences. Toute évolution vers une file séquentielle doit garder ce
verrou et vérifier l'accord cloud au démarrage effectif de chaque tâche.
