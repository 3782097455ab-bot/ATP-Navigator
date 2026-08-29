# Collaboration Workflow

## Three separate decision layers

ATP-Navigator stores the following as different records:

1. **AI recommendation**: frozen model/Decision Engine output and registered computational evidence.
2. **Team review and vote**: reviewer identity, comment, vote and timestamp.
3. **Final human decision**: explicit decision, rationale and immutable evidence snapshot hash.

A vote never changes an AI score. A final decision never becomes a training label automatically.

## Team Review Board

The board joins frozen candidate ranking, evidence completeness, protocol disagreement and collaboration records. Researchers can add comments or votes, but only an explicit final-human-decision action establishes the project decision. The snapshot hash records exactly which evidence state the researcher saw.

## Make/Test queue

The queue is currently a planning interface. Because there is no reviewed ATP inhibition, MIC or toxicity feedback, allowed states are only `Planned` and `Proposed`. Later calculation, synthesis and assay states require a separately reviewed evidence transition and cannot be asserted from this UI.

## Unified timeline

The Activity Timeline merges, without copying scientific values into a second database:

- conversation and plan events;
- Calculation Job Registry status;
- Evidence Registry additions;
- reviews, votes and human decisions.

The shared keys are project, candidate, protocol, job and decision identifiers. Product-only events are marked as such and cannot masquerade as experimental evidence.

## Deployment boundary

The local mode supports persistent sessions, plan confirmation and collaboration writes. A future cloud viewer may expose read-only registered results; it must not silently execute local scientific tools or export private project data.
