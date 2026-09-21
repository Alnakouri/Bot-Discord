"""Le quota Gemini se compte PAR MODELE : la quarantaine doit le faire aussi.

Le 2026-09-20, le juge d'eval (`gemini-3.5-flash`, 17 appels par passe) saturait SON
seau et appelait `report_error`, qui posait le cooldown sur la CLE — tous modeles
confondus. L'echelon `flash-lite` du bot mesure, dont le seau etait INTACT, se retrouvait
saute 12 a 13 fois sur 17, alors que le bot n'avait fait que DEUX appels dans la minute
concernee, sur une limite de quinze.

Le juge a ete rendu inerte le jour meme, mais ca ne reglait que le harnais. En PROD le
meme defaut restait arme : un 429 sur l'echelon VISION (`gemini-3.5-flash`) mettait en
quarantaine l'echelon TEXTE (`flash-lite`) du meme bot, sur la meme cle.

Google nomme lui-meme le seau dans son 429 : `GenerateRequestsPerMinutePerProjectPerModel`
— 15 requetes/minute PAR MODELE. La quarantaine porte donc desormais sur le couple
(cle, modele) chez les fournisseurs de `QUOTA_PAR_MODELE`, et sur la CLE partout ailleurs.

⚠️ Ce fichier garde les deux sens du filet. Elargir `QUOTA_PAR_MODELE` sans mesure
rendrait la quarantaine inoperante chez un fournisseur qui compte par cle : le bot
retaperait dans le mur avec un autre modele.
"""
import ast
import time
from pathlib import Path

import pytest

from shared.api_manager import QUOTA_PAR_MODELE, MultiAPIKeyManager

RACINE = Path(__file__).resolve().parent.parent
BOTS = ["Alfred", "JohnnyBot", "MaiqBot", "MalenaBot", "Sheogorath", "SugarBot"]

# Les deux echelons Gemini d'un meme bot, sur la meme cle : c'est la paire exacte que le
# defaut faisait tomber ensemble.
VISION = "gemini-3.5-flash"
TEXTE = "gemini-3.5-flash-lite"

CASCADES_INLINE = {
    "Alfred": "Alfred/bot_alfred.py",
    "MaiqBot": "MaiqBot/bot_maiq.py",
    "MalenaBot": "MalenaBot/bot_malena.py",
    "Sheogorath": "Sheogorath/bot_sheogorath.py",
}


def _manager(api="gemini", cles=("key1",)):
    mgr = MultiAPIKeyManager()
    mgr.register_api(api, list(cles))
    return mgr


# --------------------------------------------------------------------------------------
# Le defaut du 2026-09-20, dans les deux sens
# --------------------------------------------------------------------------------------

def test_un_429_sur_la_vision_ne_ferme_pas_l_echelon_texte():
    """LE test. Un seul bot, une seule cle, deux modeles : un seau saute, pas l'autre."""
    mgr = _manager()
    mgr.report_error("gemini", "key1", 429, retry_delay_s=60, modele=VISION)

    assert mgr.get_key("gemini", modele=TEXTE) == "key1", (
        "l'echelon TEXTE a ete saute alors que son seau est intact : c'est exactement le "
        "defaut mesure le 2026-09-20 (2 appels faits sur une limite de 15)."
    )
    assert mgr.is_api_available("gemini", modele=TEXTE) is True


def test_le_modele_qui_a_pris_le_429_est_bien_ecarte():
    """L'autre sens : sans ca, la quarantaine ne protege plus de rien."""
    mgr = _manager()
    mgr.report_error("gemini", "key1", 429, retry_delay_s=60, modele=VISION)

    assert mgr.get_key("gemini", modele=VISION) is None
    assert mgr.is_api_available("gemini", modele=VISION) is False


def test_la_duree_annoncee_gouverne_le_seau_du_modele():
    mgr = _manager()
    t0 = time.time()
    mgr.report_error("gemini", "key1", 429, retry_delay_s=24, modele=VISION)
    attente = mgr.apis["gemini"]["status"]["key1"]["cooldown_modele"][VISION] - t0
    assert 23 <= attente <= 25, f"quarantaine de {attente:.0f}s au lieu des 24s annoncees"
    assert mgr.apis["gemini"]["status"]["key1"]["cooldown"] == 0, (
        "le seau de la CLE a ete touche : les autres modeles vont sauter pour rien."
    )


