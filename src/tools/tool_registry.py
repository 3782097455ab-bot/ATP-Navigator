"""Capability discovery is separate from scientific protocol readiness."""
import importlib.metadata
import sys
from pathlib import Path
from .base_adapter import ToolAdapter,ToolInfo,probe
from .schrodinger_adapter import SchrodingerAdapter,installation_roots
from .vina_adapter import VinaAdapter
from workspace.state import write_json,now,file_hash


def discover(project, output=None, check_license=True):
    roots=installation_roots()
    entries={t:SchrodingerAdapter.discover(t,roots,check_license) for t in ['ligprep','glide','prime_mmgbsa','qikprop']}
    entries['vina']=VinaAdapter.discover(project)
    try:
        from rdkit import Chem,rdBase
        assert Chem.MolFromSmiles('CCO') is not None
        entries['rdkit']=ToolAdapter(ToolInfo('rdkit','RDKit','open_toolchain',['structure_qc','properties'],rdBase.rdkitVersion,
                                            sys.executable,'open_source_no_checkout_required','available'))
    except ImportError:
        entries['rdkit']=ToolAdapter(ToolInfo('rdkit','RDKit','open_toolchain',['structure_qc','properties'],reason='Python module missing'))
    deps=Path(project)/'workspace_local/tool_deps'
    if deps.is_dir() and str(deps) not in sys.path: sys.path.insert(0,str(deps))
    try:
        import meeko
        version=importlib.metadata.version('meeko')
        entries['meeko']=ToolAdapter(ToolInfo('meeko','Meeko + RDKit preparation','open_toolchain',
                          ['ligand_preparation','receptor_preparation'],version,sys.executable,'open_source_no_checkout_required','available'))
    except ImportError:
        entries['meeko']=ToolAdapter(ToolInfo('meeko','Meeko','open_toolchain',['ligand_preparation','receptor_preparation'],reason='Preparation dependency missing'))
    for tool,backend in [('gnina','open_toolchain'),('openmm','open_toolchain'),('gmx_mmpbsa','open_toolchain'),('desmond','commercial_full')]:
        entries[tool]=ToolAdapter(ToolInfo(tool,tool,backend,[],availability='configuration_error',reason='Reserved adapter; not implemented/executable in this release'))
    data={'created_at':now(),'installation_roots':[str(x) for x in roots],'tools':{k:v.detect() for k,v in entries.items()},
          'auxiliary_commands':{n:next((str(p/(n+'.exe')) for p in roots if (p/(n+'.exe')).is_file()),None) for n in ['run','jobcontrol','structconvert']},
          'interpretation':'Help is not checkout. Checkout is not successful calculation. Protocol readiness is checked separately.'}
    data['auxiliary_probes']={}
    for name,path in data['auxiliary_commands'].items():
        if path:
            result=probe([path,'-h'],timeout=10)
            data['auxiliary_probes'][name]={k:v for k,v in result.items() if k!='text'}
            data['auxiliary_probes'][name]['help_recognized']=any(word in result['text'].lower() for word in ['usage','options','help']) and 'Traceback' not in result['text']
    for info in data['tools'].values():
        path=info['executable_path']
        info['executable_sha256']=file_hash(path) if path and Path(path).is_file() else None
    if output: write_json(output,data)
    return data


def adapter(info):
    fields={k:v for k,v in info.items() if k in ToolInfo.__dataclass_fields__}
    cls=SchrodingerAdapter if info['tool_id'] in {'ligprep','glide','prime_mmgbsa','qikprop'} else VinaAdapter if info['tool_id']=='vina' else ToolAdapter
    return cls(ToolInfo(**fields))
