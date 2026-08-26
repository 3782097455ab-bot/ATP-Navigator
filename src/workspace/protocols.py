"""Read-only protocol archaeology; no receptor/grid creation or guessed settings."""
from pathlib import Path
import os
from .state import file_hash, digest, write_json

UNKNOWN = 'unknown'
REQUIRED = ['receptor','grid','force_field','protonation','ligand_preparation','docking_mode','mmgbsa_protocol']


def discover_protocol(project_root, output=None):
    base = Path(project_root).resolve().parent
    found = {'receptor_candidates':[], 'grid_candidates':[], 'input_configuration_candidates':[]}
    # Exclude copies, environments and generated workspaces. Only original research modules.
    for module in ['作图','运行','表征']:
        root = base / module
        if not root.exists():
            continue
        for directory, _, filenames in os.walk(root):
            for name in filenames:
                path = Path(directory) / name
                lower = name.lower()
                category = None
                if lower.endswith('.pdb') and ('7p3w' in lower or 'receptor' in lower):
                    category = 'receptor_candidates'
                elif lower.endswith('.zip') and 'grid' in lower:
                    category = 'grid_candidates'
                elif lower.endswith(('.in','.inp')):
                    category = 'input_configuration_candidates'
                if category:
                    found[category].append({'path':str(path.relative_to(base)), 'sha256':file_hash(path),
                                            'size':path.stat().st_size})
    manifest = {'project':'atp_synthase','target_reference':'7P3W',
                **{k:UNKNOWN for k in REQUIRED},'historical_equivalence':'unverified',
                'confirmation':'required','discovery':found,
                'note':'7P3W-A.pdb is a historical receptor candidate, not proof of the prepared docking receptor. No grid is created.'}
    manifest['protocol_id'] = 'atp_historical_audit_' + digest(manifest)[:12]
    if output:
        write_json(output,manifest)
    return manifest


def rdkit_protocol(version):
    return {'protocol_id':'rdkit_morgan2_1024_chiral_v1_' + version.replace('.','_'),
            'tool':'rdkit','tool_version':version,'canonical_isomeric_smiles':True,
            'fingerprint':{'type':'Morgan','radius':2,'bits':1024,'chirality':True},
            'protonation':'preserve_input_no_reionization','salt_handling':'preserve_input',
            'geometry_generation':False,'confirmation':'built_in_explicit_contract'}


def protocol_issues(manifest, tool, stage):
    if tool == 'rdkit':
        return []
    required = ['force_field','protonation','ligand_preparation']
    if tool in {'glide','prime_mmgbsa'}:
        required += ['receptor','grid','docking_mode']
    if tool == 'prime_mmgbsa':
        required += ['mmgbsa_protocol']
    issues = ['protocol.' + k + '=unknown' for k in required if manifest.get(k) in (None,'',UNKNOWN)]
    if manifest.get('confirmation') != 'researcher_confirmed':
        issues.append('protocol_confirmation_required')
    if stage in {'HTVS','SP','XP'} and manifest.get('docking_mode') not in ([stage], stage):
        # A protocol may explicitly declare all three independent modes.
        modes = manifest.get('docking_mode')
        if not isinstance(modes,list) or stage not in modes:
            issues.append('docking_mode_not_confirmed_for_' + stage)
    for key in ['receptor','grid']:
        item = manifest.get(key)
        if isinstance(item,dict):
            path = Path(item.get('path',''))
            if not path.is_file() or file_hash(path) != item.get('sha256'):
                issues.append(key + '_missing_or_hash_mismatch')
        elif tool in {'glide','prime_mmgbsa'}:
            issues.append(key + '_must_be_hash_pinned')
    return sorted(set(issues))
