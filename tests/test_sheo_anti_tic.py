# -*- coding: utf-8 -*-
import os
import sys
import pytest

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)
_sheo_dir = os.path.join(_parent_dir, "Sheogorath")
if _sheo_dir not in sys.path:
    sys.path.insert(0, _sheo_dir)

from sheo_llm import build_anti_tic_consigne, _strip_echo_opening

def test_anti_tic_empty_or_none():
    assert build_anti_tic_consigne(None) == ""
    assert build_anti_tic_consigne([]) == ""
    assert build_anti_tic_consigne(["", None, "   "]) == ""

def test_anti_tic_extraction():
    recent = [
        "Bonjour mon cher mortel ! J'adore le fromage. 🧀",
        "<thought>Pensée</thought> Silence, ver de terre ! Haskill, apporte les cuillères. 🥄",
    ]
    consigne = build_anti_tic_consigne(recent)
    
    assert "[ANTI-TICS — VARIE OU MEURS]" in consigne
    # Amorces attendues normalisées (minuscules, sans ponctuation de bord, max 5 mots)
    # "Bonjour mon cher mortel ! J'adore le fromage." -> "bonjour mon cher mortel j'adore"
    # "Silence, ver de terre ! Haskill, apporte les cuillères." -> "silence ver de terre haskill"
    assert '"bonjour mon cher mortel j\'adore"' in consigne
    assert '"silence ver de terre haskill"' in consigne

    # Clôtures attendues (dernière phrase normalisée, max 5 mots, emoji retiré)
    # "J'adore le fromage." -> "j'adore le fromage"
    # "Haskill, apporte les cuillères." -> "haskill apporte les cuillères"
    assert '"j\'adore le fromage"' in consigne
    assert '"haskill apporte les cuillères"' in consigne

def test_anti_tic_thought_tag_ignored():
    recent = [
        "<thought>Ne dis rien</thought> Pourquoi cette question stupide ? 🥱"
    ]
    consigne = build_anti_tic_consigne(recent)
    assert '"pourquoi cette question stupide"' in consigne


# --- _strip_echo_opening : tue l'ouverture-perroquet HURLÉE, épargne le reste ---

def test_echo_shouted_caps_stripped():
    # Ouverture qui HURLE l'insulte en écho → coupée, la vanne survit.
    reply = 'Oh, "FACE DE PET" ! Tes insultes sont des haïkus scatologiques, barbare des latrines ! 🎺'
    out = _strip_echo_opening(reply, "sheo la face de pet")
    assert not out.lower().startswith("oh")
    assert "haïkus scatologiques" in out

def test_echo_interjection_then_caps_stripped():
    # Interjection « Ah... » PUIS écho hurlé → les deux sautent, la morsure reste.
    reply = 'Ah... "TÊTE DE CUL"... Espèce de misérable, je te réduis en poussière ! 🔪'
    out = _strip_echo_opening(reply, "çava tete de cul ?")
    assert "misérable" in out
    assert "tête de cul" not in out.lower()

def test_normal_case_reflection_preserved():
    # Écho en casse NORMALE sur une remarque anodine (canon) → JAMAIS touché.
    reply = "Des pâtes ? Sans la moindre meule de fromage ? Quel sacrilège ! 🧀"
    assert _strip_echo_opening(reply, "j'ai mangé des pâtes") == reply

def test_all_caps_easter_egg_preserved():
    # Cri intégral en majuscules (easter egg) → JAMAIS touché.
    reply = "SILENCE, MORTEL ! LE PRINCE A PARLÉ ! 👑"
    assert _strip_echo_opening(reply, "sheo tais toi") == reply

def test_non_echo_opening_untouched():
    # Ouverture qui n'échote pas le mortel → intacte.
    reply = "Quelle audace délicieuse ! Haskill, apporte la laitue. 🥬"
    assert _strip_echo_opening(reply, "tu es nul") == reply

def test_empty_inputs():
    assert _strip_echo_opening("", "insulte") == ""
    assert _strip_echo_opening("Une réponse.", "") == "Une réponse."


def test_quoted_echo_stripped():
    reply = '« "Tu parles trop" ? Mais mon cher pirate… la suite de ton voyage approche. »'
    out = _strip_echo_opening(reply, "tu parle trop")
    assert "Mais mon cher" in out
    assert "tu parles trop" not in out.lower()

    reply = 'Oh, "tu parles trop" ? Haha ! Toi qui m\'invoques pour râler.'
    out = _strip_echo_opening(reply, "tu parles trop")
    assert "Toi qui m'invoques" in out
    assert "tu parles trop" not in out.lower()

    reply = "Des pâtes ? Sans la moindre meule…"
    assert _strip_echo_opening(reply, "j'ai mangé des pâtes") == reply

    reply = '"Nul" ? C\'est petit.'
    assert _strip_echo_opening(reply, "t'es nul") == reply


from sheo_llm import sentence_budget

def test_sentence_budget():
    # Par défaut (limite à 4 phrases)
    assert sentence_budget("t'es nul") == 4
    assert sentence_budget("es-tu fou ?") == 4
    assert sentence_budget("oui") == 4
    
    # Avec invitation (limite à 10 phrases)
    assert sentence_budget("raconte-moi une histoire") == 10
    assert sentence_budget("explique-moi la Marche Grise") == 10
    assert sentence_budget("continue") == 10
    assert sentence_budget("RACONTE") == 10


