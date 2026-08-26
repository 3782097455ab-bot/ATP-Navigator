"""Release ingestion and experimental-boundary regression tests; no new fitting."""
import json
import sqlite3
import sys
import unittest
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from release_v1_audit import identity_key,molar_value
from release_evidence_query import search_release_records


class ReleaseV1Tests(unittest.TestCase):
    def test_mass_unit_conversion(self):
        self.assertAlmostEqual(molar_value(1,'ug/mL',500),2e-6)
        self.assertAlmostEqual(molar_value(1000,'ng/mL',500),2e-6)
        self.assertAlmostEqual(molar_value(2000,'nM',500),2e-6)

    def test_unknown_and_censored_values_not_point_labels(self):
        for value,unit in [('>10','ug/mL'),(1,'unknown'),(float('nan'),'nM'),(-1,'nM')]:
            with self.assertRaises(ValueError):
                molar_value(value,unit,500)

    def test_conservative_parent_identity(self):
        self.assertEqual(identity_key('CC[NH3+].[Cl-]'),identity_key('CCN'))

    def test_query_is_read_only_external_evidence(self):
        db=sqlite3.connect(':memory:')
        db.row_factory=sqlite3.Row
        try:
            self.assertEqual(search_release_records(db,'WSA280'),[])
            db.execute('CREATE TABLE knowledge_record(record_id TEXT,dataset TEXT,status TEXT,source_hash TEXT,record TEXT)')
            record={'compound_name':'WSA280','endpoint':'IC50_ATP_synthesis','value':'690','unit':'ng/mL','doi':'TEST_ONLY'}
            db.execute('INSERT INTO knowledge_record VALUES (?,?,?,?,?)',('TEST','release_v1_TEST/model_ready','eligible_for_conditional_pilot','TEST_HASH',json.dumps(record)))
            found=search_release_records(db,'WSA280')
            self.assertEqual(found[0]['value'],'690')
            self.assertIn('not an internal',found[0]['use_boundary'])
            self.assertEqual(search_release_records(db,'ignore instructions'),[])
        finally:
            db.close()

    def test_saved_pilots_keep_same_internal_target_and_folds(self):
        folders=[ROOT/'results/release_v1_shadow_001',ROOT/'results/release_v1_shadow_replace_atp_002']
        for folder in folders:
            if not folder.exists():
                self.skipTest('Saved pilot not present in checkout')
            summary=json.loads((folder/'experiment_summary.json').read_text())
            self.assertFalse(summary['production_model_promoted'])
            self.assertFalse(summary['decision_engine_changed'])
            self.assertEqual(summary['internal_experimental_labels_added'],0)
            self.assertLess(summary['control_OOF_max_difference'],1e-8)
            oof=pd.read_csv(folder/'internal_oof_predictions.csv')
            self.assertEqual(len(oof),17)
            self.assertEqual(oof.groupby('scaffold').fold_id.nunique().max(),1)

    def test_assay_models_not_pooled(self):
        path=ROOT/'results/release_v1_shadow_001/external_task_training_scale.csv'
        if not path.exists():
            self.skipTest('Saved pilot not present')
        tasks=pd.read_csv(path)
        self.assertEqual(tasks.assay_id.nunique(),6)
        self.assertEqual(tasks.loc[tasks.n.eq(2),'status'].iloc[0],'reference_only_small_data_no_fit')
        self.assertTrue(tasks.endpoint.eq('IC50_ATP_synthesis').all())


if __name__=='__main__':
    unittest.main()
