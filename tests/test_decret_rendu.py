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

def test_le_titre_ne_devient_jamais_plus_petit_que_le_corps():
    with patch('Sheogorath.sheo_decrees._load_font') as mock_load_font, \
         patch('Sheogorath.sheo_decrees.Image.open') as mock_open:
        
        mock_img = MagicMock()
        mock_img.size = (1000, 1000)
        mock_img.convert.return_value = mock_img
        mock_open.return_value = mock_img
        
        def mock_textbbox(xy, text, font=None, **kwargs):
            size = font.size if hasattr(font, 'size') else 64
            width = 2000 if size > 30 else 500
            return (0, 0, width, 50)
            
        def mock_textlength(text, font=None, **kwargs):
            return 100

        with patch('Sheogorath.sheo_decrees.ImageDraw.Draw') as mock_draw_class:
            mock_draw = MagicMock()
            mock_draw.textbbox.side_effect = mock_textbbox
            mock_draw.textlength.side_effect = mock_textlength
            mock_draw_class.return_value = mock_draw
            
            def side_effect_load_font(candidates, size):
                m = MagicMock()
                m.size = size
                return m
            mock_load_font.side_effect = side_effect_load_font
            
            generate_decree_image("Texte court", title="AMIRAL DES MOUCHES À FROMAGE DE LA CONFRÉRIE DES PAPILLONS DORÉS")
            
            sizes_called = [call.args[1] for call in mock_load_font.call_args_list]
            assert 40 in sizes_called
            
            title_sizes = [s for s in sizes_called if s != 40]
            if title_sizes:
                min_title_size = min(title_sizes)
                assert min_title_size >= 28

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

def test_le_corps_n_est_pas_compose_dans_la_police_de_titre():
    with patch('Sheogorath.sheo_decrees._load_font') as mock_load_font, \
         patch('Sheogorath.sheo_decrees.Image.open') as mock_open:
        mock_img = MagicMock()
        mock_img.size = (1000, 1000)
        mock_img.convert.return_value = mock_img
        mock_open.return_value = mock_img
        
        with patch('Sheogorath.sheo_decrees.ImageDraw.Draw') as mock_draw_class:
            mock_draw = MagicMock()
            mock_draw.textbbox.return_value = (0, 0, 100, 50)
            mock_draw.textlength.return_value = 100
            mock_draw_class.return_value = mock_draw
            
            def side_effect_load_font(candidates, size):
                m = MagicMock()
                m.size = size
                m.candidates = candidates
                return m
            mock_load_font.side_effect = side_effect_load_font
            
            generate_decree_image("Corps")
            
            # Find the candidates lists used
            candidates_used = [call.args[0] for call in mock_load_font.call_args_list]
            
            from Sheogorath.sheo_decrees import _FONT_CANDIDATES_BOLD, _FONT_CANDIDATES_REGULAR
            assert _FONT_CANDIDATES_BOLD in candidates_used
            assert _FONT_CANDIDATES_REGULAR in candidates_used
            assert _FONT_CANDIDATES_BOLD != _FONT_CANDIDATES_REGULAR
