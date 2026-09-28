# -*- coding: utf-8 -*-
"""Les appels fournisseur qui ne passent PAS par une cascade.

Le chantier du 2026-09-06 a branché `report_error` et `tracer_appel` sur les 11
cascades. Il en restait dehors : `!rumeur`, les décrets, le rattrapage de mention,
l'imposteur et la patrouille vocale tapent le SDK en direct, avec leur repli à deux
échelons écrit à la main. (Le conseil du vendredi d'Alfred en faisait partie ; il a été
supprimé le 2026-09-19 — voir `test_alfred_ne_publie_plus_le_conseil_du_vendredi`.)
Constaté en test live le 2026-09-07 à
22:41, journal de M'aiq :

    [GROQ RUMEUR] Error code: 429 ... Please try again in 1.785s

Zéro quarantaine sur les six bots, zéro ligne en base. La clé restait saine pour le
gestionnaire, et le message suivant retapait dans le même mur.

⚠️ La leçon qui gouverne ce fichier : **compter les APPELS à un fournisseur, pas les
cascades**. Un correctif qui couvre « toutes les cascades » laisse dehors tout ce qui
n'en est pas une, et rien ne le dit.
"""
import ast
import asyncio
import time
from pathlib import Path

import pytest

import shared.llm_cascade as cascade
from shared.api_manager import MultiAPIKeyManager
from shared.llm_cascade import appel_hors_cascade

RACINE = Path(__file__).resolve().parent.parent
BOTS = ["Alfred", "JohnnyBot", "MaiqBot", "MalenaBot", "Sheogorath", "SugarBot"]


# --------------------------------------------------------------------------------------
# Doublures
# --------------------------------------------------------------------------------------

class _Entetes:
    def __init__(self, **kw):
        self._d = {k.replace("_", "-"): v for k, v in kw.items()}

    def get(self, nom):
        return self._d.get(nom)


class _Reponse:
    def __init__(self, **kw):
        self.headers = _Entetes(**kw)


def _erreur_429(retry_after="45"):
    e = Exception("Rate limit reached")
    e.response = _Reponse(retry_after=retry_after)
    e.status_code = 429
    return e


class _FauxMessage:
    def __init__(self, contenu):
        self.content = contenu
        self.reasoning = None


class _FauxChat:
    def __init__(self, contenu):
        self.choices = [type("_C", (), {"message": _FauxMessage(contenu)})()]


class _FauxGemini:
    def __init__(self, texte):
        self.text = texte


@pytest.fixture
def traces(monkeypatch):
    """`tracer_appel` détourné : on veut la ligne qui SERAIT écrite, pas la base."""
    lignes = []
    monkeypatch.setattr(cascade, "tracer_appel", lambda **kw: lignes.append(kw))
    return lignes


def _appeler(**kw):
    return asyncio.run(appel_hors_cascade(**kw))


# --------------------------------------------------------------------------------------
# Le cas qui a motivé le lot : un 429 isolé doit écarter la clé
# --------------------------------------------------------------------------------------

def test_un_429_hors_cascade_met_la_cle_en_quarantaine(traces):
    """C'est très exactement `!rumeur` le 2026-09-07 : avant, rien ne se passait."""
    mgr = MultiAPIKeyManager()
    mgr.register_api("groq", ["gsk_1"])
    t0 = time.time()

    def _create(**_kw):
        raise _erreur_429(retry_after="45")

    assert _appeler(fournisseur="groq", fonction=_create, key_manager=mgr,
                    bot_label="M'aiq", modele="modele-groq") is None
    assert mgr.is_api_available("groq") is False, "le 429 n'a pas écarté la clé"
    attente = mgr.apis["groq"]["status"]["gsk_1"]["cooldown"] - t0
    assert 44 <= attente <= 46, (
        f"quarantaine de {attente:.0f}s : le délai annoncé par l'en-tête n'est pas lu"
    )
    assert traces[-1]["code_erreur"] == 429
    assert traces[-1]["succes"] is False


