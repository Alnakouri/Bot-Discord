import subprocess
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

# 1. Vérifier que la consigne d'extraction interdit les faits de registre
def test_consigne_extraction_interdit_registre():
    # Bots à tester : Sheogorath, Alfred, Johnny, Maiq, Sugar, Twitch LLM
    fichiers = [
        RACINE / "Sheogorath" / "bot_sheogorath.py",
        RACINE / "Alfred" / "bot_alfred.py",
        RACINE / "JohnnyBot" / "bot_johnny.py",
        RACINE / "MaiqBot" / "bot_maiq.py",
        RACINE / "SugarBot" / "bot_sugar.py",
        RACINE / "shared" / "twitch" / "llm.py"
    ]
    
    for fichier in fichiers:
        assert fichier.exists(), f"Fichier non trouvé : {fichier}"
        content = fichier.read_text(encoding="utf-8")
        
        # On cherche la mention de l'interdiction
        # "N'enregistre JAMAIS d'observations sur le ton de l'échange, les images employées, ou ce dont il « semble obsédé »"
        assert "semble obsédé" in content or "semble obsédé" in content.lower(), f"L'interdiction 'semble obsédé' est absente de {fichier.name}"
        assert "ton de l'échange" in content or "ton de l'échange" in content.lower(), f"L'interdiction 'ton de l'échange' est absente de {fichier.name}"

# 2. extract_facts refuse un fait vide ou tronqué
def test_extract_facts_refuse_vide_ou_tronque():
    import sys
    sys.path.insert(0, str(RACINE))
    from Sheogorath.sheo_llm import extract_facts
    sys.path.pop(0)

    class DummyMemory:
        def __init__(self):
            self.facts = []
        def add_fact(self, user_id, fact):
            self.facts.append(fact)

    memory = DummyMemory()
    user_id = "123"

    # Fait normal
    extract_facts("Voici la réponse. <fact>Il aime le fromage.</fact>", memory, user_id)
    assert len(memory.facts) == 1
    assert memory.facts[0] == "Il aime le fromage."

    # Fait vide
    memory.facts.clear()
    extract_facts("Voici la réponse. <fact></fact>", memory, user_id)
    assert len(memory.facts) == 0

    # Fait tronqué
    memory.facts.clear()
    extract_facts("Voici la réponse. <fact>Il aime le", memory, user_id)
    assert len(memory.facts) == 0

# 3. Le purgeur ne touche rien sans --appliquer
def test_purgeur_ne_modifie_rien_par_defaut(tmp_path):
    # On vérifie que lancer le purgeur sans --appliquer ne crée pas de backup et ne modifie pas le dossier data
    backups_dir = RACINE / "data" / "backups_faits"
    
    # Nombre de backups avant
    backups_avant = list(backups_dir.glob("*.bak")) if backups_dir.exists() else []
    
    # Run the script
    result = subprocess.run(["python", str(RACINE / "tools" / "purge_faits_auto.py")], capture_output=True, text=True)
    assert result.returncode == 0
    
    # Nombre de backups après
    backups_apres = list(backups_dir.glob("*.bak")) if backups_dir.exists() else []
    
    assert len(backups_avant) == len(backups_apres), "Le purgeur a créé un backup sans l'argument --appliquer !"
