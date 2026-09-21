# -*- coding: utf-8 -*-
import re
import time
import random
import collections
import asyncio
from datetime import datetime
from shared.twitch.sanitize import strip_stage_directions, send_chat_safe
from shared.twitch.llm import ANTI_INJECTION_GUARD

# Tout ce qui ressemble à une adresse dans la phrase écrite par le modèle. Le lien
# officiel est accolé par le code : celui que le modèle invente est au mieux inutile,
# au pire faux — et personne ne verifie une URL avant de cliquer.
_RESSEMBLE_A_UN_LIEN = re.compile(
    r"(?:https?://\S+|www\.\S+|\b\S+\.(?:gg|com|fr|net|io|tv|org)(?:/\S*)?)",
    re.IGNORECASE,
)


# ⚠️ Le lieu d'ou l'on ECRIT n'a rien a faire dans une invitation.
#
# Signale par Ahmed le 2026-09-19, sur une phrase de Sugar postee dans le chat d'un
# streamer : « Les piques volent bas par ici, mais notre coin secret a autrement plus de
# mordant. » Le bot DENIGRE le salon qui l'heberge pour vendre l'autre — sur une chaine
# qui n'est meme pas la sienne.
#
# La cause n'est pas la persona : c'est que la consigne interdit tout ce qui est CONCRET
# sur la destination (ni chiffre, ni salon, ni evenement, ni recompense) et demande quand
# meme de « promettre l'ambiance ». Il ne reste alors au modele rien de vrai a offrir, et
# la seule chose qu'il puisse observer est le chat devant lui : il vend par contraste.
# La consigne a donc ete reecrite pour lui rendre quelque chose de vrai a promettre (LUI,
# sa presence et ce qu'il y fera) — et ca, c'est mesurable et ca marche.
#
# ⚠️ Mais la consigne NE SUFFIT PAS pour le denigrement lui-meme : mesure du 19/09 sur
# deux tirages, 2/6 -> 1/6 puis 1/10 -> 3/10. Le verdict s'INVERSE d'une passe a l'autre,
# c'est du bruit ([[gotcha-plancher-de-bruit-du-harnais]]). Une regle de prompt ne protege
# que ce qu'un modele veut bien suivre : d'ou ce filet, qui lui ne depend d'aucun tirage.
#
# Rejette, ne repare pas — meme philosophie que l'adresse ci-dessous : le gabarit fixe est
# fade, et fade bat cassé. Motif evalue sur les 20 phrases des deux tirages : il attrape
# les 4 fautes reelles, 0 faux positif, 0 rate.
# ⚠️ « par ici » N'EST PAS dans ce motif, et c'est delibere : il designe aussi bien la
# DESTINATION (« Viens sucrer tes levres par ici ») que la source (« les piques volent bas
# par ici »). Le premier jet le rejetait, et la suite de tests l'a attrape aussitot sur sa
# propre phrase de reference. On ne garde donc que les tournures sans ambiguite : celles
# qui NOMMENT le salon hote, et celles qui le COMPARENT.
_NOMME_LA_SOURCE = re.compile(
    r"(?:"
    # Nommer le lieu d'ou l'on ecrit.
    r"\bce chat\b|\bdu chat\b|\ble chat\b|chat twitch|\btwitch\b"
    r"|\bce stream\b|\ble stream\b|en plein stream|\bce live\b|\ble live\b"
    r"|\bce salon-ci\b|\bce tchat\b"
    # Le comparer : « plus savoureux qu'ici », « autrement plus de mordant ».
    r"|\bqu['’ ]?ici\b|autrement plus|\bmieux qu|\bmeilleur qu"
    r")", re.IGNORECASE)


