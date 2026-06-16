# -*- coding: utf-8 -*-

# INJECTION SHARED FOLDER
import sys
import os
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

"""
Conversion des mentions textuelles en vraies mentions Discord.
Le LLM génère parfois <username> ou @username au lieu de <@ID>.
"""
import re
import logging

logger = logging.getLogger("sheogorath")


async def convert_text_mentions_to_discord(text, channel):
    """Convertit les mentions textuelles en vraies mentions Discord."""
    result = text

    # Collecter les membres du canal pour le mapping nom -> ID
    members_map = {}
    try:
        # Récupérer les membres qui ont récemment parlé
        async for msg in channel.history(limit=50):
            if msg.author.id not in members_map:
                # Mapper plusieurs variantes du nom
                members_map[msg.author.name.lower()] = msg.author.id
                members_map[msg.author.display_name.lower()] = msg.author.id
                # Aussi sans accents/caractères spéciaux
                clean_name = re.sub(r'[^a-zA-Z0-9]', '', msg.author.name.lower())
                if clean_name:
                    members_map[clean_name] = msg.author.id
    except Exception as e:
        logger.warning(f"[MENTION FIX] Erreur collecte membres: {e}")

    # Pattern 1: <username> (sans @, juste le nom entre chevrons)
    pattern1 = r'<([^@<>]+)>'
    for match in re.finditer(pattern1, result):
        potential_name = match.group(1).lower().strip()
        if potential_name in members_map:
            user_id = members_map[potential_name]
            result = result.replace(match.group(0), f'<@{user_id}>')
            logger.debug(f"[MENTION FIX] '{match.group(0)}' → '<@{user_id}>'")

    # Pattern 2: @username (mention textuelle)
    pattern2 = r'@([a-zA-Z0-9_]+)'
    for match in re.finditer(pattern2, result):
        potential_name = match.group(1).lower().strip()
        if potential_name in members_map:
            user_id = members_map[potential_name]
            result = result.replace(match.group(0), f'<@{user_id}>')
            logger.debug(f"[MENTION FIX] '{match.group(0)}' → '<@{user_id}>'")

    return result
