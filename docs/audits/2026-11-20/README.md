# Audit de cohérence préinstallation — 20 novembre 2026

[← État du dépôt](../../../STATUS.md) · [Réception Fedora](../../RECEPTION_ETAPE3.md) · [FinOps](../../validation/FINOPS.md)

**Type :** audit ciblé du dépôt, pas recette matérielle ni certification des modèles.

**Référence :** branche main, commit `626d1f4cc54c2066ccaf86697d6ea246d96a4e3b`.
**Correctifs :** [PR #203](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/pull/203).

## Vérifications et anomalies corrigées

| Référence | Constat sur la base | Correction | Contrôle ajouté |
|---|---|---|---|
| A-01 — FinOps | Un appel direct à `Ledger.reserve` pouvait fournir des nombres de tokens invalides, un prix infini ou un identifiant de modèle absent des enveloppes. La passerelle normalisait déjà ses propres entrées ; la défense interne restait incomplète. | Refus avant écriture du journal, sans modifier les enveloppes 15/10/10 € ni les modèles. | `test_malformed_reservation_cannot_write_to_ledger` |
| A-02 — Choix du modèle | La commande statique `!modele` recommandait principalement Qwen/DeepSeek et traitait `audit` comme un incident CI. | Sol mentionné pour contre-expertise ; catégorie `audit` distincte ; accord cloud et absence de bascule locale rappelés. | `test_model_advice.py` |
| A-03 — Rôles | La fiche des sept agents décrivait deux moteurs, sans la sélection DeepSeek/Sol par rôle et étape. | Explication des trois modèles et tableau exact routine/escalade. | `test_documentation_navigation.py` |
| A-04 — Interface | Le libellé « budget DeepSeek » cachait la seconde enveloppe Sol. | Libellé « Budget cloud » et guides accordés. | Contrat de l'interface documentaire |
| A-05 — Schémas | Les vues SVG et sources Draw.io présentaient seulement la route DeepSeek. | Textes synchronisés avec DeepSeek routine/Sol expertise ; géométrie et styles conservés. | Parsing XML et comparaison de libellés SVG/Draw.io |
| A-06 — Référence technique | Les exemples de `PASSERELLE_CLOUD.md` et le catalogue de compatibilité suggéraient une unique route cloud. | Compatibilité de l'alias historique documentée, quatre alias automatiques distingués et version native épinglée explicitée. | Contrats existants de configuration et navigation |

Ces changements sont **préparatoires**. Ils ne démontrent pas que Sol est plus fiable
que DeepSeek, ni que la B580 fonctionne, ni qu'OpenRouter accepte un endpoint réel.

## Règles de sécurité préservées

- Cloud désactivé par défaut ; aucun passage automatique du local vers le cloud.
- Consentement explicite du projet et filtrage des messages et outils.
- Deux identifiants upstream approuvés, aucun troisième fournisseur.
- Enveloppes locales : 15 € DeepSeek, 10 € Sol, 10 € non routables ; limite fournisseur
  et prépaiement indispensables en plus du ledger.
- Aucune commande destructive ni installation sur le PC de l'utilisateur.

## À qualifier sur le vrai poste, sans anticipation

1. Fedora 45 / GNOME 51, UEFI, SELinux Enforcing, montage secondaire et pilote Arc `xe`.
2. Installation gérée, Ollama local, sept agents, OpenClaw et interface WebUI.
3. Route DeepSeek puis Sol sur données publiques, selon [la recette FinOps](../../validation/FINOPS.md),
   uniquement après activation volontaire et limites de crédits.
4. Précision du contexte et du cache, latence, coûts réconciliés, qualité et contre-expertise.
5. Projet de bout en bout, preuves d'audit, sauvegarde/restauration et reprise après redémarrage.

**Preuves CI :** consulter les trois contrôles associés à la PR #203 avant
fusion ; une branche `main` verte ne remplace jamais les étapes ci-dessus.
