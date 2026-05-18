"""
Benchmark: DTDL→ASP fact parsing, @DTDL/Debug solving, @DTDL/Analysis solving,
           and end-to-end LLM latency for @DTDL/Debug with symbolic grounding.

Usage:
    uv run benchmark.py                        # parsing + solving only (no LLM)
    OPENROUTER_API_KEY=sk-... uv run benchmark.py  # also include LLM benchmark

Requirements:
    - clingo (pip install clingo)
    - openai (only for the LLM benchmark, installed automatically by uv)
    - The debug.lp and analysis.lp files in ../asp-chef/src/lib/operations/@DTDL/res/
      or in the same folder as this script
"""

# /// script
# requires-python = ">=3.11"
# dependencies = ["clingo", "openai", "python-dotenv"]
# ///

import json
import os
import statistics
import time

from dotenv import load_dotenv

load_dotenv()

import clingo

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_RES = os.path.join(
    SCRIPT_DIR, "..", "..", "..", "asp-chef", "src", "lib", "operations", "@DTDL", "res"
)
LOCAL_RES = SCRIPT_DIR


def load_lp(name):
    for base in [REPO_RES, LOCAL_RES]:
        path = os.path.join(base, name)
        if os.path.exists(path):
            with open(path) as f:
                return f.read()
    raise FileNotFoundError(f"{name} not found in {REPO_RES} nor {LOCAL_RES}")


DEBUG_LP = load_lp("debug.lp")
# The issue_count_warning rule uses non-standard syntax (sum of #count),
# not supported by clingo in ASP-Core-2 mode. We remove it for the benchmark.
ANALYSIS_LP = "\n".join(
    line
    for line in load_lp("analysis.lp").splitlines()
    if not line.startswith("issue_count_warning")
    and not line.strip().startswith("+ #count")
)

RUNS = 20  # repetitions per measurement

# ---------------------------------------------------------------------------
# Real DTDL models (greenhouse and vineyard from the paper)
# ---------------------------------------------------------------------------

GREENHOUSE = [
    {
        "@context": "dtmi:dtdl:context;4",
        "@id": "dtmi:agriculture:greenhouse:Greenhouse;1",
        "@type": "Interface",
        "displayName": "Greenhouse",
        "contents": [
            {"@type": "Telemetry", "name": "internalTemp", "schema": "double"},
            {"@type": "Telemetry", "name": "humidity", "schema": "double"},
            {"@type": "Telemetry", "name": "co2Level", "schema": "double"},
            {
                "@type": "Property",
                "name": "location",
                "schema": "string",
                "writable": True,
            },
            {
                "@type": "Relationship",
                "name": "hasClimateSensor",
                "target": "dtmi:agriculture:greenhouse:ClimateSensor;1",
            },
            {
                "@type": "Relationship",
                "name": "hasSoilNode",
                "target": "dtmi:agriculture:greenhouse:SoilNode;1",
            },
            {
                "@type": "Relationship",
                "name": "hasIrrigationValve",
                "target": "dtmi:agriculture:greenhouse:IrrigationValve;1",
            },
            {
                "@type": "Relationship",
                "name": "hasCropMonitor",
                "target": "dtmi:agriculture:greenhouse:CropMonitor;1",
            },
        ],
    },
    {
        "@context": "dtmi:dtdl:context;4",
        "@id": "dtmi:agriculture:greenhouse:ClimateSensor;1",
        "@type": "Interface",
        "displayName": "Climate Sensor",
        "contents": [
            {"@type": "Telemetry", "name": "temperature", "schema": "double"},
            {"@type": "Telemetry", "name": "humidityLevel", "schema": "double"},
            {"@type": "Telemetry", "name": "co2", "schema": "double"},
        ],
    },
    {
        "@context": "dtmi:dtdl:context;4",
        "@id": "dtmi:agriculture:greenhouse:SoilNode;1",
        "@type": "Interface",
        "displayName": "Soil Node",
        "contents": [
            {"@type": "Telemetry", "name": "soilMoisture", "schema": "double"},
            {"@type": "Telemetry", "name": "soilPh", "schema": "double"},
            {"@type": "Telemetry", "name": "nutrientLevel", "schema": "double"},
        ],
    },
    {
        "@context": "dtmi:dtdl:context;4",
        "@id": "dtmi:agriculture:greenhouse:IrrigationValve;1",
        "@type": "Interface",
        "displayName": "Irrigation Valve",
        "contents": [
            {
                "@type": "Property",
                "name": "valveState",
                "schema": "boolean",
                "writable": True,
            },
            {"@type": "Telemetry", "name": "flowRate", "schema": "double"},
        ],
    },
    {
        "@context": "dtmi:dtdl:context;4",
        "@id": "dtmi:agriculture:greenhouse:CropMonitor;1",
        "@type": "Interface",
        "displayName": "Crop Monitor",
        "contents": [
            {"@type": "Telemetry", "name": "plantHealth", "schema": "double"},
            {"@type": "Telemetry", "name": "leafAreaIndex", "schema": "double"},
        ],
    },
]

