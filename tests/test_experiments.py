"""Scientific invariants and durable job integration; tool fixtures are not models."""
import copy
import io
import json
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

from fourwells.evidence import objective, dominates, rank_candidates, sequence_diversity
from fourwells.experiments import Store, work, start, export_bundle, inventory
from fourwells.targets import resolve_reference_ab
from fourwells.structures import atoms, compare_interface


def evidence(value=10, method='test-assay', unit='nM', direction='min'):
    return dict(value=value, method=method, unit=unit, direction=direction,
                kind='measurement', version='1', source='test fixture', reference_value=20)


def candidate(ident, value=10, eligible=True):
    return dict(design_id=ident, sequence='EVQLVESGGGLVQPGGSLRLSC', cdrh3=ident,
                eligible=eligible, stub=False, validation={'status':'pass' if eligible else 'not_run'},
                objectives={'binding':objective(evidence(value)), 'epitope':objective(None),
                            'stability':objective(None)})


class TestEvidence(unittest.TestCase):
    def test_missing_is_not_zero_and_nonfinite_is_unknown(self):
        self.assertEqual(objective(None)['status'], 'unknown')
        self.assertEqual(objective(evidence(float('nan')))['status'], 'unknown')
        self.assertEqual(objective(evidence(True))['status'], 'unknown')

    def test_structural_confidence_cannot_be_thermal_stability(self):
        self.assertEqual(objective(evidence(.99, method='ipTM'), 'stability')['status'], 'unknown')

    def test_metadata_must_identify_a_method_as_text(self):
        self.assertEqual(objective(evidence(method={'name': 'SPR'}))['status'], 'unknown')

    def test_diversity_uses_matching_sequence_scopes(self):
        a, b = candidate('AAA'), candidate('BBB')
        b['cdrh3'] = None
        pair = sequence_diversity([a,b])[0]
        self.assertEqual(pair['scope'], 'full construct')
        self.assertEqual(pair['identity'], 1)

    def test_dominance_preserves_units_and_coverage(self):
        a, b = candidate('AAA',1),candidate('BBB',10)
        self.assertTrue(dominates(a,b))
        b['objectives']['binding']['unit']='M'
        self.assertFalse(dominates(a,b))
        b['objectives']['binding']['unit']='nM'
        b['objectives']['stability']=objective(evidence(60,unit='C',direction='max'))
        self.assertFalse(dominates(a,b))

    def test_failed_or_unvalidated_candidate_never_ranks(self):
        rows=[candidate('AAA',100),candidate('BBB',.01,False)]
        rank_candidates(rows)
        self.assertTrue(rows[0]['selected'])
        self.assertIsNone(rows[1]['rank'])

    def test_pareto_order_and_cap_are_deterministic(self):
        rows=[candidate('SEQ'+str(i),i+1) for i in range(30)]
        a=rank_candidates(copy.deepcopy(rows));b=rank_candidates(list(reversed(copy.deepcopy(rows))))
        self.assertEqual(sum(c['selected'] for c in a),20)
        self.assertEqual({c['design_id']:c['rank'] for c in a},{c['design_id']:c['rank'] for c in b})
        self.assertEqual(a[0]['pareto_front'],1)


