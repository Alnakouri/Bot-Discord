import pytest
from pathlib import Path

from shared.transcript import ligne_de_contexte

class FakeAuthor:
    def __init__(self, name, mention, bot):
        self.name = name
        self.mention = mention
        self.bot = bot
    
    def __eq__(self, other):
        if not isinstance(other, FakeAuthor):
            return False
        return self.name == other.name

class FakeMessage:
    def __init__(self, author, content):
        self.author = author
        self.content = content

def test_trace_remplace_verbatim_pour_autre_bot():
    moi = FakeAuthor("MoiBot", "@Moi", True)
    autre = FakeAuthor("AutreBot", "@Autre", True)
    msg = FakeMessage(autre, "Un contenu secret et prive")
    
    res = ligne_de_contexte(msg, moi)
    assert "[a repondu]" in res
    assert "Un contenu secret et prive" not in res
    assert "AutreBot" in res

def test_bot_se_voit_lui_meme():
    moi = FakeAuthor("MoiBot", "@Moi", True)
    msg = FakeMessage(moi, "Mon propre message")
    
    res = ligne_de_contexte(msg, moi, avec_mention=True)
    assert "Mon propre message" in res
    assert "MoiBot (@Moi)" in res

def test_cas_johnny_reconstitue():
    # Historique du 04/09 (sheo, reponse de Sheo, chut, reponse de Sheo, @M'aiq, reponse de M'aiq, @Johnny silverhand)
    johnny = FakeAuthor("Johnny", "@Johnny", True)
    sheo = FakeAuthor("Sheogorath", "@Sheo", True)
    maiq = FakeAuthor("Maiq", "@Maiq", True)
    user = FakeAuthor("ledev", "@BB", False)
    
    historique = [
        FakeMessage(user, "sheo"),
        FakeMessage(sheo, "Je suis la!"),
        FakeMessage(user, "chut"),
        FakeMessage(sheo, "D'accord..."),
        FakeMessage(user, "@M'aiq"),
        FakeMessage(maiq, "M'aiq ecoute."),
        FakeMessage(user, "@Johnny silverhand")
    ]
    
    transcript = ""
    for hist_msg in historique:
        ligne = ligne_de_contexte(hist_msg, johnny, avec_mention=False)
        if ligne:
            transcript += ligne
            
    assert "Sheogorath : [a repondu]" in transcript
    assert "Je suis la!" not in transcript
    assert "Maiq : [a repondu]" in transcript
    assert "M'aiq ecoute." not in transcript
    assert "ledev: @Johnny silverhand" in transcript

def test_les_5_bots_utilisent_le_helper():
    """⚠️ Verifier l'APPEL, pas l'occurrence du nom.

    La premiere version de ce test se contentait de `"ligne_de_contexte" in contenu` :
    JohnnyBot **importait** le helper sans jamais l'appeler — sa boucle gardait le
    `continue` qui efface les autres bots — et le test etait vert. Un import n'est pas
    un cablage.
    """
    racine = Path(__file__).resolve().parent.parent
    bots = ["Alfred", "JohnnyBot", "MaiqBot", "Sheogorath", "SugarBot"]
    trouves = 0
    for bot in bots:
        dossier = racine / bot
        fichiers_bot = list(dossier.glob("bot_*.py"))
        assert len(fichiers_bot) == 1
        fichier = fichiers_bot[0]
        contenu = fichier.read_text(encoding="utf-8")

        assert "from core.transcript import ligne_de_contexte" in contenu, (
            f"{fichier.name} n'importe pas le helper depuis le noyau vendorise !"
        )
        assert "ligne = ligne_de_contexte(hist_msg, bot.user" in contenu, (
            f"{fichier.name} importe le helper mais ne l'APPELLE pas dans sa boucle !"
        )
        assert "if hist_msg.author.bot and hist_msg.author != bot.user:" not in contenu, (
            f"{fichier.name} efface encore les autres bots du transcript "
            f"(le `continue` de [[plan-silence-total-bots]] est toujours la)."
        )
        trouves += 1

    assert trouves == 5, f"On attendait 5 fichiers inspectes, on en a eu {trouves}"


def test_les_5_bots_compilent():
    """Un import colle en colonne 0 dans un corps de fonction ne se voit qu'ici."""
    import py_compile
    racine = Path(__file__).resolve().parent.parent
    bots = ["Alfred", "JohnnyBot", "MaiqBot", "Sheogorath", "SugarBot"]
    compiles = 0
    for bot in bots:
        fichiers_bot = list((racine / bot).glob("bot_*.py"))
        assert len(fichiers_bot) == 1
        py_compile.compile(str(fichiers_bot[0]), doraise=True)
        compiles += 1
    assert compiles == 5


def test_les_deux_listes_de_vendoring_sont_alignees():
    """⚠️ `transcript.py` devait etre ajoute a DEUX listes en dur, pas une.

    `tools/vendor_core.py` copie, `tools/sonde_core_drift.py` verifie. Un module present
    dans la premiere et absent de la seconde est copie **sans jamais etre surveille**.
    """
    import sys
    racine = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(racine / "tools"))
    try:
        import vendor_core
        import sonde_core_drift
    finally:
        sys.path.pop(0)
    assert vendor_core.MODULES == sonde_core_drift.MODULES, (
        "Les listes MODULES de vendor_core.py et sonde_core_drift.py ont diverge : "
        f"{set(vendor_core.MODULES) ^ set(sonde_core_drift.MODULES)}"
    )
    assert "transcript.py" in vendor_core.MODULES


def test_module_est_vendorise():
    racine = Path(__file__).resolve().parent.parent
    bots = ["Alfred", "JohnnyBot", "MaiqBot", "MalenaBot", "Sheogorath", "SugarBot"]
    source_path = racine / "shared" / "transcript.py"
    source = source_path.read_text(encoding="utf-8")
    
    trouves = 0
    for bot in bots:
        copie = racine / bot / "core" / "transcript.py"
        assert copie.exists(), f"La copie manque pour {bot}"
        # On ne compare pas le contenu exact car vendor_core.py ajoute un header
        contenu_copie = copie.read_text(encoding="utf-8")
        assert "def ligne_de_contexte(" in contenu_copie
        trouves += 1
        
    assert trouves == 6
