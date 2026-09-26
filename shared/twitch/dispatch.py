# -*- coding: utf-8 -*-
import re
import time
import unicodedata
import random
import collections
import asyncio
import contextvars
from datetime import datetime
from shared.twitch.sanitize import strip_stage_directions, send_chat_safe
from shared.twitch.llm import ANTI_INJECTION_GUARD

# Canal d'ou vient la commande (ou l'annonce auto) en cours d'execution. Les callbacks de
# commande ne recoivent que (author, args) : sans ceci, `_jeu_en_cours` lisait toujours le
# PREMIER canal, et sur #chaine_du_dev Sugar parlait du jeu de ma_streameuse (23/09).
# Une ContextVar, et pas un attribut du bot : deux commandes de deux canaux peuvent
# s'entrelacer pendant l'appel LLM, et chacune doit garder SON canal.
_CANAL_COURANT = contextvars.ContextVar("canal_courant", default=None)

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
# ⚠️ Une invitation ne peut pas invoquer une conversation qui n'a jamais eu lieu.
#
# Signale par Ahmed le 2026-09-22 sur une vraie sortie Twitch de Sugar :
#
#     « On s'en reparlera des choix de Henry, rejoins-nous sur le serveur. 🍬 »
#
# Trois fautes en sept mots. « On s'en REparlera » suppose un echange passe — le viewer
# n'a jamais dit un mot a Sugar. Ce n'est pas une invitation mais un RENVOI a plus tard,
# qui ne donne aucune raison de venir. Et « les choix de Henry » ne dit rien du jeu, ca le
# cite. C'est la meme famille que l'objet invente, en plus retors : ce n'est pas un objet
# qu'elle invente, c'est un PASSE COMMUN.
#
# L'instruction l'interdit deja en toutes lettres (« ne promets pas qu'on en parlera
# la-bas ») et le modele passe outre. Une clause de plus n'y changera rien — trois
# formulations essayees ce soir l'ont montre. D'ou ce filet, qui ne depend d'aucun tirage.
# Evalue sur les 15 phrases reelles collectees ce soir : 5 fautes attrapees, 0 faux
# positif sur les 10 bonnes.
# ⚠️ Rejette, ne repare pas : retirer le membre de phrase laisserait un moignon, et le
# gabarit fixe est fade — fade bat casse, comme pour l'adresse et le salon hote.
# ⚠️ Une invitation ne prend pas son PUBLIC pour cible.
#
# Mesure du 2026-09-22 : en demandant a la phrase de « claquer », 2 generations sur 8
# retournaient la pique contre le chat Twitch — « fatigue moins que de supporter vos
# commentaires en boucle » — alors que la clause dit « jamais sur ceux qui regardent ».
# Une interdiction de prompt tient a 75 %, c'est la lecon de toute la soiree.
#
# Ce motif-ci ne contient QUE des tournures qui ne peuvent designer que le public d'un
# stream. Le mot « chat », lui, est dans la table par bot plus bas : c'est un mot
# parfaitement legitime chez M'aiq, qui EST un Khajiit, et chez Malena qui appelle les
# gens « mes p'tits chats ». Partager ce qui ne peut pas se tromper, isoler ce qui peut :
# c'est exactement ce que [[gotcha-un-filet-ne-se-transpose-pas-d-un-bot-a-l-autre]] repete.
_VISE_LE_PUBLIC = re.compile(
    r"(?:vos|tes|ton|votre|leur|le)\s+tchats?\b"
    r"|(?:vos|tes|leurs)\s+(?:commentaires?|messages)\b"
    r"|\bvotre\s+(?:commentaire|message)\b",
    re.I,
)

# Motifs supplementaires, PAR BOT, pour ce qu'on ne peut pas interdire a tout le monde.
# Sugar n'a pas de chat dans son lore ; M'aiq en est un. D'ou la separation.
_VISE_LE_PUBLIC_PAR_BOT = {
    "sugar": re.compile(r"(?:ton|votre|le|leur)\s+chat\b", re.I),
}

_INVOQUE_UN_PASSE_COMMUN = re.compile(
    r"\b(?:on|nous)\s+(?:s['’]en\s+|en\s+)?(?:re|ré)(?:parler|parlera|parlerons|discute"
    r"|discutera|discuterons)\w*"
    r"|\bon\s+en\s+(?:re)?(?:parlera|parlerons|parle|discutera|discute)\b"
    r"|\bcomme\s+(?:je|on)\s+(?:te|vous)\s+(?:le\s+)?disai[ts]\b",
    re.I,
)

# ⚠️ Une EPOQUE affirmee sur le jeu. Live du 2026-09-22 sur #ma_streameuse : « Le treizieme
# siecle sans armure, ca pique » pour Kingdom Come: Deliverance II — qui se passe en 1403,
# au XVe. Un spectateur l'a corrige dans le chat. Le modele ne recoit que le NOM du jeu :
# ce qu'il en affirme vient de sa memoire, et une date est ce que le chat verifie le plus
# vite. On rejette (seconde chance, puis gabarit fixe) : fade bat faux.
_AFFIRME_UNE_EPOQUE = re.compile(r"\bsi[èe]cles?\b|\b(?:1\d|20)\d\d\b", re.I)
# Sensible a la CASSE, volontairement : avec re.I, « vie » passerait pour un siecle.
_SIECLE_EN_CHIFFRES_ROMAINS = re.compile(r"\b[IVXL]{2,6}(?:e|è|ème)\b")


