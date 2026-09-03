# Moteur de projets Linux-native

Le moteur L1 transforme une entrée projet non structurée en état de travail traçable sans dépendance à un autre OS.

## Cycle

```text
INTAKE_READY -> ANALYZED -> CLARIFICATION_REQUIRED -> ANALYZED
             -> PLANNED -> ASSIGNED -> IN_PROGRESS -> VALIDATING
             -> REVIEW -> PACKAGING -> COMPLETE
```

`COMPLETE` exige une approbation humaine explicite. Une transition interdite échoue fermée.

## Intake et documents

`clawfedora project create` copie les entrées dans le projet central, refuse les symlinks et secrets évidents, calcule SHA-256/MIME et construit `context/ingestion/index.json`.

- texte/code : extraction locale ;
- DOCX/PPTX/XLSX : lecture XML locale, sans exécution ;
- ZIP : extraction locale bornée, anti-traversal, anti-fichier spécial et anti-bombe ;
- PDF : `TOOL_REQUIRED`, puis lecture réelle via l'outil OpenClaw `pdf` ;
- images : `TOOL_REQUIRED`, puis lecture réelle via `view_image` ;
- inconnu ou corrompu : `UNREADABLE`, à déclarer dans `missing_information`.

Une analyse ne passe pas si `source_coverage[]` ne couvre pas exactement l'index d'ingestion.

## Plan et exécution

Chaque tâche possède un rôle parmi les huit agents, des dépendances, sorties attendues et critères d'acceptation. Les cycles de dépendances sont refusés. Les sorties sont obligatoirement namespacées sous `work/<task-id>/`, `deliverables/<task-id>/`, `evidence/<task-id>/` ou `diagrams/<task-id>/`.

Chaque tentative crée un bundle immuable :

```text
context/exchange/<task-id>/self/run-001/
context/exchange/<consumer>/dependencies/<producer>/run-001/
```

Les sorties d'une tâche ne sont propagées aux dépendants qu'après `PASS`. Les SHA-256 et le digest agrégé sont revérifiés avant `VALIDATING`.

## Validation et packaging

L'Auditeur qualité enregistre les verdicts de validation et de review. Le packaging génère :

- `deliverables/package_manifest.json` ;
- `evidence/final_report.json`.

Aucune publication distante ni escalade cloud n'est implicite.

## Self-test hors matériel

```bash
clawfedora project selftest
```

Ce test synthétique exécute localement un cycle complet avec une entrée texte et un livrable temporaire. Il ne constitue ni un E2E OpenClaw/B580 ni une approbation V1 réelle.
