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
Slash — `/help` `/ping` `/stats` `/reputation` `/leaderboard` `/quests` `/birthday` :
⚠️ **sur 5 bots, pas 6**. Malena n'appelle jamais `setup_slash_commands` et ne l'a
**jamais** appele (`git log -S` sur tout l'historique : aucun resultat). Elle a pourtant
`setup_games` et les anniversaires cables. Ne pas chercher un slash chez elle pendant le
test : il n'y en a pas.

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

- **`report_error` n'est appele que pour Gemini** (`shared/llm_cascade.py:359`) : Groq et
  NVIDIA ne mettent jamais une cle en quarantaine sur un 429. C'est du code, pas un test
  live, et c'est le dernier vrai point ouvert.
- **Malena n'a aucune commande slash** — trouve en redigeant ce plan. Les 5 autres
  appellent `setup_slash_commands` ; elle ne l'importe meme pas, et ne l'a jamais fait.
  Correctif = 2 lignes, calquees sur `Alfred/bot_alfred.py:91` et `:425`.
- **Bruit d'arret** : `[MISSED CHECK] Erreur canal idee: Session is closed` chez Malena a
  chaque `restart` — le graceful shutdown n'annule pas les boucles en vol. Benin.
- **Phase 3 repartie** : a re-specifier, son contexte a peri (elle visait la cascade
  REPARTEE quand Grok la pilotait). **Migration mempalace** : hors depot.

⚠️ **Ne jamais lancer deux `pytest` en parallele** : ils partagent `data/` et le port 8599.
