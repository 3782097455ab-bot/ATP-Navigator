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
        'rdkit_library_generation': Tool(
            'rdkit_library_generation',
            input_contract={'format':'versioned IN-2 generator config','required':['parent_id','building_block_library_version','reaction_templates','random_seed']},
            output_contract={'format':'CSV/JSON','fields':['canonical_smiles','inchikey','provenance_hash','qc_status','rejection_reason','library_hash']},
            estimated_cost={'relative_units':1,'currency_cost':'open_source','wall_time':'measured_per_run'},
            protocol_id='in2_reconstructed_derivative_library_v1',
            reason='Deterministic reconstructed library generation; not historical Auto_Enum reproduction'),
        'rdkit': Tool('rdkit', input_contract={'format':'candidate CSV','required':['compound_id','SMILES']},
                      output_contract={'format':'CSV','fields':['canonical_smiles','scaffold','Morgan1024','descriptors','structure_status']},
                      estimated_cost={'relative_units':1,'currency_cost':'unknown','wall_time':'measured_per_job'},
                      protocol_id='rdkit_morgan2_1024_chiral_v1'),
        'vina': Tool('vina', input_contract={'required':['canonical_smiles','frozen_receptor','frozen_box','vina_protocol']},
                     output_contract={'format':'PDBQT/JSON','fields':['vina_affinity','pose_count','pose_qc']},
                     estimated_cost={'relative_units':10,'currency_cost':'open_source','wall_time':'measured_per_job'},
                     protocol_id='vina_7p3w_v1',reason='Open docking route; never named Glide SP/XP'),
        'open_mmgbsa': Tool('open_mmgbsa', input_contract={'required':['reviewed_complex_pose','open_mmgbsa_7p3w_v2','explicit_budget_gate']},
                           output_contract={'format':'CSV/trajectory artifacts','fields':['open_mmgbsa_deltaG','uncertainty','frame_count','qc_status']},
                           estimated_cost={'relative_units':100,'currency_cost':'open_source','wall_time':'measured_per_candidate'},
                           protocol_id='open_mmgbsa_7p3w_v2',reason='Stage-gated WSL physics route; not Prime MM/GBSA'),
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
