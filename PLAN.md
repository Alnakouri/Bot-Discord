# PLAN — Phrase de lien : un guillemet ORPHELIN sort dans le chat

Rédaction : Claude, le **2026-09-27**. Exécution : **Antigravity**. Plan précédent (SUITE 5 à
7, tout clos) lisible dans git (`b1b64f1:PLAN.md`).

Un seul fichier de code : `shared/twitch/dispatch.py` (+ un test). Pas de copie vendorée :
`shared/twitch/` n'est pas dans `tools/vendor_core.py`.

---

## LE CONSTAT (live, vérifié le 27/09)

Phrase publiée par Sugar sur `#ma_streameuse` (`docker logs bot-sugar`, 20:04:23) :

```
… Racontez-nous ça sur le serveur, j’écoute avec des bonbons. » 🍬 https://discord.gg/…
```

Le `»` n'a pas de `«`. Le modèle avait ouvert une citation dans son brouillon, le premier
essai a été rejeté, et le second a gardé la fermeture sans l'ouverture.

**Mesure** : 72 h de logs, les six bots, lignes `écrite par le bot` → **12 phrases, 1 avec
un guillemet orphelin** (Sugar). Les onze autres sont propres.

**Reproduit hors live** (`.venv`, `PYTHONIOENCODING=utf-8`) :

| entrée | sortie actuelle de `_nettoyer_phrase_de_lien` |
|---|---|
| `… avec des bonbons. » 🍬` | `… avec des bonbons. » 🍬` ❌ |
| `Venez en parler sur Discord ! " 🍬` | `Venez en parler sur Discord ! " 🍬` ❌ |
| `*Venez en parler sur Discord !` | `*Venez en parler sur Discord !` ❌ |
| `Venez en parler sur Discord ! ”` | `Venez en parler sur Discord ! ”` ❌ |
| `« Venez nous en parler sur Discord ! 🍬` | `Venez nous en parler sur Discord ! 🍬` ✅ (déjà géré) |

**Cause** : le déballage (`dispatch.py` l.254–270, boucle l.255) et `_strip_wrapping_quotes`
(`sanitize.py`) ne retirent que des **paires** qui entourent la phrase entière. Un
délimiteur seul n'est retiré par personne.

---

# LOT 1 — Retirer les délimiteurs orphelins dans `_nettoyer_phrase_de_lien`

**Fichier** : `shared/twitch/dispatch.py`, fonction `_nettoyer_phrase_de_lien` (l.232).

**Où** : juste APRÈS `phrase = strip_stage_directions(phrase)` (l.272), AVANT le calcul de
`premiere = next(...)` (l.284). L'ordre compte : le test de majuscule doit voir la phrase
sans le `*` ou le `«` de tête.

**Quoi** : pour chaque délimiteur, s'il est orphelin, retirer **toutes** ses occurrences,
puis réduire les espaces :

- paires asymétriques `«`/`»` et `“`/`”` : orphelin = le nombre d'ouvrantes ≠ le nombre de
  fermantes → retirer les deux caractères de la paire ;
- délimiteurs symétriques `"` et `*` : orphelin = nombre **impair** → retirer toutes les
  occurrences ;
- ensuite `" ".join(phrase.split())`.

Retirer toutes les occurrences plutôt que deviner laquelle est de trop : on perd au pire
les guillemets d'un titre (`"Elden Ring"`), jamais un mot. Même esprit que le reste de la
fonction : on ne devine pas ce qui manque ([[gotcha-nettoyeur-laisse-ce-qui-rattachait]]).

**⚠️ Pièges** :

1. **Ne JAMAIS toucher `’` ni `'`** : ce sont des apostrophes (« j’écoute »). La paire
   `‘`/`’` de `_WRAPPING_QUOTE_PAIRS` ne doit PAS être reprise ici, sinon « j’écoute »
   devient « jécoute ».
2. **Ne pas modifier `shared/twitch/sanitize.py`** : `strip_stage_directions` sert aussi
   aux réponses du chat, hors de ce périmètre.
3. **Réparer, pas rejeter**, contrairement au reste de la fonction : la phrase est
   intacte, seul le signe est de trop. La rejeter coûterait un appel de plus, ou le
   gabarit fixe, pour un caractère.
4. Une ligne de commentaire au-dessus du bloc, dans le style du fichier : `⚠️`, la phrase
   du live du 2026-09-27 et la mesure 1/12.