VINEYARD = [
    {
        "@context": "dtmi:dtdl:context;4",
        "@id": "dtmi:agriculture:vineyard:VineyardProperty;1",
        "@type": "Interface",
        "displayName": "VineyardProperty",
        "contents": [
            {"@type": "Property", "name": "owner", "schema": "string"},
            {"@type": "Property", "name": "totalArea", "schema": "double"},
            {"@type": "Property", "name": "elevation", "schema": "double"},
            {"@type": "Property", "name": "location", "schema": "string"},
            {
                "@type": "Relationship",
                "name": "hasVineyardPlots",
                "target": "dtmi:agriculture:vineyard:VineyardPlot;1",
                "maxMultiplicity": 100,
            },
            {
                "@type": "Relationship",
                "name": "hasWeatherStation",
                "target": "dtmi:agriculture:vineyard:WeatherStation;1",
            },
            {
                "@type": "Relationship",
                "name": "hasWinery",
                "target": "dtmi:agriculture:vineyard:Winery;1",
            },
        ],
    },
    {
        "@context": "dtmi:dtdl:context;4",
        "@id": "dtmi:agriculture:vineyard:PestTrap;1",
        "@type": "Interface",
        "displayName": "PestTrap",
        "contents": [
            {"@type": "Telemetry", "name": "pestCount", "schema": "integer"},
            {"@type": "Telemetry", "name": "trapStatus", "schema": "string"},
            {"@type": "Property", "name": "trapId", "schema": "string"},
            {
                "@type": "Relationship",
                "name": "installedIn",
                "target": "dtmi:agriculture:vineyard:VineyardPlot;1",
            },
        ],
    },
    {
        "@context": "dtmi:dtdl:context;4",
        "@id": "dtmi:agriculture:vineyard:SoilMoistureSensor;1",
        "@type": "Interface",
        "displayName": "SoilMoistureSensor",
        "contents": [
            {"@type": "Telemetry", "name": "soilMoisture", "schema": "double"},
            {"@type": "Telemetry", "name": "soilTemperature", "schema": "double"},
            {
                "@type": "Telemetry",
                "name": "electricalConductivity",
                "schema": "double",
            },
            {
                "@type": "Relationship",
                "name": "installedIn",
                "target": "dtmi:agriculture:vineyard:VineyardPlot;1",
            },
        ],
    },
    {
        "@context": "dtmi:dtdl:context;4",
        "@id": "dtmi:agriculture:vineyard:IrrigationController;1",
        "@type": "Interface",
        "displayName": "IrrigationController",
        "contents": [
            {"@type": "Property", "name": "controllerId", "schema": "string"},
            {
                "@type": "Property",
                "name": "irrigationSchedule",
                "schema": "string",
                "writable": True,
            },
            {"@type": "Telemetry", "name": "waterFlowRate", "schema": "double"},
            {"@type": "Telemetry", "name": "pressureLevel", "schema": "double"},
            {
                "@type": "Relationship",
                "name": "controlsPlot",
                "target": "dtmi:agriculture:vineyard:VineyardPlot;1",
                "maxMultiplicity": 10,
            },
        ],
    },
    {
        "@context": "dtmi:dtdl:context;4",
        "@id": "dtmi:agriculture:vineyard:GrapeMonitor;1",
        "@type": "Interface",
        "displayName": "GrapeMonitor",
        "contents": [
            {"@type": "Telemetry", "name": "sugarContent", "schema": "double"},
            {"@type": "Telemetry", "name": "acidityLevel", "schema": "double"},
            {"@type": "Telemetry", "name": "berrySize", "schema": "double"},
            {"@type": "Telemetry", "name": "colorIntensity", "schema": "double"},
            {"@type": "Property", "name": "monitorId", "schema": "string"},
            {
                "@type": "Relationship",
                "name": "monitoringPlot",
                "target": "dtmi:agriculture:vineyard:VineyardPlot;1",
            },
        ],
    },
]