_ROMAINS = {"I": 1, "V": 5, "X": 10, "L": 50}
_SIECLES_EN_LETTRES = {
    "dixieme": 10, "onzieme": 11, "douzieme": 12, "treizieme": 13, "quatorzieme": 14,
    "quinzieme": 15, "seizieme": 16, "dix-septieme": 17, "dix-huitieme": 18,
    "dix-neuvieme": 19, "vingtieme": 20, "vingt-et-unieme": 21, "vingt et unieme": 21,
}
# « XVe », « XVe siecle », « Xe siecle », « 15e siecle », « quinzième siècle ».
# ⚠️ Une seule lettre romaine ou un nombre en chiffres n'est un siecle que SUIVI de
# « siecle » : sinon « Le » (L + e) et « la 2e fois » passeraient pour des epoques.
# Les romains sont sensibles a la CASSE, comme `_SIECLE_EN_CHIFFRES_ROMAINS`.
_UN_SIECLE = re.compile(
    r"\b(?P<romain>[IVXL]{2,6})(?:e|è|ème)\b(?:\s+si[èe]cle)?"
    r"|\b(?:(?P<romain1>[IVXL])|(?P<chiffre>\d{1,2}))(?:e|è|ème|eme)\s+si[èe]cle"
    r"|\b(?P<lettres>(?:vingt[- ]et[- ]uni|dix-(?:sept|huit|neuv)|dix|onz|douz|treiz|"
    r"quatorz|quinz|seiz|vingt)(?:i[èe]me))\s+si[èe]cle"
)


def _romain(texte: str) -> int | None:
    valeurs = [_ROMAINS[c] for c in texte]
    total = sum(-v if i + 1 < len(valeurs) and v < valeurs[i + 1] else v
                for i, v in enumerate(valeurs))
    return total or None


def _siecles_de_la_fiche(fiche: str | None) -> set[int]:
    """Les siecles que la fiche IGDB (en anglais) AFFIRME : « 15th century »."""
    return {int(n) for n in re.findall(r"\b(\d{1,2})(?:st|nd|rd|th)[- ]century\b",
                                       fiche or "", re.I)}


# Ce qu'on retire de la fiche AVANT de la donner au modele — et SEULEMENT a lui.
# ⚠️ Le siecle SEUL, sans sa preposition : « set in 15th century Medieval Europe » doit
# devenir « set in Medieval Europe », pas « set Medieval Europe ». L'annee, AVEC sa
# preposition (et sa virgule) : « In 1403, Henry… » -> « Henry… ». Une annee nue n'est pas
# retiree : « Over 1000 quests » n'est pas une date.
_EPOQUE_DE_LA_FICHE = re.compile(
    r"\s*\b\d{1,2}(?:st|nd|rd|th)[- ]century\b"
    r"|\s*\b(?:in|since|from|during)\s+1\d{3}\b,?",
    re.I,
)


def _fiche_sans_epoque(fiche: str | None) -> str | None:
    """La fiche IGDB sans ses siecles ni ses annees, pour l'INSTRUCTION du modele.

    ⚠️ Mesure du 2026-09-23 (KCD2, n=18, Gemini) : avec « 15th century » dans la fiche, le
    siecle sort dans 18/18 phrases d'Alfred, 16/18 de Malena, 14/18 de Sugar et de Johnny,
    contre 0/18 sans fiche. Les ouvertures d'Alfred passent de 9 formes a 4. Une date
    ecrite dans le prompt devient un tic ([[gotcha-une-formule-nommee-devient-un-tic]]).
    Le reste de la fiche est garde : il fait disparaitre les faits inventes (« Henri V »).

    ⚠️ Le FILET, lui, recoit la fiche COMPLETE (`_affirme_une_epoque(phrase, jeu, fiche)`) :
    si le modele cite quand meme le XVe siecle de sa memoire, c'est juste, et ca passe.
    """
    if not fiche:
        return fiche
    propre = _EPOQUE_DE_LA_FICHE.sub("", fiche)
    return " ".join(propre.split()).replace(" ,", ",").replace(" .", ".")


def _affirme_une_epoque(phrase: str, jeu: str | None, fiche: str | None = None) -> bool:
    """Vrai si la phrase DATE le jeu d'une epoque qu'on ne lui a PAS donnee.

    Ne s'applique qu'a l'accroche (sans jeu : False).

    Les nombres du TITRE sont permis : « Cyberpunk 2077 », « Anno 1800 » sont des noms,
    pas des affirmations — les rejeter punirait la seule chose vraie qu'on a donnee.

    ⚠️ Et ce que la FICHE affirme est permis aussi. Live du 2026-09-23 sur #ma_streameuse :
    la fiche IGDB de KCD2 dit « 15th century », le modele a ecrit « XVe siecle » — JUSTE —
    deux fois, et le filet strict a rejete les deux : gabarit fixe. On permet donc le
    siecle et les annees que la fiche porte, et RIEN d'autre : « le treizieme siecle »
    d'hier reste rejete, fiche ou pas. Un siecle qu'on ne sait pas lire est rejete.
    """
    if not jeu:
        return False
    permis = set(re.findall(r"\d+", jeu)) | set(re.findall(r"\b\d{4}\b", fiche or ""))
    siecles_permis = _siecles_de_la_fiche(fiche)

    lu = phrase
    for m in _UN_SIECLE.finditer(phrase):
        if m.group("romain") or m.group("romain1"):
            n = _romain(m.group("romain") or m.group("romain1"))
        elif m.group("chiffre"):
            n = int(m.group("chiffre"))
        else:
            cle = unicodedata.normalize("NFD", m.group("lettres").lower())
            cle = "".join(c for c in cle if unicodedata.category(c) != "Mn")
            n = _SIECLES_EN_LETTRES.get(cle.replace("  ", " "))
        if n is None or n not in siecles_permis:
            return True
        lu = lu.replace(m.group(0), " ")      # siecle verifie : il ne compte plus

    for m in _AFFIRME_UNE_EPOQUE.finditer(lu):
        if m.group(0) not in permis:
            return True
    return bool(_SIECLE_EN_CHIFFRES_ROMAINS.search(lu))


