"""
Inter-judge reliability with independent non-Anthropic judges.

Uses the same 30 cases from judge_secondary_results.json (15 grounded + 15 fair_ablation)
and submits them to two new judges: gpt-5.4 (OpenAI) and gemini-3-flash-preview (Google),
both accessible via OpenRouter.

Output: judge_interrater_results.json + per-condition kappa table printed to console.

Usage:
    export OPENROUTER_API_KEY=sk-...
    uv run --with openai judge_interrater.py
"""

# /// script
# requires-python = ">=3.11"
# dependencies = ["openai"]
# ///

import json
import os
from openai import OpenAI

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
BASE_URL = "https://openrouter.ai/api/v1"

JUDGES = {
    "gpt-5.4": "openai/gpt-5.4",
    "gemini-3-flash-preview": "google/gemini-3-flash-preview",
}

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


def extract_entity_grounded(d: dict) -> str:
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


def extract_entity_fair(d: dict) -> str:
    prompt = d.get("fair_prompt", d.get("user_prompt", ""))
    return prompt.strip()[:300]


def judge_one(client, model_id, etype, entity, response) -> int:
    user_msg = JUDGE_USER_TEMPLATE.format(etype=etype, entity=entity, response=response)
    result = client.chat.completions.create(
        model=model_id,
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
    n = len(a)
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    p1 = (sum(a) / n) * (sum(b) / n)
    p0 = ((n - sum(a)) / n) * ((n - sum(b)) / n)
    pe = p1 + p0
    if pe == 1.0:
        return 1.0
    return (po - pe) / (1 - pe)


def run():
    if not API_KEY:
        raise SystemExit("ERROR: set OPENROUTER_API_KEY")

    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

    # Load the 30-case sample already used in judge2
    with open(os.path.join(DATA, "results", "judge_secondary_results.json"), encoding="utf-8") as f:
        sample_meta = json.load(f)  # contains condition, id, type, judge1

    # Load the original responses
    with open(os.path.join(DATA, "responses", "grounded_responses.json"), encoding="utf-8") as f:
        grounded_all = {d["id"]: d for d in json.load(f)}
    with open(os.path.join(DATA, "responses", "responses_fair.json"), encoding="utf-8") as f:
        fair_all = {d["id"]: d for d in json.load(f)}

    results = []

    for judge_name, model_id in JUDGES.items():
        print(f"\n=== Judge: {judge_name} ({model_id}) ===")
        for i, meta in enumerate(sample_meta, 1):
            cond = meta["condition"]
            rid = meta["id"]
            etype = meta["type"]

            if cond == "grounded":
                d = grounded_all[rid]
                entity = extract_entity_grounded(d)
            else:
                d = fair_all[rid]
                entity = extract_entity_fair(d)

            score = judge_one(client, model_id, etype, entity, d["response"])
            j1 = meta["judge1"]
            symbol = "✓" if score else "✗"
            match = "=" if score == j1 else "≠"
            print(
                f"  [{i:02d}] [{cond[:8]}] {etype[:35]:35s}  j1={j1}  {judge_name}={score}  {match} {symbol}"
            )

            results.append(
                {
                    "condition": cond,
                    "id": rid,
                    "type": etype,
                    "macro": meta["macro"],
                    "judge1": j1,
                    "judge2_opus": meta.get(
                        "judge2"
                    ),  # claude-opus-4-6 from judge2_results
                    judge_name: score,
                }
            )

    # Merge by ID: one record per case with all scores
    merged = {}
    for r in results:
        key = (r["condition"], r["id"])
        if key not in merged:
            merged[key] = {k: v for k, v in r.items()}
        else:
            merged[key].update({k: v for k, v in r.items() if k not in merged[key]})

    out = list(merged.values())
    out_path = os.path.join(DATA, "results", "judge_interrater_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"\nSaved: {out_path}")

    # --- Kappa table ---
    print("\n=== KAPPA TABLE (per condition) ===")
    judge_names = list(JUDGES.keys())
    all_judges = ["judge2_opus"] + judge_names

    header = f"{'Judge pair':40s}  {'Grounded (n=15)':>17}  {'Fair-abl. (n=15)':>17}  {'Overall (n=30)':>15}"
    print(header)
    print("-" * len(header))

    pairs = [("judge1", j) for j in all_judges] + [(judge_names[0], judge_names[1])]
    for ja, jb in pairs:
        row_parts = []
        for cond in ["grounded", "fair_ablation", None]:
            rows = [
                r
                for r in out
                if (cond is None or r["condition"] == cond)
                and r.get(ja) is not None
                and r.get(jb) is not None
            ]
            if not rows:
                row_parts.append("  n/a")
                continue
            a = [r[ja] for r in rows]
            b = [r[jb] for r in rows]
            k = cohen_kappa(a, b)
            ag = sum(1 for x, y in zip(a, b) if x == y)
            row_parts.append(f"κ={k:.2f} ({ag}/{len(rows)})")
        label = f"claude-sonnet-4-6 vs {jb}" if ja == "judge1" else f"{ja} vs {jb}"
        print(
            f"  {label:38s}  {row_parts[0]:>17}  {row_parts[1]:>17}  {row_parts[2]:>15}"
        )

    print()
    # Bias check
    print("=== BIAS CHECK (judge_correct per condition) ===")
    for jname in all_judges:
        g = [
            r[jname]
            for r in out
            if r["condition"] == "grounded" and r.get(jname) is not None
        ]
        fa = [
            r[jname]
            for r in out
            if r["condition"] == "fair_ablation" and r.get(jname) is not None
        ]
        if g and fa:
            print(
                f"  {jname:20s}  grounded={sum(g)}/{len(g)} ({100*sum(g)//len(g)}%)  "
                f"fair={sum(fa)}/{len(fa)} ({100*sum(fa)//len(fa)}%)  "
                f"gap={100*sum(g)//len(g)-100*sum(fa)//len(fa)} pp"
            )


if __name__ == "__main__":
    run()
