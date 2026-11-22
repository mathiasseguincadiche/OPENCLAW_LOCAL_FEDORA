# Atelier unifié : conversations natives, OpenClaw et Ollama

## Architecture cible

Une **seule interface graphique** : \`http://127.0.0.1:18890\`.
Navigation interne : **Discussions · Projets · GitHub · Notion**.
L'interface utilise les sept agents OpenClaw avec le fournisseur local Ollama
déjà configuré. Ni LM Studio ni le conteneur Open WebUI ne sont nécessaires
aux **nouvelles conversations natives**.

Le dialogue passe par le même contrôleur d'admission et de validation que
l'ancien pont : \`webui_bridge.make_server\` est démarré en **mémoire** sur un
port loopback temporaire, avec un jeton éphémère jamais transmis au navigateur.
Ce module partage le moteur OpenClaw, mais ne démarre **aucun service WebUI**.
L'interface n'a pas accès à un shell et ne peut pas choisir arbitrairement
le modèle, le projet ou les messages précédents de l'historique.

## Installer / lancer sur Fedora 45

La chaîne d'installation complète appelle désormais automatiquement
\`scripts/linux/21_atelier.sh install --apply\` après l'installation d'OpenClaw.
Pour une installation existante, une fois le dépôt mis à jour :

~~~bash
./menu.sh --action atelier-install             # plan, sans changement
./menu.sh --action atelier-install --apply     # unité systemd utilisateur
./menu.sh --action atelier-status
~~~

Ouvrir ensuite \`http://127.0.0.1:18890/discussions.html\` depuis GNOME.
\`atelier-start\` et \`atelier-stop\` sont aussi disponibles.
L'installation exige un runtime géré, Fedora 45, SELinux Enforcing et
un environnement Python préinstallé ; elle ne télécharge aucun nouveau LLM.

Pour utiliser les discussions : sélectionner un projet existant (ou « Sans
projet ») et l'un des sept rôles, puis créer un fil. **L'identifiant projet
et le rôle sont figés** par conversation. Les messages \`!etat\`,
\`!sources\`, \`!planifier\`, etc. sont des commandes humaines traitées
par le pont existant, avec les mêmes validations explicites.

Le diagnostic \`!fedora etat\` consulte seulement des états de service
\`systemctl\` **sur liste fixe**, sans commande arbitraire ; il ne redémarre
rien, n'installe rien et ne modifie aucune application. Les opérations
d'administration (sudo, installation Flatpak/RPM, fichiers système,
clics sur applications GNOME/Wayland) **ne sont pas activées** par ce lot.

## Isolation, historique et incidents

- Les conversations natives sont conservées dans
  \`state/atelier-chats/<identifiant>.json\` du runtime géré, sous répertoire
  0700 et fichiers 0600, non suivis par Git.
- Les historiques de LM Studio / Open WebUI et CLI OpenClaw ne sont pas
  automatiquement importés : **ne pas désinstaller/purger avant sauvegarde,
  migration explicite et essai de restauration**.
- Changer de projet ou de rôle impose un nouveau fil. Les commandes
  \`!projet\` et \`!quitter\` ne peuvent pas contourner cette règle.
- Un appel en cours est enregistré **avant** le traitement ; s'il échoue
  ou si l'interface est fermée, le fil reste marqué « incertain » et
  ne peut pas être rejoué automatiquement. Vérifier les effets réels
  avant toute reprise dans un nouveau fil.
- Les réponses ne passent que par le moteur/politiques existants. Aucun
  outil généré par le modèle ne crée une approbation humaine.
- Le premier chemin natif est **local exclusivement** : pas de sélecteur
  cloud ni d'accord cloud implicite dans la nouvelle interface.
- **Limite de sécurité :** service HTTP de bouclage conçu pour une session
  personnelle locale, pas pour un port réseau exposé, un proxy public
  ou un ordinateur multiutilisateur non fiable.

## Réception avant retrait d'Open WebUI

1. Vérifier \`atelier-status\`, \`ollama.service\`, le Gateway, Fedora 45 et
   SELinux Enforcing sur le matériel réel.
2. Créer un fil par agent, puis deux projets isolés ; vérifier
   séparation des contextes, conservation après redémarrage et refus
   des changements de projet.
3. Exercer \`!fedora etat\`, \`!projets\`, \`!etat\` et une planification
   sur un projet de test, puis vérifier les journaux et les confirmations.
4. Vérifier refus d'approbation non humaine, d'action réessayée,
   d'historique altéré et des fichiers/symlinks interdits.
5. Tester le rendu GNOME bureau/mobile et la performance réelle Ollama
   avec l'Intel Arc B580 ; la CI seule ne prouve pas l'accélération GPU.
6. Exporter/sauvegarder les anciens fils Open WebUI et tester leur
   restauration ; seulement alors envisager son retrait, avec procédure
   de retour arrière.

**Statut : code pilote et tests de CI.** Aucun test sur le PC Fedora,
aucune automatisation universelle des applications et aucune suppression
WebUI ne sont déclarés terminés.
