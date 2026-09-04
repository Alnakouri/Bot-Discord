"""Le 429 silencieux, et les cascades inline qui n'etaient pas tracees.

Audit du 2026-09-04. Sheogorath repondait en 10 a 35 secondes. Ce n'etait ni le reseau,
ni le modele, ni un echelon mort : son prompt fait **4 505 tokens** pour un quota Groq de
**8 000 tokens par minute**. Le deuxieme message de la minute prend un 429 — que le SDK
Groq **absorbe en dormant `retry-after` secondes** avant de re-essayer tout seul.

Mesure, meme cle, meme instant, `openai/gpt-oss-120b` :

    prompt Johnny (2 189 tokens) ->   287 ms
    prompt Sheo   (4 505 tokens) -> 9 837 ms puis 34 673 ms
    le meme appel avec max_retries=0 -> RateLimitError en 271 ms

Et Groq rend ses propres compteurs : `completion_time=0,207 s`. Le serveur travaillait
0,22 s ; le reste etait du sommeil.

⚠️ Le vrai degat n'est pas la lenteur, c'est que **le sommeil du SDK court-circuite la
cascade** : un 429 doit faire descendre d'un echelon, pas attendre le meme modele sature.
"""
import re
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent

BOTS = {
    "Alfred": "bot_alfred.py",
    "JohnnyBot": "bot_johnny.py",
    "MaiqBot": "bot_maiq.py",
    "MalenaBot": "bot_malena.py",
    "Sheogorath": "bot_sheogorath.py",
    "SugarBot": "bot_sugar.py",
}

# Les 3 bots dont la cascade est une COPIE inline de shared/llm_cascade.py.
# Johnny, Sugar et Malena passent par le noyau et heritent de son tracage.
BOTS_CASCADE_INLINE = {
    "Alfred": ("bot_alfred.py", "alfred"),
    "MaiqBot": ("bot_maiq.py", "maiq"),
    "Sheogorath": ("bot_sheogorath.py", "sheo"),
}


def _source(dossier, fichier):
    return (RACINE / dossier / fichier).read_text(encoding="utf-8")


def test_aucun_client_groq_ne_dort_sur_un_429():
    """Un 429 doit descendre la cascade en ~300 ms, pas dormir 7 s en silence."""
    manquants = []
    for dossier, fichier in BOTS.items():
        src = _source(dossier, fichier)
        for appel in re.findall(r"Groq\([^)]*\)", src):
            if "max_retries=0" not in appel:
                manquants.append(f"{fichier}: {appel}")
    assert not manquants, (
        "Ces clients Groq gardent le max_retries=2 par defaut : sur un 429 le SDK dort "
        "`retry-after` secondes et re-essaie LE MEME modele sature, au lieu de laisser "
        "la cascade basculer.\n  " + "\n  ".join(manquants)
    )


def test_aucun_client_openrouter_ne_dort_sur_un_429():
    """Meme piege, meme SDK (le client OpenAI a lui aussi max_retries=2 par defaut)."""
    manquants = []
    for dossier, fichier in BOTS.items():
        src = _source(dossier, fichier)
        for appel in re.findall(r"OpenAI\([^)]*openrouter[^)]*\)", src):
            if "max_retries=0" not in appel:
                manquants.append(f"{fichier}: {appel}")
    assert not manquants, "Clients OpenRouter sans max_retries=0 :\n  " + "\n  ".join(manquants)


def test_les_deux_familles_de_clients_sont_couvertes():
    """⚠️ Prouver que les tests ci-dessus ont trouve leur matiere.

    Sans cette borne, renommer la variable du client ferait passer les deux tests
    precedents au vert en n'inspectant plus rien.
    """
    groq = openrouter = 0
    for dossier, fichier in BOTS.items():
        src = _source(dossier, fichier)
        groq += len(re.findall(r"Groq\([^)]*\)", src))
        openrouter += len(re.findall(r"OpenAI\([^)]*openrouter[^)]*\)", src))
    assert groq == 6, f"On attendait 6 clients Groq (un par bot), on en a trouve {groq}"
    assert openrouter == 6, f"On attendait 6 clients OpenRouter, on en a trouve {openrouter}"


