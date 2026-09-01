import ast
import glob
from pathlib import Path

def test_commandes_une_seule_fois_et_ctx():
    bot_files = glob.glob("*Bot/bot_*.py") + ["Alfred/bot_alfred.py", "Sheogorath/bot_sheogorath.py"]
    assert len(bot_files) == 6, f"Bots manquants, trouves: {bot_files}"
    
    for bot_file in bot_files:
        with open(bot_file, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())
            
        on_message_found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "on_message":
                on_message_found = True
                
                process_cmds = 0
                for child in ast.walk(node):
                    if isinstance(child, ast.Await) and isinstance(child.value, ast.Call):
                        call = child.value
                        if isinstance(call.func, ast.Attribute) and call.func.attr == "process_commands":
                            process_cmds += 1
                            
                assert process_cmds == 1, f"{bot_file} doit avoir exactement 1 process_commands dans on_message (trouvé {process_cmds})"
                
                ctx_valid_found = False
                for child in ast.walk(node):
                    if isinstance(child, ast.Attribute) and child.attr == "valid":
                        ctx_valid_found = True
                        break
                        
                assert ctx_valid_found, f"{bot_file} doit verifier ctx.valid apres process_commands"
                
        assert on_message_found, f"Fonction on_message introuvable dans {bot_file}"

def test_anti_collision():
    bot_files = glob.glob("*Bot/bot_*.py") + ["Alfred/bot_alfred.py", "Sheogorath/bot_sheogorath.py"]
    all_commands = {}
    collisions = []
    
    for bot_file in bot_files:
        bot_name = Path(bot_file).parent.name
        with open(bot_file, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())
            
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef):
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr == "command":
                        cmd_names = []
                        for kw in dec.keywords:
                            if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                                cmd_names.append(kw.value.value)
                            elif kw.arg == "aliases" and isinstance(kw.value, (ast.List, ast.Tuple)):
                                for elt in kw.value.elts:
                                    if isinstance(elt, ast.Constant):
                                        cmd_names.append(elt.value)
                                        
                        for name in cmd_names:
                            if name == "oubliemoi":
                                continue  # Commande globale intentionnelle
                            if name not in all_commands:
                                all_commands[name] = bot_name
                            elif all_commands[name] != bot_name:
                                collisions.append(f"'{name}' ({all_commands[name]} vs {bot_name})")
                                
    if collisions:
        assert False, "Collisions détectées :\n" + "\n".join(collisions)