def test_l_appel_suivant_saute_l_echelon_sans_toucher_au_fournisseur(traces):
    """Le vrai bénéfice : on ne retape pas dans le mur au message d'après."""
    mgr = MultiAPIKeyManager()
    mgr.register_api("groq", ["gsk_1"])
    appels = []

    def _create(**_kw):
        appels.append(1)
        raise _erreur_429()

    _appeler(fournisseur="groq", fonction=_create, key_manager=mgr,
             bot_label="M'aiq", modele="modele-groq")
    _appeler(fournisseur="groq", fonction=_create, key_manager=mgr,
             bot_label="M'aiq", modele="modele-groq")

    assert len(appels) == 1, "le 2e appel a été tenté alors que la clé était écartée"
    assert traces[-1]["raison"] == "quarantaine", (
        "Un saut muet est un échelon invisible : il doit se nommer en base."
    )


# --------------------------------------------------------------------------------------
# Le reste de l'hygiène d'un échelon
# --------------------------------------------------------------------------------------

def test_une_reponse_rend_son_texte_et_une_ligne_de_succes(traces):
    mgr = MultiAPIKeyManager()
    mgr.register_api("groq", ["gsk_1"])
    texte = _appeler(fournisseur="groq", fonction=lambda **_kw: _FauxChat("Bonsoir."),
                     key_manager=mgr, bot_label="M'aiq", modele="m")
    assert texte == "Bonsoir."
    assert traces[-1]["succes"] is True
    assert traces[-1]["index_cle"] == 0


def test_gemini_batit_son_client_avec_la_cle_du_pool(traces):
    """`fabrique` reçoit la clé : c'est la seule forme où l'échelon en a besoin."""
    mgr = MultiAPIKeyManager()
    mgr.register_api("gemini", ["AIza_1"])
    vues = []

    class _Client:
        class models:
            @staticmethod
            def generate_content(**_kw):
                return _FauxGemini("Salutations.")

    def _fabrique(cle):
        vues.append(cle)
        return _Client()

    assert _appeler(fournisseur="gemini", fabrique=_fabrique,
                    methode="models.generate_content", key_manager=mgr,
                    bot_label="Alfred", modele="m") == "Salutations."
    assert vues == ["AIza_1"]


def test_gemini_sans_cle_ne_tente_rien():
    mgr = MultiAPIKeyManager()          # aucun pool
    appels = []

    def _fabrique(_cle):
        appels.append(1)
        return object()

    assert _appeler(fournisseur="gemini", fabrique=_fabrique,
                    methode="models.generate_content", key_manager=mgr,
                    bot_label="Alfred", modele="m") is None
    assert not appels, "sans clé, il n'y a rien à bâtir ni à appeler"


def test_un_pool_non_enregistre_ne_bloque_PAS_un_appel_facultatif(traces):
    """⚠️ La garde de `_cle_du_pool`, reprise ici : le client porte déjà sa clé.

    Un `register_api` oublié rendrait sinon le fournisseur muet, sans une ligne de
    journal — le piège qui a laissé NVIDIA sans un seul appel pendant huit jours.
    """
    mgr = MultiAPIKeyManager()          # aucun pool enregistré
    assert _appeler(fournisseur="groq", fonction=lambda **_kw: _FauxChat("Present."),
                    key_manager=mgr, bot_label="M'aiq", modele="m") == "Present."


def test_une_reponse_vide_ne_passe_pas_pour_une_reponse(traces):
    """Groq rend 200 OK avec un contenu vide : Discord refuse ensuite l'envoi."""
    mgr = MultiAPIKeyManager()
    mgr.register_api("groq", ["gsk_1"])
    assert _appeler(fournisseur="groq", fonction=lambda **_kw: _FauxChat("   "),
                    key_manager=mgr, bot_label="M'aiq", modele="m") is None
    assert traces[-1]["raison"] == "vide"


def test_appel_hors_cascade_gemini_bloque_porte_raison_bloque(traces):
    """SUITE 7 : un appel hors cascade refusé par Gemini porte raison='bloque:<nom>'."""
    import types
    mgr = MultiAPIKeyManager()
    mgr.register_api("gemini", ["fake_key"])
    rep = types.SimpleNamespace(
        text="",
        prompt_feedback=types.SimpleNamespace(
            block_reason=types.SimpleNamespace(name="PROHIBITED_CONTENT")
        ),
    )
    assert _appeler(fournisseur="gemini", fonction=lambda **_kw: rep,
                    key_manager=mgr, bot_label="Sugar", modele="gemini-3.5-flash-lite") is None
    assert traces[-1]["raison"] == "bloque:PROHIBITED_CONTENT"


