# -*- coding: utf-8 -*-
"""Garde globale : les tests ne doivent JAMAIS écrire dans logs/* (le dashboard
les afficherait comme des événements des bots live). Posé AVANT tout import de
module bot par les tests — conftest est chargé en premier par pytest."""
import os

os.environ.setdefault("BOTS_LOG_CONSOLE_ONLY", "1")
