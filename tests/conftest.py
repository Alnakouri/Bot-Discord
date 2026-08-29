# -*- coding: utf-8 -*-
"""Garde globale : les tests ne doivent JAMAIS écrire dans logs/* (le dashboard
les afficherait comme des événements des bots live). Posé AVANT tout import de
module bot par les tests — conftest est chargé en premier par pytest."""
import os
import tempfile

os.environ.setdefault("BOTS_LOG_CONSOLE_ONLY", "1")

# Même garde pour data/. Depuis que la cascade trace ses appels, un test qui appelle
# `generate_response` (test_cascade_reponse_vide) écrivait de vraies lignes dans
# `data/api_usage.db` : la suite de l'hôte se mélangeait aux mesures des bots live,
# avec un bot_name « test ». Mesuré le 2026-08-29 : 40 lignes parasites.
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="pytest-data-"))