def test_force_short_response_cuts_newline_separated():
    # RÉGRESSION (bug live 2026-07-15) : Mistral sépare ses phrases par des SAUTS DE LIGNE
    # sur Discord. Le filet doit compter ces phrases (frontière = ponctuation + \s, pas ' ')
    # et couper à 4, sinon Sheo débordait sur Discord alors que Twitch (mono-ligne) tenait.
    from sheo_llm import force_short_response
    txt = "Une.\nDeux.\nTrois.\nQuatre.\nCinq.\nSix. 🧀"
    out = force_short_response(txt, max_sentences=4)
    assert "Cinq" not in out and "Six" not in out
    assert out.endswith("🧀")



from sheo_llm import postprocess_response, strip_markdown_emphasis


@pytest.fixture(autouse=True)
def _sceller_les_easter_eggs(monkeypatch):
    """⚠️ `postprocess_response` tire un easter egg au sort : 2 % de ALL CAPS EXPLOSION,
    qui MET TOUTE LA SORTIE EN MAJUSCULES.

    Le 2026-09-06, `assert "Haskill" in sortie` est tombe en pleine suite : la sortie
    disait « HASKILL ». Un test qui depend d'un tirage n'est pas un test — c'est la
    quatrieme fois dans ce depot, apres les 3 du mode IMPOSTEUR (`830be3c`). Ces tests
    portent sur le nettoyage du texte, jamais sur le grain de folie : on scelle.
    """
    import sheo_llm
    monkeypatch.setattr(sheo_llm.random, "random", lambda: 1.0)

# ---------------------------------------------------------------------------
# Le markdown : un trou dans le filet, et une regle de prompt qui ne tient pas
# ---------------------------------------------------------------------------

def test_l_echo_entoure_de_markdown_est_coupe():
    """⚠️ `*Nul* ?!` passait a travers `_strip_echo_opening`.

    Sonde du 2026-09-04 : un modele a ouvert par `*Nul* ?!` — exactement le gabarit que le
    prompt de Sheogorath donne en exemple d'INTERDIT. Il est passe parce que ce n'etait ni
    un cri (pas de MAJUSCULES) ni une citation reconnue : le detecteur connaissait `"..."`,
    `«...»`, `“...”` et `'...'`, mais **pas le markdown**.
    """
    sortie = postprocess_response(
        "Haha ! *Nul* ?! Mon petit mortel, tu confonds tout. Va compter les dents de Haskill. 😈",
        None, 1, "t'es nul", max_sentences=4)
    assert "Nul ?!" not in sortie, f"l'echo interdit a survecu : {sortie}"
    assert "Haskill" in sortie, f"la vraie vanne a ete emportee : {sortie}"


def test_l_echo_anodin_en_casse_normale_reste():
    """⚠️ Le canon l'AUTORISE : « Des pâtes ? » est une reflexion voulue, pas un echo hurle.

    Sans ce test, durcir le detecteur reviendrait a supprimer un trait de personnage.
    """
    sortie = postprocess_response(
        "Des pâtes ? Voilà qui mérite un décret. Haskill, note ça. 🤔",
        None, 1, "j'ai mangé des pâtes", max_sentences=4)
    assert sortie.startswith("Des pâtes ?"), f"reflexion canon supprimee : {sortie}"


def test_les_asterisques_sont_retirees():
    """Le prompt les INTERDIT, le modele en met quand meme 9 fois sur 9.

    Mesure du 2026-09-04 (sonde des 6 personas x 3 modeles Mistral) : Sheogorath est le
    SEUL bot dont le prompt interdise explicitement les asterisques — et le SEUL a 9/9.
    Le taux le plus eleve des six. Une regle de prompt oriente ; seul un filet
    deterministe garantit.
    """
    assert strip_markdown_emphasis("Je suis **le PRINCE**, et *toi* un ver.") \
        == "Je suis le PRINCE, et toi un ver."
    # ⚠️ Ne pas amputer un pseudo : `_` n'est retire qu'entre limites de mots.
    assert strip_markdown_emphasis("Salut le_dev.") == "Salut le_dev."
    assert strip_markdown_emphasis("") == ""
    assert strip_markdown_emphasis(None) is None


def test_le_nettoyage_passe_APRES_le_detecteur_d_echo():
    """⚠️ L'ordre est le correctif, pas un detail.

    Nettoyer les asterisques AVANT `_strip_echo_opening` lui retire le marqueur `*...*`
    sur lequel il reconnait l'echo : `*Nul* ?!` redevient `Nul ?!`, en casse normale, donc
    autorise — et il ressort en clair. C'est le bug qu'a produit la premiere version.
    """
    src = open(os.path.join(_sheo_dir, "sheo_llm.py"), encoding="utf-8").read()
    corps = src.split("def postprocess_response")[1]
    i_echo = corps.index("_strip_echo_opening(response_text")
    i_md = corps.index("strip_markdown_emphasis(response_text)")
    assert i_echo < i_md, (
        "strip_markdown_emphasis passe AVANT _strip_echo_opening : le detecteur d'echo "
        "ne verra plus le markdown sur lequel il s'appuie."
    )
