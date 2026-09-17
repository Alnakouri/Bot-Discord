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
    # Le nettoyage a demenage dans `filtre_sortie` le 2026-09-17 (il est desormais partage
    # avec le harnais d'evaluation, cf. tests/test_verrou_filtre_sortie.py) : l'invariant
    # n'a pas bouge d'un pouce, seul l'endroit ou il se verifie a change.
    src = open(os.path.join(_sheo_dir, "sheo_llm.py"), encoding="utf-8").read()
    corps = src.split("def filtre_sortie")[1].split("\ndef ")[0]
    i_echo = corps.index("_strip_echo_opening(texte")
    i_md = corps.index("strip_markdown_emphasis(texte)")
    assert i_echo < i_md, (
        "strip_markdown_emphasis passe AVANT _strip_echo_opening : le detecteur d'echo "
        "ne verra plus le markdown sur lequel il s'appuie."
    )


# ---------------------------------------------------------------------------
# Le CORPS de la reponse : la ou les vrais tics vivent
# ---------------------------------------------------------------------------
#
# Mesure du 2026-09-06 sur les 8 vraies reponses de Sheo a LeDev
# (data/sheogorath_memory.json) : le moule « Haskill, <ordre> » tenait 7 repliques
# sur 8. Position de « Haskill » : 103, 117, 126, 175, 220... Le filet AMORCE
# (5 premiers mots) l'attrapait 2 fois sur 7 ; le filet CLOTURE, 0 sur 7.

# Extrait fidele du transcript live, raccourci. Le moule est au MILIEU a chaque fois.
REPLIQUES_LIVE = [
    "Ah, mortel, tu invoques le Prince comme un mauvais sort. Je te nomme Grand "
    "Chambellan de Bliss, charge de distribuer des papillons. Haskill, prepare une "
    "tasse de the qui chante.",
    "Un papillon vient de me murmurer que les etoiles portent des chapeaux de "
    "confiture. Haskill, prepare un Wabbajack a la sauce caramel.",
    "Alors, je te prepare un trone de cornichons chantants, nappe de fromage. "
    "Haskill, apporte les chandelles en forme de papillons.",
]


def test_le_moule_du_milieu_est_enfin_vu():
    """⚠️ Le test que les deux anciens filets ne pouvaient pas ecrire.

    « Haskill » n'est ni dans les 5 premiers mots ni dans les 5 derniers d'aucune de
    ces repliques : amorce et cloture le laissaient passer, replique apres replique.
    """
    from sheo_llm import _motifs_recurrents

    motifs = _motifs_recurrents(REPLIQUES_LIVE)
    assert "haskill" in motifs, f"le tic mesure a 7/8 n'est toujours pas vu : {motifs}"
    assert "papillons" in motifs


def test_un_mot_dit_une_seule_fois_n_est_pas_un_tic():
    """Le seuil est a 2 : interdire ce qui n'a servi qu'une fois etoufferait la prose."""
    from sheo_llm import _motifs_recurrents

    motifs = _motifs_recurrents(REPLIQUES_LIVE)
    assert "caramel" not in motifs, f"« caramel » n'apparait qu'une fois : {motifs}"
    assert "wabbajack" not in motifs


def test_les_mots_outils_ne_comptent_pas():
    """« dans », « pour », « comme » reviennent toujours et ne disent rien d'un tic."""
    from sheo_llm import _motifs_recurrents

    motifs = _motifs_recurrents(REPLIQUES_LIVE)
    assert not ({"dans", "pour", "comme", "avec"} & set(motifs)), motifs


@pytest.mark.parametrize("message, mot_libere", [
    ("ta tete de cornichon ?", "cornichons"),      # singulier -> pluriel
    ("parle-moi des papillons", "papillons"),      # pluriel -> pluriel
    ("j'adore le fromage", "fromage"),
])
def test_le_sujet_de_la_conversation_n_est_jamais_interdit(message, mot_libere):
    """⚠️ On interdit la rengaine, jamais le SUJET.

    Si le mortel ecrit « ta tete de cornichon ? », Sheo doit pouvoir lui repondre
    cornichons. Le rapprochement se fait sur le radical : sans ca, le singulier de
    l'utilisateur ne couvrait pas le pluriel du bot et on lui coupait la conversation.
    """
    from sheo_llm import _motifs_recurrents

    # `maxi` releve : sans ca le plafond de 6 mots ferait sortir « cornichons » de la
    # liste pour une raison qui n'a RIEN a voir avec l'exclusion qu'on teste ici.
    doublees = REPLIQUES_LIVE + REPLIQUES_LIVE
    sans = _motifs_recurrents(doublees, maxi=50)
    avec = _motifs_recurrents(doublees, message_utilisateur=message, maxi=50)
    assert mot_libere in sans, f"le test ne prouve rien si « {mot_libere} » n'etait pas interdit"
    assert mot_libere not in avec, f"« {mot_libere} » reste interdit alors que le mortel en parle"


