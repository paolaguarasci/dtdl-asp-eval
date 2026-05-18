#!/usr/bin/env python3
"""
Compute three objective binary metrics for each LLM response:
  json_valid      1 if the response contains at least one parseable JSON fragment
  entity_recall   1 if the response mentions the specific entity of the diagnostic
  action_correct  1 if entity_recall==1 AND the response suggests the correct action

Overwrites ratings in grounded_responses.json and responses_fair.json.

Usage:
    uv run evaluate.py
"""

# /// script
# requires-python = ">=3.11"
# ///

import json
import re
import os

DATA          = os.path.join(os.path.dirname(__file__), "..", "data")
GROUNDED_PATH = os.path.join(DATA, "responses", "grounded_responses.json")
ABLATION_PATH = os.path.join(DATA, "responses", "responses_fair.json")


# ---------------------------------------------------------------------------
# Action rubric by type (prefix match, case-insensitive)
# ---------------------------------------------------------------------------
ACTION_KEYWORDS = {
    "undefined_target":                  ["add", "define", "creat"],
    "extends_undefined":                 ["add", "define", "creat"],
    "missing_required_property":         ["add", "defin"],
    "component_schema_undefined":        ["add", "define", "creat"],
    "property_schema_undefined":         ["replac", "add", "primitive", "valid"],
    "command_request_schema_undefined":  ["add", "schema", "replac", "primitive"],
    "command_response_schema_undefined": ["add", "schema", "replac", "primitive"],
    "enum_no_values":                    ["add", "enumValue", "enumvalue", "value"],
    "object_no_fields":                  ["add", "field"],
    "duplicate_property_name":           ["renam", "remov", "uniqu"],
    "duplicate_telemetry_name":          ["renam", "remov", "uniqu"],
    "duplicate_relationship_name":       ["renam", "remov", "uniqu"],
    "duplicate_command_name":            ["renam", "remov", "uniqu"],
    "ambiguous_name":                    ["renam", "uniqu"],
    "ambiguous_name_rel":                ["renam", "uniqu"],
    "ambiguous_name_cmd":                ["renam", "uniqu"],
    "inherited_name_conflict":           ["renam", "remov"],
    "circular_extends":                  ["remov", "cycl", "circular", "break"],
    "self_referencing_relationship":     ["different", "target", "chang"],
    "component_self_reference":          ["different", "schema", "chang"],
    "deep_extends_chain":                ["flatten", "hierarch", "remov", "merg"],
    "isolated_interface":                ["reference", "component", "extend", "add"],
    "unit_without_semantic_type":        ["semantic", "type", "add"],
    "semantic_type_without_unit":        ["unit", "add"],
}

# Types where the key entity is arg2 of the atom (not arg1)
ARG2_TYPES = {
    "undefined_target", "missing_required_property", "extends_undefined",
    "duplicate_property_name", "duplicate_telemetry_name",
    "duplicate_relationship_name", "duplicate_command_name",
    "ambiguous_name", "ambiguous_name_rel", "ambiguous_name_cmd",
    "inherited_name_conflict", "self_referencing_relationship",
    "component_schema_undefined", "component_self_reference",
    "property_schema_undefined", "enum_no_values", "object_no_fields",
    "command_request_schema_undefined", "command_response_schema_undefined",
    "unit_without_semantic_type", "semantic_type_without_unit",
}

# Types where the key entity is arg1 (interface ID)
ARG1_TYPES = {"circular_extends", "deep_extends_chain", "isolated_interface"}


# ---------------------------------------------------------------------------
# Entity extraction
# ---------------------------------------------------------------------------

def extract_entity_from_prompt(user_prompt, dtype):
    """Extract the key entity from the structured user_prompt (grounded)."""
    field_map = {
        "undefined_target":                  "Referenced target interface",
        "missing_required_property":         "Missing property name",
        "extends_undefined":                 "Missing parent interface",
        "duplicate_property_name":           "Duplicate name",
        "duplicate_telemetry_name":          "Duplicate name",
        "duplicate_relationship_name":       "Duplicate name",
        "duplicate_command_name":            "Duplicate name",
        "ambiguous_name":                    "Ambiguous name",
        "ambiguous_name_rel":                "Ambiguous name",
        "ambiguous_name_cmd":                "Ambiguous name",
        "inherited_name_conflict":           "Conflicting name",
        "self_referencing_relationship":     "Relationship name",
        "component_schema_undefined":        "Component name",
        "component_self_reference":          "Component name",
        "property_schema_undefined":         "Property name",
        "enum_no_values":                    "Element name",
        "object_no_fields":                  "Element name",
        "command_request_schema_undefined":  "Command name",
        "command_response_schema_undefined": "Command name",
        "circular_extends":                  "Interface ID",
        "deep_extends_chain":                "Interface ID",
        "isolated_interface":                "Interface ID",
    }
    field = field_map.get(dtype)
    if not field:
        return None
    m = re.search(rf"{re.escape(field)}:\s*(.+)", user_prompt)
    return m.group(1).strip() if m else None


