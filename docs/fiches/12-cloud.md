# OpenRouter — route retirée de l'Atelier Fedora

> **Ne pas utiliser les anciennes commandes d'activation.** Cette page remplace l'ancien guide DeepSeek/OpenRouter du dépôt : le routage cloud n'est plus disponible.

L'atelier utilise dorénavant seulement Qwen 3.5 9B (six agents) et Ornith 1.5 9B (ingénieur DevOps) via Ollama local, avec des règles de permissions inchangées.

[Architecture locale complète](../ARCHITECTURE_LOCALE_QWEN_ORNITH.md) · [Sept agents](07-roles-et-outils.md).

## Retirer une ancienne configuration OpenRouter

Sur une installation Fedora **déjà gérée**, après une sauvegarde vérifiée :

```bash
./menu.sh --action local-retire-cloud
./menu.sh --action local-retire-cloud --apply
./menu.sh --action models --apply
./menu.sh --action configure-openclaw --apply
```

Le retrait arrête l'ancienne passerelle et retire les clés et l'activation du runtime géré, après contrôle des chemins. L'historique des dépenses est conservé. Cette opération ne résilie pas un abonnement externe, ne supprime pas automatiquement les crédits OpenRouter sur son site, et ne modifie pas les données personnelles GitHub/Notion.

## Ce que le local permet — et ses limites

**Zéro facturation API pour les inférences exécutées localement**, pas de garantie d'équivalence avec les meilleurs modèles cloud. Les performances et la mémoire réelle des deux modèles doivent être réceptionnées sur la B580. Les permissions système restent strictes, l'exécution autonome générale n'est pas encore activée.

L'historique Git conserve la description de l'ancien mode hybride. Les commandes `cloud-enable` et `cloud-set-key` ne font plus partie du menu actuel.
