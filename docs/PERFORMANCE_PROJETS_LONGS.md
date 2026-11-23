# Optimisations pour projets longs — premier lot contrôlé

> **Portée : code proposé sur une branche/PR, pas une mesure de performance sur la B580.**
> Aucune accélération ou qualité supérieure n'est garantie sans réception Fedora.

## Objectifs et périmètre

Ce premier lot améliore deux points précis sans ajouter de modèle, de framework
mémoire, de service réseau ni de privilège aux sept agents :

1. **Discussion native** : éviter de renvoyer systématiquement tout l'historique
   au modèle lorsque le fil grandit.
2. **Mesure locale** : comparer Qwen 3.5 9B et Ornith 1.5 9B, chacun aux contextes
   8K / 16K / 32K, sans changer automatiquement la configuration.

L'inférence demeure locale via Ollama, les permissions passent par le pont
OpenClaw, la validation humaine reste obligatoire et le worker continue de
gérer le projet. Les sources GitHub/Notion et les documents de projet
conservent leur provenance et leurs règles d'accès actuelles.

## Historique des discussions

Le module `src/clawfedora/chat_context.py` choisit, pour chaque nouvelle
requête, **des échanges utilisateur/assistant complets**, jamais des morceaux
de messages. Il conserve :

- un suffixe de **six échanges récents au maximum** dans un budget ;
- **trois échanges antérieurs pertinents au maximum** par simple correspondance
  lexicale avec le dernier message ;
- un budget conservateur de **20 000 caractères incluant le message courant**.

La limite est en caractères et **n'est pas une mesure exacte de tokens**.
Les instructions des rôles, les outils et la réponse occupent aussi du
contexte OpenClaw. Un échange trop gros peut être écarté entièrement.
La pertinence lexicale n'est pas une vérité vérifiée.

**Le fichier JSON privé conserve l'intégralité du transcript et n'est ni
réécrit ni résumé.** La sélection de contexte n'efface donc pas les conversations.
Des compteurs non sensibles (`stored_turns`, `sent_turns`,
`omitted_turns`, `recalled_turns` et tailles) sont conservés sous
`context_window` à la prochaine réponse réussie.

**Limite importante :** un échange écarté peut contenir une décision utile.
Les décisions officielles doivent rester dans les ADR, notes validées,
fichiers de projet et preuves, jamais seulement dans l'historique du chat.
Cette sélection n'est pas une mémoire sémantique universelle. Le fil
conserve les plafonds existants de 900 messages et 850 Ko ; un nouveau fil
reste nécessaire à leur atteinte. Les nouveaux fils retrouvent maintenant l'état canonique de leur projet
sélectionné, **sans récupération automatique de l'historique des anciens chats**.

## Reprise des projets longs entre fils

Le lot suivant introduit `project_resume.py`. Il ne crée pas une seconde
mémoire : il lit la feuille de route persistée et les références des décisions
acceptées du même projet. Le pont ajoute un `continuity` borné au contexte
des questions normales ; `!continuer` donne un état plus complet avec
contrôle des reçus et de l'intégrité des sources, **sans appeler le LLM**.

L'historique complet des autres fils reste privé et n'est ni copié ni
réinterprété automatiquement. Les preuves et jalons restent déclaratifs ou
à requalifier selon leurs propres reçus ; il n'y a pas de reprise automatique
de processus, de publication ou de validation humaine.

Voir [la procédure pour projets longs](PROJETS_LONGUE_DUREE.md).

## Mesurer Qwen ET Ornith sur Fedora

Depuis le dépôt et l'environnement Python installé :

```bash
# Prévisualise les 2 modèles et les 3 tailles de contexte, sans lancer de LLM.
clawfedora-gpu-benchmark --root "$PWD" --models all

# Lance explicitement les sondes locales (aucune écriture de configuration).
clawfedora-gpu-benchmark --root "$PWD" --models all --apply

# Essai proche de la limite ; plus exigeant pour la VRAM et la stabilité.
clawfedora-gpu-benchmark --root "$PWD" --models all --near-limit --apply
```

`--models qwen-max` et `--models ornith-code` sélectionnent un seul modèle.
La commande sans `--models` conserve la compatibilité historique : Qwen seul.
Le résultat `benchmarks` regroupe les rapports indépendants quand `all`
est demandé : contexte alloué, part GPU, VRAM résidente, temps de chargement,
vitesse d'évaluation du prompt et de génération.

### Ce que les sondes ne prouvent pas

- Le débit ne mesure **pas** la qualité des résolutions DevOps ni des appels d'outils.
- Un `FULL_GPU` à 60 % de remplissage reste **provisoire**.
- Une mesure près de la limite ne remplace pas les essais longs, les tests
  de stabilité et la validation humaine.
- L'exécution du code en CI ne mesure **jamais** le GPU réel Fedora.
- Les références de versions, les empreintes et le chargement du modèle sont
  vérifiés par le runtime : aucun téléchargement ou changement implicite.

## Optimisations explicitement non activées

Les réglages `Flash Attention`, `OLLAMA_KV_CACHE_TYPE=q8_0`, la durée
`keep_alive` et l'accélération d'un éventuel backend doivent être comparés
au profil actuel sur le PC réel, en maintenant constants modèle, prompt,
contexte, température et scénario. Aucun de ces réglages n'est modifié ici.

L'adaptation du streaming SSE à l'Atelier natif et la reprise des actions
interrompues restent des chantiers distincts, qui exigent des tests d'annulation,
d'isolation et de permissions.

## Réception avant fusion ou activation

1. CI Python, Mypy, Ruff et tests des contrats du dépôt réussis sur le SHA de la PR.
2. Sur Fedora : établir un profil de référence Qwen / Ornith à 8K, 16K, 32K.
3. Comparer débit et VRAM à contexte équivalent, relever toute dégradation.
4. Vérifier que le transcript complet persiste après plusieurs réponses
   dont le contexte envoyé a été réduit.
5. Tester deux projets distincts, les permissions, l'absence de reprise
   implicite après interruption et les anciennes conversations.
6. Valider manuellement les bénéfices avant tout changement de réglage GPU.