# --------------------------------------------------------------------------------------
# Les replis : ne jamais elargir la permission par accident
# --------------------------------------------------------------------------------------

def test_sans_modele_le_429_ecarte_toujours_la_cle_entiere():
    """Un appelant qui ne nomme pas son modele garde l'ancien comportement, le prudent."""
    mgr = _manager()
    mgr.report_error("gemini", "key1", 429, retry_delay_s=60)
    assert mgr.is_api_available("gemini") is False
    assert mgr.is_api_available("gemini", modele=TEXTE) is False, (
        "un cooldown pose sur la CLE doit valoir pour TOUS les modeles, sinon un 429 "
        "dont on ignore le modele ne protege plus personne."
    )


@pytest.mark.parametrize("fournisseur", ["groq", "mistral", "nvidia"])
def test_les_autres_fournisseurs_ecartent_toujours_la_cle(fournisseur):
    """⚠️ Chez eux le quota se compte par cle : le 2026-09-04, trois appels Mistral sur la
    MEME cle morte dans la meme seconde. Elargir QUOTA_PAR_MODELE demande une MESURE."""
    mgr = _manager(fournisseur, ["k1"])
    mgr.report_error(fournisseur, "k1", 429, retry_delay_s=60, modele="un-modele")
    assert mgr.is_api_available(fournisseur, modele="un-autre-modele") is False, (
        f"{fournisseur} : le 429 n'a ecarte qu'un modele, alors que son quota se compte "
        "par cle — le bot va retaper dans le mur avec l'echelon suivant."
    )


@pytest.mark.parametrize("code", [401, 403])
def test_une_cle_revoquee_le_reste_pour_tous_les_modeles(code):
    """401/403 parlent de la CLE elle-meme : aucun modele ne la sauve."""
    mgr = _manager()
    mgr.report_error("gemini", "key1", code, modele=VISION)
    assert mgr.is_api_available("gemini", modele=TEXTE) is False


@pytest.mark.parametrize("code", [503, 500, 408, 529, 400])
def test_une_erreur_de_modele_ne_pose_toujours_aucun_seau(code):
    """Inchange : ces codes parlent du modele ou de la requete, pas du quota."""
    mgr = _manager()
    mgr.report_error("gemini", "key1", code, modele=VISION)
    assert mgr.is_api_available("gemini", modele=VISION) is True
    assert mgr.apis["gemini"]["status"]["key1"]["cooldown_modele"] == {}


def test_la_rotation_sert_une_autre_cle_pour_le_modele_sature():
    """Deux cles, un modele sature sur la premiere : la seconde prend le relais."""
    mgr = _manager(cles=("key1", "key2"))
    mgr.report_error("gemini", "key1", 429, retry_delay_s=60, modele=VISION)
    servies = {mgr.get_key("gemini", modele=VISION) for _ in range(4)}
    assert servies == {"key2"}, f"cles servies pour un modele sature sur key1 : {servies}"


# --------------------------------------------------------------------------------------
# Le cablage : 7 copies du gestionnaire, 11 cascades. Et il faut les onze.
# --------------------------------------------------------------------------------------
# ⚠️ « fait sur les 6 » l'est presque toujours sur 5 : on compte, et on derive le compte
# de la liste de depart, jamais de la boucle.

def _copies_du_gestionnaire():
    return [RACINE / "shared" / "api_manager.py"] + [
        RACINE / bot / "core" / "api_manager.py" for bot in BOTS
    ]


@pytest.mark.parametrize("chemin", _copies_du_gestionnaire(),
                         ids=lambda c: f"{c.parent.name}/{c.name}")
