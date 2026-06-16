# -*- coding: utf-8 -*-

"""
sheo_decrees.py — Système de Décrets Visuels et de Rôles pour Sheogorath.
Gère la superposition de texte sur parchemin et la manipulation des rôles Discord.
"""

import discord
import os
import textwrap
import logging
import random
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

logger = logging.getLogger("sheogorath")

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
PARCHMENT_PATH = os.path.join(ASSETS_DIR, "parchment.png")

# Couleurs Sheogorath (RGB)
COLORS = {
    "PURPLE": (128, 0, 128),
    "GOLD": (212, 175, 55),
    "CHEESE": (255, 165, 0),
    "BLACK": (30, 30, 30),
    "DEMENTIA": (50, 0, 0)
}

def generate_decree_image(text, title="DÉCRET DAEDRA"):
    """
    Génère une image de parchemin avec le texte du décret.
    """
    if not os.path.exists(PARCHMENT_PATH):
        logger.error(f"❌ [DECRET] Fond de parchemin introuvable : {PARCHMENT_PATH}")
        return None

    try:
        # 1. Ouvrir le parchemin
        img = Image.open(PARCHMENT_PATH).convert("RGB")
        draw = ImageDraw.Draw(img)
        width, height = img.size

        # 2. Charger les polices (fallback sur celle par défaut si non trouvées)
        try:
            # On essaie de charger une police serif standard si possible
            # Sinon Pillow utilisera la police par défaut (très basique)
            font_title = ImageFont.truetype("arial.ttf", 60)
            font_text = ImageFont.truetype("arial.ttf", 40)
        except Exception:
            font_title = ImageFont.load_default()
            font_text = ImageFont.load_default()

        # 3. Écrire le Titre
        title_bbox = draw.textbbox((0, 0), title, font=font_title)
        title_w = title_bbox[2] - title_bbox[0]
        draw.text(((width - title_w) / 2, 150), title, font=font_title, fill=COLORS["PURPLE"])

        # 4. Écrire le Corps du Texte (avec wrapping)
        margin = 150
        max_width = width - (margin * 2)
        
        # Estimer le nombre de caractères par ligne selon la largeur
        avg_char_width = 20 # Estimation grossière
        chars_per_line = max_width // avg_char_width
        
        wrapped_text = textwrap.fill(text, width=int(chars_per_line))
        
        # Écrire le texte centré verticalement (plus ou moins)
        draw.text((margin, 300), wrapped_text, font=font_text, fill=COLORS["BLACK"])

        # 5. Sauvegarder en mémoire
        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf

    except Exception as e:
        logger.error(f"❌ [DECRET] Erreur génération image : {e}")
        return None


async def apply_decree_role(guild, member, title, duration=600):
    """
    Crée un rôle de décret, l'assigne, puis le supprime après 'duration' secondes.
    """
    try:
        role_name = f"📜 {title.upper()}"
        
        # 1. Création du rôle
        color = discord.Color.from_rgb(*random.choice([COLORS["PURPLE"], COLORS["GOLD"], COLORS["CHEESE"]]))
        role = await guild.create_role(
            name=role_name,
            color=color,
            hoist=True,
            reason=f"Décret de Sheogorath pour {member.display_name}"
        )
        
        # 2. Placement hiérarchique
        bot_role = guild.me.top_role
        new_pos = max(1, bot_role.position - 1)
        try:
            await role.edit(position=new_pos)
        except discord.Forbidden:
            pass

        # 3. Assignation
        await member.add_roles(role)
        logger.info(f"👑 [DECRET] Rôle '{role_name}' assigné à {member.display_name} pour {duration}s")

        # 4. Suppression différée (en arrière-plan pour ne pas bloquer le bot)
        async def delayed_cleanup():
            import asyncio
            await asyncio.sleep(duration)
            try:
                # On vérifie que c'est bien NOTRE rôle avant de supprimer
                if role.name.startswith("📜"):
                    await role.delete(reason="Fin du décret de Sheogorath")
                    logger.info(f"🧹 [DECRET] Rôle '{role_name}' supprimé après expiration.")
            except discord.NotFound:
                pass # Déjà supprimé manuellement
            except Exception as e:
                logger.error(f"❌ [DECRET] Erreur suppression rôle : {e}")

        import asyncio
        asyncio.create_task(delayed_cleanup())
        
        return role

    except Exception as e:
        logger.error(f"❌ [DECRET] Erreur gestion rôles : {e}")
        return None

async def cleanup_old_decree_roles(guild, days=2):
    """
    Supprime les rôles commençant par 📜 qui sont trop vieux ou n'ont plus de membres.
    (À implémenter si besoin de persistance temporelle)
    """
    pass
