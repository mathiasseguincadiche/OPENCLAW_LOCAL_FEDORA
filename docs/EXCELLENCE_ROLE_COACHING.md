# Qualification des consignes métier et outils simulés

[Run de référence 45790472002](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45790472002), commit 1f186d1d7dab7d1966b628aadadb9d460f2ce373. Les 14 jobs sont terminés avec succès. Les rapports sont reconstruits depuis les dernières lignes JSON publiques, pas depuis les ZIP originaux.

| Modèle | Profil | Initial | Corrigé | Bloqué |
| --- | --- | ---: | ---: | ---: |
| ornith | direct | 11 | 0 | 3 |
| gemma | direct | 8 | 0 | 6 |
| qwen | direct | 7 | 1 | 6 |
| gemma | gemma-think-probe | 0 | 0 | 2 |

Ornith direct est le meilleur sur les contrats factuels Boréal (11/14), contre 8/14 pour Qwen et Gemma. Gemma direct complète les 14 cas absents du run précédent. Les deux sondes Gemma thinking produisent des contenus vides avec fin par limite, y compris après correction : la réduction du budget évite le timeout mais ne qualifie pas ce mode. Ne pas confondre succès du job et qualité de la réponse.

Les trois modèles échouent sur architecture en direct à cause des valeurs enrichies (VM data, VM edge) au lieu des identifiants attendus ; ce n'est pas une preuve d'ignorance de la topologie. Qwen échoue à la lecture seule de l'auditeur dans les deux essais directs. Gemma retourne FAIL au lieu de REVISE. Qwen et Gemma omettent le préfixe sha256 du digest fictif. Ornith dépasse encore la longueur sur un DevOps et propose terraform refresh comme contrôle non destructif sur l'autre : cette commande peut modifier le state. Des justifications confondent flux déclarés/proposés, vérification de l'image et restauration des données. Aucun verdict sémantique définitif.

| Modèle | Profil | Seed | Lot | Job |
| --- | --- | --- | --- | --- |
| ornith | direct | 42 | core | [139807896084](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45790472002/job/139807896084) |
| gemma | direct | 42 | core | [139807896504](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45790472002/job/139807896504) |
| qwen | direct | 42 | core | [139807896507](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45790472002/job/139807896507) |
| qwen | direct | 73 | core | [139807896565](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45790472002/job/139807896565) |
| ornith | direct | 42 | review | [139807896587](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45790472002/job/139807896587) |
| gemma | direct | 42 | review | [139807896598](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45790472002/job/139807896598) |
| ornith | direct | 73 | review | [139807896612](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45790472002/job/139807896612) |
| qwen | direct | 73 | review | [139807896656](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45790472002/job/139807896656) |
| gemma | gemma-think-probe | 42 | core | [139807896658](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45790472002/job/139807896658) |
| gemma | direct | 73 | review | [139807896697](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45790472002/job/139807896697) |
| qwen | direct | 42 | review | [139807896723](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45790472002/job/139807896723) |
| gemma | gemma-think-probe | 42 | review | [139807896735](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45790472002/job/139807896735) |
| ornith | direct | 73 | core | [139807896762](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45790472002/job/139807896762) |
| gemma | direct | 73 | core | [139807896782](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45790472002/job/139807896782) |

## Intervention expérimentale

Une consigne commune exige identifiants littéraux, statut de preuve dans reason, contrôle des booléens et concision. Sept compléments métier ciblent le niveau d'aide, la provenance/version, les flux et placements, le state Terraform, la révocation, l'indépendance de l'audit et le retour image/données. Ils sont appliqués uniquement au profil coached. Les prompts actifs ne sont pas modifiés. Aucun identifiant attendu n'est injecté dans les consignes.

Comparer direct et coached sur les mêmes dossiers, seeds et budgets, mêmes modèles et même validateur. 12 jobs, 42 réponses initiales, au plus 42 corrections. Les consignes sont testées sur les cas qui ont motivé leur rédaction : ce n'est pas une validation indépendante. Une nouvelle suite de cas inédits est obligatoire avant promotion.

En seed 42, sept sondes d'outils simulés par modèle vérifient appel structuré, choix de l'outil autorisé, paramètre exact, absence de mutation et fidélité à un reçu synthétique. 21 sondes, au plus 42 appels supplémentaires. Elles ne font intervenir aucun outil natif, aucun fichier privé, aucun accès distant ni exécution de commande. La mutation leurre est toujours refusée par le harnais ; elle ne correspond à aucune action réelle. Un PASS ne qualifie pas l'intégration OpenClaw, la sécurité des permissions ni la capacité de diagnostiquer un véritable service.

La campagne démarre sur feat/excellence-role-coaching. Après collecte, comparer par rôle les preuves direct/coached, effectuer une revue indépendante sur cas inédits puis tester les outils natifs, notamment sandbox_iterate pour DevOps, sur Fedora. Aucun routage, catalogue ni politique de production modifié.