# LOT 2 — Le test

**Fichier** : `tests/test_twitch_phrase_de_lien.py`, à placer après
`test_le_nettoyeur_retire_didascalies_guillemets_et_ponctuation_d_annonce` (l.116).

`test_un_guillemet_ORPHELIN_ne_sort_pas_dans_le_chat` doit vérifier :

```python
# le cas du live, mot pour mot
assert _nettoyer_phrase_de_lien(
    "Alors, ce Henry qui vous a fait hurler des jurons en vieux tchèque sans comprendre "
    "un mot ? Racontez-nous ça sur le serveur, j’écoute avec des bonbons. » 🍬"
) == ("Alors, ce Henry qui vous a fait hurler des jurons en vieux tchèque sans comprendre "
      "un mot ? Racontez-nous ça sur le serveur, j’écoute avec des bonbons. 🍬")
assert _nettoyer_phrase_de_lien('Venez en parler sur Discord ! " 🍬') == "Venez en parler sur Discord ! 🍬"
assert _nettoyer_phrase_de_lien("*Venez en parler sur Discord !") == "Venez en parler sur Discord !"
assert _nettoyer_phrase_de_lien("Venez en parler sur Discord ! ”") == "Venez en parler sur Discord !"
# ce qui doit RESTER intact
assert _nettoyer_phrase_de_lien("Venez, j’écoute !") == "Venez, j’écoute !"           # apostrophe
assert _nettoyer_phrase_de_lien('Parlez-nous de "Elden Ring" sur Discord !') == 'Parlez-nous de "Elden Ring" sur Discord !'
assert _nettoyer_phrase_de_lien("Parlez-nous de « Elden Ring » sur Discord !") == "Parlez-nous de « Elden Ring » sur Discord !"
```

Plus l'**idempotence** ([[gotcha-un-filtre-non-idempotent-laisse-du-travail-a-l-ecran]]) :
pour chaque entrée ci-dessus, `f(f(x)) == f(x)`.

⚠️ Avant de figer les valeurs attendues, **exécuter** chaque cas et vérifier que la sortie
actuelle est bien celle du tableau du constat : les autres filets de la fonction
(`_NOMME_LA_SOURCE`, `_VISE_LE_PUBLIC`…) ne doivent rejeter aucune de ces phrases. Si l'un
d'eux en rejette une, changer la PHRASE du test, pas le filet.

# LOT 3 — Livrer

1. `python -m pyflakes shared/twitch/dispatch.py tests/test_twitch_phrase_de_lien.py`
2. `pytest tests/test_twitch_phrase_de_lien.py tests/test_phrase_de_lien_jeu_en_cours.py
   tests/test_phrase_de_lien_clause_par_bot.py`, puis la suite complète (**jamais deux
   pytest en parallèle**, port 8599).
3. Commit `fix(twitch): retirer les guillemets orphelins de la phrase de lien`, push,
   **`gh run list` jusqu'au vert**.
4. Redémarrer hors live les bots qui ont `!discord` armé : `docker restart bot-sugar
   bot-johnny`. Vérifier dans le conteneur que le nouveau code est présent
   (`docker exec bot-sugar grep -c "orphelin" /app/shared/twitch/dispatch.py`, adapter le
   chemin si besoin) et qu'il n'y a pas d'erreur dans `docker logs --since 5m`.

**Critère de clôture** : tests verts, CI verte, conteneurs redémarrés sans erreur. Pas de
mesure LLM nécessaire : le correctif est déterministe et ne change pas le prompt.

---

## Hors périmètre (noté, NON planifié)

- **Johnny, dates inventées** (5 replis sur 18 en mesure, SUITE 6-ter) : **une seule phrase de
  lien de Johnny en live en 72 h** (propre), aucune depuis la livraison de SUITE 6-ter. Rien à
  corriger tant que le live ne montre pas de replis. Le levier reste une clause dans
  `CLAUSES_FORME_JEU_PAR_BOT["johnny"]`, formulée **positivement** et **sans date
  d'exemple** ([[gotcha-le-prompt-enseigne-le-tic-interdit]]).
- **Alfred, boisson inventée (3/4)** : dormant, `!discord` n'est pas armé chez lui.
- **Sugar, ouvertures** : 6 phrases live sur 10 commencent par « Combien de », « boues
  médiévales » revient 3 fois. À surveiller ; « même invitation mot pour mot » était à 4/18
  en mesure.
