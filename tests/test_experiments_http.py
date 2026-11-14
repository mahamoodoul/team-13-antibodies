"""HTTP and browser regression checks for the scientific workspace."""
import io
import hashlib
import json
import time
import unittest
import urllib.error
import urllib.request
import zipfile

from tests import test_web
from fourwells.experiments import Store, work
from fourwells.targets import resolve_reference_ab


class WorkspaceServer(test_web.ServerCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.store = Store(cls.root)
        cls.ident = cls.store.create({'mode': 'demo', 'question': 'HTTP demo', 'candidates': 3})
        work(cls.root, cls.ident)
        # An imported saved PDB exercises artifact routing without claiming any
        # official validation or biological activity for the fixture.
        (cls.root / 'test.pdb').write_text(
            'ATOM      1  CA  ALA T   1       0.000   0.000   0.000  1.00 90.00           C\n'
            'ATOM      2  CA  ALA H   2       3.000   0.000   0.000  1.00 90.00           C\n')
        row = {'design_id': 'import-fixture', 'sequence': resolve_reference_ab(None).vh,
               'format': 'scfv', 'track': 'optimisation', 'structures': [{'path': 'test.pdb'}]}
        (cls.root / 'saved.jsonl').write_text(json.dumps(row) + '\n')
        cls.import_ident = cls.store.create({'mode': 'import', 'input': 'saved.jsonl',
                                            'question': 'Imported saved structure'})
        work(cls.root, cls.import_ident)

    def post(self, payload, origin=None):
        headers = {'Content-Type': 'application/json'}
        if origin:
            headers['Origin'] = origin
        request = urllib.request.Request(self.base + '/api/experiments',
                                         json.dumps(payload).encode(), headers=headers, method='POST')
        return urllib.request.urlopen(request, timeout=10)


class TestWorkspaceHttp(WorkspaceServer):
    def test_list_and_detail_expose_unknown_evidence(self):
        _, data = self.json('/api/experiments')
        self.assertTrue({self.ident, self.import_ident} <= {j['id'] for j in data['iterations']})
        _, j = self.json('/api/experiments/' + self.ident)
        self.assertEqual(j['status'], 'complete')
        self.assertEqual(j['result']['counts']['shortlisted'], 0)
        self.assertTrue(all(c['objectives']['stability']['status'] == 'unknown'
                            for c in j['result']['candidates']))

    def test_export_has_no_demo_sequences(self):
        with urllib.request.urlopen(self.base + '/api/experiments/' + self.ident + '/export') as response:
            self.assertEqual(response.headers['Content-Type'], 'application/zip')
            with zipfile.ZipFile(io.BytesIO(response.read())) as z:
                self.assertEqual(z.read('final_sequences.fasta'), b'')
                self.assertIn('manifest.json', z.namelist())
                self.assertIn('evidence.json', z.namelist())
                for artifact in json.loads(z.read('manifest.json')):
                    self.assertEqual(hashlib.sha256(z.read(artifact['path'])).hexdigest(), artifact['sha256'])

    def test_only_saved_structure_can_be_loaded(self):
        j = self.store.get(self.import_ident)
        name = j['result']['candidates'][0]['structures'][0]['path'].split('/')[-1]
        _, data = self.json('/api/experiments/' + self.import_ident + '/structure/' + name)
        self.assertEqual({a['chain'] for a in data['atoms']}, {'T', 'H'})
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.get('/api/experiments/' + self.import_ident + '/structure/reference.json')
        self.assertEqual(cm.exception.code, 404)

    def test_cross_origin_and_browser_model_commands_are_rejected(self):
        for payload, origin, expected in [
                ({'question': 'Not local'}, 'https://untrusted.invalid', 403),
                ({'question': 'No model execution', 'mode': 'live', 'profile': 'x.json'}, None, 400),
                ({'question': 'No import paths', 'mode': 'import', 'input': 'private.jsonl'}, None, 400),
                ({'question': 'Invalid count', 'candidates': -1}, None, 400),
                ([], None, 400)]:
            with self.subTest(payload=payload):
                with self.assertRaises(urllib.error.HTTPError) as cm:
                    self.post(payload, origin)
                self.assertEqual(cm.exception.code, expected)

    def test_browser_job_completes_independently_and_retains_parent(self):
        with self.post({'question': 'Detached HTTP job', 'parent': self.ident, 'mode': 'demo',
                        'candidates': 2}, self.base) as response:
            self.assertEqual(response.status, 202)
            j = json.load(response)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            _, j = self.json('/api/experiments/' + j['id'])
            if j['status'] not in ('queued', 'running'):
                break
            time.sleep(.05)
        self.assertEqual(j['status'], 'complete', j.get('error'))
        self.assertEqual(j['spec']['parent'], self.ident)
        self.assertEqual(j['result']['counts']['shortlisted'], 0)

    def test_api_does_not_expose_private_project_files(self):
        for path in ['/api/experiments/not-a-run', '/api/experiments/' + self.ident + '/spec.json',
                     '/api/experiments/' + self.ident + '/logs/worker.log']:
            with self.subTest(path=path):
                with self.assertRaises(urllib.error.HTTPError) as cm:
                    self.get(path)
                self.assertEqual(cm.exception.code, 404)


@unittest.skipUnless(test_web.CHROME.exists(), 'Chrome unavailable')
class TestWorkspaceBrowser(WorkspaceServer):
    _probe = test_web.TestInBrowser._probe

    def test_detail_opens_candidate_and_filter_works(self):
        result = self._probe('''<script>
setTimeout(function(){
  var rows=document.querySelectorAll('[data-candidate]');
  var n=rows.length;
  if(n) rows[0].click();
  var detail=document.getElementById('candidate-detail');
  var q=document.getElementById('candidate-search');
  q.value='not-a-candidate';q.dispatchEvent(new Event('input'));
  document.title='R rows='+n+'|detail='+(detail.textContent.indexOf('unknown')>=0)
    +'|filtered='+document.querySelectorAll('[data-candidate]').length;
},2000);</script>''', '/experiments/' + self.ident)
        self.assertEqual(result.get('rows'), '3')
        self.assertEqual(result.get('detail'), 'true')
        self.assertEqual(result.get('filtered'), '0')

    def test_polling_preserves_open_experiment_form(self):
        result = self._probe('''<script>
setTimeout(function(){
 document.getElementById('new-experiment').open=true;
 document.getElementById('question').value='Keep this question while polling';
},1000);
setTimeout(function(){
 document.title='R preserved='+(document.getElementById('question').value==='Keep this question while polling');
},4500);</script>''', '/experiments')
        self.assertEqual(result.get('preserved'), 'true')

    def test_returning_from_legacy_route_redraws_same_iteration(self):
        script = '''<script>
setTimeout(function(){
 document.querySelector('a[data-nav="/runs"]').click();
},1000);
setTimeout(function(){
 var a=document.createElement('a');a.href=RETURN_PATH;document.body.appendChild(a);a.click();
},2000);
setTimeout(function(){
 document.title='R rows='+document.querySelectorAll('[data-candidate]').length;
},3500);</script>'''.replace('RETURN_PATH', json.dumps('/experiments/' + self.ident))
        result = self._probe(script, '/experiments/' + self.ident)
        self.assertEqual(result.get('rows'), '3')

    def test_comparison_and_structure_viewer_render(self):
        result = self._probe('''<script>
setTimeout(function(){
  var b=document.querySelector('[data-candidate]');if(b)b.click();
},1000);
setTimeout(function(){
  document.title='R canvas='+(document.querySelectorAll('.molecule canvas').length)
    +'|chains='+document.querySelectorAll('.chain-controls input').length;
},2500);</script>''', '/experiments/' + self.import_ident)
        self.assertEqual(result.get('canvas'), '1')
        self.assertEqual(result.get('chains'), '2')
        result = self._probe('''<script>
setTimeout(function(){
 document.title='R selects='+document.querySelectorAll('select').length
   +'|comparison='+(document.getElementById('view').textContent.indexOf('Objective coverage')>=0);
},2000);</script>''', '/compare')
        self.assertEqual(result.get('selects'), '2')
        self.assertEqual(result.get('comparison'), 'true')


if __name__ == '__main__':
    unittest.main()