def _nettoyer_phrase_de_lien(texte: str | None) -> str | None:
    """Rend la phrase prête à recevoir l'URL, ou None si rien d'exploitable.

    ⚠️ Une phrase qui contient déjà une adresse est REJETÉE, pas réparée. Mesuré en
    écrivant ce filtre : découper l'URL laisse une phrase estropiée — « Rejoins le sucre
    sur mon caramel », « Rejoins-nous sur tout de suite ». La phrase est construite AUTOUR
    du lien ; lui retirer son complément la casse. Le gabarit fixe, lui, est simplement
    fade — et fade bat cassé. Même famille que
    [[gotcha-nettoyeur-laisse-ce-qui-rattachait]] : ce qu'un nettoyeur laisse derrière lui
    compte autant que ce qu'il enlève.
    """
    if not texte:
        return None
    phrase = " ".join(str(texte).split())
    phrase = strip_stage_directions(phrase)
    if _RESSEMBLE_A_UN_LIEN.search(phrase):
        return None
    # Voir le bloc au-dessus du motif : une invitation ne parle que de sa destination.
    if _NOMME_LA_SOURCE.search(phrase):
        return None
    phrase = " ".join(phrase.split()).strip().strip('"').strip("«»").strip()
    # Un modèle finit souvent sur « rejoins-nous ici : » en attendant l'adresse ; c'est
    # nous qui l'ajoutons, la ponctuation d'annonce n'a plus rien à annoncer.
    phrase = phrase.rstrip(" :;,-—–")
    if len(phrase) < 3:
        return None
    return _borner(phrase, 200)


def _borner(phrase: str, maxi: int) -> str:
    """Borne la phrase SANS couper un mot en deux.

    ⚠️ `phrase[:200]` coupait au caractere pres. Mesure du 2026-09-21 sur 32 generations
    de Johnny : ses phrases font 102 a 239 caracteres — l'instruction en demande 120 et
    ministral l'ignore — donc une invitation sur cinq partait sur Twitch tranchee au
    milieu d'un mot, juste avant l'URL. Meme famille que
    [[gotcha-nettoyeur-laisse-ce-qui-rattachait]] : ce qu'un nettoyeur laisse derriere lui
    compte autant que ce qu'il enleve.

    On coupe donc a la derniere fin de PHRASE qui tient dans la borne — la replique reste
    entiere, elle est juste plus courte. A defaut, au dernier espace, et on pose des points
    de suspension : la coupe est alors visible, ce qui vaut mieux qu'un mot tronque qui
    passe pour une faute de frappe du bot.
    """
    if len(phrase) <= maxi:
        return phrase
    # ⚠️ Le seuil est a maxi/3, pas a maxi/2 : une premiere phrase COMPLETE de 70
    # caracteres vaut mieux qu'une seconde tranchee a 199. On ne refuse une fin de phrase
    # que si elle laisserait un moignon.
    tete = phrase[:maxi]
    fin_de_phrase = max(tete.rfind(". "), tete.rfind("! "), tete.rfind("? "))
    if fin_de_phrase >= maxi // 3:
        return tete[:fin_de_phrase + 1].strip()
    # Les points de suspension comptent dans la borne : sans ca, la coupe la DEPASSE.
    tete = phrase[:maxi - 1]
    espace = tete.rfind(" ")
    if espace >= maxi // 3:
        return tete[:espace].rstrip(" ,;:—–-") + "…"
    return tete.rstrip(" ,;:—–-") + "…"


