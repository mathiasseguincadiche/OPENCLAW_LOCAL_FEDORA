# Architecture hybride historique — remplacée par le mode local

> **Archive de conception — ancien fonctionnement.** Cette page représentait la stratégie DeepSeek/Sol via OpenRouter. Depuis la migration Qwen + Ornith, elle n'est plus la politique d'exécution de l'atelier.

La référence actuelle est **[Architecture locale Qwen 3.5 9B + Ornith 1.5 9B](ARCHITECTURE_LOCALE_QWEN_ORNITH.md)**.

Les sept agents restent en place. Qwen assure six rôles d'analyse, recherche, pédagogie et audit ; Ornith est affecté à l'ingénieur DevOps. OpenRouter et ses modèles cloud sont retirés de la configuration active, sans repli automatique.

Pour retrouver le détail de l'ancienne architecture et ses décisions, consulter l'historique Git de ce fichier avant la PR #240. Aucun guide présent ici ne doit être utilisé pour activer une passerelle cloud.
