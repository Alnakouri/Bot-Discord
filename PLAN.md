# PLAN — SUITE 21 : (A) pas de fiche, pas de « jeu » dans l'invitation ; (B) Sugar range les questions posées à la streameuse et les envoie en MP sur demande

Rédaction : Claude, le **2026-10-16** (pendant le live « JAM » de ma_streameuse).
Exécution : **Antigravity**, sauf les étapes marquées **[Claude]** ou **[Ahmed]**.
Plan précédent : SUITE 20 → `b3938ea:PLAN.md` (livrée `698a2c3`, **toujours pas déployée** : son
déploiement est repris au LOT 8 ci-dessous).

## ⚠️ À LIRE AVANT DE COMMENCER

- **Fichiers touchés, et AUCUN autre** :
  - Partie A : `shared/twitch/dispatch.py`, `tests/test_phrase_de_lien_jeu_en_cours.py`,
    `tests/test_phrase_de_lien_seconde_chance.py`.
  - Partie B : `shared/twitch_chat.py`, `shared/twitch/dispatch.py` (déjà cité),
    `SugarBot/sugar_questions_twitch.py` (**NOUVEAU**), `SugarBot/bot_sugar.py`,
    `tests/test_sugar_questions_twitch.py` (**NOUVEAU**).
  - Et ce `PLAN.md` au LOT 7. **Un 9e fichier modifié → arrête-toi et dis-le.**
- `shared/twitch/` et `shared/twitch_chat.py` **ne sont pas** vendorés (`tools/vendor_core.py` ne
  les cite pas) : **ne lance pas** le vendoring. Les bots les lisent par bind mount.
- **Aucun redémarrage de conteneur.** Le LOT 8 appartient à Ahmed.
- **Ne lance jamais deux `pytest` en même temps** (port 8599 partagé).
- Ne touche à aucun `.env`, `.master_key`, `*.db`. **Les tests n'écrivent JAMAIS dans `data/`** :
  le magasin de questions prend son chemin en paramètre → `tmp_path` dans les tests.
- **Les numéros de ligne sont indicatifs** : ancre-toi sur les extraits « AVANT », copiés du code
  le 16/10.
- **Johnny et Sheogorath ne doivent voir AUCUNE différence** : le crochet de la partie B est
  optionnel (défaut `None`) et seul Sugar le passe.

---

# PARTIE A — L'invitation `!discord` parlait d'un « jeu » que personne ne jouait

## POURQUOI (logs de `bot-sugar`, heures UTC, 16/10)

```
17:00:24  Phrase de lien !discord (jeu : JAM) (type : designer) : Votre héros de ce jeu vous a déjà volé le cœur…
17:15:25  Phrase de lien !discord (jeu : JAM) (type : chiffre)  : Combien de fois ce jeu vous a-t-il fait rager…
17:33:19  Phrase de lien !discord (jeu : JAM) (type : choix)    : Vous préférez les fous rires ou les frissons dans ce jeu ?…
```

Le live n'est pas un live de jeu, mais sa catégorie Twitch est « JAM » (game_id `76822994`).
Pour Twitch, c'est un jeu : `helix/games` rend un `igdb_id` (`332595`), et la fiche IGDB est
**vide** (`{'id': '332595', 'name': 'Jam'}`, aucun résumé) → `fiche_courte` rend `None`. La liste
des catégories « pas un jeu » de `_jeu_en_cours` (`just chatting`, `music`, `art`…) ne contient
pas « jam ». Sugar parle donc d'un jeu dont elle ne sait rien, et ça se voit : « ce jeu »,
« votre héros de ce jeu ».

**Décision (Ahmed, 16/10, « oui ») : sans fiche, pas de jeu.** Si Sugar ne sait RIEN du jeu, elle
fait l'invitation normale. Revers accepté : un vrai jeu obscur sans résumé IGDB, ou un IGDB en
panne (borne 3 s), donne aussi l'invitation normale, qui est le repli déjà prévu.
⚠️ Cette décision **revient** sur le comportement du 21/09 (« jeu sans fiche = jeu nommé »),
verrouillé par `test_instruction_sans_fiche_ne_contient_pas_de_fiche`, qui est réécrit au LOT 1.

**Vérifié par Claude sur une copie jetable du dépôt (scratchpad), pas dans le dépôt :** avec le
correctif seul, **7 tests** tombent, tous parce qu'ils simulaient un jeu SANS fiche. Avec les
ajustements du LOT 1, les 7 fichiers de la phrase de lien passent entièrement (144 tests).

## LOT 1 — Le correctif et ses tests

### 1.a `shared/twitch/dispatch.py`, dans `_generate_link_line` (~l. 1143)

