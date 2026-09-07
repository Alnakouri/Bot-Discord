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

import sheo_data

def test_sheo_moods_exist_and_contain_placeholder():
    assert "neutral" in sheo_data.MOOD_PROMPTS
    assert "mania" in sheo_data.MOOD_PROMPTS
    assert "dementia" in sheo_data.MOOD_PROMPTS
    assert "bliss" in sheo_data.MOOD_PROMPTS
    
    for mood, prompt in sheo_data.MOOD_PROMPTS.items():
        assert "{comebacks_placeholder}" in prompt, f"Mood {mood} prompt is missing the comebacks placeholder"

def test_sheo_moods_are_distinct():
    neutral = sheo_data.MOOD_PROMPTS["neutral"]
    mania = sheo_data.MOOD_PROMPTS["mania"]
    dementia = sheo_data.MOOD_PROMPTS["dementia"]
    bliss = sheo_data.MOOD_PROMPTS["bliss"]
    
    assert neutral != mania
    assert neutral != dementia
    assert neutral != bliss
    assert mania != dementia
    assert mania != bliss
    assert dementia != bliss
    
    # Check that they contain distinct comedy examples
    assert "[EXEMPLES DE RÉPARTIE (HUMEUR : NEUTRE)]" in neutral
    assert "[EXEMPLES DE RÉPARTIE (HUMEUR : MANIA)]" in mania
    assert "[EXEMPLES DE RÉPARTIE (HUMEUR : DEMENTIA)]" in dementia
    assert "[EXEMPLES DE RÉPARTIE (HUMEUR : BLISS)]" in bliss

import sheo_llm

def test_no_tts_brackets_in_fewshot():
    for name in ["COMEDY_EXAMPLES_NEUTRAL", "COMEDY_EXAMPLES_MANIA", "COMEDY_EXAMPLES_DEMENTIA", "COMEDY_EXAMPLES_BLISS"]:
        val = getattr(sheo_data, name)
        for tag in ["[laugh]", "[chuckle]", "[sigh]", "[shout]"]:
            assert tag not in val.lower(), f"{name} contains forbidden TTS tag {tag}"

def test_clean_strips_tts_tags():
    input_text = "Haha ! [laugh] Voyez ça [sigh]"
    cleaned = sheo_llm.clean_internal_tags(input_text)
    assert "[laugh]" not in cleaned
    assert "[sigh]" not in cleaned
    assert cleaned == "Haha ! Voyez ça"

import re
from shared.twitch.sanitize import strip_stage_directions

def test_sheo_tutoie():
    for trigger, reply in sheo_data.COMEBACK_POOL:
        assert not re.search(r"\b(vous|votre)\b", reply, re.IGNORECASE), f"COMEBACK_POOL reply contains vous/votre: {reply}"
    
    for name in ["COMEDY_EXAMPLES_NEUTRAL", "COMEDY_EXAMPLES_MANIA", "COMEDY_EXAMPLES_DEMENTIA", "COMEDY_EXAMPLES_BLISS"]:
        val = getattr(sheo_data, name)
        assert not re.search(r"\b(vous|votre)\b", val, re.IGNORECASE), f"{name} contains vous/votre: {val}"

def test_strip_prose_stage_directions():
    text1 = "Haha ! <Un silence. Puis un chuchotement rauque...> Tu as peur ?"
    cleaned1 = strip_stage_directions(text1)
    assert cleaned1 == "Haha ! Tu as peur ?"
    
    text2 = "Non ! un soupir théâtral C'est faux."
    cleaned2 = strip_stage_directions(text2)
    assert cleaned2 == "Non ! C'est faux."
    
    text3 = "Viens voir <@1234567890> ! C'est le boss."
    cleaned3 = strip_stage_directions(text3)
    assert cleaned3 == "Viens voir <@1234567890> ! C'est le boss."


def test_writing_rendering_prompts():
    # Verify PERSONALITY_BASE contains the RENDU ÉCRIT DE TON ÉTAT block
    assert "RENDU ÉCRIT DE TON ÉTAT" in sheo_data.PERSONALITY_BASE
    
    # Verify NEUTRAL, MANIA, DEMENTIA, BLISS mood prompts contain their respective instructions
    neutral = sheo_data.MOOD_PROMPTS["neutral"]
    mania = sheo_data.MOOD_PROMPTS["mania"]
    dementia = sheo_data.MOOD_PROMPTS["dementia"]
    bliss = sheo_data.MOOD_PROMPTS["bliss"]
    
    assert "casse NORMALE" in neutral
    assert "calme glacial" in neutral
    
    assert "tu es BRUYANT" in mania
    assert "MAJUSCULES giclent" in mania
    
    assert "tu CHUCHOTES" in dementia
    assert "AUCUN cri" in dementia
    assert "AUCUNE majuscule" in dementia

    assert "FOU JOVIAL & LUCIDE" in bliss
    assert "casse normale et chaleureuse" in bliss


