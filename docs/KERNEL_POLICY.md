# Politique kernel

## Repères de lecture

| Repère | Valeur |
|---|---|
| **Public cible** | Mainteneurs, opérateurs avancés et responsables de qualification L6. |
| **Niveau** | Expert |
| **Prérequis** | Baseline Fedora fonctionnelle, kernel Fedora bootable conservé et compréhension des gates L3/L6. |
| **Objectif** | Comprendre quand et comment comparer le kernel Fedora officiel au candidat upstream sans confondre nouveauté et amélioration. |
| **Résultat attendu** | Savoir préparer K0/K1, appliquer les seuils de promotion et préserver un rollback bootable. |
| **Critère d’arrêt** | Ne pas tester le candidat si la baseline Fedora n'est pas saine ou si aucun kernel Fedora fonctionnel n'est conservé. |
| **À lire ensuite** | [`QUALIFICATION.md`](QUALIFICATION.md) pour le protocole L6 et [`UPGRADE.md`](UPGRADE.md) pour un changement contrôlé. |
| **Source de vérité** | `config/kernel_policy.yaml`, `config/optimization_policy.yaml` et les preuves L6 produites sur la machine cible. |

## Pourquoi deux kernels

Le projet vise les performances, mais refuse de confondre nouveauté et amélioration. Le kernel Fedora officiel reste donc la référence supportée et la voie de rollback. Linux 7.2.3 est un candidat séparé.

Au 2026-09-03 :

- kernel.org publie Linux 7.2.3 comme stable (2026-09-02) ;
- Fedora 44 publie encore 7.1.12-200.fc44 comme référence stable observée.

## Interdictions

- ne jamais supprimer le dernier kernel Fedora bootable ;
- ne jamais installer le candidat depuis le bootstrap de base ;
- ne jamais changer simultanément kernel + modèle + quantification + runtime lors d'une comparaison ;
- ne jamais promouvoir automatiquement 7.2.3.

## Protocole

### K0 — Fedora officiel

1. boot ;
2. GNOME 50/Wayland ;
3. B580/xe ;
4. Mesa/Vulkan ;
5. OpenClaw ;
6. E2E ;
7. HARD-40M ;
8. 3 runs de stabilité.

### K1 — Linux 7.2.3

Installer en parallèle puis rejouer **exactement** K0.

### Promotion

Le candidat doit :

- passer tous les gates fonctionnels et sécurité ;
- améliorer l'agrégat d'au moins 3 % par rapport au kernel Fedora ;
- ne dégrader aucun modèle de plus de 2 % ;
- passer au moins 3 runs stables.

Si ces critères ne sont pas remplis, le kernel Fedora reste nominal, même si 7.2.3 est plus récent.
