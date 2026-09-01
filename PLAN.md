# PLAN — Sonde des clés : supprimer les deux fausses alarmes Twitch

> État : **FAIT** (2026-09-01). Ce fichier décrit le chantier en cours ; par
> convention il se réécrit à chaque tâche.

## 1. Le problème

`tools/sonde_cles_partagees.py --vitalite` criait au feu tous les jours, deux fois :

1. **« plus de secours si data/ est perdu »** dès que le token d'ACCÈS du `.env`
   rendait 401. Or ce token dure ~4 h : le trouver périmé est *normal* et ne dit rien
   du secours. Le seul secours réel est le **refresh token**, et il était intact et
   identique des deux côtés chez les 3 bots Twitch.
2. **« 3 clés ne répondent plus »** (et sortie 1 en `--strict`) parce que les trois
   fichiers `data/twitch_chat_auth_*.json` rendaient 401 — uniquement parce que Docker
   Desktop était éteint depuis la nuit et que plus personne ne rafraîchissait.
   `shared/twitch/auth.py::get_valid_token` les rafraîchit au démarrage suivant.

Une sonde qui alarme pour un fonctionnement nominal est une sonde qu'on apprend à
ignorer — donc une sonde qui ne servira plus le jour où la panne est vraie.

## 2. Ce qui a été fait

**`amorce_env_reutilisable(bot, valeurs)`** remplace le test en ligne du token d'accès
du `.env`. Elle **compare par empreinte** le `TWITCH_REFRESH_TOKEN` du `.env` et celui
de `data/` — jamais en ligne : Twitch fait *tourner* le refresh à l'usage, le tester le
consommerait (invariant déjà tenu par
`test_aucune_sonde_ne_consomme_le_refresh_token_twitch`). États : `ok` /
`perimee` (le refresh a tourné, recopier celui de `data/`) / `absente` / `sans objet`.

**`token_twitch_vivant`** distingue désormais `perime` de `mort`, en lisant
`expires_at` avant de conclure :

| `expires_at` | validation | verdict | compté mort ? |
|---|---|---|---|
| — | 200 | `ok` | non |
| dépassé, refresh présent | 401 | `perime` (se rafraîchit seul) | **non** |
| dépassé, pas de refresh | 401 | `mort` (rejouer `twitch_authorize.py`) | oui |
| pas encore atteint | 401 | `mort` (révoqué côté Twitch) | oui |

## 3. Vérification

- **9 tests neufs** dans `tests/test_sonde_cles.py`, dont un garde anti-retour qui
  interdit à `vitalite()` de re-valider en ligne le token d'accès du `.env`.
- **Chacun vérifié par MUTATION** : le correctif retiré, le test tombe. C'est la seule
  preuve qu'un test prouve quelque chose.
- Sonde relancée en réel : verdict `OK : aucune cle partagee entre bots`, plus aucune
  ligne « ne répondent plus », les 3 amorces `.env` affichées comme intactes.
- Suite complète **530 tests verts**.

## 4. Reste à faire

Rien sur ce chantier. Pistes ouvertes ailleurs : purger le fond de sac de `MEMORY.md`
(beaucoup de fiches finissent par « Reste : test live »).
