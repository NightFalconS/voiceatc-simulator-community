#!/usr/bin/env python3
"""Validate session skins (``panels.json``) with the game's strict rules.

    python tools/validate_skin.py SKINS/harbour-blue/panels.json L/LE/panels.json

This is a port of the game's ``InterfaceSpec.strict_errors(raw)``
(``scripts/ui/session/interface_spec.gd`` and ``interface_validator.gd``): the JSON Schema
(``tools/interface_contract/interface.schema.json``, vendored from a pinned game commit by
``tools/sync_interface_contract.py``) read as data, plus the rules a schema cannot say:

- parity: a component with ``slots`` places every one of its features exactly once (the top
  plus the bottom when the bottom is ``merged_into_top``); slot names belong to the mode;
  template ids are the component's features;
- dock: ``value_popup``/``wpt``/``menus`` ``dock_strip`` and ``bottom`` ``merged_into_top`` need
  ``top`` ``dcb_grid``; ``window.close`` ``cell`` needs ``window.top_strip`` ``bar``;
- role references (``text``, ``fill``, ``font``, ``type``...) name a role the resolved tokens define;
- every mode or window feature that is not Generic's must be a capability the game supports.

Every error carries its JSON path and, where one is close, a "did you mean" hint. ``extends``
is resolved inside this repository: ``scope:<path>`` is ``<path>/panels.json`` and
``skin:<id>`` is ``SKINS/<id>/panels.json``. Exit code 1 when any file has an error.
Guide: documentation/skins-modding.md
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CONTRACT_DIR = Path(__file__).resolve().parent / "interface_contract"
GENERIC_ID = "generic"
SCOPE_PREFIX = "scope:"
SKIN_PREFIX = "skin:"
MAX_DEPTH = 4
# The slot names each component mode lays features into (InterfaceValidator.MODE_SLOTS).
MODE_SLOTS = {
    "top.cell_row": ["left", "right"],
    "top.dcb_grid": ["columns", "status"],
}
# Components whose modes need the top dcb_grid (InterfaceValidator.NEEDS_DCB_GRID).
NEEDS_DCB_GRID = {
    "value_popup": "dock_strip", "wpt": "dock_strip", "menus": "dock_strip",
    "bottom": "merged_into_top",
}


@lru_cache(maxsize=1)
def schema() -> dict[str, Any]:
    return json.loads((CONTRACT_DIR / "interface.schema.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_contract() -> dict[str, Any]:
    return json.loads((CONTRACT_DIR / "contract.json").read_text(encoding="utf-8"))


def generic() -> dict[str, Any]:
    return json.loads((CONTRACT_DIR / "generic.panels.json").read_text(encoding="utf-8"))


# --- hints -------------------------------------------------------------------------------

def similarity(a: str, b: str) -> float:
    """Godot's String.similarity: the Sorensen-Dice coefficient of the two bigram lists."""
    if a == b:
        return 1.0
    if len(a) < 2 or len(b) < 2:
        return 0.0
    src = [a[i:i + 2] for i in range(len(a) - 1)]
    tgt = [b[i:i + 2] for i in range(len(b) - 1)]
    inter = sum(1 for pair in src if pair in tgt)
    return 2.0 * inter / (len(src) + len(tgt))


def hint(word: str, options: list[Any]) -> str:
    """" (did you mean 'x'?)" for the closest of ``options``, or ""."""
    best, best_score = "", 0.5
    for option in options:
        score = similarity(word, str(option))
        if score > best_score:
            best, best_score = str(option), score
    return f" (did you mean '{best}'?)" if best else ""


# --- the schema walk (InterfaceValidator.check) --------------------------------------------

def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_type(value: Any, kind: str) -> bool:
    if kind == "string":
        return isinstance(value, str)
    if kind == "integer":
        return _is_number(value) and math.isfinite(value) and float(value) == math.floor(value)
    if kind == "number":
        return _is_number(value)
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "object":
        return isinstance(value, dict)
    if kind == "array":
        return isinstance(value, list)
    return True


