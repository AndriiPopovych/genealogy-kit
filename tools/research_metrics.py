#!/usr/bin/env python3
"""Консервативні підрахунки зі зрізу реєстрів, без генеалогічних рішень."""
import argparse
import json
from collections import defaultdict
from pathlib import Path

ACCEPTED = {'supported', 'accepted_working'}
VISUAL_METHODS = {'field_review', 'image_review', 'full_review'}


def union_size(intervals):
    total = 0
    end = -1
    for start, stop in sorted(intervals):
        total += max(0, stop - max(start, end + 1) + 1)
        end = max(end, stop)
    return total


def ancestry(people, links, root_id):
    """Лише вже прийняті parent_child; робочий місток зберігається по всій лінії."""
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

    def walk(child, supported_only):
        key = (child, supported_only)
        if key in visiting:
            raise ValueError('Цикл родоводу біля ' + child)
        if key in memo:
            return memo[key]
        visiting.add(key)
        ancestors, edge_ids, depth = set(), set(), 0
        for edge in parents[child]:
            if supported_only and edge['status'] != 'supported':
                continue
            parent = edge['roles']['parent']
            older, more_edges, more_depth = walk(parent, supported_only)
            ancestors |= older | {parent}
            edge_ids |= more_edges | {edge['id']}
            depth = max(depth, 1 + more_depth)
        visiting.remove(key)
        memo[key] = ancestors, edge_ids, depth
        return memo[key]

    all_ids, edges, depth = walk(root_id, False)
    supported, _, supported_depth = walk(root_id, True)
    return {'root_id': root_id, 'ancestor_ids': sorted(all_ids),
            'supported_ancestor_ids': sorted(supported),
            'working_only_ancestor_ids': sorted(all_ids - supported),
            'link_ids': sorted(edges), 'depth_including_working': depth,
            'depth_supported_only': supported_depth}


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
            'ancestry': tree, 'coverage': coverage(searches)}


def load(root):
    root = Path(root)
    rows = {key: json.loads((root / 'data' / (key + '.json')).read_text(encoding='utf-8'))
            for key in ('people', 'links', 'sources', 'claims')}
    rows['searches'] = [json.loads(line) for line in
                        (root / 'data/searches.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('root_person_id')
    args = parser.parse_args()
    try:
        from validate_registry import Validator
        validator = Validator(args.root)
        if validator.run():
            raise ValueError('Спочатку виправте структурні помилки реєстрів.')
        rows = load(args.root)
        result = metrics(*(rows[k] for k in ('people', 'links', 'sources', 'searches')), args.root_person_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(1, str(error) + '\n')
