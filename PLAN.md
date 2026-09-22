# PLAN — Audit du 22/09 : la CI est rouge depuis 4 jours, et le reste

Rédaction : Claude, le **2026-09-22** au soir — audit complet en lecture seule, aucune ligne
de code source modifiée. Exécution : **Antigravity**, sauf les étapes marquées **[Ahmed]**.
Le plan précédent (« Les astérisques ») était entièrement livré ; il reste dans l'historique
git (`3e3c91e`).

---

## CE QUE L'AUDIT A MESURÉ

| contrôle | résultat |
|---|---|
| **CI GitHub** | ❌ **rouge sur 48 pushs d'affilée**, depuis `c61bdb4` (18/09 23:12 UTC). Dernier vert : `d4cf565`. Les rapports de session annonçaient « 1304 verts » : c'était le LOCAL. |
| suite en Python **3.12** (= CI, env neuf) | 1300 ✅ / **4 ❌** (`test_laya_chauffe.py` : `No module named 'fastapi'`) |
| suite en Python **3.11** (= PROD, env neuf) | idem — aucune incompatibilité de version |
| 3.11 + fastapi + **cryptography 50.0.1** | **1304 ✅ / 0 ❌** — les corrections des LOTS 1.2 et 5 sont déjà validées |
| copie propre de HEAD (= clone CI) | `test_eval_harness.py::test_le_dossier_du_bot_est_DEDUIT…` ❌ : il exige un `.env.encrypted`, fichier **gitignoré** |
| compilation, caractères de contrôle, sondes bloquantes et de dérive, vendoring | ✅ |
| `sonde_cles_partagees.py --strict` | ✅ aucune clé partagée (10 variables) ; les identifiants **Twitch** — non surveillés par la sonde — sont aussi tous distincts |
| secrets dans git (tout l'historique) | ✅ aucun `.env`, `.master_key`, `.db` jamais commité |
| imports croisés entre bots | ✅ zéro |
| prod | ✅ les 6 conteneurs tournent sur le code de HEAD (le dernier commit n'ajoute que des commentaires) |
| pip-audit | ⚠️ cryptography 46.0.7 (OpenSSL embarquée vulnérable, corrigée en 48.0.1) **bloquée par `<47.0.0`** |
| dashboard (navigateur + API) | ⚠️ fenêtres de temps fausses, quarantaines invisibles, traversée de chemin (LOTS 3 et 4) |
| documentation | ❌ AGENTS.md **ordonne de garder WAL** — le code l'interdit depuis le 13/09 |
| **live `#ma_streameuse`, 22/09** | ❌ Sugar affirme « le treizième siècle » pour KCD2 (1403, XVe) — corrigée par un spectateur (LOT 1bis) |

**Ordre imposé** : LOT 1 d'abord, puis le LOT 1bis (vu en direct, promis au chat). Tant que
la CI est rouge, aucun autre lot ne peut être déclaré livré — c'est exactement ce qui s'est
passé pendant 4 jours.

---

# LOT 1 — La CI au vert (P0)

## 1.1 — Le harnais REFUSE un bot sans clés, au lieu d'un test qui exige un fichier gitignoré

**Le défaut réel** est dans `tests/eval/runner.py:120-124` :

```python
    dossier = _dossier_du_bot(bot_id)
    try:
        load_secure_env(dossier)
    except Exception as e:
        print(f"Avertissement : cles de {bot_id} illisibles ({dossier.name}) : {e}")
```

⚠️ `load_secure_env` (`shared/secure_env.py:11-75`) **ne lève jamais** : sans `.env`, sans
`.env.encrypted` ou sans `.master_key`, il **rend `False`**. Le `try/except` ne se déclenche
donc jamais, et le harnais mesure en silence avec les clés du bot chargé AVANT — le défaut
que `c61bdb4` voulait fermer. Le test de `c61bdb4` le gardait en exigeant le fichier sur le
disque : vrai chez Ahmed, faux sur tout clone.

**Remplacer les lignes 121-124 par :**

```python
    if not load_secure_env(dossier):
        raise RuntimeError(
            f"{bot_id} : aucune cle lisible dans {dossier} — le harnais refuse de mesurer "
            "avec les cles du bot charge precedemment"
        )
```

(Une exception levée par `load_secure_env` remonte désormais telle quelle : c'est voulu.)

**Dans `tests/test_eval_harness.py`**, test `test_le_dossier_du_bot_est_DEDUIT_de_la_table_des_personas`
(l.1521) : **supprimer les lignes 1539-1542** (l'`assert (dossier / ".env.encrypted").exists()`).
Le reste du test (dossier existant, six dossiers distincts) ne dépend que du dépôt : on le garde.
Sa docstring (« ne demande AUCUNE clé ») devient enfin vraie.

**Ajouter à la suite, dans le même fichier :**

```python
def test_le_harnais_REFUSE_un_bot_sans_cles(tmp_path, monkeypatch):
    """Sans cles lisibles, le harnais mesurait avec celles du bot charge AVANT, en silence.

    `load_secure_env` ne leve jamais : il rend False. Le refus doit donc lire ce RETOUR.
    Ce test ne demande aucune cle : il le verifie sur un dossier vide, ici comme en CI.
    """
    import pytest as _pytest          # style du fichier : pytest est importe localement
    from tests.eval import runner

    monkeypatch.setattr(runner, "_ATTELAGES", {})
    monkeypatch.setattr(runner, "_dossier_du_bot", lambda bot_id: tmp_path)
    with _pytest.raises(RuntimeError, match="aucune cle lisible"):
        runner.attelage_du_bot("alfred")
```

Mutation à rejouer : remettre l'ancien `try/except` → le nouveau test doit tomber.

## 1.2 — `fastapi` et `pydantic` déclarés, et un verrou pour que ça ne se reproduise pas

`tests/test_laya_chauffe.py` charge `laya-server/server.py` **par son chemin**
(`importlib.util.spec_from_file_location`). Ce fichier importe `fastapi` et `pydantic` au
niveau module (`laya` et `torch`, eux, sont importés dans `_charger()`, jamais appelé par
les tests). Le verrou existant, `tests/test_dependances_declarees.py`, ne scanne que les
imports des fichiers de `tests/` : il ne pouvait pas le voir.

**`requirements.txt`** — ajouter juste après le bloc `pyflakes>=3.0.0` (l.23) :

```
# Charges par tests/test_laya_chauffe.py : `laya-server/server.py` les importe au niveau
# module. Absents d'ici, les 4 tests de chauffe tombaient en CI (22/09) et passaient en
# local, ou fastapi etait installe pour le dashboard.
fastapi>=0.118.0,<1.0.0
pydantic>=2.0.0,<3.0.0
```

(Même borne que `dashboard/backend/requirements.txt`. Validé : 1304 verts avec fastapi 0.141.1.)

**`tests/test_dependances_declarees.py`** — ajouter à la fin :

```python
# Fichiers que la suite charge PAR CHEMIN (importlib) : leurs imports ne sont pas dans
# tests/, le scan ci-dessus ne les voit pas. Vecu le 22/09 : fastapi, 4 tests rouges en CI.
_CHARGES_PAR_CHEMIN = [_RACINE / "laya-server" / "server.py"]


def test_les_fichiers_charges_par_chemin_declarent_leurs_dependances():
    """Seuls les imports du CORPS du module comptent : ce sont eux qu'un chargement
    execute. Ceux faits dans une fonction (`laya`, `torch` dans `_charger()`) ne sont
    pas executes par les tests."""
    requirements = (_RACINE / "requirements.txt").read_text(encoding="utf-8").lower()
    manquants = set()
    for chemin in _CHARGES_PAR_CHEMIN:
        assert chemin.exists(), f"{chemin} a disparu : mettre _CHARGES_PAR_CHEMIN a jour"
        arbre = ast.parse(chemin.read_text(encoding="utf-8"), filename=str(chemin))
        for noeud in arbre.body:
            if isinstance(noeud, ast.Import):
                modules = [a.name.split(".")[0] for a in noeud.names]
            elif isinstance(noeud, ast.ImportFrom) and noeud.level == 0 and noeud.module:
                modules = [noeud.module.split(".")[0]]
            else:
                continue
            for module in modules:
                if module in sys.stdlib_module_names or module in _LOCAUX:
                    continue
                if _NOM_PAQUET.get(module, module).lower() not in requirements:
                    manquants.add(f"{module} ({chemin.name})")
    assert not manquants, f"absents de requirements.txt : {sorted(manquants)}"
```

Mutation à rejouer : retirer la ligne `fastapi` de `requirements.txt` → ce test doit tomber.

## 1.3 — La CI teste la version de Python qui tourne en prod

Mesuré : les six conteneurs tournent en **Python 3.11.16** (`Dockerfile` : `python:3.11-slim`),
la CI en 3.12, le `.venv` local en 3.13. La suite passe en 3.11 comme en 3.12 aujourd'hui,
mais rien ne garantit que ça dure : une API 3.12+ passerait la CI et casserait la prod.

`.github/workflows/ci.yml:30-31`, remplacer :

```yaml
        # 3.12 comme en local : c'est la version qui fait foi pour la suite de tests.
        python-version: "3.12"
```

par :

```yaml
        # 3.11 : c'est la version des SIX conteneurs (Dockerfile, python:3.11-slim). La CI
        # doit tester ce qui tourne. Mesure du 22/09 : prod 3.11, CI 3.12, .venv 3.13.
        python-version: "3.11"
```

## Validation du LOT 1

1. `python -m pytest` en local : **1306 passed** (1304 + les 2 nouveaux tests), 0 échec
   (⚠️ ne PAS ajouter `-q` : avec l'`addopts = "-q"` de `pyproject.toml`, `-qq` masque le total).
2. Pousser, puis **`gh run list --limit 1`** : `completed success`. Le lot n'est livré qu'à
   ce moment-là — pas sur la foi de la suite locale.

---

# LOT 1bis — Le « treizième siècle » de Sugar (P0, vu EN DIRECT le 22/09)

**Le fait** (journal de `bot-sugar`, 19:59:45 UTC, `#ma_streameuse`, écrit par
`gemini-3.5-flash-lite`, jeu = *Kingdom Come: Deliverance II*) :

> compte_bot_sugar: Le treizième siècle sans armure, ça pique un peu, mais on t'attend de pied
> ferme sur le discord. ✨ https://discord.gg/exemple
> triKsOff: d'ailleurs c'est le 15eme siecle / bah kcd c'es en 1403 xd
> Chaine_du_Dev: merci je vais corriger le bot

**La cause, lue dans le code** : `shared/twitch/dispatch.py:845-862`, le bloc `if jeu:`.
Il exige que la phrase « DIT quelque chose de ce jeu : une comparaison, un constat… » en
ne donnant au modèle que le **NOM** du jeu. La borne qui suit (« tu ne sais RIEN de la
partie en cours ») porte sur la PARTIE, pas sur le JEU : époque, lieux, personnages, tout
vient de la mémoire du modèle — et une date est ce que le chat vérifie le plus vite.
Le texte est commun aux **quatre** bots de `ACCROCHE_AU_JEU` (sugar, alfred, malena, johnny).

**Le remède retenu : un filet, pas une phrase de plus dans le prompt commun.** Trois
mesures du 21-22/09 l'ont établi : aucune formulation partagée n'améliore les six (elle
répare l'un et effondre les ouvertures d'un autre). Un filet ne touche aucune voix. Même
mécanique que `_INVOQUE_UN_PASSE_COMMUN` : on REJETTE, la seconde chance retente, le
gabarit fixe reste le plancher — fade bat faux.

## 1bis.1 — Le motif, dans `shared/twitch/dispatch.py`, juste après `_INVOQUE_UN_PASSE_COMMUN` (l.91-97)

```python
# ⚠️ Une EPOQUE affirmee sur le jeu. Live du 2026-09-22 sur #ma_streameuse : « Le treizieme
# siecle sans armure, ca pique » pour Kingdom Come: Deliverance II — qui se passe en 1403,
# au XVe. Un spectateur l'a corrige dans le chat. Le modele ne recoit que le NOM du jeu :
# ce qu'il en affirme vient de sa memoire, et une date est ce que le chat verifie le plus
# vite. On rejette (seconde chance, puis gabarit fixe) : fade bat faux.
_AFFIRME_UNE_EPOQUE = re.compile(r"\bsi[èe]cles?\b|\b(?:1\d|20)\d\d\b", re.I)
# Sensible a la CASSE, volontairement : avec re.I, « vie » passerait pour un siecle.
_SIECLE_EN_CHIFFRES_ROMAINS = re.compile(r"\b[IVXL]{2,6}(?:e|è|ème)\b")


def _affirme_une_epoque(phrase: str, jeu: str | None) -> bool:
    """Vrai si la phrase DATE le jeu. Ne s'applique qu'a l'accroche (sans jeu : False).

    Les nombres du TITRE sont permis : « Cyberpunk 2077 », « Anno 1800 » sont des noms,
    pas des affirmations — les rejeter punirait la seule chose vraie qu'on a donnee.
    """
    if not jeu:
        return False
    permis = set(re.findall(r"\d+", jeu))
    for m in _AFFIRME_UNE_EPOQUE.finditer(phrase):
        if m.group(0) not in permis:
            return True
    return bool(_SIECLE_EN_CHIFFRES_ROMAINS.search(phrase))
```

## 1bis.2 — Le branchement, dans la boucle des deux essais de `_generate_link_line` (l.872-884)

Juste après `phrase = _nettoyer_phrase_de_lien(texte, self.bot_id)` (l.876) :

```python
            if phrase and _affirme_une_epoque(phrase, jeu):
                phrase = None
```

(`jeu` est déjà une variable locale de la méthode, l.713. Le journal de rejet existant —
« rejetee par les filets (essai n/2) » — imprime le brouillon : rien d'autre à ajouter.)

## 1bis.3 — Verrous : `tests/test_phrase_de_lien_seconde_chance.py`

Unitaires sur `_affirme_une_epoque`, avec `jeu = "Kingdom Come: Deliverance II"` sauf mention :

| phrase | attendu | pourquoi |
|---|---|---|
| « Le treizième siècle sans armure, ça pique un peu, mais on t'attend de pied ferme sur le discord. ✨ » | `True` | le cas réel |
| « Entre deux roustes au Moyen Âge, viens donc faire un tour sur le serveur, on t'y garde une place au chaud. 🍬 » | `False` | l'autre phrase réelle du soir : vraie, et vague |
| « En 1403 on se battait moins bien que toi, viens nous voir. » | `True` | une année |
| « Au XVe, même les chevaliers auraient rejoint le serveur. » | `True` | chiffres romains |
| « La vie de chevalier use, viens souffler avec nous. » | `False` | la casse protège « vie » |
| « Night City t'attend en 2077, viens nous voir. » avec `jeu = "Cyberpunk 2077"` | `False` | nombre du titre |
| n'importe laquelle avec `jeu = None` | `False` | hors accroche, le filet dort |
| « Viens nous voir, on t'attend depuis des siècles. 🍬 » | `True` | **faux positif ASSUMÉ** : il coûte un second brouillon, pas l'invitation |

Et un test de bout en bout, sur le montage `_bot(...)` du fichier, en donnant un jeu :

```python
def test_une_epoque_inventee_est_RATTRAPEE_par_le_second_essai():
    bot = _bot(["Le treizième siècle sans armure, ça pique un peu, mais on t'attend. ✨",
                "Entre deux roustes, viens souffler avec nous. 🍬"])

    async def jeu():
        return "Kingdom Come: Deliverance II"
    bot._jeu_en_cours = jeu

    assert _lancer(bot) == "Entre deux roustes, viens souffler avec nous. 🍬 https://x.y"
    assert bot.appels == 2
```

Mutation : retirer le branchement de 1bis.2 → ce test doit tomber.

## 1bis.4 — Mesure, APRÈS le live **[Ahmed donne le feu vert]**

⚠️ **Jamais pendant un direct sur la chaîne du bot** : la sonde puise dans le quota de
PRODUCTION (flash-lite = 15 requêtes/min par projet), et `--pause 2` par défaut le dépasse.
Et `--clause` **remplace** la clause de Sugar : ne pas s'en servir pour ce lot.

    python tools/sonde_phrase_de_lien.py --bot sugar --jeu "Kingdom Come: Deliverance II" --n 18 --pause 5 > sugar_kcd2_avant.txt

avant le correctif, puis après, et la même chose pour `alfred`, `malena`, `johnny`. Compter
**en lisant** (la sonde le dit elle-même : une regex écrite après coup trouve ce qu'on
espère) : époques, lieux et noms affirmés sur le jeu, et le taux de repli au gabarit fixe.
▶ Si le filet rejette plus d'**un brouillon sur cinq** chez un bot, envisager POUR CE BOT
SEUL une clause (`CLAUSES_PAR_BOT`) qui nomme ce qu'il ne doit pas affirmer — mesuré le
22/09 : dans une clause, nommer ÉCARTE (Alfred p=0,0002, Sheogorath p=0,044), mais pas
toujours (Malena p=0,32).
⚠️ Ce filet n'attrape que les DATES. Un lieu ou un personnage faux passerait encore : seule
la lecture le voit. D'où l'étape suivante.

## 1bis.5 — Donner au modèle la FICHE du jeu (direction demandée par Ahmed le 22/09)

« Il peut pas consulter Twitch pour ça ? » — mesuré le 22/09, en lecture seule, avec les
identifiants Twitch de Sugar :

- **Twitch seul ne sait rien du jeu** : `GET /helix/games` rend 4 champs — `name`, `id`,
  `box_art_url`, `igdb_id`.
- **Mais il donne l'`igdb_id`**, et IGDB (la base de jeux de Twitch) s'interroge avec les
  MÊMES identifiants — aucune clé nouvelle, aucun compte : `TWITCH_CLIENT_ID/SECRET`, déjà
  propres à chaque bot (vérifié distincts). Pour KCD2 (id 298526) : *« A thrilling
  story-driven action RPG … set in **15th century** Medieval Europe … through the eyes of
  young Henry »*, thèmes `Action, Historical, Open world`. **Le bon siècle était là.**
- ⚠️ La recherche PAR NOM du code actuel (`IGDBClient.search_game`, `game_info.py:54`)
  rend en PREMIER « Dead Island 2: Kingdom Come - Deliverance II Weapon Pack ». Passer
  par l'`igdb_id` que donne Twitch : il est exact.

**`shared/twitch/game_info.py`** (tout ce qui suit ne lève jamais : `None` + `logger.debug`) :

- `HelixClient.get_igdb_id(game_id)` : `GET https://api.twitch.tv/helix/games?id=<game_id>`
  → `data[0]["igdb_id"]`, cache module 24 h (comme `HELIX_CACHE`).
- `IGDBClient.get_game_by_id(igdb_id)` : `int(igdb_id)` d'abord (refuser tout ce qui n'est
  pas un entier : la valeur est interpolée dans la requête IGDB), puis
  `fields name,summary,themes.name; where id = <n>;`, cache dans `IGDB_CACHE` sous la clé
  `f"id:{n}"`, 24 h.
- `fiche_courte(game) -> str | None` : `"Résumé : <summary[:300]> | Thèmes : <…>"`,
  `None` sans résumé.

**`shared/twitch/dispatch.py`** :

- `_jeu_en_cours` (l.632) **ne change pas** (les tests le remplacent par un faux).
- Nouvelle `async def _fiche_du_jeu(self) -> str | None` : réutilise `self._helix_client`
  (créé par `_jeu_en_cours`), relit `get_current_game(chan, live_only=True)` — **en cache,
  donc gratuit** — pour l'`id` que `_jeu_en_cours` jette (`nom, _ = …`, l.655), puis
  `get_igdb_id` → `get_game_by_id` → `fiche_courte`. Le tout sous
  `asyncio.wait_for(…, 3)` et `except Exception: return None` : quelqu'un attend devant son
  chat, et seule la PREMIÈRE invitation d'un jeu paie (cache 24 h).
- Dans le bloc `if jeu:` (l.845-862), si la fiche existe, ajouter :
  « Voici la fiche officielle de ce jeu (en anglais) : {fiche}. C'est TOUT ce que tu sais
  de vrai sur lui : inspire-t'en, mais n'affirme rien qui n'y figure pas. »
  Sans fiche (IGDB muet, jeu inconnu) : l'instruction reste **exactement** celle
  d'aujourd'hui.
- Le filet de 1bis.1 **reste strict** (aucune date, même présente dans la fiche) : on
  mesure d'abord, on ne l'assouplit que s'il rejette souvent des phrases justes.

**Verrous** :
- `tests/test_journal_jeu_question.py:99-100` : ajouter `"_fiche_du_jeu"` aux `interdits`
  de `_question_de_jeu` — observer ne doit toujours RIEN aller chercher. Le verrou des
  l.120-133 (`_fetch_game_facts_block` sous `enable_game_qa`) garde son sens : RÉPONDRE aux
  questions sur le jeu reste éteint ; ceci n'enrichit que l'invitation.
- Fiche présente → elle figure dans l'instruction (capturer l'argument `instruction` du
  faux `_ecrire_phrase_de_lien`) ; fiche absente → instruction identique à aujourd'hui ;
  client qui lève → `_fiche_du_jeu` rend `None` ; `get_game_by_id("1; fields *")` → `None`
  sans requête.

**Mesure** (après le live, comme 1bis.4) : ajouter à `tools/sonde_phrase_de_lien.py` une
option `--fiche "<texte>"` qui remplace `DispatchMixin._fiche_du_jeu` le temps de la mesure
(sa fausse Helix ne connaît pas d'`igdb_id`). Pour les 4 bots, KCD2 puis Elden Ring, sans
et avec fiche : faits inventés sur le jeu, **l'invitation invite-t-elle encore** (le bras
« jeu » de Sheogorath l'avait fait disparaître une fois sur deux), variété des ouvertures.

⚠️ Le chemin des RÉPONSES aux questions (`get_game_facts`, éteint par `enable_game_qa`)
cherche lui aussi par nom : le jour où on l'allume, le passer à l'`igdb_id`.

---

# LOT 2 — La documentation qui ordonne le contraire du code (P0)

AGENTS.md est lu **en premier** par tous les agents (Antigravity, Cursor, Gemini, Copilot).
Il dit aujourd'hui de préserver WAL — or WAL sur `data/bots_database.db` **rend les six bots
muets** (live du 13/09, `tests/test_base_partagee.py::test_wal_n_est_JAMAIS_pose`). Un agent
obéissant « réparerait » la base en la cassant.

## 2.1 — `AGENTS.md:14`

Remplacer :

```
5. **NE JAMAIS changer le mode journal SQLite** (WAL) dans `shared_database.py`
```

par :

```
5. **NE JAMAIS passer une base de `data/` en WAL** — `shared_database.py` pose TRUNCATE, et
   c'est voulu : la base est partagée entre l'hôte Windows et six conteneurs Linux, et WAL
   exige une mémoire partagée (`-shm`) que les deux mondes ne peuvent pas partager. Live du
   2026-09-13 : WAL a rendu les six bots MUETS. Verrou : `tests/test_base_partagee.py`.
```

## 2.2 — `ARCHITECTURE.md`

| ligne | aujourd'hui | remplacer par |
|---|---|---|
| 100 | `SQLite centralisé (WAL mode)` | `SQLite centralisé (TRUNCATE — jamais WAL)` |
| 117 | `SQLite partagé (WAL)` | `SQLite partagé (TRUNCATE — jamais WAL)` |
| 121 | `Orchestration 6 bots + Ollama` | `Orchestration 6 bots + Laya (trieur CPU partagé)` |
| 133 | `3.12 (Docker et CI)` | `3.11 (Docker et CI)` — contredit aujourd'hui la ligne 122 du même fichier |
| 139 | `WAL mode, accès concurrent` | `TRUNCATE, accès concurrent — WAL interdit (base partagée hôte/conteneurs)` |
| 226 | note 3 « mode WAL … Ne pas changer le mode journal » | reprendre le texte de 2.1 |
| 214 | `→ OpenRouter` dans le schéma | retirer (OpenRouter est retiré du code, `tests/test_openrouter_est_retire.py`) |

Ajouter à la structure (après `chatterbox-server/`) une ligne pour `laya-server/` :
`# 🧭 Laya — trieur « System One » CPU, PARTAGÉ, consultatif (borne 300 ms côté client)`.

## 2.3 — `DEV_GUIDE.md`

- l.79 : « quarantaine des clés renvoyant des erreurs `429` … ou `503` » → **seul un 429**
  écarte la clé ; un 503 fait descendre d'un échelon sans quarantaine
  (`gotcha-503-quarantaine-cle`, corrigé et validé live le 03/09).
- l.80 : retirer OpenRouter de la liste des secours.
- l.96 : « Le mode de journalisation visé est **WAL** » → reprendre le texte de 2.1.

## 2.4 — Verrou : `tests/test_documentation.py`

```python
def test_aucun_document_ne_demande_de_garder_WAL():
    """AGENTS.md ordonnait de PRESERVER WAL alors que le code l'interdit depuis le 13/09 :
    un agent obeissant aurait rendu les six bots muets. Toute ligne qui parle de WAL doit
    dire qu'il est interdit."""
    fautes = []
    for nom in ("AGENTS.md", "ARCHITECTURE.md", "DEV_GUIDE.md"):
        for n, ligne in enumerate((_racine / nom).read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"\bWAL\b", ligne) and not re.search(
                    r"jamais|interdit|TRUNCATE|pas en WAL", ligne, re.IGNORECASE):
                fautes.append(f"{nom}:{n}: {ligne.strip()[:80]}")
    assert not fautes, "WAL presente comme un mode a garder :\n" + "\n".join(fautes)
```

Mutation : remettre l'ancienne ligne 14 d'AGENTS.md → le test doit tomber.

---

# LOT 3 — Dashboard : des fenêtres de temps fausses (P1)

Le dashboard est l'outil qui sert à **trancher** (fournisseurs, clés, échelons). Il ment sur
deux axes, mesurés sur la vraie base et vus dans le navigateur le 22/09 :

1. **Format.** `api_calls.timestamp` est écrit en ISO avec un `T` (`2026-09-22T20:27:07.12`).
   `datetime('now', ?)` de SQLite rend un **espace** (`2026-09-22 19:27:07`). Comparées en
   chaînes, `'T' > ' '` : toute ligne du même jour calendaire passe la borne, quelle que
   soit l'heure. Mesure : fenêtre « 1 h » = **481 appels (vrai : 120)** ; « 24 h » = 751
   (vrai : 520) ; KPI d'accueil « Taux Succès API » **74,9 % (vrai : 67,0 %)** ; Gemini
   affiché à 60 % quand il est à **29 %** — la panne Gemini est **minimisée** à l'écran.
2. **Fuseau.** Les conteneurs écrivent en **UTC** (`datetime.now()` sans `TZ`), le dashboard
   et les sondes de `tools/` tournent sur l'hôte en **heure locale (UTC+2)**. Conséquences :
   - `error_analyzer.count_recent(1)` et `conversation_analyzer.get_activity(1)` calculent
     leur seuil en heure locale : un événement venu d'un conteneur est estampillé 2 h
     « plus tôt » → **la fenêtre « 1 h » ne peut jamais le compter** ;
   - `api_tracker.get_keys_status()` (l.133) compare `cooldown_until` (UTC) à l'heure
     locale → **une quarantaine de moins de 2 h n'apparaît jamais** : tout est « ACTIVE » ;
   - 8 lignes de `api_calls` sont horodatées **dans le futur** (sondes lancées sur l'hôte).

**Règle retenue : UNE seule base de temps, UTC naïf ISO (`YYYY-MM-DDTHH:MM:SS.ffffff`), à
l'écriture comme à la lecture.** C'est déjà ce qu'écrivent les conteneurs : les lignes
existantes restent valides, seules celles des sondes hôte (~quelques dizaines) sont décalées.

## 3.1 — Les écrivains (`shared/`, puis `python tools/vendor_core.py`)

- `shared/api_tracking.py` l.6 : `from datetime import datetime` → `from datetime import datetime, timezone`
- l.146, l.183, l.206 : `datetime.now().isoformat()` → `_maintenant_utc()`, avec en tête de module :

```python
def _maintenant_utc() -> str:
    """UTC naif ISO : la base est ecrite par six conteneurs (UTC) ET par des sondes sur
    l'hote (heure locale). Une seule base de temps, sinon les fenetres du dashboard mentent."""
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
```

- `shared/journal_decisions.py` l.163 et l.197 : même remplacement (même raison : le corpus
  est lu depuis l'hôte).
- `shared/api_manager.py:192` produit `cooldown_iso` en heure LOCALE du processus :
  `datetime.fromtimestamp(status["cooldown"]).isoformat()` →
  `datetime.fromtimestamp(status["cooldown"], timezone.utc).replace(tzinfo=None).isoformat()`,
  et l.2 `from datetime import datetime` → `from datetime import datetime, timezone`.
- ⚠️ **Relancer `python tools/vendor_core.py`** : ces modules ont six copies dans `*/core/`.
  La CI le vérifie (`git diff --exit-code -- '*/core/'`).

## 3.2 — Les lecteurs (`dashboard/backend/`)

- `api_tracker.py:38` et `:57` : `datetime('now', ?)` → `strftime('%Y-%m-%dT%H:%M:%S', 'now', ?)`
  (même paramètre `f"-{hours} hours"`).
- `api_tracker.py:133` : `now = datetime.now()` → `now = datetime.now(timezone.utc).replace(tzinfo=None)`
  (import LOCAL l.131 : `from datetime import datetime, timezone`).
- `error_analyzer.py:111`, `conversation_analyzer.py:24` et `:76` : seuil calculé depuis
  `datetime.now(timezone.utc).replace(tzinfo=None)`. Imports : `error_analyzer.py:107`
  (import local) et `conversation_analyzer.py:3` → ajouter `timezone`.
- `conversation_analyzer.py:90` (`now = datetime.now()`, construction des tranches) : la clé
  de recherche `hour_str` doit être en **UTC** (comme la base) ; l'étiquette renvoyée au
  front doit être en **heure locale**. Renvoyer `{"hour": <locale>, "count": …}` en
  calculant `count` avec la clé UTC :

```python
            now = datetime.now(timezone.utc)
            for i in range(hours):
                dt = now - timedelta(hours=hours - 1 - i)
                cle_utc = dt.strftime('%Y-%m-%dT%H:00')
                buckets.append({"hour": dt.astimezone().strftime('%Y-%m-%dT%H:00'),
                                "count": db_data.get(cle_utc, 0)})
```

## 3.3 — Verrous : nouveau fichier `tests/test_dashboard_fenetres_de_temps.py`

Sur une base SQLite temporaire (schéma de `api_calls` et `api_key_status` recopié de
`shared/api_tracking.py`), sans toucher `data/` :

1. une ligne à **UTC − 30 min** et une à **UTC − 3 h** → `APITracker.get_usage(1)["total_calls"] == 1` ;
2. une ligne à **UTC − 20 h** et une à **UTC − 30 h** → `get_usage(24)["total_calls"] == 1` ;
3. `cooldown_until` = **UTC + 10 min** → `get_keys_status()` rend `status == "cooldown"` ;
4. AST : aucune occurrence de `datetime('now'` dans `dashboard/backend/*.py`, et aucun
   `datetime.now().isoformat()` dans `shared/api_tracking.py` ni `shared/journal_decisions.py`.

Mutation : remettre `datetime('now', ?)` → le cas 1 doit tomber (il compte 2).

---

# LOT 4 — Dashboard : traversée de chemin dans `/api/reports/generate` (P1, sécurité)

`dashboard/backend/report_generator.py:51` : `filename = f"report_{scope}_{timestamp}.{format}"`,
avec `scope` et `format` **tels que reçus** par `app.py:339-343`. **Vérifié par une expérience
dans un dossier jetable** : sous Windows, `scope="../../../X"` écrit le fichier **hors** de
`reports/` (les `..` sont résolus lexicalement), et `format` choisit **l'extension**.
Réservé à une session authentifiée (le cookie `SameSite=Strict` bloque le CSRF) : gravité
moyenne, mais c'est une écriture de fichier arbitraire sur l'hôte.

**`dashboard/backend/report_generator.py`, `generate` (l.48)** — refuser en tête, AVANT de
construire le nom :

```python
        if format not in ("md", "json") or scope not in ("all", "status", "errors", "api", "conversations"):
            raise ValueError(f"format ou scope invalide : {format!r}, {scope!r}")
```

(`scope` : exactement les valeurs testées plus bas dans `generate`, l.62/77/98/132.)
Défense en profondeur, juste après `os.path.join` (l.52) : si
`os.path.realpath(filepath)` ne commence pas par `os.path.realpath(self.reports_dir) + os.sep`,
`ValueError`.

**`dashboard/backend/app.py:341`** — convertir en 400 :

```python
    try:
        res = report_generator.generate(format, scope, hours)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

**Test** (aucun test existant n'utilise `TestClient` : tester la classe directement) :
`ReportGenerator(str(tmp_path / "data" / "bots.db"))` range ses rapports dans
`tmp_path/dashboard/reports` (constructeur l.14). `generate(scope="../../x")` et
`generate(format="bat")` → `ValueError`, et **aucun fichier** créé sous `tmp_path`
(comparer `rglob("*")` avant/après).

---

# LOT 5 — cryptography : lever le plafond qui bloque le correctif (P1)

pip-audit sur les versions de prod : **cryptography 46.0.7**, 4 avis. Trois visent des
fonctions X.509/PKCS7 que le projet n'utilise pas (il ne se sert que de **Fernet**). Le
quatrième compte : **GHSA-537c-gmf6-5ccf**, l'OpenSSL embarquée dans les roues, corrigée en
**48.0.1** — et le plafond `<47.0.0` **interdit** le correctif.

Remplacer `cryptography>=46.0.5,<47.0.0` par `cryptography>=48.0.1,<51.0.0` dans les **7**
fichiers (un bot sur six manque toujours : les compter) :

    requirements.txt:8          Alfred/requirements.txt:14     JohnnyBot/requirements.txt:8
    MaiqBot/requirements.txt:8  MalenaBot/requirements.txt:7   Sheogorath/requirements.txt:8
    SugarBot/requirements.txt:8

**Déjà validé** : Python 3.11 + cryptography 50.0.1 → suite 1304 verte, et la sonde des clés
déchiffre les six vrais `.env.encrypted`.

**PyNaCl 1.5.0 (CVE-2025-69277) : NE RIEN FAIRE.** discord.py impose lui-même
`PyNaCl<1.6,>=1.5.0` (extra `voice`), et l'avis vise `crypto_core_ed25519_is_valid_point`,
que la voix Discord n'utilise pas. Ajouter un commentaire au-dessus de `PyNaCl` dans
`requirements.txt:28` pour que personne ne « corrige » en cassant discord.py.

**[Ahmed]** après le merge : `docker compose build` puis `docker compose up -d`, et vérifier
dans chaque conteneur que le bot démarre (le démarrage déchiffre son `.env.encrypted`).

---

# LOT 6 — Règle « une clé par bot » : fermer deux angles morts (P2)

## 6.1 — La sonde ne regarde pas Twitch

`tools/sonde_cles_partagees.py:54-64` : ajouter `"TWITCH_CLIENT_ID"`, `"TWITCH_CLIENT_SECRET"`,
`"TWITCH_OAUTH_TOKEN"`, `"TWITCH_REFRESH_TOKEN"` à `CLES_SURVEILLEES`. Mesuré le 22/09 : les
six jeux sont distincts aujourd'hui (aucune alarme ne partira) — mais AGENTS.md dit « chaque
fournisseur, chaque variable », et une règle qu'aucun outil ne contrôle est un vœu.
⚠️ Ne PAS y mettre `TWITCH_CHAT_CHANNELS`, `TWITCH_PEER_BOTS`, `TWITCH_BOT_USERNAME` : non
secrètes, identiques par construction (`NON_SECRETES` de `tools/preparer_env.py:73`).
Test dans `tests/test_sonde_cles.py` : les quatre noms sont dans `CLES_SURVEILLEES`.

## 6.2 — `load_secure_env` lit le `.env` du dossier PARENT

`shared/secure_env.py:17` : `env_paths = [bot_path / ".env", bot_path.parent / ".env"]`.
Un `.env` posé un jour à la racine du dépôt serait chargé **par les six bots** (sur l'hôte :
harnais, sondes) — exactement le partage de clés interdit. Aucun n'existe aujourd'hui
(vérifié sans ouvrir : `I:\IA\.env`, `<dépôt>\.env` absents), donc le retirer ne change rien.
Le dashboard charge son `.env` par `dotenv` (`app.py:55`), il n'est pas concerné.

- Remplacer par `env_paths = [bot_path / ".env"]`, puis `python tools/vendor_core.py`.
- Test : un dossier de bot vide dans `tmp_path`, un `.env` dans son PARENT → `load_secure_env`
  rend `False` et `os.environ` ne contient pas la variable du parent (nettoyer par `monkeypatch`).

---

# LOT 7 — Environnement local reproductible (P2, **[Ahmed]**)

Mesuré : **aucun interpréteur local ne peut jouer la suite telle qu'écrite.**

| interpréteur | version | manque | utilisé par |
|---|---|---|---|
| `.venv` | 3.13.13 | **pyflakes** → la collecte casse | le shell (PATH) |
| `C:\Python312` | 3.12.10 | **pytest-asyncio** → 13 tests async échouent | le dashboard (processus du port 8501) |
| conteneurs | **3.11.16** | — | la prod |

Recréer `.venv` sur la version de prod, depuis la racine du dépôt :

    uv venv --python 3.11 .venv
    uv pip install --python .venv\Scripts\python.exe -r requirements.txt

Le dashboard n'en dépend pas (il tourne sur `C:\Python312`) : rien d'autre ne bouge.

---

# LOT 8 — Nettoyage (P3, optionnel)

## 8.1 — Alfred télécharge chaque image DEUX fois

`Alfred/bot_alfred.py:1672-1705` est l'ancien chemin vision : il télécharge l'image
(`aiohttp`, **sans borne de temps**) dans `image_data`, jamais relu. Le vrai téléchargement
est `download_media` (l.1755), qui applique déjà la limite de taille. Le préfixe `VISION`
posé l.1702 ne sert que sous `if is_bot_talking:` (l.1714), **toujours faux** (la garde
`author.bot` l.1409 sort avant) : mort aussi.
⚠️ **Mais `has_image = True` (l.1692) EST lu l.1718** (consigne `[INSTRUCTION VISION]`).
Donc : garder la boucle, le contrôle de taille et `has_image = True` + `break` ; retirer
l'`async with aiohttp.ClientSession()` et tout son corps (l.1693-1705), `image_data = None`
(l.1675) et l'affectation `context_prefix = "VISION…"`. Aucun changement de comportement
attendu hormis un appel réseau de moins.

## 8.2 — Les `.env.example` ne décrivent plus les `.env`

Aligner chacun sur le `SOCLE` de `tools/preparer_env.py:82` (`DISCORD_TOKEN`,
`GEMINI_KEY_1`, `GROQ_API_KEY`, `MISTRAL_API_KEY`, `NVIDIA_API_KEY`) :
- `Sheogorath/.env.example` : **n'a pas `DISCORD_TOKEN`**, ni les `TWITCH_*` alors qu'il est
  sur Twitch (reprendre la liste de `JohnnyBot/.env.example`) ;
- retirer `XAI_API_KEY` (Alfred, M'aiq, Malena, Sheogorath — Grok est mort) et
  `ELEVENLABS_API_KEY` / `ELEVENLABS_VOICE_ID` (Alfred — retirées des `.env` le 31/08).
⚠️ Ne toucher QUE les `.env.example`. Jamais un `.env`, jamais un `.env.encrypted`.

## 8.3 — `MaiqBot/debug_db.py`

Outil de débogage mort : il vise `MaiqBot/bots_database.db` (la base vit dans `data/`) et
importe `shared.*` sans garde. Le supprimer.

## 8.4 — Dashboard, affichage

- Page « Gestion Clés API » : les cartes `mistral` et `nvidia` **débordent** du cadre du
  panneau « État des clés » (hauteur figée sur celle du graphique voisin).
- L'en-tête reste « Vue d'ensemble de l'écosystème » sur toutes les pages.

---

## QUESTIONS POUR AHMED — ne pas trancher à sa place

1. **Sheogorath réagit (emoji) aux messages des AUTRES bots.** `bot_sheogorath.py:1878-1893` :
   les réactions (`fromage`, `folie`, `ordre`…) passent AVANT la garde `author.bot` (l.1896),
   c'est le seul des six. Depuis `e773ccd` (17/06). Une réaction n'est pas une réponse ;
   mais « ordre » est un mot courant. Voulu ?
2. La borne de 300 ms de Laya (à 1,3× la médiane réelle) reste la décision ouverte du 22/09.

---

## CE QUI EST SAIN — ne pas y toucher

Authentification du dashboard (comparaison à temps constant, jeton haché, cookie
`httponly` + `SameSite=Strict`, écoute sur 127.0.0.1, CORS restreint, WebSocket contrôlé,
`basename` sur le téléchargement, liste blanche `BOT_REGISTRY` sur start/stop/restart) ;
indépendance des bots ; imports `shared.*` (les deux sans `try` sont derrière
`if not DATABASE_AVAILABLE: return`) ; vendoring ; aucune boucle `while True` hors
`@tasks.loop` ; aucun secret dans git.

## INTERDITS DE CE PLAN

- Aucun `.env`, `.master_key`, `.env.encrypted`, ni base de `data/` touché.
- Après toute modification de `shared/` : `python tools/vendor_core.py`.
- **Un seul `pytest` à la fois** (port 8599 et `data/` partagés).
- **Aucun lot n'est « livré » tant que `gh run list --limit 1` ne dit pas `success`.**
