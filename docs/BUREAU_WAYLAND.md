# Recette du consentement pour le bureau Fedora

La commande utilise une fenêtre synthétique et produit un résultat JSON.

~~~bash
clawfedora desktop-rehearsal --mode observe
clawfedora desktop-rehearsal --mode pointer
~~~

Le simulateur associe le consentement à une fenêtre et à un mode précis
pendant cinq minutes. Le mode `observe` donne accès à l'état de la fenêtre
fictive. Le mode `pointer` ouvre un volet fictif après approbation de
l'action et vérification de l'observation précédente. Le résultat
`SYNTHETIC_NO_COMPOSITOR` décrit les états avant et après.

Le changement de fenêtre, l'expiration, la révocation ou la limite
d'observations ferment la session. Les tests couvrent aussi les refus
avant consentement, l'utilisation d'une observation d'une autre session
et le rejeu d'une action.

## Préparation de l'intégration native

L'observation réelle utilisera les capacités annoncées par le portail
ScreenCast et la source choisie par l'opérateur. Le contrôle du pointeur
dépend de l'accord du portail RemoteDesktop et des périphériques qu'il
accorde. Le signal de fermeture du portail devra révoquer la session
locale. Les sélections, le flux PipeWire et la disponibilité d'EIS
feront partie de la qualification sur le poste Fedora dans C12.

- [Portail ScreenCast](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.ScreenCast.html)
- [Portail RemoteDesktop](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.RemoteDesktop.html)
