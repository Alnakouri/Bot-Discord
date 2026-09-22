# -*- coding: utf-8 -*-
"""Journal des DECISIONS que les bots prennent avant d'appeler un modele.

POURQUOI CE MODULE EXISTE
-------------------------
Les bots decident de trois choses avec des listes de mots-cles et des des, AVANT tout
appel LLM : ce qu'on leur demande quand on les interpelle, le ton du message, et s'il
faut intervenir spontanement. Personne ne sait a quelle FREQUENCE ces regles se
trompent — et sans ce chiffre, remplacer une regex par autre chose est un pari.

Mesure du 2026-09-20 : le depot ne garde AUCUN texte de message.
`data/bots_database.db` stocke `user_id + type + horodatage`, `api_usage.db` des durees,
et les rapports d'eval ne contiennent que **18 messages distincts**. Il n'existe donc
aujourd'hui aucun corpus pour mesurer le defaut, ni pour affiner quoi que ce soit.

Ce journal produit les deux d'un coup : le taux d'erreur des regles actuelles, et le
corpus d'entrainement de ce qui les remplacerait.

CE QU'IL NE FAIT PAS
--------------------
⚠️ Il ne DECIDE rien et ne change aucun comportement. Il observe la decision deja prise
et la range. Un bug ici ne peut pas rendre un bot muet ni bavard.

⚠️ Il n'est jamais sur le chemin de la reponse : l'ecriture part dans une file et un
thread la vide. `journalise()` rend la main immediatement, et si la file est pleine elle
JETTE l'entree au lieu d'attendre. Un journal qui ralentit le bot qu'il observe ne vaut
pas son cout.

⚠️ Il stocke le TEXTE des messages, ce que rien d'autre ne fait ici. C'est necessaire —
on n'affine pas un classifieur sur des horodatages — mais ca n'est pas anodin : le
fichier reste dans `data/`, couvert par `.gitignore` (`*.db`), et ne sort jamais de la
machine. `purge()` efface au-dela d'un age donne.

⚠️ JAMAIS `journal_mode=WAL` sur une base de `data/`. Le repertoire est monte depuis
l'hote Windows dans six conteneurs Linux, et un WAL orphelin les ejecte EN SILENCE :
les six bots deviennent muets ([[gotcha-wal-orphelin-verrouille-la-base]]). On reprend
le `TRUNCATE` de `api_tracking.py`, qui vit deja cette contrainte.
"""
import logging
import os
import queue
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger("journal_decisions")


def _maintenant_utc() -> str:
    """UTC naif ISO : la base est ecrite par six conteneurs (UTC) ET par des sondes sur
    l'hote (heure locale). Une seule base de temps, sinon les fenetres du dashboard mentent."""
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


# Les trois points de decision, tels qu'ils existent dans le code aujourd'hui.
INTENTION = "intention"     # Alfred seul : stop_keywords + la liste de rattrapage
TON = "ton"                 # Sugar seule : sugar_grudge.classify_tone
PERTINENCE = "pertinence"   # les six : _other_bot_in_focus / intervention spontanee
# ⚠️ Ajoutee le 2026-09-22, et c'est la decision qui remplira ce journal. Les trois
# premieres se declenchent si rarement qu'en DEUX JOURS elles n'ont produit que
# 30 lignes, dont zero pour `intention`. `detect_game_question` tourne sur le chat
# Twitch, cent fois plus souvent — c'est elle qui donnera un corpus utilisable, aux
# autres decisions comprises.
# C'est aussi le meilleur candidat du depot pour Laya : ensemble FERME d'etiquettes,
# tout est DANS le texte, et la regle actuelle est un mur de 66 motifs regex
# (`shared/twitch/game_info.py`). ⚠️ Mais on JOURNALISE d'abord, on branche ensuite,
# sur un chiffre : sans corpus, « Laya ferait mieux » est une opinion.
JEU_QUESTION = "jeu_question"   # les six sur Twitch : game_info.detect_game_question
DECISIONS = (INTENTION, TON, PERTINENCE, JEU_QUESTION)

# Au-dela, on jette plutot que d'attendre : le bot passe avant son journal.
_TAILLE_FILE = 500
# Un message de salon est court ; au-dela c'est du copier-coller qui n'apprend rien.
_MAX_TEXTE = 500

_file = queue.Queue(maxsize=_TAILLE_FILE)
_ecrivain = None
_verrou = threading.Lock()
_jetees = 0
_alerte_file_pleine = False


