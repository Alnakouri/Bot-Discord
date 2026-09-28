# PLAN — SUITE 13 : l'annonce auto de Sugar resservait la phrase que le chat venait de lire

Rédaction : Claude, le **2026-09-28**. Exécution : **Antigravity**, sauf les étapes marquées
**[Ahmed]** ou **[Claude]**. Plan précédent (SUITE 12, livré `478cf0b`) lisible dans git
(`478cf0b:PLAN.md`).

Périmètre : **un seul fichier de code**, `shared/twitch/dispatch.py`, et un fichier de tests.
**Aucun appel API, aucune modification de prompt, aucun `.env` touché.**
Un seul redémarrage, `bot-sugar`, au LOT 4, **après accord d'Ahmed**.

---

## LE CONSTAT (vérifié par Claude le 28/09 dans `docker logs bot-sugar`)

Sugar est le seul bot dont `!discord` a une annonce auto (journal de démarrage du 28/09 :
`!discord (+1 alias, phrase du bot, auto 15 min / 15 msgs)` ; Johnny a `!discord` sans
auto, les quatre autres rien).

Sur 27 phrases générées depuis le 20/09, **trois envois sont la copie exacte de l'envoi
précédent**, et les trois ont la même forme : un viewer tape `!discord`, puis l'annonce
auto part **moins de 15 min après** et reprend la phrase **dans le cache** (aucune ligne
`✨ Phrase de lien` avant son envoi) :

| `!discord` tapé | annonce auto | écart |
|---|---|---|
| 21:17:26 | 21:23:49 | 6 min 23 s |
| 22:22:23 | 22:36:57 | 14 min 34 s |
| 20:09:45 (27/09) | 20:23:50 | 14 min 05 s |

**Deux causes, dans `shared/twitch/dispatch.py`** :

1. **La commande tapée ne remet pas le minuteur à zéro.** `_try_link_timer` (l.638) ne
   regarde que `_etat_timers[(canal, cmd)]["depuis"]`, que seul le minuteur réécrit
   (l.667). Un `!discord` tapé par un viewer n'y touche pas : le chat peut revoir le
   lien 6 min après l'avoir reçu.
2. **L'annonce auto passe par le cache de 900 s.** Elle appelle le même callback que la
   commande (`cb("timer", "")`, l.660), donc `_generate_link_line`, qui rend la phrase
   en cache si elle a moins de 900 s (l.1073). 15 min d'intervalle et 900 s de cache se
   chevauchent dès qu'une commande a été tapée entre deux annonces. Et l'intervalle se
   règle dans le dashboard (5 min au minimum, `shared/twitch_chat.py` l.470) : à 5 min,
   le minuteur resservirait **sa propre** phrase trois fois de suite.

Hors périmètre, noté pour la SUITE suivante : **1 génération sur 27 a redonné mot pour
mot une phrase déjà écrite** (« Entre Henri, les lames et la boue de Bohême… », type
`designer`, 20:09:45 puis 22:56:07). C'est le modèle, pas le cache : ce plan ne le
corrige pas.

---

# LOT 1 — Le code (`shared/twitch/dispatch.py` seulement)

## 1.a — Une commande de lien tapée remet son minuteur à zéro

Dans `_handle_command`, **juste après** le `await send_chat_safe(...)` (l.586), et
seulement là (une commande bloquée par un cooldown ou par la limite globale n'a rien
envoyé, donc ne remet rien à zéro) :

```python
                    self._repousser_annonce_auto(chan, cmd_name, now)
```

Nouvelle méthode du mixin, placée juste avant `_try_link_timer` :

```python
    def _repousser_annonce_auto(self, chan: str, cmd: str, now: float) -> None:
        """Un lien tape par un viewer compte comme une annonce : le minuteur repart de zero.

        Sans ca, l'annonce auto tombait quelques minutes apres un `!discord` tape, et le chat
        relisait le lien qu'il venait de recevoir (Sugar, 3 fois sur 27 : 6 a 14 min d'ecart).
        """
        if not any(t["cmd"] == cmd for t in getattr(self, "link_timers", [])):
            return
        if not hasattr(self, "_etat_timers"):
            self._etat_timers = {}
        self._etat_timers[(chan.lower(), cmd)] = {"depuis": now, "msgs": 0}
```

- `cmd_name` est déjà résolu depuis l'alias (l.545) : `!ma_streameuse` repousse bien le
  minuteur de `!discord`. **Ne pas** re-résoudre l'alias dans la méthode.
