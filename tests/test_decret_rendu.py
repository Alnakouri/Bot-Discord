import pytest
from unittest.mock import patch, MagicMock
import os
import re

from Sheogorath.sheo_decrees import (
    generate_decree_image, 
    _wrap_by_width, 
    espaces_francaises,
    INSECABLE
)
from PIL import ImageDraw, Image, ImageFont

def test_la_ponctuation_double_ne_part_pas_seule_a_la_ligne():
    texte = "tu ne trouves pas ?"
    res = espaces_francaises(texte)
    assert res == f"tu ne trouves pas{INSECABLE}?"

    mock_draw = MagicMock()
    def mock_textlength(text, font=None):
        if text == "tu ne trouves": return 100
        if text == f"tu ne trouves pas{INSECABLE}?": return 200
        if text == f"pas{INSECABLE}?": return 50
        return len(text) * 10
        
    mock_draw.textlength.side_effect = mock_textlength
    font = MagicMock()
    
    lines = _wrap_by_width(mock_draw, texte, font, 150)
    assert "?" not in lines
    assert f"pas{INSECABLE}?" in lines

def test_l_insecable_survit_a_la_decoupe():
    mock_draw = MagicMock()
    mock_draw.textlength.return_value = 10
    font = MagicMock()
    
    texte = f"mot1{INSECABLE}?"
    lines = _wrap_by_width(mock_draw, texte, font, 100)
    assert INSECABLE in lines[0]

def test_l_image_est_generee_sur_un_decret_long_et_un_court():
    img_court = generate_decree_image("Court")
    assert img_court is not None
    assert img_court.getbuffer().nbytes > 0
    
    texte_long = "Bla " * 200
    img_long = generate_decree_image(texte_long)
    assert img_long is not None
    assert img_long.getbuffer().nbytes > 0


# ---------------------------------------------------------------------------
# Le texte doit TENIR dans le parchemin — la régression du 2026-08-30
# ---------------------------------------------------------------------------
#
# La refonte visuelle avait remplacé la boucle d'ajustement par `body_size = 40` figé.
# Sur un décret court ça ne se voit pas ; sur un long, les dernières lignes sortaient
# par le bas de l'image, coupées net. Ces tests-ci s'appuient sur les VRAIES polices et
# le vrai calcul : un test entièrement mocké aurait laissé passer exactement ça.

from Sheogorath.sheo_decrees import (
    _ajuster_corps, _CORPS_MAX, _CORPS_MIN, _INTERLIGNE, _load_font,
    _FONT_CANDIDATES_REGULAR, _FONT_CANDIDATES_BOLD,
)

_DECRET_LONG = (
    "Je decrete solennellement que toi, tu as l'obligation d'offrir tes intestins en "
    "pature a mes papillons dores, sous peine d'etre transforme sur-le-champ en une "
    "meule de cheddar rance ! Et ce n'est pas tout : tu porteras une chaussette sur la "
    "tete pendant trois lunes, tu chanteras l'hymne des mouches a chaque aube, et tu "
    "offriras a Haskill un fromage different chaque jour jusqu'a la fin des temps. "
    "C'est d'un CHIC absolu, tu ne trouves pas ? Ose me contredire, mortel !"
)


def _draw_reel():
    return ImageDraw.Draw(Image.new("RGB", (1024, 1024), "white"))


ZONE_H, MAX_WIDTH = 560, 694          # valeurs réelles du gabarit 1024x1024


@pytest.mark.parametrize("texte", ["Court.", _DECRET_LONG])
def test_le_corps_tient_toujours_dans_la_zone_disponible(texte):
    """Un décret que Sheogorath peut réellement écrire doit tenir, point.

    Pas d'échappatoire « sauf si on est au plancher » ici : ces deux textes tiennent à
    une taille lisible, donc l'ajustement DOIT la trouver. Une clause de repli dans
    l'assertion laissait passer la régression qu'elle était censée attraper.
    """
    _, lignes, hauteur = _ajuster_corps(_draw_reel(), texte, MAX_WIDTH, ZONE_H)
    debordement = hauteur * len(lignes) - ZONE_H
    assert debordement <= 0, f"le texte dépasse de {debordement} px"


