from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import os
import subprocess


def child_environment():
    env = dict(os.environ)
    if os.name == 'nt':
        # Standard OS path only, never an alternative license or credential.
        windows = env.get('SystemRoot') or env.get('WINDIR') or 'C:\\Windows'
        if Path(windows, 'System32').is_dir():
            env.setdefault('WINDIR', windows)
            env.setdefault('SystemRoot', windows)
    return env


@dataclass
class ToolInfo:
    tool_id: str
    tool_name: str
    backend_type: str
    supported_tasks: list
    tool_version: str = 'unknown'
    executable_path: str | None = None
    license_status: str = 'unknown'
    availability: str = 'not_found'
    reason: str = ''
    probe: dict | None = None

    def record(self):
        return asdict(self)


class ToolAdapter:
    """All subprocess work is claimed and supervised by the shared executor."""
    def __init__(self, info):
        self.info = info

    def detect(self):
        return self.info.record()

    def validate_environment(self):
        return [] if self.info.availability == 'available' else [self.info.tool_id+': '+self.info.availability+' '+self.info.reason]

    def prepare_input(self, state, paths):
        return [state.artifact(p) for p in paths]

    def build_command(self, project, request_path):
        import sys
        return [sys.executable, str(Path(project)/'src/tools/computation_worker.py'), '--request', str(request_path)]

    def run(self, executor, job_id, retry=False):
        return executor.run(job_id, retry=retry)

    def parse_output(self, path, candidate_id):
        import json
        result = json.loads(Path(path).read_text(encoding='utf-8'))
        if result['compound_id'] != candidate_id:
            raise ValueError('Output compound identity mismatch')
        return result

    def register_evidence(self, state, job, artifact, result):
        rows = [{**r, 'compound_id':job['candidate_id'], 'tool_version':self.info.tool_version} for r in result['evidence']]
        state.register_many(job['project_id'], job['job_id'], artifact['artifact_hash'], rows,
                            'tool_execution', {'backend':self.info.backend_type,'tool_id':self.info.tool_id,
                            'run_id':job['batch_id'],'job_id':job['job_id'], 'protocol_id':job['protocol_id']})


def probe(argv, timeout=12):
    """Only hashes and a short status go to tracked capability metadata."""
    import hashlib
    try:
        p = subprocess.run(argv, capture_output=True, timeout=timeout, env=child_environment())
        raw = p.stdout+p.stderr
        return {'return_code':p.returncode,'sha256':hashlib.sha256(raw).hexdigest(),
                'text':raw.decode('utf-8',errors='replace')}
    except subprocess.TimeoutExpired:
        return {'return_code':None,'text':'probe_timeout','sha256':None}
    except OSError as e:
        return {'return_code':None,'text':type(e).__name__,'sha256':None}
