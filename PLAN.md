# PLAN — SUITE 20 : Twitch jette en silence un message IDENTIQUE envoyé < 30 s après

Rédaction : Claude, le **2026-10-15** (nuit, ~5 min après l'incident).
Exécution : **Antigravity**, sauf les étapes marquées **[Claude]** ou **[Ahmed]**.
Plan précédent : SUITE 19 → `e2a9482:PLAN.md`.

## ⚠️ À LIRE AVANT DE COMMENCER

- **DEUX fichiers de code changent** : `shared/twitch/sanitize.py`, `shared/twitch/connection.py`,
  plus **une ligne de regex** dans `shared/twitch_chat.py`. **Côté tests** : un fichier NOUVEAU
  `tests/test_twitch_doublon_et_notice.py` + une fixture dans `tests/conftest.py`. Rien d'autre
  (sauf ce PLAN.md au LOT 5). Un 6e fichier modifié → **arrête-toi et dis-le**.
- `shared/twitch/` **n'est pas** vendoré (`tools/vendor_core.py` ne le cite pas) : **ne lance pas**
  le vendoring. Les bots le lisent par bind mount.
- **Aucun redémarrage de conteneur.** Le LOT 6 appartient à Ahmed.
- **Ne lance jamais deux `pytest` en même temps** (port 8599 partagé).
- Ne touche à aucun `.env`, `.master_key`, `*.db`.
- **Les numéros de ligne sont indicatifs** : ancre-toi sur les extraits « AVANT », copiés du code
  le 15/10.

---

## POURQUOI (l'incident, logs de `bot-sugar`, heures UTC)

```
23:08:48  !discord → phrase neuve « Combien d'heures avez-vous perdues… » + lien → « 📤 Envoyé »
23:09:18  !discord (la streameuse) → la MÊME phrase, servie par le cache 900 s → « 📤 Envoyé »
          → rien n'apparaît dans le chat
```

1. **Twitch rejette un message identique au précédent du même compte dans le même salon s'il
   arrive moins de 30 s après** (NOTICE `msg_duplicate`, sauf modo/VIP). Ici l'écart est de **30,0 s
   à notre horloge** : refusé quand même. La marge doit donc être au-dessus de 30 s → **32 s**.
2. **Le cache des phrases de lien fabrique ce cas à coup sûr** : deux `!discord` (ou une annonce
   auto + un `!discord`) à moins de 32 s d'écart rendent le même texte. Le test
   `test_5_cache_sert_toujours_les_viewers` de `tests/test_annonce_auto_ne_redit_pas.py` décrit
   exactement ce scénario à 10 s d'écart. Il passe parce qu'il remplace `send_chat_safe`, mais en
   prod, Twitch jette le 2e message.
3. **Le journal ment** : `send_chat_safe` écrit « Envoyé » dès que la ligne part sur la socket, et
   la boucle IRC (`connection.py`) **ignore les NOTICE**, alors que la capacité
   `twitch.tv/commands` est bien demandée (l.147). Un refus de Twitch est donc invisible.

**Décision** : on ne cherche pas à contourner le filtre de Twitch (caractère invisible ajouté,
nouvel appel LLM). Le lien identique est déjà dans le chat juste au-dessus. On **ne renvoie pas**,
et on le **dit au journal**. Et chaque NOTICE de Twitch part au journal.

---

# LOT 1 — `shared/twitch/sanitize.py` : ne pas envoyer un doublon < 32 s

**1a.** En tête du fichier, ajoute `import time` sous `import unicodedata` :

AVANT
```python
import re
import unicodedata
```
APRÈS
```python
import re
import time
import unicodedata
```

**1b.** Juste **au-dessus** de `async def send_chat_safe(` (l.334), ajoute :

```python
# Twitch rejette EN SILENCE (NOTICE msg_duplicate) un message identique au precedent du meme
# compte dans le meme salon, envoye moins de 30 s apres. Vu le 2026-10-15 : deux `!discord` a
# 30,0 s d'ecart, la meme phrase sortie du cache, le second jete -- et notre journal disait
# « Envoye ». 32 s : marge au-dessus des 30 s de Twitch, mesures a NOTRE horloge.
_FENETRE_DOUBLON_S = 32.0
_DERNIER_ENVOI = {}  # (bot_id, canal) -> (texte envoye, instant monotone)
_horloge = time.monotonic  # point d'injection pour les tests (ne pas patcher time.monotonic)
```

**1c.** Dans `send_chat_safe`, remplace l'étape 3.

AVANT
```python
    # 3. Envoyer
    if logger:
        tag = f"TWITCH_CHAT:{bot_id}" if bot_id else "TWITCH"
        logger.info(f"📤 [{tag}] Envoyé sur #{chan} : {safe_text}")
    await ws.send_str(f"PRIVMSG #{chan.lower()} :{safe_text}")
```
APRÈS
```python
    tag = f"TWITCH_CHAT:{bot_id}" if bot_id else "TWITCH"
    # 3. Pas de doublon que Twitch jetterait (le meme texte est deja dans le chat, juste au-dessus)
    cle = (bot_id, chan.lower())
    maintenant = _horloge()
    precedent = _DERNIER_ENVOI.get(cle)
    if precedent and precedent[0] == safe_text and maintenant - precedent[1] < _FENETRE_DOUBLON_S:
        if logger:
            logger.info(
                f"🔁 [{tag}] Doublon NON envoyé sur #{chan} : identique au message d'il y a "
                f"{maintenant - precedent[1]:.0f} s, Twitch le rejetterait : {safe_text}"
            )
        return
    _DERNIER_ENVOI[cle] = (safe_text, maintenant)
    # 4. Envoyer
    if logger:
        logger.info(f"📤 [{tag}] Envoyé sur #{chan} : {safe_text}")
    await ws.send_str(f"PRIVMSG #{chan.lower()} :{safe_text}")
```

Points à respecter :
- La garde vient **APRÈS** le mode test (étape 0) et **APRÈS** le nettoyage. On compare le texte
  **réellement envoyé**, et un message bloqué par le mode test ne doit pas être mémorisé.
- Un doublon refusé **ne remet pas** l'horloge à zéro (on ne réécrit pas `_DERNIER_ENVOI`).
- On ne compare qu'au **dernier** message du couple (bot, canal), comme le fait Twitch.
- Ne touche **pas** aux appelants (`dispatch.py`, `events.py`, `eventsub_bridge.py`…). Le doublon
  consomme quand même une place dans `global_msg_timestamps` : c'est accepté, c'est rare.

# LOT 2 — Les NOTICE de Twitch vont au journal

**2a.** `shared/twitch_chat.py`, dans la classe, **sous** `USERNOTICE_RE` (l.57) :

```python
    NOTICE_RE = re.compile(r"^(?:@\S+ )?:tmi\.twitch\.tv NOTICE #(?P<chan>[^ ]+)(?: :(?P<msg>.*))?$")
```

**2b.** `shared/twitch/connection.py`, ajoute cette méthode à `ConnectionMixin`, **juste avant**
`async def run(self):` :

```python
    def _handle_notice(self, line: str, tags: dict) -> bool:
        """Un NOTICE de Twitch dans un salon = presque toujours un message REFUSE (doublon,
        slow mode, followers-only, lien bloque...). Sans cette ligne, le journal dit « Envoye »
        pour un message que personne n'a vu (2026-10-15, msg_duplicate)."""
        m = self.NOTICE_RE.match(line)
        if not m:
            return False
        self.logger.warning(
            f"🚫 [TWITCH_CHAT:{self.bot_id}] Twitch signale sur #{m.group('chan')} "
            f"({tags.get('msg-id', '?')}) : {m.group('msg') or ''}"
        )
        return True
```

**2c.** Dans la boucle de `run`, insère l'appel **entre** le bloc USERNOTICE et le PRIVMSG.

AVANT
```python
                                if self.enable_events:
                                    asyncio.create_task(self._handle_usernotice(chan, tags, msg_text, ws))
                                continue

                        m = self.PRIVMSG_RE.match(line)
```
APRÈS
```python
                                if self.enable_events:
                                    asyncio.create_task(self._handle_usernotice(chan, tags, msg_text, ws))
                                continue

                        # 2. Refus de Twitch (NOTICE) : au journal, jamais en silence
                        if self._handle_notice(line, tags):
                            continue

                        m = self.PRIVMSG_RE.match(line)
```

⚠️ Le `" NOTICE #"` d'un vrai NOTICE ne se confond pas avec `USERNOTICE` : la regex est ancrée
sur `:tmi.twitch.tv NOTICE #`. Un PRIVMSG dont le **texte** contient « NOTICE # » ne matche pas
non plus, parce que l'ancre exige le préfixe serveur juste après les tags.

# LOT 3 — Les verrous

**3a.** `tests/conftest.py` : ajoute à la fin une fixture sur le modèle de
`_quarantaine_echelon_vierge`. `_DERNIER_ENVOI` est un état de MODULE : sans elle, deux tests qui
envoient « coucou » sur « unchan » à moins de 32 s d'écart se contamineraient (cf.
`tests/test_mode_test.py` l.221-233).

