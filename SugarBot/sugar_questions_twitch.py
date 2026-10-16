"""Gestion des questions posées à la streameuse sur Twitch (SUITE 21).

Sugar observe le chat Twitch en lecture seule, repère les questions posées
à la streameuse (heuristiques + tri LLM au moment de la demande), et les
envoie en MP sur Discord aux modérateurs / à la streameuse.
"""
import json
import logging
import os
import re
import time

FENETRE_S = 12 * 3600          # la liste couvre les 12 dernieres heures
RETENTION_S = 48 * 3600        # au-dela, purge a chaque sauvegarde
MAX_ENTREES = 300              # plafond du fichier (les plus anciennes partent)
MAX_A_TRIER_PAR_APPEL = 40     # au-dela, les plus anciennes restent « a trier »
CONTEXTE_MAX = 4               # messages du salon gardes avant une question ambigue
TAILLE_PAGE = 1900             # un MP Discord plafonne a 2000

_MOTS_QUESTION_RE = re.compile(
    r"^(?:pourquoi|comment|quand|combien|quel|quelle|quels|quelles|"
    r"est[- ]ce|c['’]?est quoi|qu['’]?est[- ]ce|où|ou\s+est)\b",
    re.IGNORECASE,
)

_DEMANDE_RE = re.compile(r"\bquestions?\b", re.IGNORECASE)
_SUJET_RE = re.compile(r"twitch|live|strea?m|t?chat|view|vewer|spectat", re.IGNORECASE)

TABLE_VERDICTS = {
    "S": "streameuse",
    "B": "sugar",
    "V": "viewer",
    "A": "personne",
}


def _echapper(s: str) -> str:
    """Échappe le markdown Discord et neutralise les mentions @."""
    s = re.sub(r"([\\*_~`|>])", r"\\\1", s)
    s = s.replace("@", "@\u200b")
    return s


def est_une_question(texte: str) -> bool:
    """Détermine si un texte ressemble à une question."""
    if not texte:
        return False
    sans_mentions = re.sub(r"@\w+", "", texte).strip()
    nb_lettres = sum(1 for c in sans_mentions if c.isalpha())
    if nb_lettres < 8:
        return False
    if "?" in sans_mentions:
        return True
    return bool(_MOTS_QUESTION_RE.search(sans_mentions))


def destinataire_evident(chan: str, author: str, text: str, tags: dict | None, bot_login: str = "") -> str | None:
    """Identifie le destinataire évident d'une question ou indique s'il faut la trier."""
    streameuse = chan.lower().lstrip("#")
    aut = author.lower()
    if aut == streameuse or (bot_login and aut == bot_login.lower()):
        return None

    texte_propre = (text or "").strip()
    if not texte_propre or texte_propre.startswith("!"):
        return None

    if not est_une_question(texte_propre):
        return None

    parent = (tags or {}).get("reply-parent-user-login", "").lower()
    if parent:
        return "streameuse" if parent == streameuse else None

    m_pseudo = re.match(r"^@(\w+)", texte_propre)
    if m_pseudo:
        return "streameuse" if m_pseudo.group(1).lower() == streameuse else None

    if re.search(rf"@\b{re.escape(streameuse)}\b", texte_propre, re.IGNORECASE):
        return "streameuse"

    return "a_trier"


def demande_la_liste(texte: str, en_prive: bool) -> bool:
    """Détecte si un message demande la liste des questions Twitch."""
    if not texte or not _DEMANDE_RE.search(texte):
        return False
    if en_prive:
        return True
    return bool(_SUJET_RE.search(texte))


def peut_demander(guilds, user_id: int) -> bool:
    """Vérifie si l'utilisateur est propriétaire ou modo sur au moins un serveur."""
    if not guilds or not user_id:
        return False
    for guild in guilds:
        if getattr(guild, "owner_id", None) == user_id:
            return True
        get_member = getattr(guild, "get_member", None)
        member = get_member(user_id) if callable(get_member) else None
        if member:
            perms = getattr(member, "guild_permissions", None)
            if perms:
                if (getattr(perms, "administrator", False)
                        or getattr(perms, "manage_messages", False)
                        or getattr(perms, "moderate_members", False)):
                    return True
    return False


