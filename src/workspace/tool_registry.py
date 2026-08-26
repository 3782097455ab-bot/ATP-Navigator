"""Tool contracts, not an LLM permission to invent calculations."""
from dataclasses import asdict, dataclass, field


@dataclass
class Tool:
    tool_id: str
    version: str = 'unknown'
    executable: str | None = None
    availability: str = 'not_found'
    license_status: str = 'not_detected'
    input_contract: dict = field(default_factory=dict)
    output_contract: dict = field(default_factory=dict)
    estimated_cost: dict = field(default_factory=lambda: {'currency_cost':'unknown','wall_time':'unknown'})
    protocol_id: str = 'researcher_confirmed_protocol_required'
    reason: str = ''

    def record(self):
        return asdict(self)


def contracts():
    return {
        'rdkit': Tool('rdkit', input_contract={'format':'candidate CSV','required':['compound_id','SMILES']},
                      output_contract={'format':'CSV','fields':['canonical_smiles','scaffold','Morgan1024','descriptors','structure_status']},
                      estimated_cost={'relative_units':1,'currency_cost':'unknown','wall_time':'measured_per_job'},
                      protocol_id='rdkit_morgan2_1024_chiral_v1'),
        'glide': Tool('glide',input_contract={'required':['prepared_ligand','readonly_grid','docking_mode','confirmed_protocol']},
                      output_contract={'format':'Maestro/CSV','fields':['r_i_docking_score','r_i_glide_emodel']},
                      estimated_cost={'relative_units':10,'currency_cost':'unknown','wall_time':'unknown'}),
        'prime_mmgbsa': Tool('prime_mmgbsa',input_contract={'required':['poseviewer_complex','confirmed_protocol']},
                            output_contract={'format':'Maestro/CSV','fields':['r_psp_MMGBSA_dG_Bind']},
                            estimated_cost={'relative_units':50,'currency_cost':'unknown','wall_time':'unknown'}),
        'qikprop': Tool('qikprop',input_contract={'required':['prepared_ligand','confirmed_protocol']},
                        output_contract={'format':'Maestro/CSV','fields':['r_qp_*']},
                        estimated_cost={'relative_units':5,'currency_cost':'unknown','wall_time':'unknown'}),
        'desmond': Tool('desmond',input_contract={'required':['CMS','MD configuration','confirmed_protocol']},
                        output_contract={'format':'trajectory_and_analysis'},reason='reserved_not_implemented'),
    }
