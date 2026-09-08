# PLAN — Phase 3 de la repartie : apprendre de ses defaites

Redaction : Claude, le 2026-09-08, sur feu vert user du jour (« Phase 3 repartie (re-spec) »).
Remplace le protocole des tests live : ses sessions 1, 1-bis et 2 sont **jouees et closes**
(detail en memoire, `test-live-session1-2026-09-07`), et sa partie Twitch est **gelee** —
elle est conservee telle quelle en **annexe**, a rouvrir seulement quand l'utilisateur en
reparle.

Execution : **Antigravity**. ⚠️ Relire ce qu'il livre avant de commiter, et commencer par
`pyflakes`, pas par `pytest` : 62 `logger` indefinis n'avaient casse aucun test.

---

## Ce que le chantier veut obtenir, en une phrase

Un bot qui se fait battre en joute doit changer de **comportement**, pas apprendre une
vanne. La lecon retenue est une **meta-regle** (« arrete de te justifier, retourne
l'accusation »), jamais une repartie figee — une repartie figee redeviendrait le tic que
trois filets passent deja leur temps a casser.

---

## Pourquoi on RE-specifie au lieu de ressortir le design de juin

Le design de 2026-06-10 est toujours en memoire (`plan-repartie-auto-amelioration`), et il
est bon. Mais **trois de ses appuis n'existent plus**, et les reprendre tels quels ferait
ecrire du code sans effet :

1. **Le code d'origine est perdu**, jamais commite (`git log -S` = 0 occurrence). Il n'y a
   rien a recuperer, seulement a reconstruire.
2. **Le but affiche a peri.** Phase 3 devait « mieux nourrir la cascade REPARTEE **quand
   Grok la pilotait** ». Grok a disparu du code, et `get_model_cascade` rend aujourd'hui
   la **meme liste** pour `TEXT` et pour `REPARTEE`, prouve a l'execution sur les 6
   personas. ⚠️ **Ce chantier ne doit RIEN attendre du routage et n'y touche pas.**
   `RequestType.REPARTEE` reste un signal de classification juste, c'est tout.
3. **La « Couche A » est deja livree — sous un autre nom, et chez UN seul bot.** Le design
   demandait un `detect_gimmick_lock`. Ce qui existe s'appelle `build_anti_tic_consigne`
   (`Sheogorath/sheo_llm.py:527`) cote Discord, et `_build_anti_tic_consigne`
   (`shared/twitch/llm.py:185`) cote Twitch. Chercher le nom du CONCEPT, jamais le nom
   qu'on lui aurait donne soi-meme.

---

## L'etat verifie le 08/09 — a ne pas re-chercher

| Ce qu'on croit devoir ecrire | Ce qui existe deja, et ou |
|---|---|
| anti-boucle sur le mot-a-mot | `ResponseMemory` (`shared/response_memory.py`, 28 lignes) + bloc `[ANTI-REPETITION]` chez les 5 bots a transcript |
| anti-boucle sur le **motif** | `build_anti_tic_consigne` — **chez Sheo SEUL** cote Discord (`bot_sheogorath.py:2279`) ; version generique cote Twitch |
| few-shot de comebacks tournants | `COMEBACK_POOL` + `get_random_comebacks(5)` injectes par `{comebacks_placeholder}` |
| longueur de la riposte | `sentence_budget(user_message)` — plus aucune constante |
| un appel LLM isole, propre | `appel_hors_cascade` (`shared/llm_cascade.py:520`) : cle du pool, quarantaine, `report_error`, tracage, borne de temps |
| un bot ne nomme jamais sa mecanique | verrou en place depuis le 07/09, 4 fuites corrigees |

**Les 5 bots a transcript** : Sheogorath, Alfred, Johnny, M'aiq, Sugar.
**Malena est hors chantier** : elle appelle le LLM avec `transcript=""` — il n'y a pas de
joute a observer chez elle. ⚠️ C'est la seule exclusion legitime ; partout ailleurs,
compter **les cinq** avant d'ecrire « fait ».

---

## Lot 1 — le filet « tu boucles » la ou il manque (4 bots)

**Le defaut, mesurable aujourd'hui** : Alfred, Johnny, M'aiq et Sugar n'ont que le bloc
`[ANTI-REPETITION]`, qui liste les 5 dernieres repliques et interdit de les **repeter**.
Il ne voit pas un **moule** qui revient. C'est exactement ce qui a echappe aux filets de
Sheo le 07/09 : `Haskill, <ordre>` tenait 7 repliques sur 8 sans qu'une seule phrase soit
repetee.

**A faire** :

1. Promouvoir **une seule** implementation dans `shared/anti_tic.py`, batie sur celle de
   Sheo — c'est la plus complete, elle porte la garde `message_utilisateur`.
2. `Sheogorath/sheo_llm.build_anti_tic_consigne` et
   `shared/twitch/llm._build_anti_tic_consigne` deviennent des enveloppes qui delegent.
   Leurs tests existants doivent rester verts **sans etre modifies** : c'est eux qui
   prouvent que la promotion n'a rien perdu.
3. Cabler les 4 bots la ou ils batissent deja `anti_repeat_prompt`
   (`bot_alfred.py:1672`, `bot_sugar.py:909`, `bot_johnny.py:985`, `bot_maiq.py:1358`).

⚠️ **Ne JAMAIS interdire le sujet de la conversation.** La garde `message_utilisateur`
existe pour ca : si le mortel parle de cornichons, le bot doit pouvoir repondre
cornichons. On interdit la rengaine, jamais le sujet. Un cablage qui oublie de passer le
message de l'utilisateur rend le filet nuisible, pas seulement inoperant.

⚠️ Un tic vit **au milieu** de la replique, pas seulement a l'amorce ou a la cloture.

---

## Lot 2 — le carnet de lecons (le vrai Phase 3)

Nouveau module **`shared/repartee_lessons.py`**, quatre pieces.

### 1. `detect_defeat_signal(message_utilisateur) -> str | None`

Rend le motif reconnu, ou `None`. Deux familles seulement :
- un **verdict sur la joute** (« ta repartie est claquee », « t'es a court », « tu te
  repetes ») ;
- une **declaration de victoire** adressee au bot (« je t'ai humilie », « t'as perdu »,
  « tu t'es couche »).

⚠️ **L'insulte ordinaire n'est PAS un signal.** Le salon insulte les bots toute la
journee — c'est meme un critere d'admission des modeles. Un detecteur qui prend « t'es
nul » pour une defaite declencherait a chaque echange.

⚠️ **Deuxieme condition, obligatoire : le bot doit avoir parle juste avant.** Sans elle,
un verdict lance a un autre humain declenche la reflexion. La derniere replique du bot est
dans `response_memory.get_recent(guild_id)` — si elle est vide, il n'y a pas de defaite,
il y a une conversation entre mortels.

### 2. `ReparteeLessons(bot_id)` — le carnet

- Fichier **`data/repartee_lessons_<bot>.json`**. ⚠️ Sous `DATA_DIR`, jamais dans `<Bot>/` :
  l'hote et les 6 conteneurs partagent `data/`, et un test de garde doit lire la valeur de
  **`conftest.py`**, pas la recalculer.
- Cap **15** lecons, dedup, la plus ancienne evincee. Ecriture **atomique** (`.tmp` puis
  `os.replace`).
- **Cloisonne par bot** : un carnet n'est JAMAIS lu par un autre bot.
- ⚠️ Une `PermissionError` ne doit pas tuer le `on_message` : un bot muet a deja coute une
  soiree (M'aiq, `save_data()` sur un fichier `root:root`).

### 3. `reflect_on_defeat(...)` — la reflexion, hors du chemin de la reponse

- **Un** appel LLM, via **`appel_hors_cascade`**. ⚠️ Jamais le SDK nu : un verrou AST
  l'interdit, et les 19 appels nus de la semaine derniere ont montre pourquoi (aucune
  quarantaine, aucune ligne en base, la meme cle qui retape dans le mur).
- Lance en `asyncio.create_task` : **zero latence ajoutee** a la replique en cours.
- Sortie attendue : **UNE** regle de comportement, ≤ 160 caracteres, a la 2e personne,
  sans citer de vanne, sans nommer l'utilisateur.

**Assainissement — la lecon est du texte inspire par un inconnu.** Une lecon est **jetee**
(refus journalise) si elle porte une consigne d'identite (« tu es », « oublie »,
« ignore »), une mention `<@`, une URL, ou depasse la borne. Sans ce filtre, n'importe qui
reecrit la persona d'un bot en se declarant vainqueur trois fois de suite.

**Debit borne** : cooldown **5 min par salon et par bot**, plafond **6 reflexions par jour
et par bot**. Au-dela → journal, pas de reflexion.

### 4. `format_for_prompt()` — la reinjection

Un bloc `[CE QUE TU AS APPRIS]` ajoute au `system_instruction`, juste apres l'anti-tic.

⚠️ **Un bot ne parle JAMAIS de sa mecanique.** Il ne dit pas « j'ai retenu une lecon », il
ne cite pas son carnet, il n'annonce pas qu'il progresse. Ce qui explique le systeme va
dans le **journal**. Le prompt doit le dire, et un test doit l'exiger.

**Interrupteur** : cle `repartee_lessons_enabled` dans `data/bot_features.json`, defaut
`true` pour les 5. ⚠️ Le refus du a l'interrupteur se journalise ; il ne se dit pas au
salon.

---

## Ordre d'execution

1. Lot 1 (les 4 bots) — independant, verifiable seul, et il rend Lot 2 plus lisible.
2. `shared/repartee_lessons.py` + ses tests, **sans aucun cablage**.
3. **Sheo seul**, cable de bout en bout — c'est son clash de reference qui a lance l'idee.
4. Replication mecanique aux 4 autres.

---

## Les pieges — chacun a deja mordu dans ce depot

- **Vendoring, DEUX listes.** `anti_tic.py` et `repartee_lessons.py` doivent entrer dans
  `tools/vendor_core.py` **ET** `tools/sonde_core_drift.py` : absent de la seconde =
  vendorise **sans filet**. `tests/test_transcript.py` exige deja leur egalite. Puis
  `python tools/vendor_core.py` et `python tools/sonde_core_drift.py`.
- **Independance stricte.** Les bots importent `core.<module>`, jamais `shared.` ; import
  en `try/except ImportError` avec repli **no-op**, et un bot doit demarrer sans `shared/`.
  ⚠️ Les imports **indentes** comptent aussi.
- **Un import ajoute n'est pas un cablage.** Un test qui cherche le NOM d'un helper passe
  au vert sur un simple import : exiger l'import, **l'appel avec ses arguments**, ET
  l'absence du code remplace.
- **Aucun tirage aleatoire dans les tests** — 4 fois deja dans ce depot.
- **`pyflakes` AVANT `pytest`**, et **ne jamais supprimer par motif textuel**.
- **Un seul `pytest` a la fois** : `data/` et le port 8599 sont partages.

---

## Ce qui prouve que c'est fait

**Mecaniquement** (tests neufs) :
- `detect_defeat_signal` : le vrai cas documente passe, et **10 insultes ordinaires du
  salon ne declenchent pas** — c'est ce compte-la qui vaut preuve, pas le cas positif ;
- le signal ne declenche pas quand le bot n'a pas parle juste avant ;
- carnet : cap 15, dedup, ecriture atomique, chemin **sous la valeur de `conftest`** ;
- assainissement : 6 lecons empoisonnees refusees, refus journalise ;
- **AST** : `reflect_on_defeat` n'appelle aucun SDK nu et passe par `appel_hors_cascade` ;
- **AST** : les 5 bots importent ET APPELLENT, et le code remplace a disparu ;
- les tests anti-tic existants restent verts **sans modification** ;
- `tests/test_independance_bots.py` vert, sonde de derive *No drift detected*, **CI verte**.

**En salon** (ce qu'aucun test ne voit) — mode test arme, puis **desarme a la fin** :
- rejouer un clash sur Sheo : journal `defaite detectee`, puis la lecon retenue ;
- ⚠️ la replique **suivante** ne doit ni citer la lecon, ni annoncer qu'il a appris ;
- relancer le meme clash sous les 5 min : le cooldown journalise, aucun 2e appel.

⚠️ **Ne jamais dire « c'est bon » avant que la CI soit verte** — le local ment sur tout ce
qui depend de l'environnement.

---

## Ce qui n'est PAS dans ce chantier

- Le routage et les cascades : `TEXT == REPARTEE`, c'est verifie, on n'y touche pas.
- Twitch : **gele**. L'annexe ci-dessous garde le mode d'emploi intact pour le jour ou.
- La migration mempalace (355 tiroirs dans des wings par-bot) : hors depot, non urgente.

---

# ANNEXE — protocole live Twitch, GELE le 2026-09-08

⚠️ **Ne pas proposer ces deux sessions.** Decision user du 08/09 : « on laisse ca de cote,
je compte pas streamer ». Conserve mot pour mot, a rouvrir seulement sur sa demande.

## Session 3 — EventSub de Sheo (20 min, une seule fois)

Le seul point qui demande une manip technique. EventSub (points de chaine, subs, hype,
sondages, follows) exige le token du **PROPRIETAIRE de la chaine**, pas celui du bot.

    python twitch_authorize.py --bot sheogorath_broadcaster ^
        --client-id <CLIENT_ID_SHEO> --client-secret <CLIENT_SECRET_SHEO>

⚠️ **Se connecter avec le compte STREAMER**, pas avec le compte du bot. Depuis le 08/09
(`86710cb`), le helper le DIT lui-meme quand le nom finit par `_broadcaster`, et il
refuse de proposer le token du streamer pour `TWITCH_OAUTH_TOKEN` — l'y coller aurait
fait parler le bot sous l'identite du streamer. Le fichier ecrit
(`data/twitch_chat_auth_sheogorath_broadcaster.json`) est repere tout seul.
Puis cocher `chat.eventsub` pour Sheo (dashboard, ou `data/twitch_config.json` : il est a
`false`), et redemarrer Sheo.

### Les deux moities, disjointes — et c'est la premiere qui rate

**1. Le token (le vrai risque) — se verifie SANS declencher quoi que ce soit.**
Redemarrer Sheo, puis :

    docker logs --since 3m bot-sheogorath 2>&1 | grep EVENTSUB

Attendu : `🔌 Connecte au WebSocket`, `🔑 Session bienvenue recue`, puis **7** lignes
`✅ Abonne a channel.…`. Un `⚠️ Echec abonnement … (code 403)` dit qu'on a pris le token
du BOT et non celui du streamer. C'est l'echec probable, et il se lit en 2 minutes.

**2. La reaction — la partie qu'on ne peut presque jamais provoquer.**

⚠️ Une recompense de points exige d'etre **Affilie**, d'avoir cree une recompense
**PERSONNALISEE** (les recompenses integrees de Twitch — « Mettre en avant mon message »,
« Debloquer un emote » — ne declenchent **jamais**
`channel.channel_points_custom_reward_redemption.add`), et un **second compte** pour la
depenser : le streamer n'accumule pas de points sur sa propre chaine.

Trois voies, de la plus simple a la plus lourde :

- **Un follow depuis un second compte.** Aucun Affilie, aucun point, marche hors live,
  et c'est le MEME chemin de code qu'une recompense. Unfollow/refollow pour rejouer.
- **Un sondage**, la seule chose declenchable seul (Creator Dashboard → Stream Manager →
  Quick Actions). Affilie requis.
- **Le serveur factice de la CLI Twitch** (gratuit, officiel) :

        twitch event websocket start-server
        twitch event trigger channel.follow --transport=websocket

  Le bot y est pointe par `TWITCH_EVENTSUB_WS_URL` (ajoutee le 2026-09-08 ; sans elle,
  l'endpoint reste celui de Twitch). ⚠️ **Depuis un conteneur, `127.0.0.1` designe le
  conteneur** : viser `ws://host.docker.internal:8080/ws`.
  ⚠️ Le serveur factice accepte n'importe quel abonnement : il ne prouve **pas** le
  token. Il ne remplace pas le point 1, il complete le point 2.
  ⚠️ La substitution s'ANNONCE dans le journal (`🧪 endpoint SUBSTITUE`) : oubliee, elle
  rendrait EventSub definitivement muet sans une erreur.

**Preuve, dans les deux cas** : `🔔 Evenement recu: channel.…`, puis Sheo parle dans le
chat. Pour une recompense : `🎁 Custom reward redeemed: <titre> par <pseudo>`.

⚠️ Cooldown de **5 s par type d'evenement** : deux essais rapproches du meme type, le
second est ignore (`⏳ … (cooldown)`). Ce n'est pas une panne.

⚠️ `reward_map` est vide : **n'importe quel** titre de recompense declenche la reaction
LLM generique. Pas besoin d'un nom precis.

---

## Session 4 — le vrai live (pendant un stream)

Rien ici ne peut se simuler.

1. **Annonces de live** — demarrer le stream, attendre 90 s (`poll_interval_seconds`).
   Les bots annoncent sur Discord. **Anti-doublon** : une seule annonce, pas six.
2. **Ton adaptatif Twitch de Sugar** — lui parler dans le chat Twitch. Le ton doit
   differer de Discord.
3. **Silence sauf si nomme** — parler dans le chat **sans** nommer un bot : les 3 bots
   presents se taisent.
4. **Pont anti-doublon Discord↔Twitch** — poser la meme question sur les deux : la 2e
   reponse ne doit pas recopier la 1re.
5. **Ecoute STT** — sur le PC du micro, **d'abord** le diagnostic isole :

        python check_stt.py --model small --device cpu --seconds 6

   S'il transcrit, le plus dur est fait. Ensuite le hub : `python run_stream_listener.py`.
   ⚠️ `Hub d'ecoute injoignable (port 8765)` au demarrage de Sheo est **nominal** tant que
   le hub ne tourne pas. Parler au micro → **un seul** bot repond.

---