# ---------------------------------------------------------------------------
# DTDL → ASP parsing (Python replica of the dtdl.ts logic)
# ---------------------------------------------------------------------------


def escape(s):
    return s.replace('"', '\\"')


def schema_id(schema, owner_id=None, name=None):
    if isinstance(schema, str):
        return f'"{schema}"'
    if schema.get("@id"):
        return schema["@id"]
    return f'({owner_id}, "{name}")'


def process_schema(sid, schema, res):
    if isinstance(schema, str):
        return
    t = schema.get("@type")
    if t == "Array":
        elem = schema_id(schema["elementSchema"], sid, "element")
        res.append(f"array({sid}, {elem}).")
        process_schema(elem, schema["elementSchema"], res)
    elif t == "Enum":
        val = schema_id(schema["valueSchema"], sid, "value")
        res.append(f"enum({sid}, {val}).")
        for ev in schema.get("enumValues", []):
            v = (
                f'"{escape(ev["enumValue"])}"'
                if isinstance(ev["enumValue"], str)
                else ev["enumValue"]
            )
            res.append(f'enum_value({sid}, "{ev["name"]}", {v}).')
    elif t == "Map":
        mv = schema_id(schema["mapValue"]["schema"], sid, "value")
        res.append(f"map({sid}, {mv}).")
        process_schema(mv, schema["mapValue"]["schema"], res)
    elif t == "Object":
        res.append(f"object({sid}).")
        for field in schema.get("fields", []):
            fsid = schema_id(field["schema"], sid, field["name"])
            res.append(f'has_field({sid}, "{field["name"]}", {fsid}).')
            process_schema(fsid, field["schema"], res)


def process_interface(iface, res):
    iid = f'"{iface["@id"]}"'
    res.append(f"interface({iid}).")
    if iface.get("displayName"):
        res.append(f'displayName({iid}, "{escape(iface["displayName"])}").')
    for content in iface.get("contents", []):
        ctype = (
            content["@type"][0]
            if isinstance(content["@type"], list)
            else content["@type"]
        )
        name = content["name"]
        cid = f'({iid}, "{name}")'
        if ctype == "Property":
            sid = schema_id(content["schema"], iid, name)
            res.append(f'has_property({iid}, "{name}", {cid}).')
            res.append(f"property({cid}).")
            res.append(f"schema({cid}, {sid}).")
            if content.get("writable"):
                res.append(f"writable({cid}).")
            process_schema(sid, content["schema"], res)
        elif ctype == "Telemetry":
            sid = schema_id(content["schema"], iid, name)
            res.append(f'has_telemetry({iid}, "{name}", {cid}).')
            res.append(f"telemetry({cid}).")
            res.append(f"schema({cid}, {sid}).")
            process_schema(sid, content["schema"], res)
        elif ctype == "Relationship":
            res.append(f'has_relationship({iid}, "{name}", {cid}).')
            res.append(f"relationship({cid}).")
            if content.get("target"):
                res.append(f'target({cid}, "{content["target"]}").')
            if content.get("maxMultiplicity") is not None:
                res.append(f'maxMultiplicity({cid}, {content["maxMultiplicity"]}).')
            if content.get("minMultiplicity") is not None:
                res.append(f'minMultiplicity({cid}, {content["minMultiplicity"]}).')
        elif ctype == "Command":
            res.append(f'has_command({iid}, "{name}", {cid}).')
            res.append(f"command({cid}).")
    for ext in iface.get("extends") or []:
        ext_list = ext if isinstance(ext, list) else [ext]
        for e in ext_list:
            res.append(f'extends({iid}, "{e}").')


