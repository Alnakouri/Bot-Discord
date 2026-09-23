# -*- coding: utf-8 -*-
"""Tests unitaires de la garde « 1 appel LLM par jour » de `shared/twitch/daily_profile.py`
(reco #5 de l'audit).

`_ensure_daily_profile` ne doit appeler le LLM (`_generate_daily_profile`) que lorsque
aucun profil n'existe pour la date du jour. Deux niveaux de cache :
1. mémoire process (`self._profile_day`) : pas de second appel dans le même process ;
2. état persistant JSON : un process neuf relit le profil du jour sans appeler le LLM.
"""
import os
import sys
import logging
import shutil
import unittest
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, call

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from shared.twitch import daily_profile
from shared.twitch.daily_profile import DailyProfileMixin


class _Host(DailyProfileMixin):
    """Hôte minimal : on isole la logique de cache en mockant la génération LLM."""

    def __init__(self):
        self.bot_id = "testbot"
        self.logger = logging.getLogger("test_daily_profile")
        self._profile_day = None
        self.profile_helper = AsyncMock()
        self.gen_calls = 0

    async def _generate_daily_profile(self):
        # Remplace l'appel LLM réel : on compte les invocations.
        self.gen_calls += 1
        return ("ma bio du jour", "blue_violet")


class _HostAvecRepli(_Host):
    """Un bot qui a une bio FIXE (Johnny) et dont la bio du jour est refusee."""

    def __init__(self):
        super().__init__()
        self.profile_bio = "bio fixe qui passe"
        self.profile_helper.update_profile = AsyncMock(side_effect=["bio_refusee", None])


class TestDailyProfileCache(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Redirige DATA_DIR vers un dossier temporaire isolé.
        self.test_dir = Path(__file__).parent / "temp_test_profile"
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self._orig_data_dir = daily_profile.DATA_DIR
        daily_profile.DATA_DIR = str(self.test_dir)

    def tearDown(self):
        daily_profile.DATA_DIR = self._orig_data_dir
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    async def test_single_llm_call_per_process(self):
        host = _Host()
        await host._ensure_daily_profile()
        await host._ensure_daily_profile()  # même process, même jour → pas de 2e appel
        self.assertEqual(host.gen_calls, 1)
        self.assertEqual(host._profile_day, datetime.now().strftime("%Y-%m-%d"))
        host.profile_helper.update_profile.assert_awaited_with(
            bio="ma bio du jour", chat_color="blue_violet"
        )

    async def test_first_call_persists_state(self):
        host = _Host()
        await host._ensure_daily_profile()
        state = host._load_profile_state()
        self.assertIsNotNone(state)
        self.assertEqual(state["date"], datetime.now().strftime("%Y-%m-%d"))
        self.assertEqual(state["bio"], "ma bio du jour")
        self.assertEqual(state["color"], "blue_violet")

    async def test_fresh_process_reuses_persisted_profile_without_llm(self):
        # 1er process : génère + persiste.
        host1 = _Host()
        await host1._ensure_daily_profile()
        self.assertEqual(host1.gen_calls, 1)

        # 2e process (état mémoire neuf) : doit relire le JSON, AUCUN appel LLM.
        host2 = _Host()
        await host2._ensure_daily_profile()
        self.assertEqual(host2.gen_calls, 0)
        host2.profile_helper.update_profile.assert_awaited_with(
            bio="ma bio du jour", chat_color="blue_violet"
        )

    async def test_stale_state_triggers_regeneration(self):
        # État persistant daté d'hier → doit régénérer (appel LLM).
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        host = _Host()
        host._save_profile_state({"date": yesterday, "bio": "vieille bio", "color": "red"})
        await host._ensure_daily_profile()
        self.assertEqual(host.gen_calls, 1)
        state = host._load_profile_state()
        self.assertEqual(state["date"], datetime.now().strftime("%Y-%m-%d"))

    async def test_bio_refusee_retombe_sur_la_bio_fixe(self):
        host = _HostAvecRepli()
        await host._ensure_daily_profile()
        self.assertEqual(host.profile_helper.update_profile.await_count, 2)
        self.assertEqual(
            host.profile_helper.update_profile.await_args_list[1],
            call(bio="bio fixe qui passe"),
        )
        state = host._load_profile_state()
        self.assertIsNotNone(state)
        self.assertEqual(state["bio"], "bio fixe qui passe")
        self.assertEqual(state["color"], "blue_violet")

    async def test_bio_refusee_sans_bio_fixe_n_envoie_rien_de_plus(self):
        host = _Host()
        host.profile_helper.update_profile = AsyncMock(return_value="bio_refusee")
        await host._ensure_daily_profile()
        self.assertEqual(host.profile_helper.update_profile.await_count, 1)
        state = host._load_profile_state()
        self.assertIsNotNone(state)
        self.assertEqual(state["bio"], "ma bio du jour")

    async def test_bio_acceptee_pas_de_repli(self):
        host = _HostAvecRepli()
        host.profile_helper.update_profile = AsyncMock(return_value=None)
        await host._ensure_daily_profile()
        self.assertEqual(host.profile_helper.update_profile.await_count, 1)

    async def test_redemarrage_apres_repli_n_appelle_pas_le_llm(self):
        host1 = _HostAvecRepli()
        await host1._ensure_daily_profile()
        self.assertEqual(host1.gen_calls, 1)

        host2 = _HostAvecRepli()
        host2.profile_helper.update_profile = AsyncMock(return_value=None)
        await host2._ensure_daily_profile()
        self.assertEqual(host2.gen_calls, 0)
        host2.profile_helper.update_profile.assert_awaited_with(
            bio="bio fixe qui passe", chat_color="blue_violet"
        )


if __name__ == "__main__":
    unittest.main()
