"""A name a handler uses must exist when it runs. Python only finds out when that line executes, so
a missing import in a branch tests don't reach ships and then fails for a real request (the preview
of a memo with a deal did exactly that). This reads every function in the API modules and checks that
each name it loads is bound somewhere it can see."""

import ast
import builtins
import glob

import pytest

API_MODULES = sorted(glob.glob("app/api/*.py"))


def _bound_in_module(tree: ast.Module) -> set[str]:
    names = set(dir(builtins)) | {"__name__", "__file__"}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)) and node in tree.body:
            for alias in node.names:
                names.add((alias.asname or alias.name).split(".")[0])
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                names |= {n.id for n in ast.walk(target) if isinstance(n, ast.Name)}
        elif isinstance(node, (ast.If, ast.Try, ast.With, ast.For)):
            for inner in ast.walk(node):
                if isinstance(inner, (ast.Import, ast.ImportFrom)):
                    names |= {(a.asname or a.name).split(".")[0] for a in inner.names}
                elif isinstance(inner, ast.Name) and isinstance(inner.ctx, ast.Store):
                    names.add(inner.id)
                elif isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    names.add(inner.name)
    return names


def _bound_in_function(fn) -> set[str]:
    names = {a.arg for a in fn.args.args + fn.args.kwonlyargs + fn.args.posonlyargs}
    if fn.args.vararg:
        names.add(fn.args.vararg.arg)
    if fn.args.kwarg:
        names.add(fn.args.kwarg.arg)
    for node in ast.walk(fn):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names |= {(a.asname or a.name).split(".")[0] for a in node.names}
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
            if not isinstance(node, ast.ClassDef):
                names |= {a.arg for a in node.args.args + node.args.kwonlyargs + node.args.posonlyargs}
                if node.args.vararg:
                    names.add(node.args.vararg.arg)
                if node.args.kwarg:
                    names.add(node.args.kwarg.arg)
        elif isinstance(node, ast.Lambda):
            names |= {a.arg for a in node.args.args + node.args.kwonlyargs}
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            names |= set(node.names)
    return names


@pytest.mark.parametrize("path", API_MODULES)
def test_every_name_a_handler_uses_is_defined(path):
    tree = ast.parse(open(path, encoding="utf-8").read())
    module = _bound_in_module(tree)
    missing: list[str] = []
    for fn in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        visible = module | _bound_in_function(fn)
        # A nested function sees the names of the functions around it.
        for outer in [o for o in ast.walk(tree) if isinstance(o, (ast.FunctionDef, ast.AsyncFunctionDef)) and o is not fn]:
            if any(inner is fn for inner in ast.walk(outer)):
                visible |= _bound_in_function(outer)
        used = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
        for name in sorted(used - visible):
            missing.append(f"{fn.name}: {name}")
    assert not missing, f"{path} uses names that are never defined: {missing}"
