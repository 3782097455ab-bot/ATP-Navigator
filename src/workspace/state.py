"""One project state. Immutable evidence and protocols; CSVs are only exports."""
from __future__ import annotations

import hashlib
import json
import math
import shutil
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temporary.write_text(encode(value), encoding='utf-8')
    temporary.replace(path)


class State:
    def __init__(self, project_root, runtime_root=None):
        self.project = Path(project_root).resolve()
        self.root = Path(runtime_root or self.project / 'workspace_local').resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / 'workspace.sqlite3'
        self._verified = {}
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS execution_project(project_id TEXT PRIMARY KEY, created_at TEXT);
            CREATE TABLE IF NOT EXISTS candidate(project_id TEXT, candidate_id TEXT, smiles TEXT NOT NULL,
                alias TEXT, PRIMARY KEY(project_id,candidate_id));
            CREATE TABLE IF NOT EXISTS protocol(protocol_id TEXT PRIMARY KEY, manifest TEXT NOT NULL, sha256 TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS calculation_batch(batch_id TEXT PRIMARY KEY, project_id TEXT, session_id TEXT,
                created_at TEXT, intent TEXT, plan TEXT, actual TEXT);
            CREATE TABLE IF NOT EXISTS calculation_job(job_id TEXT PRIMARY KEY, batch_id TEXT, project_id TEXT,
                candidate_id TEXT, tool_id TEXT, protocol_id TEXT, input_artifacts TEXT, command_manifest TEXT,
                created_at TEXT, started_at TEXT, completed_at TEXT, status TEXT, return_code INTEGER,
                stdout_path TEXT, stderr_path TEXT, output_artifacts TEXT, provenance TEXT,
                signature TEXT UNIQUE, reason TEXT, attempt INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS calculation_artifact(artifact_hash TEXT PRIMARY KEY, path TEXT NOT NULL,
                size INTEGER, original_path TEXT, created_at TEXT);
            CREATE TABLE IF NOT EXISTS evidence(evidence_id TEXT PRIMARY KEY, project_id TEXT, compound_id TEXT,
                evidence_type TEXT, raw_value TEXT, normalized_value REAL, unit TEXT, protocol_id TEXT,
                tool_version TEXT, source_job_id TEXT, artifact_hash TEXT, timestamp TEXT, provenance TEXT,
                UNIQUE(project_id,compound_id,evidence_type,protocol_id,source_job_id,artifact_hash));
            CREATE TABLE IF NOT EXISTS decision_run(decision_run_id TEXT PRIMARY KEY, project_id TEXT,
                batch_id TEXT, session_id TEXT, protocol_id TEXT, model_version TEXT, evidence_ids TEXT,
                output_path TEXT, output_sha256 TEXT, created_at TEXT);
            CREATE TABLE IF NOT EXISTS feedback_link(project_id TEXT, candidate_id TEXT, protocol_id TEXT,
                decision_run_id TEXT, model_version TEXT, record_id TEXT, snapshot_id TEXT, record TEXT,
                UNIQUE(project_id,record_id,snapshot_id,decision_run_id));
            CREATE TABLE IF NOT EXISTS knowledge_record(record_id TEXT PRIMARY KEY, dataset TEXT,
                status TEXT, endpoint_stratum TEXT, source_hash TEXT, record TEXT, issues TEXT);
            CREATE INDEX IF NOT EXISTS evidence_project ON evidence(project_id,compound_id,evidence_type);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def project_id(self, project_id):
        if not project_id or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in project_id):
            raise ValueError('Invalid project identifier')
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO execution_project VALUES (?,?)', (project_id, now()))
        return project_id

    def candidate(self, project_id, candidate_id, smiles, alias=''):
        from rdkit import Chem
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise ValueError('Invalid candidate structure: ' + candidate_id)
        canonical = Chem.MolToSmiles(mol)
        with self.connect() as db:
            old = db.execute('SELECT smiles FROM candidate WHERE project_id=? AND candidate_id=?', (project_id, candidate_id)).fetchone()
            if old and old['smiles'] != canonical:
                raise ValueError('Candidate identity collision: ' + candidate_id)
            db.execute('INSERT OR IGNORE INTO candidate VALUES (?,?,?,?)', (project_id, candidate_id, canonical, alias))

    def artifact(self, path):
        path = Path(path).resolve()
        token = file_hash(path)
        dest = self.root / 'artifacts' / token / path.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and file_hash(dest) != token:
            raise ValueError('Artifact archive tampered')
        if not dest.exists():
            shutil.copyfile(path, dest)
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO calculation_artifact VALUES (?,?,?,?,?)',
                       (token, str(dest), path.stat().st_size, str(path), now()))
        return {'artifact_hash': token, 'path': str(dest), 'original_path': str(path)}

    def verify_artifact(self, token):
        with self.connect() as db:
            row = db.execute('SELECT * FROM calculation_artifact WHERE artifact_hash=?', (token,)).fetchone()
        if not row:
            raise ValueError('Missing artifact: ' + token)
        path = Path(row['path'])
        stat = path.stat()
        stamp = (stat.st_size,stat.st_mtime_ns)
        if self._verified.get(token) != stamp and file_hash(path) != token:
            raise ValueError('Missing or altered artifact: ' + token)
        self._verified[token] = stamp
        return Path(row['path'])

    def freeze_protocol(self, manifest):
        token = manifest['protocol_id']
        encoded, hashed = encode(manifest), digest(manifest)
        with self.connect() as db:
            old = db.execute('SELECT sha256 FROM protocol WHERE protocol_id=?', (token,)).fetchone()
            if old and old['sha256'] != hashed:
                raise ValueError('Protocol is immutable; use a new protocol_id')
            db.execute('INSERT OR IGNORE INTO protocol VALUES (?,?,?)', (token, encoded, hashed))
        return token

    def protocol(self, token):
        with self.connect() as db:
            row = db.execute('SELECT * FROM protocol WHERE protocol_id=?', (token,)).fetchone()
        if not row or digest(json.loads(row['manifest'])) != row['sha256']:
            raise ValueError('Protocol missing or altered')
        return json.loads(row['manifest'])

    def batch(self, project_id, intent, session_id=None):
        token = 'batch_' + uuid.uuid4().hex[:16]
        with self.connect() as db:
            db.execute('INSERT INTO calculation_batch VALUES (?,?,?,?,?,?,?)',
                       (token, project_id, session_id, now(), encode(intent), '{}', '{}'))
        return token

    def job(self, batch_id, project_id, candidate_id, tool_id, protocol_id, inputs, command):
        self.protocol(protocol_id)
        # No batch id: a second confirmed plan cannot silently repeat the same work.
        signature = digest([project_id, candidate_id, tool_id, protocol_id,
                            sorted(a['artifact_hash'] for a in inputs), command])
        token = 'job_' + signature[:20]
        with self.connect() as db:
            db.execute('''INSERT OR IGNORE INTO calculation_job
                (job_id,batch_id,project_id,candidate_id,tool_id,protocol_id,input_artifacts,command_manifest,
                 created_at,status,output_artifacts,provenance,signature,reason)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                       (token,batch_id,project_id,candidate_id,tool_id,protocol_id,encode(inputs),encode(command),
                        now(),'planned','[]',encode({'origin':'execution_workspace'}),signature,''))
        return token

    def get_job(self, job_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM calculation_job WHERE job_id=?', (job_id,)).fetchone()
        if not row:
            raise ValueError('Unknown job')
        return dict(row)

    def evidence(self, project_id, compound_id, evidence_type, value, unit, protocol_id,
                 tool_version, source_job_id, artifact_hash, provenance, normalized=None):
        if isinstance(value, (int, float)) and not math.isfinite(value):
            raise ValueError('Nonfinite evidence')
        if normalized is not None and not math.isfinite(normalized):
            raise ValueError('Nonfinite normalized evidence')
        self.protocol(protocol_id)
        self.verify_artifact(artifact_hash)
        if provenance.get('origin') not in {'tool_execution','historical_result','frozen_model_output'}:
            raise ValueError('Numerical evidence must have a permitted real source')
        job = self.get_job(source_job_id)
        if job['project_id'] != project_id or job['status'] != 'completed' or job['protocol_id'] != protocol_id:
            raise ValueError('Evidence must reference a completed job in this project/protocol')
        with self.connect() as db:
            if not db.execute('SELECT 1 FROM candidate WHERE project_id=? AND candidate_id=?', (project_id,compound_id)).fetchone():
                raise ValueError('Unregistered candidate')
            key = [project_id,compound_id,evidence_type,protocol_id,source_job_id,artifact_hash]
            token = 'ev_' + digest(key)[:24]
            old = db.execute('SELECT raw_value FROM evidence WHERE evidence_id=?', (token,)).fetchone()
            if old and old['raw_value'] != encode(value):
                raise ValueError('Evidence is immutable')
            db.execute('INSERT OR IGNORE INTO evidence VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (token,project_id,compound_id,evidence_type,encode(value),normalized,unit,protocol_id,
                        tool_version,source_job_id,artifact_hash,now(),encode(provenance)))
        return token

    def evidence_rows(self, project_id):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM evidence WHERE project_id=? ORDER BY timestamp,evidence_id', (project_id,))]

    def register_many(self, project_id, job_id, artifact_hash, rows, origin, extra=None):
        job = self.get_job(job_id)
        if job['status'] != 'completed' or job['project_id'] != project_id:
            raise ValueError('Cannot register evidence for an unfinished/unrelated job')
        if origin not in {'tool_execution','historical_result','frozen_model_output'}:
            raise ValueError('Unsupported provenance origin')
        self.verify_artifact(artifact_hash)
        self.protocol(job['protocol_id'])
        with self.connect() as db:
            allowed = {r[0] for r in db.execute('SELECT candidate_id FROM candidate WHERE project_id=?',(project_id,))}
            for row in rows:
                compound,field,value = row['compound_id'],row['evidence_type'],row['raw_value']
                if compound not in allowed:
                    raise ValueError('Unregistered output identity')
                raw = encode(value)  # also rejects NaN inside nested structures
                key = [project_id,compound,field,job['protocol_id'],job_id,artifact_hash]
                token = 'ev_' + digest(key)[:24]
                old = db.execute('SELECT raw_value FROM evidence WHERE evidence_id=?',(token,)).fetchone()
                if old and old[0] != raw:
                    raise ValueError('Immutable evidence changed')
                provenance = {'origin':origin,**(extra or {}),**row.get('provenance',{})}
                db.execute('INSERT OR IGNORE INTO evidence VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                           (token,project_id,compound,field,raw,row.get('normalized_value'),row.get('unit','unknown'),
                            job['protocol_id'],row.get('tool_version','unknown'),job_id,artifact_hash,now(),encode(provenance)))

    def event(self, session_id, kind, payload):
        if not session_id:
            return
        with self.connect() as db:
            db.execute('INSERT INTO events(session_id,created_at,kind,payload) VALUES (?,?,?,?)',
                       (session_id,now(),kind,encode(payload)))
