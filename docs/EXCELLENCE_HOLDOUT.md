# Contre-expertise sur cas inédits — Silex

[Run Boréal coached 45893686907](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45893686907), commit c8caccea4769efd699e39c1ee9b2b72ef7530819.
Douze rapports reconstruits depuis les logs JSON publics, archivés sans modifier leurs verdicts. ZIP d'origine non téléchargés ni vérifiés.

| Modèle | Direct initial/corrigé/bloqué | Coached initial/corrigé/bloqué |
| --- | --- | --- |
| Qwen | 7/1/6 | 8/2/4 |
| Ornith | 11/0/3 | 10/0/4 |
| Gemma | 8/0/6 | 9/0/5 |

Les consignes améliorent les contrats Qwen et Gemma, mais régressent sur Ornith (audit lecture seule). Les trois restent bloqués sur les identifiants enrichis d'architecture ; ne pas confondre précision de format et connaissance du placement. Le texte métier exige une revue indépendante.

## Défaut du banc d'outils

Les 21 sondes historiques ont retourné FAIL_TOOL_CALL. Dix-huit appels (Gemma 7, Ornith 7, Qwen 4) contenaient exactement le nom et les arguments attendus, mais la structure Ollama comporte aussi function.index=0. Le comparateur d'objet entier a rejeté ces 18 appels. Les trois autres (Qwen) n'ont produit aucun appel. Le replay corrige exclusivement l'interprétation de la première étape : 18 appels conformes, trois non conformes. Aucun retour d'outil n'a été transmis lors de ces essais ; aucune réussite de bout en bout ne peut être attribuée.

Le nouveau validateur accepte uniquement index entier 0 facultatif, nom exact, arguments exacts et un seul appel ; mutation, arguments supplémentaires, index invalide ou autre outil restent refusés. Les verdicts archivés sont conservés. Les sondes seront rejouées pour collecter le véritable second tour.

| Modèle | Seed | Lot | Job |
| --- | --- | --- | --- |
| qwen | 73 | core | [140162244609](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45893686907/job/140162244609) |
| gemma | 42 | review | [140162244692](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45893686907/job/140162244692) |
| qwen | 42 | review | [140162244714](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45893686907/job/140162244714) |
| ornith | 42 | review | [140162244758](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45893686907/job/140162244758) |
| gemma | 42 | core | [140162244777](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45893686907/job/140162244777) |
| ornith | 73 | review | [140162244778](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45893686907/job/140162244778) |
| qwen | 42 | core | [140162244797](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45893686907/job/140162244797) |
| ornith | 42 | core | [140162244820](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45893686907/job/140162244820) |
| gemma | 73 | core | [140162244870](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45893686907/job/140162244870) |
| ornith | 73 | core | [140162244875](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45893686907/job/140162244875) |
| gemma | 73 | review | [140162244889](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45893686907/job/140162244889) |
| qwen | 73 | review | [140162244994](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45893686907/job/140162244994) |

## Suite indépendante Silex

Sept cas inédits : diagnostic HTTP, compatibilité versionnée, sens des flux réseau, verrou Terraform, TLS SAN, couverture des preuves et restauration isolée. Les identifiants attendus sont explicitement définis comme valeurs machine nues ou enum dans les questions, sans injecter la réponse attendue. Les critères de revue figurent dans la suite, ne sont pas transmis au modèle. Même prompts de rôle et mêmes paramètres que Boréal direct/coached ; pas de retouche des consignes après consultation des résultats Silex avant clôture de la campagne.

Matrice : trois modèles, deux variantes (direct/coached), seed 42, deux lots ; 12 jobs et 42 réponses initiales au plus autant de corrections. Sur coached, 21 sondes des outils corrigés, au plus 42 appels. Cette contre-expertise est une première mesure sur un nouveau dossier et non une étude statistique indépendante avec évaluateur tiers : une seule seed par variante, revue qualitative encore nécessaire. Les tests ne prouvent ni outils natifs, ni performances GPU, ni excellence finale.

La décision de promotion exige revue de la sécurité et des contradictions, puis non-régression multi-agents et qualification Fedora sur B580. Aucun changement des modèles actifs, prompts actifs, autorisations, routage ou version d'Ollama.
