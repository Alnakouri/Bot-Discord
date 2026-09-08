# -*- coding: utf-8 -*-
import os
import json
from pathlib import Path
from bot_manager import BOT_REGISTRY

DEFAULTS = {
    "decret_enabled": True,
    # Carnet de repartie : le bot tire une regle de comportement de ses defaites et se
    # l'injecte ensuite dans son prompt systeme. ⚠️ C'est la SEULE fonction qui reecrit la
    # persona a partir de ce qu'un inconnu a declenche : il faut pouvoir la couper d'un
    # clic sans redeployer. `shared/repartee_lessons.est_active` lit cette cle ici, par
    # bot — elle etait lue a la racine du fichier, ou elle n'existait jamais.
    "repartee_lessons_enabled": True,
    # Mode test par bot : ce bot ne publie que sur le serveur prive. S'ajoute a
    # l'interrupteur global (l'un des deux suffit), cf. shared/bot_features.py.
    "test_mode": False,
}

# Reglages qui ne dependent d'aucun bot, ranges sous la cle "_global" du meme fichier.
CLE_GLOBALE = "_global"
DEFAULTS_GLOBAUX = {
    "test_mode": False,      # bascule les 6 bots d'un geste
    "test_guild_id": None,   # serveur privé autorisé pendant le mode test
}

class FeaturesConfigManager:
    def __init__(self, data_dir: Path):
        self.config_path = data_dir / "bot_features.json"
        self.data_dir = data_dir

    def _load_raw(self) -> dict:
        if not self.config_path.exists():
            return {}
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_raw(self, data: dict):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        # Atomic write
        tmp_path = self.config_path.with_suffix(".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self.config_path)
        except Exception as e:
            if tmp_path.exists():
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass  # le temporaire a deja disparu ; l'erreur d'origine est relancee juste apres
            raise e

    def get_all(self) -> dict:
        cfg = self._load_raw()
        updated = False
        section = cfg.get(CLE_GLOBALE)
        if not isinstance(section, dict):
            cfg[CLE_GLOBALE] = section = {}
            updated = True
        for k, v in DEFAULTS_GLOBAUX.items():
            if k not in section:
                section[k] = v
                updated = True
        for bot_id in BOT_REGISTRY:
            if bot_id not in cfg:
                cfg[bot_id] = {}
                updated = True
            for k, v in DEFAULTS.items():
                if k not in cfg[bot_id]:
                    cfg[bot_id][k] = v
                    updated = True
        if updated:
            self._save_raw(cfg)
        return cfg

    def get_bot(self, bot_id: str) -> dict:
        if bot_id not in BOT_REGISTRY:
            raise ValueError(f"Bot '{bot_id}' non enregistré.")
        return self.get_all()[bot_id]

    def set_feature(self, bot_id: str, feature: str, value: bool):
        if bot_id not in BOT_REGISTRY:
            raise ValueError(f"Bot '{bot_id}' non enregistré.")
        if feature not in DEFAULTS:
            raise ValueError(f"Feature '{feature}' inconnue.")
        if not isinstance(value, bool):
            raise ValueError("'value' doit être un booléen.")
        cfg = self.get_all()
        cfg[bot_id][feature] = value
        self._save_raw(cfg)

    # ---------------------------------------------------------------- global

    def get_global(self) -> dict:
        return self.get_all()[CLE_GLOBALE]

    def set_global(self, cle: str, valeur):
        if cle not in DEFAULTS_GLOBAUX:
            raise ValueError(f"Réglage global '{cle}' inconnu.")
        if cle == "test_mode":
            if not isinstance(valeur, bool):
                raise ValueError("'value' doit être un booléen.")
        elif cle == "test_guild_id":
            # Un identifiant Discord est un entier 64 bits ; on le stocke en texte
            # pour ne pas le voir arrondi par le JSON du navigateur.
            if valeur in (None, "", 0):
                valeur = None
            else:
                try:
                    valeur = str(int(str(valeur).strip()))
                except (TypeError, ValueError):
                    raise ValueError("Identifiant de serveur invalide.")
        cfg = self.get_all()
        cfg[CLE_GLOBALE][cle] = valeur
        self._save_raw(cfg)
        return cfg[CLE_GLOBALE]

    def get_guilds(self) -> dict:
        """Serveurs remontés par les bots (shared/test_mode.enregistrer_serveurs).

        Le dashboard n'est pas un client Discord : sans cette remontée, il faudrait
        coller un identifiant à la main.
        """
        chemin = self.data_dir / "bot_guilds.json"
        if not chemin.exists():
            return {"guilds": [], "bots_vus": []}
        try:
            with open(chemin, "r", encoding="utf-8") as f:
                brut = json.load(f) or {}
        except Exception:
            return {"guilds": [], "bots_vus": []}

        fusion, bots_vus = {}, []
        for bot_id, bloc in brut.items():
            if not isinstance(bloc, dict):
                continue
            bots_vus.append(bot_id)
            for g in bloc.get("guilds", []):
                gid = str(g.get("id"))
                entree = fusion.setdefault(gid, {"id": gid, "name": g.get("name"), "bots": []})
                entree["bots"].append(bot_id)
        return {
            "guilds": sorted(fusion.values(), key=lambda g: (g["name"] or "").lower()),
            "bots_vus": sorted(bots_vus),
        }
