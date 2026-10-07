# Atelier Projets

[← Guide](../GUIDE.md)

L'atelier, à l'adresse `http://127.0.0.1:18890`, sert aux travaux qui dépassent une simple conversation : plusieurs documents en entrée, plusieurs étapes, des fichiers à livrer et une trace de ce qui a été décidé.

Si Open WebUI n'est pas installé, lance l'atelier seul avec `./menu.sh --action dashboard` et garde le terminal ouvert.

## Le parcours d'un projet

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

Un modèle local de cette taille fait des erreurs. L'atelier limite leurs conséquences :

- **Tes documents d'origine sont en lecture seule.** Les rôles travaillent sur des copies.
- **Les rôles n'écrivent pas directement.** Ils proposent le contenu des fichiers ; un collecteur vérifie les chemins et les formats avant d'écrire.
- **Les rôles n'exécutent rien.** Un script proposé n'est jamais lancé sur ton PC : c'est toi qui l'exécutes, dans ton environnement d'exercice.
- **Une tâche attend celles dont elle dépend.** Elle ne reçoit leur travail qu'une fois relu.
- **Deux tentatives maximum par tâche**, pour ne pas tourner en rond.

## Chercher dans tes documents

Dans un projet, clique **Actualiser l'index** puis saisis quelques mots. La recherche indique le fichier et le passage. Elle fonctionne sur le texte, les documents Office et les vingt premières pages des PDF textuels. Un PDF scanné ou une image ne sont pas indexés.

## Garder une décision

Le formulaire **Conserver une décision** enregistre un titre et ses raisons dans le projet. Les rôles peuvent ensuite les retrouver. C'est toi qui écris ces notes ; aucun modèle ne les modifie.

## Modifier un travail déjà fait

Utilise **Demander une modification cohérente du projet** : choisis la tâche à reprendre et regarde son impact. Après ton accord, l'atelier archive les anciennes versions et reprend les tâches qui en dépendaient, documentation et relectures comprises. Modifier un fichier à la main sur ton disque ne déclenche pas cette reprise.

## Mettre en pause

Clique **Mettre en pause**. La tâche en cours se termine, puis le travail s'arrête. Tu peux alors passer en mode jeu, et cliquer **Reprendre** plus tard. Les tâches déjà terminées ne sont pas refaites.

## En ligne de commande

Tout ce que fait l'interface existe aussi dans le terminal. La commande `clawfedora` est installée dans `/srv/openclaw-local/runtime/venv/bin` ; ajoute ce dossier à ton `PATH` ou donne le chemin complet.

```bash
export PATH="/srv/openclaw-local/runtime/venv/bin:$PATH"
clawfedora project status --project-id mon-projet
clawfedora project search --project-id mon-projet --query "reverse proxy"
clawfedora project pause  --project-id mon-projet
clawfedora project resume --project-id mon-projet --apply
clawfedora project --help
```
