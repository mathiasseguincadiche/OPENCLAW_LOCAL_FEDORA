# Fedora 44 + Intel Arc B580

## Références de pile au 2026-09-03

Ces versions sont des **références observées**, pas des pins éternels. La qualification doit toujours enregistrer les versions réellement installées.

- Fedora 44 : GNOME 50.
- Kernel Fedora 44 stable observé : 7.1.12-200.fc44.
- Linux upstream stable : 7.2.3, publié le 2026-09-02.
- Mesa Vulkan Fedora 44 updates : 26.1.8.

Sources :

- https://www.kernel.org/
- https://packages.fedoraproject.org/pkgs/kernel/kernel-devel-matched/fedora-44-updates.html
- https://packages.fedoraproject.org/pkgs/mesa/mesa-vulkan-drivers/fedora-44-updates.html

## Baseline GPU

La pile nominale est volontairement courte :

```text
Intel Arc B580
    ↓
module kernel xe
    ↓
DRM render node
    ↓
Mesa Vulkan
    ↓
Ollama Vulkan / llama.cpp Vulkan
```

Contrôles minimum :

```bash
lspci -Dnn
lsmod | grep '^xe '
ls -l /dev/dri
rpm -q mesa-vulkan-drivers
vulkaninfo --summary
```

Le compte utilisateur doit disposer des droits appropriés sur le render node. Le bootstrap ajoute les groupes `render` et `video` lorsqu'ils existent ; une reconnexion de session est nécessaire après modification de groupe.

## Candidat SYCL/Level Zero

SYCL/Level Zero est traité comme un **candidat Linux de performance**, pas comme une dépendance de base. Il est installé et mesuré dans une campagne séparée après validation complète de la baseline Vulkan.

Règles :

- il ne bloque jamais le bootstrap initial ;
- il ne bloque jamais le gate matériel Vulkan ;
- sa pile et ses versions doivent être enregistrées exactement lorsqu'il est activé ;
- il doit battre la baseline sur des mesures comparables pour être retenu ;
- Vulkan reste disponible comme chemin local de repli.

## ReBAR

Resizable BAR est un prérequis de la cible matérielle. Le gate GPU tente de l'observer via `lspci -vv`. Si les informations PCI étendues ne sont pas lisibles sans privilèges, le résultat reste WARN et doit être confirmé dans le firmware et par une lecture privilégiée.

## Mesures à enregistrer

Pour chaque runtime et chaque kernel :

- first token ;
- TTFT réponse ;
- prompt tokens/s ;
- génération tokens/s ;
- VRAM ;
- RAM ;
- temps de chargement ;
- temps de switch modèle ;
- puissance GPU si disponible ;
- erreurs ;
- stabilité ;
- tool calling.

Aucun résultat ne doit être comparé si le modèle, la quantification, le contexte ou le prompt diffèrent.