def test_les_cascades_inline_tracent_leurs_appels():
    """Alfred, M'aiq et Sheo ont recopie la cascade SANS son bloc de tracage.

    Consequence mesuree : pendant tout le test live du 04/09, `data/api_usage.db` n'avait
    **aucune ligne** pour ces trois bots, alors qu'ils avaient tous les trois repondu.
    On ne pouvait donc pas savoir pourquoi Sheo mettait 12 secondes.
    """
    trouves = 0
    for dossier, (fichier, bot_id) in BOTS_CASCADE_INLINE.items():
        src = _source(dossier, fichier)
        assert "from core.api_tracking import tracer_appel" in src, (
            f"{fichier} n'importe pas tracer_appel"
        )
        # ⚠️ L'import ne prouve rien : exiger l'APPEL, avec l'identifiant du bot.
        assert f'bot="{bot_id}"' in src, (
            f"{fichier} importe tracer_appel mais ne l'APPELLE pas pour '{bot_id}'"
        )
        assert "finally:" in src and "_latence = int((time.perf_counter() - _depart) * 1000)" in src, (
            f"{fichier} n'a pas le bloc finally qui mesure la latence"
        )
        trouves += 1
    assert trouves == 3, f"On attendait 3 cascades inline inspectees, on en a eu {trouves}"


def test_la_latence_est_mesuree_au_perf_counter():
    """⚠️ Jamais datetime.now() : l'horloge des conteneurs derive de 2 h."""
    for dossier, (fichier, _) in BOTS_CASCADE_INLINE.items():
        src = _source(dossier, fichier)
        bloc = src[src.index("_latence = int("):][:120]
        assert "perf_counter" in bloc, f"{fichier} ne mesure pas la latence au perf_counter"


def test_on_ready_survit_a_une_reconnexion():
    """`on_ready` rejoue a chaque reconnexion, et la 2e pose des commandes slash leve.

    Le 04/09 a 11:17:45, apres une sortie de veille de l'hote, les 6 bots ont rejoue
    `on_ready`. Trois ont plante sur `CommandAlreadyRegistered`, ce qui a **avorte tout
    le reste** : les mini-jeux d'Alfred, le rattrapage des enigmes de M'aiq, et **la
    reprise des punitions** de Sheogorath.

    ⚠️ Meme mecanisme que le `RuntimeError: Task is already launched` corrige par
    `839fae5` — celui-la visait les `.start()`, il manquait tout le reste de `on_ready`.
    """
    nus = []
    inspectes = 0
    for dossier, fichier in BOTS.items():
        src = _source(dossier, fichier)
        for n, ligne in enumerate(src.split("\n")):
            if "setup_slash_commands(bot," not in ligne and "setup_games(bot," not in ligne:
                continue
            inspectes += 1
            # L'appel doit se trouver dans un try: — on regarde les 6 lignes au-dessus.
            avant = src.split("\n")[max(0, n - 6):n]
            if not any(l.strip() == "try:" for l in avant):
                nus.append(f"{fichier}:{n + 1} {ligne.strip()}")
    # ⚠️ Prouver que le test a trouve sa matiere : sans cette borne, un renommage le
    # rendrait vert en n'inspectant plus une seule ligne.
    assert inspectes >= 10, f"Trop peu d'appels inspectes : {inspectes}"
    assert not nus, (
        "Ces appels ne sont pas proteges : a la reconnexion ils levent et avortent la "
        "suite de on_ready (mini-jeux, rattrapages, reprise des punitions).\n  "
        + "\n  ".join(nus)
    )


