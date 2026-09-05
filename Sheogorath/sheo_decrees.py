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
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from io import BytesIO

INSECABLE = " "
_PONCTUATION_DOUBLE = re.compile(r"\s+([!?;:])")

def espaces_francaises(texte):
    texte = " ".join((texte or "").split())      # normalise tabulations / retours
    return _PONCTUATION_DOUBLE.sub(lambda m: INSECABLE + m.group(1), texte)

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
    os.path.join(ASSETS_DIR, "MedievalSharp.ttf"),
    os.path.join(ASSETS_DIR, "DejaVuSerif.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "DejaVuSerif.ttf",
    "arial.ttf",
]
_FONT_CANDIDATES_BOLD = [
    os.path.join(ASSETS_DIR, "MedievalSharp.ttf"),  # pas de Bold MedievalSharp → même fichier
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
    text = (text or "").replace("œ", "oe").replace("Œ", "OE").replace("æ", "ae").replace("Æ", "AE")
    text = _EMOJI_RE.sub("", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def petites_capitales(draw, texte, font, x_center, y, couleur, ecart):
    """Dessine du texte en ajoutant un écart en pixels entre chaque caractère, centré sur x_center."""
    texte = texte.upper()
    largeur_totale = sum(draw.textlength(c, font=font) for c in texte) + ecart * (len(texte) - 1)
    x = x_center - largeur_totale / 2
    for c in texte:
        draw.text((x, y), c, font=font, fill=couleur)
        x += draw.textlength(c, font=font) + ecart


def justifie(draw, ligne, font, largeur_visee, derniere, x_start, y, couleur):
    """Dessine une ligne justifiée, ou au fer à gauche si `derniere`."""
    mots = ligne.split(" ")
    if not mots:
        return
    if derniere or len(mots) == 1:
        # Fer à gauche
        x = x_start
        for mot in mots:
            draw.text((x, y), mot, font=font, fill=couleur)
            x += draw.textlength(mot + " ", font=font)
        return

    # Justification
    largeur_mots = sum(draw.textlength(mot, font=font) for mot in mots)
    espace_dispo = largeur_visee - largeur_mots
    ecart_moyen = espace_dispo / (len(mots) - 1)
    
    x = x_start
    for i, mot in enumerate(mots):
        draw.text((x, y), mot, font=font, fill=couleur)
        if i < len(mots) - 1:
            x += draw.textlength(mot, font=font) + ecart_moyen



def _wrap_by_width(draw, text, font, max_width, indent_lines=0, indent_width=0):
    """Découpe `text` en lignes qui tiennent dans `max_width` pixels."""
    lines, cur = [], ""
    for word in espaces_francaises(text).split(" "):
        current_max = max_width - indent_width if len(lines) < indent_lines else max_width
        trial = (cur + " " + word).strip()
        if draw.textlength(trial, font=font) <= current_max or not cur:
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

# Couleurs du décret. Nommées plutôt qu'inline : la D.A. se règle ici, et un test
# peut détourner _HALO_CREME pour vérifier que le halo est réellement posé.
#
# Le halo crème flou sous le texte est CE QUI REND LE DÉCRET LISIBLE : l'encre seule sur
# un parchemin moucheté et bordé de brume violette se noie (rendu rejeté le 2026-08-30).
# Ne pas le remplacer par un `stroke_width` : le contour net donne un rendu d'autocollant.
_HALO_CREME = (250, 240, 214)
_ENCRE_SEPIA = (54, 34, 18)
_FILET_OR = (150, 106, 32)
# Gris de l'ombre du titre. Volontairement clair : l'image est en RGB, donc PIL
# ignore tout canal alpha — la douceur ne peut venir que de la couleur elle-meme.
_OMBRE_TITRE = (120, 100, 90)

# Bornes du corps de texte. 44 px est confortable pour un décret ordinaire ; 24 px est
# le plancher en dessous duquel on préfère un texte serré à un texte illisible.
_CORPS_MAX, _CORPS_MIN, _INTERLIGNE = 44, 24, 1.5


def _ajuster_corps(draw, text, max_width, zone_h, indent_lines=0, indent_width=0):
    """Choisit la plus grande taille de corps qui TIENT dans `zone_h`.

    Rend `(police, lignes, hauteur_de_ligne)`.

    ⚠️ Ne pas remplacer par une taille fixe. Une taille en dur ne déborde pas sur un
    décret court, mais Sheogorath en écrit de très longs : mesuré le 2026-08-30 avec
    `body_size = 40` figé, un décret de 12 lignes sortait **par le bas de l'image**, les
    trois dernières lignes coupées net. La boucle d'ajustement existait avant la refonte
    visuelle et avait disparu avec elle.
    """
    for taille in range(_CORPS_MAX, _CORPS_MIN - 1, -2):
        police = _load_font(_FONT_CANDIDATES_REGULAR, taille)
        lignes = _wrap_by_width(draw, text, police, max_width, indent_lines, indent_width)
        hauteur = int(taille * _INTERLIGNE)
        if hauteur * len(lignes) <= zone_h:
            return police, lignes, hauteur

    # Même au plancher ça déborde : on rend le plancher plutôt que rien, et on le dit.
    police = _load_font(_FONT_CANDIDATES_REGULAR, _CORPS_MIN)
    lignes = _wrap_by_width(draw, text, police, max_width, indent_lines, indent_width)
    logger.warning(
        "⚠️ [DECRET] Texte trop long même à %d px (%d lignes) : le bas sera coupé.",
        _CORPS_MIN, len(lignes))
    return police, lignes, int(_CORPS_MIN * _INTERLIGNE)


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

        # 2. On retire les emoji/symboles non couverts par la police
        title = _clean_for_image(title)
        text = _clean_for_image(text)

        # Sur-titre. ⚠️ UNE seule source pour la chaine : le halo et le texte visible
        # doivent etre poses avec le MEME texte et le MEME interlettrage. Les separer
        # (une chaine pre-espacee pour le masque, `petites_capitales` pour le rendu)
        # donnait un halo plus large que le texte, decale d'une dizaine de pixels.
        SUR_TITRE = "ÉDIT IMPÉRIAL"
        ECART_SUR_TITRE = 4
        font_sur_titre = _load_font(_FONT_CANDIDATES_REGULAR, 18)
        y_sur_titre = 100
        x_center = width / 2
        
        # 3. Écrire le Titre — taille max 64px, plier sur 2 lignes si besoin
        margin = 150
        max_title_w = width - 2 * margin
        title_size = 64
        while title_size > 28:
            font_title = _load_font(_FONT_CANDIDATES_BOLD, title_size)
            lines_title = _wrap_by_width(draw, title, font_title, max_title_w)
            if len(lines_title) <= 2:
                break
            title_size -= 4

        y_title = 135
        # On calcule où s'arrête le titre
        y_title_end = y_title
        for line_t in lines_title:
            y_title_end += int(title_size * 1.2)

        # Filet doré avec losange
        filet_y = y_title_end + 15
        filet_w = 400
        
        # 4. Corps du texte
        body_margin = 185
        max_width = width - 2 * body_margin
        top = filet_y + 40
        bottom = height - 150
        zone_h = bottom - top

        # Gestion de la lettrine
        lettrine = text[0] if text else ""
        reste_texte = text[1:] if text else ""
        
        # Taille fixe pour la lettrine : 2.5x le corps max
        lettrine_size = int(_CORPS_MAX * 2.5)
        font_lettrine = _load_font(_FONT_CANDIDATES_REGULAR, lettrine_size)
        lettrine_w = draw.textlength(lettrine, font=font_lettrine)
        indent_w = lettrine_w + 12
        indent_lines = 2
        
        font_text, lines, line_h = _ajuster_corps(draw, reste_texte, max_width, zone_h, indent_lines=indent_lines, indent_width=indent_w)
        
        block_h = line_h * len(lines)
        y_body = top + max(0, (zone_h - block_h) // 2)

        # Masque du halo : sur-titre, titre, lettrine et corps. PAS le filet ni le
        # losange — ce sont des aplats, ils se lisent sans etre detoures.
        txt_mask = Image.new('L', img.size, 0)
        draw_mask = ImageDraw.Draw(txt_mask)
        
        # Halo Sur-titre
        petites_capitales(draw_mask, SUR_TITRE, font_sur_titre, x_center, y_sur_titre,
                          255, ECART_SUR_TITRE)
        
        # Halo Titre
        y_m = y_title
        for line_t in lines_title:
            tw = draw.textlength(line_t, font=font_title)
            draw_mask.text(((width - tw) / 2, y_m), line_t, font=font_title, fill=255)
            y_m += int(title_size * 1.2)
            
        # Halo lettrine
        draw_mask.text((body_margin, y_body), lettrine, font=font_lettrine, fill=255)
        
        # Halo Corps
        y_mask = y_body
        for i, line in enumerate(lines):
            x_m = body_margin + (indent_w if i < indent_lines else 0)
            draw_mask.text((x_m, y_mask), line, font=font_text, fill=255)
            y_mask += line_h
            
        blurred_mask = txt_mask.filter(ImageFilter.GaussianBlur(6))
        cream_layer = Image.new('RGB', img.size, _HALO_CREME)
        img.paste(cream_layer, (0, 0), blurred_mask)
        
        # Texte par-dessus
        draw_text_final = ImageDraw.Draw(img)
        
        # Dessin Sur-titre (petites capitales)
        petites_capitales(draw_text_final, SUR_TITRE, font_sur_titre, x_center, y_sur_titre,
                          _ENCRE_SEPIA, ECART_SUR_TITRE)
        
        # Dessin Titre
        y_t = y_title
        for line_t in lines_title:
            tw = draw_text_final.textlength(line_t, font=font_title)
            # Ombre portee. ⚠️ PIL ignore le canal alpha sur une image RGB : un
            # `fill=(50, 50, 50, 100)` donnait un gris PLEIN, pas une ombre douce.
            # La douceur vient donc d'un gris deja proche du parchemin, pas d'alpha.
            draw_text_final.text(((width - tw) / 2 + 3, y_t + 3), line_t, font=font_title,
                                 fill=_OMBRE_TITRE)
            draw_text_final.text(((width - tw) / 2, y_t), line_t, font=font_title, fill=COLORS["PURPLE"])
            y_t += int(title_size * 1.2)
            
        # Dessin Filet avec losange
        draw_text_final.line(((width - filet_w) / 2, filet_y, (width + filet_w) / 2, filet_y), fill=_FILET_OR, width=2)
        draw_text_final.regular_polygon((x_center, filet_y, 12), 4, rotation=45, fill=COLORS["PURPLE"])
        
        # Dessin lettrine
        # Ajustement manuel pour la lettrine (aligner avec le texte)
        y_lettrine = y_body - (lettrine_size * 0.15)
        draw_text_final.text((body_margin, y_lettrine), lettrine, font=font_lettrine, fill=COLORS["PURPLE"])
        
        # Dessin Corps justifié
        y_text = y_body
        for i, line in enumerate(lines):
            x_start = body_margin + (indent_w if i < indent_lines else 0)
            largeur_visee = max_width - (indent_w if i < indent_lines else 0)
            derniere = (i == len(lines) - 1)
            
            if "@" in line:
                mots = line.split(" ")
                largeur_mots = sum(draw_text_final.textlength(mot, font=font_text) for mot in mots)
                espace_dispo = largeur_visee - largeur_mots
                ecart_moyen = espace_dispo / (len(mots) - 1) if len(mots) > 1 and not derniere else 0
                
                x = x_start
                for mot in mots:
                    is_pseudo = mot.startswith("@")
                    color = COLORS["PURPLE"] if is_pseudo else _ENCRE_SEPIA
                    draw_text_final.text((x, y_text), mot, font=font_text, fill=color)
                    if is_pseudo:
                        mw = draw_text_final.textlength(mot, font=font_text)
                        draw_text_final.line((x, y_text + line_h - 4, x + mw, y_text + line_h - 4), fill=COLORS["PURPLE"], width=2)
                    
                    x += draw_text_final.textlength(mot, font=font_text) + (ecart_moyen if not derniere else draw_text_final.textlength(" ", font=font_text))
            else:
                justifie(draw_text_final, line, font_text, largeur_visee, derniere, x_start, y_text, _ENCRE_SEPIA)
            y_text += line_h

        # 5. Sauvegarder en mémoire
        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf

    except Exception as e:
        logger.error(f"❌ [DECRET] Erreur génération image : {e}")
        return None



async def _resoudre_membre(guild, cible):
    """Rend un Member pour `cible`, ou None si la resolution echoue.

    `discord.User` et `discord.Member` se ressemblent — meme `id`, meme
    `display_name` — mais seul Member appartient a une guilde, donc seul Member sait
    porter un role. Un User arrive des qu'on prend `message.author` sur un auteur
    absent du cache des membres.

    On ne devine pas : `add_roles` est la seule chose qui nous interesse, on teste sa
    presence plutot que le type (une sous-classe, un mock de test ou une version
    future de discord.py restent acceptes).
    """
    if hasattr(cible, "add_roles"):
        return cible
    if guild is None or not hasattr(cible, "id"):
        logger.error("❌ [DECRET] Cible inutilisable : ni Member, ni identifiable.")
        return None

    membre = guild.get_member(cible.id)          # cache : gratuit
    if membre is not None:
        return membre
    try:
        return await guild.fetch_member(cible.id)   # sinon un appel API
    except Exception as e:
        logger.error(
            f"❌ [DECRET] {getattr(cible, 'display_name', cible.id)} introuvable dans "
            f"la guilde : {e} — aucun role cree (mieux qu'un role que personne ne porte)."
        )
        return None


async def apply_decree_role(guild, member, title, duration=600):
    """
    Crée un rôle de décret, l'assigne, puis le supprime après 'duration' secondes.
    La suppression est PERSISTÉE dans sheo_decrees_active.json : si le bot
    redémarre avant l'expiration, le filet `cleanup_old_decree_roles` (boucle
    périodique) garantit quand même la suppression.
    """
    try:
        # 0. La cible DOIT être un Member : seul Member porte `add_roles`, User ne
        #    l'a pas. Ça ne se voyait pas avec `!decret @qqun` — la signature
        #    `target: discord.Member` convertit — mais SANS argument la cible est tirée
        #    au sort dans l'historique du salon, et `msg.author` y est un User dès que
        #    l'auteur n'est pas dans le cache des membres. Mesuré en test live le
        #    2026-08-31 : « 'User' object has no attribute 'add_roles' ». Le décret
        #    s'affichait quand même, le rôle était créé, personne ne le portait, et le
        #    balayage l'effaçait 10 min plus tard — un échec parfaitement invisible.
        member = await _resoudre_membre(guild, member)
        if member is None:
            return None

        role_name = f"📜 {title.upper()}"

        # 1. Création du rôle
        color = discord.Color.from_rgb(*random.choice([COLORS["PURPLE"], COLORS["GOLD"], COLORS["CHEESE"]]))
        role = await guild.create_role(
            name=role_name,
            color=color,
            hoist=True,
            reason=f"Décret de Sheogorath pour {member.display_name}"
        )

        # 1.bis PERSISTANCE IMMÉDIATE (survit aux redémarrages — le vrai filet est la
        #       boucle). Fait AVANT tout autre await : sinon, pendant les await suivants
        #       (position/add_roles), la boucle de nettoyage pourrait voir ce rôle 📜
        #       absent du store et le supprimer comme « orphelin ».
        _add_decree({
            "role_id": role.id,
            "guild_id": guild.id,
            "title": role_name,
            "expire_at": time.time() + duration,
        })

        # 2. Placement hiérarchique
        bot_role = guild.me.top_role
        new_pos = max(1, bot_role.position - 1)
        try:
            await role.edit(position=new_pos)
        except discord.Forbidden as e:
            logger.debug(f"[DECRET] placement hierarchique du role refuse : {e}")

        # 3. Assignation. Échec attendu si la cible est le PROPRIÉTAIRE du serveur
        #    (Discord interdit à tout bot de gérer ses rôles) ou si elle a un rôle
        #    plus haut que le bot. Dans ce cas on annule le rôle qu'on vient de créer
        #    pour ne pas laisser un 📜 fantôme (non assigné) traîner jusqu'au balayage.
        try:
            await member.add_roles(role)
        except discord.Forbidden:
            logger.warning(
                f"⚠️ [DECRET] Impossible d'assigner '{role_name}' à {member.display_name} "
                f"(propriétaire du serveur ou rôle trop haut) → annulation du rôle."
            )
            try:
                await role.delete(reason="Décret non assignable (cible protégée)")
            except discord.HTTPException as e:
                logger.debug(f"[DECRET] suppression du role non assignable impossible : {e}")
            _remove_decree(role.id)
            return None
        logger.info(f"👑 [DECRET] Rôle '{role_name}' assigné à {member.display_name} pour {duration}s")

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
                pass  # le role a deja disparu, c'est precisement le but recherche
            except discord.Forbidden:
                logger.warning(f"⚠️ [DECRET] Permissions insuffisantes (orphelin '{role.name}').")
            except Exception as e:
                logger.error(f"❌ [DECRET] Erreur suppression orphelin '{role.name}': {e}")

    if changed:
        _save_decrees(data)
