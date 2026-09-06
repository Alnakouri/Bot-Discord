import ast
import glob
from pathlib import Path

def test_commandes_une_seule_fois_et_ctx():
    from .conftest import BOT_FILES
    bot_files = BOT_FILES
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
    from .conftest import BOT_FILES
    bot_files = BOT_FILES
    assert len(bot_files) == 6, f"Bots manquants, trouves: {bot_files}"
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


def test_les_six_bots_posent_les_commandes_slash():
    """Malena etait le SEUL bot sans commandes slash — et ne les avait JAMAIS eues.

    `git log -S setup_slash_commands -- MalenaBot/` ne rendait rien sur tout
    l'historique : pas une regression, un oubli d'origine. Les 5 autres exposaient
    `/help` `/ping` `/stats` `/reputation` `/leaderboard` `/quests` `/birthday`, elle
    aucune — alors qu'elle a les mini-jeux et les anniversaires cables.

    ⚠️ Un test qui cherche le NOM passe au vert sur un simple import. On exige donc
    l'import ET les deux appels, lus dans l'AST.
    """
    from .conftest import BOT_FILES
    bot_files = BOT_FILES
    assert len(bot_files) == 6, f"Bots manquants, trouves: {bot_files}"

    for bot_file in bot_files:
        source = Path(bot_file).read_text(encoding="utf-8")
        tree = ast.parse(source)
        nom = Path(bot_file).name

        importe = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module == "shared.slash_commands"
            for alias in node.names
        }
        assert "setup_slash_commands" in importe, (
            f"{nom} n'importe pas setup_slash_commands depuis shared.slash_commands"
        )
        assert "sync_slash_commands" in importe, (
            f"{nom} n'importe pas sync_slash_commands : sans sync, Discord n'affiche rien"
        )

        appeles = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "setup_slash_commands" in appeles, (
            f"{nom} importe setup_slash_commands mais ne l'appelle jamais"
        )
        assert "sync_slash_commands" in appeles, (
            f"{nom} ne synchronise jamais l'arbre : les commandes n'apparaitront pas"
        )