def dtdl_to_asp(model):
    res = []
    items = model if isinstance(model, list) else [model]
    for iface in items:
        process_interface(iface, res)
    return "\n".join(res)


# ---------------------------------------------------------------------------
# Solving with clingo
# ---------------------------------------------------------------------------


def solve(facts, program):
    ctl = clingo.Control(["--models=1"])
    ctl.add("base", [], facts + "\n" + program)
    ctl.ground([("base", [])])
    models = []
    with ctl.solve(yield_=True) as handle:
        for model in handle:
            models.append(model.symbols(shown=True))
    return models


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------


def measure(fn, runs=RUNS):
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)  # ms
    return {
        "mean_ms": round(statistics.mean(times), 3),
        "median_ms": round(statistics.median(times), 3),
        "min_ms": round(min(times), 3),
        "max_ms": round(max(times), 3),
        "stdev_ms": round(statistics.stdev(times), 3) if len(times) > 1 else 0.0,
        "runs": runs,
    }


def benchmark_model(name, model, property_value_defined_facts=""):
    print(f"\n{'='*60}")
    print(f"Model: {name}")
    print(f"{'='*60}")

    # --- parsing ---
    parse_stats = measure(lambda: dtdl_to_asp(model))
    facts = dtdl_to_asp(model)
    n_facts = facts.count("\n") + 1
    print(
        f"  Parse:    {parse_stats['mean_ms']:.3f} ms mean  "
        f"(median {parse_stats['median_ms']:.3f}, "
        f"min {parse_stats['min_ms']:.3f}, max {parse_stats['max_ms']:.3f})  "
        f"[{n_facts} facts]"
    )

    # --- debug solving ---
    debug_program = property_value_defined_facts + "\n" + DEBUG_LP
    debug_stats = measure(lambda: solve(facts, debug_program))
    print(
        f"  Debug:    {debug_stats['mean_ms']:.3f} ms mean  "
        f"(median {debug_stats['median_ms']:.3f}, "
        f"min {debug_stats['min_ms']:.3f}, max {debug_stats['max_ms']:.3f})"
    )

    # --- analysis solving ---
    analysis_stats = measure(lambda: solve(facts, ANALYSIS_LP))
    print(
        f"  Analysis: {analysis_stats['mean_ms']:.3f} ms mean  "
        f"(median {analysis_stats['median_ms']:.3f}, "
        f"min {analysis_stats['min_ms']:.3f}, max {analysis_stats['max_ms']:.3f})"
    )

    return {
        "model": name,
        "n_interfaces": len(model),
        "n_facts": n_facts,
        "parse": parse_stats,
        "debug": debug_stats,
        "analysis": analysis_stats,
    }


def benchmark_scaling():
    """Synthetic models of increasing size: 5, 10, 20, 50 interfaces."""
    print(f"\n{'='*60}")
    print("Scaling benchmark (synthetic models)")
    print(f"{'='*60}")

    results = []
    for n in [5, 10, 20, 50]:
        model = []
        for i in range(n):
            iface = {
                "@context": "dtmi:dtdl:context;4",
                "@id": f"dtmi:bench:Interface{i};1",
                "@type": "Interface",
                "displayName": f"Interface{i}",
                "contents": [
                    {"@type": "Telemetry", "name": f"temp{i}", "schema": "double"},
                    {"@type": "Telemetry", "name": f"humidity{i}", "schema": "double"},
                    {"@type": "Property", "name": f"id{i}", "schema": "string"},
                ],
            }
            if i > 0:
                iface["contents"].append(
                    {
                        "@type": "Relationship",
                        "name": f"rel{i}",
                        "target": f"dtmi:bench:Interface{i-1};1",
                    }
                )
            model.append(iface)

        parse_stats = measure(lambda m=model: dtdl_to_asp(m))
        facts = dtdl_to_asp(model)
        n_facts = facts.count("\n") + 1
        debug_stats = measure(lambda f=facts: solve(f, DEBUG_LP))
        analysis_stats = measure(lambda f=facts: solve(f, ANALYSIS_LP))

        print(
            f"  n={n:3d}  parse {parse_stats['mean_ms']:.3f} ms  "
            f"debug {debug_stats['mean_ms']:.3f} ms  "
            f"analysis {analysis_stats['mean_ms']:.3f} ms  "
            f"[{n_facts} facts]"
        )

        results.append(
            {
                "n_interfaces": n,
                "n_facts": n_facts,
                "parse_ms": parse_stats["mean_ms"],
                "debug_ms": debug_stats["mean_ms"],
                "analysis_ms": analysis_stats["mean_ms"],
            }
        )
    return results