def test_un_texte_demesure_tombe_au_plancher_et_le_dit(caplog):
    """Cas pathologique : même au plancher ça ne rentre pas. On rend quand même une
    image (mieux qu'un décret muet) mais le log doit le signaler, sinon la coupure est
    invisible.

    NB : « Bla » x200 ne suffit PAS à déclencher ce cas — il tient à 26 px. On étrangle
    donc la zone, ce qui teste la branche de repli sans dépendre d'un texte de la bonne
    longueur exacte."""
    import logging
    with caplog.at_level(logging.WARNING, logger="sheogorath"):
        police, _, _ = _ajuster_corps(_draw_reel(), _DECRET_LONG, MAX_WIDTH, zone_h=50)
    assert police.size == _CORPS_MIN
    assert any("coupé" in r.message or "coup" in r.message for r in caplog.records),         "une coupure silencieuse est pire qu'une coupure annoncée"


def test_un_decret_court_garde_une_grande_police():
    """L'ajustement ne doit pas rapetisser ce qui tient déjà : sinon on aurait « corrigé »
    le débordement en écrivant tout en minuscule."""
    police, _, _ = _ajuster_corps(_draw_reel(), "Court.", MAX_WIDTH, ZONE_H)
    assert police.size == _CORPS_MAX


def test_un_decret_long_est_reduit_mais_reste_lisible():
    police, _, _ = _ajuster_corps(_draw_reel(), _DECRET_LONG, MAX_WIDTH, ZONE_H)
    assert police.size < _CORPS_MAX, "un décret de 12 lignes doit être réduit"
    assert police.size >= _CORPS_MIN, "jamais en dessous du plancher de lisibilité"


def test_le_titre_reste_plus_grand_que_le_corps():
    """Le titre était auto-rétréci jusqu'à 28 px sur une seule ligne, donc il pouvait
    finir PLUS PETIT que le corps — la hiérarchie s'inversait. Il se plie désormais sur
    2 lignes. On vérifie l'invariant sur le titre le plus long qu'on ait vu."""
    titre = "AMIRAL DES MOUCHES A FROMAGE DE LA CONFRERIE DES PAPILLONS DORES"
    draw = _draw_reel()
    taille_titre = 64
    while taille_titre > 28:
        police_titre = _load_font(_FONT_CANDIDATES_BOLD, taille_titre)
        if len(_wrap_by_width(draw, titre, police_titre, 724)) <= 2:
            break
        taille_titre -= 4
    police_corps, _, _ = _ajuster_corps(draw, _DECRET_LONG, 694, 560)
    assert taille_titre > police_corps.size


def test_le_halo_est_reellement_pose_sous_le_texte(monkeypatch):
    """C'est le halo qui rend l'encre lisible sur une texture mouchetée : sans lui on
    revient au rendu rejeté le 2026-08-30.

    Mesurer la luminosité MOYENNE de la zone ne marche pas — l'encre sombre pèse plus
    que l'éclaircissement, et la moyenne BAISSE alors même que le halo est posé
    (mesuré : 167 avec halo contre 177 sur parchemin nu). On détourne donc la couleur du
    halo vers un magenta, et on compte les pixels à dominante bleue dans le cœur du bloc
    de texte — un parchemin n'en contient aucun, la brume violette des bords est hors
    cadre. Mesuré : 0 sans le détournement, ~10 000 avec.
    """
    import Sheogorath.sheo_decrees as sd
    from PIL import Image as _Image

    COEUR_DU_TEXTE = (280, 400, 750, 700)     # loin de la brume violette des bords
    bleutes = lambda im: sum(1 for p in im.getdata() if p[2] > p[1] + 20)

    sans = _Image.open(sd.generate_decree_image(_DECRET_LONG, title="DECRET DAEDRA"))
    assert bleutes(sans.convert("RGB").crop(COEUR_DU_TEXTE)) == 0,         "la mesure est faussée : le cadrage attrape la brume violette"

    monkeypatch.setattr(sd, "_HALO_CREME", (255, 0, 255))
    avec = _Image.open(sd.generate_decree_image(_DECRET_LONG, title="DECRET DAEDRA"))
    assert bleutes(avec.convert("RGB").crop(COEUR_DU_TEXTE)) > 1000,         "le calque de halo n'est pas collé sur l'image"


# Nouveaux tests pour la DA Manuscrit Enluminé

