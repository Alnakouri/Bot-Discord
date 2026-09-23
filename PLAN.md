# PLAN — La bio Twitch de Johnny, refusée par la modération chaque jour

Rédaction : Claude, le **2026-09-23**. Exécution : **Antigravity**, sauf les étapes marquées
**[Ahmed]**. Le plan précédent (phrase de lien : fiche sans date + clause Sugar) est livré
(`2bb82b5`, CI verte, en prod depuis le 23/09 13:32 UTC). Il reste lisible dans git
(`2bb82b5:PLAN.md`).

Deux fichiers de code, tous deux dans `shared/twitch/`, **non vendorés** (ni `profile` ni
`daily_profile` dans `tools/vendor_core.py`) : pas de `vendor_core.py` à relancer.
`profile.py` et `daily_profile.py` servent aux six bots, mais seuls Johnny et Sheogorath
passent un `profile_bio` (`JohnnyBot/bot_johnny.py:614`, `Sheogorath/bot_sheogorath.py:868`).

---

## CE QUI A ÉTÉ CONSTATÉ (23/09)

- À chaque démarrage (00:00, 01:18, 09:47, 13:32 le 23/09), Johnny journalise :
  `⚠️ [TWITCH_PROFILE:johnny] Erreur mise à jour bio (400): {... "message":"Description failed moderation."}`
- La bio envoyée n'est **pas** `TWITCH_BIO` : c'est celle que le LLM génère chaque jour
  (`shared/twitch/daily_profile.py:_generate_daily_profile`), gardée dans
  `data/twitch_profile_johnny.json`. Celle du 23/09 :
  « Johnny Silverhand en direct depuis le chaos : whisky, clopes et la dernière **putain** de
  corporation à faire **péter**. … »
- **Le repli n'existe pas** : un refus est journalisé, puis rien. La bio de Johnny sur
  Twitch reste celle d'un jour ancien, sans que rien ne le signale hors du journal.
- **`TWITCH_BIO` passe la modération** : essayé le 23/09 par Claude dans le conteneur de
  Johnny, avec son propre jeton → `✅ Description mise à jour avec succès.` C'est la bio en
  ligne en ce moment.
- Sugar n'a pas de `profile_bio` : son repli est la chaîne vide, et il doit le rester
  (aucune bio envoyée plutôt qu'une bio vide).

---

# LOT 1 — `update_profile` dit si la bio a été REFUSÉE par la modération

`shared/twitch/profile.py`, méthode `update_profile` (l.15).

1. Signature : `-> str | None`. Docstring, ajouter :
   « Rend `"bio_refusee"` si Twitch a refusé la bio par sa modération (400
   « failed moderation »), sinon `None`. La couleur n'entre pas dans ce retour. »
2. Initialiser `resultat = None` **juste avant** `async with aiohttp.ClientSession() as session:` (l.32).
3. Dans la branche `else:` de la bio (l.44-46), **après** le `self.logger.warning(...)` existant :

```python
                            if resp.status == 400 and "moderation" in err_text.lower():
                                resultat = "bio_refusee"
```

4. Tout en bas de la méthode (après le bloc couleur, l.77), **hors** du `async with`, au
   même niveau d'indentation que `async with` : `return resultat`.

⚠️ Les deux `return` anticipés (l.20 et l.25) rendent déjà `None` : ne pas y toucher.
⚠️ Le bloc couleur doit continuer à s'exécuter après un refus de bio (la couleur, elle,
passe) : **pas** de `return` dans la branche bio.

---

# LOT 2 — Sur refus, `_ensure_daily_profile` retombe sur la bio FIXE, et la garde

`shared/twitch/daily_profile.py`, `_ensure_daily_profile`, **avant** (l.165-168) :

```python
            # Application du profil
            if self.profile_helper:
                await self.profile_helper.update_profile(bio=bio, chat_color=color)
                self._profile_day = today
```

**après** :

