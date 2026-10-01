#!/usr/bin/env python3
"""Render the skin key reference (every key: type, default, allowed values) from the schema.

    python tools/skin_reference.py            # rewrite documentation/skins-reference.md
    python tools/skin_reference.py --check    # fail when the page is out of date
    python tools/skin_reference.py --stdout   # print it (the game repo's reference page)

The schema is ``tools/interface_contract/interface.schema.json`` (vendored from the game), so
the page always describes the rules ``tools/validate_skin.py`` applies.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = Path(__file__).resolve().parent / "interface_contract" / "interface.schema.json"
CONTRACT = Path(__file__).resolve().parent / "interface_contract" / "contract.json"
GENERIC = Path(__file__).resolve().parent / "interface_contract" / "generic.panels.json"
PAGE = ROOT / "documentation" / "skins-reference.md"
# $defs drawn as their own tables (referenced by name elsewhere) instead of inlined.
SHARED = ("box", "state", "states", "slot_entry")
SECTIONS = (
    ("Metadata and extends", None),
    ("Tokens", "tokens"),
    ("Primitives", "primitives"),
    ("Components", "components"),
)


def _schema() -> dict[str, Any]:
    return json.loads(SCHEMA.read_text(encoding="utf-8"))


def _name(ref: str) -> str:
    return ref.removeprefix("#/$defs/")


def _resolve(node: dict[str, Any], defs: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """The rule behind ``node`` (``$ref`` followed unless it is a shared def) and that def's name."""
    shared = ""
    rule = dict(node)
    own_description = rule.get("description")
    while "$ref" in rule:
        name = _name(rule.pop("$ref"))
        if name in SHARED:
            shared = name
            rule = {**{"type": "object"}, **rule}
            break
        rule = {**defs[name], **rule}
    if own_description is None and not shared and rule.get("type") != "object":
        rule.pop("description", None)
    return rule, shared


def _code(value: Any) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    text = text.replace("\n", "\\n").replace("|", "\\|")
    return f"`{text}`" if text != "" else '`""`'


def _type(rule: dict[str, Any], shared: str) -> str:
    if shared:
        return f"[{shared}](#{shared})"
    kinds = rule.get("type", "")
    text = " or ".join(kinds) if isinstance(kinds, list) else str(kinds)
    if rule.get("x-ref"):
        return {"colors": "colour role", "fonts": "font role", "type": "type role"}[rule["x-ref"]]
    if rule.get("x-px"):
        return "px"
    return text or "any"


def _allowed(rule: dict[str, Any]) -> str:
    parts = []
    if "enum" in rule:
        parts.append(", ".join(_code(option) for option in rule["enum"]))
    if "minimum" in rule or "maximum" in rule:
        parts.append(f"{rule.get('minimum', '')}–{rule.get('maximum', '')}")
    if "maxLength" in rule:
        parts.append(f"≤ {rule['maxLength']} characters")
    if "pattern" in rule:
        parts.append("`RRGGBB` or `RRGGBBAA`" if "0-9A-Fa-f" in rule["pattern"] else _code(rule["pattern"]))
    if "minItems" in rule and rule.get("type") == "array":
        parts.append(f"{rule['minItems']}–{rule.get('maxItems', '')} items")
    if rule.get("x-ref"):
        parts.append(f"a name in `tokens.{rule['x-ref']}`")
    if rule.get("x-capability"):
        parts.append(f"capability `interface.{rule['x-capability']}.<value>`")
    return "; ".join(parts)


def _describe(rule: dict[str, Any]) -> str:
    return str(rule.get("description", "")).replace("|", "\\|").replace("\n", " ")


