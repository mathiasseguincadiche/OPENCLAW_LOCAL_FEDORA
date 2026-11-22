# Décision de modèles — Qwen 3.5 9B et Ornith 1.5 9B

**Décision active : deux modèles exécutés exclusivement par Ollama local.** L'ancienne stratégie OpenRouter/DeepSeek/GPT-6.2 Sol est retirée ; elle demeure consultable dans l'historique Git.

- **Qwen 3.5 9B Q4_K_M** : mentor, recherche, architecture, sécurité, rédaction et audit.
- **Ornith 1.5 9B Q4_K_M** : ingénieur DevOps, code, scripts, IaC, débogage et CI/CD.
- **Worker** : sélection déterministe des rôles et contrôle des autorisations ; aucun repli vers un modèle cloud.
- **Matériel** : une B580 12 Go, un seul modèle en VRAM à la fois ; performances à qualifier sur Fedora.
- **État** : décision de conception motivée par les benchmarks de code et de suivi d'outils ; non garantie de qualité cloud.

[Consulter l'analyse et la matrice OpsDesk](ARCHITECTURE_LOCALE_QWEN_ORNITH.md).
