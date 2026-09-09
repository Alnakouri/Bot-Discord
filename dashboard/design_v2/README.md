# Dashboard v2 — la maquette

Deux fichiers, déposés ici le **2026-09-09** pour que la direction artistique ne vive plus
uniquement dans `~/Downloads`.

| Fichier | Quoi |
|---|---|
| `maquette_autonome.html` | Le bundle Claude Design tel qu'exporté (1,6 Mo). **Double-cliquer pour voir le design.** Il se dépaquette tout seul au chargement. |
| `maquette_source.jsx` | Le seul code qui compte : les 28 Ko de la page, extraits du bundle. C'est la référence pour le portage. |

## ⚠️ Ce que la maquette N'EST PAS

**Ce n'est pas un dashboard qui marche.** Vérifié en dépaquetant le bundle :

- **zéro** `fetch`, `XMLHttpRequest`, `WebSocket` ou `window.claude` dans le code de la page ;
- **zéro** chaîne `/api/` ;
- toutes les données sont des constantes en dur en tête de fichier : `STATE` (les 6 bots),
  `ERRORS`, `KEYS`, `LOGS`, `AUDIT`, `REPORT`, `FEATURES`, `TWITCH_PANELS`, `SUBS`,
  `TOP_USERS`, `LEVELS`.

Faire pointer le raccourci du Bureau dessus donnerait une belle page **morte** : pas
d'authentification, pas d'état réel des bots, aucun bouton qui agit.

## Ce qu'elle EST

Une maquette **complète et navigable** : c'est une classe React avec `setState`, donc les
onglets fonctionnent. Les 8 entrées de navigation couvrent exactement les sections du
dashboard actuel — `overview`, `logs`, `errors`, `api-keys`, `conversations`, `reports`,
`audit-logs`, `bot-config` (qui contient les 5 onglets Twitch).

C'est donc un **reskin**, pas un changement de fonctionnalité : les 48 routes de
`backend/app.py` ne bougent pas. Le portage est mécanique, section par section.

## Contenu du bundle, si besoin de le redépaquetter

Le bundle contient, en plus de la page : Chart.js 4.4.1, React 18.3.1 + ReactDOM (UMD), le
`dc-runtime` de Claude Design, et 22 fontes (Inter & co) — d'où les 1,6 Mo. Les blocs utiles
sont les `<script type="__bundler/template">` (la page, en JSON) et
`<script type="__bundler/manifest">` (les assets, base64 + gzip).