def test_le_429_dit_pourquoi_dans_les_logs():
    """Un 429 porte ses raisons dans ses en-tetes ; sans elles c'est un echec anonyme."""
    import sys

    sys.path.insert(0, str(RACINE))
    from shared.models import details_de_quota

    class FauxReponse:
        headers = {
            "retry-after": "7",
            "x-ratelimit-limit-tokens": "8000",
            "x-ratelimit-remaining-tokens": "3771",
            "x-ratelimit-reset-tokens": "31.7s",
        }

    class FauxErreur(Exception):
        response = FauxReponse()

    resume = details_de_quota(FauxErreur())
    assert "reprise dans=7" in resume
    assert "tokens restants=3771" in resume
    assert "quota=8000" in resume

    # Une exception sans en-tetes ne doit rien inventer ni lever.
    assert details_de_quota(ValueError("rien")) == ""


def test_le_helper_de_quota_est_branche_dans_les_deux_cascades():
    """Le noyau ET la copie inline de Sheogorath doivent journaliser le quota."""
    noyau = (RACINE / "shared" / "llm_cascade.py").read_text(encoding="utf-8")
    sheo = _source("Sheogorath", "bot_sheogorath.py")
    for nom, src in (("shared/llm_cascade.py", noyau), ("bot_sheogorath.py", sheo)):
        assert "details_de_quota(e)" in src, f"{nom} n'appelle pas details_de_quota"
        assert "[QUOTA]" in src, f"{nom} ne journalise pas le detail du quota"


# ═══════════════════════════════════════════════════════════════════════════
# Le chronometre bout-en-bout
# ═══════════════════════════════════════════════════════════════════════════

def test_le_chrono_mesure_au_perf_counter_pas_a_l_horloge(monkeypatch):
    """⚠️ Une horloge murale saute (sortie de veille) et derive de 2 h en conteneur."""
    import sys

    sys.path.insert(0, str(RACINE))
    from shared import chrono as mod

    faux = iter([100.0, 100.2, 101.4])
    monkeypatch.setattr(mod.time, "perf_counter", lambda: next(faux))
    monkeypatch.setattr(mod, "tracer_reponse", lambda **kw: None)

    c = mod.Chrono("essai")
    c.etape("contexte")
    assert c.fin(envoye=True) == 1400.0
    assert c.etapes["contexte"] == 200


def test_le_chrono_n_explose_jamais(monkeypatch):
    """Un chronometre qui casse `on_message` serait pire que pas de chronometre."""
    import sys

    sys.path.insert(0, str(RACINE))
    from shared import chrono as mod

    def explose(**kw):
        raise RuntimeError("base injoignable")

    monkeypatch.setattr(mod, "tracer_reponse", explose)
    c = mod.Chrono("essai")
    assert c.fin(envoye=True) == 0.0  # avale l'erreur, ne la propage pas


def test_le_chrono_ne_compte_qu_une_fois():
    """Deux `fin()` sur le meme chrono ne doivent pas ecrire deux lignes."""
    import sys

    sys.path.insert(0, str(RACINE))
    from shared.chrono import Chrono

    ecrits = []
    import shared.chrono as mod

    original = mod.tracer_reponse
    mod.tracer_reponse = lambda **kw: ecrits.append(kw)
    try:
        c = Chrono("essai")
        c.fin(envoye=True)
        c.fin(envoye=True)
    finally:
        mod.tracer_reponse = original
    assert len(ecrits) == 1


def test_les_6_bots_chronometrent_leur_reponse():
    """⚠️ L'import ne prouve rien : exiger la creation, le jalon `llm` ET `fin(`."""
    ids = {"Alfred": "alfred", "JohnnyBot": "johnny", "MaiqBot": "maiq",
           "MalenaBot": "malena", "Sheogorath": "sheo", "SugarBot": "sugar"}
    trouves = 0
    for dossier, fichier in BOTS.items():
        src = _source(dossier, fichier)
        assert "from core.chrono import Chrono" in src, f"{fichier} n'importe pas Chrono"
        assert f'Chrono("{ids[dossier]}"' in src, f"{fichier} ne cree pas de Chrono"
        assert '_chrono.etape("llm")' in src, f"{fichier} ne jalonne pas l'appel LLM"
        assert "_chrono.fin(" in src, f"{fichier} ne cloture jamais son chrono"
        trouves += 1
    assert trouves == 6, f"On attendait 6 bots chronometres, on en a eu {trouves}"