AVANT :
```python
        # APRES le cache, jamais avant : un echec IGDB n'est pas mis en cache, et chaque
        # `!discord` servi depuis le cache aurait paye jusqu'a 3 s d'attente pour rien.
        fiche = await self._fiche_du_jeu() if jeu else None
```
APRÈS (ajouter juste en dessous, rien d'autre ne bouge) :
```python
        # APRES le cache, jamais avant : un echec IGDB n'est pas mis en cache, et chaque
        # `!discord` servi depuis le cache aurait paye jusqu'a 3 s d'attente pour rien.
        fiche = await self._fiche_du_jeu() if jeu else None
        # ⚠️ SANS FICHE, PAS DE JEU (SUITE 21, 16/10). La categorie « JAM » est un « jeu »
        # pour Twitch (fiche IGDB vide), mais le live n'en etait pas un : Sugar a ecrit
        # trois invitations sur « ce jeu », qu'elle ne connaissait pas. Un nom seul ne
        # suffit pas a parler d'un jeu ; sans rien de vrai a en dire, l'invitation normale.
        if jeu and not fiche:
            self.logger.info(
                f"🎮 [TWITCH_CHAT:{self.bot_id}] « {jeu} » : aucune fiche, invitation sans le jeu"
            )
            jeu = None
```
- La clé du cache (`cle_cache`, calculée plus haut avec le nom) **ne change pas** : la phrase neutre
  est rangée sous `(cmd, "JAM")` et resservie 15 min, ce qui est le comportement voulu.
- Ne touche **ni** à `_jeu_en_cours` **ni** à sa liste de catégories.

### 1.b `tests/test_phrase_de_lien_jeu_en_cours.py`

1. Sous `BOTS_MESURES = {"sugar", "alfred", "malena", "johnny"}`, ajouter :
   ```python
   # SUITE 21 : un jeu SANS fiche n'est plus un jeu. Les tests qui simulent un jeu lui
   # donnent donc une fiche par defaut ; VRAIE_FICHE garde la vraie methode.
   FICHE_DE_TEST = "Résumé : A game about a knight in a kingdom. | Thèmes : Action"
   VRAIE_FICHE = object()
   ```
2. `_faux_bot` : signature `def _faux_bot(bot_id="sugar", channels=("un_canal",), avec_cles=True, fiche=FICHE_DE_TEST):`
   et, juste avant son `return f` :
   ```python
       if fiche is not VRAIE_FICHE:
           async def _fiche():
               return fiche
           f._fiche_du_jeu = _fiche
   ```
3. `test_fiche_du_jeu_ne_leve_jamais` : `f = _faux_bot()` → `f = _faux_bot(fiche=VRAIE_FICHE)`
   (il teste la VRAIE méthode).
4. **Réécrire** `test_instruction_sans_fiche_ne_contient_pas_de_fiche` en
   `test_un_jeu_SANS_fiche_donne_l_invitation_normale` : jeu `"JAM"`, `_fiche_du_jeu` → `None`.
   Assertions : l'instruction capturée ne contient **ni** `« JAM »`, **ni**
   `"le chat regarde quelqu'un jouer"`, **ni** `DispatchMixin.CLAUSES_JEU_PAR_BOT["sugar"]`, **ni**
   aucune phrase de `TYPES_DE_QUESTION_JEU_PAR_BOT["sugar"]` ; et `bot._rang_type_question`
   n'existe pas (`not hasattr`). Docstring : le cas vécu du 16/10 (les 3 phrases ci-dessus).
   **Ce test doit ÉCHOUER sur le code d'avant 1.a** : vérifie-le (retire temporairement les 4
   lignes, constate le rouge, remets-les).

### 1.c `tests/test_phrase_de_lien_seconde_chance.py`

Dans `_bot(sorties)`, entre `f._ecrire_phrase_de_lien = faux_appel` et `return f` :
```python

    async def fiche():
        return "Résumé : A game about a knight in a kingdom. | Thèmes : Action"
    f._fiche_du_jeu = fiche
```
(La fiche ne cite aucun siècle : `test_une_epoque_inventee_est_RATTRAPEE_par_le_second_essai`
garde donc son sens, le « treizième siècle » reste une époque inventée.)

### 1.d Vérification du LOT 1

```bash
python -m pytest -q tests/test_phrase_de_lien_jeu_en_cours.py tests/test_annonce_auto_ne_redit_pas.py tests/test_journal_jeu_question.py tests/test_phrase_de_lien_clause_par_bot.py tests/test_phrase_de_lien_sans_redite.py tests/test_phrase_de_lien_seconde_chance.py tests/test_twitch_phrase_de_lien.py
```
Attendu : **tout vert**. Un test rouge ailleurs que dans ces deux fichiers → arrête-toi.

