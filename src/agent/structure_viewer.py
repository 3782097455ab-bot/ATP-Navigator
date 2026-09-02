"""Registered-pose lookup and browser-native 3Dmol.js rendering."""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class PoseRegistry:
    def __init__(self, project: str | Path):
        self.project = Path(project).resolve()
        self.receptor = self.project / "configs/projects/ab_atp_synthase/vina_7p3w_v1/assets/ATP_e_g_prepared.pdb"

    @lru_cache(maxsize=1)
    def _cloud_pose(self) -> dict[str, Any]:
        """Return the committed, read-only pose manifest used by cloud_viewer."""
        path = self.project / "data/cloud_demo/pose_manifest.json"
        if not path.is_file():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    @lru_cache(maxsize=1)
    def _historical(self) -> dict[str, dict[str, Any]]:
        path = self.project / "results/phase14/full_library_vina_ranking.csv"
        if not path.is_file():
            return {}
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        return {str(row["canonical_id"]): row for row in frame.to_dict("records")}

    @lru_cache(maxsize=1)
    def _generated(self) -> dict[str, dict[str, Any]]:
        path = self.project / "results/phase16/generated_vina_results.csv"
        if not path.is_file():
            return {}
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        return {str(row["generated_candidate_id"]): row for row in frame.to_dict("records")}

    def _internal_pose(self, candidate_id: str) -> tuple[Path, dict[str, Any]] | None:
        for result_path in (self.project / "workspace_local/multi_jobs").glob("*/attempt_*/result.json"):
            try:
                payload = json.loads(result_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if payload.get("compound_id") != candidate_id:
                continue
            pose = result_path.with_name("pose.pdbqt")
            if pose.is_file():
                evidence = next((item for item in payload.get("evidence", []) if item.get("evidence_type") == "vina_affinity"), {})
                return pose, {
                    "affinity": evidence.get("raw_value"),
                    "pose_hash": evidence.get("provenance", {}).get("output_pose_hash", sha256(pose)),
                    "pose_qc": "registered",
                    "protocol": "vina_7p3w_v1",
                    "source_job": result_path.parent.parent.name,
                }
        return None

    def lookup(self, candidate_id: str) -> dict[str, Any]:
        candidate_id = str(candidate_id)
        pose: Path | None = None
        metadata: dict[str, Any] = {}
        historical = self._historical().get(candidate_id)
        if historical:
            signature = historical["signature"]
            pose = self.project / "workspace_local/phase14_vina/jobs" / signature[:2] / signature / "pose.pdbqt"
            metadata = {
                "affinity": float(historical["vina_affinity"]),
                "pose_hash": historical["pose_sha256"],
                "pose_qc": "pass" if pose.is_file() else "missing",
                "protocol": "vina_7p3w_v1",
                "source_job": signature,
            }
            if not pose.is_file():
                cloud = self._cloud_pose()
                if cloud.get("candidate_id") == candidate_id:
                    pose = self.project / cloud["pose_path"]
                    self.receptor = self.project / cloud["receptor_path"]
                    metadata = {
                        "affinity": cloud.get("vina_affinity_kcal_mol"),
                        "pose_hash": cloud.get("pose_sha256", ""),
                        "pose_qc": cloud.get("pose_qc", "unknown"),
                        "protocol": cloud.get("protocol_id", "vina_7p3w_v1"),
                        "source_job": cloud.get("source_job_signature", ""),
                    }
        generated = self._generated().get(candidate_id)
        if generated:
            declared = generated.get("pose_path", "").replace("\\", "/")
            pose = self.project / declared
            metadata = {
                "affinity": float(generated["vina_affinity"]) if generated.get("vina_affinity") else None,
                "pose_hash": generated.get("pose_hash", ""),
                "pose_qc": generated.get("pose_qc", "unknown"),
                "protocol": generated.get("protocol_id", "vina_7p3w_v1"),
                "source_job": generated.get("job_signature", ""),
            }
        if pose is None:
            internal = self._internal_pose(candidate_id)
            if internal:
                pose, metadata = internal
        if pose is None or not pose.is_file() or not self.receptor.is_file():
            return {
                "status": "missing",
                "candidate_id": candidate_id,
                "message": "No registered pose available.",
                "protocol": metadata.get("protocol", "unknown"),
            }
        observed = sha256(pose)
        recorded = metadata.get("pose_hash")
        if recorded and recorded != observed:
            return {
                "status": "integrity_failure",
                "candidate_id": candidate_id,
                "message": "Registered pose hash does not match the file.",
                "protocol": metadata.get("protocol", "unknown"),
            }
        return {
            "status": "available",
            "candidate_id": candidate_id,
            "protocol": metadata.get("protocol", "vina_7p3w_v1"),
            "affinity": metadata.get("affinity"),
            "pose_qc": metadata.get("pose_qc", "unknown"),
            "receptor": "7P3W subunits e/g",
            "receptor_path": str(self.receptor),
            "receptor_hash": sha256(self.receptor),
            "pose_path": str(pose),
            "pose_hash": observed,
            "source_job": metadata.get("source_job", ""),
            "scientific_scope": "registered Vina pose; not an MM/GBSA pose or experimental structure",
        }

    def html(self, candidate_id: str, height: int = 620) -> tuple[str | None, dict[str, Any]]:
        record = self.lookup(candidate_id)
        if record["status"] != "available":
            return None, record
        receptor = Path(record["receptor_path"]).read_text(encoding="utf-8", errors="replace")
        ligand = Path(record["pose_path"]).read_text(encoding="utf-8", errors="replace")
        receptor_js = json.dumps(receptor)
        ligand_js = json.dumps(ligand)
        html = f"""
        <div style="position:relative;width:100%;height:{height}px;border:1px solid #dfe7e5;border-radius:10px;overflow:hidden;background:#f8fbfa">
          <div id="atpnav_3d" style="width:100%;height:100%;position:relative"></div>
          <div style="position:absolute;right:10px;top:10px;z-index:5;display:flex;gap:6px">
            <button onclick="atpnavViewer.zoomTo({{model:1}});atpnavViewer.render()">聚焦配体</button>
            <button onclick="atpnavViewer.zoomTo();atpnavViewer.render()">重置视图</button>
          </div>
        </div>
        <script src="https://3Dmol.org/build/3Dmol-min.js"></script>
        <script>
          const element = document.getElementById('atpnav_3d');
          const atpnavViewer = $3Dmol.createViewer(element, {{backgroundColor:'#f8fbfa'}});
          atpnavViewer.addModel({receptor_js}, 'pdb');
          atpnavViewer.setStyle({{model:0}}, {{cartoon:{{color:'spectrum',opacity:0.88}}}});
          atpnavViewer.addModel({ligand_js}, 'pdbqt');
          atpnavViewer.setStyle({{model:1}}, {{stick:{{radius:0.24,colorscheme:'Jmol'}},sphere:{{scale:0.28,colorscheme:'Jmol'}}}});
          atpnavViewer.addStyle({{model:0,within:{{distance:5,sel:{{model:1}}}}}}, {{stick:{{radius:0.15,colorscheme:'Jmol'}}}});
          atpnavViewer.zoomTo({{model:1}});
          atpnavViewer.render();
          atpnavViewer.spin(false);
        </script>
        """
        return html, record
