# Des livrables utilisables, au format demandé

Le modèle rédige le contenu; le plugin local **clawfedora_artifact** produit les fichiers. L’export documentaire utilise ReportLab 5.0.1, python-docx 1.2.0 et markdown-it-py 4.2.0, sur CPU, à la demande. Un seul Qwen reste chargé; aucun service de conversion ni abonnement n’est ajouté.

## Qui produit quoi ?

| Rôle | Livrables et formats utiles |
|---|---|
| Mentor OPS | Brief, plan d’apprentissage, fiche de repères : Markdown/TXT et PDF/DOCX si demandés |
| Recherche | Note sourcée, comparaison et bibliographie datée : Markdown/TXT/PDF/DOCX |
| Architecte | ADR/dossier Markdown/PDF/DOCX, Draw.io éditable + SVG; ébauches YAML/JSON/HCL et templates |
| DevOps | Ansible/CI/Compose/Kubernetes `.yaml/.yml`, Terraform `.tf/.tfvars/.hcl`, scripts `.sh/.py`, Dockerfile, Jinja `.j2`, unités systemd `.service`, INI/TOML/JSON/XML; runbooks Markdown/PDF/DOCX/TXT |
| Sécurité | Rapports Markdown/PDF/DOCX/TXT, configurations de droits/exposition/politiques et templates techniques |
| Rédacteur pédagogique | Documents structurés Markdown, PDF, DOCX et texte; source modifiable et exports cohérents |
| Auditeur | Son propre rapport Markdown/TXT/PDF/DOCX; aucune modification des livrables audités |

Les sept rôles disposent des formats documentaires. La génération de fichiers techniques par ce plugin est réservée à l’architecte, au DevOps et à la sécurité. L’outil Draw.io demeure réservé à l’architecte. Ces permissions ne donnent pas de terminal général.

## Demander le résultat dans le chat

Exemple : « Explique-moi le rôle des artefacts dans une CI, puis fournis une fiche Markdown, PDF et DOCX. » Le rédacteur appelle le plugin; la passerelle ajoute de vrais liens de téléchargement à sa réponse, après vérification des fichiers et de leurs hashes. Le paramètre `filename` conserve un nom utile, par exemple `fiche-ops.md`, `main.tf`, `Dockerfile` ou `nginx.service`, sans accepter de chemin. Le contenu de la réponse ne suffit pas à inventer une pièce jointe.

Les liens concernent le tour courant et expirent après 24 heures; télécharger les fichiers pour les conserver. Ils sont locaux, personnels et signés, sans divulguer le jeton opérateur. Le chat ne publie rien dans un projet. Les fichiers restent dans le workspace géré; ce dossier entre dans la maintenance et les sauvegardes de l’installation.

## Travailler dans un projet

Préciser les formats dans la demande. Le mentor inscrit les chemins dans le plan; le PDF/DOCX exige une source `.md` de même nom dans le même dossier. Exemple de sorties approuvées :

```text
deliverables/guide/guide.md
deliverables/guide/guide.pdf
deliverables/guide/guide.docx
deliverables/guide/guide.txt
```

Le rédacteur fournit le Markdown une fois au plugin, avec les exports demandés. Le plugin retourne des références courtes; les PDF/DOCX ne passent pas en base64 dans les 1024 tokens de réponse. Le worker vérifie rôle, appel courant, formats et hashes, puis collecte les fichiers attendus. Une exportation réussie ne valide pas le contenu du document.

En guidé, la source Markdown reste modifiable dans le formulaire. Les exports indiquent la source à modifier; ils ne sont pas des champs de texte binaire. Après soumission, le spécialiste relit le brouillon et les exports réels dans un snapshot protégé. Ils sont publiés après le retour PASS, avec des hashes correspondant exactement aux fichiers relus. Les tâches dépendantes reçoivent aussi la source; une révision approuvée les reprend comme les autres livrables. Télécharger les fichiers publiés depuis la liste de documents du projet.

Les brouillons de configuration, de code et de Markdown sont également téléchargeables dans leur format texte avant soumission. Le formulaire ne les exécute pas. Les fichiers générés restent non exécutables sur le poste tant que l’opérateur ne choisit pas leur utilisation.

## Les bons outils pour le bon travail

```text
clawfedora_artifact(
  format="markdown",
  content="# Une fiche OPS\n\nComprendre, essayer, vérifier.\n",
  exports=["pdf", "docx", "txt"]
)
```

Les formats techniques sont `yaml`, `json`, `python`, `shell`, `hcl`, `ini`, `toml`, `xml`, `dockerfile`, `template`. L’outil préserve les fichiers et contrôle la syntaxe JSON/YAML/Python/TOML/XML sans les exécuter. YAML accepte plusieurs documents, utile pour Kubernetes. Pour un fichier Jinja encore incomplet, choisir `template`, puis contrôler le résultat rendu dans le laboratoire.

HCL, Dockerfile, INI, shell et Jinja sont produits comme du texte littéral. Leur création ne signifie pas qu’un validateur métier les a acceptés. Appeler les linters disponibles, puis vérifier Terraform/Ansible/Compose/Kubernetes dans l’exercice ou sa CI. Une configuration utilisable et sa documentation restent deux fichiers distincts.

## Budgets et qualité des exports

Entrée du plugin : 12 000 octets de contenu; au plus trois exports. Documents longs : produire plusieurs sections/tâches, avec une source structurée. La conversion interne accepte au plus 60 000 octets de Markdown, 500 blocs, 100 lignes/6 colonnes par table et 80 pages PDF; un artefact est limité à 2 Mo. Les exports sont déterministes pour les mêmes sources et versions, afin de conserver la preuve du fichier relu.

Le rendu prend en charge titres, paragraphes, listes, blocs de code et tableaux simples. Les ressources externes ne sont pas téléchargées; les images restent des indications textuelles et les liens sont conservés comme texte. Les schémas Draw.io/SVG restent fournis séparément. Ce moteur n’est pas une reproduction de toute la mise en forme Word, ni un convertisseur de PDF vers DOCX. Le DOCX reste éditable dans Word/LibreOffice; une modification externe de cet export ne met pas automatiquement à jour le Markdown. Reprendre la source dans le projet pour garder les formats cohérents.

Le code complet demeure dans le fichier technique ou la source Markdown : les longues lignes peuvent être repliées pour la lecture du PDF. Les contrôles logiciels ne prouvent pas la vitesse, la stabilité GPU ou la qualité rédactionnelle du vrai modèle sur la B580. `clawfedora_tool_status` expose les formats et versions présents; un export indisponible doit être signalé.

Sources officielles consultées le 6 octobre 2026 : [ReportLab/Platypus](https://docs.reportlab.com/reportlab/userguide/ch5_platypus/), [python-docx](https://python-docx.readthedocs.io/en/stable/), [markdown-it-py](https://pypi.org/project/markdown-it-py/), [plugins OpenClaw](https://docs.openclaw.ai/tools/plugin). Les versions ci-dessus sont des pins de cette intégration.
