import pytest
from unittest.mock import AsyncMock, MagicMock
from discord.ext import commands
import importlib.util
import glob
from pathlib import Path
import sys

def load_bot_module(filepath):
    module_name = Path(filepath).stem
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as e:
        print(f"Could not load {filepath}: {e}")
        return None
    return module

def test_erreurs_commandes(caplog):
    import asyncio
    asyncio.run(_test_erreurs_commandes_async(caplog))

async def _test_erreurs_commandes_async(caplog):
    bot_files = glob.glob("*Bot/bot_*.py") + ["Alfred/bot_alfred.py", "Sheogorath/bot_sheogorath.py"]
    
    for bot_file in bot_files:
        bot_dir = Path(bot_file).parent.resolve()
        sys.path.insert(0, str(bot_dir))
        module = load_bot_module(bot_file)
        sys.path.pop(0)
            
        if module is None or not hasattr(module, 'on_command_error'):
            continue
            
        on_command_error = module.on_command_error
        
        ctx = MagicMock()
        ctx.send = AsyncMock()
        ctx.command = MagicMock()
        ctx.command.name = "testcmd"
        ctx.command.signature = "<arg>"
        
        # Test MissingRequiredArgument
        caplog.clear()
        error = commands.MissingRequiredArgument(MagicMock())
        await on_command_error(ctx, error)
        
        ctx.send.assert_called_once()
        sent_text = ctx.send.call_args[0][0]
        assert "testcmd" in sent_text
        
        # Verify nothing logged as ERROR
        for record in caplog.records:
            assert record.levelname != "ERROR"
            
        # Test CommandNotFound
        ctx.send.reset_mock()
        caplog.clear()
        error = commands.CommandNotFound()
        await on_command_error(ctx, error)
        
        ctx.send.assert_not_called()
        # Verify nothing logged
        assert len(caplog.records) == 0