def _chemin():
    dossier = os.getenv("DATA_DIR", str(Path(__file__).parent.parent / "data"))
    os.makedirs(dossier, exist_ok=True)
    return os.path.join(dossier, "decisions.db")


def _connexion():
    conn = sqlite3.connect(_chemin(), timeout=20)
    # ⚠️ TRUNCATE, jamais WAL : voir l'avertissement en tete de module.
    try:
        conn.execute("PRAGMA journal_mode=TRUNCATE;")
        conn.execute("PRAGMA synchronous=NORMAL;")
    except sqlite3.Error as e:
        logger.warning(f"[JOURNAL] PRAGMA refuse : {e}")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            horodatage TEXT NOT NULL,
            bot TEXT NOT NULL,
            decision TEXT NOT NULL,
            texte TEXT NOT NULL,
            etiquette TEXT NOT NULL,
            detail TEXT,
            -- Rempli a la main, plus tard, quand on relit les desaccords. C'est LUI qui
            -- fait du journal un corpus : sans verite de reference, on ne mesure rien.
            verite TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_decision ON decisions(decision, horodatage)")
    conn.commit()
    return conn


def _boucle():
    try:
        conn = _connexion()
    except sqlite3.Error as e:
        logger.warning(f"[JOURNAL] base injoignable, journal desactive : {e}")
        return
    try:
        while True:
            tache = _file.get()
            try:
                if tache is None:
                    break
                conn.execute(
                    "INSERT INTO decisions (horodatage, bot, decision, texte, etiquette, detail)"
                    " VALUES (?, ?, ?, ?, ?, ?)", tache)
                conn.commit()
            except sqlite3.Error as e:
                logger.warning(f"[JOURNAL] ecriture refusee : {e}")
            finally:
                # ⚠️ Dans le `finally` : un `task_done()` saute sur la moindre exception
                # laisse `join()` pendre a jamais ([[plan-suivi-appels-api]]).
                _file.task_done()
    finally:
        try:
            conn.close()
        except sqlite3.Error:
            # Fermeture d'une connexion deja morte, a l'arret du thread : il n'y a plus
            # rien a sauver ni personne pour lire l'alerte. Crier ici ajouterait une
            # ligne d'erreur a chaque arret propre des six bots.
            pass


def _demarre():
    global _ecrivain
    with _verrou:
        if _ecrivain is None or not _ecrivain.is_alive():
            _ecrivain = threading.Thread(target=_boucle, daemon=True,
                                         name="journal-decisions")
            _ecrivain.start()


def journalise(bot, decision, texte, etiquette, detail=None):
    """Range une decision DEJA PRISE. Ne juge rien, ne bloque jamais.

    `etiquette` est ce que la regle en place a rendu ; `detail` ce qui explique son
    choix (la branche prise, le mot-cle qui a mordu). C'est `detail` qui permettra de
    relire les desaccords sans rouvrir le code.
    """
    if decision not in DECISIONS:
        raise ValueError(f"decision inconnue : {decision!r} (attendu : {DECISIONS})")
    if not texte:
        return
    _demarre()
    entree = (_maintenant_utc(), str(bot), decision,
              str(texte)[:_MAX_TEXTE], str(etiquette),
              None if detail is None else str(detail)[:200])
    try:
        _file.put_nowait(entree)
    except queue.Full:
        # On JETTE. Le bot passe avant son journal — et on ne crie qu'une fois, sinon
        # l'alerte devient le bruit ([[gotcha-alerte-qui-crie-pour-du-nominal]]).
        global _jetees, _alerte_file_pleine
        _jetees += 1
        if not _alerte_file_pleine:
            logger.warning("[JOURNAL] file pleine, entrees jetees (bot prioritaire)")
            _alerte_file_pleine = True


def compte(decision=None):
    """Combien d'entrees, par decision. Pour savoir quand le corpus est assez gros."""
    try:
        conn = _connexion()
    except sqlite3.Error:
        return {}
    try:
        if decision:
            r = conn.execute("SELECT COUNT(*) FROM decisions WHERE decision = ?",
                             (decision,)).fetchone()
            return {decision: r[0]}
        return {d: n for d, n in conn.execute(
            "SELECT decision, COUNT(*) FROM decisions GROUP BY decision")}
    finally:
        conn.close()


def purge(jours=90):
    """Efface les entrees plus vieilles que `jours`. Rend le nombre de lignes retirees."""
    limite = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=jours)).isoformat()
    try:
        conn = _connexion()
    except sqlite3.Error:
        return 0
    try:
        cur = conn.execute("DELETE FROM decisions WHERE horodatage < ?", (limite,))
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()
