# Migration OpenClaw 2026.9.8 → 2026.10.2

## Décision et périmètre

Cette migration remplace **le pin du dépôt**, pas silencieusement le binaire déjà installé sur le poste Fedora. Les versions d'OpenClaw **et du plugin Parallel** passent ensemble à **2026.10.2**, avec verrouillage exact et mises à jour automatiques désactivées. Aucune modification de Qwen, Ollama, du modèle cloud, des sept rôles, des permissions des outils ou du plafond cloud de 25 €/mois.

Sources amont :
- Notes de version officielles : https://github.com/openclaw/openclaw/releases/tag/v2026.10.2
- Package npm OpenClaw : https://www.npmjs.com/package/openclaw/v/2026.10.2
- Métadonnées du plugin Parallel (tag) : https://github.com/openclaw/openclaw/blob/v2026.10.2/extensions/parallel/package.json

## Compatibilité 2026.10.2 corrigée pendant la CI

OpenClaw 2026.10.2 refuse désormais les marqueurs hérités `agents.entries.<id>.default` sans propriétaire de surface explicite. La configuration générée n'utilise plus ces anciens marqueurs : elle définit `agents.ownership: explicit`, `agents.defaults.systemAgent.agentId: chef-operations` et `talk.agentId: chef-operations`. Le patch de migration supprime encore les marqueurs historiques du runtime existant. Le mentor reste l'agent système et le rôle par défaut du projet ; les six autres agents restent explicitement sélectionnés. Le test avec le binaire npm réel doit accepter la configuration et la migration, sans exécuter `doctor --fix` sur l'installation de l'utilisateur.

## Nouvel outil natif bloqué par défaut

Le test natif du nouveau binaire a découvert l'outil `skills_read`, présenté spontanément au modèle alors que le rôle ne l'avait pas autorisé dans notre politique. Nous l'ajoutons aux refus globaux de la configuration OpenClaw et aux tests de non-exposition, plutôt que d'élargir implicitement les privilèges de tous les rôles. Une future activation nécessitera un audit spécifique de ses chemins d'accès et de la confidentialité.

## Bénéfices attendus et limites

Les correctifs amont touchent la redaction de secrets dans les résultats d'outils volumineux, la stabilité des sessions et des conversations longues, la réactivité du Gateway et du tableau de bord, les mises à jour et Doctor, ainsi que des erreurs sur les images tronquées. Les optimisations de cache Anthropic ou de compaction OpenAI ne justifient **aucun changement** à notre route locale Ollama/DeepSeek via OpenRouter. Leur gain sur la B580 n'est pas démontré.

La CI exécute le **vrai binaire npm 2026.10.2** avec le plugin **2026.10.2** : schéma, configuration à sept rôles, migration des rôles retirés, cloud simulé et taille des prompts. Le contrôle a été renforcé : nom du package et version du plugin installé sont comparés au verrou exact, plutôt que de se contenter de vérifier la présence du manifeste. Cette CI ne prouve pas le comportement réel du GPU ou d'Open WebUI.

## Procédure sur Fedora (humain uniquement)

1. Vérifier les changements : `git pull --ff-only`, puis `./menu.sh --action validate` et `./menu.sh --action upgrade` (aperçu non mutant).
2. Vérifier l'état, les tâches en cours et la place disque, puis créer une **sauvegarde vérifiable** avant toute mise à jour : `./menu.sh --action backup`. Conserver l'ancienne révision Git et la sauvegarde hors de tout nettoyage automatique.
3. Programmer une interruption du chat. Lancer **explicitement** `./menu.sh --action upgrade --apply` depuis le compte Fedora habituel, pas root. Le script arrête les services, effectue une seconde sauvegarde, installe la version prévue, réapplique la configuration native et vérifie la santé.
4. Vérifier : `openclaw --version` doit retourner **2026.10.2**, puis `./menu.sh --action health`, `./menu.sh --action context-probe --apply` et les essais de la [qualification finale](QUALIFICATION_FINALE_FEDORA.md). Tester les sept rôles, la recherche Parallel, une réponse Qwen, la route cloud seulement si autorisée, le mode hors réseau et Open WebUI.
5. En cas d'échec, **ne pas forcer** Doctor en boucle ni relancer le cloud : les services sont arrêtés. Appliquer la [procédure de retour arrière](fiches/09-entretenir.md), réinstaller le commit précédent avec son pin 2026.9.8 et restaurer **dans un répertoire vide** une sauvegarde contrôlée. Ne jamais écraser directement le répertoire de production.

## Critères de sortie

- Aucun agent ne peut modifier la version ni lancer lui-même l'upgrade.
- Les deux packages restent épinglés en `2026.10.2` ; pas de `latest`, pas de version partielle.
- CI de PR et sur `main` verte, dont schéma OpenClaw natif et test du cloud simulé.
- **Qualification finale uniquement sur le PC** : fonctionnement GPU, PDF visuels, SSE navigateur, WebUI, performances et restauration sur copie.

**Statut tant que non testé sur Fedora :** migration GitHub préparée et validée en CI, **installation effective non confirmée**.