ℹ️ Conséquence à connaître, **sans rien y changer** : `tools/sonde_phrase_de_lien.py` sans
`--fiche "…"` mesure désormais l'invitation SANS jeu (son faux bot n'a pas de vraie clé IGDB).
Pour mesurer la variante jeu, il faut passer `--fiche`.

---

# PARTIE B — Sugar range les questions posées à la streameuse, et les envoie en MP sur demande

## CE QU'AHMED A DEMANDÉ (16/10)

« je veux que Sugar puisse récupérer la liste des questions posées à la streameuse par les viewers
sur Twitch et la donner sur Discord au modo ou à la streameuse par message privé », puis :
« je veux qu'elle fasse la liste si je lui demande en privé ou sur Discord », puis :
« elle doit comprendre pour qui est la question ».

## LA CONCEPTION (décidée, ne pas la rediscuter)

1. **Sur Twitch, Sugar observe sans jamais répondre.** Un crochet en lecture seule
   (`message_observer`) voit chaque message hors commande, mentions de Sugar comprises (un viewer
   qui écrit « Sugar, tu joues à quoi demain ? » vise souvent la streameuse). Il n'envoie rien.
2. **À qui s'adresse la question : d'abord les règles, l'IA seulement si elles ne savent pas.**
   - Évident, sans IA : réponse Twitch (tag `reply-parent-user-login`), `@pseudo` en tête,
     `@streameuse` dans le texte.
   - Ambigu : rangé « à trier », avec les 4 messages du salon qui le précèdent.
   - L'IA tranche **au moment de la demande**, en **UN seul appel** pour toutes les questions à
     trier. Chaque question n'est triée qu'une fois : le verdict est enregistré.
3. **Sur Discord, à la demande seulement.** Un message adressé à Sugar (MP, mention, réponse, ou
   son nom) qui demande « les questions » → Sugar envoie la liste **en MP** à la personne, si
   celle-ci est streameuse ou modo. Sinon : rien de spécial, la conversation normale continue.
4. **Fenêtre : 12 dernières heures**, groupées par chaîne Twitch (Sugar écoute `ma_streameuse` et
   `chaine_du_dev`).
5. **Rien n'est perdu en silence** : si l'IA est en panne, les questions non triées sortent quand
   même, dans une section « Pas sûre du destinataire ».

## LOT 2 — Le crochet `message_observer` (shared, opt-in)

### 2.a `shared/twitch_chat.py`

- `TwitchChatBot.__init__` (~l. 108), juste après `passive_handler: Callable | None = None,` :
  ```python
          message_observer: Callable | None = None,
  ```
- (~l. 170) juste après `self.passive_handler = passive_handler` :
  ```python
          # Observateur en LECTURE SEULE de chaque message hors commande (SUITE 21) :
          # appele avec (chan, author, text, tags, contexte), sa valeur est ignoree.
          self.message_observer = message_observer
  ```
- `setup_twitch_chat` (~l. 295), juste après `passive_handler: Callable | None = None,` :
  ```python
                        message_observer: Callable | None = None,
  ```
- Dans l'appel `TwitchChatBot(...)` (~l. 543), juste après `passive_handler=passive_handler,` :
  ```python
          message_observer=message_observer,
  ```

### 2.b `shared/twitch/dispatch.py`, dans `_handle_privmsg` (~l. 411)

AVANT :
```python
        # 2. Check Command
        is_cmd = await self._handle_command(chan, author, text, ws)
        if is_cmd:
            return

        # 3. Check Mention
```
APRÈS :
```python
        # 2. Check Command
        is_cmd = await self._handle_command(chan, author, text, ws)
        if is_cmd:
            return

        # 2 bis. Observateur en LECTURE SEULE (SUITE 21 : Sugar y range les questions
        # posees a la streameuse). Il voit tout message hors commande — mention comprise,
        # car « Sugar, tu joues a quoi demain ? » vise souvent la streameuse — et ne
        # repond jamais : sa valeur de retour est ignoree, une exception ne coupe rien.
        # Le contexte est pris AVANT que ce message n'y soit ajoute (branches 3 et 4).
        observateur = getattr(self, "message_observer", None)
        if observateur:
            try:
                contexte = list(getattr(self, "channel_recent", {}).get(chan.lower(), ()))
                observateur(chan, author, text, tags, contexte)
            except Exception as e:
                self.logger.error(f"❌ [TWITCH_CHAT:{self.bot_id}] Erreur message_observer: {e}")

        # 3. Check Mention
```
- `getattr` partout : des tests construisent des faux `DispatchMixin` sans `__init__`.
- L'observateur est **synchrone** (pas d'`await`) : ne pas le rendre async.

