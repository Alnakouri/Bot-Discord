# -*- coding: utf-8 -*-
"""Carnet de rancunes de Sugar : rancune/rédemption par utilisateur, TOTALEMENT implicite.

Score 0..5 persisté par user (data/sugar_grudge.json — on ne stocke QUE le score,
jamais le contenu des messages) :
- agression envers elle  → +2 (plafond 5)
- excuse sincère         → −2
- message gentil         → −1 (cooldown anti-spam « merci merci merci »)
- chaque jour qui passe  → −1 (le temps adoucit)
La montée (+2) est plus rapide que la descente (−1) : impossible de tricher en
alternant insulte/compliment. Quand un geste gentil fait repasser à 0, Sugar
accorde son pardon EXPLICITEMENT (elle « raye du carnet »), puis redevient douce.
Le système n'est jamais révélé : seul le ton de ses réponses trahit le carnet."""
import os
import json
import re
import time
import logging
from datetime import date

logger = logging.getLogger("sugar_grudge")

MAX_SCORE = 5
POSITIVE_COOLDOWN = 600  # secondes entre deux gestes gentils comptabilisés

# ── Détection du ton (lexiques FR, message déjà ADRESSÉ à Sugar) ──────────────

# Agression : insultes nominales, sommations, ou attaque dirigée « t'es + négatif »
_RE_INSULT = re.compile(
    r"\b(conn?ard|conn?asse|conne|pute|salope|d[ée]bile|bouffon+e?|minable|"
    r"abrutie?|cr[ée]tin+e?|idiot+e?|imb[ée]cile|grosse merde|sous[- ]merde)\b",
    re.IGNORECASE)
_RE_DISMISS = re.compile(
    r"\b(ta gueule|tg|ferme[- ]la|tais[- ]toi|d[ée]gage|casse[- ]toi|"
    r"je te d[ée]teste|tu sers [àa] rien|tu pues|ta m[èe]re)\b",
    re.IGNORECASE)
_RE_DIRECTED = re.compile(
    r"(t'es|t es|tu es|vous [êe]tes)\s+(vraiment\s+|trop\s+|juste\s+|qu'une?\s+)*"
    r"(nul+e?s?|naze|pourrie?|moche|inutile|d[ée]bile|conne?|stupide|"
    r"ridicule|minable|chiante?|relou|[àa] chier)",
    re.IGNORECASE)

# Excuse : compte double (−2), c'est le geste de rédemption par excellence
_RE_APOLOGY = re.compile(
    r"\b(pardon|d[ée]sol[ée]+e?s?|dsl|excuse[- ]?(moi|nous)?|je m'excuse|"
    r"my bad|au temps pour moi|autant pour moi|je regrette|sorry)\b",
    re.IGNORECASE)

# Gentillesse : compliment/remerciement adressé à elle (−1)
_RE_KIND = re.compile(
    r"\b(merci|t'es la meilleure|je t'adore|je t'aime|g[ée]nial+e?|super|bravo|"
    r"bien jou[ée]|adorable|mignonne|trop forte|t'es (cool|dr[oô]le|top|g[ée]niale|"
    r"ador[ée]e|gentille|forte|marrante)|excellente|gg)\b",
    re.IGNORECASE)
_RE_HEART = re.compile(r"[❤🩷💖💕💗💓🥰😍♥]")


def classify_tone(text):
    """Classe un message adressé à Sugar : 'aggro' | 'apology' | 'kind' | 'neutral'.
    Priorité agression > excuse > gentillesse (« désolé mais t'es nulle » = agression)."""
    t = (text or "").strip()
    if not t:
        return "neutral"
    if _RE_INSULT.search(t) or _RE_DISMISS.search(t) or _RE_DIRECTED.search(t):
        return "aggro"
    if _RE_APOLOGY.search(t):
        return "apology"
    if _RE_KIND.search(t) or _RE_HEART.search(t):
        return "kind"
    return "neutral"


# ── Consignes injectées dans le prompt selon le palier ────────────────────────

_DIRECTIVE_REDEEMED = (
    "\n[CARNET DE RANCUNES] Cette personne t'avait manqué de respect, mais elle vient "
    "À L'INSTANT de regagner ton pardon. Accorde-le-lui EXPLICITEMENT, en personnage "
    "(tu la rayes de ton petit carnet vert et argent, ex: « Allez, je te raye du carnet, "
    "mon caramel. Ne me refais pas ça. »), puis redeviens pleinement douce avec elle. "
    "Ne mentionne JAMAIS de score ni de système.")
