# -*- coding: utf-8 -*-
"""Tous les échelons de texte doivent obéir à NOS bornes, pas aux défauts du fournisseur.

Mesuré le 2026-09-16. Dans `shared/llm_cascade.py`, l'échelon **Mistral** ne passait
**ni `temperature` ni `max_tokens`**, et l'échelon **Groq** ne passait pas `max_tokens`.
Deux échelons sur quatre servaient donc aux réglages du fournisseur, en silence.

Ça ne se voyait que sur un bot : **Malena est la seule dont la cascade est Mistral-FIRST**
(`shared/models.py`). Elle est aussi la seule dont les réponses partaient à 432 mots et
dégénéraient en boucle de répétition. Ce n'était ni sa persona ni sa température — sa
cascade INLINE, elle, passait correctement les quatre bornes sur ses quatre échelons.
C'est la cascade PARTAGÉE qui était trouée, celle qu'utilisent les cinq autres bots.

⚠️ `ollama` est hors périmètre : c'est la vision locale, elle délègue à
`process_image_ollama` et ne génère pas de texte ici.
"""
import os
import re

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ECHELONS_DE_TEXTE = ("gemini", "mistral", "groq", "nvidia")

# shared/ + les 6 copies vendorisées : un bot déployé SEUL ne lit que sa copie.
CIBLES = ["shared/llm_cascade.py"] + [
    f"{b}/core/llm_cascade.py"
    for b in ("Alfred", "JohnnyBot", "MaiqBot", "MalenaBot", "Sheogorath", "SugarBot")
]


def _par_echelon(src):
    blocs = re.split(r'\n\s+(?:el)?if client_type == "', src)
    return {b.split('"')[0]: b[:2800] for b in blocs[1:]}


def test_chaque_echelon_de_texte_porte_temperature_et_borne():
    manques = {}
    for relatif in CIBLES:
        chemin = os.path.join(_parent_dir, relatif)
        if not os.path.exists(chemin):
            continue
        blocs = _par_echelon(open(chemin, encoding="utf-8").read())
        for echelon in ECHELONS_DE_TEXTE:
            corps = blocs.get(echelon)
            assert corps is not None, f"{relatif} : échelon {echelon} introuvable"
            trous = []
            if "temperature=temperature" not in corps:
                trous.append("temperature")
            if not any(k in corps for k in ("max_tokens=max_tokens", "max_output_tokens=")):
                trous.append("borne de tokens")
            if trous:
                manques.setdefault(relatif, {})[echelon] = trous

    assert not manques, (
        f"des échelons servent aux défauts du fournisseur : {manques}. "
        "Un échelon qui ignore nos bornes rend des réponses d'une autre longueur et d'un "
        "autre hasard que les autres — et seul le bot qui le tire en PREMIER le montre."
    )


def test_la_cascade_INLINE_de_malena_obeit_aussi():
    """Elle ne passe pas par `shared/` : elle doit être vérifiée à part, toujours."""
    chemin = os.path.join(_parent_dir, "MalenaBot", "bot_malena.py")
    blocs = _par_echelon(open(chemin, encoding="utf-8").read())
    for echelon in ECHELONS_DE_TEXTE:
        corps = blocs.get(echelon)
        assert corps is not None, f"échelon {echelon} introuvable dans la cascade inline"
        assert "temperature=" in corps, f"inline {echelon} : pas de température"
        assert "max_tokens=" in corps or "max_output_tokens=" in corps, \
            f"inline {echelon} : pas de borne de tokens"