def test_chaque_copie_du_gestionnaire_connait_le_quota_par_modele(chemin):
    arbre = ast.parse(chemin.read_text(encoding="utf-8"), filename=str(chemin))
    signatures = {
        n.name: [a.arg for a in n.args.args] + [a.arg for a in n.args.kwonlyargs]
        for n in ast.walk(arbre)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for methode in ("report_error", "get_key", "is_api_available"):
        assert "modele" in signatures.get(methode, []), (
            f"{chemin}::{methode} ignore le modele : cette copie pose encore la "
            "quarantaine sur la CLE entiere."
        )
    assert "QUOTA_PAR_MODELE" in chemin.read_text(encoding="utf-8")


def test_les_7_copies_sont_bien_toutes_inspectees():
    copies = _copies_du_gestionnaire()
    assert len(copies) == 7
    manquantes = [str(c) for c in copies if not c.exists()]
    assert not manquantes, f"copie introuvable : {manquantes}"


def _toutes_les_cascades():
    chemins = [RACINE / "shared" / "llm_cascade.py"]
    chemins += [RACINE / bot / "core" / "llm_cascade.py" for bot in BOTS]
    chemins += [RACINE / rel for rel in CASCADES_INLINE.values()]
    return chemins


def _fonctions_de_cascade(source, chemin):
    """Les fonctions qui portent une boucle `for client_type, model_name in cascade`."""
    arbre = ast.parse(source, filename=str(chemin))
    trouvees = []
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for interne in ast.walk(noeud):
            if (isinstance(interne, ast.For)
                    and isinstance(interne.target, ast.Tuple)
                    and [getattr(el, "id", None) for el in interne.target.elts]
                        == ["client_type", "model_name"]):
                trouvees.append(noeud)
                break
    return trouvees


@pytest.mark.parametrize("chemin", _toutes_les_cascades(),
                         ids=lambda c: f"{c.parent.name}/{c.name}")
def test_chaque_cascade_nomme_le_modele_en_signalant_l_erreur(chemin):
    """⚠️ Exiger l'APPEL avec son argument, pas le NOM quelque part dans le fichier.

    Un `report_error` sans `modele=` est exactement le defaut d'origine : il condamne les
    cinq autres echelons de la meme cle.
    """
    source = chemin.read_text(encoding="utf-8")
    fonctions = _fonctions_de_cascade(source, chemin)
    assert fonctions, f"{chemin} : aucune boucle de cascade trouvee"
    for fonction in fonctions:
        appels = [n for n in ast.walk(fonction)
                  if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Attribute)
                  and n.func.attr == "report_error"]
        assert appels, f"{chemin}::{fonction.name} : plus aucun report_error"
        for appel in appels:
            nomme = {kw.arg: kw.value for kw in appel.keywords}
            assert getattr(nomme.get("modele"), "id", None) == "model_name", (
                f"{chemin}::{fonction.name} signale son 429 sans nommer le modele : la "
                "cle entiere part en quarantaine, echelons intacts compris."
            )


@pytest.mark.parametrize("chemin", _toutes_les_cascades(),
                         ids=lambda c: f"{c.parent.name}/{c.name}")
def test_chaque_cascade_demande_sa_cle_pour_le_modele_vise(chemin):
    """Le sens lecture : sans `modele`, la cascade saute un echelon dont le seau est plein."""
    source = chemin.read_text(encoding="utf-8")
    for fonction in _fonctions_de_cascade(source, chemin):
        appels = [n for n in ast.walk(fonction)
                  if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Name)
                  and n.func.id == "_cle_du_pool"]
        assert appels, f"{chemin}::{fonction.name} : plus aucun _cle_du_pool"
        for appel in appels:
            nomme = {kw.arg: kw.value for kw in appel.keywords}
            assert getattr(nomme.get("modele"), "id", None) == "model_name", (
                f"{chemin}::{fonction.name} demande sa cle sans nommer le modele."
            )


def test_les_11_cascades_sont_bien_toutes_la():
    chemins = _toutes_les_cascades()
    assert len(chemins) == 11
    manquants = [str(c) for c in chemins if not c.exists()]
    assert not manquants, f"cascade introuvable : {manquants}"


def test_la_liste_des_fournisseurs_par_modele_reste_fermee():
    """Une mesure, pas une intuition : Google est le seul a documenter un seau par modele."""
    assert set(QUOTA_PAR_MODELE) == {"gemini"}, (
        "QUOTA_PAR_MODELE a change : chez un fournisseur qui compte par CLE, un 429 "
        "n'ecarterait plus qu'un modele et le bot retaperait dans le mur. Mesurer avant."
    )
