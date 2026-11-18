# Dérogation temporaire pour picomatch

L’audit npm de la PR #192 signale [GHSA-fc5q-39xc-vjpf](https://github.com/advisories/GHSA-fc5q-39xc-vjpf), un avis de sévérité élevée. Au 17 novembre 2026, l’avis couvre les versions de picomatch jusqu’à 4.0.7 et ne répertorie aucune version corrigée. L’archive npm 12.2.3 vérifiée embarque elle aussi picomatch 4.0.5.

La dérogation couvre uniquement picomatch **4.0.5** sous `node_modules/npm/node_modules/tinyglobby/node_modules/picomatch`, dans **npm 12.2.1**. L’audit vérifie que le rapport désigne cette seule copie et que le verrou confirme les deux versions et le statut embarqué. Un emplacement supplémentaire, une version différente ou une sévérité revue à la hausse fait échouer le contrôle.

L’installation de l’atelier utilise le verrou avec `npm ci --ignore-scripts`. Le plugin Parallel est ensuite lié depuis l’arborescence locale. Ces limites réduisent l’usage de npm dans le parcours documenté. La copie vulnérable reste présente et l’exposition des autres usages de npm n’a pas été qualifiée.

La dérogation expire le **17 décembre 2026 inclus**. Dès qu’une version corrigée est livrée dans npm, mettre à jour le verrou, relancer l’audit et retirer la dérogation. À l’échéance, l’audit échoue si l’avis est encore présent.