- Une commande ne passe pas par le compteur de messages (`_handle_privmsg` rend la main
  l.387-388 avant la boucle l.456) : `msgs` repart bien de 0.
- Vaut aussi pour une commande de lien à **gabarit fixe** (champ « Message » rempli) :
  le chat a vu le lien de la même façon.

## 1.b — L'annonce auto n'emprunte jamais le cache

Nouvelle ContextVar, **juste sous** `_CANAL_COURANT` (l.18), avec un commentaire du même
ton :

```python
# Vrai pendant une annonce AUTO. Elle ne prend jamais la phrase en cache : le cache sert a
# ne pas payer un appel par `!discord` tape, et une annonce qui resert la phrase que le chat
# vient de lire est un doublon, pas une economie (Sugar, 27/09 : 20:09 puis 20:23).
_ANNONCE_AUTO = contextvars.ContextVar("annonce_auto", default=False)
```

Dans `_try_link_timer`, poser le drapeau **avec** le canal et le retirer dans le même
`finally` :

```python
            jeton = _CANAL_COURANT.set(chan)
            jeton_auto = _ANNONCE_AUTO.set(True)
            try:
                ...                                  # inchangé
            finally:
                _ANNONCE_AUTO.reset(jeton_auto)
                _CANAL_COURANT.reset(jeton)
```

Dans `_generate_link_line`, l.1073, **une seule condition ajoutée** :

```python
        if vue and not _ANNONCE_AUTO.get() and maintenant - vue[0] < 900:
```

- La phrase écrite par l'annonce auto **est** rangée dans le cache (l.1274, inchangé) :
  un `!discord` tapé juste après une annonce reçoit la même phrase sans appel LLM. C'est
  voulu (le viewer demande le lien, il le reçoit ; la commande ne pollue pas le chat
  toute seule).
