"""Реальні підрахунки й локальні PDF на синтетичних даних; без мережі."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from research_metrics import ancestry, coverage, load, metrics, union_size
from build_family_pdf import NATURES, build, local_file, web_url
from validate_registry import ALIASES, FILES, Validator
from affected_records import affected


class MetricsTests(unittest.TestCase):
    def setUp(self):
        self.rows = load(ROOT / 'examples/synthetic')

    def test_working_bridge_and_candidate_are_not_supported_ancestors(self):
        rows = self.rows
        rows['links'][0]['relationship_nature'] = 'biological'
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
            return {'id': i, 'kind': 'parent_child', 'status': 'supported', 'relationship_nature': 'biological',
                    'roles': {'child': child, 'parent': parent}}
        links = [edge('a', 'P1', 'P2'), edge('b', 'P1', 'P3'), edge('c', 'P2', 'P4'), edge('d', 'P3', 'P4')]
        tree = ancestry(self.rows['people'], links, 'P1')
        self.assertEqual(tree['ancestor_ids'], ['P2', 'P3', 'P4'])
        with self.assertRaisesRegex(ValueError, 'Цикл'):
            ancestry(self.rows['people'], links + [edge('e', 'P4', 'P1')], 'P1')
        self.rows['people'][1]['merged_into'] = 'P3'
        with self.assertRaisesRegex(ValueError, 'неактивну'):
            ancestry(self.rows['people'], links, 'P1')

    def test_nature_controls_entire_older_line_without_hiding_context(self):
        bridge = self.rows['links'][0]
        older = dict(bridge, id='L3', status='supported', relationship_nature='biological',
                     person_ids=['P2', 'P3'], roles={'child': 'P2', 'parent': 'P3'})
        for nature in (*NATURES, None):
            with self.subTest(nature=nature):
                if nature is None:
                    bridge.pop('relationship_nature', None)
                else:
                    bridge['relationship_nature'] = nature
                tree = ancestry(self.rows['people'], [bridge, older], 'P1')
                family = nature in {'biological', 'adoptive'}
                self.assertEqual(tree['ancestor_ids'], ['P2', 'P3'] if family else [])
                self.assertEqual(tree['working_only_ancestor_ids'], tree['ancestor_ids'])
                self.assertEqual(tree['depth_including_working'], 2 if family else 0)
                self.assertEqual(tree['supported_ancestor_ids'], [])
                self.assertEqual(tree['depth_supported_only'], 0)
                self.assertEqual(tree['biological_ancestor_ids'], ['P2', 'P3'] if nature == 'biological' else [])
                self.assertEqual(tree['adoptive_only_ancestor_ids'], ['P2', 'P3'] if nature == 'adoptive' else [])
                self.assertEqual(tree['context_only_person_ids'], [] if family else ['P2', 'P3'])
                self.assertEqual(tree['link_ids'], ['L1', 'L3'])
                self.assertEqual(tree['family_link_ids'], ['L1', 'L3'] if family else [])
                supported = ancestry(self.rows['people'], [dict(bridge, status='supported'), older], 'P1')
                self.assertEqual(supported['supported_ancestor_ids'], tree['ancestor_ids'])
                self.assertEqual(supported['depth_supported_only'], 2 if family else 0)

    def test_mixed_paths_do_not_double_count_or_erase_biological_route(self):
        def edge(i, child, parent, nature):
            return dict(id=i, kind='parent_child', status='supported', relationship_nature=nature,
                        roles={'child': child, 'parent': parent})
        links = [edge('a', 'P1', 'P2', 'adoptive'), edge('b', 'P1', 'P3', 'biological'),
                 edge('c', 'P2', 'P4', 'biological'), edge('d', 'P3', 'P4', 'biological'),
                 edge('e', 'P1', 'P5', 'household'), edge('f', 'P5', 'P4', 'biological')]
        tree = ancestry(self.rows['people'], links, 'P1')
        self.assertEqual(tree['ancestor_ids'], ['P2', 'P3', 'P4'])
        self.assertEqual(tree['biological_ancestor_ids'], ['P3', 'P4'])
        self.assertEqual(tree['adoptive_only_ancestor_ids'], ['P2'])
        self.assertEqual(tree['context_only_person_ids'], ['P5'])
        self.assertEqual(tree['family_link_ids'], ['a', 'b', 'c', 'd'])
        self.assertEqual(tree['depth_supported_only'], 2)

    def test_json_and_jsonl_bom_match_plain_input_in_loader_and_cli(self):
        expected = metrics(*(self.rows[k] for k in ('people', 'links', 'sources', 'searches')), 'P1')
        for names in ([], ['people.json'], ['searches.jsonl'], list(FILES.values())):
            with self.subTest(names=names), tempfile.TemporaryDirectory() as temp:
                root = Path(temp) / 'research'
                shutil.copytree(ROOT / 'examples/synthetic', root)
                for name in names:
                    path = root / 'data' / name
                    path.write_bytes(b'\xef\xbb\xbf' + path.read_bytes())
                before = {p.name: p.read_bytes() for p in (root / 'data').iterdir()}
                self.assertEqual(load(root), self.rows)
                result = subprocess.run([sys.executable, str(ROOT / 'tools/research_metrics.py'), str(root), 'P1'],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout), expected)
                self.assertEqual(before, {p.name: p.read_bytes() for p in (root / 'data').iterdir()})

    def test_loader_rejects_conflicting_aliases(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'research'
            shutil.copytree(ROOT / 'examples/synthetic', root)
            links = self.rows['links']
            links[0]['parentage_type'] = 'biological'
            (root / 'data/links.json').write_text(json.dumps(links))
            with self.assertRaisesRegex(ValueError, 'структурні'):
                load(root)

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

    def test_all_relationship_natures_visible_with_older_line(self):
        from pypdf import PdfReader
        links = load(self.root)['links']
        original = copy.deepcopy(links[0])
        older = dict(original, id='L3', status='supported', relationship_nature='biological',
                     person_ids=['P2', 'P3'], roles={'child': 'P2', 'parent': 'P3'})
        for nature, label in NATURES.items():
            with self.subTest(nature=nature):
                links[0] = dict(original, relationship_nature=nature)
                (self.root / 'data/links.json').write_text(json.dumps(links + [older], ensure_ascii=False))
                pdf = build(self.root, 'family_report.json', 'exports/nature-' + nature, FONT)
                text = ' '.join(' '.join(page.extract_text() for page in PdfReader(pdf).pages).split())
                self.assertIn('Природа зв’язку: ' + label, text)
                self.assertIn('Природа зв’язку: Біологічний', text)
                self.assertIn('Мавра', text)  # Старша лінія лишається видимою й за контекстним містком.
                stats = json.loads((pdf.parent / 'metrics.json').read_text())
                family = nature in {'biological', 'adoptive'}
                self.assertEqual(stats['ancestors_including_working'], 2 if family else 0)
                self.assertEqual(stats['ancestry']['depth_including_working'], 2 if family else 0)
                self.assertEqual(text.count('Контекстний перехід:'), 0 if family else 2)

    def test_supported_aliases_and_bom_preserve_files_and_record_hashes(self):
        from pypdf import PdfReader
        for encoding in ('utf-8', 'utf-8-sig'):
            with self.subTest(encoding=encoding):
                for kind, aliases in ALIASES.items():
                    path = self.root / 'data' / FILES[kind]
                    plain = path.read_text(encoding='utf-8-sig')
                    rows = [json.loads(line) for line in plain.splitlines() if line.strip()] if path.suffix == '.jsonl' else json.loads(plain)
                    for row in rows:
                        for old, new in aliases.items():
                            if new in row:
                                row[old] = row.pop(new)
                    content = '\n'.join(json.dumps(row, ensure_ascii=False) for row in rows) if path.suffix == '.jsonl' else json.dumps(rows, ensure_ascii=False)
                    path.write_text(content + '\n', encoding=encoding)
                # Усі JSON/JSONL, включно з people та редакційним планом.
                for name in FILES.values():
                    path = self.root / 'data' / name
                    path.write_text(path.read_text(encoding='utf-8-sig'), encoding=encoding)
                plan = self.root / 'family_report.json'
                plan.write_text(plan.read_text(encoding='utf-8-sig'), encoding=encoding)
                validator = Validator(self.root)
                self.assertEqual(validator.run(), 0, validator.issues)
                self.assertTrue(any(issue['code'] == 'alias' for issue in validator.issues))
                before = {p.name: p.read_bytes() for p in (self.root / 'data').iterdir()}
                pdf = build(self.root, 'family_report.json', 'exports/aliases-' + encoding, FONT)
                text = ' '.join(' '.join(page.extract_text() for page in PdfReader(pdf).pages).split())
                self.assertIn('Природа зв’язку: Природу не встановлено', text)
                self.assertIn('Перевірено лише два вигадані акти', text)
                manifest = json.loads((pdf.parent / 'manifest.json').read_text())
                for ref in manifest['record_refs']:
                    record = validator.index[ref['type']][ref['id']]
                    expected = hashlib.sha256(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
                    self.assertEqual(ref['sha256'], expected)
                editions = affected(self.root, ['L2'])['editions']
                edition = next(e for e in editions if e['path'] == str((pdf.parent / 'manifest.json').relative_to(self.root.resolve())))
                self.assertEqual(edition['changed_records'], [])
                self.assertEqual(edition['changed_files'], [])
                self.assertEqual(before, {p.name: p.read_bytes() for p in (self.root / 'data').iterdir()})
        links_path = self.root / 'data/links.json'
        links = json.loads(links_path.read_text(encoding='utf-8-sig'))
        links[0]['kinship_confidence']['reason'] += '; нова перевірка'
        links_path.write_text(json.dumps(links, ensure_ascii=False), encoding='utf-8-sig')
        edition = next(e for e in affected(self.root, ['L2'])['editions'] if e['path'] == 'exports/aliases-utf-8-sig/manifest.json')
        self.assertEqual(edition['changed_records'], ['L:L1'])

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
