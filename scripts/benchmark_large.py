"""
Scalability benchmark on large synthetic models:
100, 150, 200 interfaces — extension of Table 5 of the paper.

Uses the same logic as benchmark.py but covers the >50 interface range
requested by the reviewers (W4).

Usage:
    uv run benchmark_large.py
"""

# /// script
# requires-python = ">=3.11"
# dependencies = ["clingo"]
# ///

import json
import os
import statistics
import time

import clingo

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_RES = os.path.join(
    SCRIPT_DIR, "..", "..", "..", "asp-chef", "src", "lib", "operations", "@DTDL", "res"
)


def load_lp(name):
    for base in [REPO_RES, SCRIPT_DIR]:
        path = os.path.join(base, name)
        if os.path.exists(path):
            with open(path) as f:
                return f.read()
    raise FileNotFoundError(f"{name} not found")


DEBUG_LP = load_lp("debug.lp")
ANALYSIS_LP = "\n".join(
    line
    for line in load_lp("analysis.lp").splitlines()
    if not line.startswith("issue_count_warning") and not line.strip().startswith("+ #count")
)

RUNS = 20


def dtdl_to_asp(model):
    res = []
    for iface in (model if isinstance(model, list) else [model]):
        iid = f'"{iface["@id"]}"'
        res.append(f"interface({iid}).")
        if iface.get("displayName"):
            res.append(f'displayName({iid}, "{iface["displayName"]}").')
        for content in iface.get("contents", []):
            ctype = content["@type"][0] if isinstance(content["@type"], list) else content["@type"]
            name = content["name"]
            cid = f'({iid}, "{name}")'
            if ctype == "Property":
                schema = f'"{content["schema"]}"' if isinstance(content["schema"], str) else content["schema"]
                res.append(f'has_property({iid}, "{name}", {cid}).')
                res.append(f"property({cid}).")
                res.append(f"schema({cid}, {schema}).")
                if content.get("writable"):
                    res.append(f"writable({cid}).")
            elif ctype == "Telemetry":
                schema = f'"{content["schema"]}"' if isinstance(content["schema"], str) else content["schema"]
                res.append(f'has_telemetry({iid}, "{name}", {cid}).')
                res.append(f"telemetry({cid}).")
                res.append(f"schema({cid}, {schema}).")
            elif ctype == "Relationship":
                res.append(f'has_relationship({iid}, "{name}", {cid}).')
                res.append(f"relationship({cid}).")
                if content.get("target"):
                    res.append(f'target({cid}, "{content["target"]}").')
        for ext in iface.get("extends") or []:
            for e in (ext if isinstance(ext, list) else [ext]):
                res.append(f'extends({iid}, "{e}").')
    return "\n".join(res)


def solve(facts, program):
    ctl = clingo.Control(["--models=1"])
    ctl.add("base", [], facts + "\n" + program)
    ctl.ground([("base", [])])
    with ctl.solve(yield_=True) as handle:
        for _ in handle:
            pass


def measure(fn):
    times = []
    for _ in range(RUNS):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
    return {
        "mean_ms": round(statistics.mean(times), 3),
        "stdev_ms": round(statistics.stdev(times), 3),
    }


def make_synthetic(n):
    """
    Synthetic model with n interfaces. Richer structure than the base benchmark:
    - each interface has 2 telemetry, 1 property, 1 relationship to the previous one
    - every 10 interfaces: extends from the tenth preceding one (flat hierarchy, max depth 1)
    """
    model = []
    for i in range(n):
        iface = {
            "@context": "dtmi:dtdl:context;4",
            "@id": f"dtmi:bench:large:Interface{i};1",
            "@type": "Interface",
            "displayName": f"Interface{i}",
            "contents": [
                {"@type": "Telemetry", "name": f"temp{i}", "schema": "double"},
                {"@type": "Telemetry", "name": f"humidity{i}", "schema": "double"},
                {"@type": "Property",  "name": f"label{i}", "schema": "string"},
            ],
        }
        if i > 0:
            iface["contents"].append({
                "@type": "Relationship",
                "name": f"linksTo{i}",
                "target": f"dtmi:bench:large:Interface{i-1};1",
            })
        if i >= 10 and i % 10 == 0:
            iface["extends"] = [f"dtmi:bench:large:Interface{i-10};1"]
        model.append(iface)
    return model


if __name__ == "__main__":
    print("Scaling benchmark — large models (100, 150, 200 interfaces)")
    print(f"{'='*65}")
    print(f"{'n':>5}  {'facts':>6}  {'parse ms':>10}  {'debug ms':>10}  {'analysis ms':>12}")
    print(f"{'-'*65}")

    results = []
    for n in [100, 150, 200]:
        model = make_synthetic(n)
        facts = dtdl_to_asp(model)
        n_facts = facts.count("\n") + 1

        p = measure(lambda m=model: dtdl_to_asp(m))
        d = measure(lambda f=facts: solve(f, DEBUG_LP))
        a = measure(lambda f=facts: solve(f, ANALYSIS_LP))

        print(f"{n:>5}  {n_facts:>6}  {p['mean_ms']:>8.3f} ms  {d['mean_ms']:>8.3f} ms  {a['mean_ms']:>10.3f} ms")
        results.append({"n_interfaces": n, "n_facts": n_facts,
                        "parse_ms": p["mean_ms"], "parse_stdev": p["stdev_ms"],
                        "debug_ms": d["mean_ms"], "debug_stdev": d["stdev_ms"],
                        "analysis_ms": a["mean_ms"], "analysis_stdev": a["stdev_ms"]})

    out = os.path.join(SCRIPT_DIR, "..", "data", "results", "benchmark_large_results.json")
    with open(out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved: {out}")
