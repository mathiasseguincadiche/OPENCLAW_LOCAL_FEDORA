# Boréal — résultats du raisonnement et profils expérimentaux

[Run de référence 45781161395](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45781161395), commit eaa704b09fce7915c078e56aea1efa2d14ce56b7.
Les douze rapports JSON proviennent de la dernière ligne JSON des jobs, et sont conservés dans tests/fixtures. Les ZIP d'artefacts ne sont pas téléchargés ni vérifiés.

| Modèle | Réponses initiales conformes | Corrigées | Bloquées | Non collectées |
| --- | ---: | ---: | ---: | ---: |
| Qwen | 7 | 3 | 4 | 0 |
| Ornith | 3 | 5 | 6 | 0 |
| Gemma | 0 | 0 | 0 | 14 |

Gemma : quatre TimeoutError avant la première réponse de chaque job. Un timeout n'est pas une erreur factuelle. Les huit autres jobs ont collecté les 28 réponses initiales. Qwen est stable sur mentor, DevOps, sécurité ; audit nécessite une correction, architecture et rédaction échouent aux identifiants exacts. Ornith souffre de sorties vides/tronquées et de longueurs excessives, même lorsqu'il comprend le dossier. La revue sémantique reste nécessaire ; les scores ne certifient pas l'excellence.

| Modèle | Seed | Lot | Job |
| --- | --- | --- | --- |
| qwen | 73 | core | [139776688972](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45781161395/job/139776688972) |
| qwen | 42 | core | [139776689206](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45781161395/job/139776689206) |
| ornith | 73 | review | [139776689211](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45781161395/job/139776689211) |
| gemma | 42 | review | [139776689220](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45781161395/job/139776689220) |
| qwen | 73 | review | [139776689223](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45781161395/job/139776689223) |
| gemma | 42 | core | [139776689226](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45781161395/job/139776689226) |
| ornith | 42 | review | [139776689292](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45781161395/job/139776689292) |
| gemma | 73 | review | [139776689306](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45781161395/job/139776689306) |
| ornith | 42 | core | [139776689315](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45781161395/job/139776689315) |
| gemma | 73 | core | [139776689355](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45781161395/job/139776689355) |
| qwen | 42 | review | [139776689362](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45781161395/job/139776689362) |
| ornith | 73 | core | [139776689392](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45781161395/job/139776689392) |

## Expérience suivante

| Profil | Modèle | Thinking | Budget tokens | Timeout socket |
| --- | --- | --- | ---: | ---: |
| direct | Qwen | non | 900 | 900 s |
| direct | Ornith | non | 1200 | 1200 s |
| direct | Gemma | non | 900 | 1500 s |
| gemma-think-probe | Gemma | oui | 900 | 1500 s |

Même suite, mêmes prompts, digests, contexte 8192 et température 0. Douze jobs direct (trois modèles, deux seeds, deux lots), plus deux sondes Gemma avec thinking sur la seed 42 : mentor-dns et security-secret, comparables à leurs homologues direct avec budget et délai identiques. 42 réponses direct et 2 sondes, au plus autant de corrections. Pas de nouvelle campagne complète avec thinking pour Qwen/Ornith : la référence existante est conservée. Les budgets et délais changent également ; cette comparaison de profils ne permet pas d'attribuer causalement un écart au seul thinking pour Qwen/Ornith. Le timeout socket est un délai d'inactivité, pas une borne absolue de durée ; le job est limité à 240 minutes. Une erreur interrompt son lot, conserve les résultats collectés et n'est jamais comptée comme faute technique du modèle. Aucun fallback automatique.

Le workflow expérimental démarre sur feat/excellence-inference-profiles et peut être déclenché manuellement. Ne pas relancer une campagne entière pour un correctif sans vérifier la provenance. Les rapports distinguent le profil demandé, les tokens observés, le thinking observé et le temps CPU. La qualification GPU, les outils natifs, la grille de revue et le routage de production restent inchangés. Une comparaison honnête du coût/qualité exige les mesures réelles sur B580.

## Résultats et expérimentation des consignes

[Audit de la campagne et consignes candidates](EXCELLENCE_ROLE_COACHING.md).
