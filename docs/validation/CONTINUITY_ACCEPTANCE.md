# Recette synthétique Atlas — Continuité des projets (C04)

La recette reprend la même mission Atlas que le [scénario d'orchestration](ORCHESTRATION_ACCEPTANCE.md).
Elle utilise les fichiers réels d'un projet temporaire. Les réponses des rôles de
production et d'audit, les versions GitHub et le reçu de jalon sont simulés.
Les commandes `!continuer` traversent le point d'entrée natif sans appeler de modèle.

| Cas | Résultat attendu |
| --- | --- |
| Publication interrompue | Un fil neuf retrouve la tâche et la tentative à terminer. La reprise conserve la tentative déjà publiée. |
| Reprise entre rôles | Plusieurs fils retrouvent le même état du projet. L'ancien fil et un autre projet gardent leur contenu privé. |
| Décision et clarification | Le titre de la décision acceptée est visible. Le point ouvert reste à confirmer et le rapport cite ses fichiers par empreinte. |
| Mise à jour de source | La recherche locale retourne le commit approuvé et sa représentation. Le reçu de l'ancien commit passe à `REQUALIFY`. |
| Correction approuvée | Le nouveau fil montre la révision courante. Une sortie inchangée bloque la tâche et le rapport d'audit précédent reste archivé. |
| Relecture finale | Le fil de l'auditeur retrouve l'état `COMPLETE` et les deux verdicts courants. Le reçu GitHub ancien reste à requalifier. |

~~~bash
python -m pytest -q tests/test_orchestration_acceptance.py
~~~

Le job `quality` publie l'artefact `continuity-c04-synthetic` avec les six
résultats, le SHA Git testé et l'empreinte SHA-256 du rapport. La recette
couvre les comportements logiciels en CI. La qualification avec les
modèles et le poste Fedora relève de C12.
