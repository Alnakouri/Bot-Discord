import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock, PropertyMock
import importlib
import sys

BOTS = [
    ("Alfred", "bot_alfred"),
    ("JohnnyBot", "bot_johnny"),
    ("MaiqBot", "bot_maiq"),
    ("MalenaBot", "bot_malena"),
    ("Sheogorath", "bot_sheogorath"),
    ("SugarBot", "bot_sugar"),
]

@pytest.mark.parametrize("dossier, module_name", BOTS)
def test_on_ready_replay(dossier, module_name):
    asyncio.run(_test_on_ready_replay(dossier, module_name))

async def _test_on_ready_replay(dossier, module_name):
    if dossier not in sys.path:
        sys.path.insert(0, dossier)
    
    mod = importlib.import_module(module_name)
    
    started_loops = set()
    def fake_start(self, *args, **kwargs):
        started_loops.add(id(self))
    
    def fake_is_running(self):
        return id(self) in started_loops

    test_user = MagicMock(name="TestBot", id=123)
    test_user.name = "TestBot"

    with patch('discord.ext.tasks.Loop.start', autospec=True, side_effect=fake_start) as mock_start, \
         patch('discord.ext.tasks.Loop.is_running', autospec=True, side_effect=fake_is_running), \
         patch.object(mod.bot, 'change_presence', new_callable=AsyncMock), \
         patch.object(mod.bot.tree, 'sync', new_callable=AsyncMock), \
         patch.object(mod.bot, 'wait_until_ready', new_callable=AsyncMock), \
         patch.object(mod, 'check_missed_riddle_answers', new_callable=AsyncMock, create=True), \
         patch('discord.ext.commands.Bot.user', new_callable=PropertyMock, return_value=test_user):
        
        if hasattr(mod, 'setup_slash_commands'):
            mod.setup_slash_commands = MagicMock()
        if hasattr(mod, 'sync_slash_commands'):
            mod.sync_slash_commands = AsyncMock()
        if hasattr(mod, 'setup_games'):
            mod.setup_games = MagicMock()

        if hasattr(mod, 'twitch_chat') and mod.twitch_chat:
            mod.twitch_chat.run = AsyncMock()
        
        # 1er appel : le demarrage normal.
        with patch.object(mod.logger, 'info') as mock_info:
            await mod.on_ready()
            assert mock_start.call_count > 0, "Aucune boucle n'a été démarrée"
            assert mock_info.call_count > 0, "Le 1er appel n'a rien loggé : le test ne mesure rien"
        boucles_apres_1 = set(started_loops)

        mock_start.reset_mock()

        # 2e appel : ce que fait discord.py a chaque RESUME du WebSocket.
        #
        # ⚠️ Ce qui coute cher n'est PAS le RuntimeError : en production discord.py
        # l'avale (« Ignoring exception in on_ready »). Ce sont les lignes d'APRES, qui ne
        # sont alors jamais rejouees. Ici la coroutine est attendue directement, donc
        # toute interruption remonte et fait echouer le test : c'est `await` lui-meme qui
        # tient l'assertion « la fonction va jusqu'au bout ».
        #
        # ⚠️ Ne pas comparer le dernier log des deux passages : les blocs volontairement
        # idempotents (`if twitch_chat is None:`) sont sautes au 2e appel, la queue differe
        # legitimement chez Johnny et Sugar.
        with patch.object(mod.logger, 'info') as mock_info:
            await mod.on_ready()

            assert mock_start.call_count == 0, (
                f"Des boucles ont tenté de démarrer au 2e appel : {mock_start.call_count} fois"
            )
            assert mock_info.call_count > 0, "Le 2e appel n'a rien loggé du tout"
            assert set(started_loops) == boucles_apres_1, (
                "Le 2e appel a perdu ou ajouté des boucles : "
                f"{len(started_loops)} au lieu de {len(boucles_apres_1)}"
            )