## LOT 3 — `SugarBot/sugar_questions_twitch.py` (NOUVEAU)

Module **pur** : aucun import de `discord`, d'un fournisseur LLM ou de `shared`. L'appel IA lui
est **passé** (comme `grudge_book.refine_async(..., _grudge_llm_call)`), sinon le verrou
`test_aucun_appel_fournisseur_nu_dans_les_bots` tombe. Imports permis : `os`, `json`, `re`,
`time`, `logging`, `unicodedata`.

### Constantes

```python
FENETRE_S = 12 * 3600          # la liste couvre les 12 dernieres heures
RETENTION_S = 48 * 3600        # au-dela, purge a chaque sauvegarde
MAX_ENTREES = 300              # plafond du fichier (les plus anciennes partent)
MAX_A_TRIER_PAR_APPEL = 40     # au-dela, les plus anciennes restent « a trier »
CONTEXTE_MAX = 4               # messages du salon gardes avant une question ambigue
TAILLE_PAGE = 1900             # un MP Discord plafonne a 2000
```

### Fonctions libres

**`est_une_question(texte) -> bool`** : après avoir retiré les `@pseudo` du texte :
- vrai si le texte contient `?` **et** compte au moins **8 lettres** (`??`, `quoi ?`, `hein ?` → faux) ;
- vrai aussi, sans `?`, si le texte commence (insensible à la casse et aux accents) par
  `pourquoi|comment|quand|combien|quel|quelle|quels|quelles|est-ce|est ce|c'est quoi|cest quoi|qu'est-ce|quest ce|où|ou est`
  suivi d'une frontière de mot, **et** compte au moins 8 lettres.

**`destinataire_evident(chan, author, text, tags, bot_login="") -> str | None`**. Rend `"streameuse"`, `"a_trier"` ou `None` (ignorer).
Dans cet ordre :
1. `streameuse = chan.lower().lstrip("#")` ; `author.lower()` égal à `streameuse` ou à `bot_login.lower()` → `None`.
2. Texte vide ou commençant par `!` → `None`.
3. `not est_une_question(text)` → `None`.
4. `parent = (tags or {}).get("reply-parent-user-login", "").lower()` : s'il est non vide →
   `"streameuse"` si `parent == streameuse`, sinon `None` (réponse à un viewer ou au bot).
5. Texte qui commence par `@(\w+)` → `"streameuse"` si ce pseudo est la streameuse, sinon `None`.
6. `@<streameuse>` n'importe où (regex, insensible à la casse, frontière de mot) → `"streameuse"`.
7. Sinon → `"a_trier"`.

