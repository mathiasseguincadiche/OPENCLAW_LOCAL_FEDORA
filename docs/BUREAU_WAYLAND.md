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


## Lire les capacités du portail

Dans une session Wayland, exécutez la sonde depuis un terminal de cette
même session.

~~~bash
clawfedora desktop-portal
~~~

La sonde interroge le propriétaire D-Bus déjà actif du portail sur le bus
utilisateur. Elle lit les versions de ScreenCast et RemoteDesktop, les
sources annoncées pour la capture de fenêtres et les périphériques
annoncés pour le pointeur. Elle désactive l'activation automatique et
l'autorisation interactive sur ses appels de lecture.

`PROBED` indique que les deux interfaces ont répondu. Un champ de capacité
à `null` indique une donnée indisponible ou non vérifiable. Le champ
`eis_api_in_version` indique si la version annoncée de RemoteDesktop
comprend l'API EIS. Le résultat conserve `qualification: PENDING`.
La recette CI utilise des réponses D-Bus simulées. La fenêtre réelle, le
dialogue de consentement et le flux PipeWire feront partie de C12.


## Vérifier la simulation à partir du portail

~~~bash
clawfedora desktop-rehearsal --mode pointer --require-portal
~~~

Le mode observation demande la capacité de capture de fenêtre. Le mode
pointeur demande aussi le périphérique pointeur et une version qui annonce
l'API EIS. Le contrôle porte sur les capacités publiées par le portail.
Une fois ce contrôle passé, les actions de la recette utilisent la fenêtre
fictive et le résultat conserve la portée `SYNTHETIC_NO_COMPOSITOR`.

Le job qualité publie `desktop-c06-synthetic`, un rapport associé au SHA
Git testé. Il couvre l'observation, le refus du pointeur ou d'une version
sans API EIS, l'action approuvée et la fermeture de la session par un
événement simulé du portail. La qualification GNOME reste en C12.
