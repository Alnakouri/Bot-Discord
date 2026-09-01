# Chantier — la cascade REPARTEE annonçait un modèle qui n'existe plus

Session du 2026-09-01 (2e partie). Parti d'une ligne classée « dette cosmétique »,
le défaut s'est révélé plus large : **du code et des logs qui décrivaient un monde
disparu**, sans qu'aucun filet ne puisse le voir.

## Le constat

`get_model_cascade` rend **exactement la même cascade** pour `TEXT` et pour `REPARTEE`
(`shared/smart_router.py`) : depuis le passage à une cascade par persona, la distinction
ne sélectionne plus aucun modèle. Or tout autour d'elle affirmait le contraire :

- les logs runtime annonçaient `🎭 Banter adressé → Grok (xAI)` et
  `🎭 Humour / Répartie → Grok (xAI)` — **Grok a disparu du code** ;
- `🧠 Raisonnement complexe → Gemini Pro` : la cascade REASONING n'a jamais mené à un
  « Pro » ;
- `RequestType` documentait `IMAGE`/`AUDIO` comme « Gemini 2.0 Flash », génération
  retirée à l'audit du 24 août ;
- le commentaire du garde `addressed` justifiait un **coût** (« Grok est payant ») qui
  n'existe plus ;
- `JohnnyBot/bot_johnny.py` promouvait TEXT → REPARTEE « pour mettre Grok en priorité » :
  aucun effet sur le modèle, mais la phrase partait dans `routing["reason"]`, **journalisé
  par `llm_cascade`**, donc annoncée à chaque réponse de Johnny ;
- `Sheogorath/bot_sheogorath.py` : `if REPARTEE: ... else: ...` aux **deux branches
  identiques ligne pour ligne** (les plafonds avaient été alignés sans retirer le test).

## Ce qui a été fait

1. **Textes** — plus aucun modèle nommé dans `shared/smart_router.py` ni
   `shared/twitch/llm.py` : les commentaires renvoient à `get_model_cascade`, seule
   autorité. Raisons de log ramenées à ce qu'elles décrivent vraiment
   (`🎭 Banter adressé`, `🎭 Humour / Répartie détecté`, `Texte simple`).
2. **Code inerte** — promotion no-op de Johnny supprimée (+ son import
   `get_model_cascade`, jamais appelé) ; branches identiques de Sheo fusionnées.
   L'historique de chaque suppression est conservé en commentaire : c'est lui qui
   explique pourquoi le code avait cette forme.
3. **Vendoring** — `python tools/vendor_core.py` puis `tools/sonde_core_drift.py` :
   *No drift detected* sur les 6 copies.

## Ce qui n'a PAS été fait, et pourquoi

- **`RequestType.REPARTEE` est conservé.** Il ne choisit plus de modèle, mais il reste un
  signal de classification correct, et le supprimer toucherait ~8 tests pour un gain nul.
- **Aucun nouveau test de garde.** `tests/test_model_ids.py` scanne déjà les `.py` pour
  les *identifiants* morts. Il n'a rien vu ici parce que les commentaires disaient
  « Grok » en toutes lettres, pas `x-ai/grok`. Interdire les noms de marque en prose
  ferait tomber les notes historiques légitimes (y compris celles de ce chantier).
  ⚠️ **La leçon est donc à retenir, pas à outiller : un filet sur les identifiants ne
  protège pas la prose.**

## Vérifications

- 6 bots : `py_compile` OK.
- Sonde de dérive vendoring : verte.
- Suite complète : voir la session (aucun test ne portait sur les morceaux retirés —
  vérifié avant de toucher au code).

---

# Suite — CI : sortir de Node 20 avant que ça casse

Relevé dans les annotations du run `33527961612` : `actions/checkout@v4` et
`actions/setup-python@v5` ciblent Node 20, **déjà forcées sur Node 24** par le runner,
avec un avertissement à chaque exécution. C'est une panne programmée, pas un détail.

Montées en `v7` toutes les deux (vérifié : `runs.using = node24` dès v5/v6
respectivement, et v7 pour les deux). Aucun changement cassant pour cet usage — la seule
rupture des notes de version est l'exigence d'un runner ≥ v2.327.1 (largement dépassée
sur les runners hébergés) et le retrait de l'entrée `pip-install` en v7, que ce workflow
n'utilise pas. `python-version: "3.12"` et `cache: pip` sont inchangés.

Aucun test ni document ne référence ces versions — la CI elle-même est la vérification.
