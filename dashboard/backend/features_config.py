# -*- coding: utf-8 -*-
import os
import json
from pathlib import Path
from bot_manager import BOT_REGISTRY

DEFAULTS = {"decret_enabled": True}   # extensible : ajouter ici les futures features Discord

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
                    pass
            raise e

    def get_all(self) -> dict:
        cfg = self._load_raw()
        updated = False
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