```python
            # Application du profil
            if self.profile_helper:
                resultat = await self.profile_helper.update_profile(bio=bio, chat_color=color)
                # ⚠️ 23/09 : la bio GENEREE de Johnny (juron + appel a « faire peter » une
                # corpo) etait refusee par la moderation Twitch a chaque demarrage, et rien
                # ne suivait : sa bio restait celle d'un vieux jour. On retombe sur la bio
                # FIXE du bot et on l'ECRIT dans l'etat du jour, sinon chaque redemarrage
                # renverrait la bio refusee. Pas de bio fixe (Sugar) : on n'envoie rien.
                # ⚠️ Comparer a la CHAINE : un AsyncMock rend un MagicMock, qui est vrai.
                repli = getattr(self, "profile_bio", None) or ""
                if resultat == "bio_refusee" and repli and bio != repli:
                    self.logger.warning(
                        f"⚠️ [TWITCH_CHAT:{self.bot_id}] Bio du jour refusee par la moderation "
                        f"Twitch : repli sur la bio fixe."
                    )
                    await self.profile_helper.update_profile(bio=repli)
                    self._save_profile_state({"date": today, "bio": repli, "color": color})
                self._profile_day = today
```

⚠️ **Piège 1** : `resultat == "bio_refusee"`, **pas** `if resultat:`. Les tests existants
mockent `profile_helper` par `AsyncMock()`, dont l'`await` rend un `MagicMock` **vrai** :
`if resultat:` déclencherait le repli dans les 4 tests existants.
⚠️ **Piège 2** : le second appel ne repasse **pas** `chat_color` : la couleur est déjà posée.
⚠️ **Piège 3** : `bio != repli` empêche une boucle si la bio fixe était elle-même refusée un
jour : un seul repli, jamais deux.
⚠️ `getattr(..., "profile_bio", None)` : l'hôte de test `_Host` n'a pas cet attribut.

---

# LOT 3 — Le prompt demande une bio qui passe la modération

`shared/twitch/daily_profile.py:67`, **avant** :

```python
            f'{{"bio": "<1-2 phrases, 1re personne, en personnage, ≤280 caractères, sans guillemets ni didascalies>", '
```

**après** :

```python
            f'{{"bio": "<1-2 phrases, 1re personne, en personnage, ≤280 caractères, sans guillemets ni didascalies, '
            f'sans juron ni appel à la violence : elle doit passer la modération de Twitch>", '
```

Pourquoi en plus du LOT 2 : sans lui, Johnny n'aurait **plus jamais** de bio du jour, le
repli la remplacerait chaque matin. Le LOT 2 reste le filet : le prompt réduit les refus,
il ne les supprime pas.
⚠️ Aucun mot interdit n'est **cité** dans la consigne : une formule écrite dans le prompt
ressort dans la sortie.

---

# LOT 4 — Tests

## 4.1 — `tests/test_twitch_daily_profile.py`

