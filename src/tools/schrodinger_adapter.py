"""Discover installed products, not MSI media; never modify license settings."""
from pathlib import Path
import os
import re
import shutil
from .base_adapter import ToolAdapter, ToolInfo, probe

FEATURES = {'glide':['GLIDE_MAIN:1','GLIDE_SP_DOCKING:1','GLIDE_XP_DOCKING:1'],
            'prime_mmgbsa':['PSP_PLOP:8'],'qikprop':['QIKPROP_MAIN:2'],'ligprep':['LIGPREP_MAIN:1']}
# Feature names are product checkout requests; success still does not guarantee
# every protocol-specific optional feature. Runtime failures remain visible.


def installation_roots(extra=()):
    roots = [Path(p) for p in extra]
    if os.environ.get('SCHRODINGER'):
        roots.insert(0,Path(os.environ['SCHRODINGER']))
    if os.name == 'nt':
        import winreg
        for hive in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
            for keyname in [r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',r'SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall']:
                try:
                    with winreg.OpenKey(hive,keyname) as key:
                        for i in range(winreg.QueryInfoKey(key)[0]):
                            try:
                                with winreg.OpenKey(key,winreg.EnumKey(key,i)) as sub:
                                    name=winreg.QueryValueEx(sub,'DisplayName')[0]
                                    if 'schrodinger' in name.lower():
                                        roots.append(Path(winreg.QueryValueEx(sub,'InstallLocation')[0]))
                            except OSError:
                                pass
                except OSError:
                    pass
    for base in ['C:/Schrodinger','D:/Schrodinger','C:/Program Files/Schrodinger','D:/Program Files/Schrodinger']:
        p=Path(base)
        if p.exists():
            roots += [p,*[x for x in p.iterdir() if x.is_dir()]]
    return list(dict.fromkeys(p.resolve() for p in roots if p.is_dir()))


class SchrodingerAdapter(ToolAdapter):
    @classmethod
    def discover(cls, tool_id, roots, check_license=True):
        executable=shutil.which(tool_id)
        if not executable:
            executable=next((str(p/(tool_id+'.exe')) for p in roots if (p/(tool_id+'.exe')).is_file()),None)
        info=ToolInfo(tool_id,tool_id,'commercial_full',[tool_id],executable_path=executable)
        if not executable:
            info.reason='Installed executable not found (installation media is not executable installation)'
            return cls(info)
        info.availability='installed'
        result=probe([executable,'-h'])
        info.probe={k:v for k,v in result.items() if k!='text'}
        # Some product help commands return 1 legitimately.
        if not re.search(r'usage|options',result['text'],re.I) or 'Traceback' in result['text']:
            info.availability='configuration_error'; info.reason='Minimal help command failed or timed out'
            return cls(info)
        # Read installed package version; never parse a licensing-library version
        # printed by -v as the computational product's version.
        product={'glide':'glide','prime_mmgbsa':'psp','qikprop':'qikprop','ligprep':'macromodel'}[tool_id]
        folders=list(Path(executable).parent.glob(product+'-v*'))
        if folders: info.tool_version=folders[0].name.split('-v')[-1]
        if not check_license:
            info.reason='License checkout not requested'; return cls(info)
        lictest=Path(executable).parent/'utilities/lictest.exe'
        if not lictest.is_file():
            info.reason='Checkout utility missing'; return cls(info)
        checkout=probe([str(lictest),'-x',*FEATURES[tool_id]],timeout=15)
        info.probe['license_checkout']={k:v for k,v in checkout.items() if k!='text'}
        info.probe['license_checkout']['requested_features']=FEATURES[tool_id]
        if checkout['return_code']==0:
            info.availability='available';info.license_status='checkout_passed_for_declared_feature'
            info.reason='Real checkout passed; additional runtime entitlements may still be required'
        else:
            info.availability='installed_but_license_unavailable'
            info.license_status='unverified_timeout' if checkout['return_code'] is None else 'checkout_failed'
            info.reason='Real checkout did not establish usable entitlement; no calculation authorized'
        return cls(info)

    def build_command(self, project, request_path):
        return [str(Path(self.info.executable_path).parent/'run.exe'),
                str(Path(project)/'src/tools/commercial_worker.py'),'--request',str(request_path)]
