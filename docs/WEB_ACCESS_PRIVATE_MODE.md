# Recherche Web privée ou connectée

Les sept agents utilisent **Qwen local** pour le raisonnement, mais la recherche
\`web_search\` (fournisseur Parallel) et la consultation \`web_fetch\`
peuvent envoyer des requêtes et des URLs à des services externes.

Deux états de configuration sont disponibles :

| État | Accès Web natif des agents | Inférence Qwen locale |
| --- | --- | --- |
| \`connected\` (état historique) | Autorisé selon la politique versionnée | Oui |
| \`private\` (activation explicite) | Refusé pour les sept agents, globalement ET individuellement | Oui |

Le mode privé **désactive uniquement les outils Web d'OpenClaw**. Il ne constitue
pas une coupure réseau système et **ne désactive pas à lui seul la route DeepSeek
cloud**, laquelle reste soumise à l'activation de la passerelle et au consentement
spécifique du projet. Pour empêcher toute sortie Internet, utiliser en complément
des règles réseau système adaptées et révoquer les accords cloud concernés.

## Passer en mode privé : une commande contrôlée

Sur Fedora 45 installé, avec le disque secondaire **monté sur `/data`** et aucun projet en cours :

```bash
./menu.sh --action web-private             # aperçu, ne change rien
./menu.sh --action web-private --apply     # verrou + arrêt Gateway + patch + vérification + redémarrage
./menu.sh --action web-status              # mode souhaité, sans preuve réseau
```

**Le basculement avec `--apply` est fail-closed** : le script refuse un runtime non géré, verrouille le worker, arrête le Gateway **avant** de changer le mode voulu, réapplique le contrat natif, vérifie le fichier `openclaw.json` (outils Web désactivés globalement et pour les sept rôles), puis redémarre et confirme que le Gateway est actif. Un échec intermédiaire **laisse le Gateway arrêté** ; consulter les journaux, corriger le problème, puis relancer la commande. Seul `WEB_ACCESS_RESULT=PASS` confirme la réussite de cette procédure.

`web-status` retourne toujours l'état **souhaité**, pas une certification du service actif ni du trafic. Le contrôle de fichier est une preuve de **configuration enregistrée**, pas une preuve d'absence d'egress réseau. Le cloud DeepSeek demeure un réglage distinct ; révoquer les accords cloud si une absence totale de sortie est nécessaire.

## Repasser explicitement au mode connecté

```bash
./menu.sh --action web-connected             # aperçu
./menu.sh --action web-connected --apply     # réactivation volontaire vérifiée
```

La même séquence de sécurité s'applique. Le retour au mode Web connecté n'est **jamais automatique** lors d'une mise à jour ou d'un redémarrage. Des recherches peuvent alors quitter le PC même lorsque le modèle d'inférence choisi est Qwen local.

## Procédure avancée en cas de panne

`clawfedora-ops web-access private|connected --apply` ne fait que **préparer le marqueur** ; son message `GATEWAY_APPLIED=NOT_VERIFIED` signifie que la configuration du Gateway n'est pas encore appliquée. Préférer le menu ci-dessus, qui regroupe vérification et redémarrage. Ne jamais publier le contenu de `openclaw.json` ou une capture qui contiendrait des secrets.

## Limites de preuve

Les tests GitHub vérifient le rendu de la configuration et le verrou d'accès,
pas la véritable absence de trafic réseau du PC. Une inspection de la
configuration active, un essai d'appel Web refusé et un contrôle réseau sur
le Fedora natif restent nécessaires avant qualification de production.
