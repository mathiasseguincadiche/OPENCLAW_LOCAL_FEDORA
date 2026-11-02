# Revue des dépendances npm — 2 novembre 2026 (A01)

[← Audit du 27 octobre](../../AUDIT_SOURCE_2026_10_27.md) · [État](../../../STATUS.md)

Les résultats bruts sont dans ce dossier. Ils ont été produits par `npm audit --package-lock-only` sur le verrou, **sans rien installer ni exécuter**.

| Verrou | Élevées | Modérées | Total | Résultat brut |
| --- | --- | --- | --- | --- |
| Avant : OpenClaw 2026.10.4 | 6 | 35 | 41 | [npm-audit-avant-2026.10.4.json](npm-audit-avant-2026.10.4.json) |
| Après : OpenClaw 2026.10.9 + 3 correctifs imposés | **1** | 35 | 36 | [npm-audit.json](npm-audit.json) |

Le 27 octobre, l'audit relevait 10 entrées. Le 2 novembre, le même verrou en relève 41 : de nouveaux avis ont été publiés entre-temps, surtout sur les dépendances embarquées par `npm`. Un audit reste un instantané à refaire régulièrement.

## Ce qui a été changé

- **OpenClaw et le plugin Parallel passent de 2026.10.4 à 2026.10.9.** C'est la dernière version stable au 2 novembre. Elle retire les alertes élevées `@modelcontextprotocol/sdk` et `body-parser`.
- **Trois correctifs de même série sont imposés.** OpenClaw fige ses dépendances en versions exactes, même en 2026.10.9. Le bloc `overrides` de `config/npm-runtime/package.json` les remplace par des correctifs de la même série :

  | Paquet | Figé par OpenClaw | Imposé | Avis corrigés (exemples) |
  | --- | --- | --- | --- |
  | `undici` | 8.11.2 | 8.12.3 | GHSA-rfgv-xxqx-mfg5, GHSA-2m5v-pch6-74hx, GHSA-4w7w-5xrc-9h26 |
  | `zod` | 4.6.5 | 4.6.7 | GHSA-mrhx-c7xc-m3w5 |
  | `npm` | 12.2.0 | 12.2.1 | dépendances embarquées `brace-expansion`, `postcss-selector-parser` |

- **Les correctifs imposés sont contrôlés.** Ils sont déclarés une seule fois dans `config/runtime_versions.yaml` (`npm_security_overrides`). `check_dependency_artifact_locks.py` refuse tout correctif non déclaré, une plage de versions, ou un correctif qui n'apparaît pas dans le verrou.
- **Node.js : OpenClaw 2026.10.9 exige Node ≥ 24.22.1** (contre ≥ 24.16.0 pour 2026.10.4). Le job CI `fedora-45-contract` installe le `nodejs` de Fedora 45 et rejoue le même `npm ci --engine-strict` que l'installateur. Si cette étape échoue, la version de Node de Fedora 45 est trop ancienne. Repli qualifié dans ce cas : OpenClaw 2026.10.5 avec les mêmes correctifs (même résultat d'audit, Node ≥ 24.16.0).

## Ce qui reste, et pourquoi

| Entrée | Niveau | Copie concernée | Pourquoi elle n'est pas corrigée | Exposition dans l'atelier |
| --- | --- | --- | --- | --- |
| `undici` 6.29.0 | Élevé | Embarquée dans `npm` 12.2.1 | Le correctif est en 6.29.1, mais aucune version publiée de `npm` ne l'embarque encore. Une copie embarquée ne peut pas être remplacée par `overrides`. | Elle ne sert que quand OpenClaw utilise npm (installation de plugins). Ces installations ont lieu à la configuration, sur des versions figées, avec mises à jour automatiques désactivées. Aucune exploitation n'a été démontrée, et l'absence d'exposition non plus. |
| `minimatch` 10.2.6 | Modéré | Dépendance directe d'OpenClaw | Le correctif est en 11.0.1, une version majeure : le risque de régression n'a pas été qualifié. | Déni de service par motifs glob. Les motifs viennent de la configuration et des outils locaux, pas du réseau. |
| `glob`, `minimatch`, `ip-address`… | Modéré | Embarquées dans `npm` 12.2.1 | Même raison que `undici` embarqué. | Même périmètre que `npm`. |
| `openclaw`, `@openclaw/parallel-plugin`, `@npmcli/*`, `libnpm*`… | Modéré | Agrégats | Ces entrées héritent des avis ci-dessus ; ce ne sont pas des failles distinctes. | — |

## À refaire

- Relancer `npm audit --package-lock-only` dans `config/npm-runtime` à chaque nouvelle version d'OpenClaw ou de `npm`. Retirer un `override` dès qu'OpenClaw fige lui-même une version corrigée.
- Surveiller `npm` 12.2.2 ou plus (correctif embarqué de `undici` 6.29.1), puis le passage d'OpenClaw à `minimatch` 11.
- Une CI verte prouve que le schéma, les outils, les limites de prompt et la route cloud acceptent la nouvelle version. **Elle ne prouve pas son fonctionnement sur le PC** : la réception sur Fedora reste à faire.