**`demande_la_liste(texte, en_prive) -> bool`** :
```python
_DEMANDE_RE = re.compile(r"\bquestions?\b", re.IGNORECASE)
_SUJET_RE = re.compile(r"twitch|live|strea?m|t?chat|view|vewer|spectat", re.IGNORECASE)
```
Faux sans `_DEMANDE_RE`. En MP : vrai dès que `_DEMANDE_RE` matche. Dans un salon : il faut aussi
`_SUJET_RE` (« Sugar, t'as des questions ? » ne doit pas déclencher la liste).
Les fautes d'Ahmed doivent passer : « stremeuse », « viewver ».

**`peut_demander(guilds, user_id) -> bool`** : vrai si, sur **au moins un** serveur de Sugar,
la personne est propriétaire (`guild.owner_id == user_id`) ou membre (`guild.get_member(user_id)`)
avec `guild_permissions.administrator`, `.manage_messages` ou `.moderate_members`. Sinon faux.
Accès par `getattr` (les tests passent des `SimpleNamespace`).

### Classe `QuestionsTwitch(chemin, logger=None)`

Une **seule** instance par processus, qui garde les entrées **en mémoire** et les écrit sur disque
à chaque changement. Format du fichier :
```json
{"version": 1, "prochain_id": 7, "entrees": [
  {"id": 6, "ts": 1760634000.0, "chan": "ma_streameuse", "auteur": "pseudo",
   "texte": "c'est quoi ce jeu ?", "dest": "a_trier",
   "contexte": ["un_viewer: …", "autre: …"]}
]}
```
`dest` ∈ `streameuse`, `a_trier`, `sugar`, `viewer`, `personne`. `contexte` n'existe que pour
une entrée `a_trier`. Le `texte` est coupé à 300 caractères, chaque ligne de contexte à 150.

- **Chargement** : fichier absent ou illisible (JSON cassé) → magasin vide + `logger.warning`,
  **jamais** d'exception.
- **Sauvegarde atomique** : écrire `chemin + ".tmp"` puis `os.replace`. Avant d'écrire : purger les
  entrées de plus de `RETENTION_S`, puis ne garder que les `MAX_ENTREES` plus récentes.
- **`observer(chan, author, text, tags, contexte, bot_login="")`** (synchrone) :
  `destinataire_evident(...)` ; `None` → rien. Doublon (même chaîne, même auteur, même texte
  normalisé en minuscules et espaces compactés, dans la `FENETRE_S`) → rien. Sinon : ajouter,
  sauvegarder, et `logger.info(f"❓ [QUESTIONS] Question rangée ({dest}) de {author} sur #{chan} : {texte[:80]}")`.
- **`async rapport(appel_llm, bot_login="", maintenant=None) -> list[str]`** : rend les pages du MP.
  1. Sélectionner les entrées de la `FENETRE_S`.
  2. Celles en `a_trier` : prendre les `MAX_A_TRIER_PAR_APPEL` plus récentes, noter leurs **id**.
     S'il y en a, **un seul** `await appel_llm(system_prompt, user_message)` (prompt ci-dessous).
  3. ⚠️ **Après l'`await`, réappliquer les verdicts PAR ID sur `self.entrees`**, jamais sur une copie
     prise avant l'appel : une question rangée par Twitch PENDANT l'appel doit survivre. (Gotcha du
     dépôt : protéger le CYCLE lire-modifier-écrire.) Puis sauvegarder une fois.
  4. `appel_llm` rend `None`, lève, ou rend du texte illisible → les entrées restent `a_trier`,
     pas d'exception (`logger.warning`).
  5. Construire le texte : par chaîne (la plus fournie d'abord), les `streameuse` dans l'ordre
     chronologique, puis une section « Pas sûre du destinataire » pour les `a_trier` restantes.
  6. Découper en pages ≤ `TAILLE_PAGE` **sans jamais couper une ligne**.
  7. `logger.info(f"📋 [QUESTIONS] Liste : {n} pour la streameuse, {k} triée(s) par l'IA, {r} non triée(s)")`.

**Le prompt du tri** (garder ce texte) :
```python
system_prompt = (
    f"Tu tries des messages du chat Twitch de la chaîne « {chan} ». La streameuse est "
    f"« {chan} » : elle parle à voix haute, ses paroles ne sont pas dans le chat. "
    f"« {bot_login or 'le bot'} » est Sugar, un bot du chat. Les viewers appellent souvent la "
    f"streameuse par un bout de son pseudo — y compris « Sugar », comme le bot : tranche avec "
    f"le sens. Pour chaque message numéroté, dis à QUI la question s'adresse : "
    f"S = la streameuse ; B = le bot Sugar ; V = un autre viewer ; "
    f"A = personne (réaction, question rhétorique, pas vraiment une question). "
    f"Une question posée au chat sans destinataire, sur la streameuse, son live, ses jeux "
    f"ou sa vie, est pour elle : S. "
    f"Réponds une ligne par message, au format numéro:lettre, et rien d'autre."
)
```
Si les questions à trier viennent de plusieurs chaînes, faire **un appel par chaîne** (en
pratique : une seule, `ma_streameuse`). Le `user_message` liste chaque question ainsi :
```
#1 — contexte juste avant :
  un_viewer: …
  autre: …
pseudo : texte de la question
```
Lecture : regex par ligne `^\s*#?\s*(\d+)\s*[:=\-–]\s*([SBVA])\b` (insensible à la casse) ;
S→`streameuse`, B→`sugar`, V→`viewer`, A→`personne`. Un numéro absent ou hors liste → l'entrée
reste `a_trier`.

**Le texte du MP** :
- En-tête par chaîne : `**❓ Questions pour {chan}** — 12 dernières heures ({n})`
- Une ligne par question : `<t:{int(ts)}:t> **{auteur}** : {texte}` (Discord affiche l'heure dans
  le fuseau du lecteur, donc pas de souci UTC / UTC+2).
- Le texte et le pseudo passent par `_echapper` : `re.sub(r"([\\*_~`|>])", r"\\\1", s)`, puis
  `@` → `@​` (un `@everyone` d'un viewer ne doit jamais notifier).
- Section non triée : `**Pas sûre du destinataire** ({r})`, mêmes lignes.
- Rien du tout : une seule page, `Aucune question pour la streameuse sur les 12 dernières heures.`

## LOT 4 — Câblage dans `SugarBot/bot_sugar.py`

### 4.a Import et instance (~l. 236-250)

Dans le `try/except ImportError` existant :
```python
try:
    from sugar_memory import FactMemory, DailyMemory
    from sugar_grudge import GrudgeBook, classify_tone, tone_directive
    from sugar_questions_twitch import QuestionsTwitch, demande_la_liste, peut_demander
except ImportError:
    from SugarBot.sugar_memory import FactMemory, DailyMemory
    from SugarBot.sugar_grudge import GrudgeBook, classify_tone, tone_directive
    from SugarBot.sugar_questions_twitch import QuestionsTwitch, demande_la_liste, peut_demander
```
Après `grudge_book = GrudgeBook(...)` :
```python
# Questions posees a la streameuse sur Twitch (SUITE 21) : rangees par le chat Twitch,
# envoyees en MP sur demande. Fichier dans DATA_DIR : `SugarBot/` est en lecture seule
# dans le conteneur.
questions_twitch = QuestionsTwitch(os.path.join(DATA_DIR, "sugar_questions_twitch.json"),
                                   logger=logger)
```
(`data/*.json` est déjà ignoré par Git : vérifié, `git check-ignore` → `.gitignore:42`.)

### 4.b Appel IA du tri (juste après `_grudge_llm_call`, ~l. 285)

```python
async def _tri_questions_llm_call(system_prompt, user_message):
    return await generate_response(
        routing={"type": RequestType.TEXT, "reason": "questions_tri"},
        system_prompt=system_prompt, transcript="", user_message=user_message,
        conversation_history=[], media_data=None, mime_type="",
        key_manager=key_manager, mistral_client=mistral_client,
        groq_client=groq_client,  nvidia_client=nvidia_client,
        bot_label="Sugar Bot", temperature=0.0, max_tokens=300)
```

### 4.c Observateur Twitch (juste après `_ton_twitch`, ~l. 275)

```python
def _observer_question_twitch(chan, author, text, tags, contexte):
    """Range une question posee a la streameuse. Lecture seule : n'envoie rien."""
    login = getattr(twitch_chat, "username", "") if twitch_chat else ""
    questions_twitch.observer(chan, author, text, tags, contexte, bot_login=login)
```
Et dans l'appel `setup_twitch_chat("sugar", ...)` (~l. 494), après `enable_voice_listen=False,` :
```python
            message_observer=_observer_question_twitch,
```

### 4.d La demande sur Discord, dans `on_message` (~l. 765)

AVANT :
```python
    # Noms alternatifs pour Sugar Bot (détection dans le message)
    SUGAR_NAMES = ["sugar", "sugar bot"]
    content_lower = message.content.lower()
    is_name_mentioned = any(name in content_lower for name in SUGAR_NAMES)
```
APRÈS (ajouter juste en dessous) :
```python
    # LISTE DES QUESTIONS TWITCH (SUITE 21) : streameuse et modos seulement, en MP.
    # Quelqu'un d'autre qui demande « les questions » tombe dans la conversation normale.
    if ((is_mentioned or is_reply or is_dm or is_name_mentioned)
            and demande_la_liste(message.content, en_prive=is_dm)
            and peut_demander(bot.guilds, message.author.id)):
        await _envoyer_les_questions(message)
        return
```
Et la fonction, définie au niveau module **avant** `on_message` :
```python
async def _envoyer_les_questions(message):
    """Envoie en MP la liste des questions posees a la streameuse (SUITE 21)."""
    login = getattr(twitch_chat, "username", "") if twitch_chat else ""
    pages = await questions_twitch.rapport(_tri_questions_llm_call, bot_login=login)
    try:
        for page in pages:
            await message.author.send(page, allowed_mentions=discord.AllowedMentions.none())
    except discord.Forbidden:
        if message.guild:
            await message.reply(
                "Je n'arrive pas à t'écrire en privé : ouvre tes messages privés et redemande-moi.",
                mention_author=False)
        return
    if message.guild:
        try:
            await message.add_reaction("📬")
        except discord.HTTPException:
            pass
    logger.info(f"📋 [QUESTIONS] Liste envoyée en MP à {message.author}")
```

## LOT 5 — `tests/test_sugar_questions_twitch.py` (NOUVEAU)

Import comme `tests/test_sugar_grudge.py` (`sys.path` + `from SugarBot.sugar_questions_twitch import …`).
Le magasin est **toujours** créé dans `tmp_path`. Pas de réseau, pas de vraie IA.
Chaque test du crochet (groupe E) doit **échouer sur le code d'avant le LOT 2**.

**A. Repérage (`destinataire_evident`, chaîne `ma_streameuse`, bot `compte_bot_sugar`)**
1. `@ma_streameuse tu joues à quoi demain ?` → `streameuse`
2. tag `reply-parent-user-login=ma_streameuse`, texte `@ma_streameuse et après ça ?` → `streameuse`
3. tag `reply-parent-user-login=un_viewer`, texte `@un_viewer tu parles de quel jeu ?` → `None`
4. `@un_viewer t'as vu ce qu'elle a fait ?` → `None` ; `@compte_bot_sugar tu dors encore ou quoi ?` → `None`
   (textes assez longs exprès : un texte court tomberait au point 3 des règles, pas au point 5)
5. `??`, `quoi ?` → `None`
6. auteur `Ma_Streameuse` (la streameuse elle-même), texte `vous voulez quel jeu demain ?` → `None`
7. `!discord ?` → `None`
8. `c'est quoi ce jeu ?` → `a_trier`
9. `pourquoi tu ris` (sans `?`) → `a_trier`
10. `trop bien ce live` → `None`

**B. Magasin**
11. Le même message du même auteur, deux fois → une seule entrée.
12. Une nouvelle instance sur le même chemin relit les entrées.
13. Une entrée de plus de 48 h disparaît à la sauvegarde ; une de 13 h reste dans le fichier mais
    n'est pas dans le rapport (passer `maintenant=`).
14. Fichier JSON cassé → magasin vide, aucune exception.
15. Une entrée `a_trier` garde au plus 4 lignes de contexte.

**C. Rapport et tri** (faux `appel_llm` async qui compte ses appels)
16. 3 questions à trier, réponse `"1:S\n2:V\n3:A"` → seule la 1re sort, avec les `streameuse`
    évidentes ; les verdicts sont écrits sur disque ; un 2e `rapport` **n'appelle plus** l'IA.
17. `appel_llm` rend `None` (puis : lève une exception) → les questions sortent sous
    « Pas sûre du destinataire » et restent `a_trier`.
18. ⚠️ Le faux `appel_llm` appelle `observer(...)` (nouvelle question) **avant** de rendre sa
    réponse → après le rapport, la nouvelle question est toujours là, en mémoire **et** sur disque.
19. 60 questions longues → toutes les pages font ≤ 1900 caractères et aucune ligne n'est coupée.
20. Une question `@everyone regarde **ça** ?` → la page ne contient ni `@everyone` intact ni `**ça**` brut.
21. Magasin vide → une page, `Aucune question pour la streameuse sur les 12 dernières heures.`

**D. Demande et droits**
22. `demande_la_liste` : MP `les questions ?` → vrai ; salon `Sugar, les questions du live` → vrai ;
    salon `Sugar, t'as des questions ?` → faux ; salon `les questions de la stremeuse` → vrai ;
    salon `les questions des viewver` → vrai ; `salut Sugar` → faux.
23. `peut_demander` : propriétaire → vrai ; `manage_messages` → vrai ; `moderate_members` → vrai ;
    membre simple → faux ; absent de tous les serveurs → faux.

**E. Le crochet (shared)**
24. Faux `DispatchMixin` piloté par `_handle_privmsg` (stubs : `_handle_command`, `_question_de_jeu`,
    `_defaite_observee`, `_generate_response` → `None`, `trigger_re`, `channel_recent`, `session_seen`,
    `viewers_state`, `_save_viewers_state_debounced`, `link_timers=[]`, `passive_handler=None`,
    `enable_*=False`, `user_cooldowns`, `global_msg_timestamps`, `logger`) :
    - message passif → l'observateur est appelé **une fois** avec `(chan, author, text, tags, contexte)`,
      et `contexte` = les lignes déjà dans `channel_recent` (sans le message courant) ;
    - message qui mentionne le bot → appelé aussi ;
    - commande (`_handle_command` rend `True`) → **pas** appelé ;
    - message avec `bits` → **pas** appelé ;
    - observateur qui lève → le message passif est quand même rangé dans `channel_recent`.
25. `setup_twitch_chat` a un paramètre `message_observer` **et** le transmet (AST : mot-clé
    `message_observer=message_observer` dans l'appel `TwitchChatBot(...)`).
26. Verrou de câblage (AST sur `SugarBot/bot_sugar.py`) : l'appel `setup_twitch_chat("sugar", …)` a
    le mot-clé `message_observer` ; `on_message` appelle `demande_la_liste` **et** `peut_demander`.
    (Gotcha du dépôt : un import ajouté mais jamais branché.)

## LOT 6 — Suite complète, pyflakes, commit, CI

```bash
python -m pyflakes SugarBot/sugar_questions_twitch.py SugarBot/bot_sugar.py shared/twitch_chat.py shared/twitch/dispatch.py tests/test_sugar_questions_twitch.py
python -m pytest -q
```
- pyflakes **avant** pytest. Suite complète **verte**, sinon arrête-toi et rapporte la sortie brute.
- `python tools/sonde_core_drift.py` → 0 dérive (rien de vendoré ne doit avoir bougé).
- Deux commits :
  - `fix(twitch): sans fiche du jeu, l'invitation ne parle plus d'un jeu (categorie JAM)`
  - `feat(sugar): range les questions posees a la streameuse sur Twitch, liste en MP sur demande`
- `git push`, puis **`gh run list --limit 3`** jusqu'à la CI verte. CI rouge → arrête-toi.

## LOT 7 — Compte rendu

En bas de ce `PLAN.md`, une section `## COMPTE RENDU` : les hash, le nombre de tests (avant →
après), la sortie **brute** de `gh run list`, et tout écart au plan. Commit `docs(plan): SUITE 21 - compte rendu`.

## LOT 8 — [Ahmed] Déploiement, HORS LIVE

Redémarrer **hors live** (un redémarrage ré-annonce tout live en cours) :
`docker restart bot-sugar bot-johnny bot-sheogorath`. Ça déploie aussi la SUITE 20 (`698a2c3`),
toujours en attente. Pour `661bd22` (annonce d'Alfred), redémarrer aussi les autres conteneurs,
comme prévu depuis le 09/10.

## LOT 9 — [Claude] Vérification

- `docker logs bot-sugar --since 10m` : 0 erreur au démarrage.
- Au prochain live de ma_streameuse : lignes `❓ [QUESTIONS] Question rangée`. Si la catégorie est
  encore « JAM » : ligne `🎮 … « JAM » : aucune fiche` et une invitation sans « ce jeu ».
- Ahmed envoie à Sugar en MP « les questions du live » → MP reçu ; un compte non modo → rien.
- Relire 10 verdicts du tri à la main (S/B/V/A) avant de conclure que « comprendre pour qui » tient.

---

## COMPTE RENDU (Exécution SUITE 21)

- [x] LOT 1 (fix twitch sans fiche)
- [x] LOT 2 (crochet message_observer)
- [x] LOT 3 (SugarBot/sugar_questions_twitch.py)
- [x] LOT 4 (câblage SugarBot/bot_sugar.py)
- [x] LOT 5 (tests/test_sugar_questions_twitch.py)
- [x] LOT 6 (pyflakes, suite complète, push, CI)
- [x] LOT 7 (compte rendu)
- [ ] LOT 8 [Ahmed] Déploiement hors live
- [ ] LOT 9 [Claude] Vérification

### Commits
- `3903f0e` : `fix(twitch): sans fiche du jeu, l'invitation ne parle plus d'un jeu (categorie JAM)`
- `b6daeec` : `feat(sugar): range les questions posees a la streameuse sur Twitch, liste en MP sur demande`

### Tests
- Tests avant : **1545** (tous verts)
- Tests après : **1571** (+26 tests dans `tests/test_sugar_questions_twitch.py`, tous verts)
- Core drift : 0 dérive (`sonde_core_drift.py: No drift detected.`)

### Sortie brute `gh run list --limit 3`
```
completed	success	feat(sugar): range les questions posees a la streameuse sur Twitch, l…	CI	main	push	38946424851	4m17s	2026-10-16T18:19:17Z
completed	success	docs(plan): SUITE 20 - compte rendu	CI	main	push	38655495162	4m22s	2026-10-14T23:40:13Z
completed	success	fix(twitch): un message identique < 32 s n'est plus envoye (Twitch le…	CI	main	push	38655013835	4m10s	2026-10-14T23:35:26Z
```

### Écarts par rapport au plan
- `SugarBot/bot_sugar.py` : ajout d'un commentaire explicatif `# Pas de permission d'ajouter des réactions dans ce salon` sur le `pass` du bloc `except discord.HTTPException:` dans `_envoyer_les_questions` pour satisfaire le verrou `tests/test_except_muet_documente.py`.
- `tests/test_sugar_questions_twitch.py` :
  - `_FauxDispatch` utilise des méthodes synchrones pour `_question_de_jeu(self, text, contexte_ou_voie="")` et `_defaite_observee(self, text)` conformes à `DispatchMixin`.
  - Le verrou AST `test_verrou_cablage_bot_sugar_ast` inspecte `(ast.FunctionDef, ast.AsyncFunctionDef)` car `on_message` est défini via `async def`.
  - Dans `test_rapport_concurrence_nouvelle_question_pendant_llm`, la question simulée comporte plus de 8 lettres hors mention (`@ma_streameuse tu viens quand aujourd'hui ?`) pour satisfaire le filtre `est_une_question`.