def test_un_client_absent_n_est_pas_un_echec_d_api(traces):
    """Sans client, la base ne doit pas se remplir d'erreurs sans cause."""
    mgr = MultiAPIKeyManager()
    mgr.register_api("groq", ["gsk_1"])
    assert _appeler(fournisseur="groq", fonction=None, key_manager=mgr,
                    bot_label="M'aiq", modele="m") is None
    assert traces[-1]["raison"] == "non_tentee"


def test_un_appel_qui_traine_est_borne_et_ne_leve_pas(traces):
    mgr = MultiAPIKeyManager()
    mgr.register_api("groq", ["gsk_1"])

    def _lent(**_kw):
        time.sleep(1.0)
        return _FauxChat("trop tard")

    assert _appeler(fournisseur="groq", fonction=_lent, key_manager=mgr,
                    bot_label="M'aiq", modele="m", timeout=0.05) is None
    assert traces[-1]["succes"] is False


def test_l_appel_ne_bloque_pas_la_boucle_asyncio():
    """Le SDK est SYNCHRONE : appelé en direct, il gèle le bot entier (audit 0131583)."""
    mgr = MultiAPIKeyManager()
    mgr.register_api("groq", ["gsk_1"])
    temoin = []

    async def _scenario():
        async def _battement():
            for _ in range(5):
                temoin.append(1)
                await asyncio.sleep(0.01)

        _, _ = await asyncio.gather(
            appel_hors_cascade("groq", lambda **_kw: (time.sleep(0.2), _FauxChat("ok"))[1],
                               key_manager=mgr, bot_label="M'aiq", modele="m"),
            _battement(),
        )

    asyncio.run(_scenario())
    assert len(temoin) == 5, "la boucle est restée bloquée pendant l'appel"


# --------------------------------------------------------------------------------------
# Le client Gemini doit SURVIVRE a son propre appel
# --------------------------------------------------------------------------------------

def test_le_client_bati_par_la_fabrique_reste_vivant_pendant_l_appel(traces):
    """⚠️ Regression du 2026-09-07, vue dans le journal du decret du soir :

        [GEMINI FAIL] gemini-3.5-flash - RuntimeError: Cannot send a request,
                                         as the client has been closed.
        [MISTRAL ministral-14b-latest] Sheogorath (hors cascade)

    Premiere version de la fabrique :
    `lambda cle: get_safe_genai_client(cle).models.generate_content`. Le `Client` n'etait
    alors reference par personne — `client.models` ne garde AUCUN lien vers lui — donc le
    GC le ramassait et fermait son transport HTTP. **Tous** les appels Gemini hors cascade
    echouaient, sur les 6 bots, et personne ne le voyait : l'echelon suivant repondait.

    Ici on mesure la seule chose qui compte : au moment ou l'appel s'execute, l'objet rendu
    par la fabrique est-il encore vivant ?
    """
    import gc
    import weakref

    mgr = MultiAPIKeyManager()
    mgr.register_api("gemini", ["AIza_1"])
    temoin = {}

    class _Client:
        def __init__(self):
            self.models = self

        def generate_content(self, **_kw):
            gc.collect()          # le pire moment possible
            temoin["vivant"] = temoin["ref"]() is not None
            return _FauxGemini("Salutations.")

    def _fabrique(_cle):
        client = _Client()
        temoin["ref"] = weakref.ref(client)
        return client

    assert _appeler(fournisseur="gemini", fabrique=_fabrique,
                    methode="models.generate_content", key_manager=mgr,
                    bot_label="Sheogorath", modele="m") == "Salutations."
    assert temoin["vivant"] is True, (
        "Le client a ete ramasse par le GC pendant son propre appel : son transport HTTP "
        "est ferme, et tous les appels Gemini hors cascade echouent en silence."
    )


