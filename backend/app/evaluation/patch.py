"""A minimal JSON Patch (RFC 6902 subset: add, replace, remove).

Benchmark cases describe how they break the base lesson as a list of these
operations, so a reviewer can see exactly what was changed.
"""

import copy
from typing import Any


class PatchError(ValueError):
    pass


def _parts(path: str) -> list[str]:
    if not path.startswith("/"):
        raise PatchError(f"path must start with '/': {path}")
    return [p.replace("~1", "/").replace("~0", "~") for p in path[1:].split("/")]


def _child(node: Any, key: str, path: str) -> Any:
    try:
        return node[int(key)] if isinstance(node, list) else node[key]
    except (KeyError, IndexError, ValueError) as exc:
        raise PatchError(f"path does not exist: {path}") from exc


def apply_patch(document: dict, operations: list[dict]) -> dict:
    """Return a patched deep copy; the original document is never changed."""
    doc = copy.deepcopy(document)
    for operation in operations:
        op, path = operation["op"], operation["path"]
        *parents, key = _parts(path)
        node = doc
        for part in parents:
            node = _child(node, part, path)

        if op == "remove":
            _child(node, key, path)  # must exist
            del node[int(key) if isinstance(node, list) else key]
        elif op == "replace":
            _child(node, key, path)  # must exist
            node[int(key) if isinstance(node, list) else key] = copy.deepcopy(operation["value"])
        elif op == "add":
            value = copy.deepcopy(operation["value"])
            if isinstance(node, list):
                if key == "-":
                    node.append(value)
                else:
                    index = int(key)
                    if not 0 <= index <= len(node):
                        raise PatchError(f"index out of range: {path}")
                    node.insert(index, value)
            else:
                node[key] = value
        else:
            raise PatchError(f"unsupported operation '{op}'")
    return doc