def test_un_abandon_laisse_une_trace():
    """Un bot qui renonce apres 15 s est le cas qui n'en laissait aucune."""
    abandons = [d for d, f in BOTS.items() if "_chrono.fin(envoye=False)" in _source(d, f)]
    assert abandons, "Aucun bot n'enregistre le cas ou il renonce a repondre"


def test_les_copies_vendorisees_n_importent_plus_shared():
    """⚠️ `vendor_core.py` ne reecrit `shared.` qu'en DEBUT DE LIGNE.

    Un `from shared.x import y` **indente** (dans un try/except, par exemple) traverse le
    vendoring intact : en conteneur il leve ImportError et la fonctionnalite disparait en
    silence. Pris sur le fait avec `shared/chrono.py` le 2026-09-04.
    """
    import sys

    sys.path.insert(0, str(RACINE / "tools"))
    try:
        import sonde_core_drift
    finally:
        sys.path.pop(0)

    fautifs = []
    inspectes = 0
    for bot in ["Alfred", "JohnnyBot", "MaiqBot", "MalenaBot", "Sheogorath", "SugarBot"]:
        for module in sonde_core_drift.MODULES:
            copie = RACINE / bot / "core" / module
            if not copie.exists():
                continue
            inspectes += 1
            for n, ligne in enumerate(copie.read_text(encoding="utf-8").split("\n")):
                if re.match(r"\s*(from|import)\s+shared\.", ligne):
                    fautifs.append(f"{bot}/core/{module}:{n + 1} {ligne.strip()}")
    assert inspectes >= 60, f"Trop peu de copies inspectees : {inspectes}"
    assert not fautifs, (
        "Ces copies vendorisees importent encore `shared.` — elles leveront ImportError "
        "en conteneur. Mettre l'import en DEBUT DE LIGNE pour que le vendoring le "
        "reecrive.\n  " + "\n  ".join(fautifs)
    )


# ═══════════════════════════════════════════════════════════════════════════
# NVIDIA : 4e fournisseur, et la fuite de raisonnement
# ═══════════════════════════════════════════════════════════════════════════

def test_nvidia_coupe_le_raisonnement_a_la_source():
    """⚠️ Sans ce parametre, nemotron RECOPIE sa pensee dans `content`.

    Mesure du 2026-09-04 (tools/sonde_fuite_raisonnement.py, prompt de persona reel) :

        sans rien      6 779 ms   « L'utilisateur m'envoie un message simple : ... »
        effort=none    1 001 ms   « Et toi t'as un clavier et une connexion. choom. »

    Le parametre ne supprime pas seulement la fuite : il divise la latence par SIX.

    ⚠️ `reasoning_effort` n'est PAS un parametre du client OpenAI : il doit passer par
    `extra_body`, sinon l'appel leve avant meme de partir sur le reseau.
    """
    import sys

    sys.path.insert(0, str(RACINE))
    from shared.models import nvidia_kwargs

    kw = nvidia_kwargs("nvidia/nemotron-3.5-lightning-30b-a3b")
    assert "extra_body" in kw, "le parametre doit passer par extra_body, pas en direct"
    assert kw["extra_body"].get("reasoning_effort") == "none"


def test_la_cascade_appelle_nvidia_avec_le_garde_fou():
    """Le noyau doit poser le parametre ET garder le filet de sortie."""
    src = (RACINE / "shared" / "llm_cascade.py").read_text(encoding="utf-8")
    assert 'elif client_type == "nvidia"' in src, "aucune branche NVIDIA dans la cascade"
    branche = src.split('elif client_type == "nvidia"')[1].split("elif client_type ==")[0]
    assert "nvidia_kwargs(" in branche, (
        "la branche NVIDIA n'applique pas nvidia_kwargs : nemotron recitera sa pensee"
    )
    # ⚠️ Ceinture ET bretelles : le parametre pourrait cesser d'etre honore par le
    # fournisseur. Le filet de sortie doit rester.
    assert "_fuite_de_raisonnement(" in branche, (
        "la branche NVIDIA n'a pas le filet _fuite_de_raisonnement"
    )


