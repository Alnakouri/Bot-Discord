# -*- coding: utf-8 -*-
"""Tests unitaires du parseur de statut Discord (shared/discord_status.py).

`_parse_items` extrait une liste [(type, texte)] d'une réponse LLM JSON tolérante :
fences ```…```, texte autour, types en français/majuscules, dédoublonnage, longueur."""
import os
import sys
import unittest

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from shared.discord_status import DiscordDailyStatus, MAX_STATUS_LEN

parse = DiscordDailyStatus._parse_items


class TestParseItems(unittest.TestCase):
    def test_plain_json_array(self):
        out = parse('[{"type":"watching","text":"le caramel dorer"}]')
        self.assertEqual(out, [("watching", "le caramel dorer")])

    def test_all_three_types(self):
        out = parse('[{"type":"watching","text":"a"},'
                    '{"type":"playing","text":"b"},'
                    '{"type":"listening","text":"c"}]')
        self.assertEqual([t for t, _ in out], ["watching", "playing", "listening"])

    def test_french_and_uppercase_types_normalized(self):
        out = parse('[{"type":"Regarde","text":"x"},{"type":"ÉCOUTE","text":"y"}]')
        self.assertEqual(out, [("watching", "x"), ("listening", "y")])

    def test_code_fences_and_surrounding_text(self):
        out = parse('Voici :\n```json\n[{"type":"playing","text":"à la marchande"}]\n```')
        self.assertEqual(out, [("playing", "à la marchande")])

    def test_unknown_type_dropped(self):
        out = parse('[{"type":"streaming","text":"x"},{"type":"playing","text":"y"}]')
        self.assertEqual(out, [("playing", "y")])

    def test_empty_text_dropped(self):
        self.assertEqual(parse('[{"type":"playing","text":"  "}]'), [])

    def test_dedup_case_insensitive(self):
        out = parse('[{"type":"playing","text":"Caramel"},{"type":"playing","text":"caramel"}]')
        self.assertEqual(out, [("playing", "Caramel")])

    def test_text_truncated(self):
        long = "a" * 200
        out = parse('[{"type":"playing","text":"%s"}]' % long)
        self.assertEqual(len(out[0][1]), MAX_STATUS_LEN)

    def test_garbage_returns_empty(self):
        self.assertEqual(parse("désolée, pas de JSON ici"), [])
        self.assertEqual(parse(""), [])
        self.assertEqual(parse(None), [])

    def test_not_a_list_returns_empty(self):
        self.assertEqual(parse('{"type":"playing","text":"x"}'), [])


if __name__ == "__main__":
    unittest.main()
