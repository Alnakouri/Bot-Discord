# PLAN — les 5 « MOOD CHANGE » : ce n'etaient pas 5, et ce n'etait pas l'humeur

Redaction et execution : Claude, le 2026-09-06.

Le point ouvert disait : « **5 `MOOD CHANGE` dans la meme seconde** apres une reconnexion :
jamais explique. » Il est explique. Il y en avait **40**, et le changement d'humeur n'y
etait pour rien.

---

## Etat : vert  🟢

**644 tests passent** (+46 sous-tests), suite complete en un seul processus. CI verte (`34027591224`), les 6 conteneurs redemarres et le correctif **constate dans les 6 journaux**.

---

## Ce que le journal disait vraiment

`docker logs bot-sheogorath`, groupe par horodatage :

    38 lignes MOOD CHANGE a 11:20:50   (+2 a 11:20:49)
    20 lignes MOOD CHANGE a 14:00:40

Et le contexte, le 2026-09-04 :

| heure | evenement |
|---|---|
| 07:56:28 | dernier `MOOD CHANGE` normal |
| — | **3 h 21 sans une seule ligne** : l'hote etait en veille |
| 11:17:36 | `Shard ID None session has been invalidated` — reconnexion de la gateway |
| 11:20:49–50 | **40 `MOOD CHANGE` en deux secondes** |

40 × 5 min = 200 min = **exactement le trou**.

⚠️ Le premier reflexe — « `on_ready` rejoue et relance la boucle » — etait faux. Les
gardes `is_running()` sont en place depuis `839fae5` et tiennent. La cause est ailleurs.

---

## La cause : `tasks.loop` dort jusqu'a un instant ABSOLU

`discord/ext/tasks/__init__.py` :

```python
def _get_next_sleep_time(self, now=MISSING):
    if self._sleep is not MISSING:
        return self._last_iteration + datetime.timedelta(seconds=self._sleep)
```

L'instant du prochain tour est calcule depuis **l'iteration precedente**, jamais depuis
« maintenant ». Quand l'horloge saute, cet instant est deja passe : la boucle s'execute,
recalcule `precedent + intervalle`, retombe sur un instant **encore** passe, recommence.
Elle rejoue tout le retard, dos a dos.

⚠️ discord.py **a** une correction de derive d'horloge — mais elle est gardee par
`while self._is_explicit_time() and ...` : elle ne s'applique qu'aux boucles a heure fixe
(`time=`). Les boucles a intervalle, **c'est-a-dire toutes les notres**, n'ont aucun filet.

**Mesure de reproduction** (10 lignes, sans Discord) : un saut de 10 minutes sur une
boucle de 5 s produit **120 rattrapages en 7 ms**.

---

## Pourquoi seul le changement d'humeur se voyait

Parce qu'il est **le seul a journaliser chaque tour**. Les 29 autres boucles ont rattrape
en silence. Pour une veille nocturne de 8 h, les memes secondes rejouent :

| boucle | intervalle | rattrapages |
|---|---|---|
| `vocal_patrol_loop` | 30 s | 960 |
| `voice_idle_check` | 60 s | 480 |
| `twitch_poll_loop` (×6 bots) | 90 s | 320 **chacune** |
| `check_missed_mentions_*` | 2 min | 240 |
| `mood_changer`, `decree_cleanup_loop`, `riddle_passive_hint_loop` | 5 min | 96 |
| `daily_bio_loop_*`, `daily_rumor_check_*` | 1 h | 8 |

`twitch_poll_loop` appelle l'API Twitch. Ce n'etait donc pas du bruit de journal : c'est
**pres de 4 000 corps de boucle en une fraction de seconde a chaque reveil de la machine**,
dont des milliers d'appels reseau.

---

## La correction : `shared/boucles.py`  ✅

On ne touche pas aux 30 boucles une par une — on corrige le calcul, **une fois**, pour
toutes les boucles du processus, y compris celles de `shared/twitch/` et celles qui
seront ecrites demain. Si l'instant calcule est deja passe, on repart de maintenant au
lieu de rejouer le retard, et on le **dit** dans le journal.

`installer_anti_rattrapage(logger)` est pose dans le `if __name__ == "__main__"` des 6
bots, juste avant `setup_graceful_shutdown`. **Pas au niveau module** : les tests importent
ces fichiers, et un correctif global pose a l'import empecherait de tester le defaut.

⚠️ Effet de bord assume : un corps de boucle qui dure plus longtemps que son propre
intervalle attend desormais un intervalle complet au lieu de repartir aussitot. C'est le
comportement souhaitable — sans quoi la boucle s'empile sur elle-meme.

