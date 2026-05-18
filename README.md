# dtdl-asp-eval

Evaluation dataset and replication scripts for the paper:

> **Symbolic Analysis and LLM-Guided Debugging of Digital Twin Models with ASP Chef and DTDL**
> Mario Alviano, Paola Guarasci — _Information_ (MDPI), 2026.

This repository contains the complete evaluation material referenced in Section 7
of the paper: the DTDL test models, the LLM responses, the evaluation logs, and
the scripts that compute the reported metrics. All results in Tables 5–7 are
reproducible from these files.

## Requirements

- Python ≥ 3.14
- [`uv`](https://docs.astral.sh/uv/) (manages the Python version and dependencies)
- Dependencies (`openai`, `clingo`, `python-dotenv`) are declared in
  `pyproject.toml` and resolved automatically by `uv run`
- An `OPENROUTER_API_KEY` environment variable (only to regenerate LLM responses
  or judge scores; the mechanical metrics need no API key)

```bash
uv sync
```

## Repository layout

```
dtdl-asp-eval/
├── scripts/                 # all evaluation scripts (+ debug.lp)
├── data/
│   ├── models/              # DTDL test models with injected errors
│   ├── responses/           # LLM repair suggestions (grounded + fair-ablation)
│   └── results/             # judge / benchmark / validation logs
└── docs/                    # GitHub Pages (paper summary)
```

| Path | Description |
|------|-------------|
| `data/models/` | DTDL test models with injected errors (21 diagnostic classes, 4 domains) |
| `data/responses/grounded_responses.json` | LLM repair suggestions — **grounded** condition (full symbolic context) |
| `data/responses/responses_fair.json` | LLM repair suggestions — **fair-ablation** condition (error type + entity name only) |
| `data/results/judge_primary_results.json` | Primary judge verdicts (Claude Sonnet 4.6) |
| `data/results/judge_secondary_results.json`, `judge_interrater_results.json` | Inter-judge reliability data (Table 7) |
| `data/results/validation_results.json` | Symbolic validation logs |
| `data/results/benchmark_results.json`, `benchmark_large_results.json` | Latency/scalability measurements (Table 5) |

## Scripts

| Script | Purpose | Needs API key |
|--------|---------|:-:|
| `scripts/evaluate.py` | Computes `json_valid` and `entity_recall` for both conditions | no |
| `scripts/score.py` | Prints accuracy tables (grounded vs. fair ablation) per type/domain | no |
| `scripts/judge_primary.py` | Fix-quality scoring with the primary judge (Claude Sonnet 4.6, temp 0) | yes |
| `scripts/judge_secondary.py` | Second judge (Claude Opus 4.6) on the 30-case stratified sample | yes |
| `scripts/judge_interrater.py` | Independent judges (gpt-5.4, gemini-3-flash-preview) — Table 7 | yes |
| `scripts/run_grounded.py` | Regenerates `grounded_responses.json` (deepseek/deepseek-v3.2) | yes |
| `scripts/run_ablation_fair.py` | Regenerates `responses_fair.json` (fair-ablation baseline) | yes |
| `scripts/benchmark.py`, `benchmark_large.py` | End-to-end latency / scalability (Table 5) | yes |

## Reproducing the reported metrics

The mechanical metrics (no API key required) reproduce the headline numbers of
Table 6 directly from the committed responses:

```bash
uv run scripts/evaluate.py   # json_valid: 86% grounded vs. 75% fair ablation
uv run scripts/score.py      # per-type and per-domain accuracy breakdown
```

To regenerate the LLM responses and judge scores from scratch (requires
`OPENROUTER_API_KEY`):

```bash
export OPENROUTER_API_KEY=sk-or-...
uv run scripts/run_grounded.py
uv run scripts/run_ablation_fair.py
uv run scripts/evaluate.py
uv run scripts/judge_primary.py
uv run scripts/judge_secondary.py
uv run scripts/judge_interrater.py
```

## Citation

```bibtex
@article{alviano2026dtdlasp,
  title   = {Symbolic Analysis and LLM-Guided Debugging of Digital Twin
             Models with ASP Chef and DTDL},
  author  = {Alviano, Mario and Guarasci, Paola},
  journal = {Information},
  year    = {2026},
  publisher = {MDPI}
}
```

## License

Released for academic replication purposes accompanying the paper above.
