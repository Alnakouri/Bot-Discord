# PLAN — Sheo : court PAR DÉFAUT, garanti par un filet déterministe (Discord + Twitch)

> Antigravity exécute. Claude a rédigé (2026-07-15).
> Cibles : `Sheogorath/sheo_data.py`, `Sheogorath/sheo_llm.py`, `Sheogorath/bot_sheogorath.py`,
> `shared/twitch/llm.py`, + tests. Repérer par CONTENU, pas par numéro de ligne.

## Contexte / décision user (tests live 2026-07-15 ~00:16)

Après e84488b+40be201 (arbitrage « le message décide » + ping d'un mot), test « sheo est-tu
fou ? » : réponses de 5-8 phrases sur les DEUX canaux. Verdict user : **« trop long sur
twitch et discord c trop »** — même une vraie question mérite une réponse courte par défaut.
Constat technique : 2 itérations de prompt n'ont pas suffi (Mistral déborde) → il faut un
**filet déterministe** en plus du prompt.

Principe : COURT PAR DÉFAUT (≤ 4 phrases), le déploiement long n'est permis QUE sur
invitation EXPLICITE du mortel à raconter/développer.

## Phase A — Prompt durci (`sheo_data.py`, bloc « ⚖️ QUI DÉCIDE DE LA LONGUEUR »)

REMPLACER les 3 puces internes existantes (« Pique courte… », « Question précise… »,
« PING D'UN MOT… », « Sujet riche… ») par :

```
  * PAR DÉFAUT : 1 à 3 phrases, 4 MAXIMUM. Piques, questions (même profondes : « es-tu
    fou ? »), pings, compliments : tout se répond COURT. Une réponse courte et dense est
    plus folle qu'une tirade — le couperet surprend, le tapis de mots endort.
  * Tu ne dépasses 4 phrases QUE si le mortel t'y INVITE EXPLICITEMENT (« raconte »,
    « explique », « développe », « continue », « une histoire »...). Là, le conteur peut
    serpenter — tant que chaque phrase AJOUTE.
```

GARDER la puce « L'EXCEPTION DU CONTEUR ne s'applique JAMAIS à une critique… » telle quelle.
Dans la puce « LONGUEUR = PERTINENCE… » plus haut, remplacer « Mais une tirade qui MONTE
(…) peut se déployer pleinement » par « Mais une tirade ne se déploie QUE sur invitation
explicite du mortel » (cohérence : plus deux règles qui se contredisent).

## Phase B — Filet déterministe Discord (`sheo_llm.py` + `bot_sheogorath.py`)

1. `sheo_llm.py` : nouveau helper pur, à côté de `force_short_response` :
```python
INVITATION_PATTERN = re.compile(
    r"\b(raconte|racontes?-moi|explique|développe|developpe|continue|détaille|detaille|"
    r"histoire|conte|poème|poeme|chante|décris|decris)\b", re.IGNORECASE)

def sentence_budget(user_message, short_cap=4, long_cap=10):
    """Filet déterministe : 4 phrases par défaut, 10 si le mortel invite à développer."""
    if user_message and INVITATION_PATTERN.search(user_message):
        return long_cap
    return short_cap
```
2. `bot_sheogorath.py` : là où `max_sentences_val = 10` est posé (les 2 branches REPARTEE
   et défaut, vers l.2248/2251), remplacer par
   `max_sentences_val = sentence_budget(user_message)` (importer `sentence_budget` à côté
   de `postprocess_response`). NE PAS toucher `max_tokens_val = 340` (l'espace pour les
   longues reste, c'est le filet qui décide).
3. Rappel comportement de `force_short_response` : coupe à la frontière de phrase, les
   « ... » ne comptent pas comme fins de phrase, l'emoji final est préservé — ne rien y
   changer, seul le budget passé varie.

## Phase C — Filet déterministe Twitch (`shared/twitch/llm.py`, générique)

1. Répliquer le helper `sentence_budget` + `INVITATION_PATTERN` (même logique, module
   autonome — pas d'import du bot, comme les autres gardes de parité).
2. Ajouter une coupe par phrases AVANT `_truncate_for_twitch(text, 480)` :
   `text = _force_sentence_cap(text, sentence_budget(clean))` où `_force_sentence_cap`
   reproduit la logique de `sheo_llm.force_short_response` (frontières de phrases, « ... »
   neutres, emoji final préservé). Défaut 4 phrases / 10 sur invitation → sur Twitch la
   limite 480 car. reste le plafond ultime.
3. ⚠️ GÉNÉRIQUE : ce filet s'applique à TOUS les bots du chat Twitch (Johnny, Sugar…).
   C'est VOULU (cohérent avec « longueur=pertinence » de Johnny), mais le seuil doit
   rester le même pour tous — pas de logique spécifique Sheo dans shared/.

## Phase D — Tests

1. `tests/test_sheo_moods.py` : asserts prompt — « 4 MAXIMUM » présent ; « INVITE
   EXPLICITEMENT » présent.
2. Nouveau bloc dans `tests/test_sheo_anti_tic.py` (ou fichier dédié) pour `sentence_budget` :
   - « t'es nul » → 4 ; « es-tu fou ? » → 4 ; « oui » → 4 ;
   - « raconte-moi une histoire » → 10 ; « explique-moi la Marche Grise » → 10 ;
   - « continue » → 10 ; casse mélangée (« RACONTE ») → 10.
3. Miroir Twitch : `_force_sentence_cap` coupe à 4 une réponse de 8 phrases ; préserve
   l'emoji final ; laisse passer 10 phrases sur « raconte » ; les « ... » ne comptent pas.
4. Suite complète verte (213+).

## Garde-fous

- Ne PAS toucher : humeurs, anti-écho (e84488b), few-shot, max_tokens (340 Discord /
  120 Twitch), `_truncate_for_twitch`.
- Le filet coupe la QUANTITÉ, le prompt reste responsable de la QUALITÉ : ne pas retirer
  les règles de densité existantes.
- `sentence_budget` doit être PUR (aucun état, aucun I/O) — testable sans mock.

## Déploiement + re-test (après commit)

`docker compose up -d --build --force-recreate sheogorath johnny sugar`
(shared/ touché → --build ; Johnny et Sugar héritent du filet Twitch générique).
Sondes : « es-tu fou ? » → ≤ 4 phrases (les 2 canaux) · « t'es nul » → 1-2 sèches ·
« raconte-moi une histoire » → longue autorisée · vérifier que la coupe ne laisse pas de
phrase orpheline ni ne mange l'emoji final.
