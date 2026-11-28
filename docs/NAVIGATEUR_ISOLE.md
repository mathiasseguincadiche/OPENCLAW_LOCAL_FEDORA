# Observation dans un navigateur isolé

Le mode `official-docs` de `clawfedora-visual-capture` consulte une page HTML
publique et produit un aperçu du DOM ainsi que des captures de rendu.
Il s'adresse à l'opérateur de l'atelier.

## Observer une documentation officielle

Préparez l'option visuelle Playwright du dépôt et son Chromium. Prévisualisez
d'abord la cible. Cette commande valide l'adresse et décrit les vues prévues.

~~~bash
install -d -m 700 "$HOME/clawfedora-observations"
clawfedora-visual-capture \
  --kind official-docs \
  --url https://playwright.dev/python/docs/browser-contexts \
  --output-dir "$HOME/clawfedora-observations"
~~~

Ajoutez `--capture` pour récupérer et afficher le document. Le dossier doit
être privé et situé en dehors d'un dépôt Git.

## Adresses et données

La commande accepte des URL HTTPS directes sur les domaines de documentation
suivants.

| Documentation | Domaine |
| --- | --- |
| Fedora | `docs.fedoraproject.org` |
| Ansible | `docs.ansible.com` |
| Terraform | `developer.hashicorp.com` |
| Kubernetes | `kubernetes.io` |
| GitHub | `docs.github.com` |
| OpenClaw | `docs.openclaw.ai` |
| Playwright | `playwright.dev` |

Une requête HTTPS récupère au plus 2 Mo de HTML UTF-8. Fournissez directement
l'adresse finale si le serveur répond par une redirection. Un refus d'accès
arrête l'observation. Chromium reçoit
l'HTML en mémoire dans un nouveau contexte hors réseau, avec JavaScript et
workers de service désactivés. Les ressources distantes et formulaires sont
bloqués. Le rendu d'une documentation publique dépend du HTML et des
styles intégrés.

Chaque observation complète inclut un `manifest.json` daté. Il indique
l'adresse, l'empreinte du HTML reçu, le titre, quelques titres de section
et un extrait du DOM. Les fichiers PNG comportent des dimensions et une
empreinte SHA-256. Les trois vues couvrent le bureau clair, le bureau sombre
et une fenêtre mobile. Le contenu Web reste une donnée non fiable et la
qualité visuelle reste à juger.

La CI vérifie les refus d'URL et de redirection. Elle utilise aussi Chromium
pour afficher un document synthétique et vérifier les captures et leurs
empreintes. L'essai sur les sites publics et sur le poste Fedora relève de
la qualification ultérieure.


## Observer un panneau de ClawFedora

Avec l'atelier local démarré, choisissez le panneau à observer. Le port
`18890` est celui utilisé par défaut par le tableau de bord.

| Mode | Adresse locale | Données affichées au chargement |
| --- | --- | --- |
| `local-dashboard` | `http://127.0.0.1:18890/` | État de l'atelier et projets |
| `local-performance` | `http://127.0.0.1:18890/performance.html` | Rapport local de performances |
| `local-github` | `http://127.0.0.1:18890/github.html` | Liste des projets issue de l'atelier |
| `local-notion` | `http://127.0.0.1:18890/notion.html` | Écran initial du panneau Notion |

~~~bash
clawfedora-visual-capture \
  --kind local-dashboard \
  --url http://127.0.0.1:18890/ \
  --output-dir "$HOME/clawfedora-observations" \
  --capture
~~~

Chromium exécute le JavaScript du panneau dans un contexte temporaire hors
réseau. La commande lui fournit en mémoire les fichiers du panneau choisi
et sa lecture d'API locale, si elle est nécessaire. Chaque réponse autorisée
est lue une fois et réutilisée pour toutes les vues. Les requêtes d'écriture,
les destinations externes, les redirections, les WebSockets et les
téléchargements sont bloqués. La capture attend la fin du chargement
du panneau. Le manifeste attribue à chaque ressource locale son chemin
et son empreinte SHA-256. Il indique la préférence de thème demandée et
le thème réellement appliqué. Le panneau Performances utilise un thème
clair dans les trois vues.

En CI, Chromium exerce les quatre panneaux avec le véritable serveur
ClawFedora et des données synthétiques. La qualification sur le poste
Fedora reste à faire.
