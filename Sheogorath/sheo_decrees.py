# -*- coding: utf-8 -*-

"""
sheo_decrees.py — Système de Décrets Visuels et de Rôles pour Sheogorath.
Gère la superposition de texte sur parchemin et la manipulation des rôles Discord.
"""

import discord
import os
import re
import textwrap
import logging
import random
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

logger = logging.getLogger("sheogorath")

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
PARCHMENT_PATH = os.path.join(ASSETS_DIR, "parchment.png")

# Polices embarquées (DejaVu Serif) : couvrent tous les accents français, donc
# fonctionnent IDENTIQUEMENT en local et en Docker (où arial.ttf n'existe pas).
# On garde des chemins système en repli si jamais le fichier embarqué manque.
_FONT_CANDIDATES_REGULAR = [
    os.path.join(ASSETS_DIR, "DejaVuSerif.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "DejaVuSerif.ttf",
    "arial.ttf",
]
_FONT_CANDIDATES_BOLD = [
    os.path.join(ASSETS_DIR, "DejaVuSerif-Bold.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "DejaVuSerif-Bold.ttf",
    "arialbd.ttf",
] + _FONT_CANDIDATES_REGULAR

# Emoji et symboles hors-police (ranges non couverts par DejaVu) : on les retire
# du texte de l'image pour éviter les carrés « tofu ». Ils restent dans le
# message Discord d'accompagnement.
_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    "\U00002B00-\U00002BFF\U0000FE00-\U0000FE0F\U00002190-\U000021FF]+",
    flags=re.UNICODE,
)


def _load_font(candidates, size):
    """Charge la première police disponible dans la liste, sinon police défaut."""
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    logger.warning("⚠️ [DECRET] Aucune police TTF trouvée, repli sur la police par défaut (accents possiblement absents).")
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _clean_for_image(text):
    """Retire emoji/symboles hors-police et normalise les espaces pour l'image."""
    text = _EMOJI_RE.sub("", text or "")
    return re.sub(r"[ \t]{2,}", " ", text).strip()

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

        # 2. Charger les polices embarquées (DejaVu Serif → accents OK partout).
        font_text = _load_font(_FONT_CANDIDATES_REGULAR, 40)

        # On retire les emoji/symboles non couverts par la police (sinon carrés).
        title = _clean_for_image(title)
        text = _clean_for_image(text)

        # 3. Écrire le Titre — taille auto-réduite pour tenir dans la largeur.
        margin = 150
        max_title_w = width - 2 * margin
        title_size = 60
        while title_size > 28:
            font_title = _load_font(_FONT_CANDIDATES_BOLD, title_size)
            tb = draw.textbbox((0, 0), title, font=font_title)
            if (tb[2] - tb[0]) <= max_title_w:
                break
            title_size -= 4
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
