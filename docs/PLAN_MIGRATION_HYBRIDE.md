# Plan de migration hybride (OpenRouter + Qwen local)

**Statut : plan validé le 9 octobre 2026. Rien de ce qui suit n'est implémenté, sauf ce que le suivi des lots indique.**
Le dépôt reste 100 % local tant que le cloud n'est pas activé explicitement (voir « Garde-fou d'activation »).

Ce document fixe les décisions, l'architecture, l'ordre des lots et ce que chaque lot doit prouver. Il se met à jour à chaque lot : une case n'est cochée que si la preuve annoncée existe.

## 1. Objectif

Un atelier hybride qui place GLM là où il aide l'apprentissage et les livrables, garde Qwen local comme socle, repli et refuge pour le sensible, et tient dans **25 € réellement payés par mois, frais, change et TVA compris**. Les explications correctes passent avant tout ; les livrables sont co-construits (livrable complet, expliqué bloc par bloc, sans exercice imposé).

## 2. Décisions figées

| Sujet | Décision |
|---|---|
| Fournisseur | OpenRouter, géré nativement par OpenClaw 2026.9.8 (références `openrouter/<fournisseur>/<modèle>`). |
| Modèle cloud | GLM-5.3 Flash (`z-ai/glm-5.3-flash`). Mistral Large 4 : hors périmètre. |
| Mode **Apprendre** (Open WebUI) | GLM par défaut pour le mentor et les explications. |
| Mode **Travail** (Open WebUI) | Qwen local uniquement. |
| Atelier Projets | Cloud autorisé **projet par projet**, par accord explicite de l'utilisateur. |
| Repli | Chat : repli cloud → local avec bandeau visible. Atelier : **pause visible** de la tâche, jamais de bascule silencieuse. |
| Pas de repli payant | Aucun basculement vers un modèle plus cher. |
| Benchmark | Aucun benchmark préalable (décision de l'utilisateur). Le routage se corrige à l'usage, via le journal de coûts. |
| Retour arrière | `cloud_enabled=false` ramène à l'état 100 % local. |

## 3. Exigences non négociables

1. **Le filtre couvre tout ce qui part au cloud** : historique, contexte ajouté par l'atelier (fiche mentor, extraits), prompt système **et résultats des outils**.
2. **Le cloud reste désactivé tant que le filtre et le contrôle de budget ne fonctionnent pas ensemble.** Il n'existe pas d'état « filtre seul » ou « budget seul » avec cloud actif.
3. **Le suivi comptabilise tous les appels facturés**, y compris les appels intermédiaires d'une boucle d'outils, les nouvelles tentatives et les appels échoués ou interrompus, avec un plafond de **25 € réels par mois**.

## 4. Architecture : une passerelle cloud locale unique

Un agent OpenClaw ne fait pas un seul appel par message : chaque appel d'outil ajoute un aller-retour vers le modèle, et le résultat de l'outil est renvoyé au modèle. Un contrôle placé seulement dans la passerelle Open WebUI ne verrait ni ces résultats ni ces appels. La conception retenue est donc :

```
Open WebUI / Atelier ──► passerelle chat ──► OpenClaw (--model local ou cloud)
                                                   │
                       Qwen local (Ollama)  ◄──────┤
                                                   ▼
                          passerelle cloud locale 127.0.0.1 (filtre + budget)
                                                   │
                                                   ▼
                                              OpenRouter
```

- OpenClaw envoie ses requêtes cloud à la **passerelle cloud locale**, qui seule détient la clé OpenRouter. OpenClaw ne la voit pas.
- La passerelle inspecte **tout le corps de chaque requête** (prompt, historique, résultats d'outils), applique le filtre, **réserve** le coût maximal avant l'appel, injecte les réglages OpenRouter (`data_collection: deny`, `require_parameters: true`, `max_price`, liste de fournisseurs, `zdr` selon l'évaluation), transmet, puis **journalise** le coût réel de la réponse (y compris interrompue).
- Fail-closed : filtre ou budget indisponible, plafond atteint, secret détecté, clé absente → refus, jamais un envoi dégradé.
- Vérifié au lot 3 avec le vrai OpenClaw 2026.9.8 : un fournisseur personnalisé `cloudgw` à URL locale est accepté, `--model` par tour fonctionne, et la passerelle reçoit les résultats d'outils (un tour avec un outil = deux appels facturables). Détails et pièges dans `docs/PASSERELLE_CLOUD.md` (lot 3).

Le choix du modèle par requête utilise `openclaw agent --model <réf>`. Le raisonnement facturé est borné **par la passerelle**, qui injecte `reasoning` dans chaque requête : `--thinking low` est refusé pour un fournisseur personnalisé (vérifié avec OpenClaw 2026.9.8). Les 7 rôles sont conservés : pas d'agents dupliqués. Dans Open WebUI, chaque rôle apparaît en deux entrées (« · local », « · cloud ») : **le mode est le choix du modèle**. Avec `--model`, OpenClaw désactive ses replis configurés : le repli cloud → local est fait par notre code, donc visible.

## 5. Confidentialité

- Texte seulement : la passerelle chat refuse déjà les pièces jointes.
- Blocage (fail-closed) : clés et jetons à forme réelle, clés privées, chaînes de connexion avec mot de passe, `.env` avec valeurs à forte entropie, identifiants d'abonnement/tenant explicitement étiquetés et non factices, et **liste personnelle de termes sensibles** (fichier local, hors dépôt, droits 0600).
- Autorisé : plages d'adresses de documentation, adresses privées RFC 1918, `example.com`/`.test`, GUID factices ou à zéros. Les exemples de cours ne doivent pas être bloqués ; un jeu de tests de faux positifs (Terraform, Ansible, CI) fait partie du lot 5.
- Limite assumée : un filtre ne reconnaît pas ce qui est confidentiel sans forme de secret (config d'un employeur, nom d'un serveur interne). C'est le rôle du mode **Travail** et de la liste de termes sensibles. Le mode Apprendre l'indique par un avertissement visible.
- La clé OpenRouter vit dans un fichier à droits 0600 lu par la passerelle, jamais dans le dépôt, les patchs, les journaux ni la config d'OpenClaw.
- Les journaux n'enregistrent aucun contenu de message.
- GLM est édité par Z.ai : l'utilisateur a accepté l'envoi de contenu d'apprentissage public. Le `zdr` (non-rétention) est évalué séparément de `data_collection: deny` : il peut réduire la liste de fournisseurs disponibles.

## 6. Budget

Trois couches indépendantes :

1. **Achat** : crédits prépayés, sans rechargement automatique, total acheté ≤ 25 € TTC par mois. C'est le vrai plafond : OpenRouter ne peut pas débiter au-delà.
2. **Clé OpenRouter** : limite de crédit par clé (en dollars, avec marge pour le change, les frais d'achat de crédits et la TVA), erreur 402 à l'épuisement.
3. **Passerelle locale** : réservation avant appel (entrée estimée × prix + sortie maximale × prix, avec les prix de la config), journal de tous les appels, alerte à 80 %, arrêt à 100 % du plafond configuré en euros avec facteur de frais prudent.

Les tarifs sont une hypothèse à relire sur la page OpenRouter à l'achat (la promotion affichée sur GLM-5.3 Flash a expiré le 9 septembre 2026). Estimation indicative à confirmer par le journal : 100 appels/jour de 8 000 tokens en entrée et 1 500 en sortie ≈ 6 à 10 $ par mois.

## 7. Garde-fou d'activation

`cloud_enabled` est `false` par défaut. Une commande d'activation explicite exécute des **auto-contrôles** et refuse tant que l'un échoue :

- clé présente avec limite posée, plafond configuré et journal inscriptible ;
- filtre : un faux secret de test est bloqué, un exemple de cours passe ;
- budget : une requête qui dépasserait le plafond est refusée avant l'appel ;
- la passerelle cloud locale démarre et refuse tout sans clé.

## 8. Lots, branches et pull requests

Une branche et une PR en brouillon par lot ; aucune fusion automatique. Chaque PR dit ce que la CI prouve et ce qu'elle ne prouve pas.

| Lot | Contenu | État |
|---|---|---|
| 1 | Correctif des 8 outils + ce plan | [x] #33 |
| 2 | Prompts V2.3 réconciliés avec les contrôles de la PR #32 (reprise tracée) | [x] #34 |
| 3 | Fondation : catalogue, config OpenClaw (fournisseur OpenRouter via la passerelle locale), invariants `local_only`, démarrage hors ligne | [x] #35, repris sur `main` par #39 |
| 4 | Exécuteur multi-modèles : `--model`/`--thinking`, vérifications Ollama réservées au local, identité du modèle réellement utilisé, réparation JSON sur la même route | [x] #36 (déviation : la réparation JSON reste toujours locale) |
| 5 | Passerelle cloud locale et filtre (couvre prompt, historique, contexte, résultats d'outils) ; modes Apprendre/Travail dans Open WebUI | [x] #37 (déviation : un blocage du filtre répond 451, pas 403) |
| 6 | Budget : réservation, journal de tous les appels, plafonds, 402, auto-contrôles d'activation | [x] #38 |
| 7 | Atelier : accord explicite par projet, pause visible, affichage du modèle et du coût | [x] cette PR |
| 8 | Documentation (README, STATUS, fiches) | [ ] |

Déviations par rapport au plan initial : le raisonnement du modèle est borné par la passerelle (`--thinking` est refusé pour un fournisseur personnalisé) ; la réparation d'un JSON malformé reste locale ; un blocage du filtre répond 451 car 401/402/403/429 déclenchent la pause d'une minute du fournisseur côté OpenClaw.

Le cloud ne peut s'activer qu'après les lots 5 et 6 réunis. Hors périmètre pour l'instant, chacun sur nouvel accord : validateurs comme outils d'agent, contrôle des citations par extrait, Mistral Large 4 (avec sous-plafond), registre de compétences et révisions espacées, laboratoire d'exécution.

## 9. Ce qui ne sera pas prouvé par la CI

Qualité de GLM ou de Qwen, appel réel vers OpenRouter avec outils, comportement sur le PC Fedora et la carte B580. Un test de fumée manuel sera fourni après le lot 7 : réponse cloud avec modèle affiché, bascule en local, plafond atteint, démarrage hors ligne.

## 10. Étiquettes d'honnêteté pour les livrables

Les agents distinguent ce qui est **vérifié** de ce qui ne l'est pas : `terraform validate` ne vérifie que la cohérence interne (pas un `plan` ni un `apply` Azure) ; l'idempotence Ansible exige une cible jetable et deux exécutions (la seconde sans changement) ; un lint n'est ni un test ni un déploiement. Le contrat des prompts (lot 2) l'écrit.
