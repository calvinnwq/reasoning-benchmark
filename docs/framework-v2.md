# Reasoning Benchmark Framework v2 Spec

**Status:** M1 draft  
**Scope owner:** NGX-131  
**Primary goal:** Turn the current short-reasoning benchmark into a small, durable framework without changing its character or pretending it is a general evaluation platform.

## Why v2 Exists

The repository already has a useful core: a 50-question dataset, prompt contract, runner scaffolding, adapter layer, and conservative answer scorer. V2 should make those pieces easier to extend and audit while preserving the current benchmark's main value: short natural-language prompts that expose shallow reasoning failures.

The framework should not become a broad agent benchmark, a task harness for arbitrary tools, or a heavy platform. It should make the existing benchmark more reproducible, make future task families fit cleanly, and keep scored artifacts comparable over time.

## Current Repo Baseline

The current implementation is intentionally small and stdlib-only:

- `data/questions.json` is the canonical dataset.
- `scripts/benchmark_contract.py` owns the model-facing response shape.
- `scripts/run_benchmark.py` lists questions, emits sample runs, and exports prompt JSONL.
- `scripts/run_baselines.py` creates raw and scored baseline artifacts for selected models.
- `scripts/score_run.py` applies V1 automatic final-answer scoring and preserves manual review fields.
- `docs/scoring.md` defines the scoring contract.

V2 should evolve these surfaces rather than replace them wholesale.

## Product Scope

V2 covers four responsibilities:

1. **Dataset contracts**
   Define the fields a benchmark case needs for identity, task family, prompt text, expected answers, accepted alternatives, failure modes, ambiguity metadata, and evaluation mode.

2. **Execution contracts**
   Define how a run selects a suite, models, prompt contract, budgets, seeds where relevant, adapter path, and output location.

3. **Evaluation contracts**
   Keep exact final-answer scoring as the default, but allow future rubric and hybrid evaluators to exist beside it with explicit scoring dimensions and weights.

4. **Artifact contracts**
   Save enough evidence for every run to be replayed, audited, and compared: config, dataset fingerprint, raw model output, normalized scoring trace, and summary metadata.

## Non-Goals

V2 does not need to support:

- browser, file, shell, or tool-use tasks
- multi-agent collaboration runs
- long-horizon task completion benchmarks
- externally hosted job orchestration
- a web UI
- a database
- package manager or non-stdlib runtime dependencies
- automatic LLM-as-judge scoring as the default path

These are possible future extensions, but the core should stay focused on short reasoning cases.

## Selective Platform Concepts

The framework can borrow platform-level concepts from org-bench-style systems only where they solve an immediate problem:

- **Suite:** a named collection of cases, such as full, smoke, starter, or holdout.
- **Task family:** a stable grouping for analysis, such as goal grounding, social pragmatics, or physical commonsense.
- **Run config:** a reproducible declaration of suite, models, adapter, prompt contract, budget, and output path.
- **Artifact bundle:** a directory or JSON manifest that ties together raw outputs, scored outputs, config, and fingerprints.
- **Report summary:** aggregate accuracy and breakdowns by model, suite, task family, evaluation mode, and failure mode.

Concepts that should not be pulled into the core yet:

- agent roles
- tools and permissions
- environment setup tasks
- graders that require external services
- organization-level dashboards
- worker queues or distributed execution

## Framework Objects

The detailed JSON shapes belong to NGX-132, but V2 should reserve these object boundaries:

- **BenchmarkCase:** one prompt plus expected-answer and evaluation metadata.
- **TaskFamily:** a logical family used for curation and reporting.
- **Suite:** an ordered case selection with a reason for inclusion.
- **PromptContract:** the model-facing instruction and required response shape.
- **RunConfig:** one reproducible run request.
- **ModelResult:** one model's raw answer and reasoning for one case.
- **ScoreRecord:** one evaluated result with scoring trace and preserved manual fields.
- **RunArtifactBundle:** the durable saved evidence for a run.
- **ReportSummary:** aggregate comparison output.

These boundaries should be simple enough to represent as plain JSON and Python dictionaries until implementation pressure proves a need for stronger abstractions.

## Data Flow

1. Load a suite from `data/questions.json` or a future suite manifest.
2. Build prompts using `scripts/benchmark_contract.py`.
3. Execute each selected model through the adapter layer or emit blank/dry-run records.
4. Write raw run records under `runs/`.
5. Score raw records with `scripts/score_run.py`.
6. Preserve raw answers, normalized matching traces, manual scoring fields, and summary metadata.
7. Generate reports from scored artifacts without re-running models.

## Extension Points

V2 should expose extension points where the next milestones already point:

- **Dataset schema extension:** add ambiguity, cooperative-intent, accepted-interpretation, calibration, and evaluator fields without breaking existing questions.
- **Evaluator modes:** support exact, rubric, and hybrid evaluation through explicit per-case configuration.
- **Suite selection:** allow named slices such as smoke, starter, full, and holdout.
- **Adapters:** keep CLI and direct/provider adapters behind the shared adapter library.
- **Reporting:** compute comparisons by family, failure mode, model, and evaluator mode from saved artifacts.

Extension points should be data contracts first. Code abstractions should appear only when they reduce duplication in the runner, scorer, or reporter.

## Compatibility Rules

- Existing `data/questions.json` rows must remain readable during migration.
- Existing run shapes accepted by `score_run.py` (`results`, `runs`, `items`, `answers`, or bare list) should continue to score.
- Scored artifacts must keep `score_answer`, `score_reasoning`, `score_constraint_extraction`, `penalties`, and `notes`.
- Automatic scoring must continue to distinguish exact matches from heuristic matches.
- New metadata fields should be optional until all dataset rows are migrated.
- Public docs should refer to `data/questions.json` and `data/questions.csv` as canonical paths.

## M1 Deliverables

M1 should produce contracts, not a full rewrite:

- NGX-131: this framework spec.
- NGX-132: canonical entities and artifact bundle schema.
- NGX-133: extended dataset schema for ambiguity and pragmatic reasoning cases.

After M1, M2 can refactor the runner and evaluator code against these contracts with less ambiguity.

## Acceptance Criteria

This spec is complete enough for NGX-131 when:

- it describes the actual repository shape rather than an aspirational platform
- it names the core framework objects and their ownership boundaries
- it defines scope and non-goals clearly
- it identifies which platform concepts are useful now and which should stay out
- it leaves detailed JSON schemas to NGX-132 and dataset field migration to NGX-133
