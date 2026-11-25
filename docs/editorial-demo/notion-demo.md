# Atelier Atlas — espace d’apprentissage

<callout icon="🧭" color="blue_bg">
<b>Objectif</b>

Comprendre comment un service Linux devient reproductible, observable et restaurable. Démonstration fictive, non déployée.
</callout>

<columns>
<column ratio="50">
<callout icon="🔎" color="gray_bg">
<b>Comprendre</b>

Le besoin, la topologie et les décisions.
</callout>

<callout icon="🧰" color="gray_bg">
<b>Préparer</b>

Inventaire et installation conditionnelle.
</callout>

<callout icon="🛠️" color="gray_bg">
<b>Pratiquer</b>

Cours, exercices et indices.
</callout>
</column>
<column ratio="50">
<callout icon="📈" color="gray_bg">
<b>Suivre</b>

Preuves personnelles et difficultés.
</callout>

<callout icon="📚" color="gray_bg">
<b>Ressources</b>

Runbooks et références.
</callout>
</column>
</columns>

## Architecture

[Vue SVG de présentation](atlas-presentation.svg) · [Source éditable](atlas-presentation.drawio)

## Parcours d’apprentissage

| Étape | Objectif | Contrôle |
| --- | --- | --- |
| 01 | Comprendre le service | À réaliser |
| 02 | Préparer les outils | À réaliser |
| 03 | Déployer et superviser | À réaliser |
| 04 | Restaurer et expliquer | À réaliser |

Une base native de suivi pourrait reprendre ces lignes ; ce tableau statique n’est pas une base de données créée.

## Exemple de fiche — vérifier l'environnement

<table-of-contents />

### Situation professionnelle

Tu dois préparer un serveur sans modifier une machine déjà utilisée.

### Préparer l’environnement et installer si nécessaire

Inventorier les outils, la version du système et les ressources avant d’installer quoi que ce soit.

~~~bash
# Identifier le système puis l'espace des volumes.
cat /etc/os-release
df -h
~~~

### Pratiquer

Explique ce que chaque commande indique et ce qu’elle ne prouve pas. Identifie la prochaine vérification nécessaire.

<toggle color="gray">
Indice — distinguer capacité disque et espace réellement libre.

Comparer les colonnes de la sortie df ; ne pas inventer une observation.
</toggle>

### Vérifier le résultat

Consigner la cible, la sortie réelle, une limite et la prochaine action. Aucun contrôle ni niveau personnel n'est attribué dans cet exemple.
