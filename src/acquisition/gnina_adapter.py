"""Optional GNINA shadow-backend capability check.

GNINA never blocks Phase 15 and never fabricates a score. Absence of an
executable, usable runtime, or certified protocol yields explicit unavailable.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def certify(project: Path, timeout_seconds: int = 30) -> dict:
    candidates = [shutil.which("gnina"), shutil.which("gnina.exe")]
    executable = next((Path(value).resolve() for value in candidates if value), None)
    if executable is None:
        return {"backend": "gnina", "status": "unavailable", "reason": "executable_not_found",
                "certification_timeout_seconds": timeout_seconds, "shadow_scores_generated": 0,
                "blocking": False}
    try:
        result = subprocess.run([str(executable), "--version"], capture_output=True, text=True,
                                timeout=min(timeout_seconds, 30), check=False)
    except (OSError, subprocess.SubprocessError) as error:
        return {"backend": "gnina", "status": "unavailable",
                "reason": f"version_check_failed:{type(error).__name__}",
                "executable": str(executable), "shadow_scores_generated": 0, "blocking": False}
    if result.returncode != 0:
        return {"backend": "gnina", "status": "unavailable", "reason": "version_check_nonzero",
                "return_code": result.returncode, "executable": str(executable),
                "shadow_scores_generated": 0, "blocking": False}
    # A binary alone is insufficient: Phase 15 has no reviewed frozen GNINA
    # receptor/box/preparation manifest, so numerical execution is forbidden.
    return {"backend": "gnina", "status": "unavailable",
            "reason": "binary_found_but_frozen_gnina_protocol_missing",
            "version_output": (result.stdout or result.stderr).strip()[:500],
            "executable": str(executable), "executable_sha256": _hash(executable),
            "shadow_scores_generated": 0, "blocking": False}
