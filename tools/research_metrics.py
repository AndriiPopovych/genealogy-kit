#!/usr/bin/env python3
"""Консервативні підрахунки зі зрізу реєстрів, без генеалогічних рішень."""
import argparse
import json
from collections import defaultdict
from pathlib import Path

from validate_registry import Validator

ACCEPTED = {'supported', 'accepted_working'}
FAMILY_NATURES = frozenset({'biological', 'adoptive'})
VISUAL_METHODS = {'field_review', 'image_review', 'full_review'}


def union_size(intervals):
    total = 0
    end = -1
    for start, stop in sorted(intervals):
        total += max(0, stop - max(start, end + 1) + 1)
        end = max(end, stop)
    return total


def ancestry(people, links, root_id):
    """Прийняті зв’язки: родовідні підрахунки окремо від контекстної схеми."""
    active = {p['id'] for p in people if not p.get('merged_into')}
    if root_id not in active:
        raise ValueError('Початкова особа відсутня або об’єднана: ' + root_id)
    parents = defaultdict(list)
    for link in links:
        if link['kind'] == 'parent_child' and link['status'] in ACCEPTED:
            parent, child = link['roles']['parent'], link['roles']['child']
            if parent not in active or child not in active:
                raise ValueError('Прийнятий зв’язок посилається на неактивну особу: ' + link['id'])
            parents[child].append(link)
    memo, visiting = {}, set()

    def walk(child, supported_only, natures):
        key = (child, supported_only, natures)
        if key in visiting:
            raise ValueError('Цикл родоводу біля ' + child)
        if key in memo:
            return memo[key]
        visiting.add(key)
        ancestors, edge_ids, depth = set(), set(), 0
        for edge in parents[child]:
            if supported_only and edge['status'] != 'supported':
                continue
            if natures is not None and edge.get('relationship_nature', 'unspecified') not in natures:
                continue
            parent = edge['roles']['parent']
            older, more_edges, more_depth = walk(parent, supported_only, natures)
            ancestors |= older | {parent}
            edge_ids |= more_edges | {edge['id']}
            depth = max(depth, 1 + more_depth)
        visiting.remove(key)
        memo[key] = ancestors, edge_ids, depth
        return memo[key]

    # Повна схема зберігає небіологічні та невизначені зв’язки разом зі старшими
    # лініями. Її наявність не перетворює їх на предків початкової особи.
    recorded, edges, _ = walk(root_id, False, None)
    all_ids, family_edges, depth = walk(root_id, False, FAMILY_NATURES)
    supported, _, supported_depth = walk(root_id, True, FAMILY_NATURES)
    biological, _, biological_depth = walk(root_id, False, frozenset({'biological'}))
    biological_supported, _, biological_supported_depth = walk(root_id, True, frozenset({'biological'}))
    return {'root_id': root_id, 'ancestor_ids': sorted(all_ids),
            'supported_ancestor_ids': sorted(supported),
            'working_only_ancestor_ids': sorted(all_ids - supported),
            'biological_ancestor_ids': sorted(biological),
            'biological_supported_ancestor_ids': sorted(biological_supported),
            'adoptive_only_ancestor_ids': sorted(all_ids - biological),
            'context_only_person_ids': sorted(recorded - all_ids),
            'family_link_ids': sorted(family_edges),
            'link_ids': sorted(edges), 'depth_including_working': depth,
            'depth_supported_only': supported_depth,
            'biological_depth_including_working': biological_depth,
            'biological_depth_supported_only': biological_supported_depth}


def coverage(searches):
    """Окремі одиниці; текстові прогалини не вгадуються, OCR не є оглядом."""
    groups = defaultdict(list)
    excluded = []
    for row in searches:
        reason = None
        if row.get('access_status') in {'access_blocked', 'not_checked', 'catalog_only'}:
            reason = 'немає виконаного огляду'
        elif not row.get('document_key') or not row.get('coverage_parts'):
            reason = 'немає однозначних координат'
        elif row.get('gaps'):
            reason = 'є прогалини; їх межі потрібно звірити перед підрахунком'
        if reason:
            excluded.append({'id': row['id'], 'reason': reason})
            continue
        pending = []
        for part in row['coverage_parts']:
            start, stop = part.get('from'), part.get('to')
            unit, method = part.get('unit'), part.get('method', row.get('method'))
            if (type(start) is not int or type(stop) is not int or
                    start < 1 or stop < start or not isinstance(unit, str) or not unit or
                    method not in VISUAL_METHODS | {'ocr'}):
                reason = 'непідтримувані координати або метод'
                break
            category = 'ocr' if method == 'ocr' else 'visual'
            pending.append(((category, unit, row['document_key']), (start, stop)))
        if reason:
            excluded.append({'id': row['id'], 'reason': reason})
        else:
            for key, interval in pending:
                groups[key].append(interval)
    counts = {'visual': {}, 'ocr': {}}
    for (category, unit, _), intervals in groups.items():
        counts[category][unit] = counts[category].get(unit, 0) + union_size(intervals)
    return {'known_units': counts, 'excluded': excluded,
            'note': 'Лише однозначне зафіксоване покриття. Одиниці й OCR/зір не додаються між собою; огляд полів не означає повного прочитання.'}


def metrics(people, links, sources, searches, root_id):
    tree = ancestry(people, links, root_id)
    return {'people_cards': sum(not p.get('merged_into') for p in people),
            'source_records': len(sources), 'search_entries': len(searches),
            'ancestors_including_working': len(tree['ancestor_ids']),
            'ancestors_supported_only': len(tree['supported_ancestor_ids']),
            'biological_ancestors_including_working': len(tree['biological_ancestor_ids']),
            'adoptive_only_ancestors_including_working': len(tree['adoptive_only_ancestor_ids']),
            'context_only_people': len(tree['context_only_person_ids']),
            'ancestry': tree, 'coverage': coverage(searches)}


def load(root, *, hashes=False):
    """Єдиний перевірений зріз: BOM і сумісні поля обробляє валідатор у пам’яті."""
    validator = Validator(root, hashes=hashes)
    if validator.run():
        raise ValueError('Реєстри або хеші джерел мають структурні помилки.')
    return {name: [record for record, _ in validator.rows[kind]]
            for kind, name in [('P', 'people'), ('L', 'links'), ('S', 'sources'),
                               ('C', 'claims'), ('SEARCH', 'searches')]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('root_person_id')
    args = parser.parse_args()
    try:
        rows = load(args.root)
        result = metrics(*(rows[k] for k in ('people', 'links', 'sources', 'searches')), args.root_person_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(1, str(error) + '\n')