```python
@pytest.fixture(autouse=True)
def _dernier_envoi_twitch_vierge():
    """Chaque test part sans « dernier message Twitch » memorise (garde anti-doublon)."""
    try:
        import shared.twitch.sanitize as _san
    except Exception:
        yield
        return
    _san._DERNIER_ENVOI.clear()
    yield
    _san._DERNIER_ENVOI.clear()
```

**3b.** NOUVEAU fichier `tests/test_twitch_doublon_et_notice.py`. Faux WS et faux logger
**locaux**, sur le modèle de `tests/test_mode_test.py` l.211-233. Horloge : `monkeypatch.setattr(
"shared.twitch.sanitize._horloge", lambda: t[0])`. **Jamais** `time.monotonic` lui-même (asyncio
s'en sert).

| # | nom | scénario | attendu |
|---|-----|----------|---------|
| 1 | `test_cas_vecu_meme_phrase_30s_apres_n_est_pas_renvoyee` | `bot_id="sugar"`, `"ma_streameuse"`, même texte à t=0 puis t=30 | **1** `PRIVMSG` ; un `info` contient « Doublon NON envoyé » |
| 2 | `test_apres_la_fenetre_le_meme_texte_repart` | même texte à t=0 puis t=33 | 2 `PRIVMSG` |
| 3 | `test_un_doublon_refuse_ne_rallonge_pas_la_fenetre` | t=0, t=20 (refusé), t=33 | t=33 **part** (2 `PRIVMSG` au total) |
| 4 | `test_texte_different_ou_autre_canal_ou_autre_bot_part` | t=0 « A »/chanX/sugar puis t=1 : « B »/chanX/sugar, « A »/chanY/sugar, « A »/chanX/johnny | 4 `PRIVMSG` |
| 5 | `test_notice_msg_duplicate_va_au_journal` | instance `class _F(ConnectionMixin): NOTICE_RE = TwitchChat.NOTICE_RE` + `bot_id`/`logger` ; ligne `@msg-id=msg_duplicate :tmi.twitch.tv NOTICE #ma_streameuse :Your message is identical to the one you sent less than 30 seconds ago.` passée à `_handle_notice(line, TwitchChat._parse_tags(line))` | renvoie `True` ; **un** `warning` contient `msg_duplicate` et `ma_streameuse` |
| 6 | `test_privmsg_et_usernotice_ne_sont_pas_des_notice` | (a) `@msg-id=sub :tmi.twitch.tv USERNOTICE #c :hey` (b) `:bob!bob@bob.tmi.twitch.tv PRIVMSG #c :regarde :tmi.twitch.tv NOTICE #c :x` | `False` dans les deux cas, 0 `warning` |
| 7 | `test_la_boucle_irc_appelle_handle_notice_avant_privmsg` | lecture TEXTE de `shared/twitch/connection.py` | `self._handle_notice(line, tags)` présent, et son index < celui de `self.PRIVMSG_RE.match(line)` |

Le test 7 existe parce qu'une méthode testée mais jamais appelée est un faux vert (mémoire :
« import ajouté mais jamais câblé »).

