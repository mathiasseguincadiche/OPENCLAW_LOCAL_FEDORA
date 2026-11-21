# Notion — révision contrôlée d'un bloc texte

[← Charte du wiki](NOTION_WIKI_DESIGN_SYSTEM.md) · [Sources GitHub/Notion](INTEGRATION_GITHUB_NOTION.md) · [GitHub sous approbation](GITHUB_CHAT_DASHBOARD.md)

## Portée réelle

L'atelier dispose de `clawfedora-notion-write` pour **proposer puis modifier un unique
bloc textuel Notion existant**, après lecture et approbation explicite de l'opérateur.
Ce module est un **premier sous-ensemble sûr**, pas un éditeur de wiki complet.

- **Prévisualisation :** lecture des métadonnées de la page et du bloc via l'API Notion ;
  calcul d'un diff lisible et écriture locale d'un plan JSON privé (mode `0600`).
- **Contrôle :** empreinte SHA-256 sur tout le plan (page, bloc, type, version de base et nouveau
  texte), confirmation manuelle de la page et de l'empreinte, expiration après 24 heures.
- **Écriture :** une seule requête PATCH vers le bloc exact, après une nouvelle lecture qui
  refuse le décalage de version, puis lecture de vérification. Un marqueur local
  `ATTEMPTED` est créé avant la requête d'écriture pour empêcher une relance silencieuse.
- **Limites :** uniquement un bloc **direct** de type paragraphe, titre H2/H3 ou élément
  de liste simple, sans lien, formatage spécial, enfant ou rich text multiple.

Aucun bloc n'est supprimé, déplacé ou recréé. Les pages enfants, bases de données,
suivi de progression, images, fichiers, styles riches et autres blocs ne sont pas
modifiés. Les cinq espaces du wiki et **la section d'installation des outils** doivent
être conservés. L'atelier ne prétend pas avoir contrôlé visuellement Notion.

### Règles de sécurité

Ce composant est une **commande locale d'opérateur**, pas un outil autonome du
modèle IA et pas une commande `!notion` dans Open WebUI. Les agents peuvent
préparer le **texte proposé** et la justification dans le dossier local du projet.
Ils ne peuvent pas approuver ni déclencher une écriture Notion.

Conserver les jetons dans le gestionnaire de secrets / l'environnement du
processus Fedora ; ne jamais les entrer dans un prompt, des arguments CLI, Git,
une page publiée ou un fichier de configuration versionné. Deux variables sont
nécessaires : `NOTION_API_TOKEN` pour **lire** pendant le plan et les contrôles,
`NOTION_WRITE_TOKEN` pour l'écriture. Idéalement, utiliser deux intégrations Notion
avec droits et pages partagées minimaux. La connexion Notion de ChatGPT ne fournit
aucun jeton à Fedora.

Les fichiers de plan contiennent le **texte de remplacement** et sont strictement
**locaux et privés** : ne pas les placer sous `deliverables/`, dans Git,
dans une CI, dans un espace de chat cloud ou dans un dépôt public. Le diff du plan
affiche le texte précédent et le texte proposé dans le terminal local.

## Procédure pas à pas

**1.** Choisir une page Notion réellement autorisée et un bloc textuel simple qu'il
est pertinent de modifier. Relever leurs identifiants depuis l'interface ou une
lecture API. Ne jamais modifier une page complète en devinant ses identifiants.

**2.** Faire réviser le texte à l'architecte, au rédacteur, au DevOps si la procédure
inclut des commandes, à la sécurité et enfin à l'auditeur. Enregistrer uniquement
le texte final dans un fichier local privé.

```bash
# Les chemins et ID ci-dessous sont des exemples à remplacer.
chmod 600 /chemin/prive/texte-relus.txt

# Lecture Notion réelle, diff et plan privé. AUCUNE écriture distante.
clawfedora-notion-write plan \
  --page "IDENTIFIANT_PAGE_NOTION" \
  --block "IDENTIFIANT_BLOC_NOTION" \
  --text-file "/chemin/prive/texte-relus.txt" \
  --output "/chemin/prive/proposition-notion.json"
```

**3.** Lire le diff complet ; vérifier le sens, les commandes, la cohérence avec le
SHA GitHub connu, la protection des notes, les liens et la place de la section
d'installation. Le résultat `PREVIEW_ONLY` donne `manifest_sha256`.

**4.** Uniquement après validation explicite du changement ciblé, appliquer avec
la page et **l'empreinte du plan réellement produit**.

```bash
clawfedora-notion-write apply \
  --plan "/chemin/prive/proposition-notion.json" \
  --approve-page "IDENTIFIANT_PAGE_NOTION" \
  --approve-manifest "EMPREINTE_64_CARACTERES_DU_PLAN" \
  --apply
```

Si Notion a changé le bloc entre le plan et l'application, l'opération est
refusée. Si la requête d'écriture a été tentée et échoue, **ne pas réutiliser
le plan** : contrôler l'état réel du bloc dans Notion puis produire un nouveau
plan si nécessaire. Notion ne fournit pas une comparaison-échange atomique,
donc une modification concurrente dans la courte fenêtre entre lecture et
PATCH reste possible. Éviter toute édition parallèle pendant l'opération.

**5.** Ouvrir la page réelle dans Notion et contrôler les titres, liens,
espacements, encadrés, navigation, bureau/mobile et la conservation des autres
blocs. Consigner séparément :

| Contrôle | Verdict disponible |
| --- | --- |
| Intégrité plan + autorisation exacte | Vérifié par le programme |
| Bloc ciblé lu après PATCH | Vérifié par le programme si succès |
| Autres blocs, sous-pages et bases intactes | Conçu pour ne pas les toucher ; à inspecter |
| Rendu visuel Notion natif | **Non vérifié par le programme** |
| Installation / exploitation Fedora-Rocky | **Non exécutée par le programme** |
| Avancement personnel des exercices | **Jamais attribué automatiquement** |

## Suite technique à prévoir

Pour passer à un véritable éditeur de pages Notion, concevoir d'abord une
édition **multi-blocs avec inventaire des éléments protégés**, prévisualisation
et accords bloc par bloc, journal de réconciliation des échecs partiels,
gestion des images et liens, protection explicite des bases et sous-pages,
et recette de rendu graphique native. Cette commande ne prétend pas satisfaire
ces étapes avancées.

Une intégration de ces opérations au chat ou au tableau de bord nécessitera
des validations supplémentaires : isolation des données Notion privées,
protection des conversations cloud, contrôle d'origine, anti-rejeu, journal
de consentement, et parité des refus dans les deux interfaces.