⚠️ `boucles.py` a ete ajoute aux **DEUX** listes de vendoring
([[gotcha-deux-listes-vendoring]]) : `vendor_core.py` copie, `sonde_core_drift.py`
surveille. Un module absent de la seconde serait vendorise sans filet.

## Le verrou : `tests/test_anti_rattrapage_boucles.py`

9 tests. Le premier est un **temoin** : il verifie que **le defaut existe toujours** dans
la version installee de discord.py. Sans lui, une correction en amont rendrait les autres
verts alors que plus rien ne protegerait, et personne ne le saurait.

Les autres : le correctif supprime le rattrapage (120 appels → 2), la pose est
**idempotente** (`on_ready` rejoue a chaque reconnexion — deux poses empileraient un
enrobage sur l'autre), et chacun des 6 bots **importe ET appelle**
([[gotcha-import-ajoute-mais-pas-cable]]).

---

## L'addendum : le correctif ne se voyait nulle part

`da4a852` n'ecrit qu'une seule ligne — celle du rattrapage abandonne — et elle n'apparait
**qu'apres une vraie veille de l'hote**. Sur une machine qui tourne, rien ne permettait de
constater que le filet etait en place : le meme piege que
[[gotcha-echelon-de-secours-invisible]], applique cette fois a un correctif.

`installer_anti_rattrapage` **dit maintenant sa pose** au demarrage, et se tait quand elle
etait deja faite (`on_ready` rejoue a chaque reconnexion — une 2e pose qui parlerait
polluerait le journal a chaque coupure reseau). 2 tests de plus, verifies **par la
negative** : retirer la ligne fait tomber le test.

Constate le 06/09 sur les 6 conteneurs :

    10:30:20 | INFO | [BOUCLES] anti-rattrapage pose : les iterations manquees ne seront pas rejouees

⚠️ Exhume au passage : au `docker restart`, Malena log `[MISSED CHECK] Erreur canal idee:
Session is closed` — une boucle encore en vol quand la session se ferme. Benin (c'est
l'arret, pas le demarrage), mais le graceful shutdown ne l'annule pas. Note dans les points
ouverts.

---

## Ce que la lecture du journal a exhume au passage

Le meme reveil du 04/09 montre `on_ready` mourir sur
`CommandAlreadyRegistered: Command 'reputation' already registered` — la 2e pose des
commandes slash. **Ce cas est deja couvert** : les 6 bots enveloppent
`setup_slash_commands` dans un `try/except` depuis `839fae5`, et
`tests/test_latence_et_quota.py` l'exige. La trace du journal est anterieure au correctif.

---

## Ce qui reste ouvert

- **`report_error` n'est appele que pour Gemini** : decision de design a poser. C'est le
  dernier vrai point de la liste.
- **Bruit d'arret** : `[MISSED CHECK] Erreur canal idee: Session is closed` chez Malena a
  chaque `restart` — le graceful shutdown n'annule pas les boucles en vol.
- Un reglage nemotron plus mordant que `reasoning_effort=none` : jamais sonde, NVIDIA
  rate-limite des qu'on enchaine. Sans urgence.
- Un **5e fournisseur reste inutile** : NVIDIA, 4e echelon, a **0 appel** en base sur
  342 lignes depuis avril. Un 5e se placerait derriere un echelon jamais atteint.
- Le reste de [[dette-validation-live]] : ce qui exige un humain, un clic ou un vrai live.
- Les 2 pistes de fond : Phase 3 repartie, migration mempalace.

---

## Regles de travail — celles qui ont paye aujourd'hui

- ⚠️ **Un chiffre rapporte de memoire est un chiffre a re-mesurer.** « 5 MOOD CHANGE »
  etait 40, et la cause n'avait rien a voir avec l'humeur.
- ⚠️ **Grouper le journal par horodatage** (`awk | sort | uniq -c`) montre les rafales
  qu'une lecture lineaire noie.
- ⚠️ **Ce qui se voit dans un journal, c'est ce qui journalise.** 29 boucles rattrapaient
  en silence ; seule celle qui parle a trahi les 29 autres.
- ⚠️ **Reproduire le defaut avant de le corriger**, et **garder le temoin dans la suite** :
  un correctif dont on ne verifie plus que le probleme existe devient un no-op silencieux.
- ⚠️ **Verifier l'indentation de la cible avant d'inserer** : `setup_graceful_shutdown`
  est a 4 espaces chez 2 bots et a 8 chez 4 autres. L'insertion aveugle a casse 4 fichiers,
  rattrapee par `py_compile`.
- ⚠️ **Ne jamais lancer deux `pytest` en parallele** : ils partagent `data/` et le port 8599.
