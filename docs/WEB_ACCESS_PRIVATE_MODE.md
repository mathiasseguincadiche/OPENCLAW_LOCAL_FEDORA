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

## Préparer le mode privé

Après installation native et sur le compte utilisateur propriétaire du runtime :

\`\`\`bash
clawfedora-ops web-access status
clawfedora-ops web-access private
clawfedora-ops web-access private --apply
\`\`\`

La dernière commande écrit **uniquement le choix voulu** dans
\`state/web-access/private.enabled\` avec permissions \`0600\`, et annonce
\`GATEWAY_APPLIED=NOT_VERIFIED\`. Tant que le correctif de configuration n'est
pas appliqué et que le Gateway n'est pas redémarré, le mode privé ne peut pas
être considéré comme effectif.

Ensuite, sur le vrai Fedora et après avoir vérifié qu'aucun projet ne tourne :

\`\`\`bash
bash scripts/linux/03_configure_openclaw.sh --apply
systemctl --user restart openclaw-gateway.service
clawfedora-ops web-access status
\`\`\`

Vérifier également **dans la configuration effective** les deux propriétés :
\`tools.web.search.enabled=false\` et \`tools.web.fetch.enabled=false\`,
les outils \`web_search\` et \`web_fetch\` dans \`tools.deny\`, et leur absence
des \`alsoAllow\` des sept agents. Ne jamais déclarer \`MODE_PRIVÉ_ACTIF\`
avant cette inspection. Ne pas afficher ou publier le contenu complet de
\`openclaw.json\` : il peut contenir des informations sensibles.

## Repasser au mode connecté

Le retour est **explicite**, et ne se fait pas automatiquement à l'occasion
d'une mise à jour :

\`\`\`bash
clawfedora-ops web-access connected --apply
bash scripts/linux/03_configure_openclaw.sh --apply
systemctl --user restart openclaw-gateway.service
\`\`\`

Le même contrôle de la configuration effective est nécessaire, cette fois
avec \`web_search\`/\`web_fetch\` autorisés selon le contrat versionné.
La recherche Web peut quitter l'ordinateur, même quand le modèle reste local.

## Limites de preuve

Les tests GitHub vérifient le rendu de la configuration et le verrou d'accès,
pas la véritable absence de trafic réseau du PC. Une inspection de la
configuration active, un essai d'appel Web refusé et un contrôle réseau sur
le Fedora natif restent nécessaires avant qualification de production.