class QuestionsTwitch:
    """Magasin persistant des questions Twitch observées."""

    def __init__(self, chemin: str, logger: logging.Logger | None = None):
        self.chemin = chemin
        self.logger = logger
        self.entrees: list[dict] = []
        self.prochain_id: int = 1
        self._charger()

    def _charger(self) -> None:
        if not os.path.exists(self.chemin):
            self.entrees = []
            self.prochain_id = 1
            return
        try:
            with open(self.chemin, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.entrees = data.get("entrees", [])
            max_id = max([e.get("id", 0) for e in self.entrees], default=0)
            self.prochain_id = data.get("prochain_id", max_id + 1)
        except Exception as e:
            if self.logger:
                self.logger.warning(f"⚠️ [QUESTIONS] Impossible de charger {self.chemin}: {e}")
            self.entrees = []
            self.prochain_id = 1

    def _sauvegarder(self, maintenant: float | None = None) -> None:
        if maintenant is None:
            maintenant = time.time()
        # Purge des entrées au-delà de RETENTION_S
        self.entrees = [e for e in self.entrees if maintenant - e.get("ts", 0) <= RETENTION_S]
        if len(self.entrees) > MAX_ENTREES:
            self.entrees = self.entrees[-MAX_ENTREES:]

        dir_name = os.path.dirname(self.chemin)
        if dir_name and not os.path.exists(dir_name):
            os.makedirs(dir_name, exist_ok=True)

        tmp_path = self.chemin + ".tmp"
        data = {
            "version": 1,
            "prochain_id": self.prochain_id,
            "entrees": self.entrees,
        }
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.chemin)

    def observer(self, chan: str, author: str, text: str, tags: dict | None,
                 contexte: list[str] | None, bot_login: str = "") -> None:
        """Observe un message du chat Twitch et range une question si repérée."""
        dest = destinataire_evident(chan, author, text, tags, bot_login=bot_login)
        if dest is None:
            return

        clean_chan = chan.lower().lstrip("#")
        maintenant = time.time()
        texte_norm = " ".join(text.lower().split())

        for e in self.entrees:
            if (maintenant - e.get("ts", 0) <= FENETRE_S
                    and e.get("chan", "").lower() == clean_chan
                    and e.get("auteur", "").lower() == author.lower()
                    and " ".join(e.get("texte", "").lower().split()) == texte_norm):
                return

        texte_tronque = text[:300]
        entree = {
            "id": self.prochain_id,
            "ts": maintenant,
            "chan": clean_chan,
            "auteur": author,
            "texte": texte_tronque,
            "dest": dest,
        }
        if dest == "a_trier":
            contexte_tronque = [str(l)[:150] for l in (contexte or [])[-CONTEXTE_MAX:]]
            entree["contexte"] = contexte_tronque

        self.prochain_id += 1
        self.entrees.append(entree)
        self._sauvegarder(maintenant=maintenant)
        if self.logger:
            self.logger.info(
                f"❓ [QUESTIONS] Question rangée ({dest}) de {author} sur #{chan} : {text[:80]}"
            )

    async def rapport(self, appel_llm, bot_login: str = "", maintenant: float | None = None) -> list[str]:
        """Génère les pages du rapport de questions pour le MP Discord."""
        if maintenant is None:
            maintenant = time.time()
        else:
            maintenant = float(maintenant)

        # 1. Sélectionner les entrées de la FENETRE_S
        recents = [e for e in self.entrees if maintenant - e.get("ts", 0) <= FENETRE_S]
        a_trier = [e for e in recents if e.get("dest") == "a_trier"]

        k = 0
        if a_trier and appel_llm:
            selection = a_trier[-MAX_A_TRIER_PAR_APPEL:]
            # Groupement par chaîne (en pratique une seule)
            par_chaine: dict[str, list[dict]] = {}
            for q in selection:
                par_chaine.setdefault(q.get("chan", ""), []).append(q)

            verdicts: dict[int, str] = {}
            for ch, questions_chan in par_chaine.items():
                system_prompt = (
                    f"Tu tries des messages du chat Twitch de la chaîne « {ch} ». La streameuse est "
                    f"« {ch} » : elle parle à voix haute, ses paroles ne sont pas dans le chat. "
                    f"« {bot_login or 'le bot'} » est Sugar, un bot du chat. Les viewers appellent souvent la "
                    f"streameuse par un bout de son pseudo — y compris « Sugar », comme le bot : tranche avec "
                    f"le sens. Pour chaque message numéroté, dis à QUI la question s'adresse : "
                    f"S = la streameuse ; B = le bot Sugar ; V = un autre viewer ; "
                    f"A = personne (réaction, question rhétorique, pas vraiment une question). "
                    f"Une question posée au chat sans destinataire, sur la streameuse, son live, ses jeux "
                    f"ou sa vie, est pour elle : S. "
                    f"Réponds une ligne par message, au format numéro:lettre, et rien d'autre."
                )

                lignes_user = []
                for q in questions_chan:
                    ctx = q.get("contexte") or []
                    lignes_user.append(f"#{q['id']} — contexte juste avant :")
                    for c in ctx:
                        lignes_user.append(f"  {c}")
                    lignes_user.append(f"{q['auteur']} : {q['texte']}")
                user_message = "\n".join(lignes_user)

                reponse = None
                try:
                    reponse = await appel_llm(system_prompt, user_message)
                except Exception as e:
                    if self.logger:
                        self.logger.warning(f"⚠️ [QUESTIONS] Erreur appel LLM tri: {e}")
                    reponse = None

                if reponse and isinstance(reponse, str):
                    for ligne in reponse.splitlines():
                        m = re.match(r"^\s*#?\s*(\d+)\s*[:=\-–]\s*([SBVA])\b", ligne, re.IGNORECASE)
                        if m:
                            qid = int(m.group(1))
                            lettre = m.group(2).upper()
                            if lettre in TABLE_VERDICTS:
                                verdicts[qid] = TABLE_VERDICTS[lettre]

            if verdicts:
                id_map = {e["id"]: e for e in self.entrees if "id" in e}
                for qid, nouveau_dest in verdicts.items():
                    if qid in id_map and id_map[qid].get("dest") == "a_trier":
                        id_map[qid]["dest"] = nouveau_dest
                        k += 1
                if k > 0:
                    self._sauvegarder(maintenant=maintenant)

        # 5. Construire le texte depuis self.entrees
        recents_apres = [e for e in self.entrees if maintenant - e.get("ts", 0) <= FENETRE_S]
        streameuses = [e for e in recents_apres if e.get("dest") == "streameuse"]
        non_triees = [e for e in recents_apres if e.get("dest") == "a_trier"]

        n = len(streameuses)
        r = len(non_triees)

        if n == 0 and r == 0:
            if self.logger:
                self.logger.info(f"📋 [QUESTIONS] Liste : 0 pour la streameuse, {k} triée(s) par l'IA, 0 non triée(s)")
            return ["Aucune question pour la streameuse sur les 12 dernières heures."]

        # Grouper par chaîne (la plus fournie d'abord)
        toutes_pertinentes = streameuses + non_triees
        chaines = set(e.get("chan", "") for e in toutes_pertinentes)
        compte = {ch: sum(1 for e in toutes_pertinentes if e.get("chan", "") == ch) for ch in chaines}
        chaines_triees = sorted(chaines, key=lambda ch: compte[ch], reverse=True)

        toutes_lignes: list[str] = []
        for ch in chaines_triees:
            ch_streameuse = sorted([e for e in streameuses if e.get("chan", "") == ch], key=lambda e: e.get("ts", 0))
            ch_non_triees = sorted([e for e in non_triees if e.get("chan", "") == ch], key=lambda e: e.get("ts", 0))

            toutes_lignes.append(f"**❓ Questions pour {ch}** — 12 dernières heures ({len(ch_streameuse)})")
            for e in ch_streameuse:
                toutes_lignes.append(f"<t:{int(e['ts'])}:t> **{_echapper(e['auteur'])}** : {_echapper(e['texte'])}")

            if ch_non_triees:
                toutes_lignes.append(f"**Pas sûre du destinataire** ({len(ch_non_triees)})")
                for e in ch_non_triees:
                    toutes_lignes.append(f"<t:{int(e['ts'])}:t> **{_echapper(e['auteur'])}** : {_echapper(e['texte'])}")

        # 6. Découper en pages <= TAILLE_PAGE sans jamais couper une ligne
        pages: list[str] = []
        page_courante: list[str] = []
        longueur_courante = 0

        for ligne in toutes_lignes:
            supplement = len(ligne) + (1 if page_courante else 0)
            if page_courante and (longueur_courante + supplement > TAILLE_PAGE):
                pages.append("\n".join(page_courante))
                page_courante = [ligne]
                longueur_courante = len(ligne)
            else:
                page_courante.append(ligne)
                longueur_courante += supplement

        if page_courante:
            pages.append("\n".join(page_courante))

        if self.logger:
            self.logger.info(f"📋 [QUESTIONS] Liste : {n} pour la streameuse, {k} triée(s) par l'IA, {r} non triée(s)")

        return pages
