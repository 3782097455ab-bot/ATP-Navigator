"""Conservative, read-only discovery; a help command is NOT a license check."""
from __future__ import annotations
import importlib.metadata
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from .state import now, file_hash, write_json
from .tool_registry import contracts

COMMANDS = ['glide','prime_mmgbsa','qikprop','ligprep','structconvert','jobcontrol','run','desmond','lictest']


def find_command(name, roots, which=shutil.which):
    found = which(name)
    if found:
        return str(Path(found).resolve())
    for root in roots:
        for sub in ['', 'utilities']:
            for suffix in ['', '.exe', '.bat', '.cmd']:
                path = Path(root) / sub / (name + suffix)
                if path.is_file():
                    return str(path.resolve())
    return None


def license_classification(installed, probe):
    if not installed:
        return 'not_found', 'not_detected'
    if probe is None:
        return 'configuration_missing', 'unknown'
    text = (probe.stdout + probe.stderr).lower()
    if re.search(r'no (valid |available )?licenses?|license (has )?expired|cannot connect.*license|no license found', text):
        return 'installed_but_unlicensed', 'unavailable'
    # Server availability does not establish a tool-specific checkout entitlement.
    return 'configuration_missing', 'server_reported_but_tool_entitlement_unverified' if probe.returncode == 0 else 'unknown'


def discover(output=None, env=None, roots=None, which=shutil.which, runner=subprocess.run, license_features=None):
    env = dict(os.environ if env is None else env)
    install_roots = list(roots or [])
    if env.get('SCHRODINGER'):
        install_roots.insert(0, Path(env['SCHRODINGER']))
    if roots is None:
        for base in [Path('C:/Program Files'),Path('C:/Program Files (x86)'),Path('C:/Schrodinger'),Path('D:/Schrodinger')]:
            if base.exists():
                install_roots.extend(p for p in base.glob('*') if p.is_dir() and ('schrodinger' in p.name.lower() or base.name.lower()=='schrodinger'))
        install_roots += [p for root in list(install_roots) for p in Path(root).glob('*') if p.is_dir()]
    commands = {name: find_command(name,install_roots,which) for name in COMMANDS}
    tools = contracts()
    try:
        from rdkit import Chem, rdBase
        if Chem.MolFromSmiles('CCO') is None:
            raise RuntimeError('RDKit smoke check failed')
        tools['rdkit'].version = rdBase.rdkitVersion
        tools['rdkit'].executable = sys.executable
        tools['rdkit'].availability = 'available'
        tools['rdkit'].license_status = 'open_source_no_checkout_required'
    except ImportError:
        tools['rdkit'].reason = 'RDKit not importable in current interpreter'
    probe, probe_info = None, {'status':'not_run_no_schrodinger_runner'}
    if commands['run']:
        try:
            # Never expose license-server addresses/keys in the public capability file.
            probe = runner([commands['run'],'lictool','status'],capture_output=True,text=True,timeout=20,shell=False)
            import hashlib
            probe_info = {'status':'completed','return_code':probe.returncode,
                          'output_sha256':hashlib.sha256((probe.stdout+probe.stderr).encode()).hexdigest(),
                          'command':['run','lictool','status'],'tool_specific_entitlement':'unknown'}
        except (OSError,subprocess.TimeoutExpired) as error:
            probe_info = {'status':'probe_failed','error':type(error).__name__}
    for name in ['glide','prime_mmgbsa','qikprop','desmond']:
        tools[name].executable = commands[name]
        tools[name].availability, tools[name].license_status = license_classification(commands[name],probe)
        tools[name].reason = 'Executable not found' if not commands[name] else 'Tool-specific license checkout not established; execution requires a verified entitlement adapter'
        # Optional administrator-supplied feature mapping. Never infer GLIDE/PRIME
        # entitlements from the generic server status or a boolean config switch.
        features = (license_features or {}).get(name, [])
        if commands[name] and commands['lictest'] and features:
            checked = []
            for feature in features:
                if not re.fullmatch(r'[A-Z][A-Z0-9_]*',feature):
                    raise ValueError('Invalid licensing feature name')
                try:
                    result = runner([commands['lictest'],'-d',feature+':1:1'],capture_output=True,text=True,timeout=20,shell=False)
                    checked.append(result.returncode == 0 and bool(re.search(r'\bSuccess\b',result.stdout)))
                except (OSError,subprocess.TimeoutExpired):
                    checked.append(False)
            if all(checked):
                tools[name].availability, tools[name].license_status = 'available','verified_checkout_configured_features'
                tools[name].reason = 'Real lictest checkout passed for the administrator-declared feature set; execution still may fail if additional tokens are required'
            else:
                tools[name].availability, tools[name].license_status = 'installed_but_unlicensed','checkout_failed'
    result = {'created_at':now(),'interpreter':sys.executable,'SCHRODINGER_configured':bool(env.get('SCHRODINGER')),
              'searched_install_roots':[str(p) for p in install_roots], 'commands':commands,
              'license_probe':probe_info,'tools':{k:v.record() for k,v in tools.items()},
              'note':'Commercial availability is conservative; a successful help/version command is not proof of a license.'}
    if output:
        write_json(output,result)
    return result
