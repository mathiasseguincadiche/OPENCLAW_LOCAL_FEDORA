# Vérifier l'application des corrections documentaires — C02, lot 7

Après fusion, relever le SHA complet à vérifier dans `main`. Conserver
la [revue approuvée](GITHUB_DOCUMENTARY_CORRECTIONS.md), son
`report_sha256` relevé lors de l'approbation, l'inventaire GitHub de base
et les rapports d'audit utilisés dans la revue. Produire un
[nouvel inventaire GitHub](GITHUB_DOCUMENTARY_INVENTORY.md) sur le SHA
à vérifier, puis relancer les audits concernés sur ce même SHA.

```bash
python -m clawfedora.github_document_verification \
  --repo PROPRIETAIRE/DEPOT --commit SHA_APRES_FUSION \
  --review "$DOSSIER_PRIVE/revue-corrections.json" \
  --review-sha256 EMPREINTE_APPROUVEE \
  --before-inventory "$DOSSIER_PRIVE/inventaire-base.json" \
  --after-inventory "$DOSSIER_PRIVE/inventaire-apres.json" \
  --before-report "$DOSSIER_PRIVE/liens-base.json" \
  --after-report "$DOSSIER_PRIVE/liens-apres.json" \
  --output "$DOSSIER_PRIVE/verification.json"
```

Répéter `--before-report` pour chaque rapport utilisé dans la revue et
`--after-report` pour chaque nouvel audit de liens, cohérence ou CI.
Chaque inventaire et rapport doit être produit pour le même dépôt,
avec le SHA complet et l'empreinte d'inventaire de sa révision.

| Contrôle | Preuve attendue |
| --- | --- |
| Fichiers | Chaque chemin contient le blob approuvé sur le SHA contrôlé. |
| Liens | Les documents concernés ont été lus sur le même périmètre. Leur audit ne relève plus de lien en écart ou non vérifié. |
| Cohérence | Le blob du contrat est identique et la règle concernée est conforme. |
| Références CI | Les documents concernés ont été lus. Les références GitHub Actions relevées pointent vers des runs réussis sur le SHA contrôlé. Le retrait d'une référence non étayée peut aussi faire disparaître le constat. |
| Frontières | Les documents concernés ont été lus et aucun signal de diffusion n'y est relevé. Pour un passage dupliqué, les autres documents concernés doivent aussi avoir été lus. |

Pour un constat de frontière, utiliser les mêmes valeurs
`--boundary-scope CHEMIN` (répétable) ou `--boundary-public-tree` et la
même `--boundary-policy` privée que lors de l'audit d'origine. Le
vérificateur relance cet audit en lecture seule sur la base GitHub et
compare l'empreinte au rapport d'origine. Il effectue ensuite le même
audit sur le SHA contrôlé. Le fichier de politique reste local.
Les autres familles sont vérifiées hors ligne à partir des rapports.

Le rapport privé distingue la présence du blob approuvé de l'effet
constaté par l'audit. Un rapport absent, un périmètre différent ou une
lecture incomplète laisse le constat à vérifier. Examiner la formulation
des preuves, les liens historiques intentionnels et la pertinence
éditoriale lors de la revue humaine. Le contrôle porte sur le SHA fourni.
L'opérateur confirme la fusion et relève ce SHA dans GitHub.

La commande écrit un rapport neuf en mode `0600` hors Git. Elle
renvoie `0` lorsque les blobs et les constats sélectionnés sont
confirmés, `1` si la revue reste nécessaire et `2` si une entrée
ou la destination est refusée.