def test_la_derniere_ligne_d_un_paragraphe_n_est_pas_justifiee():
    from Sheogorath.sheo_decrees import justifie
    from PIL import ImageDraw, Image, ImageFont
    from unittest.mock import MagicMock
    
    mock_draw = MagicMock()
    mock_font = MagicMock()
    mock_draw.textlength.side_effect = lambda t, font=None: len(t) * 10
    
    # derniere=True
    justifie(mock_draw, "mot1 mot2", mock_font, 100, True, 0, 0, (0,0,0))
    calls = mock_draw.text.call_args_list
    assert len(calls) == 2
    assert calls[0][0][0] == (0, 0)
    # mot1 + espace = 40 + 10 = 50
    assert calls[1][0][0] == (50, 0)

def test_une_ligne_justifiee_atteint_la_largeur_demandee():
    from Sheogorath.sheo_decrees import justifie
    from unittest.mock import MagicMock
    
    mock_draw = MagicMock()
    mock_font = MagicMock()
    mock_draw.textlength.side_effect = lambda t, font=None: len(t) * 10
    
    justifie(mock_draw, "mot1 mot2", mock_font, 100, False, 0, 0, (0,0,0))
    calls = mock_draw.text.call_args_list
    assert len(calls) == 2
    assert calls[0][0][0] == (0, 0)
    # (100 - (40 + 40)) / 1 = 20; 40 + 20 = 60
    assert calls[1][0][0] == (60, 0)

def test_la_lettrine_ne_mord_que_sur_les_deux_premieres_lignes():
    """La lettrine impose une largeur REDUITE sur les 2 premieres lignes seulement.

    ⚠️ `assert len(lines) > 2` ne prouvait rien : c'etait deja vrai sans lettrine. On
    mesure donc le nombre de mots par ligne, avec une police simulee a 10 px par
    caractere : 100 px de large = 10 caracteres, moins 30 px de retrait = 7 sur les
    deux premieres. Le contrat tient sur la BASCULE a la 3e ligne — c'est elle qui
    dirait si le retrait bavait sur tout le paragraphe.
    """
    from Sheogorath.sheo_decrees import _wrap_by_width
    from unittest.mock import MagicMock
    draw = MagicMock()
    font = MagicMock()
    draw.textlength.side_effect = lambda t, font=None: len(t) * 10

    texte = "A B C D E F G H I J K L M N O P Q R S T"
    avec = _wrap_by_width(draw, texte, font, 100, indent_lines=2, indent_width=30)
    sans = _wrap_by_width(draw, texte, font, 100)

    mots = [len(l.split()) for l in avec]
    assert mots[0] == mots[1] == 4, "les 2 premieres lignes ne sont pas retrecies"
    assert mots[2] == 5, "le retrait bave au-dela de la 2e ligne"
    assert [len(l.split()) for l in sans] == [5, 5, 5, 5],         "sans lettrine, aucune ligne ne doit etre retrecie"

def test_le_texte_ne_touche_jamais_la_brume_des_bords():
    from Sheogorath.sheo_decrees import generate_decree_image, _ENCRE_SEPIA
    img_bytes = generate_decree_image("Bla " * 100)
    from PIL import Image
    img = Image.open(img_bytes).convert("RGB")
    for y in range(400, 600):
        assert img.getpixel((180, y)) != _ENCRE_SEPIA
        assert img.getpixel((1024 - 180, y)) != _ENCRE_SEPIA

def test_aucun_caractere_ne_sort_en_tofu():
    from Sheogorath.sheo_decrees import _FONT_CANDIDATES_REGULAR
    from fontTools.ttLib import TTFont
    
    font = TTFont(_FONT_CANDIDATES_REGULAR[0])
    cmap = font.getBestCmap()
    
    text = "É D I T   I M P É R I A L DÉCRET DAEDRA"
    
    for c in text:
        if c != " ":
            assert ord(c) in cmap, f"Char {c} non supporté par la police"
            
def test_la_mention_est_mise_en_valeur():
    from Sheogorath.sheo_decrees import generate_decree_image
    from PIL import ImageDraw
    from unittest.mock import patch
    with patch.object(ImageDraw.ImageDraw, 'line') as mock_line:
        generate_decree_image("Texte @Pseudo")
        calls = [c for c in mock_line.call_args_list if c[1].get('fill') == (128, 0, 128) and c[1].get('width') == 2]
        assert len(calls) >= 1
