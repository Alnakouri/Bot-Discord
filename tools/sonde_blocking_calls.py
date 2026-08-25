# -*- coding: utf-8 -*-
"""Sonde anti-régression : la boucle asyncio des bots ne doit jamais être bloquée.

Trois contrôles, tous statiques (AST), à lancer depuis la racine du dépôt :

    python tools/sonde_blocking_calls.py

1. APPEL BLOQUANT — un SDK LLM synchrone (`google-genai`, `groq`, `mistralai`,
   `openai`) appelé directement dans une coroutine gèle toute la boucle pendant
   la génération : heartbeat Discord suspendu, WebSocket Twitch muet, tâches
   périodiques en retard. Il faut `asyncio.to_thread`.

2. PIÈGE DES PARENTHÈSES — `asyncio.to_thread(fn(...))` exécute `fn` AVANT de
   passer le résultat au thread : ça bloque exactement comme avant, sans erreur
   visible. Il faut passer la fonction par référence : `asyncio.to_thread(fn, ...)`.

3. MASQUAGE D'`asyncio` — un `import asyncio` au milieu d'une fonction rend le nom
   LOCAL à tout son corps : chaque `asyncio.x` situé plus haut lève
   `UnboundLocalError` à l'exécution. Ce bug a rendu M'aiq et Alfred muets, et il
   est invisible à `py_compile` comme aux tests.

Code de sortie : 0 si tout est propre, 1 sinon (utilisable en CI).
"""
import ast
import pathlib
import sys

BLOCK = ('generate_content', 'chat.completions.create', 'chat.complete')


def coroutine_ranges(tree):
    """Lignes couvertes par chaque fonction, avec le drapeau async."""
    out = []

    def walk(n):
        for ch in ast.iter_child_nodes(n):
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out.append((ch.lineno, ch.end_lineno, isinstance(ch, ast.AsyncFunctionDef), ch.name))
            walk(ch)

    walk(tree)
    return out


def in_coroutine(ranges, lineno):
    inner = [r for r in ranges if r[0] <= lineno <= r[1]]
    return bool(inner) and max(inner, key=lambda r: r[0])[2]


def wrapped_calls(src, tree):
    """Noeuds d'appel déjà enveloppés dans to_thread / run_in_executor."""
    wrapped = set()
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = ast.get_source_segment(src, n.func) or ''
        if 'to_thread' in f or 'run_in_executor' in f:
            for a in n.args:
                wrapped.add((a.lineno, a.col_offset))
    return wrapped


def check_file(path):
    src = path.read_text(encoding='utf-8')
    tree = ast.parse(src)
    ranges = coroutine_ranges(tree)
    wrapped = wrapped_calls(src, tree)
    problems = []

    # 1 + 2 : appels LLM
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = (ast.get_source_segment(src, n.func) or '').strip()

        # 2. to_thread(fn(...)) : le 1er argument est un APPEL, pas une référence
        if ('to_thread' in f or 'run_in_executor' in f) and n.args:
            a0 = n.args[0]
            if isinstance(a0, ast.Call):
                seg = (ast.get_source_segment(src, a0.func) or '').strip()
                if any(b in seg for b in BLOCK):
                    problems.append((n.lineno, f"to_thread({seg}(...)) : parentheses de trop, "
                                               f"l'appel s'execute AVANT le thread"))
            continue

        # 1. appel LLM synchrone dans une coroutine
        if not any(b in f for b in BLOCK):
            continue
        if (n.lineno, n.col_offset) in wrapped:
            continue
        if in_coroutine(ranges, n.lineno):
            problems.append((n.lineno, f"{f}(...) bloquant dans une coroutine "
                                       f"-> envelopper dans asyncio.to_thread"))

    # 3. import asyncio local masquant le module
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        local = []

        def scan(n):
            for ch in ast.iter_child_nodes(n):
                if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                    continue
                if isinstance(ch, ast.Import):
                    for a in ch.names:
                        if a.name == 'asyncio' and a.asname is None:
                            local.append(ch.lineno)
                scan(ch)

        scan(fn)
        if not local:
            continue
        first = min(local)
        before = sorted({
            n.value.lineno
            for n in ast.walk(fn)
            if isinstance(n, ast.Attribute)
            and isinstance(n.value, ast.Name)
            and n.value.id == 'asyncio'
            and n.value.lineno < first
        })
        if before:
            problems.append((first, f"'import asyncio' local dans {fn.name}() masque le module : "
                                    f"UnboundLocalError sur les lignes {before[:5]}"))

    return sorted(problems)


def main():
    root = pathlib.Path('.')
    files = sorted(root.glob('*/bot_*.py'))
    if not files:
        print("Aucun bot_*.py trouve : lancer la sonde depuis la racine du depot.")
        return 1

    total = 0
    for p in files:
        problems = check_file(p)
        total += len(problems)
        if problems:
            print(f"{p} : {len(problems)} probleme(s)")
            for ln, msg in problems:
                print(f"    L{ln} : {msg}")
        else:
            print(f"{p} : OK")

    print()
    if total:
        print(f"TOTAL : {total} probleme(s) -> ATTENDU : 0")
        return 1
    print("TOTAL : 0 probleme -> la boucle asyncio n'est bloquee nulle part.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
