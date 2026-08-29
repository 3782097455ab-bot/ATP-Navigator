# Phase 18B — Conversational Execution, Collaboration and 3D Structural Workspace

Date: 2026-08-30

## Outcome

Phase 18B integrates the Phase 18A local product with persistent research conversation, explicit Plan Preview/confirmation, a strict action registry, registered-pose 3D viewing, team review, a unified activity timeline and a computational DBTL view. It does not train a model or change any frozen scientific result.

## Implemented capability

- 13 intent types route to structured read-only queries or confirmed actions.
- Multi-turn candidate context supports “从这里” follow-up requests.
- Acquisition, generation and calculation requests cannot execute before confirmation.
- Product actions are recorded in the shared Calculation Job Registry with a distinct product protocol and no fabricated evidence.
- Candidate pose rendering verifies artifact identity and preserves protocol scope.
- AI recommendation, reviewer vote and final human decision remain separate records.
- The Make/Test queue is restricted to `Planned`/`Proposed` until separately reviewed evidence exists.
- Presentation Mode demonstrates registered data and cached real results without simulating live computation.

## Browser acceptance

The real local Streamlit app was exercised in the in-app browser. Acceptance covered:

- Research Console load;
- read-only Glide/Vina disagreement query;
- contextual acquisition Plan Preview;
- explicit confirmation and versioned panel creation;
- plan-linked Job Registry display;
- registered Vina pose rendering with zero browser console errors;
- team review/vote audit path;
- unified activity timeline;
- computational DBTL boundary;
- Presentation Mode.

Screenshots are stored in `results/phase18b/screenshots/`.

The contextual acceptance request asked for five candidates from the previous ten-candidate set. Four had records in the frozen acquisition feature universe, so the final versioned panel contains four and reports the difference; no identity or feature was invented to force the requested count.

## Scientific and product limitations

- No reviewed ATP inhibition, MIC or toxicity feedback is available.
- The conversational layer does not improve Model v3 predictive performance; performance comparison is not applicable.
- The optional OpenAI intent provider is not required for deterministic operation and was not needed for acceptance.
- 3D display depends on registered poses and represents protocol-specific computational structure only.
- Phase 17.1 WSL work remains an independent background scientific execution and was not stopped, restarted or modified by this phase.

## Verification

Automated tests cover intent routing, context, confirmation gating, action whitelisting, job linking/provenance, collaboration separation, planning-only Make/Test state, evidence unknown semantics, registered pose handling and computational DBTL wording. The final full suite passed 195/195; all 24 protected model files match the Phase14 SHA-256 baseline. Machine-readable results are in `results/phase18b/acceptance.json`.