# ---------------------------------------------------------------------------
# LLM benchmark
# ---------------------------------------------------------------------------

LLM_MODELS = [
    ("meta-llama/llama-3.2-3b-instruct", "3B"),
    ("qwen/qwen2.5-coder-7b-instruct", "7B"),
    ("meta-llama/llama-3.3-70b-instruct", "70B"),
    ("deepseek/deepseek-v3.2", "deepseek-v3.2"),  # model used in the paper
]
LLM_BASE_URL = "https://openrouter.ai/api/v1"
LLM_RUNS = 5  # API calls: kept low to avoid wasting credits

# Representative diagnostics: one per class (as in the paper)
LLM_DIAGNOSTICS = [
    {
        "type": "missing_required_property",
        "diagnostic": (
            "Interface dtmi:agriculture:vineyard:VineyardPlot;1 "
            "is missing required property 'soilType'. "
            "Add the property definition or mark it as optional."
        ),
    },
    {
        "type": "undefined_target",
        "diagnostic": (
            "Relationship 'hasVineyardPlots' in interface "
            "dtmi:agriculture:vineyard:VineyardProperty;1 "
            "references undefined interface 'dtmi:agriculture:vineyard:VineyardPlot;1'. "
            "Check DTDL model or add missing interface definition."
        ),
    },
]

LLM_SYSTEM = (
    "You are an expert in DTDL (Digital Twins Definition Language) v4. "
    "You help users debug and repair DTDL models. "
    "You will be given a specific error detected by a symbolic validator. "
    "Explain the issue and suggest one or more concrete DTDL fixes. Max 200 words."
)