Ne **pas** toucher à `_Host` (il reste sans `profile_bio` : c'est le cas Sugar). Ajouter,
après `_Host` :

```python
class _HostAvecRepli(_Host):
    """Un bot qui a une bio FIXE (Johnny) et dont la bio du jour est refusee."""

    def __init__(self):
        super().__init__()
        self.profile_bio = "bio fixe qui passe"
        self.profile_helper.update_profile = AsyncMock(side_effect=["bio_refusee", None])
```

Et dans `TestDailyProfileCache` :

1. `test_bio_refusee_retombe_sur_la_bio_fixe` : `_HostAvecRepli`, `_ensure_daily_profile()`.
   Vérifier : `update_profile.await_count == 2` ; `await_args_list[1] == call(bio="bio fixe qui passe")`
   (importer `call` de `unittest.mock`) ; l'état persistant a `bio == "bio fixe qui passe"`
   et `color == "blue_violet"`.
2. `test_bio_refusee_sans_bio_fixe_n_envoie_rien_de_plus` : `_Host`, avec
   `host.profile_helper.update_profile = AsyncMock(return_value="bio_refusee")`.
   Vérifier `await_count == 1` et l'état garde `"ma bio du jour"`.
3. `test_bio_acceptee_pas_de_repli` : `_HostAvecRepli` puis
   `host.profile_helper.update_profile = AsyncMock(return_value=None)` → `await_count == 1`.
4. `test_redemarrage_apres_repli_n_appelle_pas_le_llm` : après le cas 1, un **nouvel**
   `_HostAvecRepli` avec `update_profile = AsyncMock(return_value=None)` :
   `gen_calls == 0` et `update_profile` attendu avec `bio="bio fixe qui passe"`.

## 4.2 — Nouveau `tests/test_twitch_profile_moderation.py`

`TwitchProfile("johnny", logger, "cid", auth)` avec `auth.get_valid_token = AsyncMock(return_value="tok")`.
Patcher `shared.twitch.profile.aiohttp.ClientSession` pour que `session.put(...)` rende
(en contexte async) une réponse `status=400` dont `text()` rend
`'{"status":400,"message":"Description failed moderation."}'`.
- `update_profile(bio="x")` → `== "bio_refusee"` ;
- même montage avec `"message":"Invalid parameter"` → `is None` ;
- `status=200` → `is None`.

Seul modèle existant dans la suite qui patche `ClientSession` : `tests/test_laya_client.py`.
⚠️ Aucun appel réseau réel : si le patch est mal posé, le test doit échouer, pas appeler Twitch
(`get_valid_token` mocké garantit qu'aucun vrai jeton n'est lu).

---

# LOT 5 — Vérifier, dans cet ordre

1. `python -m pyflakes shared/twitch/profile.py shared/twitch/daily_profile.py tests/test_twitch_daily_profile.py tests/test_twitch_profile_moderation.py`
2. La suite complète, **un seul pytest à la fois** (port 8599) :
   `uv run --no-project --python 3.11 --with-requirements requirements.txt -- python -m pytest -q`
   Attendu : tout vert.
3. Commit, push, puis **`gh run list --limit 1` → `success`**. Rien n'est livré avant.

---

# LOT 6 — Prod **[Ahmed : hors live]**

`docker restart bot-johnny bot-sheogorath` (les deux seuls bots avec une bio fixe ; les
autres ne changent pas de comportement, inutile de les redémarrer).

⚠️ Le profil du 23/09 est déjà dans `data/twitch_profile_johnny.json` avec la bio refusée :
au redémarrage, elle est renvoyée, refusée, puis **remplacée** par la bio fixe — c'est le
test en vrai. Dans `docker logs --since 5m bot-johnny`, attendre :
`Bio du jour refusee par la moderation Twitch : repli sur la bio fixe.` puis
`✅ [TWITCH_PROFILE:johnny] Description mise à jour avec succès.`
Au redémarrage suivant : plus aucun `failed moderation`.

---

## RESTE DES PLANS PRÉCÉDENTS

- **LOT 7 du 22/09 [Ahmed]** — recréer `.venv` en 3.11 (aujourd'hui 3.13 sans pyflakes) :
  `uv venv --python 3.11 .venv` puis
  `uv pip install --python .venv\Scripts\python.exe -r requirements.txt`.
- **Questions ouvertes** : (1) Sheogorath réagit par emoji aux messages des AUTRES bots
  (`bot_sheogorath.py`, réactions avant la garde `author.bot`) — voulu ? (2) la borne de
  300 ms de Laya (Laya est GARDÉ, décision d'Ahmed du 23/09).
- Petite dette : `610fdac` pose un attelage factice par `setdefault` sur
  `runner._ATTELAGES` sans le retirer (fuite d'état entre tests ; `monkeypatch` serait propre).
- **À lire après le live du 23/09 au soir** : les lignes
  `Phrase de lien !discord (jeu : …) écrite par le bot` de Sugar et Johnny (première
  mesure réelle de `2bb82b5`) ; le tic « boue / médiéval » n'est à traiter que s'il se voit.

## INTERDITS DE CE PLAN

- Aucun `.env`, `.master_key`, `.env.encrypted`, ni base de `data/` touché — y compris
  `data/twitch_profile_*.json` : c'est le code qui le réécrit, pas l'exécutant.
- Aucun jeton d'un bot utilisé pour un autre.
- Aucun import entre bots ; aucune factorisation.
- Ne pas changer `TWITCH_BIO` de Johnny : elle passe la modération (vérifié le 23/09).
- **Un seul `pytest` à la fois.** Aucun lot « livré » tant que la CI n'est pas `success`.