class DispatchMixin:
    async def _fetch_game_facts_block(self, chan: str, category: str):
        """Récupère un bloc de faits IGDB pour le jeu en cours sur `chan`.

        Réutilise des clients Helix/IGDB persistés sur le bot (token OAuth conservé
        entre les appels). Retourne (facts_block | None, no_facts_warning: bool).
        Toute erreur réseau → (None, True) : le bot nuance en personnage.
        """
        from shared.twitch.game_info import HelixClient, IGDBClient, get_game_facts, format_facts_block
        if getattr(self, "_helix_client", None) is None:
            self._helix_client = HelixClient(self.client_id, self.client_secret)
        if getattr(self, "_igdb_client", None) is None:
            self._igdb_client = IGDBClient(self.client_id, self.client_secret)
        try:
            game_name, _ = await self._helix_client.get_current_game(chan)
            if not game_name:
                return None, True
            facts = await get_game_facts(game_name, self.client_id, self.client_secret, igdb_client=self._igdb_client)
            if facts:
                return format_facts_block(facts, category), False
            return None, True
        except Exception as e:
            self.logger.error(f"❌ [TWITCH_CHAT:{self.bot_id}] Erreur recuperation faits jeu: {e}")
            return None, True

    async def _handle_privmsg(self, chan: str, author: str, text: str, tags: dict, ws):
        # 1. Traitement des commandes bits si présents
        if "bits" in tags:
            bits_amount = tags.get("bits", "0")
            if self.enable_events:
                await self._react_to_event_with_ws(chan, "bits", {"author": author, "amount": bits_amount, "msg": text}, ws)
            return

        # 2. Check Command
        is_cmd = await self._handle_command(chan, author, text, ws)
        if is_cmd:
            return

        # 3. Check Mention
        is_mention = self.trigger_re.search(text)
        if is_mention:
            # Cooldown par utilisateur (3s)
            now = time.time()
            last_user_time = self.user_cooldowns.get(author.lower(), 0)
            if now - last_user_time < 3.0:
                self.logger.info(f"⏳ [TWITCH_CHAT:{self.bot_id}] Message de {author} ignoré (cooldown)")
                return
            self.user_cooldowns[author.lower()] = now

            # Rate limit global (18 msgs / 30s)
            while self.global_msg_timestamps and now - self.global_msg_timestamps[0] > 30.0:
                self.global_msg_timestamps.popleft()

            if len(self.global_msg_timestamps) >= 18:
                self.logger.warning(f"🚨 [TWITCH_CHAT:{self.bot_id}] Rate limit global atteint. Message ignoré.")
                return

            self.logger.info(f"📥 [TWITCH_CHAT:{self.bot_id}] Message reçu de {author} sur #{chan} : {text}")

            # Le message mentionnant le bot alimente aussi le contexte ambiant du salon
            chan_key = chan.lower()
            if chan_key not in self.channel_recent:
                self.channel_recent[chan_key] = collections.deque(maxlen=8)
            self.channel_recent[chan_key].append(f"{author}: {text}")

            # On compte la tentative de génération dans le rate-limit global
            self.global_msg_timestamps.append(time.time())

            # Réponse (mention) - Réponse questions jeu
            facts_block = None
            no_facts_warning = False
            if getattr(self, "enable_game_qa", False):
                from shared.twitch.game_info import detect_game_question
                category = detect_game_question(text)
                if category:
                    facts_block, no_facts_warning = await self._fetch_game_facts_block(chan, category)

            reply = await self._generate_response(chan, author, text, game_facts_block=facts_block, no_facts_warning=no_facts_warning)
            if reply:
                await send_chat_safe(ws, chan, reply, bot_id=self.bot_id, logger=self.logger)
            return

        # 4. Message passif
        chan_lower = chan.lower()
        if chan_lower not in self.channel_recent:
            self.channel_recent[chan_lower] = collections.deque(maxlen=8)
        self.channel_recent[chan_lower].append(f"{author}: {text}")

        # Suivi des viewers (accueil)
        author_lower = author.lower()
        is_first_session_msg = False
        if author_lower not in self.session_seen:
            self.session_seen.add(author_lower)
            is_first_session_msg = True
            
            if author_lower not in self.viewers_state:
                self.viewers_state[author_lower] = {"count": 0, "last_seen": ""}
            
            today = datetime.now().strftime("%Y-%m-%d")
            viewer_data = self.viewers_state[author_lower]
            if viewer_data.get("last_seen") != today:
                viewer_data["count"] = viewer_data.get("count", 0) + 1
                viewer_data["last_seen"] = today
                self._save_viewers_state_debounced()

        # Au plus une seule action spontanée
        spontaneous_sent = False

        # Option A : Favor passif (si configuré)
        if self.passive_handler:
            try:
                if asyncio.iscoroutinefunction(self.passive_handler):
                    res = await self.passive_handler(author, text)
                else:
                    res = self.passive_handler(author, text)
                if res:
                    now = time.time()
                    while self.global_msg_timestamps and now - self.global_msg_timestamps[0] > 30.0:
                        self.global_msg_timestamps.popleft()
                    if len(self.global_msg_timestamps) < 18:
                        self.global_msg_timestamps.append(now)
                        await send_chat_safe(ws, chan, res, bot_id=self.bot_id, logger=self.logger)
                        spontaneous_sent = True
            except Exception as e:
                self.logger.error(f"❌ [TWITCH_CHAT:{self.bot_id}] Erreur passive_handler: {e}")

        # Option A.2 : Réponse passive co-host aux questions jeu
        if not spontaneous_sent and getattr(self, "enable_game_qa", False):
            chan_key = chan.lower().lstrip("#")
            if chan_key in getattr(self, "cohost_channels", []):
                from shared.twitch.game_info import detect_game_question
                category = detect_game_question(text)
                if category:
                    now = time.time()
                    last_cohost_time = getattr(self, "_last_cohost_qa", {}).get(chan_key, 0)
                    if now - last_cohost_time >= 30.0:
                        while self.global_msg_timestamps and now - self.global_msg_timestamps[0] > 30.0:
                            self.global_msg_timestamps.popleft()
                        if len(self.global_msg_timestamps) < 14:
                            facts_block, no_facts_warning = await self._fetch_game_facts_block(chan, category)

                            reply = await self._generate_response(chan, author, text, game_facts_block=facts_block, no_facts_warning=no_facts_warning)
                            if reply:
                                if not hasattr(self, "_last_cohost_qa"):
                                    self._last_cohost_qa = {}
                                self._last_cohost_qa[chan_key] = now
                                self.global_msg_timestamps.append(now)
                                await send_chat_safe(ws, chan, reply, bot_id=self.bot_id, logger=self.logger)
                                spontaneous_sent = True

        # Option B : Accueil de session
        if not spontaneous_sent and is_first_session_msg and self.enable_greetings:
            spontaneous_sent = await self._try_greeting(chan, author, ws)

        # Option C : Interjection spontanée
        if not spontaneous_sent and self.enable_interjections:
            await self._try_interjection(chan, ws)

    async def _handle_command(self, chan: str, author: str, text: str, ws) -> bool:
        if not text.startswith("!"):
            return False
            
        parts = text[1:].split(" ", 1)
        cmd_name = parts[0].strip().lower()
        args = parts[1].strip() if len(parts) > 1 else ""
        
        # Résolution alias
        if cmd_name in self.command_aliases:
            cmd_name = self.command_aliases[cmd_name]
            
        if cmd_name in self.commands:
            now = time.time()
            # Cooldown utilisateur (3s)
            last_user_time = self.user_cooldowns.get(author.lower(), 0)
            if now - last_user_time < 3.0:
                self.logger.info(f"⏳ [TWITCH_CHAT:{self.bot_id}] Commande !{cmd_name} de {author} ignorée (cooldown utilisateur)")
                return True
            self.user_cooldowns[author.lower()] = now

            # Cooldown global commande (5s)
            last_cmd_time = self.command_cooldowns.get(cmd_name, 0)
            if now - last_cmd_time < 5.0:
                self.logger.info(f"⏳ [TWITCH_CHAT:{self.bot_id}] Commande !{cmd_name} ignorée (cooldown global)")
                return True
            self.command_cooldowns[cmd_name] = now

            # Exécution
            try:
                callback = self.commands[cmd_name]
                if asyncio.iscoroutinefunction(callback):
                    res = await callback(author, args)
                else:
                    res = callback(author, args)
                
                if res:
                    while self.global_msg_timestamps and now - self.global_msg_timestamps[0] > 30.0:
                        self.global_msg_timestamps.popleft()
                    
                    if len(self.global_msg_timestamps) >= 18:
                        self.logger.warning(f"🚨 [TWITCH_CHAT:{self.bot_id}] Rate limit global atteint pour la commande !{cmd_name}.")
                        return True

                    self.global_msg_timestamps.append(now)
                    await send_chat_safe(ws, chan, res, bot_id=self.bot_id, logger=self.logger)
            except Exception as e:
                self.logger.error(f"❌ [TWITCH_CHAT:{self.bot_id}] Erreur lors de l'exécution de la commande !{cmd_name}: {e}")
            return True
            
        return False

    async def _try_greeting(self, chan: str, author: str, ws) -> bool:
        now = time.time()
        # Cooldown accueil spécifique (15 s)
        last_greet = getattr(self, "_last_greet_ts", 0)
        if now - last_greet < 15.0:
            return False

        # Budget check (marge rate limit global)
        while self.global_msg_timestamps and now - self.global_msg_timestamps[0] > 30.0:
            self.global_msg_timestamps.popleft()
        if len(self.global_msg_timestamps) >= 14:
            return False

        self._last_greet_ts = now
        self.global_msg_timestamps.append(now)

        viewer_data = self.viewers_state.get(author.lower(), {})
        count = viewer_data.get("count", 1)
        reply = self._generate_templated_greet(author, count, chan=chan)
        
        await send_chat_safe(ws, chan, reply, bot_id=self.bot_id, logger=self.logger)
        return True

    async def _try_interjection(self, chan: str, ws) -> bool:
        now = time.time()
        last_inter = getattr(self, "_last_interjection", 0)
        if now - last_inter < self.interjection_min_interval:
            return False

        if random.random() > self.interjection_chance:
            return False

        while self.global_msg_timestamps and now - self.global_msg_timestamps[0] > 30.0:
            self.global_msg_timestamps.popleft()
        if len(self.global_msg_timestamps) >= 14:
            return False

        self._last_interjection = now
        self.global_msg_timestamps.append(now)

        reply = await self._generate_interjection(chan)
        if reply:
            await send_chat_safe(ws, chan, reply, bot_id=self.bot_id, logger=self.logger)
            return True
        return False

    # Clauses ajoutees a l'instruction POUR UN SEUL BOT. Vide par defaut : un bot absent
    # de cette table recoit exactement le texte commun, inchange.
    #
    # ⚠️ Pourquoi par bot et pas dans le texte commun : la mesure du 2026-09-21 (detaillee
    # dans `_generate_link_line`) montre que cette clause fait passer Sugar de 4 objets
    # inventes sur 6 a ZERO, et qu'elle EFFONDRE les ouvertures de M'aiq (5/5 sur la meme
    # formule). Ajouter un bot ici demande donc de mesurer ce bot-la, pas de supposer.
    CLAUSES_PAR_BOT = {
        "sugar": (
            "⚠️ Et tu n'offres RIEN de matériel : si ta phrase contient une chose qu'on "
            "pourrait tenir, boire ou déballer, c'est une invention, même modeste — "
            "remplace-la par ce que TU y seras ou y feras. "
            "Ce que tu annonces change à chaque fois : tantôt ce que tu y fais, tantôt ce "
            "que tu leur diras en arrivant, tantôt ce qui t'y amuse. Évite la formule "
            "d'attente toute faite : dis quelque chose que toi seul dirais. "
            "⚠️ Ce serveur n'est pas le tien : il appartient à la communauté, et tu n'es "
            "qu'une de celles qui s'y trouvent. Tu ne dis jamais « mon serveur » ni « chez "
            "moi », et tu n'invites pas comme si tu en étais l'hôtesse. Parle au NOUS "
            "quand tu parles de là-bas — « on t'attend », « viens nous voir » — et garde "
            "le « je » pour ce que toi seule y fais. "
        ),
        # ⚠️ Johnny promettait une tournee : sur 8 generations du texte commun, SIX
        # offraient une biere, un verre ou une clope au lecteur (« les clopes sont
        # gratuites », « je te sers le premier verre »). Mesure du 2026-09-21 sur sa vraie
        # tete (ministral), 8 generations par variante :
        #
        #     texte commun seul .................... 6/8 promettent quelque chose
        #     clause neutre de Sugar ............... 6/8  (aucun effet)
        #     clause ci-dessous .................... 3/8
        #
        # ⚠️ Elle vise la PROMESSE, pas le mot : le whisky et la clope SONT son vocabulaire
        # et doivent rester. Ce qui est interdit, c'est d'en offrir un au lecteur.
        # ⚠️ Et elle nomme les objets interdits, ce qui va contre
        # [[gotcha-le-prompt-enseigne-le-tic-interdit]] — c'est assume : la version SANS
        # exemple a ete mesuree aussi (4/8), et elle faisait en plus sortir la phrase entre
        # guillemets et asterisques 4 fois sur 8, ce que le nettoyeur jette.
        "johnny": (
            "⚠️ Tu ne promets rien qui les attendrait là-bas : ni tournée, ni verre, ni "
            "place gardée — tu n'as rien à offrir et tu n'as jamais rien offert à "
            "personne. Ce qui les attend, c'est toi : ta gueule, tes histoires, ce que tu "
            "vas leur balancer. Tes clopes et ton whisky restent les TIENS, tu ne les "
            "partages pas dans la phrase. "
        ),
    }

    async def _generate_link_line(self, cmd: str, label: str, url: str) -> str | None:
        """Fait écrire au bot, EN PERSONNAGE, la phrase qui accompagne un lien.

        ⚠️ Le modèle n'écrit JAMAIS l'adresse. Il produit une phrase, et le code y accole
        l'URL telle qu'elle est configurée. Un lien est la seule chose d'un message dont
        l'exactitude ne se négocie pas : une adresse « presque bonne » est pire qu'une
        phrase fade, et un LLM tronque, francise ou invente une URL sans prévenir.
        Tout ce qui ressemble à une adresse est donc retiré de sa phrase avant l'envoi.

        Rend None si rien d'exploitable : l'appelant retombe alors sur le gabarit fixe.
        """
        if not url:
            return None

        # Cache court : `!discord` peut être tapé dix fois d'affilée, et chaque appel
        # coûterait un appel LLM. La phrase change plusieurs fois par heure, ça suffit.
        maintenant = time.time()
        cache = getattr(self, "_link_lines_cache", None)
        if cache is None:
            cache = self._link_lines_cache = {}
        vue = cache.get(cmd)
        if vue and maintenant - vue[0] < 900:
            return f"{vue[1]} {url}"

        system_prompt = self.personality_prompt
        if self.system_prompt_provider:
            try:
                sp = self.system_prompt_provider()
                if sp:
                    system_prompt = sp
            except Exception as e:
                self.logger.warning(
                    f"⚠️ [TWITCH_CHAT:{self.bot_id}] system_prompt_provider a échoué "
                    f"dans _generate_link_line : {e}"
                )
        if not system_prompt or self.key_manager is None:
            return None

        quoi = label or cmd
        # ⚠️ « Inviter » ne suffisait pas : le modèle rendait des constats polis. On lui
        # demande de DONNER ENVIE, et on lui rappelle ce qu'il ne sait pas — il ignore qui
        # est dans ce serveur, ce qui s'y passe et combien ils sont. Sans cette borne, une
        # accroche enthousiaste invente un chiffre, un salon ou une récompense, et le chat
        # y croit. Même règle que l'annonce de live : enjoliver le TON, jamais les FAITS.
        # L'emoji est explicitement autorisé (un seul) : rien ne le retire sur le chemin
        # Twitch — la troncature le recolle même à la fin — mais tant qu'on ne le demandait
        # pas, les phrases sortaient sèches.
        # ⚠️ « Promets l'AMBIANCE » ne tenait pas debout : la phrase d'apres interdit TOUT
        # ce qui est concret sur la destination. Il ne restait rien de vrai a offrir, et
        # un modele a qui on demande de donner envie sans rien pouvoir promettre se
        # rabat sur la seule chose qu'il observe — le chat devant lui — et vend par
        # comparaison. D'ou les deux reproches d'Ahmed le 19/09 sur la MEME phrase :
        # elle denigrait le salon hote, et elle ne donnait pas envie.
        # On lui rend donc la seule chose qu'il sache avec certitude : LUI. Sa presence
        # la-bas et ce qu'il y fera n'inventent rien, et c'est concret.
        # Mesure : « l'air y est delicieusement veneneux » / « la meilleure ambiance du
        # coin » deviennent « j'ai garde une place rien que pour toi » / « rejoins-moi,
        # tu verras a quel point le sucre peut mordre ».
        #
        # ⚠️ CE QUI RESTE CASSE, ET LES DEUX RUSTINES QUI NE MARCHENT PAS (mesure du
        # 2026-09-21, apres un signalement d'Ahmed sur une phrase de Sugar : « je t'attends
        # avec une bonne tasse de caramel chaud »). Le modele invente un OBJET — une
        # boisson, un siege, un cadeau — dans environ une generation sur deux, alors que
        # la clause ci-dessus lui interdit deja d'inventer une « recompense ». Compte sur
        # 4 a 6 generations par cellule, tete flash-lite, temperature 1.0 :
        #
        #     variante                         sugar        maiq         alfred
        #     A : le texte actuel              4/6 objets   2/4          2/4
        #     B : + « tu n'offres rien de
        #         materiel » (interdiction)    1/6          3/5          3/5
        #     C : B + « varie ce que tu
        #         annonces »                   0/6          1/4          2/4
        #     D : « ce que tu offres est
        #         immateriel » (positive)      1/5          3/5           -
        #
        # B et C reparent Sugar et CASSENT M'aiq : ses ouvertures s'effondrent sur une
        # seule formule (5/5 « Les Plaines de l'Echo... » en B, 3/4 en C) la ou le texte
        # actuel en rend quatre differentes. **Aucune formulation partagee n'ameliore les
        # six** — troisieme demonstration du meme jour que
        # [[gotcha-un-filet-ne-se-transpose-pas-d-un-bot-a-l-autre]].
        # D'ou `CLAUSES_PAR_BOT` ci-dessus : la variante C est livree POUR SUGAR SEUL,
        # ou elle est mesuree (4/6 -> 0/6), et le texte commun ne bouge pas d'une virgule
        # pour les cinq autres.
        #
        # ⚠️ 2e reproche d'Ahmed sur la meme phrase, le soir meme : **Sugar parlait du
        # Discord comme du SIEN** (« Viens sur mon serveur »), alors qu'il est celui de la
        # communaute. La cause est la clause « ce que tu promets, c'est TOI » ci-dessus :
        # elle a supprime la vente par comparaison, et installe la possession a la place.
        # Une clause collective (« il appartient a la communaute, parle au NOUS ») a ete
        # mesuree, ajoutee a ce que chaque bot recoit deja :
        #
        #     sugar (avec sa clause)   0/6 « mon serveur », 0/6 objet, voix intacte
        #     maiq  (texte commun)     5/5 ouvertures IDENTIQUES, et le feu de camp revient
        #     alfred (texte commun)    5/5 inventent un the ou des tasses (contre 2/4 avant)
        #
        # Le mecanisme est celui du 19/09 : prive de ce qu'il peut promettre, le modele se
        # rabat sur ce qu'il imagine du lieu. Chez Sugar la clause anti-objet retient cette
        # dérive ; chez les deux autres, qui ne l'ont pas, elle s'aggrave. La clause
        # collective est donc livree DANS la clause de Sugar, pas dans le texte commun.
        #
        # ⚠️ ET LA QUESTION « POURQUOI PAS LES CINQ AUTRES ? » EST TRANCHEE, PAR LA MESURE.
        # Le 2026-09-21 au soir, la clause complete de Sugar (anti-objet + variete +
        # collectif) a ete essayee sur chacun, **sur sa vraie tete de cascade** — johnny
        # sur ministral, sheo sur groq, les autres sur flash-lite. 4 generations par
        # cellule :
        #
        #     bot      texte commun                   + clause de Sugar
        #     alfred   3/4 objets, 1/4 « demeure »    2/4 objets, 0/4 possession   leger +
        #     malena   0 objet, 0 possession          4/4 LA MEME ouverture         -
        #     maiq     2/4 objets                     3/4 a 5/5 la meme ouverture   -
        #     johnny   4/4 objets (bieres, clopes)    3/4 objets                    =
        #     sheo     propre sur 3 generations       non mesure (429 Groq)         ?
        #
        # La clause n'est donc PAS etendue : elle abime Malena et M'aiq, dont les ouvertures
        # s'effondrent sur une formule unique, et n'apporte rien de mesurable a Johnny.
        # Chez Alfred le gain est dans le bruit a n=4.
        # ⚠️ Ce que la mesure a montre au passage, et qui reste OUVERT : Johnny invente une
        # boisson dans 4 generations sur 4 (« les premieres bieres sont a mon nom »), Alfred
        # dans 3 sur 4 — le defaut signale sur Sugar existe chez eux aussi, en pire. Et
        # leurs phrases depassent allegrement les 120 caracteres demandes.
        #
        # ⚠️ Au passage, un defaut voisin, deja present SANS aucune rustine : Alfred sort
        # « Cette demeure », « Ces murs » et meme « La bibliotheque du serveur » — alors
        # que sa fiche lui interdit « le Manoir » et que cette instruction-ci lui interdit
        # d'inventer un salon. Non corrige, faute de mesure suffisante (2 cas sur 4).
        instruction = (
            f"Écris UNE seule phrase très courte (max 120 caractères), en personnage, "
            f"qui donne ENVIE au chat Twitch de rejoindre {quoi} : une invitation adressée "
            f"directement à eux, pas une annonce. "
            f"Sois CHALEUREUX et GENTIL : tu es content qu'ils viennent, et ça s'entend. "
            f"Pas de pique, pas de moquerie, pas de défi, rien aux dépens de qui que ce "
            f"soit — même pour rire. Tu gardes ta voix, mais tu en montres le côté le "
            f"plus accueillant. "
            f"Ce que tu promets, c'est TOI : que tu y es, et que tu les y accueilleras. "
            f"C'est la seule chose que tu saches avec certitude, et elle suffit. "
            f"Tu ne sais rien d'autre : ni qui s'y trouve, ni ce qui s'y passe, ni combien "
            f"ils sont — n'invente ni chiffre, ni salon, ni évènement, ni récompense. "
            f"Ta phrase ne parle que de là-bas. L'endroit d'où tu écris n'y apparaît pas : "
            f"tu ne le décris pas, tu ne le juges pas, et tu ne compares jamais les deux. "
            f"Tu peux finir par UN emoji, s'il colle à ton personnage. "
            f"N'ÉCRIS PAS l'adresse ni aucun lien : elle sera ajoutée juste après ta phrase. "
            f"Pas de guillemets, pas de didascalie."
        )
        # ⚠️ La clause par bot s'insere AVANT la fin du texte commun serait plus propre,
        # mais l'ordre ne change rien a la mesure : elle est ajoutee ici, et un bot absent
        # de la table ne voit aucune difference.
        instruction += " " + self.CLAUSES_PAR_BOT.get(self.bot_id, "")

        try:
            from shared.llm_cascade import generate_response
            from shared.smart_router import classify_request
            try:
                routing = classify_request(instruction)
            except Exception:
                routing = {"type": "text"}

            texte = await generate_response(
                routing=routing,
                system_prompt=system_prompt + "\n\n" + ANTI_INJECTION_GUARD,
                transcript="",
                user_message=instruction,
                conversation_history=[],
                media_data=None,
                mime_type="",
                key_manager=self.key_manager,
                mistral_client=self.mistral_client,
                groq_client=self.groq_client,
                nvidia_client=getattr(self, "nvidia_client", None),
                bot_label=self.bot_label or self.bot_id,
                temperature=1.0,
                max_tokens=60,
                # Quelqu'un attend devant son chat : on préfère le gabarit fixe à
                # quinze secondes de silence.
                call_timeout=8.0,
            )
        except Exception as e:
            self.logger.error(f"❌ [TWITCH_CHAT:{self.bot_id}] Erreur phrase de lien !{cmd} : {e}")
            return None

        phrase = _nettoyer_phrase_de_lien(texte)
        if not phrase:
            return None

        cache[cmd] = (maintenant, phrase)
        self.logger.info(f"✨ [TWITCH_CHAT:{self.bot_id}] Phrase de lien !{cmd} écrite par le bot : {phrase}")
        return f"{phrase} {url}"

    async def _generate_interjection(self, chan: str) -> str | None:
        system_prompt = self.personality_prompt
        if self.system_prompt_provider:
            try:
                sp = self.system_prompt_provider()
                if sp:
                    system_prompt = sp
            except Exception as e:
                self.logger.warning(f"⚠️ [TWITCH_CHAT:{self.bot_id}] system_prompt_provider a échoué dans _generate_interjection : {e}")

        if not system_prompt or self.key_manager is None:
            return None

        recent_msgs = list(self.channel_recent.get(chan.lower(), []))
        if not recent_msgs:
            return None

        context_str = "\n".join(recent_msgs)
        instruction = (
            f"Voici les derniers messages du chat Twitch :\n{context_str}\n\n"
            f"Fais une interjection spontanée très courte (1 phrase, max 100 caractères), en personnage, "
            f"pour commenter ou réagir avec dérision à ce que disent les viewers. Sois bref et percutant."
        )

        full_system_prompt = system_prompt + "\n\n" + ANTI_INJECTION_GUARD

        try:
            from shared.llm_cascade import generate_response
            from shared.smart_router import classify_request
            
            try:
                routing = classify_request(instruction)
            except Exception:
                routing = {"type": "text"}

            text = await generate_response(
                routing=routing,
                system_prompt=full_system_prompt,
                transcript="",
                user_message=instruction,
                conversation_history=[],
                media_data=None,
                mime_type="",
                key_manager=self.key_manager,
                mistral_client=self.mistral_client,
                groq_client=self.groq_client,
                 nvidia_client=getattr(self, "nvidia_client", None),
                bot_label=self.bot_label or self.bot_id,
                temperature=1.0,
                max_tokens=70
            )
            if text:
                text = " ".join(text.split())
                text = strip_stage_directions(text)
                return text[:480]
        except Exception as e:
            self.logger.error(f"❌ [TWITCH_CHAT:{self.bot_id}] Erreur lors de l'intégration de l'interjection : {e}")
        return None