def extract_entity_from_atom(atom, dtype):
    """Extract the key entity from the ASP atom (ablation, no user_prompt)."""
    if dtype in ARG1_TYPES:
        # arg1 is always a plain string for these types
        m = re.search(r'__debug__\("[^"]+",\s*"([^"]+)"', atom)
        return m.group(1) if m else None

    if dtype in ARG2_TYPES:
        # arg1 may be a string or a compound tuple
        # try the tuple form first: __debug__("type", ("x","y",n), "arg2")
        m = re.search(r'__debug__\("[^"]+",\s*\([^)]+\),\s*"([^"]+)"', atom)
        if m:
            return m.group(1)
        # then the plain string form: __debug__("type", "arg1", "arg2")
        m = re.search(r'__debug__\("[^"]+",\s*"[^"]+",\s*"([^"]+)"', atom)
        return m.group(1) if m else None

    return None


# ---------------------------------------------------------------------------
# Metric 1: json_valid
# ---------------------------------------------------------------------------

def _clean_json(text):
    """Remove JS comments and trailing commas to attempt the parse."""
    lines = [l for l in text.split("\n") if not re.match(r"\s*//", l)]
    cleaned = re.sub(r",(\s*[}\]])", r"\1", "\n".join(lines))
    return cleaned


def metric_json_valid(response):
    """1 if at least one ```json``` block is parseable after cleanup."""
    blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)```", response)
    for b in blocks:
        for candidate in [b, _clean_json(b)]:
            try:
                json.loads(candidate)
                return 1
            except Exception:
                pass
    return 0


# ---------------------------------------------------------------------------
# Metric 2: entity_recall
# ---------------------------------------------------------------------------

def metric_entity_recall(response, entity):
    """1 if the entity (exact string) appears in the response text."""
    if not entity:
        return 0
    return 1 if entity.lower() in response.lower() else 0


# ---------------------------------------------------------------------------
# Metric 3: action_correct
# ---------------------------------------------------------------------------

def metric_action_correct(response, dtype, entity_recall):
    """1 if entity_recall==1 AND at least one action keyword matches."""
    if not entity_recall:
        return 0
    keywords = ACTION_KEYWORDS.get(dtype, [])
    text = response.lower()
    for kw in keywords:
        if kw.lower() in text:
            return 1
    return 0


# ---------------------------------------------------------------------------
# Full computation for one entry
# ---------------------------------------------------------------------------

def evaluate_entry(entry, use_prompt=True):
    """Compute the 3 metrics for an entry and update entry['ratings']."""
    dtype    = entry["type"]
    response = entry["response"]

    if use_prompt and "user_prompt" in entry:
        entity = extract_entity_from_prompt(entry["user_prompt"], dtype)
    else:
        entity = extract_entity_from_atom(entry.get("atom", ""), dtype)

    jv = metric_json_valid(response)
    er = metric_entity_recall(response, entity)
    ac = metric_action_correct(response, dtype, er)

    entry["ratings"] = {
        "json_valid":      jv,
        "entity_recall":   er,
        "action_correct":  ac,
    }
    return entry


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    with open(GROUNDED_PATH, encoding="utf-8") as f:
        grounded = json.load(f)
    for entry in grounded:
        evaluate_entry(entry, use_prompt=True)
    with open(GROUNDED_PATH, "w", encoding="utf-8") as f:
        json.dump(grounded, f, indent=2, ensure_ascii=False)
    print(f"Grounded: {len(grounded)} entries -> {GROUNDED_PATH}")

    with open(ABLATION_PATH, encoding="utf-8") as f:
        ablation = json.load(f)
    for entry in ablation:
        evaluate_entry(entry, use_prompt=False)
    with open(ABLATION_PATH, "w", encoding="utf-8") as f:
        json.dump(ablation, f, indent=2, ensure_ascii=False)
    print(f"Fair ablation: {len(ablation)} entries -> {ABLATION_PATH}")

    # Summary
    for label, data in [("Grounded", grounded), ("Fair ablation", ablation)]:
        print(f"\n--- {label} ---")
        for k in ["json_valid", "entity_recall", "action_correct"]:
            total = len(data)
            correct = sum(d["ratings"][k] for d in data)
            print(f"  {k}: {correct}/{total} ({100*correct//total}%)")


if __name__ == "__main__":
    main()
