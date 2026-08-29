# Conversational Execution

## Purpose

Phase 18B turns ATP-Navigator's existing evidence and execution modules into a controlled research conversation. The conversation is an interface to registered data and allowlisted actions; it is not a source of docking, MM/GBSA, activity, toxicity, or other scientific values.

## Runtime path

```text
Researcher message
  -> deterministic/optional OpenAI intent parser
  -> structured intent and session context
  -> read-only answer OR Plan Preview
  -> explicit researcher confirmation
  -> allowlisted Action Registry
  -> Calculation Job / Evidence / Collaboration registries
  -> result, provenance, limitations and linked jobs returned to dialogue
```

Supported intent classes include candidate/evidence/provenance queries, protocol comparison, frozen decision ranking, acquisition, generation request, calculation planning, job status, missing evidence, tool capability, parent lineage and versioned export.

## Safety contract

- Natural-language input is never executed as shell, SQL, Python, `eval`, or arbitrary tool text.
- Only actions declared in `src/agent/actions.py` can run.
- Acquisition, generation and calculation-plan requests stop at a Plan Preview until confirmed.
- The preview states scope, candidate count, backend, protocol, runtime/resource expectation, Registry/file changes and scientific caveats.
- The optional OpenAI provider may only parse intent. Its key comes from `OPENAI_API_KEY`; it cannot create scientific numbers or bypass the Action Registry.
- Unknown experimental ATP inhibition, MIC and toxicity remain unknown.

## Multi-turn context

Each persistent research session stores selected candidates and the previous structured result. Therefore a second turn such as “从这里选5个” resolves only against the candidates returned in the previous turn. If fewer scoped candidates have complete acquisition features, the actual panel may be smaller and the execution result reports that difference.

## Example

1. `找出Glide和Vina分歧最大的10个候选。`
2. `如果MMGBSA只能再算5个，从这里帮我选一下。`
3. Inspect Plan Preview.
4. Confirm. ATP-Navigator writes a versioned panel, registers the product action and links existing real high-cost jobs when available. It does not simulate a new MM/GBSA result.

## Main files

- `src/agent/providers.py`: intent providers.
- `src/agent/orchestrator.py`: session, plan and confirmation orchestration.
- `src/agent/actions.py`: allowlisted actions.
- `src/agent/models.py`: intent and plan contracts.
- `workspace_local/collaboration.sqlite3`: local product/session state; excluded from scientific source data.

