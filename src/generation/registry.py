"""In-memory registries with deterministic CSV export contracts."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd


@dataclass
class GeneratorRegistry:
    backends: list[dict] = field(default_factory=list)

    def register(self, record: dict) -> None:
        required = {"generator_id", "version", "status", "reason"}
        if not required.issubset(record):
            raise ValueError("Incomplete generator registration")
        self.backends.append(record)

    def as_dict(self) -> dict:
        return {"backends": self.backends, "available": [r["generator_id"] for r in self.backends if r["status"] == "available"]}


@dataclass
class GeneratedCandidateRegistry:
    records: list[dict] = field(default_factory=list)

    def add(self, record: dict) -> None:
        required = {"generated_candidate_id", "parent_candidate_id", "parent_structure_hash",
                    "generation_method", "generator_version", "generator_config", "random_seed",
                    "reaction_or_operation", "canonical_smiles", "inchikey", "murcko_scaffold",
                    "generation_timestamp", "provenance_hash"}
        if not required.issubset(record):
            raise ValueError("Incomplete generated candidate provenance")
        self.records.append(record)

    def frame(self) -> pd.DataFrame:
        frame = pd.DataFrame(self.records)
        if len(frame) and (frame["generated_candidate_id"].duplicated().any() or frame["canonical_smiles"].duplicated().any()):
            raise ValueError("Generated registry must be identity-unique")
        return frame


def provenance_hash(payload: dict) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