_NOMME_LA_SOURCE = re.compile(
    r"(?:"
    # Nommer le lieu d'ou l'on ecrit.
    r"\bce chat\b|\bdu chat\b|\ble chat\b|chat twitch|\btwitch\b"
    r"|\bce stream\b|\ble stream\b|en plein stream|\bce live\b|\ble live\b"
    r"|\bce salon-ci\b|\bce tchat\b"
    # Le comparer : « plus savoureux qu'ici », « autrement plus de mordant ».
    r"|\bqu['’ ]?ici\b|autrement plus|\bmieux qu|\bmeilleur qu"
    r")", re.IGNORECASE)


def _nettoyer_phrase_de_lien(texte: str | None, bot_id: str | None = None) -> str | None:
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
    # ⚠️ DEBALLER AVANT DE NETTOYER. Certains modeles rendent toute la replique enrobee :
    # `*"... viens donc. 🎸"*`. `strip_stage_directions` y voit une didascalie et supprime
    # TOUT — la phrase devient vide, et le bot retombe sur le gabarit fixe. Mesure du
    # 2026-09-22 : avec l'accroche au jeu, ministral enrobe 5 repliques de Johnny sur 6,
    # donc cinq invitations ecrites pour rien. On retire donc l'emballage tant qu'il
    # entoure la phrase ENTIERE — ce qui n'enleve aucune vraie didascalie, celles-ci
    # n'occupant jamais la replique complete.
    for _ in range(3):
        avant = phrase
        for ouvre, ferme in (("*", "*"), ('"', '"'), ("«", "»"), ("“", "”")):
            if len(phrase) > 2 and phrase.startswith(ouvre) and phrase.endswith(ferme):
                milieu = phrase[len(ouvre):-len(ferme)]
                # Un emballage n'a pas de jumeau a l'interieur : `*a* et *b*` n'est pas
                # une phrase enrobee, c'est une phrase AVEC deux didascalies.
                # ⚠️ Et on n'ouvre que si l'interieur est une PHRASE : sans ce garde,
                # `*sourit*` — une vraie didascalie, que le nettoyeur jetait a raison —
                # deviendrait l'invitation « sourit ». Deux criteres, parce que le
                # premier seul laissait passer `*Il sourit puis repart tranquillement*` :
                # au moins quatre mots, ET une ponctuation de fin de phrase quelque part.
                # Une didascalie de ces bots n'en a jamais.
                if (ouvre not in milieu and ferme not in milieu
                        and len(milieu.split()) >= 4
                        and any(c in milieu for c in ".!?…")):
                    phrase = milieu.strip()
        if phrase == avant:
            break
    phrase = strip_stage_directions(phrase)
    # ⚠️ UNE PHRASE QUI COMMENCE AU MILIEU EST CASSEE — on la REJETTE, on ne la repare pas.
    # Mesure du 2026-09-22, ministral : il met le nom du jeu en valeur, `*Elden Ring* vous
    # fait courir apres des ombres...`, et `strip_stage_directions` prend cette tete pour
    # une didascalie et la SUPPRIME. L'invitation partait alors sans son sujet — deux a
    # trois fois sur dix-huit. En MILIEU de phrase le meme nettoyeur se contente d'oter
    # les asterisques : c'est la POSITION qui decide, pas le contenu.
    # On ne tente pas de deviner ce qui a ete enleve ([[gotcha-nettoyeur-laisse-ce-qui-
    # rattachait]]) : on constate le degat sur le RESULTAT. Une invitation commence par
    # une majuscule ; si la premiere lettre est minuscule, il manque quelque chose devant,
    # que ce soit le nettoyeur ou le modele qui l'ait perdu. La seconde chance donne un
    # autre brouillon, et le gabarit fixe reste le plancher.
    premiere = next((c for c in phrase if c.isalpha()), "")
    if premiere and premiere.islower():
        return None
    if _RESSEMBLE_A_UN_LIEN.search(phrase):
        return None
    # Voir le bloc au-dessus du motif : une invitation ne parle que de sa destination.
    if _NOMME_LA_SOURCE.search(phrase):
        return None
    # Et elle n'invoque pas une conversation qui n'a jamais eu lieu.
    if _INVOQUE_UN_PASSE_COMMUN.search(phrase):
        return None
    # Ni ne prend son public pour cible.
    if _VISE_LE_PUBLIC.search(phrase):
        return None
    propre_au_bot = _VISE_LE_PUBLIC_PAR_BOT.get(bot_id or "")
    if propre_au_bot is not None and propre_au_bot.search(phrase):
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
            # ⚠️ ON DETECTE ET ON RANGE TOUJOURS, ON NE REPOND QUE SI C'EST COCHE.
            # Avant, la detection etait sous le `if enable_game_qa` — et comme ce reglage
            # est a False chez les SEPT bots (verifie le 22/09 dans `twitch_config.json`),
            # le journal ne pouvait rien enregistrer. Le cocher pour observer aurait
            # ALLUME la fonctionnalite, alors que ce journal a ete construit pour ne
            # jamais changer un comportement. D'ou la separation : `_question_de_jeu`
            # observe, `enable_game_qa` decide de la REPONSE.
            category = self._question_de_jeu(text, "mention")
            self._defaite_observee(text)
            if category and getattr(self, "enable_game_qa", False):
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

        # ⚠️ LE GROS DU CORPUS EST ICI. Sur un chat Twitch, les messages qui mentionnent
        # le bot sont une poignee ; tout le reste passe par cette branche. Ne journaliser
        # que les mentions remplirait ce journal aussi lentement que les trois decisions
        # d'avant — 30 lignes en deux jours — c'est-a-dire pas du tout.
        # ⚠️ Cet appel n'envoie RIEN et ne declenche RIEN : il lit le texte, range une
        # ligne, et rend une valeur dont la branche passive ne se sert pas. La reponse
        # co-host plus bas reste conditionnee a `enable_game_qa`, et REUTILISE cette
        # valeur — sans quoi un message de canal co-host serait compte deux fois.
        categorie_jeu = self._question_de_jeu(text, "passif")

        for t in getattr(self, "link_timers", []):
            if not hasattr(self, "_etat_timers"):
                self._etat_timers = {}
            etat = self._etat_timers.setdefault((chan_lower, t["cmd"]),
                                                {"depuis": time.time(), "msgs": 0})
            etat["msgs"] += 1

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
                category = categorie_jeu      # deja detecte et range plus haut
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

        # Option A.3 : annonce automatique d'un lien (reglee dans le dashboard, 23/09)
        if not spontaneous_sent and getattr(self, "link_timers", None):
            spontaneous_sent = await self._try_link_timer(chan, ws)

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
                jeton = _CANAL_COURANT.set(chan)
                try:
                    if asyncio.iscoroutinefunction(callback):
                        res = await callback(author, args)
                    else:
                        res = callback(author, args)
                finally:
                    _CANAL_COURANT.reset(jeton)
                
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

    async def _try_link_timer(self, chan: str, ws) -> bool:
        """Poste un lien regle en « auto » dans le dashboard, si son heure est venue.

        Trois conditions : l'intervalle, le nombre de messages depuis la derniere annonce,
        et le DIRECT (hors live, le chat d'une chaine ne doit pas recevoir de pub). Le
        texte est celui de la commande elle-meme : meme callback, meme cache.
        """
        now = time.time()
        chan_lower = chan.lower()
        for t in getattr(self, "link_timers", []):
            etat = getattr(self, "_etat_timers", {}).get((chan_lower, t["cmd"]))
            if not etat or now - etat["depuis"] < t["every"] or etat["msgs"] < t["min_msgs"]:
                continue
            if not await self._canal_en_direct(chan_lower):
                return False
            while self.global_msg_timestamps and now - self.global_msg_timestamps[0] > 30.0:
                self.global_msg_timestamps.popleft()
            if len(self.global_msg_timestamps) >= 14:
                return False
            jeton = _CANAL_COURANT.set(chan)
            try:
                cb = t["callback"]
                res = await cb("timer", "") if asyncio.iscoroutinefunction(cb) else cb("timer", "")
            except Exception as e:
                self.logger.error(f"❌ [TWITCH_CHAT:{self.bot_id}] annonce auto !{t['cmd']} : {e}")
                return False
            finally:
                _CANAL_COURANT.reset(jeton)
            etat["depuis"], etat["msgs"] = now, 0
            if not res:
                return False
            self.global_msg_timestamps.append(now)
            self.logger.info(f"⏰ [TWITCH_CHAT:{self.bot_id}] Annonce auto !{t['cmd']} sur #{chan_lower}")
            await send_chat_safe(ws, chan, res, bot_id=self.bot_id, logger=self.logger)
            return True
        return False

    async def _canal_en_direct(self, chan: str) -> bool:
        """Vrai si CE canal est en direct. Faux au moindre doute (pas d'identifiants, erreur)."""
        if not getattr(self, "client_id", None) or not getattr(self, "client_secret", None):
            return False
        try:
            from shared.twitch.game_info import HelixClient
            if getattr(self, "_helix_client", None) is None:
                self._helix_client = HelixClient(self.client_id, self.client_secret)
            nom, _ = await self._helix_client.get_current_game(chan, live_only=True)
            return nom is not None
        except Exception as e:
            # HelixClient ou réseau indisponible : on considère hors-ligne par sécurité
            self.logger.debug(f"[TWITCH_CHAT:{self.bot_id}] direct indisponible pour #{chan} : {e}")
            return False

    # Clauses ajoutees a l'instruction POUR UN SEUL BOT. Vide par defaut : un bot absent
    # de cette table recoit exactement le texte commun, inchange.
    #
    # ⚠️ Pourquoi par bot et pas dans le texte commun : la mesure du 2026-09-21 (detaillee
    # dans `_generate_link_line`) montre que cette clause fait passer Sugar de 4 objets
    # inventes sur 6 a ZERO, et qu'elle EFFONDRE les ouvertures de M'aiq (5/5 sur la meme
    # formule). Ajouter un bot ici demande donc de mesurer ce bot-la, pas de supposer.
    #
    # ⚠️ LES DEUX QUI N'EN ONT PAS, ET C'EST MESURE — ne pas retenter sans raison neuve.
    # Balayage du 2026-09-22 sur ministral (Gemini rendait 503), 18 generations par bras,
    # chaque bot dans son etat de prod :
    #
    #     MALENA   objets 11/18 sans clause -> 7/18 avec une clause qui NOMME ses objets
    #              **p = 0,32 : aucun effet**. La meme forme donne pourtant 12/17 -> 1/17
    #              chez Alfred et 12/18 -> 5/18 chez Sheogorath. 3e demonstration du jour
    #              que [[gotcha-un-filet-ne-se-transpose-pas-d-un-bot-a-l-autre]].
    #              ⚠️ Son vrai defaut est ailleurs et il est DEJA TRANCHE : « Oh ma vie »
    #              ouvre **16 phrases sur 18** ici, ce qui confirme les 82 % mesures sous
    #              ministral contre 13 % sous flash-lite, fiche identique. C'est
    #              l'ECHELON, pas la fiche — decision `3cac596`, ne pas toucher sa fiche.
    #
    #     M'AIQ    objets **3/18 seulement** : il n'y a pas grand-chose a reparer, et son
    #              risque connu est l'effondrement des ouvertures (deja 11/18 sur « Les
    #              Plaines de... » ici). Le rapport gain/risque est contre la clause.
    #              ⚠️ ET ATTENTION AU FAUX DEFAUT : il « invente » un lieu pour la
    #              destination 17 fois sur 18 — « Les Plaines de l'Echo », « La Boite
    #              Magique ». Ce n'est PAS une invention : sa fiche le lui PRESCRIT
    #              (`maiq_data.py:52`, « 'Discord' n'existe pas »). Compter ca comme une
    #              faute reviendrait a lui retirer sa voix
    #              ([[gotcha-un-defaut-peut-etre-une-fonctionnalite]]).
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
        # ⚠️ MESURE DU 2026-09-22, SUR MINISTRAL (Groq rate-limite a 3-4 appels, et
        # ministral est justement son 2e echelon — celui qui le sert des que Groq refuse,
        # ce qui lui arrive souvent : il porte 18 des 21 refus du projet). Sheogorath
        # n'avait JAMAIS pu etre mesure depuis le 21/09. Trois bras, 18 generations :
        #
        #     bras                    accroche le jeu   PROMET un objet   INVITE encore
        #     A  rien (etat actuel)        0/18            12/18              18/18
        #     B  accroche au jeu          18/18             1/18               9/18  <-
        #     C  clause ci-dessous         1/18             5/18              17/18
        #
        # ▶ **B EST DISQUALIFIE, ET PAS POUR L'OBJET.** Le jeu repare l'objet invente
        # mieux que tout (12/18 -> 1/18, p = 0,0003) — mais il fait DISPARAITRE
        # L'INVITATION une fois sur deux (18/18 -> 9/18, p = 0,001), et concentre les
        # ouvertures sur « Ah, ces... » **13 fois sur 18**, pire que le 4/6 de M'aiq qui
        # l'avait exclu. Une invitation qui n'invite plus n'est pas une invitation.
        # ▶ C garde tout : objet 12/18 -> 5/18 (p = 0,044), invitation intacte (17/18),
        # et la variete AUGMENTE (12 ouvertures distinctes contre 10, la plus frequente
        # 4 fois contre 5). La longueur mediane tombe de 187 a 148 caracteres.
        # ⚠️ Comme pour Alfred, elle NOMME les objets : c'est la seule forme qui agisse.
        "sheogorath": (
            "⚠️ Tu n'offres RIEN qui les attendrait là-bas : ni fromage, ni papillon, ni "
            "chaise, ni festin. Tu n'as rien à leur servir et tu ne tiens aucun lieu. "
            "Ce qui les attend, c'est TOI : ta folie, ta voix, ce que tu vas leur dire. "
            "Ton fromage et tes papillons restent les TIENS, tu ne les promets pas dans "
            "la phrase. "
        ),

        # ⚠️ MESURE DU 2026-09-22, SUR MINISTRAL — et elle dit l'inverse de ce que la
        # fiche d'Alfred avait appris le meme jour. Sa fiche CITAIT le the ; la de-citer
        # a fait tomber l'objet invente de 6/18 a 1/22 SOUS FLASH-LITE (`2b4e7f1`). Mais
        # sous ministral, fiche de-citee, le the revient a **12/17**. Trois variantes,
        # 17 a 18 generations chacune, meme fiche, meme jeu, ministral partout :
        #
        #     A  sans clause ......................... 12/17 inventent un the
        #     B  clause ci-dessous, qui NOMME ........  1/17      p = 0,0002
        #     C  « rien de materiel », qui ne nomme .. 11/18      p = 0,72  (aucun effet)
        #
        # ▶ NOMMER L'OBJET NE MARCHE QUE DANS LA CLAUSE, PAS DANS LA FICHE. Dans la fiche,
        # le the cite en exemple entre dans son vocabulaire et ressort partout ; dans la
        # clause, au moment d'ecrire, le nommer l'ecarte. C'est la 2e mesure du meme
        # effet : la clause de Johnny nomme aussi ses bieres, et la version SANS exemple
        # y avait ete mesuree moins bonne. Nuance donc
        # [[gotcha-le-prompt-enseigne-le-tic-interdit]] : c'est la PLACE qui decide.
        # ⚠️ Prix mesure : l'ouverture la plus frequente passe de 5/17 a 7/17. Reel, mais
        # sans commune mesure avec les 4/4 qui ont disqualifie la clause de Sugar ailleurs.
        # ⚠️ NON MESUREE SOUS FLASH-LITE : Gemini rendait 503 ce jour-la. Sous flash-lite
        # le the est deja a 1/22 ; le risque n'est donc pas l'objet, c'est la VARIETE.
        # A remesurer des que Gemini repond.
        "alfred": (
            "⚠️ Tu n'offres RIEN qui les attendrait là-bas : ni thé, ni tasse, ni siège, "
            "ni service. Tu n'as rien à leur servir et tu ne tiens aucune maison là-bas. "
            "Ce qui les attend, c'est toi : ta voix et tes remarques. Ton service reste "
            "le TIEN, tu ne le proposes pas dans la phrase. "
        ),
        "johnny": (
            "⚠️ Tu ne promets rien qui les attendrait là-bas : ni tournée, ni verre, ni "
            "place gardée — tu n'as rien à offrir et tu n'as jamais rien offert à "
            "personne. Ce qui les attend, c'est toi : ta gueule, tes histoires, ce que tu "
            "vas leur balancer. Tes clopes et ton whisky restent les TIENS, tu ne les "
            "partages pas dans la phrase. "
        ),
    }

    # Bots dont la phrase de lien s'accroche au JEU diffuse sur le stream (demande
    # d'Ahmed le 2026-09-21). Sans jeu — hors live, ou categorie « Just Chatting » —
    # l'instruction ne bouge pas d'une virgule et l'invitation reste la normale.
    # ⚠️ Meme regle que CLAUSES_PAR_BOT : on n'ajoute un bot ici qu'apres l'avoir mesure.
    # Un fait VRAI n'est pas une clause de style, mais il allonge quand meme l'instruction,
    # et une instruction plus longue effondre certains modeles (mesure du jour sur M'aiq).
    #
    # Mesure du 2026-09-22, jeu = Elden Ring, 6 generations par bot, chacun sur SA tete :
    #
    #     sugar    6/6 accrochent, 0/6 objet invente (contre 4/6 sans jeu)      LIVRE
    #     alfred   6/6 accrochent, 1/6 objet (contre 3/4), et ZERO « demeure »  LIVRE
    #     malena   6/6 accrochent, 0/6 objet, sa voix intacte                   LIVRE
    #     maiq     6/6 accrochent, mais 4/6 ouvrent sur la MEME formule, et les
    #              objets ne bougent pas (2/6) — rien a gagner                  non livre
    #     johnny   6/6 accrochent. Il enrobe 5 repliques sur 6 de `*"..."*`, ce
    #              qui les faisait JETER par le nettoyeur — corrige le 2026-09-22 :
    #              l'emballage est desormais deballe, pas jete                  LIVRE
    #     sheo     2 generations exploitables sur 6 (429 Groq) : pas mesure     non livre
    ACCROCHE_AU_JEU = {"sugar", "alfred", "malena", "johnny"}

    # Clauses ajoutees POUR UN SEUL BOT, et SEULEMENT quand un jeu est diffuse : elles
    # parlent de « ce jeu », et hors live elles n'auraient pas de sens.
    #
    # ⚠️ SUGAR — demande d'Ahmed le 2026-09-23 : qu'elle interroge les lecteurs sur LEUR
    # experience du jeu (« Vous galerez autant en Boheme que Henry ? venez nous partager
    # ca »). Sans exemple dans le texte : une formule citee devient un tic.
    # Premiere version mesuree le 23/09 (KCD2 + fiche, n=18, Gemini) :
    #     question aux lecteurs + invitation ... ~13/18   (contre ~0 sans)
    #     contenu du Discord invente ..........   0/18   (contre 3/18)
    #     longueur mediane ....................  176 car. (contre 112)  <- REFUSE
    #     au-dela de 120 car. .................  17/18
    # Elle demandait « une question PUIS une invitation » : le modele collait deux
    # phrases. Cette version-ci exige que les deux tiennent dans UNE phrase courte.
    CLAUSES_JEU_PAR_BOT = {
        "sugar": (
            "⚠️ Adresse-toi à ceux qui LISENT, pas au personnage du jeu : ta phrase est "
            "UNE question sur ce que CE JEU leur a fait vivre, à eux, quand ils y ont "
            "joué — jamais sur la partie en cours, jamais une pique sur eux — et cette "
            "même question les invite à venir le raconter sur le serveur Discord. Question et invitation "
            "tiennent dans la MÊME phrase, sous les 120 caractères : pas de mise en scène "
            "avant, pas de seconde phrase après. "
        ),
    }

    def _canal_du_jeu(self) -> str | None:
        """Le canal d'ou vient la commande en cours ; a defaut, le premier configure."""
        courant = _CANAL_COURANT.get()
        if courant:
            return courant.lower().lstrip("#")
        canaux = getattr(self, "channels", None) or []
        return canaux[0] if canaux else None

    async def _jeu_en_cours(self) -> str | None:
        """Le jeu diffuse sur le canal du bot, ou None. Ne leve jamais.

        ⚠️ `HelixClient.get_current_game` a son propre cache : appeler ceci a chaque
        `!discord` ne coute pas un appel Twitch a chaque fois.

        Le canal retenu est celui d'ou vient la commande (`_canal_du_jeu`). Sans canal,
        sans identifiants, ou au moindre incident : None — l'invitation normale sort, ce
        qui est exactement le repli demande.
        """
        chan = self._canal_du_jeu()
        if not chan or not getattr(self, "client_id", None) or not getattr(self, "client_secret", None):
            return None
        try:
            from shared.twitch.game_info import HelixClient
            if getattr(self, "_helix_client", None) is None:
                self._helix_client = HelixClient(self.client_id, self.client_secret)
            # ⚠️ `live_only=True` : hors direct, `helix/channels` rend toujours la
            # derniere categorie de la chaine, et l'invitation parlerait du jeu d'hier.
            # « Le stream est termine » -> pas de jeu -> annonce normale, comme demande.
            nom, _ = await self._helix_client.get_current_game(chan, live_only=True)
            nom = (nom or "").strip()
            # « Just Chatting » et consorts ne sont pas des jeux : s'y accrocher ferait
            # dire au bot n'importe quoi. Hors de cette liste, on fait confiance a Twitch.
            if nom.lower() in {"just chatting", "talk shows & podcasts", "special events",
                               "music", "art", ""}:
                return None
            return nom
        except Exception as e:
            self.logger.debug(f"[TWITCH_CHAT:{self.bot_id}] jeu en cours indisponible : {e}")
            return None

    async def _fiche_du_jeu(self) -> str | None:
        """Fiche courte IGDB du jeu en cours, ou None. Ne lève jamais, borne 3 s."""
        chan = self._canal_du_jeu()
        if not chan or not getattr(self, "client_id", None) or not getattr(self, "client_secret", None):
            return None
        try:
            async def _recuperer():
                from shared.twitch.game_info import HelixClient, IGDBClient, fiche_courte
                if getattr(self, "_helix_client", None) is None:
                    self._helix_client = HelixClient(self.client_id, self.client_secret)
                nom, game_id = await self._helix_client.get_current_game(chan, live_only=True)
                if not game_id:
                    return None
                igdb_id = await self._helix_client.get_igdb_id(game_id)
                if not igdb_id:
                    return None
                if getattr(self, "_igdb_client", None) is None:
                    self._igdb_client = IGDBClient(self.client_id, self.client_secret)
                game = await self._igdb_client.get_game_by_id(igdb_id)
                if not game:
                    return None
                return fiche_courte(game)

            return await asyncio.wait_for(_recuperer(), timeout=3.0)
        except Exception as e:
            self.logger.debug(f"[TWITCH_CHAT:{self.bot_id}] fiche du jeu indisponible : {e}")
            return None

    def _question_de_jeu(self, texte, voie):
        """La categorie de question sur le jeu, et on RANGE la decision au passage.

        ⚠️ Cette methode ne DECIDE rien de nouveau : `detect_game_question` tranche
        exactement comme avant, et son resultat sort tel quel. Elle ne fait qu'observer.

        Pourquoi la journaliser, elle : c'est la seule decision a mots-cles du depot qui
        se declenche souvent. Les trois deja instrumentees (intention, ton, pertinence)
        n'ont produit que 30 lignes en deux jours, dont ZERO pour `intention` — de quoi
        ne mesurer rien du tout. Celle-ci tourne sur le chat Twitch.

        ⚠️ Le cas `None` est journalise AUSSI, sous l'etiquette `aucune`, et c'est le
        plus important : le defaut probable de 66 motifs regex n'est pas de se tromper
        de categorie, c'est de RATER une question posee autrement. Un journal qui ne
        garderait que les detections ne pourrait jamais montrer ce manque-la.
        """
        from shared.twitch.game_info import detect_game_question
        categorie = detect_game_question(texte)
        try:
            from shared.journal_decisions import journalise, JEU_QUESTION
            journalise(self.bot_id, JEU_QUESTION, texte, categorie or "aucune",
                       detail=f"voie={voie}")
        except Exception as e:
            # Un journal ne doit jamais couter une reponse : s'il casse, le bot continue.
            self.logger.debug(f"[TWITCH_CHAT:{self.bot_id}] journal jeu_question : {e}")
        return categorie

    def _defaite_observee(self, texte):
        """Le bot a-t-il ete declare battu ? On RANGE la reponse, on n'en fait RIEN.

        ⚠️ Sur Twitch, le carnet de repartie n'existe pas : les bots n'y apprennent rien
        et n'y appliquent aucune lecon. C'est pourtant la qu'il y a du monde. Avant de
        l'y brancher — un troll qui ecrit « je t'ai eu » ferait reflechir le bot sur sa
        persona — on mesure combien de defaites y sont declarees, et combien la liste
        de motifs en rate (`aucune` est rangee aussi). Ne declenche aucune reflexion,
        n'envoie rien, et un journal qui casse ne coute pas la reponse.
        """
        try:
            from shared.repartee_lessons import detect_defeat_signal
            return detect_defeat_signal(texte, bot_id=self.bot_id, detail="voie=twitch")
        except Exception as e:
            self.logger.debug(f"[TWITCH_CHAT:{self.bot_id}] journal defaite : {e}")
            return None

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
        jeu = await self._jeu_en_cours() if self.bot_id in self.ACCROCHE_AU_JEU else None
        # ⚠️ Le jeu fait partie de la CLE du cache : sans ca, un changement de jeu en
        # cours de live laisserait tourner pendant un quart d'heure une invitation qui
        # parle du precedent — pire qu'une invitation neutre.
        cle_cache = (cmd, jeu)
        vue = cache.get(cle_cache)
        if vue and maintenant - vue[0] < 900:
            return f"{vue[1]} {url}"
        # APRES le cache, jamais avant : un echec IGDB n'est pas mis en cache, et chaque
        # `!discord` servi depuis le cache aurait paye jusqu'a 3 s d'attente pour rien.
        fiche = await self._fiche_du_jeu() if jeu else None

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
        # ⚠️ MESURES SUITE 2 & SUITE 2-bis (2026-09-26) : « là-bas » éliminé de l'instruction.
        # Remplacement dans CLAUSES_JEU_PAR_BOT["sugar"] ET dans le texte commun ci-dessous
        # (l.1100 « du serveur Discord », l.1124 « sur le serveur »).
        # Tableau mesuré sur les six bots (18 tirages par cellule, 216 au total, jeu Kingdom Come II) :
        #   Sugar (Gemini)      : là-bas ambigu 9/18 -> 2/18, destination 0/18 -> 10/18, replis 0/18 -> 0/18
        #   Alfred (Gemini)     : destination 18/18, 0 là-bas, replis 0/18 -> 0/18
        #   Malena (Gemini)     : destination 18/18 -> 16/16 (2 replis chat), 2 là-bas (Bohême)
        #   M'aiq (Gemini)      : Discord nommé 0/18 (règle préservée), 0 là-bas, replis 0/18 -> 0/18
        #   Johnny (Mistral)    : replis 3/18 -> 1/18, destination 2/18 -> 3/17, 0 là-bas
        #   Sheogorath (Mistral): là-bas 3/18 -> 1/18, destination 0/18 -> 1/18, replis 0/18 -> 0/18
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
            f"Ta phrase ne parle que du serveur Discord. L'endroit d'où tu écris n'y apparaît pas : "
            f"tu ne le décris pas, tu ne le juges pas, et tu ne compares jamais les deux. "
            f"Tu peux finir par UN emoji, s'il colle à ton personnage. "
            f"N'ÉCRIS PAS l'adresse ni aucun lien : elle sera ajoutée juste après ta phrase. "
            f"Pas de guillemets, pas de didascalie."
        )
        # ⚠️ La clause par bot s'insere AVANT la fin du texte commun serait plus propre,
        # mais l'ordre ne change rien a la mesure : elle est ajoutee ici, et un bot absent
        # de la table ne voit aucune difference.
        instruction += " " + self.CLAUSES_PAR_BOT.get(self.bot_id, "")
        if jeu:
            # ⚠️ Le jeu est la SEULE chose vraie qu'on puisse lui donner sur le moment
            # present — et c'est justement ce qui manquait a cette phrase depuis le 19/09
            # (cf. le bloc plus haut : prive de tout fait, le modele en invente un).
            # On lui donne donc le nom, et on borne aussitot ce qu'il peut en dire : le
            # nom est vrai, tout le reste serait devine.
            instruction += (
                f" ⚠️ En ce moment, le chat regarde quelqu'un jouer à « {jeu} ». Ta phrase "
                f"DIT quelque chose de ce jeu : une comparaison, un constat qui fait "
                f"sourire celui qui y joue, une pique sur ce que le JEU fait subir — "
                f"jamais sur ceux qui regardent, jamais sur leur chat. Le nommer ne "
                f"suffit pas, et citer son héros non plus — un nom n'est pas une remarque. "
                f"Mais tu ne sais RIEN de la partie en cours — ni qui gagne, ni où ils en "
                f"sont, ni ce qui vient de se passer : n'en raconte pas un moment, et ne "
                f"promets pas qu'on en parlera sur le serveur. "
            )
            if fiche:
                instruction += (
                    f"Voici la fiche officielle de ce jeu (en anglais) : {_fiche_sans_epoque(fiche)}. "
                    f"C'est TOUT ce que tu sais de vrai sur lui : inspire-t'en, mais n'affirme rien qui n'y figure pas. "
                )
            instruction += self.CLAUSES_JEU_PAR_BOT.get(self.bot_id, "")
            instruction += (
                "⚠️ Et ta phrase doit CLAQUER : une seule idée, la chute à la fin, rien "
                "avant qui la retarde. Si elle ne fait pas sourire à la lecture, recommence."
            )

        # ⚠️ DEUX ESSAIS, ET PAS PLUS. Les filets ci-dessus REJETTENT au lieu de reparer :
        # sans seconde chance, une faute au tirage coutait le gabarit fixe, et la mesure du
        # 2026-09-22 en donne une sur quatre (2 generations sur 8 visaient le chat). Un
        # second appel ramene ce risque a ~6 %, pour ~1,4 s de plus — la mediane mesuree de
        # flash-lite le soir meme. On s'arrete la : quelqu'un attend devant son chat, et
        # trois appels feraient du gabarit fixe le choix le plus RAPIDE, ce qui serait
        # absurde.
        texte = None
        for essai in (1, 2):
            texte = await self._ecrire_phrase_de_lien(instruction, system_prompt, cmd)
            if texte is None:
                return None          # panne franche : le gabarit fixe, tout de suite
            phrase = _nettoyer_phrase_de_lien(texte, self.bot_id)
            if phrase and _affirme_une_epoque(phrase, jeu, fiche):
                phrase = None
            if phrase:
                break
            self.logger.info(
                f"🔁 [TWITCH_CHAT:{self.bot_id}] Phrase de lien !{cmd} rejetee par les "
                f"filets (essai {essai}/2) : « {' '.join(str(texte).split())[:90]} »"
            )
        else:
            return None

        cache[cle_cache] = (maintenant, phrase)
        self.logger.info(
            f"✨ [TWITCH_CHAT:{self.bot_id}] Phrase de lien !{cmd}"
            + (f" (jeu : {jeu})" if jeu else "")
            + f" écrite par le bot : {phrase}"
        )
        return f"{phrase} {url}"

    async def _ecrire_phrase_de_lien(self, instruction, system_prompt, cmd):
        """Un appel au modele. Rend le texte brut, ou None si l'appel a echoue."""
        try:
            from shared.llm_cascade import generate_response
            from shared.smart_router import classify_request
            try:
                routing = classify_request(instruction)
            except Exception:
                routing = {"type": "text"}

            return await generate_response(
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