def test_sheo_new_behaviors():
    # Verify PERSONALITY_BASE is included in PERSONALITY_BLISS
    assert sheo_data.PERSONALITY_BASE in sheo_data.PERSONALITY_BLISS
    
    # Verify transversal blocks Phase A (double-sens) and Phase B (conteur) are in PERSONALITY_BASE
    assert "CAPRICE À DOUBLE SENS" in sheo_data.PERSONALITY_BASE
    assert "EXCEPTION DU CONTEUR" in sheo_data.PERSONALITY_BASE
    
    # Verify they are therefore in all 4 moods
    for mood, prompt in sheo_data.MOOD_PROMPTS.items():
        assert "CAPRICE À DOUBLE SENS" in prompt, f"Mood {mood} prompt is missing Phase A block"
        assert "EXCEPTION DU CONTEUR" in prompt, f"Mood {mood} prompt is missing Phase B block"


def test_sheo_length_rules():
    assert "QUI DÉCIDE DE LA LONGUEUR" in sheo_data.PERSONALITY_BASE
    assert "jamais en défense" in sheo_data.PERSONALITY_BASE
    assert "4 MAXIMUM" in sheo_data.PERSONALITY_BASE
    assert "INVITE EXPLICITEMENT" in sheo_data.PERSONALITY_BASE




# ---------------------------------------------------------------------------
# Les enveloppes vides : chaque nettoyeur retire un contenu, aucun ne ramassait
# le delimiteur devenu vide
# ---------------------------------------------------------------------------

def test_une_enveloppe_videe_de_son_contenu_disparait_aussi():
    """⚠️ Constate en live le 2026-09-06, message `!neutre` de LeDev.

    La reponse de Sheo se terminait par « ...lors de ta prochaine crise de rage ? 🎩 () »
    — la parenthese vide est bien en base, ce n'est pas un artefact d'affichage.

    Le mecanisme est generique : `clean_internal_tags` retire `[laugh]`,
    `strip_markdown_emphasis` retire `*rire*`, l'extracteur de faits retire
    `<fact>...</fact>`. Aucun ne regarde le delimiteur qui les entourait.
    """
    from sheo_llm import clean_internal_tags

    assert clean_internal_tags("Va compter les dents. 🎩 ([laugh])").endswith("🎩")
    assert "()" not in clean_internal_tags("Haskill ! ([laugh]) Apporte le the.")
    assert "[]" not in clean_internal_tags("Un ordre [<fact>x</fact>] et puis rien.")


def test_une_enveloppe_qui_contient_encore_quelque_chose_est_intacte():
    """Le nettoyage ne doit pas manger une vraie parenthese : `(vraiment)` reste."""
    from sheo_llm import clean_internal_tags

    sortie = clean_internal_tags("Un cornichon (vraiment) chantant.")
    assert "(vraiment)" in sortie


# ---------------------------------------------------------------------------
# La ponctuation ORPHELINE : celle qui rattachait le morceau retire
# ---------------------------------------------------------------------------

def test_une_virgule_orpheline_en_tete_de_replique_disparait():
    """⚠️ Constate en live le 2026-09-07 a 18:37 (journal du conteneur : 16:37:36).

    Sheogorath a repondu, mot pour mot :

        « , @LeDev. Tu penses vraiment dompter le vent en le nommant serviteur... »

    Meme mecanisme que l'enveloppe vide du 06/09, une couche plus loin : un nettoyeur
    retire `[whisper]` ou `<note>...</note>` et laisse la virgule qui les accrochait.
    Une parenthese vide se voit ; une virgule en tete passe pour une faute du modele.
    """
    from sheo_llm import clean_internal_tags

    assert clean_internal_tags("[whisper], @LeDev. Tu penses dompter le vent ?") \
        .startswith("@LeDev")
    assert clean_internal_tags("<note>Haskill se penche</note>, @LeDev. Le vent.") \
        .startswith("@LeDev")


def test_deux_separateurs_colles_par_un_retrait_fusionnent():
    """Le morceau retire etait AU MILIEU : `Ah, [laugh], mortel` -> `Ah, mortel`."""
    from sheo_llm import clean_internal_tags

    assert clean_internal_tags("Ah, [laugh], mortel !") == "Ah, mortel !"


@pytest.mark.parametrize("propre", [
    "... et puis le silence.",              # reprise a mi-pensee : VOULUE
    "\u2026 le silence, encore.",
    "\u2014 Le vent, dis-tu ?",                 # auto-interruption : VOULUE
    "Vraiment ; oui : c'est cela !",        # espace avant ; : ! ? = typographie FR
    "Un cornichon (vraiment) chantant.",
    "Que veux-tu, mortel ?",
])
def test_une_replique_propre_n_est_jamais_touchee(propre):
    """⚠️ La garde qui compte : le filet ne doit pas mordre sur du legitime.

    Les points de suspension et le tiret d'auto-interruption sont des ouvertures
    voulues, et l'espace francais devant `;` `:` `!` `?` est CORRECT.
    """
    from sheo_llm import _retirer_ponctuation_orpheline

    assert _retirer_ponctuation_orpheline(propre) == propre


