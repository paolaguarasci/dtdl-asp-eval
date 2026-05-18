"""
LLM-as-judge evaluation for DTDL repair suggestions.

Uses anthropic/claude-sonnet-4-6 (a different model family from deepseek/deepseek-v3.2)
as an independent judge to assess whether each repair suggestion is appropriate.
Replaces the author-defined keyword rubric used for action_correct in evaluate.py.

The judge receives: error type, affected entity info, and the LLM response.
It answers YES (1) or NO (0) — fully binary, no ordinal scale.

Usage:
    export OPENROUTER_API_KEY=sk-...
    uv run --with openai judge_primary.py

Output: judge_primary_results.json
"""

# /// script
# requires-python = ">=3.11"
# dependencies = ["openai"]
# ///

import os
import json
import re
from openai import OpenAI

API_KEY   = os.environ.get("OPENROUTER_API_KEY", "")
JUDGE_MODEL = "anthropic/claude-sonnet-4-6"
BASE_URL  = "https://openrouter.ai/api/v1"

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


def extract_entity(d: dict, source_key: str = "user_prompt") -> str:
    """Extract entity description from user_prompt structured fields."""
    prompt = d.get(source_key) or d.get("fair_prompt") or ""
    lines = prompt.strip().split("\n")
    parts = []
    for line in lines[1:]:
        if line.startswith("Problem:"):
            break
        if ":" in line:
            field, val = line.split(":", 1)
            parts.append(f"{field.strip()}: {val.strip()}")
    return "; ".join(parts) if parts else d.get("atom", "")


def judge_response(client: OpenAI, etype: str, entity: str, response: str) -> int:
    """Returns 1 if the judge says YES, 0 if NO."""
    user_msg = JUDGE_USER_TEMPLATE.format(
        etype=etype, entity=entity, response=response
    )
    result = client.chat.completions.create(
        model=JUDGE_MODEL,
        temperature=0,
        max_tokens=16,
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user",   "content": user_msg},
        ],
    )
    answer = result.choices[0].message.content.strip().upper()
    return 1 if answer.startswith("YES") else 0


def process_file(client, path: str, condition: str, entity_key: str = "user_prompt"):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    results = []
    for i, d in enumerate(data, 1):
        entity = extract_entity(d, entity_key)
        score = judge_response(client, d["type"], entity, d["response"])
        results.append({
            "condition": condition,
            "id":        d["id"],
            "type":      d["type"],
            "judge_correct": score,
        })
        symbol = "✓" if score else "✗"
        print(f"[{condition}] [{i:03d}/{len(data)}] {d['type'][:35]:35s} {symbol}")

    return results


def run():
    if not API_KEY:
        print("ERROR: set OPENROUTER_API_KEY environment variable.")
        return

    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    data = os.path.join(os.path.dirname(__file__), "..", "data")

    all_results = []

    print("=== Judging GROUNDED responses ===")
    all_results += process_file(
        client,
        os.path.join(data, "responses", "grounded_responses.json"),
        "grounded",
        "user_prompt",
    )

    print("\n=== Judging FAIR ABLATION responses ===")
    all_results += process_file(
        client,
        os.path.join(data, "responses", "responses_fair.json"),
        "fair_ablation",
        "fair_prompt",
    )

    out = os.path.join(data, "results", "judge_primary_results.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    print(f"\nSaved {len(all_results)} judge scores to {out}")

    # Summary
    print("\n=== SUMMARY ===")
    for cond in ["grounded", "fair_ablation"]:
        rows = [r for r in all_results if r["condition"] == cond]
        if not rows:
            continue
        correct = sum(r["judge_correct"] for r in rows)
        print(f"{cond:20s}: {correct}/{len(rows)} ({100*correct//len(rows)}%)")


if __name__ == "__main__":
    run()
