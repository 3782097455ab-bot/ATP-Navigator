from pathlib import Path
import math
import re
import shutil
from .base_adapter import ToolAdapter,ToolInfo,probe


def validate_box(box):
    if not isinstance(box,dict) or set(box)!={'center','size'}:
        raise ValueError('Explicit box center and size required; no guessed binding site')
    for k in ['center','size']:
        if len(box[k])!=3 or not all(isinstance(v,(float,int)) and math.isfinite(v) for v in box[k]):
            raise ValueError('Box requires three finite coordinates')
    if any(v<=0 or v>100 for v in box['size']):
        raise ValueError('Box size outside explicit local docking limits')


def parse_vina_pose(path):
    text=Path(path).read_text(encoding='utf-8')
    values=re.findall(r'^REMARK VINA RESULT:\s+([-+\d.eE]+)',text,re.M)
    if not values or not any(line.startswith(('ATOM','HETATM')) for line in text.splitlines()):
        raise ValueError('Missing real Vina affinity/pose')
    values=[float(x) for x in values]
    if not all(math.isfinite(x) for x in values):
        raise ValueError('Nonfinite Vina score')
    return {'affinity':values[0],'pose_count':len(values),'affinities':values}


class VinaAdapter(ToolAdapter):
    @classmethod
    def discover(cls, project):
        path=shutil.which('vina')
        if not path:
            candidates=sorted((Path(project)/'workspace_local/tools').glob('vina*/vina*.exe'))
            path=str(candidates[-1]) if candidates else None
        info=ToolInfo('vina','AutoDock Vina','open_toolchain',['docking'],executable_path=path,
                      license_status='open_source_no_checkout_required')
        if path:
            result=probe([path,'--version'])
            info.probe={k:v for k,v in result.items() if k!='text'}
            match=re.search(r'Vina\s+(v?\d+\.\d+\.\d+)',result['text'],re.I)
            if result['return_code']==0 and match:
                info.availability='available';info.tool_version=match.group(1)
            else:
                info.availability='configuration_error';info.reason='Vina version probe failed'
        return cls(info)

    def validate_protocol(self, protocol):
        errors=[]
        try: validate_box(protocol.get('box'))
        except (ValueError,TypeError) as e: errors.append(str(e))
        if protocol.get('confirmation') not in {'researcher_confirmed','official_tutorial_smoke_only'}:
            errors.append('New protocol and box require researcher confirmation')
        if not protocol.get('receptor'):
            errors.append('Prepared receptor missing')
        return errors
