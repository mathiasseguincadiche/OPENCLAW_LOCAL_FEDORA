# Revue des dépendances npm — 2 novembre 2026 (A01)

[← Audit du 27 octobre](../../AUDIT_SOURCE_2026_10_27.md) · [État](../../../STATUS.md)

Les résultats bruts sont dans ce dossier. Ils ont été produits par `npm audit --package-lock-only` sur le verrou, **sans rien installer ni exécuter**.

| Verrou | Élevées | Modérées | Total | Résultat brut |
| --- | --- | --- | --- | --- |
| Avant : OpenClaw 2026.10.4 | 6 | 35 | 41 | [npm-audit-avant-2026.10.4.json](npm-audit-avant-2026.10.4.json) |
| Après : OpenClaw 2026.10.5 + 3 correctifs imposés | **1** | 35 | 36 | [npm-audit.json](npm-audit.json) |

Le 27 octobre, l'audit relevait 10 entrées. Le 2 novembre, le même verrou en relève 41 : de nouveaux avis ont été publiés entre-temps, surtout sur les dépendances embarquées par `npm`. Un audit reste un instantané à refaire régulièrement.

## Ce qui a été changé

- **OpenClaw et le plugin Parallel passent de 2026.10.4 à 2026.10.5.** Cette version retire les alertes élevées `@modelcontextprotocol/sdk` et `body-parser`.
- **Pourquoi pas 2026.10.9, la dernière version stable ?** À partir de 2026.10.6, OpenClaw exige Node ≥ 24.22.1 ou ≥ 26.12.1. Fedora 45 n'en fournit aucune : un essai dans le conteneur Fedora 45 de la CI le confirme.

  | Paquet Fedora 45 | Version | OpenClaw 2026.10.4 / 10.5 (≥ 24.16.0 ou ≥ 26.1.0) | OpenClaw 2026.10.6 à 10.9 (≥ 24.22.1 ou ≥ 26.12.1) |
  | --- | --- | --- | --- |
  | `nodejs` (défaut) | 22.23.1 | refusé | refusé |
  | `nodejs24` | 24.18.0 | accepté | refusé |
  | `nodejs26` | 26.3.1 | accepté | refusé |

  OpenClaw 2026.10.9 donne le même résultat d'audit (1 alerte élevée) une fois les mêmes correctifs imposés : rester en 2026.10.5 ne coûte donc aucune protection mesurée.
- **Défaut d'installation découvert et corrigé.** `00_bootstrap.sh` installait `nodejs`, c'est-à-dire Node **22** sur Fedora 45, alors que même OpenClaw 2026.10.4 exige Node ≥ 24.16.0. Le `npm ci --engine-strict` de l'installateur aurait donc échoué dès la première installation. Le script installe désormais `nodejs24`, et ses commandes `node`/`npm` sans suffixe. `check_node_engine.py` vérifie la version avant `npm ci` et donne un message clair.
- **Trois correctifs de même série sont imposés.** OpenClaw fige ses dépendances en versions exactes. Le bloc `overrides` de `config/npm-runtime/package.json` les remplace par des correctifs de la même série :

  | Paquet | Figé par OpenClaw | Imposé | Avis corrigés (exemples) |
  | --- | --- | --- | --- |
  | `undici` | 8.11.2 | 8.12.3 | GHSA-rfgv-xxqx-mfg5, GHSA-2m5v-pch6-74hx, GHSA-4w7w-5xrc-9h26 |
  | `zod` | 4.6.5 | 4.6.7 | GHSA-mrhx-c7xc-m3w5 |
  | `npm` | 12.2.0 | 12.2.1 | dépendances embarquées `brace-expansion`, `postcss-selector-parser` |

- **Les correctifs imposés sont contrôlés.** Ils sont déclarés une seule fois dans `config/runtime_versions.yaml` (`npm_security_overrides`). `check_dependency_artifact_locks.py` refuse tout correctif non déclaré, une plage de versions, ou un correctif absent du verrou.
- **CI alignée sur le PC.** `fedora-45-contract` installe le même Node que l'installateur, puis rejoue `npm ci --engine-strict` et `openclaw --version`. `native-openclaw` utilise Node 24.18.0, la version de Fedora 45.

## Ce qui reste, et pourquoi

| Entrée | Niveau | Copie concernée | Pourquoi elle n'est pas corrigée | Exposition dans l'atelier |
| --- | --- | --- | --- | --- |
| `undici` 6.29.0 | Élevé | Embarquée dans `npm` 12.2.1 | Le correctif est en 6.29.1, mais aucune version publiée de `npm` ne l'embarque encore. Une copie embarquée ne peut pas être remplacée par `overrides`. | Elle ne sert que quand OpenClaw utilise npm (installation de plugins). Ces installations ont lieu à la configuration, sur des versions figées, avec mises à jour automatiques désactivées. Aucune exploitation n'a été démontrée, et l'absence d'exposition non plus. |
| `minimatch` 10.2.6 | Modéré | Dépendance directe d'OpenClaw | Le correctif est en 11.0.1, une version majeure : le risque de régression n'a pas été qualifié. | Déni de service par motifs glob. Les motifs viennent de la configuration et des outils locaux, pas du réseau. |
| `glob`, `minimatch`, `ip-address`… | Modéré | Embarquées dans `npm` 12.2.1 | Même raison que `undici` embarqué. | Même périmètre que `npm`. |
| `openclaw`, `@openclaw/parallel-plugin`, `@npmcli/*`, `libnpm*`… | Modéré | Agrégats | Ces entrées héritent des avis ci-dessus ; ce ne sont pas des failles distinctes. | — |

## À refaire

- Le workflow hebdomadaire `Dependency Audit` relance `npm audit` et `pip-audit` sur les verrous. Les trois avis `undici` ci-dessus sont des exceptions revues jusqu'au 1er février 2027 (`config/dependency_audit_exceptions.json`) ; tout autre avis élevé ou critique fait échouer le contrôle. Retirer un `override` ou une exception dès que la version corrigée est disponible.
- Surveiller `npm` 12.2.2 ou plus (correctif embarqué de `undici` 6.29.1), le passage d'OpenClaw à `minimatch` 11, et l'arrivée de Node ≥ 24.22.1 dans Fedora 45, condition pour monter OpenClaw au-delà de 2026.10.5.
- Une CI verte prouve que le schéma, les outils, les limites de prompt et la route cloud acceptent la nouvelle version. **Elle ne prouve pas son fonctionnement sur le PC** : la réception sur Fedora reste à faire.