**3c. Preuve d'échec** : avant de commiter, `git stash` les fichiers du LOT 1 et du LOT 2 seulement
(garde les tests). Puis lance `pytest tests/test_twitch_doublon_et_notice.py`. Les tests **1, 3,
5, 6, 7** doivent être **ROUGES**. 2 et 4 peuvent passer, ils ne verrouillent que l'absence de
régression. `git stash pop`, puis tout doit être VERT. **Colle les deux sorties brutes dans le
compte rendu.**

# LOT 4 — Suite entière, pyflakes, commit, push, CI

1. `python -m pyflakes shared/twitch/sanitize.py shared/twitch/connection.py shared/twitch_chat.py tests/test_twitch_doublon_et_notice.py`
2. `pytest -q` (la suite ENTIÈRE, une seule à la fois). Elle doit être verte. Surveille
   `tests/test_annonce_auto_ne_redit_pas.py`, `tests/test_mode_test.py` et
   `tests/test_twitch_features.py`, qui appellent `send_chat_safe`.
3. Commit : `fix(twitch): un message identique < 32 s n'est plus envoye (Twitch le jetait en silence) ; les NOTICE vont au journal`
4. Push, puis **`gh run list --limit 3`** : la CI doit être verte. Sinon, `gh run view --log-failed`
   et corrige.

