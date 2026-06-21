# -*- coding: utf-8 -*-

"""
sheo_decrees.py — Système de Décrets Visuels et de Rôles pour Sheogorath.
Gère la superposition de texte sur parchemin et la manipulation des rôles Discord.
"""

import discord
import os
import re
import json
import time
import logging
import random
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

logger = logging.getLogger("sheogorath")

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
PARCHMENT_PATH = os.path.join(ASSETS_DIR, "parchment.png")

# Store persistant des décrets actifs (même volume que sheo_punishments.json,
# via la variable d'env DATA_DIR) → la suppression des rôles survit aux
# redémarrages du bot. Clé = str(role_id).
DATA_DIR = os.getenv("DATA_DIR", ".")
DECREES_FILE = os.path.join(DATA_DIR, "sheo_decrees_active.json")


def _load_decrees():
    if not os.path.exists(DECREES_FILE):
        return {}
    try:
        with open(DECREES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"⚠️ [DECRET] Erreur chargement store décrets : {e}")
        return {}


def _save_decrees(data):
    """Écriture atomique (tmp + os.replace) pour éviter la corruption en cas de crash."""
    tmp = DECREES_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, DECREES_FILE)
    except IOError as e:
        logger.error(f"❌ [DECRET] Erreur sauvegarde store décrets : {e}")


def _add_decree(entry):
    data = _load_decrees()
    data[str(entry["role_id"])] = entry
    _save_decrees(data)


def _remove_decree(role_id):
    data = _load_decrees()
    if str(role_id) in data:
        del data[str(role_id)]
        _save_decrees(data)

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


def _wrap_by_width(draw, text, font, max_width):
    """Découpe `text` en lignes qui tiennent dans `max_width` pixels."""
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if draw.textlength(trial, font=font) <= max_width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines

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

        # 2. On retire les emoji/symboles non couverts par la police (sinon carrés).
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

        # 4. Corps du texte : grande police auto-ajustée + retour à la ligne au
        #    pixel près, bloc centré horizontalement et verticalement dans le
        #    parchemin (sous le titre).
        body_margin = 120
        max_width = width - 2 * body_margin
        top = 300                      # sous le titre
        bottom = height - 150          # marge basse du parchemin
        zone_h = bottom - top

        body_size = 70
        while body_size > 30:
            font_text = _load_font(_FONT_CANDIDATES_REGULAR, body_size)
            lines = _wrap_by_width(draw, text, font_text, max_width)
            line_h = int(body_size * 1.35)
            if line_h * len(lines) <= zone_h:
                break
            body_size -= 4

        block_h = line_h * len(lines)
        y = top + max(0, (zone_h - block_h) // 2)   # centré verticalement
        for line in lines:
            lw = draw.textlength(line, font=font_text)
            draw.text(((width - lw) / 2, y), line, font=font_text, fill=COLORS["BLACK"])
            y += line_h

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
    La suppression est PERSISTÉE dans sheo_decrees_active.json : si le bot
    redémarre avant l'expiration, le filet `cleanup_old_decree_roles` (boucle
    périodique) garantit quand même la suppression.
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

        # 3.bis PERSISTANCE (survit aux redémarrages — le vrai filet est la boucle)
        _add_decree({
            "role_id": role.id,
            "guild_id": guild.id,
            "title": role_name,
            "expire_at": time.time() + duration,
        })

        # 4. Suppression différée best-effort (cas nominal sans redémarrage).
        #    En cas de redémarrage, cette tâche est perdue → cleanup_old_decree_roles
        #    (tasks.loop) prend le relais grâce au store persistant.
        async def delayed_cleanup():
            import asyncio
            await asyncio.sleep(duration)
            try:
                # On vérifie que c'est bien NOTRE rôle avant de supprimer
                if role.name.startswith("📜"):
                    await role.delete(reason="Fin du décret de Sheogorath")
                    logger.info(f"🧹 [DECRET] Rôle '{role_name}' supprimé après expiration.")
            except discord.NotFound:
                pass # Déjà supprimé (manuellement ou par le filet)
            except discord.Forbidden:
                logger.warning(f"⚠️ [DECRET] Permissions insuffisantes pour supprimer '{role_name}'.")
            except Exception as e:
                logger.error(f"❌ [DECRET] Erreur suppression rôle : {e}")
            finally:
                _remove_decree(role.id)

        import asyncio
        asyncio.create_task(delayed_cleanup())

        return role

    except Exception as e:
        logger.error(f"❌ [DECRET] Erreur gestion rôles : {e}")
        return None

async def cleanup_old_decree_roles(guild):
    """
    Filet de sécurité (appelé périodiquement via tasks.loop) :
    - supprime les rôles de décret EXPIRÉS d'après le store persistant ;
    - supprime aussi les rôles 📜 ORPHELINS (absents du store : créés avant ce
      mécanisme, ou par un redémarrage ayant perdu la tâche de suppression).
    Idempotent : ne fait rien s'il n'y a rien à nettoyer.
    """
    now = time.time()
    data = _load_decrees()
    changed = False

    # 1. Rôles suivis par le store. On collecte aussi tous les role_id suivis
    #    (toutes guilds) pour que le filet par-nom ne touche pas un décret valide.
    tracked_ids = set()
    for key, entry in list(data.items()):
        role_id = int(entry.get("role_id", 0))
        tracked_ids.add(role_id)
        if entry.get("guild_id") != guild.id:
            continue
        if entry.get("expire_at", 0) <= now:
            role = guild.get_role(role_id)
            if role:
                try:
                    await role.delete(reason="Décret expiré (nettoyage périodique)")
                    logger.info(f"🧹 [DECRET] Rôle expiré '{role.name}' supprimé (filet).")
                except discord.NotFound:
                    pass  # déjà disparu → on purge l'entrée quand même
                except discord.Forbidden:
                    logger.warning(f"⚠️ [DECRET] Permissions insuffisantes pour le rôle {role_id} ; nouvel essai au prochain tick.")
                    continue  # ne pas purger : on retentera
                except Exception as e:
                    logger.error(f"❌ [DECRET] Erreur suppression rôle {role_id}: {e}")
                    continue
            del data[key]
            changed = True

    # 2. Filet par-nom : rôles 📜 non suivis = orphelins (créés avant le store).
    for role in guild.roles:
        if role.name.startswith("📜") and role.id not in tracked_ids:
            try:
                await role.delete(reason="Rôle de décret orphelin (nettoyage)")
                logger.info(f"🧹 [DECRET] Rôle orphelin '{role.name}' supprimé (filet par-nom).")
            except discord.NotFound:
                pass
            except discord.Forbidden:
                logger.warning(f"⚠️ [DECRET] Permissions insuffisantes (orphelin '{role.name}').")
            except Exception as e:
                logger.error(f"❌ [DECRET] Erreur suppression orphelin '{role.name}': {e}")

    if changed:
        _save_decrees(data)
