"""
Reads grounded_responses.json and responses_fair.json (fair ablation) with
binary metrics and prints accuracy tables (correct/total).

Usage:
    uv run score.py
"""

import json
import os
from collections import defaultdict

METRICS = ["json_valid", "entity_recall", "action_correct"]
HEADERS = ["json_valid", "entity_recall", "action_correct"]

BASE = os.path.join(os.path.dirname(__file__), "..", "data", "responses")


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def acc(items, metric):
    total   = len(items)
    correct = sum(d["ratings"].get(metric, 0) for d in items)
    return correct, total


def fmt(correct, total):
    pct = int(100 * correct / total) if total else 0
    return f"{correct}/{total} ({pct}%)"


def check_complete(items, label):
    missing = [x["id"] for x in items if any(x["ratings"].get(m) is None for m in METRICS)]
    if missing:
        print(f"WARNING [{label}]: ratings missing for ids {missing}")
    return not missing


def print_type_table(grounded, ablation):
    all_types = sorted(
        set(d["type"] for d in grounded) | set(d["type"] for d in ablation)
    )
    col_w = 34
    print("\n=== ACCURACY: GROUNDED vs FAIR ABLATION — by type ===\n")
    print(f"{'Diagnostic type':{col_w}} {'Cond':10} {'n':>4}  " +
          "  ".join(f"{h:^18}" for h in HEADERS))
    print("-" * (col_w + 10 + 6 + 18 * len(METRICS) + 4))

    for dtype in all_types:
        g = [x for x in grounded if x["type"] == dtype]
        a = [x for x in ablation  if x["type"] == dtype]
        for cond_label, items in [("Grounded", g), ("Fair ablation", a)]:
            if not items:
                continue
            row  = [acc(items, m) for m in METRICS]
            label = dtype if cond_label == "Grounded" else ""
            print(f"{label:{col_w}} {cond_label:10} {len(items):>4}  " +
                  "  ".join(f"{fmt(c,t):^18}" for c, t in row))
        print()

    # Totals
    for cond_label, items in [("Grounded", grounded), ("Fair ablation", ablation)]:
        row   = [acc(items, m) for m in METRICS]
        label = f"TOTAL (n={len(items)})" if cond_label == "Grounded" else ""
        print(f"{label:{col_w}} {cond_label:10} {len(items):>4}  " +
              "  ".join(f"{fmt(c,t):^18}" for c, t in row))


def print_domain_table(grounded, ablation):
    domains = {
        "vineyard_original":          "Agriculture (vineyard)",
        "all_errors.json":            "Generic (multi-error)",
        "industrialiot_errors.json":  "Industrial IoT",
        "smartbuilding_errors.json":  "Smart Building",
    }

    def domain_of(d):
        src = d["source"]
        if src == "vineyard_original" or src.startswith("vineyard_"):
            return "Agriculture (vineyard variants)"
        return domains.get(src, src)

    all_domains = sorted(set(domain_of(d) for d in grounded + ablation))
    col_w = 34
    print("\n=== ACCURACY: GROUNDED vs FAIR ABLATION — by domain ===\n")
    print(f"{'Domain':{col_w}} {'Cond':10} {'n':>4}  " +
          "  ".join(f"{h:^18}" for h in HEADERS))
    print("-" * (col_w + 10 + 6 + 18 * len(METRICS) + 4))

    for dom in all_domains:
        g = [d for d in grounded if domain_of(d) == dom]
        a = [d for d in ablation  if domain_of(d) == dom]
        for cond_label, items in [("Grounded", g), ("Fair ablation", a)]:
            if not items:
                continue
            row   = [acc(items, m) for m in METRICS]
            label = dom if cond_label == "Grounded" else ""
            print(f"{label:{col_w}} {cond_label:10} {len(items):>4}  " +
                  "  ".join(f"{fmt(c,t):^18}" for c, t in row))
        print()


def main():
    g_path = os.path.join(BASE, "grounded_responses.json")
    a_path = os.path.join(BASE, "responses_fair.json")

    if not os.path.exists(g_path):
        print(f"ERROR: {g_path} not found.")
        return
    if not os.path.exists(a_path):
        print(f"ERROR: {a_path} not found.")
        return

    grounded = load(g_path)
    ablation  = load(a_path)

    check_complete(grounded, "grounded")
    check_complete(ablation,  "ablation")

    print_type_table(grounded, ablation)
    print_domain_table(grounded, ablation)


if __name__ == "__main__":
    main()
