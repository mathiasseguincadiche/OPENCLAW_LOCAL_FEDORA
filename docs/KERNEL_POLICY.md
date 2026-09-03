# Politique kernel

## Pourquoi deux kernels

Le projet vise les performances, mais refuse de confondre nouveauté et amélioration. Le kernel Fedora officiel reste donc la référence supportée et la voie de rollback. Linux 7.2.3 est un candidat séparé.

Au 2026-09-03 :

- kernel.org publie Linux 7.2.3 comme stable (2026-09-02) ;
- Fedora 44 publie encore 7.1.12-200.fc44 comme référence stable observée.

## Interdictions

- ne jamais supprimer le dernier kernel Fedora bootable ;
- ne jamais installer le candidat depuis le bootstrap de base ;
- ne jamais changer simultanément kernel + modèle + quantification + backend lors d'une comparaison ;
- ne jamais promouvoir automatiquement 7.2.3.

## Protocole

### K0 — Fedora officiel

1. boot ;
2. GNOME 50/Wayland ;
3. B580/xe ;
4. Vulkan ;
5. Level Zero ;
6. OpenClaw ;
7. E2E ;
8. HARD-40M ;
9. 3 runs de stabilité.

### K1 — Linux 7.2.3

Installer en parallèle puis rejouer **exactement** K0.

### Promotion

Le candidat doit :

- passer tous les gates fonctionnels et sécurité ;
- améliorer l'agrégat d'au moins 3 % par rapport au kernel Fedora ;
- ne dégrader aucun modèle de plus de 2 % ;
- passer au moins 3 runs stables.

Si ces critères ne sont pas remplis, le kernel Fedora reste nominal, même si 7.2.3 est plus récent.