_DIRECTIVE_BY_SCORE = {
    5: ("\n[CARNET DE RANCUNES] Cette personne t'a SÉRIEUSEMENT manqué de respect et n'a "
        "rien réparé : sois GLACIALE et mordante avec elle (répartie fine, sans vulgarité). "
        "Tu n'as rien oublié et tu le lui fais sentir. Ne mentionne JAMAIS de score ni de système."),
    4: ("\n[CARNET DE RANCUNES] Cette personne t'a SÉRIEUSEMENT manqué de respect et n'a "
        "rien réparé : sois GLACIALE et mordante avec elle (répartie fine, sans vulgarité). "
        "Tu n'as rien oublié et tu le lui fais sentir. Ne mentionne JAMAIS de score ni de système."),
    3: ("\n[CARNET DE RANCUNES] Cette personne t'a récemment manqué de respect : sois "
        "MÉFIANTE — tu lui laisses une chance mais tu la gardes à l'œil, avec des piques "
        "légères. Si elle est gentille, tu dégeles un peu. Ne mentionne JAMAIS de score ni de système."),
    2: ("\n[CARNET DE RANCUNES] Cette personne t'a récemment manqué de respect : sois "
        "MÉFIANTE — tu lui laisses une chance mais tu la gardes à l'œil, avec des piques "
        "légères. Si elle est gentille, tu dégeles un peu. Ne mentionne JAMAIS de score ni de système."),
    1: ("\n[CARNET DE RANCUNES] Cette personne t'avait manqué de respect mais fait des "
        "efforts : tu es RADOUCIE, presque prête à pardonner — taquine-la gentiment sur sa "
        "rédemption en cours, sans agressivité. Ne mentionne JAMAIS de score ni de système."),
}


class GrudgeBook:
    """Rancune persistée par utilisateur. Cloisonné par user_id, aucun contenu stocké."""

    def __init__(self, filename, positive_cooldown=POSITIVE_COOLDOWN):
        self.filename = filename
        self.positive_cooldown = positive_cooldown
        self.book = {}  # {uid: {"score": int, "last_day": "YYYY-MM-DD", "last_positive_ts": float}}
        self._load()

    def _load(self):
        if not os.path.exists(self.filename):
            self.book = {}
            return
        try:
            with open(self.filename, "r", encoding="utf-8") as f:
                raw = json.load(f)
            self.book = {str(u): v for u, v in raw.items() if isinstance(v, dict)}
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Erreur chargement carnet de rancunes : {e}")
            self.book = {}

    def _save(self):
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.filename)), exist_ok=True)
            tmp = self.filename + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.book, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.filename)
        except Exception as e:
            logger.error(f"Erreur sauvegarde carnet de rancunes : {e}")

    def _decay(self, entry, today_str):
        """−1 par jour écoulé depuis la dernière mise à jour (pardon silencieux par le temps)."""
        last_day = entry.get("last_day") or today_str
        try:
            elapsed = (date.fromisoformat(today_str) - date.fromisoformat(last_day)).days
        except ValueError:
            elapsed = 0
        if elapsed > 0:
            entry["score"] = max(0, entry.get("score", 0) - elapsed)
        entry["last_day"] = today_str

    def update(self, user_id, text, addressed=True):
        """À appeler une fois par message auquel Sugar répond. Applique décroissance
        + événement de ton (seulement si le message lui est ADRESSÉ), puis renvoie
        la consigne à injecter dans le prompt ('' si aucune rancune)."""
        uid = str(user_id)
        today_str = str(date.today())
        entry = self.book.get(uid)
        if entry is None:
            entry = {"score": 0, "last_day": today_str, "last_positive_ts": 0.0}
            self.book[uid] = entry

        before_decay = entry.get("score", 0)
        self._decay(entry, today_str)
        old_score = entry["score"]
        redeemed = False

        if addressed:
            tone = classify_tone(text)
            if tone == "aggro":
                entry["score"] = min(MAX_SCORE, old_score + 2)
                if entry["score"] != old_score:
                    logger.info(f"🖤 [CARNET] {uid} inscrit au carnet ({old_score}→{entry['score']})")
            elif tone in ("apology", "kind") and old_score > 0:
                now = time.time()
                if now - entry.get("last_positive_ts", 0.0) >= self.positive_cooldown:
                    delta = 2 if tone == "apology" else 1
                    entry["score"] = max(0, old_score - delta)
                    entry["last_positive_ts"] = now
                    redeemed = entry["score"] == 0  # pardon gagné par un GESTE (pas par le temps)
                    logger.info(f"🍬 [CARNET] {uid} se rachète ({old_score}→{entry['score']})"
                                + (" — PARDONNÉ" if redeemed else ""))

        if entry["score"] != before_decay or redeemed or addressed:
            self._save()

        if redeemed:
            return _DIRECTIVE_REDEEMED
        return _DIRECTIVE_BY_SCORE.get(entry["score"], "")