def benchmark_llm_model(client, model_id: str, model_label: str):
    """Measure end-to-end latency for a single LLM model over all diagnostics."""
    results = []
    for d in LLM_DIAGNOSTICS:
        times = []
        for i in range(LLM_RUNS):
            t0 = time.perf_counter()
            response = client.chat.completions.create(
                model=model_id,
                temperature=0,
                messages=[
                    {"role": "system", "content": LLM_SYSTEM},
                    {"role": "user", "content": d["diagnostic"]},
                ],
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000
            times.append(elapsed_ms)
            n_tokens = response.usage.completion_tokens if response.usage else "?"
            print(
                f"  [{model_label:4s}] [{d['type'][:25]}] "
                f"run {i+1}/{LLM_RUNS}: {elapsed_ms:.0f} ms, {n_tokens} tokens"
            )

        stats = {
            "model": model_id,
            "label": model_label,
            "type": d["type"],
            "mean_ms": round(statistics.mean(times), 1),
            "median_ms": round(statistics.median(times), 1),
            "min_ms": round(min(times), 1),
            "max_ms": round(max(times), 1),
            "runs": LLM_RUNS,
        }
        print(
            f"         -> mean {stats['mean_ms']:.0f} ms  "
            f"(min {stats['min_ms']:.0f}, max {stats['max_ms']:.0f})"
        )
        results.append(stats)
    return results


def benchmark_llm(api_key: str):
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=LLM_BASE_URL)

    print(f"\n{'='*60}")
    print(f"LLM benchmark ({LLM_RUNS} calls per diagnostic per model)")
    print(f"{'='*60}")

    all_results = []
    for model_id, model_label in LLM_MODELS:
        print(f"\n  Model: {model_id}")
        results = benchmark_llm_model(client, model_id, model_label)
        all_results.extend(results)

    return all_results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # property_value_defined for the vineyard (as in the paper)
    vineyard_pvd = "\n".join(
        [
            'property_value_defined("dtmi:agriculture:vineyard:VineyardPlot;1", "soilType").',
            'property_value_defined("dtmi:agriculture:vineyard:VineyardPlot;1", "plotArea").',
            'property_value_defined("dtmi:agriculture:vineyard:VineyardPlot;1", "grapeVariety").',
            'property_value_defined("dtmi:agriculture:vineyard:WeatherStation;1", "stationId").',
            'property_value_defined("dtmi:agriculture:vineyard:WeatherStation;1", "location").',
            'property_value_defined("dtmi:agriculture:vineyard:Winery;1", "wineryId").',
            'property_value_defined("dtmi:agriculture:vineyard:Winery;1", "capacity").',
        ]
    )

    greenhouse_pvd = 'property_value_defined("dtmi:agriculture:greenhouse:Greenhouse;1", "greenhouseId").'

    results = []
    results.append(benchmark_model("greenhouse", GREENHOUSE, greenhouse_pvd))
    results.append(benchmark_model("vineyard", VINEYARD, vineyard_pvd))
    scaling = benchmark_scaling()

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    llm_results = None
    if api_key:
        llm_results = benchmark_llm(api_key)
    else:
        print(
            "\n[LLM benchmark skipped: set OPENROUTER_API_KEY to include LLM latency]"
        )

    out = {
        "runs_per_measurement": RUNS,
        "models": results,
        "scaling": scaling,
    }
    if llm_results:
        out["llm"] = llm_results

    out_path = os.path.join(SCRIPT_DIR, "..", "data", "results", "benchmark_results.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)

    print(f"\nResults saved to {out_path}")
    if llm_results:
        print("\nLLM latency (end-to-end, network included):")
        print(
            f"  {'Model':<8}  {'Diagnostic type':<30}  {'mean':>7}  {'min':>7}  {'max':>7}"
        )
        print(f"  {'-'*8}  {'-'*30}  {'-'*7}  {'-'*7}  {'-'*7}")
        for r in llm_results:
            print(
                f"  {r['label']:<8}  {r['type']:<30}  "
                f"{r['mean_ms']:>6.0f}ms  {r['min_ms']:>6.0f}ms  {r['max_ms']:>6.0f}ms"
            )


def benchmark_scaling_extended():
    """Extended synthetic models: 100, 150, 200 interfaces."""
    print(f"\n{'='*60}")
    print("Scaling benchmark EXTENDED (100, 150, 200 interfaces)")
    print(f"{'='*60}")

    results = []
    for n in [100, 150, 200]:
        model = []
        for i in range(n):
            iface = {
                "@context": "dtmi:dtdl:context;4",
                "@id": f"dtmi:bench:Interface{i};1",
                "@type": "Interface",
                "displayName": f"Interface{i}",
                "contents": [
                    {"@type": "Telemetry", "name": f"temp{i}", "schema": "double"},
                    {"@type": "Telemetry", "name": f"humidity{i}", "schema": "double"},
                    {"@type": "Property", "name": f"id{i}", "schema": "string"},
                ],
            }
            if i > 0:
                iface["contents"].append(
                    {
                        "@type": "Relationship",
                        "name": f"rel{i}",
                        "target": f"dtmi:bench:Interface{i-1};1",
                    }
                )
            if i % 10 == 0 and i > 0:
                iface["extends"] = [f"dtmi:bench:Interface{i-10};1"]
            model.append(iface)

        parse_stats = measure(lambda m=model: dtdl_to_asp(m))
        facts = dtdl_to_asp(model)
        n_facts = facts.count("\n") + 1
        debug_stats = measure(lambda f=facts: solve(f, DEBUG_LP))
        analysis_stats = measure(lambda f=facts: solve(f, ANALYSIS_LP))

        print(
            f"  n={n:3d}  parse {parse_stats['mean_ms']:.3f} ms  "
            f"debug {debug_stats['mean_ms']:.3f} ms  "
            f"analysis {analysis_stats['mean_ms']:.3f} ms  "
            f"[{n_facts} facts]"
        )

        results.append(
            {
                "n_interfaces": n,
                "n_facts": n_facts,
                "parse_ms": parse_stats["mean_ms"],
                "debug_ms": debug_stats["mean_ms"],
                "analysis_ms": analysis_stats["mean_ms"],
            }
        )
    return results


if __name__ == "__main__" and False:
    pass  # main block already defined above
