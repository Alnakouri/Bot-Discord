# 🤵 Démo web d'Alfred

Une page où l'on parle à Alfred sans compte Discord. Un Cloudflare Worker sert la page et appelle le modèle, pour que la clé d'API ne quitte jamais le serveur.

## Ce qui vient du vrai bot

- **Persona** : `generer_persona.py` la dérive de `Alfred/alfred_data.py`, moins ce qui n'a pas de sens hors de Discord (duels, mentions), plus un cadre propre à une page publique.
- **Filtre de sortie** : `src/filtre.js` porte `Alfred/alfred_filtres.py`. `tests/test_demo_alfred.py` compare les deux versions sur 630 textes.
- **Cascade** : si un modèle refuse, le suivant répond. Seuls les échelons Groq sont repris, car les conditions de Gemini interdisent son offre gratuite pour des utilisateurs de l'Espace économique européen.

La mémoire, la modération et la voix restent sur Discord. Rien n'est stocké : la page renvoie elle-même les derniers messages à chaque tour.

## Le dashboard, en démo

`/dashboard/` sert le vrai front du dashboard (`dashboard/frontend/`), branché sur un faux backend : `dashboard/demo.js` remplace `fetch` et `WebSocket` dans le navigateur, avec des données inventées gardées en mémoire. Les boutons marchent, mais sur cette copie : aucun bot n'est touché, et recharger la page remet tout à zéro. La CSP de `/dashboard/` interdit toute requête réseau.

`generer_dashboard.mjs` copie le front dans `site/dashboard/`, retouche `index.html` (bandeau, lien de retour, chargement du faux backend), puis refuse de terminer s'il trouve un identifiant Discord, une clé d'API, ou un nom, salon ou serveur tiré de `data/`. À relancer après toute retouche du front :

```bash
node demo-alfred/generer_dashboard.mjs
```

## Limites voulues

| Limite | Valeur |
|---|---|
| Longueur d'un message | 300 caractères |
| Historique envoyé | 6 messages |
| Cadence | 6 messages par minute et par visiteur |
| Délai par modèle | 8 secondes |

Quand tous les modèles refusent, Alfred répond par un message d'attente au lieu d'afficher une erreur.

## Tests

```bash
cd demo-alfred && npm test
python -m pytest tests/test_demo_alfred.py -q   # depuis la racine du dépôt
```

Après toute retouche de la fiche d'Alfred : `python demo-alfred/generer_persona.py`.

## Déploiement

Il faut un compte Cloudflare gratuit et une clé Groq **réservée à cette démo** (voir la règle « une clé par bot » dans `AGENTS.md`).

`site/dashboard/` n'est pas versionné : il se régénère avant chaque envoi.

```bash
node demo-alfred/generer_dashboard.mjs
cd demo-alfred
npx wrangler@4 login
npx wrangler@4 secret put GROQ_KEY_DEMO
npx wrangler@4 versions upload    # donne une adresse d'aperçu à tester
npx wrangler@4 versions deploy <id-de-version>@100%
```
