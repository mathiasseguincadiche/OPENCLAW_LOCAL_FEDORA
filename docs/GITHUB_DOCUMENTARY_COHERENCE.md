# Cohérence documentaire au commit — C02, lot 3

Le contrôle lit un contrat documentaire versionné et compare les
déclarations sélectionnées aux fichiers techniques du même commit. Les
constats indiquent le chemin, le blob Git, le sélecteur et la ligne
documentaire lorsqu'elle est disponible.

```bash
python -m clawfedora.github_document_coherence --path /chemin/du/clone \
  --commit SHA_COMPLET --output "$DOSSIER_PRIVE/coherence-github.json"
```

Utiliser `--github PROPRIETAIRE/DEPOT` pour lire le même périmètre via
GitHub. La commande accepte l'empreinte du
[lot d'inventaire](GITHUB_DOCUMENTARY_INVENTORY.md) avec
`--inventory-sha256`. Utiliser la même source d'inventaire pour cette
vérification. Le rapport est privé et écrit hors Git.

## Déclarer les contrôles

Par défaut, le contrat est `.github/clawfedora-doc-contract.json`.
`--contract` permet de sélectionner un autre fichier du commit. Le
contrat contient `schema: 1` et un tableau `checks`.

- Une règle `version` donne un identifiant `id`, une `authority` et une
  liste de `declarations`. Chaque sélecteur contient `path`, `format` et
  `select`. Pour `json`, `toml` et `yaml`, la liste `select` contient
  les clés imbriquées. `text` lit la version du fichier entier et utilise
  une liste vide. `markdown_table` lit la première valeur en code de la
  deuxième colonne. Le sélecteur indique le titre de section et le
  libellé de la première colonne.
- Une règle `path` indique `id`, `document` et `target`. Elle vérifie
  que le chemin technique versionné est cité au début d'un fragment de
  code en ligne ou d'une commande dans un bloc shell. Les exemples sont
  lus comme du texte.

Le contrat ClawFedora vérifie les versions de la plateforme, d'OpenClaw,
du plugin Parallel et d'Ollama, ainsi que les références au lanceur
dans le README, la procédure d'installation et la recette. Les
comparaisons de version sont littérales. Les sélecteurs visent les
déclarations actives et laissent les archives hors de la comparaison.

Une version divergente ou un fichier manquant produit un constat.
Une déclaration absente ou ambiguë reste à vérifier. La commande
renvoie `0` si tous les contrôles concordent, `1` si le rapport
contient des écarts ou des contrôles à revoir et `2` pour un refus.
Les valeurs déclarées ne prouvent pas les versions installées.
