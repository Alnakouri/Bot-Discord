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
    return phrase[:200]


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
        instruction = (
            f"Écris UNE seule phrase très courte (max 120 caractères), en personnage, "
            f"qui donne ENVIE au chat Twitch de rejoindre {quoi} : une invitation adressée "
            f"directement à eux, pas une annonce. "
            f"Ce que tu promets, c'est TOI : que tu y es, et ce que tu leur y feras, dans "
            f"ton style. C'est la seule chose que tu saches avec certitude, et elle suffit. "
            f"Tu ne sais rien d'autre : ni qui s'y trouve, ni ce qui s'y passe, ni combien "
            f"ils sont — n'invente ni chiffre, ni salon, ni évènement, ni récompense. "
            f"Ta phrase ne parle que de là-bas. L'endroit d'où tu écris n'y apparaît pas : "
            f"tu ne le décris pas, tu ne le juges pas, et tu ne compares jamais les deux. "
            f"Tu peux finir par UN emoji, s'il colle à ton personnage. "
            f"N'ÉCRIS PAS l'adresse ni aucun lien : elle sera ajoutée juste après ta phrase. "
            f"Pas de guillemets, pas de didascalie."
        )

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
