# ⚠️ FICHIER GENERE — NE PAS EDITER ICI.
# Source : shared/graceful_shutdown.py — modifier la source puis relancer :
#     python tools/vendor_core.py
# La sonde tools/sonde_core_drift.py echoue si cette copie diverge.

# -*- coding: utf-8 -*-
"""
Graceful shutdown handler for Discord bots.
Ensures data is saved before the process exits (SIGTERM from Docker, Ctrl+C, etc.).
"""
import signal
import asyncio
import logging

logger = logging.getLogger("graceful_shutdown")


def setup_graceful_shutdown(bot, on_shutdown_callback=None):
    """
    Registers signal handlers for SIGTERM and SIGINT to cleanly close the bot.
    
    Args:
        bot: The discord.ext.commands.Bot instance.
        on_shutdown_callback: Optional async callable to run before closing
                              (e.g., saving memory files, flushing logs).
    """
    async def _shutdown():
        bot_name = bot.user.name if bot.user else "Bot"
        logger.info(f"[SHUTDOWN] {bot_name} - Arret gracieux en cours...")
        
        # Run custom cleanup if provided
        if on_shutdown_callback:
            try:
                await on_shutdown_callback()
                logger.info(f"[SHUTDOWN] {bot_name} - Callback de nettoyage execute.")
            except Exception as e:
                logger.error(f"[SHUTDOWN] {bot_name} - Erreur callback: {e}")
        
        # Close bot connection
        try:
            await bot.close()
            logger.info(f"[SHUTDOWN] {bot_name} - Connexion fermee proprement.")
        except Exception as e:
            logger.error(f"[SHUTDOWN] {bot_name} - Erreur fermeture: {e}")

    def _signal_handler(sig, frame):
        logger.info(f"[SHUTDOWN] Signal {sig} recu. Lancement arret gracieux...")
        # Schedule the shutdown coroutine in the bot's event loop
        loop = bot.loop
        if loop and loop.is_running():
            asyncio.ensure_future(_shutdown(), loop=loop)
        else:
            logger.warning("[SHUTDOWN] Event loop non disponible, arret force.")

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    logger.info("[SHUTDOWN] Handlers SIGTERM/SIGINT enregistres.")
