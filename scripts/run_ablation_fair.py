"""
Fair ablation baseline: LLM receives entity name + error type in natural language,
WITHOUT the structured ASP diagnostic format and remediation hint.

This isolates the contribution of symbolic grounding (the structured @DTDL/Debug
output) from the LLM's general DTDL knowledge.

Contrast with run_grounded.py (full structured diagnostic with remediation hint):
this is the fair-ablation condition reported in the paper (Table 6).

Usage:
    export OPENROUTER_API_KEY=sk-...
    uv run --with openai run_ablation_fair.py

Output: responses_fair.json
"""

# /// script
# requires-python = ">=3.11"
# dependencies = ["openai"]
# ///

import os
import json
from openai import OpenAI

API_KEY  = os.environ.get("OPENROUTER_API_KEY", "")
MODEL    = "deepseek/deepseek-v3.2"
BASE_URL = "https://openrouter.ai/api/v1"

# Shared expert system message (identical for both grounded and fair-ablation conditions)
SYSTEM = (
    "You are an expert in DTDL (Digital Twins Definition Language) v4. "
    "You receive structured diagnostic information from a symbolic ASP-based validator. "
    "Explain the root cause of the error and suggest a concrete, actionable fix "
    "including the corrected DTDL JSON-LD snippet. "
    "Do not invent properties or fields not defined in the DTDL v4 specification. "
    "Be concise: max 200 words."
)


def build_fair_prompt(d: dict) -> str:
    """
    Build a natural-language user prompt from grounded diagnostic data.
    Includes: error type name + affected entity name(s).
    Excludes: structured field labels, 'Problem:' description, remediation hint.
    """
    lines = d["user_prompt"].strip().split("\n")
    # lines[0] = 'Diagnostic: [type]' — skip
    entity_parts = []
    for line in lines[1:]:
        if line.startswith("Problem:"):
            break
        if ":" in line:
            field, val = line.split(":", 1)
            entity_parts.append(f"{field.strip()} `{val.strip()}`")

    entity_str = "; ".join(entity_parts) if entity_parts else "(unknown)"
    return (
        f"The DTDL model has a `{d['type']}` error. "
        f"The affected element is: {entity_str}. "
        f"Explain the issue and suggest one or more concrete DTDL fixes. Max 200 words."
    )


def run():
    if not API_KEY:
        print("ERROR: set OPENROUTER_API_KEY environment variable.")
        return

    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

    src = os.path.join(os.path.dirname(__file__), "..", "data", "responses", "grounded_responses.json")
    with open(src, encoding="utf-8") as f:
        diagnostics = json.load(f)

    results = []
    for d in diagnostics:
        user_msg = build_fair_prompt(d)
        print(f"[{d['id']:03d}/{len(diagnostics)}] {d['type']}")
        print(f"       prompt: {user_msg[:100]}...")

        response = client.chat.completions.create(
            model=MODEL,
            temperature=0,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user",   "content": user_msg},
            ],
        )
        text = response.choices[0].message.content.strip()
        results.append({
            "id":          d["id"],
            "source":      d.get("source", ""),
            "type":        d["type"],
            "atom":        d["atom"],
            "fair_prompt": user_msg,
            "response":    text,
        })
        print(f"       -> {len(text)} chars\n")

    out = os.path.join(os.path.dirname(__file__), "..", "data", "responses", "responses_fair.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(results)} responses to {out}")


if __name__ == "__main__":
    run()