# ---------------------------------------------------------------------------
# Le bloc [TON] rouvrait l'humeur que le systeme venait de trancher
# ---------------------------------------------------------------------------
#
# Constate en live le 2026-09-06. Journal de bot-sheogorath :
#
#   20:30:27 [MOOD CHANGE] bliss -> dementia   (Prompt: SOMBRE/CRUEL)
#   20:31:36 [LLM MODE] ... (Mood: dementia)   -> « vinaigre de licorne »
#   20:32:04 [LLM MODE] ... (Mood: dementia)   -> « trone de cornichons chantants »
#   20:32:49 [LLM MODE] ... (Mood: dementia)   -> « bulles de confiture »
#   20:33:30 [LLM MODE] ... (Mood: dementia)   -> « papillons qui fredonnent du jazz »
#
# Quatre repliques joyeuses sous un prompt SOMBRE/CRUEL. Le bloc [TON], injecte APRES
# le prompt d'humeur, disait : « joueur, exalte... (Mania), OU inquietant... (Dementia) ».
# Un choix, plus proche de la fin donc plus lourd : le modele prenait le premier terme.

HUMEURS = ["neutral", "mania", "dementia", "bliss"]


def test_le_bloc_de_ton_ne_propose_JAMAIS_deux_humeurs():
    """⚠️ LE verrou de ce correctif.

    Le bloc doit NOMMER l'humeur active, jamais en offrir une seconde. Citer deux
    humeurs, c'est rendre au modele une decision que le systeme avait deja prise.
    """
    from sheo_llm import consigne_de_ton

    for humeur in HUMEURS:
        texte = consigne_de_ton(humeur).lower()
        citees = [h for h in HUMEURS if h in texte]
        assert citees == [humeur], (
            f"pour l'humeur « {humeur} », le bloc cite {citees} : "
            "il rouvre le choix au lieu de suivre l'humeur active."
        )


def test_chaque_humeur_a_son_propre_registre():
    """Sans registre distinct, nommer l'humeur ne changerait rien a ce qui est ecrit."""
    from sheo_llm import consigne_de_ton

    textes = {h: consigne_de_ton(h) for h in HUMEURS}
    assert len(set(textes.values())) == len(HUMEURS), "deux humeurs rendent le meme bloc"
    assert "paranoiaque" in textes["dementia"]
    assert "exalte" in textes["mania"]


def test_la_garde_anti_menace_gratuite_survit():
    """⚠️ Elle existe pour une raison : Sheogorath n'est pas une brute qui menace de
    torture a chaque message anodin. Suivre l'humeur ne doit pas la faire sauter."""
    from sheo_llm import consigne_de_ton

    for humeur in HUMEURS:
        texte = consigne_de_ton(humeur)
        assert "NE le menace PAS" in texte
        assert "torture" in texte


def test_sur_provocation_le_bloc_disparait():
    """Provoque, Sheo retrouve le droit aux menaces : la branche du prompt s'en charge."""
    from sheo_llm import consigne_de_ton

    for humeur in HUMEURS:
        assert consigne_de_ton(humeur, provoque=True) == ""


def test_une_humeur_inconnue_ne_fait_pas_lever():
    """Un nouvel etat ajoute demain ne doit pas casser la generation."""
    from sheo_llm import consigne_de_ton

    texte = consigne_de_ton("humeur_qui_n_existe_pas")
    assert "[TON" in texte
    assert consigne_de_ton(None)


def test_le_bot_passe_VRAIMENT_l_humeur_courante():
    """⚠️ Chercher le nom du helper passerait au vert sur un simple import.

    On exige l'appel avec `current_mood`, ET la disparition du bloc en dur : le laisser
    en place le ferait cohabiter avec le nouveau, et l'ancien gagnerait a nouveau.
    """
    import ast
    import os

    chemin = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "Sheogorath", "bot_sheogorath.py")
    with open(chemin, encoding="utf-8") as f:
        source = f.read()

    assert "Reste pleinement Sheogorath" not in source, (
        "l'ancien bloc [TON] en dur est toujours la : il rouvre le choix de l'humeur."
    )

    appels = [n for n in ast.walk(ast.parse(source, filename=chemin))
              if isinstance(n, ast.Call)
              and isinstance(n.func, ast.Name)
              and n.func.id == "consigne_de_ton"]
    assert appels, "consigne_de_ton n'est jamais appele"
    for appel in appels:
        args = [a.id for a in appel.args if isinstance(a, ast.Name)]
        args += [k.value.id for k in appel.keywords if isinstance(k.value, ast.Name)]
        assert "current_mood" in args, (
            f"l'humeur courante n'est pas transmise : {ast.dump(appel)[:120]}"
        )