def _same(option: Any, value: Any) -> bool:
    if _is_number(option) and _is_number(value):
        return float(option) == float(value)
    return type(option) is type(value) and option == value


def _matches(text: str, pattern: str) -> bool:
    return not pattern or re.search(pattern, text) is not None


def _deref(node: dict[str, Any]) -> dict[str, Any]:
    rule = node
    while "$ref" in rule:
        name = str(rule["$ref"]).removeprefix("#/$defs/")
        merged = dict(schema()["$defs"][name])
        merged.update({key: value for key, value in rule.items() if key != "$ref"})
        rule = merged
    return rule


def _show(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _scalar_error(value: Any, rule: dict[str, Any], known: dict[str, list[str]]) -> str:
    kinds = rule["type"] if isinstance(rule.get("type"), list) else [rule.get("type", "")]
    if not any(_is_type(value, str(kind)) for kind in kinds):
        return "expected " + " or ".join(kinds)
    if "enum" in rule and not any(_same(option, value) for option in rule["enum"]):
        return (f"'{_show(value)}' is not one of {json.dumps(rule['enum'])}"
                f"{hint(_show(value), rule['enum'])}")
    if _is_number(value) and (value < rule.get("minimum", -math.inf)
                              or value > rule.get("maximum", math.inf)):
        return f"{_show(value)} is outside {rule.get('minimum', '')}..{rule.get('maximum', '')}"
    if isinstance(value, str) and (len(value) > int(rule.get("maxLength", 100000))
                                   or not _matches(value, str(rule.get("pattern", "")))):
        return f"'{value}' is not a valid value"
    if isinstance(value, list) and not (
            int(rule.get("minItems", 0)) <= len(value) <= int(rule.get("maxItems", 100000))):
        return f"expected {rule.get('minItems', 0)} to {rule.get('maxItems', 'any')} items"
    if "x-ref" in rule and value not in known[rule["x-ref"]]:
        roles = known[rule["x-ref"]]
        return f"no {rule['x-ref']} role '{value}'{hint(str(value), roles)}"
    return ""


def _walk(value: Any, node: dict[str, Any], path: str, ctx: dict[str, Any]) -> tuple[bool, Any]:
    rule = _deref(node)
    if "x-capability" in rule and isinstance(value, str) and value != rule.get("default"):
        ctx["capabilities"].append((f"interface.{rule['x-capability']}.{value}", rule["enum"]))
        if value not in rule["enum"]:
            return True, value
    why = _scalar_error(value, rule, ctx["known"])
    if why:
        ctx["errors"].append(f"{path.removeprefix('.')}: {why}")
        return False, None
    if isinstance(value, dict):
        return True, _walk_object(value, rule, path, ctx)
    if isinstance(value, list) and "items" in rule:
        for index, item in enumerate(value):
            if not _walk(item, rule["items"], f"{path}[{index}]", ctx)[0]:
                return False, None
    if str(rule.get("type", "")) == "integer":
        return True, int(value)
    return True, value


def _walk_object(value: dict[str, Any], rule: dict[str, Any], path: str,
                 ctx: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    properties: dict[str, Any] = rule.get("properties", {})
    extra = rule.get("additionalProperties", True)
    name_pattern = str(rule.get("propertyNames", {}).get("pattern", ""))
    for key, item in value.items():
        child = properties.get(key, extra)
        if key not in properties and ((extra is False) or not _matches(key, name_pattern)):
            ctx["errors"].append(
                f"{(path + '.' + key).removeprefix('.')}: unknown key{hint(key, list(properties))}")
            continue
        if isinstance(child, bool):
            cleaned[key] = item
            continue
        ok, result = _walk(item, child, path + "." + key, ctx)
        if ok:
            cleaned[key] = result
    return cleaned


def check(raw: dict[str, Any], tokens: dict[str, Any]) -> dict[str, Any]:
    """{value: the valid part, errors: ["path: why"], capabilities: [(name, known modes)]}."""
    known = {kind: list(tokens.get(kind, {})) if isinstance(tokens.get(kind), dict) else []
             for kind in ("colors", "fonts", "type")}
    ctx: dict[str, Any] = {"errors": [], "known": known, "capabilities": []}
    ok, value = _walk(raw, schema(), "", ctx)
    return {"value": value if ok else {}, "errors": ctx["errors"],
            "capabilities": ctx["capabilities"]}


# --- the rules beyond the schema (InterfaceValidator.rule_errors) --------------------------

def _mode(components: dict[str, Any], component: str) -> str:
    entry = components.get(component, {})
    return str(entry.get("mode", "")) if isinstance(entry, dict) else ""


def _slot_ids(item: Any) -> list[Any]:
    if isinstance(item, str):
        return [item]
    if isinstance(item, list):
        return item
    return item.get("ids", []) if isinstance(item, dict) else []


def _check_slots(component: str, components: dict[str, Any], errors: list[str]) -> None:
    features = load_contract()["features"]
    entry = components[component]
    mode = _mode(components, component)
    allowed = MODE_SLOTS.get(f"{component}.{mode}", [])
    expected = list(features.get(component, []))
    if component == "top" and _mode(components, "bottom") == "merged_into_top":
        expected.extend(features["bottom"])
    placed: set[Any] = set()
    for slot, items in entry["slots"].items():
        path = f"components.{component}.slots.{slot}"
        if slot not in allowed:
            errors.append(f"{path}: not a slot of {component} {mode} ({', '.join(allowed)})"
                          f"{hint(slot, allowed)}")
            continue
        for item in items:
            if isinstance(item, list) and slot != "status":
                errors.append(f"{path}: a line of ids belongs to slots.status")
            for feature in _slot_ids(item):
                if feature not in expected:
                    errors.append(f"{path}: '{feature}' is not a {component} feature"
                                  f"{hint(str(feature), expected)}")
                elif feature in placed:
                    errors.append(f"{path}: '{feature}' is placed twice")
                placed.add(feature)
    for feature in expected:
        if feature not in placed:
            errors.append(f"components.{component}.slots: '{feature}' is missing")
    for feature in entry.get("templates", {}):
        if feature not in expected:
            errors.append(f"components.{component}.templates: '{feature}' is not a {component} "
                          f"feature{hint(str(feature), expected)}")


def rule_errors(spec: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    components: dict[str, Any] = spec.get("components", {})
    top_mode = _mode(components, "top")
    for component, mode in NEEDS_DCB_GRID.items():
        if _mode(components, component) == mode and top_mode != "dcb_grid":
            errors.append(f"components.{component}.mode: {mode} needs components.top.mode dcb_grid")
    window = spec.get("primitives", {}).get("window", {})
    if window.get("close") == "cell" and window.get("top_strip") != "bar":
        errors.append("primitives.window.close: cell needs top_strip bar")
    for component, entry in components.items():
        if isinstance(entry, dict) and "slots" in entry:
            _check_slots(component, components, errors)
    return errors


# --- resolution (InterfaceSpec) ------------------------------------------------------------

def merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    """Objects merge key by key, arrays and plain values replace; an object whose ``mode``
    changes drops the base's slots and templates."""
    result = copy.deepcopy(base)
    for key, mine in over.items():
        theirs = result.get(key)
        if isinstance(mine, dict) and isinstance(theirs, dict):
            if "mode" in mine and str(theirs.get("mode", "")) != str(mine["mode"]):
                theirs.pop("slots", None)
                theirs.pop("templates", None)
            result[key] = merge(theirs, mine)
        else:
            result[key] = copy.deepcopy(mine)
    return result


def base_path(base_id: str, root: Path) -> Path | None:
    """The panels.json of ``scope:<path>`` or ``skin:<id>`` in the repository, or None."""
    if ".." in base_id:
        return None
    if base_id.startswith(SCOPE_PREFIX):
        path = root / base_id.removeprefix(SCOPE_PREFIX) / "panels.json"
    elif base_id.startswith(SKIN_PREFIX):
        path = root / "SKINS" / base_id.removeprefix(SKIN_PREFIX) / "panels.json"
    else:
        return None
    return path if path.is_file() else None


def _base(raw: dict[str, Any], root: Path, chain: list[str], errors: list[str]) -> dict[str, Any]:
    base_id = str(raw.get("extends", GENERIC_ID))
    if base_id == GENERIC_ID:
        return generic()
    path = base_path(base_id, root)
    if path is None:
        errors.append(f"extends: '{base_id}' is not generic, scope:<path> or skin:<id> "
                      "in this repository")
        return generic()
    if base_id in chain or len(chain) >= MAX_DEPTH:
        errors.append(f"extends: '{base_id}' loops or is deeper than {MAX_DEPTH} skins")
        return generic()
    return _resolve(json.loads(path.read_text(encoding="utf-8")), root, chain + [base_id])


def _check(raw: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    own = raw.get("tokens", {})
    tokens = merge(base.get("tokens", {}), own if isinstance(own, dict) else {})
    checked = check(raw, tokens)
    checked["value"].pop("extends", None)
    return checked


def _resolve(raw: dict[str, Any], root: Path, chain: list[str]) -> dict[str, Any]:
    """A base as the game resolves it: invalid parts skipped, Generic when a rule breaks."""
    ignored: list[str] = []
    base = _base(raw, root, chain, ignored)
    spec = merge(base, _check(raw, base)["value"])
    if rule_errors(spec) or missing_capabilities(spec):
        return generic()
    return spec


def _capabilities(spec: dict[str, Any]) -> list[tuple[str, list[Any]]]:
    return check(spec, spec.get("tokens", {}))["capabilities"]


def missing_capabilities(spec: dict[str, Any]) -> list[str]:
    supported = load_contract()["capabilities"]
    missing = []
    for name, modes in _capabilities(spec):
        if name not in supported:
            value = name.rsplit(".", 1)[1]
            missing.append(f"{name}{hint(value, modes)}")
    return missing


def strict_errors(raw: dict[str, Any], root: Path = ROOT) -> list[str]:
    """Every error of ``raw`` over its base: schema paths with hints, broken rules and
    capabilities the game lacks. Empty when the skin is valid."""
    errors: list[str] = []
    base = _base(raw, root, [], errors)
    checked = _check(raw, base)
    spec = merge(base, checked["value"])
    errors.extend(checked["errors"])
    errors.extend(rule_errors(spec))
    for capability in missing_capabilities(spec):
        name, _, did_you_mean = capability.partition(" ")
        suffix = f" {did_you_mean}" if did_you_mean else ""
        errors.append(f"needs capability {name}, which this build lacks{suffix}")
    return errors


# --- files and the CLI ---------------------------------------------------------------------

def file_errors(path: Path, root: Path = ROOT) -> list[str]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"]
    except (OSError, UnicodeDecodeError) as exc:
        return [f"cannot read: {exc}"]
    if not isinstance(raw, dict) or not raw:
        return ["a panels.json is a non-empty JSON object"]
    return strict_errors(raw, root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate session skins (panels.json) with the "
                                                 "game's strict rules.")
    parser.add_argument("paths", nargs="+", type=Path, help="panels.json files")
    parser.add_argument("--root", type=Path, default=ROOT,
                        help="Repository root that scope:/skin: bases resolve in")
    args = parser.parse_args(argv)
    failed = 0
    for path in args.paths:
        errors = file_errors(path, args.root)
        if not errors:
            print(f"{path}: OK")
            continue
        failed += 1
        if errors[0].startswith("invalid JSON") or errors[0].startswith("cannot read"):
            print(f"{path}: {errors[0]}")
            continue
        print(f"{path}: {len(errors)} error(s)")
        for error in errors:
            print(f"  {error}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