def test_la_fabrique_rend_le_client_et_methode_dit_quoi_appeler(traces):
    """Le chemin pointe est resolu sur l'objet, pas devine."""
    mgr = MultiAPIKeyManager()
    mgr.register_api("gemini", ["AIza_1"])

    class _Client:
        class models:
            @staticmethod
            def generate_content(**_kw):
                return _FauxGemini("par le chemin pointe")

    assert _appeler(fournisseur="gemini", fabrique=lambda _c: _Client(),
                    methode="models.generate_content", key_manager=mgr,
                    bot_label="Alfred", modele="m") == "par le chemin pointe"


def _fabriques_du_fichier(arbre):
    """Les `fabrique=` passees a `appel_hors_cascade`, avec leur ligne.

    ⚠️ Par l'AST, jamais par une regex de ligne. Premiere version de ce verrou : une
    regex `fabrique=.*generate_content` — elle ne voyait que les fabriques tenant sur UNE
    ligne, et 3 des 6 sites Gemini sont a cheval sur trois lignes. Elle rendait 3 fautes
    sur 6 en annoncant la couverture complete.
    """
    trouvees = []
    for noeud in ast.walk(arbre):
        if not (isinstance(noeud, ast.Call)
                and isinstance(noeud.func, ast.Name)
                and noeud.func.id == "appel_hors_cascade"):
            continue
        mots = {k.arg: k.value for k in noeud.keywords}
        if "fabrique" in mots:
            trouvees.append((noeud.lineno, mots["fabrique"], "methode" in mots))
    return trouvees


# M'aiq n'y est plus : ses trois appels Gemini hors cascade etaient la rumeur du jour et
# les enigmes, retirees par la SUITE 17 (28/09). Il n'a plus aucune `fabrique=`.
@pytest.mark.parametrize("chemin", ["Alfred/bot_alfred.py", "Sheogorath/bot_sheogorath.py"])
def test_une_fabrique_rend_le_client_jamais_la_methode(chemin):
    """⚠️ Le verrou de la regression du 2026-09-07.

    Une fabrique qui rend `client.models.generate_content` laisse le `Client` sans
    aucune reference : le GC le ramasse, ferme son transport, et l'echelon Gemini meurt
    en silence derriere son echelon de secours.

    La regle tient en une phrase : le corps de la lambda doit APPELER (batir un client),
    pas ACCEDER a un attribut.
    """
    arbre = ast.parse((RACINE / chemin).read_text(encoding="utf-8"), filename=chemin)
    fabriques = _fabriques_du_fichier(arbre)
    assert fabriques, f"{chemin} n'a plus aucune fabrique Gemini"

    fautes = []
    for ligne, valeur, a_methode in fabriques:
        corps = valeur.body if isinstance(valeur, ast.Lambda) else None
        if corps is not None and not isinstance(corps, ast.Call):
            fautes.append(f"  ligne {ligne} : la fabrique rend "
                          f"`{ast.unparse(corps)[:60]}` au lieu du client")
        if not a_methode:
            fautes.append(f"  ligne {ligne} : `fabrique=` sans `methode=`")

    assert not fautes, (
        f"{chemin} :\n" + "\n".join(fautes)
        + "\n\nLa fabrique doit rendre le CLIENT, et `methode=` dire quoi appeler dessus."
    )


# --------------------------------------------------------------------------------------
# Le verrou : plus AUCUN appel SDK nu dans les bots
# --------------------------------------------------------------------------------------
#
# ⚠️ Ce test-ci est le seul qui empêche la reconstruction du défaut. Les tests de
# comportement ci-dessus prouvent que le helper est bon ; ils ne disent rien de ceux qui
# ne l'appellent pas. Le prochain repli écrit à la main sera rouge ici, pas en live.

_APPELS_SDK = {
    ("chat", "completions", "create"),   # Groq, NVIDIA (SDK OpenAI)
    ("chat", "complete"),                # Mistral
    ("models", "generate_content"),      # Gemini
}


