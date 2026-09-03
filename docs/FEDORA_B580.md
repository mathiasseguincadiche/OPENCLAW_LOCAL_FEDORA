# Fedora 44 + Intel Arc B580

## Références de pile au 2026-09-03

Ces versions sont des **références observées**, pas des pins éternels. La qualification doit toujours enregistrer les versions réellement installées.

- Fedora 44 : GNOME 50.
- Kernel Fedora 44 stable observé : 7.1.12-200.fc44.
- Linux upstream stable : 7.2.3, publié le 2026-09-02.
- Mesa Vulkan Fedora 44 updates : 26.1.8.
- intel-compute-runtime Fedora 44 updates : 26.22.38646.6.
- intel-level-zero Fedora 44 updates : 26.22.38646.6.

Sources :

- https://www.kernel.org/
- https://packages.fedoraproject.org/pkgs/kernel/kernel-devel-matched/fedora-44-updates.html
- https://packages.fedoraproject.org/pkgs/mesa/mesa-vulkan-drivers/fedora-44-updates.html
- https://packages.fedoraproject.org/pkgs/intel-compute-runtime/intel-compute-runtime/fedora-44-updates.html
- https://packages.fedoraproject.org/pkgs/intel-compute-runtime/intel-level-zero/fedora-44-updates.html

## Baseline Vulkan

Le premier gate Fedora est Vulkan/Mesa. Il doit fonctionner avant d'ajouter SYCL/oneAPI.

Contrôles minimum :

```bash
lspci -Dnn
lsmod | grep '^xe '
ls -l /dev/dri
vulkaninfo --summary
rpm -q mesa-vulkan-drivers intel-compute-runtime intel-level-zero
clinfo -l
```

Le compte utilisateur doit disposer des droits appropriés sur le render node. Le bootstrap ajoute les groupes `render` et `video` lorsqu'ils existent ; une reconnexion de session est nécessaire après modification de groupe.

## SYCL / Level Zero

llama.cpp documente l'Intel Arc B580 comme device vérifié pour son backend SYCL. Le backend reste néanmoins un **candidat** dans ce projet :

- sa présence n'est pas nécessaire au premier bootstrap ;
- `sycl-ls` doit exposer un GPU Level Zero avant benchmark ;
- la version exacte oneAPI/llama.cpp doit être verrouillée avant comparaison ;
- Vulkan reste le rollback local.

Source : https://github.com/ggml-org/llama.cpp/blob/master/docs/backend/SYCL.md

## ReBAR

Resizable BAR est un prérequis de la cible matérielle. Le gate GPU tente de l'observer via `lspci -vv`. Si les informations PCI étendues ne sont pas lisibles sans privilèges, le résultat reste WARN et doit être confirmé dans le firmware/BIOS et par une lecture privilégiée.

## Mesures à enregistrer

Pour chaque backend et chaque kernel :

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
