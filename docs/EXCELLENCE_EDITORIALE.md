# Standard universel d’excellence éditoriale — V1

[GitHub](GITHUB_REPOSITORY_DESIGN_SYSTEM.md) · [Notion](NOTION_WIKI_DESIGN_SYSTEM.md) · [Démonstrations](editorial-demo/README.md)

Le standard est transversal : il ne fixe ni stack ni arborescence. Adapter chaque document à sa fonction et à son lecteur. Préserver les contenus utiles, notamment l'installation des outils et les exercices. GitHub = référence technique versionnée ; Notion = apprentissage, données privées et suivi. Les documents complémentaires gardent une source modifiable.

## Douze principes

| Principe | Résultat attendu |
| --- | --- |
| Identité | Palette sobre et cohérente, style propre au projet |
| Information | Une source de vérité par sujet |
| Rédaction | Français précis, naturel, sans remplissage |
| Vulgarisation | Définition, mécanisme, exemple utile |
| Technique | Choix, alternatives, compromis et limites |
| Progression | Comprendre, pratiquer, maîtriser ; aucune solution imposée en guidé |
| Graphiques | Présentation distincte du détail ; Draw.io et SVG |
| Navigation | Point d’entrée clair, ancres et liens réellement utiles |
| Exactitude | Version, cible, source lue, date |
| Multisupport | Cohérence des références sans duplication des notes privées |
| Expérience | Bureau, mobile, thème clair/sombre, contraste |
| Maintenance | Diff ciblé, impact, preuve et révision |

## Chaîne de responsabilité

| Rôle | Contribution | Contrôle |
| --- | --- | --- |
| Mentor OPS | Brief : public, besoin, support, périmètre | Accord sur le changement |
| Recherche | Références et versions | Sources réellement lues |
| Architecte | Information, navigation, vues et schémas | Frontières et flux justifiés |
| DevOps | Procédures, code, validation | Cible, commandes, résultat, reprise |
| Sécurité | Confidentialité, précautions | Aucun secret ni note privée publiée |
| Rédacteur | Texte, gabarits, proposition de mise en page | Relecture et liens |
| Auditeur | Revue en session distincte | Grille, blocages, preuves et limites |

Le worker conserve les droits et le protocole de collecte. Aucun huitième agent, aucun modèle supplémentaire, aucun accès d’écriture distant autonome.

## Qualification éditoriale

L'outil `clawfedora_doc_review` accepte les profils readme, procedure, course, wiki_home, architecture, proof, journal, portfolio, release, issue et pull_request. Le champ facultatif support indique github, notion, document ou markdown. Il retourne une empreinte SHA-256, des signaux de structure, des parcours de lecture, la grille et les critères bloquants **non évalués**. Les signaux ne sont pas des points.

| Critère | Points |
| --- | ---: |
| Exactitude | 20 |
| Rédaction | 15 |
| Information | 15 |
| Pédagogie | 10 |
| Graphiques | 10 |
| Navigation | 10 |
| Cohérence multisupport | 10 |
| Sources et preuves | 5 |
| Maintenance | 5 |

Évaluer chaque critère sur preuves consultées (0 à son poids), ou N/A justifié par la fonction du document ; normaliser sur le total applicable. Ne calculer aucun score si une vérification applicable manque. 0–59 insuffisant ; 60–74 acceptable ; 75–84 professionnel ; 85–94 premium ; 95–100 excellence. Une erreur technique majeure, preuve inventée, fuite privée, suppression d'une rubrique indispensable, procédure dangereuse ou revue obligatoire manquante bloque la réception quel que soit le score. Une note déclarée n'est pas une certification machine.

## Réception et publication

1. Inventorier l'existant, fixer le support et la révision.
2. Rédiger sur snapshot ; préserver code, installation et suivi personnel.
3. Contrôler structure, liens, exactitude, confidentialité et impact.
4. Prévisualiser les changements et recueillir l'approbation du périmètre exact.
5. Utiliser le circuit GitHub ou Notion existant ; refuser toute opération non supportée.
6. Relire les résultats et appliquer la [recette visuelle native](validation/VISUAL_RECEPTION_NATIVE.md). Ne pas confondre aperçu local, API, capture native, revue humaine et preuve technique.

**Limite actuelle :** l'atelier ne sait pas encore créer et publier un wiki Notion complet. Les gabarits natifs et la maquette sont des propositions. Une [création de page fille sous approbation](NOTION_EDITORIAL_CREATION.md) prend en charge les blocs natifs bornés, en plus des modifications existantes. Médias, bases de données et réorganisation de wikis restent hors périmètre. Une recette sur page de test reste nécessaire. Aucune exécution Fedora ni qualification des modèles n'est anticipée.