def test_les_6_bots_construisent_le_client_nvidia():
    """⚠️ Un client absent = un echelon silencieusement saute, sans erreur."""
    trouves = 0
    for dossier, fichier in BOTS.items():
        src = _source(dossier, fichier)
        assert 'NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")' in src, f"{fichier} ne lit pas la cle"
        assert "nvidia_client = OpenAI(" in src, f"{fichier} ne construit pas le client"
        assert "max_retries=0" in src.split("nvidia_client = OpenAI(")[1][:160], (
            f"{fichier} : client NVIDIA sans max_retries=0"
        )
        assert "nvidia_client=nvidia_client" in src, f"{fichier} ne le passe pas a la cascade"
        trouves += 1
    assert trouves == 6, f"On attendait 6 bots, on en a eu {trouves}"


def test_chaque_cascade_porte_un_4e_fournisseur():
    """Mistral plafonne + OpenRouter retire : il ne restait que 3 fournisseurs.

    ⚠️ Deriver le compte de la liste des cascades, pas de ce que la boucle a trouve.
    """
    import sys

    sys.path.insert(0, str(RACINE))
    from shared.models import CASCADES_PERSONA

    assert len(CASCADES_PERSONA) == 6, f"{len(CASCADES_PERSONA)} cascades, on en attend 6"
    for bot, cascade in CASCADES_PERSONA.items():
        fournisseurs = [f for f, _ in cascade]
        assert "nvidia" in fournisseurs, f"{bot} n'a pas d'echelon NVIDIA"
        assert len(set(fournisseurs)) >= 4, (
            f"{bot} n'a que {len(set(fournisseurs))} fournisseurs distincts : "
            "si l'un plafonne, il ne reste presque rien."
        )


def test_les_clients_sont_definis_meme_sans_aucune_cle():
    """⚠️ Le local MENT sur tout ce qui depend de l'environnement.

    Le 2026-09-04, `nvidia_client = None` avait ete pose DANS un `if OPENROUTER_API_KEY:`.
    En local la cle existe, donc la ligne s'executait et la suite etait verte. En CI, sans
    cle, le nom n'existait pas du tout :

        Sheogorath/bot_sheogorath.py:431: in <module>
            groq_client=groq_client, openrouter_client=openrouter_client, nvidia_client=nvidia_client,
        E   NameError: name 'nvidia_client' is not defined

    Le bot ne demarrait meme pas. Ce test lit la structure du module — il n'a besoin
    d'aucune cle, donc il dit la meme chose ici et en CI.
    """
    import ast

    CLIENTS = ["nvidia_client", "openrouter_client", "groq_client", "mistral_client"]
    fautifs = []
    inspectes = 0
    for dossier, fichier in BOTS.items():
        arbre = ast.parse(_source(dossier, fichier))
        # Les affectations du CORPS du module : ni dans un if, ni dans un try, ni
        # dans une fonction. Ce sont les seules qui existent a coup sur.
        surs = set()
        for noeud in arbre.body:
            if isinstance(noeud, ast.Assign):
                for cible in noeud.targets:
                    if isinstance(cible, ast.Name):
                        surs.add(cible.id)
        for nom in CLIENTS:
            inspectes += 1
            if nom not in surs:
                fautifs.append(f"{fichier}: {nom}")
    assert inspectes == 24, f"On attendait 6 bots x 4 clients, on a inspecte {inspectes}"
    assert not fautifs, (
        "Ces clients ne sont pas definis inconditionnellement au niveau du module : "
        "sans la cle correspondante, le bot leve NameError au demarrage.\n  "
        + "\n  ".join(fautifs)
    )