def _chaine_d_attributs(noeud):
    """`groq_client.chat.completions.create` -> ('chat', 'completions', 'create')."""
    morceaux = []
    while isinstance(noeud, ast.Attribute):
        morceaux.append(noeud.attr)
        noeud = noeud.value
    return tuple(reversed(morceaux))


def _boucles_de_cascade(arbre):
    """Les boucles `for client_type, model_name in cascade` — la BOUCLE, pas sa fonction.

    Les 4 cascades recopiées à la main gardent leur propre traçage
    (cf. tests/test_quarantaine_tous_fournisseurs.py) : elles sont hors sujet ici.

    ⚠️ Abriter la FONCTION entière au lieu de la boucle rendait le verrou aveugle là où
    il fallait qu'il voie : les quatre appels de l'imposteur vivent dans le `on_message`
    de Sheogorath, celui-là même qui porte sa cascade inline. Mesuré sur la version
    d'avant le correctif — 6 appels nus vus au lieu de 10.
    """
    return [noeud for noeud in ast.walk(arbre)
            if isinstance(noeud, ast.For)
            and isinstance(noeud.target, ast.Tuple)
            and [getattr(el, "id", None) for el in noeud.target.elts]
                == ["client_type", "model_name"]]


def _noeuds_couverts(arbre, cascades):
    """Tout ce qui vit à l'intérieur d'un appel à `appel_hors_cascade`, ou d'une cascade."""
    couverts = set()
    abris = list(cascades)
    for noeud in ast.walk(arbre):
        if (isinstance(noeud, ast.Call)
                and isinstance(noeud.func, ast.Name)
                and noeud.func.id == "appel_hors_cascade"):
            abris.append(noeud)
    for abri in abris:
        for interne in ast.walk(abri):
            couverts.add(id(interne))
    return couverts


@pytest.mark.parametrize("bot", BOTS)
def test_aucun_appel_fournisseur_nu_dans_les_bots(bot):
    fichiers = list((RACINE / bot).glob("bot_*.py"))
    assert len(fichiers) == 1, f"{bot} : {len(fichiers)} fichier(s) bot_*.py"
    arbre = ast.parse(fichiers[0].read_text(encoding="utf-8"), filename=str(fichiers[0]))

    couverts = _noeuds_couverts(arbre, _boucles_de_cascade(arbre))

    nus = []
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, ast.Attribute):
            continue
        if _chaine_d_attributs(noeud) not in _APPELS_SDK:
            continue
        if id(noeud) in couverts:
            continue
        nus.append(noeud.lineno)

    assert not nus, (
        f"{fichiers[0].name} : appel(s) fournisseur en direct ligne(s) {nus}. "
        "Un appel isolé ne met aucune clé en quarantaine et n'écrit rien en base — "
        "c'est le défaut du 2026-09-07. Passer par `appel_hors_cascade`."
    )


@pytest.mark.parametrize("bot", ["Alfred", "MaiqBot", "Sheogorath"])
def test_les_bots_concernes_appellent_vraiment_le_helper(bot):
    """⚠️ Un test qui cherche un NOM passe au vert sur un simple import.

    On exige l'APPEL, et le fournisseur qu'il nomme : sans ça, retirer l'appel en
    gardant l'import laisserait le verrou précédent satisfait (il ne compte que les
    appels nus, or il n'y en aurait plus).
    """
    fichiers = list((RACINE / bot).glob("bot_*.py"))
    arbre = ast.parse(fichiers[0].read_text(encoding="utf-8"), filename=str(fichiers[0]))
    fournisseurs = set()
    for noeud in ast.walk(arbre):
        if (isinstance(noeud, ast.Call)
                and isinstance(noeud.func, ast.Name)
                and noeud.func.id == "appel_hors_cascade"):
            premier = (noeud.args[0] if noeud.args
                       else next((k.value for k in noeud.keywords
                                  if k.arg == "fournisseur"), None))
            if isinstance(premier, ast.Constant):
                fournisseurs.add(premier.value)
    assert fournisseurs, f"{bot} n'appelle jamais appel_hors_cascade"
    assert fournisseurs <= {"gemini", "mistral", "groq", "nvidia"}, (
        f"{bot} nomme un fournisseur inconnu : {sorted(fournisseurs)}"
    )
