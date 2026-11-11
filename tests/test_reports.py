"""Реальні підрахунки й локальні PDF на синтетичних даних; без мережі."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from research_metrics import ancestry, coverage, load, metrics, union_size
from build_family_pdf import build, local_file, web_url


class MetricsTests(unittest.TestCase):
    def setUp(self):
        self.rows = load(ROOT / 'examples/synthetic')

    def test_working_bridge_and_candidate_are_not_supported_ancestors(self):
        rows = self.rows
        result = metrics(*(rows[k] for k in ('people', 'links', 'sources', 'searches')), 'P1')
        self.assertEqual(result['people_cards'], 5)
        self.assertEqual(result['ancestors_including_working'], 1)
        self.assertEqual(result['ancestors_supported_only'], 0)
        self.assertEqual(result['ancestry']['depth_including_working'], 1)
        link = copy.deepcopy(rows['links'][0])
        link.update(id='L3', status='supported', person_ids=['P2', 'P3'], roles={'child': 'P2', 'parent': 'P3'})
        tree = ancestry(rows['people'], rows['links'] + [link], 'P1')
        self.assertEqual(tree['working_only_ancestor_ids'], ['P2', 'P3'])
        self.assertEqual(tree['depth_supported_only'], 0)
        self.assertEqual(tree['depth_including_working'], 2)

    def test_shared_ancestor_not_counted_twice_and_cycle_rejected(self):
        def edge(i, child, parent):
            return {'id': i, 'kind': 'parent_child', 'status': 'supported', 'roles': {'child': child, 'parent': parent}}
        links = [edge('a', 'P1', 'P2'), edge('b', 'P1', 'P3'), edge('c', 'P2', 'P4'), edge('d', 'P3', 'P4')]
        tree = ancestry(self.rows['people'], links, 'P1')
        self.assertEqual(tree['ancestor_ids'], ['P2', 'P3', 'P4'])
        with self.assertRaisesRegex(ValueError, 'Цикл'):
            ancestry(self.rows['people'], links + [edge('e', 'P4', 'P1')], 'P1')
        self.rows['people'][1]['merged_into'] = 'P3'
        with self.assertRaisesRegex(ValueError, 'неактивну'):
            ancestry(self.rows['people'], links, 'P1')

    def test_overlap_gaps_ocr_and_units(self):
        def row(ident, a, b, unit='frame', method='field_review', **extra):
            return dict(id=ident, document_key='book-A', gaps=[], coverage_parts=[dict(unit=unit, method=method, **{'from': a, 'to': b})], **extra)
        rows = [row('A', 1, 3), row('B', 3, 5), row('C', 1, 2, method='ocr'), row('D', 1, 2, unit='page')]
        rows.append(dict(row('E', 1, 100), gaps=['невідомий пропуск']))
        rows.append(row('F', 1, 999, access_status='catalog_only'))
        rows.append(row('G', 1, 999, method='downloaded'))
        result = coverage(rows)
        self.assertEqual(result['known_units'], {'visual': {'frame': 5, 'page': 2}, 'ocr': {'frame': 2}})
        self.assertEqual({r['id'] for r in result['excluded']}, {'E', 'F', 'G'})
        self.assertEqual(union_size([(1, 10**9), (10, 20)]), 10**9)

    def test_unknown_empty_and_invalid_coverage_not_silently_zero(self):
        self.assertEqual(coverage([])['known_units']['visual'], {})
        bad = {'id': 'bad', 'document_key': 'A', 'gaps': [], 'coverage_parts': [{'from': True, 'to': 2, 'unit': 'frame', 'method': 'field_review'}]}
        self.assertEqual(coverage([bad])['excluded'][0]['id'], 'bad')

    def test_source_urls_cannot_be_executable_or_credentials(self):
        for value in ('javascript:alert(1)', 'file:///private/data', 'https://u:secret@example.org', 'https://example.org/\n'):
            with self.assertRaises(ValueError):
                web_url(value)
        self.assertEqual(web_url('https://example.org/record?frame=2'), 'https://example.org/record?frame=2')


FONT = next((Path(p) for p in [os.environ.get('KIT_TEST_FONT', ''),
             '/System/Library/Fonts/Supplemental/Arial.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']
             if p and Path(p).is_file()), None)
PDF_READY = bool(FONT and importlib.util.find_spec('reportlab') and importlib.util.find_spec('pypdf'))


@unittest.skipUnless(PDF_READY, 'Потрібні reportlab, pypdf і TTF-шрифт із кирилицею (KIT_TEST_FONT).')
class PDFTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'research'
        shutil.copytree(ROOT / 'examples/synthetic', self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_pdf_text_internal_external_links_and_manifest(self):
        from pypdf import PdfReader
        sources_path = self.root / 'data/sources.json'
        sources = json.loads(sources_path.read_text())
        sources[1]['digital_locator'] = {'viewer_url': 'https://example.org/synthetic?frame=2'}
        sources_path.write_text(json.dumps(sources, ensure_ascii=False))
        before = {str(p.relative_to(self.root)): p.read_bytes() for p in (self.root / 'data').iterdir()}
        pdf = build(self.root, 'family_report.json', 'exports/test-report', FONT)
        reader = PdfReader(pdf)
        text = '\n'.join(page.extract_text() for page in reader.pages)
        self.assertIn('Северин', text)
        self.assertIn('Суперечності', text)
        self.assertIn('Робочий зв’язок', text)
        self.assertIn('Не включено до підрахунку', text)
        annotations = [ref.get_object() for page in reader.pages for ref in page.get('/Annots', [])]
        self.assertTrue(any('/Dest' in a for a in annotations))
        self.assertTrue(any(a.get('/A', {}).get('/URI') == 'https://example.org/synthetic?frame=2' for a in annotations))
        manifest = json.loads((pdf.parent / 'manifest.json').read_text())
        self.assertEqual(manifest['local_status'], 'draft')
        self.assertEqual(manifest['deployed_status'], 'not_deployed')
        for entry in manifest['input_files'] + manifest['files']:
            self.assertEqual(hashlib.sha256((self.root / entry['path']).read_bytes()).hexdigest(), entry['sha256'])
        self.assertEqual(before, {str(p.relative_to(self.root)): p.read_bytes() for p in (self.root / 'data').iterdir()})
        with self.assertRaises(ValueError):
            build(self.root, 'family_report.json', 'exports/test-report', FONT)

    def test_fail_closed_on_unreviewed_audience_unknown_id_and_image(self):
        plan_path = self.root / 'family_report.json'
        original = json.loads(plan_path.read_text())
        for change in ({'audience': 'public'}, {'root_person_id': 'missing'},
                       {'documents': [{'source_id': 'S2', 'image_paths': ['../../private.png']}]},
                       {'sections': [{'title': 'Без доказів', 'text': 'Твердження'}]}):
            plan = dict(original, **change)
            plan_path.write_text(json.dumps(plan, ensure_ascii=False))
            with self.assertRaises((ValueError, KeyError)):
                build(self.root, 'family_report.json', 'exports/rejected', FONT)
            self.assertFalse((self.root / 'exports/rejected').exists())
        with self.assertRaises(ValueError):
            local_file(self.root, '../private.txt')
        target = self.root / 'shortcut.json'
        target.symlink_to(plan_path)
        with self.assertRaises(ValueError):
            local_file(self.root, 'shortcut.json')


if __name__ == '__main__':
    unittest.main()
