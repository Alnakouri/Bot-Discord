# PLAN — Conformité règles Twitch (sans trahir le persona) : filtre ToS + bio propre + accueils variés

## Contexte (test live 2026-07-02, Johnny sur #ma_streameuse)
Persona apprécié (« j'adore ce bot 😂 »), rapide, WS stable, 0 `[laugh]` en chat. MAIS Johnny a lâché
des **menaces de violence** vers de vrais users (« une balle dans le crâne », « dans les dents ») →
**risque de ban Twitch** (aucun filtre n'existe, vérifié). Aussi : bio Twitch avec `[laugh]`, et accueil
répété verbatim.

**Décision user (2026-07-03) :** le bot doit **respecter les règles Twitch tout en RESTANT FIDÈLE à sa
personnalité**. Donc : **PAS de « mode chaîne invitée »** (persona complet partout), on filtre UNIQUEMENT
ce qui casse réellement les règles Twitch (menaces de violence, propos haineux/slurs) — le mordant, les
vannes et le franc-parler RESTENT. Les **interjections** = désactivées par le user via le dashboard
(Configuration → bot → Twitch → Présence → « interjections spontanées »), pas besoin de code.

Tout est dans **`shared/twitch/`** (bénéficie aux 6 bots), 0 réseau/LLM.

---

## Axe A — Filtre de sortie ToS (le cœur)
**But :** aucune réponse ne part sur Twitch si elle enfreint les règles Twitch — **sans toucher aux
insultes/vannes ordinaires** (qui, elles, font partie du perso et sont tolérées par Twitch).

**Ne filtrer QUE les vraies violations ToS :**
- **Menaces de violence réelle** envers une personne : « (une) balle dans (le crâne/la tête) », « te
  (tue|bute|défonce|frappe|explose|démonte) », « te faire la peau », « dans les dents », « te crever »…
- **Propos haineux / slurs** (racistes, homophobes, etc.) : petite liste curée.
- (Optionnel) menaces de mort explicites, doxx.

**Ce qu'on NE filtre PAS (le persona reste intact) :** « t'es un gonk », « script kiddie à l'ego
surdimensionné », « ripperdoc qui a oublié de brancher son cerveau », le franc-parler, le sarcasme, le
mépris théâtral. C'est le sel des persos, et ce n'est pas contraire aux règles Twitch.

**Implémentation :**
1. **Un seul choke-point pour TOUT le contenu envoyé** : créer un helper partagé
   `async def send_chat_safe(ws, chan, text, *, bot_id=None, logger=None)` (dans `shared/twitch/sanitize.py`
   ou `connection.py`) qui applique `sanitize_twitch_output()` PUIS `ws.send_str(f"PRIVMSG #{chan.lower()} :{text}")`.
   Router **TOUS** les envois de contenu par lui (⚠️ 8 points, pas 5) :
   - `dispatch.py` l.57/100/159/187/210 (réponse, passif, commande, accueil, interjection),
   - `events.py` l.26 (**réactions subs/raids/bits — clé pour Sheo**),
   - `eventsub_bridge.py` l.59 (messages pilotés EventSub),
   - `voice.py` l.68 (réponses issues de l'écoute live).
   NE PAS toucher les `send_str` PROTOCOLE de `connection.py` (CAP/PASS/NICK/JOIN/PONG l.147-169) : ce
   n'est pas du contenu de chat.
2. **`sanitize_twitch_output(text)`** (nouveau, `shared/twitch/sanitize.py`, 0 LLM, regex insensible
   casse+accents comme l'anti-injection existant) :
   - `VIOLENCE_PATTERNS` + `HATE_PATTERNS` curés.
   - Si match → **réécriture soft** ciblée : remplacer le segment fautif par un équivalent NON-violent
     qui garde le mordant (table : « une balle dans le crâne » → « une bonne leçon d'humilité » ;
     « dans les dents » → « en pleine figure » ; slur → terme neutre méprisant « pauvre type »…).
   - Si après substitution il reste un motif fautif → **fallback** : remplacer TOUTE la réponse par une
     pique sûre in-persona (petit pool générique passé par l'appelant / par défaut neutre).
   - Log `⚠️ [TWITCH_SAFETY:{bot}] contenu ToS filtré`.
3. S'applique à TOUS les envois Twitch de contenu (réponse, accueil, passif, interjection, **réactions
   d'événements raids/subs/bits**, EventSub, voix) → couvre Sheo comme les 5 autres.

## Axe B — Bio Twitch propre (crochets `[laugh]`)
- Ajouter le strip des crochets TTS au **sanitize partagé** `strip_stage_directions`
  (`shared/twitch/sanitize.py`), après les strips existants :
  `re.sub(r"\[(laugh|chuckle|sigh|shout|laughs|giggle|whisper|sob|cough|gasp)\]", "", text, flags=re.I)`
  → nettoie le bio (`daily_profile.py:126`) ET le chat, pour les 6 bots.
- Le bio actuel est persisté : re-nettoyé au prochain rafraîchissement quotidien (ou purge ponctuelle si
  `[` présent — optionnel).

## Axe C — Variété des accueils
- `shared/twitch/memory.py` `_generate_templated_greet` : `random.choice` + **anti-répétition** (retenir
  le dernier template envoyé par chaîne, ne pas le reprendre juste après). Vérifier ≥ 3-4 variantes
  « new » par persona.

---

## Ce qu'on GARDE / ne casse pas
- **Le persona complet, partout** (mordant, edge, sarcasme, insultes non-violentes) — c'est voulu.
- Réponse sur mention, accueil de session, anti-injection (`ANTI_INJECTION_GUARD`), rate-limits (18/30s),
  cooldowns, silence entre bots (`TWITCH_PEER_BOTS`), strip didascalies v3.
- Les interjections restent pilotables par le dashboard (le user les coupe lui-même) — pas de modif code.
- Aucune modif de la génération LLM ni de la cascade.

## Critères d'acceptation
1. Une réponse avec « une balle dans le crâne » (ou motif violent/haineux) **ne part JAMAIS tel quel** :
   réécrite soft ou remplacée par une pique sûre ; log `TWITCH_SAFETY`.
2. Une vanne NON-violente (« t'es un gonk à l'ego surdimensionné ») **passe INCHANGÉE** (persona préservé).
3. Le bio Twitch n'affiche plus `[laugh]`/`[chuckle]`/etc.
4. Accueils variés (pas deux fois le même verbatim de suite).
5. Persona complet inchangé sur toutes les chaînes (pas de « mode réservé »).
6. `py_compile` OK ; `pytest tests/` vert (+ nouveaux tests filtre ToS + strip bio).

## Tests
- `test_sanitize_twitch_output` : menace violente/haineuse → assainie ; **vanne non-violente → inchangée**
  (garde-fou anti-sur-filtrage) ; phrase saine → inchangée.
- `test_strip_stage_directions_removes_tts_brackets` : `[laugh]` retiré via le strip partagé.

## Notes pour Antigravity
- Fichiers : `shared/twitch/sanitize.py` (filtre ToS + strip crochets + helper `send_chat_safe`),
  `shared/twitch/dispatch.py` + `events.py` + `eventsub_bridge.py` + `voice.py` (router leurs envois de
  CONTENU par `send_chat_safe`), `shared/twitch/memory.py` (variété accueil). PAS de « home_channels »,
  PAS de mode réservé (abandonné à la demande du user).
- **NE TOUCHER À AUCUN code Discord** (bot_*.py côté Discord, sheo_data.py, sheo_llm.py, etc.). Tout est
  Twitch-only via `shared/twitch/` → la version Discord des 6 bots reste STRICTEMENT inchangée. Le filtre
  est un post-traitement de SORTIE Twitch, il ne touche ni les prompts/persona ni Discord.
- 0 réseau/LLM (patterns curés). **Rester CONSERVATEUR côté filtre : le risque = sur-filtrer et neutrer
  le perso.** Ne viser QUE menaces de violence + haine/slurs ; laisser passer le franc-parler.
- Code PARTAGÉ → vérifier que les 6 bots démarrent et chattent encore.
- Après exécution : `pytest` + relire le filtre sur 3 cas (menace → assainie, insulte simple → intacte,
  phrase saine → intacte). Test live user : provoquer une réponse violente et vérifier qu'elle sort propre.
