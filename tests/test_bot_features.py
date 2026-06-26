# -*- coding: utf-8 -*-
import os
import json
import time
import pytest
import sys
from pathlib import Path

# Inject parent directory and dashboard/backend to path
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)
backend_dir = os.path.join(_parent_dir, "dashboard", "backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from shared.bot_features import is_feature_enabled, _CACHE
from features_config import FeaturesConfigManager

@pytest.fixture(autouse=True)
def setup_temp_data_dir(tmp_path, monkeypatch):
    # Reset cache between tests
    _CACHE["data"] = None
    _CACHE["ts"] = 0.0
    
    # Patch DATA_DIR in shared.bot_features
    monkeypatch.setattr("shared.bot_features.DATA_DIR", str(tmp_path))
    
    return tmp_path

def test_is_feature_enabled_file_absent():
    # If file is absent, should return the default value
    assert is_feature_enabled("sheogorath", "decret_enabled", default=True) is True
    assert is_feature_enabled("sheogorath", "decret_enabled", default=False) is False

def test_is_feature_enabled_file_present(setup_temp_data_dir):
    tmp_dir = setup_temp_data_dir
    config_file = tmp_dir / "bot_features.json"
    
    # Save a config with feature disabled
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump({"sheogorath": {"decret_enabled": False}}, f)
        
    assert is_feature_enabled("sheogorath", "decret_enabled", default=True) is False

def test_is_feature_enabled_corrupted_json(setup_temp_data_dir):
    tmp_dir = setup_temp_data_dir
    config_file = tmp_dir / "bot_features.json"
    
    # Save corrupted/invalid JSON
    with open(config_file, "w", encoding="utf-8") as f:
        f.write("{invalid json...")
        
    # Should fall back to default and NOT raise exception
    assert is_feature_enabled("sheogorath", "decret_enabled", default=True) is True
    assert is_feature_enabled("sheogorath", "decret_enabled", default=False) is False

def test_features_config_manager(setup_temp_data_dir):
    tmp_dir = setup_temp_data_dir
    manager = FeaturesConfigManager(tmp_dir)
    
    # Get all should initialize with defaults
    cfg = manager.get_all()
    assert "sheogorath" in cfg
    assert cfg["sheogorath"]["decret_enabled"] is True
    
    # Set feature
    manager.set_feature("sheogorath", "decret_enabled", False)
    assert manager.get_bot("sheogorath")["decret_enabled"] is False
    
    # Errors on unknown bot or feature
    with pytest.raises(ValueError):
        manager.set_feature("unknown_bot", "decret_enabled", False)
        
    with pytest.raises(ValueError):
        manager.set_feature("sheogorath", "unknown_feature", False)
        
    with pytest.raises(ValueError):
        manager.set_feature("sheogorath", "decret_enabled", "not_a_bool")

def test_cache_ttl(setup_temp_data_dir, monkeypatch):
    tmp_dir = setup_temp_data_dir
    config_file = tmp_dir / "bot_features.json"
    
    # 1. Write initially enabled
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump({"sheogorath": {"decret_enabled": True}}, f)
        
    # First read (caches value)
    assert is_feature_enabled("sheogorath", "decret_enabled") is True
    
    # 2. Modify file in background
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump({"sheogorath": {"decret_enabled": False}}, f)
        
    # Immediate read should return cached value (True) because TTL not expired
    assert is_feature_enabled("sheogorath", "decret_enabled") is True
    
    # 3. Simulate time passing (monkeypatch time.time to be +6 seconds)
    now = time.time()
    monkeypatch.setattr(time, "time", lambda: now + 6.0)
    
    # Read now should return updated value (False) as TTL expired
    assert is_feature_enabled("sheogorath", "decret_enabled") is False
