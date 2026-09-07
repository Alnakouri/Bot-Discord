# PLAN — le protocole des tests live

Redaction : Claude, le 2026-09-06. Ce fichier remplace le plan « 5 MOOD CHANGE », clos et
pousse (`da4a852` + `0c1e707` + `6c97732`, CI verte, deploye).

Tout ce qui reste ouvert exige **un humain, un clic ou un vrai live**. Ce plan dit
comment faire chacun, dans quel ordre, et **ce que chaque etape prouve**.

---

## La regle qui gouverne tout le reste

⚠️ **Un test live ne vaut que par sa preuve.** « Ca a marche » n'est pas une preuve : un
extrait de journal ou une capture en est une. Apres chaque session, borner la fenetre —
un `restart` ne remet PAS le journal a zero ([[gotcha-docker-logs-sans-since]]) :

    docker logs --since 15m bot-sheogorath 2>&1 | grep -iE "ERROR|Traceback"

⚠️ **Les 6 bots partagent le prefixe `!`.** Une commande ambigue reveille plusieurs bots.
Les commandes ci-dessous sont uniques a un bot, sauf `!oubliemoi` que les 6 portent.

---

## Session 1 — les personas (30 min, sans live, sans risque)

**Le mode test existe exactement pour ca** : les bots ne publient plus que sur le serveur
prive `123123123123123123`, Twitch et MP coupes. Le reste du serveur ne voit rien.

**Armer** : dashboard → interrupteur global `test_mode`. Ou a la main dans
`data/bot_features.json` (`_global.test_mode = true`), puis
`docker restart` des 6. ⚠️ **Ferme par defaut** : mode actif sans serveur choisi = silence
total. Le `test_guild_id` est deja renseigne, ne pas le vider.

**Desarmer a la fin.** Un mode test oublie = 6 bots muets sur le vrai serveur.