class TestExperiments(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.store=Store(self.root)

    def fixture(self, passed=True, track='optimisation', code=0):
        # Adapter output protocol fixture. No official tool is impersonated in product data.
        script=self.root/'fixture.py'
        script.write_text('import json,sys\nfrom pathlib import Path\n'+
            f'Path(sys.argv[2]).write_text(json.dumps({{"passed":{passed!r},"track":{track!r},"numbering_confidence":0.9,"failed_rules":[]}}))\n'+f'sys.exit({code})\n')
        (self.root/'tutorial.txt').write_text('Synthetic test adapter, no biological validity')
        profile={'documentation':'tutorial.txt','verified_against_installed_docs':True,
                 'stages':{'validation':{'argv':[sys.executable,str(script),'{input}','{output}'],'version':'test-fixture'}}}
        (self.root/'profile.json').write_text(json.dumps(profile))
        ref=resolve_reference_ab(None)
        seq=ref.vh.replace(ref.cdrh3,'WQATGFYQMD')
        row={'design_id':'test-design','sequence':seq,'format':'scfv','track':'optimisation',
             'generator':'test-fixture','evidence':{'binding':evidence()}}
        (self.root/'input.jsonl').write_text(json.dumps(row)+'\n')
        return {'mode':'import','input':'input.jsonl','profile':'profile.json','question':'Fixture test'}

    def run_spec(self,spec):
        ident=self.store.create(spec);work(self.root,ident);return self.store.get(ident)

    def test_missing_authority_keeps_candidate_visible_but_no_submission(self):
        spec=self.fixture();spec.pop('profile')
        j=self.run_spec(spec)
        self.assertEqual(j['status'],'complete')
        self.assertEqual(j['result']['counts']['generated'],1)
        self.assertEqual(j['result']['counts']['shortlisted'],0)
        self.assertEqual(j['result']['candidates'][0]['objectives']['stability']['status'],'unknown')

    def test_traceable_validated_export_and_immutable_retry(self):
        j=self.run_spec(self.fixture())
        self.assertEqual(j['status'],'complete',j['error'])
        self.assertEqual(j['result']['counts']['shortlisted'],1)
        with zipfile.ZipFile(io.BytesIO(export_bundle(self.root,j['id']))) as z:
            self.assertIn('test-design',z.read('final_sequences.fasta').decode())
            self.assertIn('reference.json',z.namelist());self.assertIn('manifest.json',z.namelist())
            self.assertIn('logs/validation-test-design.stdout',z.namelist())
        with self.assertRaises(ValueError):work(self.root,j['id'])
        new=self.store.create({**j['spec'],'parent':j['id']})
        self.assertNotEqual(new,j['id'])

    def test_authority_fail_cannot_be_reclassified_or_exported(self):
        for passed,track in [(False,'optimisation'),(True,'de_novo')]:
            with self.subTest(passed=passed,track=track):
                j=self.run_spec(self.fixture(passed,track))
                self.assertEqual(j['result']['counts']['shortlisted'],0)
                self.assertEqual(j['result']['candidates'][0]['validation']['status'],'fail')

    def test_success_json_does_not_override_nonzero_exit(self):
        j=self.run_spec(self.fixture(code=1))
        self.assertEqual(j['status'],'complete')
        self.assertEqual(j['result']['counts']['shortlisted'],0)
        self.assertIn('exited 1', ' '.join(j['result']['candidates'][0]['validation']['failed_rules']))
        self.assertTrue((self.store.directory(j['id'])/'logs/validation-test-design.command.json').exists())

    def test_live_without_verified_documentation_is_blocked(self):
        (self.root/'profile.json').write_text('{}')
        j=self.run_spec({'mode':'live','profile':'profile.json','question':'Live prerequisites'})
        self.assertEqual(j['status'],'blocked')
        self.assertIn('documentation',j['error'])

    def test_duplicate_ids_fail_loudly(self):
        spec=self.fixture();p=self.root/'input.jsonl';p.write_text(p.read_text()*2)
        j=self.run_spec(spec)
        self.assertEqual(j['status'],'failed');self.assertIn('Duplicate',j['error'])

    def test_detached_worker_finishes_without_a_server(self):
        j=start(self.root,{'mode':'demo','question':'Detached worker','candidates':3})
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            j=self.store.get(j['id'])
            if j['status'] not in ('queued','running'):break
            time.sleep(.05)
        self.assertEqual(j['status'],'complete',j)
        self.assertEqual(j['result']['counts']['shortlisted'],0)
        self.assertTrue(all(c['stub'] for c in j['result']['candidates']))

    def test_invalid_parent_and_traversal_rejected(self):
        with self.assertRaises(ValueError):self.store.directory('../keys')
        with self.assertRaises(ValueError):self.store.create({'question':'x','parent':'missing'})

    def test_invalid_second_candidate_preserves_first_candidate_evidence(self):
        spec=self.fixture();p=self.root/'input.jsonl'
        bad=json.loads(p.read_text());bad.update(design_id='bad', cdrh3='THISISNOTINTHESEQUENCE')
        p.write_text(p.read_text()+json.dumps(bad)+'\n')
        j=self.run_spec(spec)
        self.assertEqual(j['status'],'failed')
        self.assertIn('CDRH3',j['error'])
        self.assertEqual(len(j['partial_result']['candidates']),1)
        self.assertNotIn('result',j)

    def test_nonfinite_raw_prediction_records_failure_instead_of_hanging(self):
        spec=self.fixture();p=self.root/'input.jsonl';row=json.loads(p.read_text())
        row['predictions']=[{'iptm':float('nan')}]
        p.write_text(json.dumps(row)+'\n')
        j=self.run_spec(spec)
        self.assertEqual(j['status'],'failed')
        self.assertIn('JSON compliant',j['error'])

    def live_fixture(self, missing=False):
        self.fixture()
        source=self.root/'input.jsonl'
        stub=json.loads(source.read_text());stub.update(design_id='stub-design',is_stub=True)
        source.write_text(source.read_text()+json.dumps(stub)+'\n')
        profile=json.loads((self.root/'profile.json').read_text())
        predictions={} if missing else {'test-design':{
            'evidence': {'epitope':evidence(.8, method='contact-fixture',unit='fraction',direction='max')},
            'predictions':[{'model':'synthetic-fixture','version':'1','iptm':.8}],
            'model_disagreement':['Synthetic disagreement retained'],
            'developability':{'method':'synthetic-solubility','value':.5},
            'limitations':['Fixture only']}}
        script=self.root/'stages.py'
        script.write_text('import json,sys,shutil\nfrom pathlib import Path\n'
            'stage,src,out=sys.argv[1:]\n'
            'if stage=="design": shutil.copyfile(src,out)\n'
            'else:\n'
            ' rows=json.loads(Path(src).read_text())\n'
            ' assert [r["design_id"] for r in rows]==["test-design"]\n'
            f' if stage=="refold_score": Path(out).write_text(json.dumps({predictions!r}))\n')
        for stage in ('design','refold_prepare','predict','refold_score'):
            profile['stages'][stage]={'version':'synthetic-fixture','argv':[
                sys.executable,str(script),stage,str(source) if stage=='design' else '{input}','{output}']}
        (self.root/'profile.json').write_text(json.dumps(profile))
        return {'mode':'live','profile':'profile.json','question':'Synthetic adapter protocol integration'}

    def test_live_protocol_folds_only_eligible_and_preserves_predictions(self):
        j=self.run_spec(self.live_fixture())
        self.assertEqual(j['status'],'complete',j['error'])
        self.assertEqual(j['result']['counts']['shortlisted'],1)
        c=j['result']['candidates'][0]
        self.assertEqual(c['model_disagreement'],['Synthetic disagreement retained'])
        self.assertEqual(c['developability']['method'],'synthetic-solubility')
        self.assertEqual(c['objectives']['stability']['status'],'unknown')
        stages=[e['stage'] for e in j['events'] if e['status']=='complete']
        for stage in ('design','refold_prepare','predict','refold_score'):
            self.assertIn(stage,stages)

    def test_missing_live_prediction_is_not_a_completed_scientific_run(self):
        j=self.run_spec(self.live_fixture(missing=True))
        self.assertEqual(j['status'],'failed')
        self.assertIn('missing eligible candidates',j['error'])
        self.assertEqual(len(j['partial_result']['candidates']),2)


class TestInterfaces(unittest.TestCase):
    def test_contact_recovery_uses_explicit_chain_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'complex.pdb'
            p.write_text('ATOM      1  CA  ALA T   1       0.000   0.000   0.000  1.00 90.00           C\n'
                         'ATOM      2  CA  ALA B   2       3.000   0.000   0.000  1.00 90.00           C\n')
            self.assertEqual(len(atoms(p)),2)
            ev=compare_interface(p,p,['T'],['B'],['T'],['B'])
            self.assertEqual(ev['value'],1)
            with self.assertRaises(ValueError):compare_interface(p,p,['X'],['B'],['T'],['B'])

if __name__=='__main__':unittest.main()