def _generic_value(path: str) -> Any:
    value: Any = json.loads(GENERIC.read_text(encoding="utf-8"))
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _rows(node: dict[str, Any], path: str, defs: dict[str, Any], rows: list[str],
          top: str = "") -> None:
    rule, shared = _resolve(node, defs)
    if path and path != top:
        generic = _generic_value(path)
        if generic is not None and not isinstance(generic, dict) and len(json.dumps(generic)) <= 40:
            default = _code(generic)
        else:
            default = _code(rule["default"]) if "default" in rule else ""
        rows.append(f"| `{path}` | {_type(rule, shared)} | {default} | {_allowed(rule)} | {_describe(rule)} |")
    if shared:
        return
    for key, child in rule.get("properties", {}).items():
        if key == "$schema" and not path:
            continue
        _rows(child, f"{path}.{key}" if path else key, defs, rows, top)
    extra = rule.get("additionalProperties")
    if isinstance(extra, dict):
        _rows(extra, f"{path}.<name>" if path else "<name>", defs, rows, top)
    items = rule.get("items")
    if isinstance(items, dict) and rule.get("type") == "array":
        items_rule, items_shared = _resolve(items, defs)
        if items_shared or items_rule.get("type") == "object":
            _rows(items, f"{path}[]", defs, rows, top)


HEADER = "| Key | Type | Default | Allowed | What it does |\n|---|---|---|---|---|"


def _table(node: dict[str, Any], path: str, defs: dict[str, Any]) -> str:
    rows: list[str] = []
    _rows(node, path, defs, rows, path)
    return HEADER + "\n" + "\n".join(rows)


def render() -> str:
    schema = _schema()
    defs = schema["$defs"]
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    out = [
        "# Skin key reference",
        "",
        "<!-- Generated by tools/skin_reference.py from tools/interface_contract/interface.schema.json "
        f"(game commit {contract['game_commit'][:9]}). Do not edit by hand. -->",
        "",
        "Every key a `panels.json` accepts: its type, its Generic default, the values it allows and what it does.",
        "Every key is optional; a skin writes only what differs from the skin it `extends`. **px** is a whole number",
        "of design pixels at interface size 1.0 (the game scales it). A **role** is a name defined in `tokens`",
        "(Generic's or the skin's own). **Default** is Generic's value (`resources/session_skins/generic/panels.json`).",
        "How to build a skin: [skins modding guide](skins-modding.md).",
        "",
    ]
    root_rows: list[str] = []
    for key in ("name", "author", "description", "extends"):
        _rows(schema["properties"][key], key, defs, root_rows)
    out += ["## Metadata and extends", "", HEADER, *root_rows, ""]
    out += ["## Tokens", "", _table(defs["tokens"], "tokens", defs), ""]
    out += ["## Primitives", "",
            "Each primitive has `states` (see [states](#states)); a state's look is a [state](#state), "
            "its background a [box](#box).", ""]
    for name, node in defs["primitives"]["properties"].items():
        out += [f"### {name}", "", _describe(node), "", _table(node, f"primitives.{name}", defs), ""]
    out += ["## Components", "",
            "Each part of the screen picks a `mode` (renderer code). A mode other than Generic's is a "
            "capability the game must support. Slots take [slot entries](#slot_entry).", ""]
    for name, node in defs["components"]["properties"].items():
        features = contract["features"].get(name)
        line = f"Features: {', '.join(f'`{f}`' for f in features)}." if features else ""
        out += [f"### {name}", "", line, "", _table(node, f"components.{name}", defs), ""]
    out += ["## Shared shapes", ""]
    for name in SHARED:
        node = defs[name]
        out += [f"### {name}", "", _describe(node), "", HEADER]
        rows: list[str] = []
        for key, child in node.get("properties", {}).items():
            _rows(child, key, defs, rows)
        out += [*rows, ""]
    out += ["## Capabilities the game supports", "",
            ", ".join(f"`{name}`" for name in contract["capabilities"]), ""]
    return "\n".join(line.rstrip() for line in out).replace("\n\n\n", "\n\n").rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="Fail when the page is out of date")
    parser.add_argument("--stdout", action="store_true", help="Print instead of writing")
    args = parser.parse_args(argv)
    text = render()
    if args.stdout:
        sys.stdout.buffer.write(text.encode("utf-8"))
        return 0
    if args.check:
        current = PAGE.read_text(encoding="utf-8") if PAGE.exists() else ""
        if current != text:
            print(f"{PAGE.relative_to(ROOT)} is out of date: run python tools/skin_reference.py",
                  file=sys.stderr)
            return 1
        return 0
    PAGE.write_text(text, encoding="utf-8", newline="\n")
    print(f"Wrote {PAGE.relative_to(ROOT)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