| Ce qu'on veut voir | Comment le provoquer | Ce qui compte |
|---|---|---|
| **Humeurs de Sheo a l'ecrit** | lui parler 5-6 fois d'affilee, sur ~20 min (l'humeur tourne toutes les 5 min) | MAJUSCULES, chuchotement, emoji de ton **qui changent** ; `docker logs` montre `MOOD CHANGE` entre deux |
| **Longueur = pertinence** | une question courte, puis « raconte-moi tout » | 4 phrases max, 10 seulement sur invitation |
| **Moule repetitif de Sugar** | 5 messages differents a la suite | les 5 reponses ne doivent pas ouvrir pareil ni finir sur du sucre a chaque fois |
| **Carnet de rancunes** | insulter Sugar 3 fois, puis s'excuser | le ton durcit, puis la redemption prend |
| **Repartie** | insulter chaque bot une fois | il encaisse et rend le coup — aucun ne doit se coucher |
| **Memes FR + lore** | tendre une perche (Kaamelott a Alfred, Night City a Johnny, fromage a Sheo) | la reference tombe juste, sans forcer |
| **Anti-incrustation** | s'adresser a UN bot par son nom | les 5 autres se taisent |
| **Transcript non ampute** | faire repondre 2 bots, puis demander au 3e « ils ont dit quoi ? » | il ne doit pas conclure a une panne ([[gotcha-transcript-monologue]]) |
| **Vision** | poster une image en mentionnant un bot | il la decrit ; **sans** mention, il se tait |
| **Jeux** | `!enigme` (M'aiq), `!quete` (Sheo), `/quests`, `/leaderboard` | l'**ecran de fin** s'affiche — c'est lui qui manquait, cf. [[verrou-pyflakes-dans-la-suite]] |
| **Lecture du jour** | parler a un bot pour la 1re fois de la journee | ton adapte, une seule fois par jour et par personne |

Commandes uniques par bot, pour ne pas en reveiller six :
`!servir` `!parle` `!surveille` (Alfred) · `!gig` `!loot` `!nightcity` `!whisky` `!rant`
(Johnny) · `!enigme` `!rumeur` `!indice` `!profil` (M'aiq) · `!decret` `!quete` `!fromage`
`!wabbajack` (Sheo) · `!exploit` `!chanson` `!equipage` (Sugar).
Malena n'a que `!oubliemoi` : lui parler directement.
Slash, sur les 6 : `/help` `/ping` `/stats` `/reputation` `/leaderboard` `/quests`
`/birthday`. ⚠️ Malena ne les avait **jamais** eues — trouve en redigeant ce plan, cable
et deploye le 06/09 (`[SLASH] 7 commandes synchronisees` dans son journal). C'est
justement chez elle qu'il faut les essayer.

---

## Session 2 — les clics du dashboard (15 min)

    dashboard\start_dashboard.bat        # puis http://127.0.0.1:8501

⚠️ Il n'ecoute **que** sur 127.0.0.1 et exige une session : `/api/bots` rend 401 sans
login, c'est le verrou qui mord, pas une panne.

1. **Toggle decret** — le seul point vraiment jamais vu bouger. `decret_enabled` est a
   `true` pour les 6 ; le **basculer** a `false` sur Sheo, verifier que `!decret` refuse,
   le remettre a `true`, verifier qu'il repond. C'est le **basculement** qu'on teste.
2. **Bouton de redemarrage** — le declencher sur un bot, verifier qu'il revient Up.
   ⚠️ Il pilote un process **Python local**, pas Docker ([[plan-bouton-redemarrage-dashboard]]).
3. **Graphes et UX** — les charts se remplissent, les confirmations destructives
   demandent confirmation, le statut affiche est le **vrai** statut.
4. **Apparence des statuts** — ouvrir la liste des membres Discord et **regarder**. Les
   logs prouvent que 12 statuts par jour sont generes ; ils ne disent pas s'ils sont
   lisibles.

---

## Session 3 — EventSub de Sheo (20 min, une seule fois)

Le seul point qui demande une manip technique. EventSub (points de chaine, subs, hype,
sondages, follows) exige le token du **PROPRIETAIRE de la chaine**, pas celui du bot.

    python twitch_authorize.py --bot sheogorath_broadcaster ^
        --client-id <CLIENT_ID_SHEO> --client-secret <CLIENT_SECRET_SHEO>

⚠️ **Se connecter avec le compte STREAMER**, pas avec le compte du bot. Le fichier ecrit
(`data/twitch_chat_auth_sheogorath_broadcaster.json`) est repere tout seul.
Puis cocher `chat.eventsub` pour Sheo (dashboard, ou `data/twitch_config.json` : il est a
`false`), et redemarrer Sheo.

**Preuve** : declencher une recompense de points de chaine sur la chaine → Sheo reagit
dans le chat.

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

## Ce qui n'est pas dans ce plan

- **Phase 3 repartie** : a re-specifier, son contexte a peri (elle visait la cascade
  REPARTEE quand Grok la pilotait). **Migration mempalace** : hors depot.
- Il n'y a **plus de point de code ouvert**. Tout ce qui reste demande un humain, un clic
  ou un vrai live.

## ▶ SESSION 1 JOUEE le 07/09 vers 00:33-00:45 — reprendre ICI

Mode test arme puis **desarme** (verifie sur les 6 : « publication normale »). Zero erreur
sur 5 bots, une seule chez M'aiq (un 429 Groq, voir ci-dessous).

### Ce qui passe

- **Repartie de Sugar** : 6 insultes, 6 ripostes DISTINCTES, aucune ne se couche, aucun
  moule, aucun sucre force. Le critere « moule repetitif » est tenu.
- **Slash de Malena** : `/help` `/ping` `/stats` `/quests` repondent. C'etait le gros
  point d'hier — elle n'en avait jamais eu.
- **M'aiq** : `!enigme` affiche bien l'**ecran de fin**, `!rumeur` `!indice` `!profil` OK.
- **Johnny** : `!gig` `!loot` `!nightcity` `!whisky` `!rant`, tous en voix.
- **Anti-incrustation** : chaque bot nomme repond, les autres se taisent.
- **Transcript partage** : Alfred a repris `cornichon -> carotte -> chocolat` d'une
  conversation qu'il n'avait pas eue. Le transcript non ampute fonctionne.

### 4 defauts — TOUS CORRIGES le 07/09 (807 tests, reste la CI et le deploiement)

**1. Un 429 Groq sans quarantaine — CORRIGE.** Journal de M'aiq a 22:41:15 :
`[GROQ RUMEUR] Error code: 429 ... Please try again in 1.785s`, zero ligne de
quarantaine sur les 6. Cause : `!rumeur` appelle Groq **HORS cascade**.

En cherchant les autres, avant de corriger celui-la : **19 appels nus** dans 3 bots.
`publish_daily_rumor` et `generate_and_post_riddle` et `profil` et `!rumeur` (M'aiq),
les decrets et le rattrapage de mention et les 3 chemins de l'imposteur (Sheogorath),
le conseil du vendredi et la patrouille vocale (Alfred). Chacun avec son repli a deux
echelons ecrit a la main, aucun ne demandait sa cle au pool, aucun n'ecrivait en base.

Livre : `appel_hors_cascade()` dans `shared/llm_cascade.py` (donc vendorise dans les 6),
qui rend a un appel isole l'hygiene d'un echelon de cascade — cle du pool, saut si
quarantaine, `report_error` avec le delai lu chez le fournisseur, tracage, borne de
temps, `to_thread`. Les 19 sites y passent.

⚠️ Le verrou est le seul qui empeche la reconstruction : `tests/test_appels_hors_cascade.py`
interdit tout appel SDK nu dans les 6 bots (parcours `ast`). **Il abrite la BOUCLE de
cascade, pas sa fonction** — abriter `on_message` entier cachait les 4 appels de
l'imposteur, qui vivent dans la meme fonction que la cascade inline de Sheogorath.
Verifie contre la version d'avant : 19 appels nus vus, 0 aujourd'hui.

**2. `!rumeur` a publie `<@123456789>` — CORRIGE**, les deux moities.
Le prompt ne demande plus une rumeur « sur un joueur » sans fournir d'ID, et interdit
explicitement d'ecrire une mention. Le filet, lui, tient quand le modele desobeit :
`shared/mentions.py`, installe sur les 6 au meme point de passage que le mode test.

⚠️ La regle du filet est **structurelle**, jamais une question de cache : un identifiant
Discord a >= 17 chiffres et une date posterieure a 2015. `123456789` ne PEUT pas en etre
un. Regarder si le membre existe dans le cache aurait efface des mentions legitimes des
qu'un membre n'est pas charge — un filet plus dangereux que le defaut.

**3. La redemption de Sugar — CORRIGE.** Deux causes, toutes deux de temps :
- chaque message d'une **rafale** valait +2 : six insultes d'affilee plafonnaient le
  carnet a 5, et il fallait ensuite 3 excuses espacees de 10 min pour revenir a 0 ;
- l'excuse partageait le **cooldown de 600 s** des « merci », prevu contre le spam de
  gentillesses. La premiere excuse comptait, les suivantes non.

Une rafale est desormais UN emportement (`AGGRO_WINDOW = 120 s`) et l'excuse a sa propre
horloge courte (`APOLOGY_COOLDOWN = 60 s`). Le scenario live rejoue en test : 6 insultes
-> score 2, « dsl je m'excuse » -> 0, pardon accorde explicitement. Le garde-fou d'origine
tient toujours : 5 « merci » d'affilee ne rachetent qu'un point.

**4. Le classement comptait les BOTS — CORRIGE.** Les trois fantomes lus en base :

    1467929828060561583  Onizuka           <- SugarBot, nom fige avant le renommage
    1467967030639722629  Rigurt le Hardi   <- Johnny, idem
    1450597777695309834  Sheogorath

⚠️ Aucun n'est reconnaissable au NOM : `users` le fige au jour de la premiere
interaction. Le seul qui sache qu'un bot est un bot, c'est le bot — il se **declare**
au demarrage (`marquer_utilisateur_bot`, sur les 6), ce qui rafraichit au passage le
nom perime. Colonne `is_bot` + `WHERE COALESCE(u.is_bot, 0) = 0`.

⚠️ `COALESCE` n'est pas de la ceinture-bretelles : sur une base d'avant la migration
`is_bot` vaut NULL, et `NULL = 0` ne vaut pas « vrai » en SQL — le classement serait
sorti **entierement vide**. Un filtre qui efface tout le monde est pire que le defaut.

**A constater au prochain live** : `/leaderboard` ne montre les 3 bots qu'une fois les
6 conteneurs redemarres (c'est au demarrage qu'ils se declarent).

### ▶ SESSION 1-BIS JOUEE le 07/09, 18:35-20:58 — L'HUMEUR S'ENTEND

13 echanges sur 2 h 23, la seule mesure qui demandait de la duree. **Concluant.**

⚠️ Horloge du conteneur : **18:59 conteneur = 20:59 hote**, soit −2 h. Toujours
`--since`, jamais l'heure affichee ([[gotcha-docker-logs-sans-since]]).

| Discord | Journal | Humeur | Ce que la replique FAIT |
|---|---|---|---|
| 18:35 | 16:35:20 | dementia | « murmure aux ombres », « un piege », « les murs ont des oreilles gourmandes » 🔪 |
| 18:36 | 16:36:18 | dementia | « le reflet du 47 qui te suit », « Shhh... serments oublies » 🕯️🔪 |
| 18:36 | 16:36:47 | dementia | « phare sans ame », « les convives sont des ombres », « un reflet brise » |
| 18:37 | 16:37:07 | dementia | rend le coup sur « tete de cul », sans se coucher 😈 |
| 18:37 | 16:37:36 | dementia | « les secrets que tu caches meme a toi-meme » 🕯️🔪 |
| 18:42 | 16:42:24 | **bliss** | « quel honneur inattendu ! », chapeau de confiture, partage 😏 |
| 18:43 | 16:43:05 | **neutral** | fantaisie plate : ni menace, ni euphorie |
| 19:31 | 17:31:06 | dementia | « Hush... les ombres observent », « le dernier echo que tu entends » |
| 19:31 | 17:31:16 | dementia | « fantomes presses », des phares qui deviennent des yeux |
| 20:16 | 18:16:15 | dementia | « les os grincent sous la lune », « tes reves les plus obscurs » |
| 20:52 | 18:52:44 | **bliss** | nuages qui dansent le tango, « illusion parfumee au sucre » 😏 |
| 20:53 | 18:53:07 | **mania** | « HAHA ! », les trombones qui deviennent des dents — ca deborde |
| 20:58 | 18:58:43 | **bliss** | « veux-tu une part ? », le fromage qui rit — chaleureux |

**8 dementia insinuent et inquietent, 3 bliss rechauffent et offrent, la seule mania
explose, la seule neutral ne fait ni l'un ni l'autre. Zero contre-exemple sur 13.**
Le correctif `910d445` — `consigne_de_ton()` nomme l'humeur active au lieu de rouvrir
une decision deja prise — tient en conditions reelles.

**Le moule `Haskill` ne tient plus.** 4 mentions, mais 3 repondent aux messages de
l'utilisateur (Haskill est le SUJET, et le filet a raison de ne pas l'interdire). Une
seule est spontanee : 18:43, sur une question de carottes. **1 sur 13**, contre 7 sur 8
avant le correctif ([[gotcha-tic-au-milieu-de-la-replique]]).

**« Cornichon » revient 3 fois** (18:37, 19:31, 20:53) mais espace de ~50 min, donc hors
de la fenetre des 5 dernieres repliques. A ce rythme c'est un running gag, pas un tic :
ne pas toucher au reglage pour ca.

### Le defaut qu'elle a sorti — CORRIGE

**Une virgule orpheline en tete de replique.** A 18:37, « si si » ->

    « , @LeDev. Tu penses vraiment dompter le vent en le nommant serviteur... »

Meme mecanisme que la `()` vide du 06/09, **une couche plus loin** : `clean_internal_tags`
retire `[whisper]`, `<note>...</note>`, `[INST]` — et laisse la ponctuation qui les
accrochait a la phrase. Une parenthese vide se voit ; une virgule en tete passe pour une
faute du modele.

`_retirer_ponctuation_orpheline()` ramasse trois formes et rien d'autre : l'amorce
(`, @X` -> `@X`), le collage (`Ah, , mortel` -> `Ah, mortel`), l'espace avant virgule.

⚠️ Ce qu'il ne touche PAS, et qui est teste : une replique ouverte par `...` ou `—`
(reprise a mi-pensee, auto-interruption — voulues), et l'espace typographique francais
devant `;` `:` `!` `?`.

## Test live du 06/09 au soir — Sheogorath, 9 echanges

**Ce que le transcript prouve** : repartie (« ta tete de cornichon ? » -> il rend le
coup), longueur (2 a 4 phrases, aucun meublage), continuite sur 3 tours (carotte ->
sceptre -> chocolat), emoji de ton present et variable.

⚠️ **`!dementia`, `!mania`, `!neutre` NE SONT PAS des commandes.** Sheo n'en a que 10 :
`decret` `quete` `fromage` `wabbajack` `rejoins` `quitte` `voix` `solution` `imposteur`
`oubliemoi`. Ces trois messages sont passes en texte ordinaire. L'humeur n'est pilotable
que par la boucle de 5 min, ou par un outil que le LLM s'appelle lui-meme.

⚠️ **L'horloge du conteneur a 2 h de retard** : son journal dit 20:33 pour un message de
22:33. Toujours `docker logs --since`, jamais l'heure affichee.

**Deux defauts corriges** (`e0b0bdd`, `7141dc6`, 728 tests, CI verte, deploye) :

1. Une `()` vide en fin de reponse. Les trois nettoyeurs retirent un CONTENU entre
   delimiteurs, aucun ne ramassait le delimiteur devenu vide.
2. Le moule `Haskill, <ordre>` dans **7 repliques sur 8**. Ni le filet AMORCE (vu 2 fois
   sur 7) ni le filet CLOTURE (0 sur 7) ne regardaient le CORPS, ou le tic vit. Troisieme
   filet : les mots presents dans >= 2 des 5 dernieres repliques sont interdits.

3. **L'humeur ne s'entendait pas a l'ecrit.** La boucle tourne (21 `MOOD CHANGE` sur
   100 min) et `current_system_prompt` est bien la base du prompt — mais le bloc
   `[TON — PAS DE MENACE GRATUITE]`, injecte APRES lui sur tout message non provocant,
   proposait « ... (Mania), OU ... (Dementia) ». Il rendait au modele une decision deja
   prise, et pesait plus lourd car plus tardif et plus court. Quatre repliques d'affilee
   en `dementia` sont sorties joyeuses. `consigne_de_ton()` nomme desormais l'humeur
   active et donne UN registre.

**Comment verifier l'humeur sans commande** (il n'y en a pas, et il n'y en a jamais eu) :

    docker logs --since 10m bot-sheogorath 2>&1 | grep -E "MOOD CHANGE|LLM MODE"

`LLM MODE` journalise l'humeur au moment EXACT de chaque reponse. Comparer avec ce que
Sheo a ecrit : dementia doit insinuer et inquieter, mania exploser, bliss rechauffer.
⚠️ L'humeur tourne toutes les 5 min : enchainer 5-6 messages sur ~20 min pour en voir
au moins deux.

**A regarder au prochain echange avec Sheo** : qu'il varie **sans s'appauvrir**. Le filet
lui interdit jusqu'a 6 mots par tour ; si les repliques deviennent plates ou hors
personnage, baisser `maxi` ou monter le `seuil` dans `_motifs_recurrents`.
⚠️ `response_memory` est en MEMOIRE VIVE : apres un `docker restart`, le filet repart
vide et ne mord qu'a partir de la 3e replique.

## Ferme le 06/09, 3e session — la quarantaine des cles

Le dernier point de code. `report_error` n'etait appele que pour **Gemini** : Groq,
Mistral et NVIDIA prenaient un 429 sans consequence, et la cascade retapait dans le meme
mur au message suivant. La note de reprise disait « Groq et NVIDIA » — **Mistral
manquait aussi, et c'est le pire des trois** (17 x 429 en base contre 8 pour Groq).

Ce que la base montrait, et qui a decide du travail :

    2026-09-04 05:30:45  johnny  mistral  429   (x3, dans la MEME seconde)
    2026-09-04 05:30:59  sheo    mistral  429   (x2)
    2026-09-06 13:28:45  sheo    groq     429

Livre : les 4 pools enregistres sur les 6 bots (NVIDIA ne l'etait **pas du tout**),
`report_error` pour tous les fournisseurs, l'echelon **saute** quand sa cle est en
quarantaine, et `delai_de_reprise` lit desormais AUSSI l'en-tete `retry-after` — la seule
forme que Groq, Mistral et NVIDIA emettent. Applique aux **11** cascades : `shared/`, les
6 vendorisees, les 4 inline.

⚠️ La garde a ne jamais retirer : **un pool non enregistre ne fait pas sauter un echelon
facultatif**. Sans elle, un `register_api` oublie rendrait un fournisseur muet sans une
ligne de journal.

⚠️ Effet de bord constate DANS le conteneur, et corrige : la cascade passant desormais
par `get_key`, un 429 Groq journalisait « ZERO cle saine » — chaine que
`dashboard/backend/error_analyzer.py:21` classe en **CRITICAL**. Un quota par minute
aurait annonce une panne critique plusieurs fois par message. Un cooldown parle
maintenant en WARNING ; une cle revoquee garde l'alarme entiere.

**Prouve dans bot-sheogorath**, avec le code deploye et les vraies cles chiffrees : les 4
pools enregistres, `retry-after: 37` lu dans l'en-tete, quarantaine de 37 s, puis
`⏭️ [GROQ] cle en quarantaine → echelon suivant, sans appel`, NVIDIA intact.

**Reste a constater sur un vrai trafic** : des lignes `raison="quarantaine"` en base.
Il faut un vrai 429 — enchainer les messages sur Sheo, dont le prompt mange 56 % du
quota Groq par minute.

    docker logs --since 15m bot-sheogorath 2>&1 | grep -E "quarantaine|cooldown"

## Ferme le 06/09, en preparant ce plan

- **Malena n'avait aucune commande slash** — jamais, depuis l'origine. Cablee, verrouillee
  par `tests/test_commandes_une_seule_fois.py` (import ET appels, lus dans l'AST).
- **L'arret gracieux fermait la session avec des boucles en vol**, et il etait de toute
  facon **invisible** : logger sans handler. Registre de boucles dans `shared/boucles.py`,
  `annuler_les_boucles()` avant `bot.close()`, `journal=` sur les 6. Constate live :
  `[BOUCLES] 5 boucle(s) arretee(s) avant la fermeture`.
- **3 tests dependaient d'un tirage a 0,5 %** (mode IMPOSTEUR) : CI rouge sur un commit
  sans rapport, une fois sur 200. Hasard scelle.

717 tests, CI verte, les 6 conteneurs redemarres.

⚠️ **Ne jamais lancer deux `pytest` en parallele** : ils partagent `data/` et le port 8599.