- **Ne pas** toucher à la valeur 900, **ne pas** vider le cache, **ne pas** ajouter de
  paramètre à `_generate_link_line` ni au callback de `shared/twitch_chat.py` (les
  sondes `tools/sonde_phrase_de_lien.py` l'appellent avec trois arguments).
- Si la génération échoue pendant une annonce auto, le callback retombe sur le gabarit
  fixe comme aujourd'hui : **ne pas** ajouter de repli sur le cache.

**Aucun autre fichier de code ne change.** `shared/twitch/` n'est pas vendorisé
(`tools/vendor_core.py` ne le liste pas) : pas de copie à mettre à jour.

---

# LOT 2 — Les verrous (`tests/test_annonce_auto_ne_redit_pas.py`, nouveau)

Aucun appel réseau, aucun modèle : reprendre `_BotFactice`, `_avec_reponse` et la fixture
`_restaurer_cascade` de `tests/test_twitch_phrase_de_lien.py` (les **recopier** dans le
nouveau fichier, ne pas les importer d'un autre test). `send_chat_safe` remplacé par un
faux qui **range** ce qui est envoyé ; `_canal_en_direct` remplacé par une coroutine qui
rend `True`. Le temps est piloté en remplaçant `time.time` dans
`shared.twitch.dispatch` (modèle : `tests/test_twitch_features.py` l.334).

Le faux modèle rend une phrase **différente à chaque appel** (« Phrase 1 », « Phrase 2 »…)
pour que « même phrase » et « nouvel appel » se distinguent.

Les tests passent par les **vraies** méthodes `_handle_command` et `_try_link_timer`,
avec un vrai `link_timers` dont le callback appelle `bot._generate_link_line` (même forme
que `shared/twitch_chat.py` l.450-458). **Ne pas** appeler `_generate_link_line`
directement pour simuler l'annonce auto : c'est l'enchaînement qui était faux.

1. **Le cas vécu (20:09 → 20:23)** : minuteur 15 min armé depuis t=0, `!discord` tapé à
   t=100 → « Phrase 1 » envoyée. 15 messages, `_try_link_timer` à t=945 → **rien
   envoyé** (l'ancien code envoyait ici « Phrase 1 » depuis le cache). 15 messages
   encore, `_try_link_timer` à t=1001 → une phrase **différente** de « Phrase 1 » est
   envoyée. Deux appels au modèle au total. Ce test doit **échouer** sur le code
   d'avant la SUITE 13 : le vérifier une fois avec `git stash` et le noter dans le
   compte rendu.
2. **La commande repousse le minuteur** : minuteur armé depuis t=0 avec 15 messages,
   `!discord` tapé à t=850 → `_etat_timers[("canal", "discord")] == {"depuis": 850,
   "msgs": 0}`, et `_try_link_timer` à t=950 **n'envoie rien**.
3. **Par l'alias aussi** : même test que 2 en tapant l'alias → minuteur de `discord`
   repoussé.
4. **Intervalle court (5 min, `every=300`)** : minuteur armé à t=0, 15 messages avant
   chaque appel, `_try_link_timer` à t=301 puis à t=602 → deux phrases **différentes**,
   deux appels (l'ancien code resservait la première depuis le cache). Ce test aussi
   doit échouer sur l'ancien code.
5. **Le cache sert toujours les viewers** : annonce auto (« Phrase 1 ») puis `!discord`
   tapé 10 s après → le viewer reçoit « Phrase 1 », **un seul** appel au total.
6. **Le drapeau ne fuit pas** : après une annonce auto dont le callback **lève**, puis
   un `!discord` tapé → servi depuis le cache si une phrase y est (et
   `_ANNONCE_AUTO.get()` vaut `False` hors annonce).
7. **Une commande bloquée ne repousse rien** : `!discord` refusé par le cooldown global
   (5 s) → `_etat_timers` inchangé.
8. **Verrou AST** sur `shared/twitch/dispatch.py` : dans `_generate_link_line`, la
   comparaison au seuil `900` est dans un `if` qui lit `_ANNONCE_AUTO` ; dans
   `_try_link_timer`, `_ANNONCE_AUTO.set` et `_ANNONCE_AUTO.reset` sont présents, le
   `reset` dans un `finally`. (Le verrou vise des **noms**, pas du texte : cf. les
   verrous existants sur `dispatch.py`.)

Les tests existants **restent verts sans modification**, en particulier
`test_le_cache_evite_de_bruler_un_appel_par_commande` et
`tests/test_twitch_features.py::…test_try_link_timer`.

---

# LOT 3 — Vérifications avant commit

```bash
.venv/Scripts/python -m pyflakes shared/twitch/dispatch.py tests/test_annonce_auto_ne_redit_pas.py
.venv/Scripts/python -m pytest -q
```

- `pyflakes` **avant** `pytest`. Suite **entière** verte, **jamais deux pytest en
  parallèle** (port 8599).
- `git diff --stat` : exactement `shared/twitch/dispatch.py`, le nouveau test, et
  `PLAN.md` si besoin. Tout autre fichier = s'arrêter et le signaler.
- Commit : `fix(twitch): l'annonce auto ne ressert plus la phrase du cache (SUITE 13)`.
- Après le push : `gh run list --limit 3` jusqu'au vert. **Rouge = on ne déploie pas.**

---

# LOT 4 — Déploiement **[Ahmed]** donne l'accord, Antigravity exécute

**Un seul conteneur** : Sugar est le seul bot avec une annonce auto. Johnny prend aussi
le code au prochain redémarrage (sans effet pour lui : pas de minuteur), **ne pas** le
redémarrer pour ça.

```bash
docker restart bot-sugar
docker inspect -f '{{.State.StartedAt}} {{.RestartCount}}' bot-sugar
docker exec bot-sugar grep -c "_ANNONCE_AUTO" /app/shared/twitch/dispatch.py   # attendu : >= 4
docker logs --since <StartedAt> bot-sugar 2>&1 | grep -iE "error|traceback"      # attendu : rien
docker logs --since <StartedAt> bot-sugar 2>&1 | grep "Commandes de lien armees" # la ligne auto 15 min
```

Vérifier **`State.StartedAt`**, pas `CreatedAt` (erreur du compte rendu de la SUITE 12).
Aucun autre conteneur ne doit avoir un `StartedAt` postérieur à 10:22 UTC le 28/09.

---

# LOT 5 — Mesure en live **[Claude]**, au prochain live de Sugar

Sur les envois de `!discord` depuis le redémarrage :

```bash
docker logs --since <StartedAt> bot-sugar 2>&1 | grep -E "Envoyé sur .*discord.gg|Annonce auto|Phrase de lien"
```

- **0** envoi identique à l'envoi `!discord` précédent sur le même canal ;
- après chaque `!discord` tapé, l'annonce auto suivante arrive **≥ 15 min** plus tard ;
- chaque `⏰ Annonce auto` est précédée d'une ligne `✨ Phrase de lien` à la même seconde
  (preuve qu'elle n'a pas pris le cache), ou d'un envoi du gabarit fixe si la cascade
  a échoué.

Au moins **5 annonces auto** avant de clore. Le compte rendu donne les lignes brutes,
pas un résumé.