def test_la_consigne_porte_bien_la_section_du_corps():
    """Le filet doit arriver JUSQU'AU prompt, pas seulement exister dans un helper."""
    from sheo_llm import build_anti_tic_consigne

    consigne = build_anti_tic_consigne(REPLIQUES_LIVE)
    assert "DANS LE CORPS" in consigne
    assert "haskill" in consigne.lower()


def test_entrees_vides_rendent_une_consigne_vide():
    from sheo_llm import _motifs_recurrents, build_anti_tic_consigne

    assert _motifs_recurrents([]) == []
    assert _motifs_recurrents(None) == []
    assert _motifs_recurrents([None, "", "   "]) == []
    assert build_anti_tic_consigne([]) == ""


def test_le_message_de_l_utilisateur_est_VRAIMENT_passe_par_le_bot():
    """⚠️ Un test qui cherche le NOM du parametre passerait au vert sur la signature
    seule. On exige l'APPEL, avec son argument, dans `bot_sheogorath.py`."""
    import ast
    import os

    chemin = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "Sheogorath", "bot_sheogorath.py")
    with open(chemin, encoding="utf-8") as f:
        arbre = ast.parse(f.read(), filename=chemin)

    appels = [n for n in ast.walk(arbre)
              if isinstance(n, ast.Call)
              and isinstance(n.func, ast.Name)
              and n.func.id == "build_anti_tic_consigne"]
    assert appels, "build_anti_tic_consigne n'est plus appele du tout"
    for appel in appels:
        noms = {k.arg for k in appel.keywords}
        assert "message_utilisateur" in noms, (
            "le message du mortel n'est pas transmis : le filet interdirait alors le "
            "SUJET de la conversation, pas seulement la rengaine."
        )


# ═══════════════════════════════════════════════════════════════════════════════════════
# Le prompt ne doit pas ENSEIGNER le tic que le filet interdit
# ═══════════════════════════════════════════════════════════════════════════════════════


def _phrases_des_litteraux(chemin):
    """Toutes les phrases de toutes les chaines du fichier persona."""
    import ast
    import re

    with open(chemin, encoding="utf-8") as f:
        arbre = ast.parse(f.read(), filename=chemin)
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Constant) and isinstance(noeud.value, str):
            for phrase in re.split(r"(?<=[.!?])\s+|\n", noeud.value):
                phrase = phrase.strip()
                if phrase:
                    yield phrase


def test_la_persona_ne_DEMONTRE_plus_le_moule_Haskill():
    """⚠️ Test live du 2026-09-08 : le moule « Haskill, <ordre> » revient dans 3 repliques
    sur 4, alors que le filet anti-tics venait d'etre deploye et interdisait bien le mot
    (verifie en rejouant les 4 repliques).

    La cause n'etait pas le filet : `sheo_data.py` PRESCRIVAIT le moule (« appel a
    Haskill » listee comme facon de clore) et le DEMONTRAIT — 3 des 15 exemples few-shot,
    dont 5 sont tires au hasard a chaque message, plus 4 exemples d'humeur. Le prompt
    montrait donc le tic ~2 fois pendant qu'une ligne le lui interdisait. Une
    demonstration bat une interdiction.

    Ce test interdit la DEMONSTRATION, pas le personnage : « je comptais les dents de
    Haskill » reste parfaitement legitime. Ce qui est banni, c'est une phrase qui
    COMMENCE par un ordre lance a Haskill — le moule lui-meme."""
    import os

    chemin = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "Sheogorath", "sheo_data.py")

    fautives = [p for p in _phrases_des_litteraux(chemin) if p.startswith("Haskill,")]
    assert not fautives, (
        "la persona demontre a nouveau le moule « Haskill, <ordre> » ; le filet "
        "anti-tics ne peut pas gagner contre un exemple :\n  " + "\n  ".join(fautives))


def test_la_persona_ne_PRESCRIT_plus_Haskill_comme_facon_de_clore():
    """La regle « MAITRE DU JEU » proposait « appel a Haskill » parmi les facons de
    reprendre la main. Nommer un tiers precis dans une liste de sorties, c'est en faire
    la sortie par defaut."""
    import os

    chemin = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "Sheogorath", "sheo_data.py")
    with open(chemin, encoding="utf-8") as f:
        source = f.read()

    assert "appel à Haskill" not in source, (
        "« appel à Haskill » est de retour dans les facons de clore : c'est ce qui "
        "fabriquait le moule que le filet passe son temps a interdire.")
