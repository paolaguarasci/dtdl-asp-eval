"""
Inter-judge reliability: second judge (anthropic/claude-opus-4-6) over a
stratified sample of 30 cases (15 grounded + 15 fair_ablation).

Purpose: verify agreement with the first judge (Claude Sonnet 4.6) and estimate
whether a systematic pro-Anthropic bias exists that would invalidate the
grounded vs ablation comparison.

Output: judge_secondary_results.json + printout of inter-judge agreement and Cohen's kappa.

Usage:
    export OPENROUTER_API_KEY=sk-...
    uv run judge_secondary.py
"""

# /// script
# requires-python = ">=3.11"
# dependencies = ["openai"]
# ///

import json
import os
import random
from collections import defaultdict
from openai import OpenAI

JUDGE2_MODEL = "anthropic/claude-opus-4-6"
BASE_URL = "https://openrouter.ai/api/v1"
API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

SAMPLE_PER_CONDITION = 15
RANDOM_SEED = 42

JUDGE_SYSTEM = (
    "You are a DTDL (Digital Twins Definition Language) v4 expert evaluating "
    "LLM-generated repair suggestions. You decide whether a suggestion "
    "appropriately addresses a specific DTDL error. "
    "Answer ONLY with YES or NO — no explanation."
)

JUDGE_USER_TEMPLATE = """\
DTDL error type: {etype}
Affected element: {entity}

LLM repair suggestion:
{response}

Does this suggestion provide an appropriate and actionable fix for the `{etype}` \
error affecting `{entity}`? Answer YES or NO."""

DATA = os.path.join(os.path.dirname(__file__), "..", "data")

# Macro-categories for stratification
MACRO = {
    "reference_errors": {
        "undefined_target",
        "extends_undefined",
        "component_schema_undefined",
    },
    "naming_errors": {
        "duplicate_property_name",
        "duplicate_telemetry_name",
        "duplicate_relationship_name",
        "duplicate_command_name",
        "ambiguous_name",
        "ambiguous_name_rel",
        "ambiguous_name_cmd",
        "inherited_name_conflict",
    },
    "schema_errors": {
        "property_schema_undefined",
        "enum_no_values",
        "object_no_fields",
        "command_request_schema_undefined",
        "command_response_schema_undefined",
    },
    "structural_errors": {
        "circular_extends",
        "deep_extends_chain",
        "self_referencing_relationship",
        "component_self_reference",
        "isolated_interface",
    },
    "semantic_errors": {"unit_without_semantic_type", "semantic_type_without_unit"},
}


def get_macro(etype):
    for macro, types in MACRO.items():
        if etype in types:
            return macro
    return "other"


def extract_entity(d: dict, condition: str) -> str:
    """Extract the entity description from the structured prompt."""
    if condition == "grounded":
        prompt = d.get("user_prompt", "")
        lines = prompt.strip().split("\n")
        parts = []
        for line in lines[1:]:
            if line.startswith("Problem:"):
                break
            if ":" in line:
                field, val = line.split(":", 1)
                parts.append(f"{field.strip()}: {val.strip()}")
        return "; ".join(parts) if parts else d.get("atom", "")
    else:
        prompt = d.get("fair_prompt", d.get("user_prompt", ""))
        # For fair ablation the prompt is natural language; extract it all
        return prompt.strip()[:300]


def stratified_sample(data, n, condition):
    """Stratified sample by macro-category, n total."""
    by_macro = defaultdict(list)
    for d in data:
        by_macro[get_macro(d["type"])].append(d)

    macros = list(by_macro.keys())
    rng = random.Random(RANDOM_SEED)

    # Proportional distribution with at least 1 per macro
    total = len(data)
    sample = []
    allocated = 0
    for i, macro in enumerate(macros):
        if i == len(macros) - 1:
            quota = n - allocated
        else:
            quota = max(1, round(n * len(by_macro[macro]) / total))
        quota = min(quota, len(by_macro[macro]))
        sample.extend(rng.sample(by_macro[macro], quota))
        allocated += quota
        if allocated >= n:
            break

    return sample[:n]


def judge_response(client, etype, entity, response):
    user_msg = JUDGE_USER_TEMPLATE.format(etype=etype, entity=entity, response=response)
    result = client.chat.completions.create(
        model=JUDGE2_MODEL,
        temperature=0,
        max_tokens=16,
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
    )
    answer = result.choices[0].message.content.strip().upper()
    return 1 if answer.startswith("YES") else 0


def cohen_kappa(a, b):
    """Cohen's kappa between two lists of binary values."""
    assert len(a) == len(b)
    n = len(a)
    agree = sum(1 for x, y in zip(a, b) if x == y)
    po = agree / n
    p1 = (sum(a) / n) * (sum(b) / n)
    p0 = ((n - sum(a)) / n) * ((n - sum(b)) / n)
    pe = p1 + p0
    if pe == 1.0:
        return 1.0
    return (po - pe) / (1 - pe)