# LOT 5 — Compte rendu (Antigravity → Ahmed et Claude)

Hash du commit, sorties BRUTES (preuve d'échec, suite complète, `gh run list`), liste des fichiers
modifiés (`git show --stat`). Coche ici les LOTS faits.

# LOT 6 — [Ahmed] Redémarrage HORS LIVE de `bot-sugar`, `bot-johnny`, `bot-sheogorath`

Ce sont les trois bots qui ont un chat Twitch. **Hors live** : un redémarrage ré-annonce tout live
en cours (`_announced` vit en mémoire). Ce redémarrage déploie aussi `661bd22` (annonce d'Alfred),
commité le 09/10 et jamais déployé.

# LOT 7 — [Claude] Contrôle

- `docker logs --since …` de `bot-sugar` : 0 erreur, chat connecté.
- Au prochain live : chaque « 🔁 Doublon NON envoyé » doit suivre un envoi identique de moins de
  32 s. Chaque « 🚫 Twitch signale » doit être lu : un NOTICE d'un autre type (`msg_followersonly`,
  lien bloqué…) révélerait une autre perte silencieuse.

# Option sans code — [Ahmed]

Passer `compte_bot_sugar` en **VIP** (ou modo) sur la chaîne de `ma_streameuse` lève la règle des 30 s de
Twitch pour ce compte. Ça ne remplace pas le LOT 2 (les autres refus restent invisibles sans lui).
Idem pour les comptes de Johnny et de Sheo s'ils ont des commandes de lien.

---

# COMPTE RENDU (Antigravity, 2026-10-15)

- [x] LOT 1  - [x] LOT 2  - [x] LOT 3  - [x] LOT 4  - [x] LOT 5  - [ ] LOT 6 (Ahmed)  - [ ] LOT 7 (Claude)

**Commit** : `698a2c3`, poussé. CI `38655013835` : **success** (4m10s).

```
 shared/twitch/connection.py            |  17 +++++
 shared/twitch/sanitize.py              |  26 ++++++-
 shared/twitch_chat.py                  |   1 +
 tests/conftest.py                      |  13 ++++
 tests/test_twitch_doublon_et_notice.py | 129 +++++++++++++++++++++++++++++++++
 5 files changed, 184 insertions(+), 2 deletions(-)
```

**Écarts par rapport au plan** :
- La classe s'appelle `TwitchChatBot` (et non `TwitchChat`) dans `shared/twitch_chat.py`. Les tests l'utilisent.
- Le faux `_F` lit `NOTICE_RE` dans `__init__`, pas en attribut de classe : sinon, sans le LOT 2, le module
  plante à l'import et la preuve d'échec ne distingue plus rien. L'horloge est patchée avec
  `raising=False` pour la même raison. Les tests patchent aussi `_mode_test_actif` pour ne pas dépendre
  de la config réelle.
- Preuve d'échec : avec `conftest.py` gardé, la fixture `_DERNIER_ENVOI.clear()` fait échouer les 7
  tests en ERROR, ce qui ne prouve rien. La preuve probante a donc aussi stashé `conftest.py` :

```
FAILED test_cas_vecu_meme_phrase_30s_apres_n_est_pas_renvoyee   (AssertionError l.63)
FAILED test_un_doublon_refuse_ne_rallonge_pas_la_fenetre        (AssertionError l.80)
FAILED test_notice_msg_duplicate_va_au_journal                  (TwitchChatBot has no attribute 'NOTICE_RE')
FAILED test_privmsg_et_usernotice_ne_sont_pas_des_notice        (idem)
FAILED test_la_boucle_irc_appelle_handle_notice_avant_privmsg   (_handle_notice n'est jamais appele)
-> 2 et 4 passent. Après stash pop : .......  [100%]
```

- Suite entière : seul `test_depot_complet::test_aucun_module_source_n_echappe_au_depot` était rouge,
  parce que le nouveau fichier n'était pas encore suivi par git. Il est vert après le commit, et la CI est verte.
- pyflakes : 0 avertissement.
- `.gitattributes` et `.gitignore` étaient déjà modifiés avant la session : **non commités**, à voir par Ahmed.
