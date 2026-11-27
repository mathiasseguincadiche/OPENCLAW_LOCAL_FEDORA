# Inventaire documentaire GitHub à un commit précis — C02, lot 1

L'inventaire identifie les fichiers versionnés d'un dépôt, leurs catégories,
leurs modes Git et les identifiants de leurs blobs. Les signaux de la
[charte GitHub](GITHUB_REPOSITORY_DESIGN_SYSTEM.md) indiquent où chercher
le README, l'architecture, les workflows et les preuves.

## Choisir la source et la révision

Renseigner le SHA complet du commit et un dossier de sortie privé hors Git.
La commande écrit un JSON neuf en mode `0600` sur un système POSIX.

```bash
python -m clawfedora.github_document_inventory --path /chemin/du/clone \
  --commit SHA_COMPLET --output "$DOSSIER_PRIVE/inventaire-github.json"
```

En local, Git lit directement l'arbre du commit. Les fichiers modifiés,
non suivis ou absents du répertoire de travail n'affectent pas le résultat.
L'identité du commit est vérifiée et l'accès au réseau est désactivé.

```bash
python -m clawfedora.github_document_inventory --github PROPRIETAIRE/DEPOT \
  --commit SHA_COMPLET --output "$DOSSIER_PRIVE/inventaire-github.json"
```

La source GitHub utilise le connecteur de lecture existant dans ClawFedora.
Elle récupère le commit et son arbre récursif avec deux requêtes. Aucun
blob n'est téléchargé et le plafond de l'import de contenu ne s'applique
pas. Un arbre tronqué, divergent ou hors budget est refusé.

## Lire le rapport

- Le SHA du commit, l'identifiant de son arbre et l'empreinte du rapport
  permettent de rattacher l'analyse à une révision précise.
- Les catégories recensent la documentation, ses ressources graphiques,
  les workflows, la gouvernance, les preuves et les fichiers techniques.
- Les chemins sensibles reconnus par les règles existantes et les
  dossiers explicitement privés sont exclus. Les liens symboliques et
  sous-modules sont comptés sans être suivis.
- Les signaux décrivent les chemins trouvés. La présence d'un workflow
  ne démontre pas sa réussite. La conformité du contenu, les ancres,
  les versions et les preuves CI demandent leurs contrôles dédiés.

Le rapport contient des noms de fichiers. Le conserver dans le périmètre
du projet et le relire avant toute diffusion. L'auditeur
`clawfedora-github-audit` reste disponible pour inspecter les contenus d'un
dossier ou d'un instantané importé. Cette commande d'inventaire couvre
jusqu'à 12 000 entrées, avec des limites de transport et de taille du JSON.

[Documentation de git ls-tree](https://git-scm.com/docs/git-ls-tree)
