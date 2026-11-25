# Préparer l'image OCI des validateurs

**Statut :** recette de construction disponible ; image réelle non construite
et non qualifiée. Ce guide est réservé à l'opérateur, après installation Fedora.
Il n'ajoute ni agent, ni registre, ni téléchargement au runtime.

## 1. Préparer les entrées vérifiées

Choisir une base OCI Linux AMD64 (Fedora/Rocky compatible avec les outils),
déjà chargée dans Podman rootless par digest de registre complet.
Elle doit fournir Python 3, venv/pip, un shell POSIX, git et les bibliothèques
requises par les outils retenus. Enregistrer provenance, versions, digest,
licences, signatures ou checksums officiels et scan de vulnérabilités.
Un manifest local ne remplace pas la vérification des sources officielles.

Préparer un répertoire privé **extérieur au dépôt**, contenant uniquement :

| Chemin | Contenu |
| --- | --- |
| bin/ | terraform, shellcheck, actionlint, hadolint, kubeconform |
| wheels/ | Wheels Python compatibles avec la base, dépendances transitives incluses |
| requirements.lock | Versions exactes et hashes pip de ansible-lint, pytest et dépendances |
| terraform-providers/ | Miroir de providers, dont libvirt si requis, avec versions verrouillées |
| schemas/ | Schémas Kubernetes stricts hors ligne pour la version cible |
| sources.md | Versions, sources officielles, digests et résultat de revue |
| manifest.json | Objet JSON chemin relatif vers SHA-256 de chaque autre fichier |

Les binaires sont les exécutables Linux AMD64 vérifiés, pas des archives.
Le miroir Terraform doit utiliser la disposition attendue par Terraform ;
le verrou du projet doit correspondre aux providers et à la plateforme.
Pour Kubeconform, voir la [documentation officielle](https://github.com/yannh/kubeconform#overriding-schemas-location) :
le dossier local suit la structure du catalogue. Le runner utilise actuellement
le défaut de version Kubeconform ; fournir le dossier strict correspondant
et vérifier sa correspondance avec le K3s cible avant de conclure.
Ne pas créer de schémas permissifs pour obtenir artificiellement PASS.
Aucun artefact réel ni version de provider n'est fourni par ce dépôt.

Une fois les sources et leur contenu vérifiés, générer le manifest depuis
le dossier des ressources (ne pas y mettre de secrets) :

```bash
python3 - /chemin/prive/validator-payload <<'PY'
import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
manifest = {}
for path in sorted(root.rglob("*")):
    if path.is_symlink():
        raise SystemExit(f"Lien interdit : {path}")
    if path.is_file() and path != root / "manifest.json":
        with path.open("rb") as stream:
            manifest[path.relative_to(root).as_posix()] = hashlib.file_digest(
                stream, "sha256"
            ).hexdigest()
(root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
PY
```

## 2. Vérifier puis construire sans réseau

Depuis le dépôt, venv actif, renseigner le vrai digest de la base locale
et le chemin des ressources. Le premier appel est un plan sans Podman :

```bash
python -m clawfedora.validator_image \
  --base "$VALIDATOR_BASE" --payload "$VALIDATOR_PAYLOAD"

python -m clawfedora.validator_image \
  --base "$VALIDATOR_BASE" --payload "$VALIDATOR_PAYLOAD" --apply
```

La construction utilise le [Containerfile](../containers/validators/Containerfile)
et Podman avec `--pull=never --network=none`. Les entrées sont revérifiées
dans un contexte temporaire. Les checks de versions au build contrôlent
la présence des outils ; ils ne prouvent ni leur qualité ni leur compatibilité.
Le statut `BUILT_NOT_QUALIFIED` renvoie l'identifiant local complet
`sha256:...` (identité de configuration OCI, distincte du digest de manifeste
d'un registre). Il n'y a ni push, ni tag flottant, ni approbation automatique.

## 3. Qualifier avant approbation

Conserver le JSON de construction et le manifest ; contrôler l'image avec
un scan local disposant de données de vulnérabilités à jour.
La campagne synthétique intégrée prépare seize cas, un positif et un négatif
par validateur, sans données réelles ni téléchargement :

```bash
python -m clawfedora.validator_acceptance
# Sur Fedora, avec l'image locale déjà construite :
python -m clawfedora.validator_acceptance --image "$VALIDATOR_IMAGE" --apply
```

Le plan ne lance aucun conteneur. Le rapport réel conserve les codes de retour
et les logs bornés. Un échec attendu impose la relecture du diagnostic :
un défaut de dépendance n'est pas une détection correcte du code invalide.
Même `SMOKE_REVIEW_REQUIRED` ne signifie ni image qualifiée ni approuvée.
Terraform synthétique est sans provider ; compléter impérativement avec
le provider libvirt et les collections Ansible de la vraie cible.
Sur le PC Fedora, utiliser aussi :

```bash
clawfedora-lab --project "$FIXTURE" --tool terraform-validate \
  --image "$VALIDATOR_IMAGE" --apply
```

Répéter pour les huit validateurs, sur des fixtures adaptées à chaque outil :
un cas valide puis un cas volontairement invalide. Tester notamment un
module libvirt avec son vrai verrou, un playbook et ses collections,
un workflow, un Dockerfile, un manifeste K3s et un test Python.
Conserver image, versions, commandes, sorties et codes de retour.
Un échec d'init ou de schéma manquant bloque la qualification ; ne pas
le masquer en changeant les tests. Ansible idempotent, apply Terraform
et déploiement réel restent des recettes distinctes.

Seulement après revue humaine, approuver l'identifiant exact :

```bash
python -m clawfedora.devops_sandbox --runtime "$RUNTIME" \
  --image "$VALIDATOR_IMAGE" --apply
```

Une image reconstruite reçoit sa propre identité et demande une nouvelle
revue et approbation. Le runtime ne tire jamais d'image automatiquement.
Voir [boucle Ornith](BOUCLE_ORNITH_EDIT_TEST.md) et
[recette globale](RECETTE_GLOBALE.md).