def run():
    if not API_KEY:
        print("ERROR: set OPENROUTER_API_KEY environment variable.")
        return

    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

    # Load data
    with open(os.path.join(DATA, "responses", "grounded_responses.json"), encoding="utf-8") as f:
        grounded_data = json.load(f)
    with open(os.path.join(DATA, "responses", "responses_fair.json"), encoding="utf-8") as f:
        fair_data = json.load(f)
    with open(os.path.join(DATA, "results", "judge_primary_results.json"), encoding="utf-8") as f:
        judge1_all = json.load(f)

    # Index judge1 by (condition, id)
    judge1_idx = {(r["condition"], r["id"]): r["judge_correct"] for r in judge1_all}

    # Stratified sample
    grounded_sample = stratified_sample(grounded_data, SAMPLE_PER_CONDITION, "grounded")
    fair_sample = stratified_sample(fair_data, SAMPLE_PER_CONDITION, "fair_ablation")

    results = []

    print(f"=== Second judge: {JUDGE2_MODEL} ===")
    print(
        f"Sample: {len(grounded_sample)} grounded + {len(fair_sample)} fair_ablation\n"
    )

    for condition, sample, data_map in [
        ("grounded", grounded_sample, grounded_data),
        ("fair_ablation", fair_sample, fair_data),
    ]:
        print(f"--- {condition} ---")
        for i, d in enumerate(sample, 1):
            entity = extract_entity(d, condition)
            score2 = judge_response(client, d["type"], entity, d["response"])
            score1 = judge1_idx.get((condition, d["id"]), None)
            agree = (score1 == score2) if score1 is not None else None
            symbol = "✓" if score2 else "✗"
            match = "=" if agree else "≠" if agree is not None else "?"
            print(
                f"  [{i:02d}] {d['type'][:35]:35s}  j1={score1}  j2={score2}  {match}  {symbol}"
            )
            results.append(
                {
                    "condition": condition,
                    "id": d["id"],
                    "type": d["type"],
                    "macro": get_macro(d["type"]),
                    "judge1": score1,
                    "judge2": score2,
                    "agree": agree,
                }
            )
        print()

    # Save
    out_path = os.path.join(DATA, "results", "judge_secondary_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"Saved: {out_path}\n")

    # Agreement statistics
    all_j1 = [r["judge1"] for r in results if r["judge1"] is not None]
    all_j2 = [r["judge2"] for r in results if r["judge1"] is not None]
    paired = [(r["judge1"], r["judge2"]) for r in results if r["judge1"] is not None]

    n = len(paired)
    agree = sum(1 for a, b in paired if a == b)
    kappa = cohen_kappa(all_j1, all_j2)

    print("=== INTER-JUDGE AGREEMENT ===")
    print(f"  Sample N:         {n}")
    print(f"  Agreement:        {agree}/{n} ({100*agree//n}%)")
    print(f"  Cohen's κ:        {kappa:.2f}")
    print()

    # Per condition
    for cond in ["grounded", "fair_ablation"]:
        rows = [
            r for r in results if r["condition"] == cond and r["judge1"] is not None
        ]
        j1 = [r["judge1"] for r in rows]
        j2 = [r["judge2"] for r in rows]
        ag = sum(1 for a, b in zip(j1, j2) if a == b)
        k = cohen_kappa(j1, j2)
        j2_correct = sum(j2)
        print(
            f"  [{cond}]  agreement {ag}/{len(rows)} ({100*ag//len(rows)}%)  κ={k:.2f}  "
            f"judge2_correct={j2_correct}/{len(rows)} ({100*j2_correct//len(rows)}%)"
        )

    print()
    # Bias check: does judge2 favor grounding?
    j2_grounded = sum(r["judge2"] for r in results if r["condition"] == "grounded")
    j2_fair = sum(r["judge2"] for r in results if r["condition"] == "fair_ablation")
    n_g = sum(1 for r in results if r["condition"] == "grounded")
    n_f = sum(1 for r in results if r["condition"] == "fair_ablation")
    print(f"  judge2 grounded:      {j2_grounded}/{n_g} ({100*j2_grounded//n_g}%)")
    print(f"  judge2 fair_ablation: {j2_fair}/{n_f} ({100*j2_fair//n_f}%)")
    print(
        f"  judge2 gap: {100*j2_grounded//n_g - 100*j2_fair//n_f} pp "
        f"(vs expected judge1 gap: ~35 pp)"
    )


if __name__ == "__main__":
    run()
