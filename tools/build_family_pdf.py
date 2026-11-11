#!/usr/bin/env python3
"""Локальний PDF зі зрізу реєстрів і перевіреного редакційного плану. Без мережі."""
import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
from xml.sax.saxutils import escape

from research_metrics import load, metrics

STATUS = {'supported': 'Добре обґрунтовано', 'accepted_working': 'Робочий зв’язок',
          'candidate': 'Кандидат', 'unresolved': 'Не вирішено', 'rejected': 'Відхилено'}
DECISIONS = {'continue': 'Пошук триває', 'goal_reached': 'Погоджену мету досягнуто',
             'paused_input': 'Очікуємо потрібну дію', 'paused_resource': 'Пауза через ресурс',
             'stopped_low_yield': 'Доступний перспективний пошук завершено'}
LEVELS = {'high': 'висока', 'medium': 'середня', 'low': 'низька', 'undetermined': 'не визначено'}
NATURES = {'biological': 'Біологічний', 'adoptive': 'Усиновлення',
           'step': 'Вітчим / мачуха', 'household': 'Спільне домогосподарство',
           'other': 'Інший', 'unspecified': 'Природу не встановлено'}
SOURCE_KINDS = {'family_testimony': 'Родинне свідчення', 'original_record': 'Оригінальний запис',
                'derivative_index': 'Похідний покажчик', 'research_report': 'Дослідницький звіт',
                'tree_assertion': 'Твердження з дерева', 'catalog': 'Каталог',
                'historical_copy': 'Історична копія', 'reference_work': 'Довідкова праця'}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def local_file(root, value):
    path = Path(value)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('Потрібен відносний шлях усередині дослідження: ' + str(value))
    full = root / path
    if any(p.is_symlink() for p in (full, *full.parents)):
        raise ValueError('Символічні посилання не дозволені: ' + str(value))
    full.resolve().relative_to(root)
    if not full.is_file():
        raise ValueError('Файл відсутній: ' + str(value))
    return full


def web_url(value):
    if not value:
        return None
    parts = urlsplit(value)
    if parts.scheme not in {'http', 'https'} or not parts.hostname or parts.username or parts.password:
        raise ValueError('Непридатна адреса джерела; дозволено http/https без облікових даних.')
    if any(ord(c) < 32 for c in value):
        raise ValueError('Керівні символи в адресі джерела.')
    return value


def build(root, plan_path, output, font, bold_font=None):
    # Залежність необов’язкова для решти комплекту.
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, Image

    root = Path(root).resolve()
    plan_path = local_file(root, Path(plan_path).as_posix())
    output = Path(output)
    if not output.is_absolute():
        output = root / output
    if output.is_symlink() or output.parent.is_symlink():
        raise ValueError('Каталог результату не може бути символічним посиланням.')
    if output.resolve().parent != root / 'exports' or output.exists():
        raise ValueError('Результат має бути новою папкою exports/<назва> дослідження.')
    input_paths = {plan_path, *(root / 'data' / (name + '.json') for name in ('people', 'sources', 'links', 'claims')),
                   root / 'data/searches.jsonl'}
    input_hashes = {path: digest(path.read_bytes()) for path in input_paths}
    rows = load(root, hashes=True)
    plan = json.loads(plan_path.read_text(encoding='utf-8-sig'))
    for key in ('title', 'snapshot_at', 'audience', 'root_person_id', 'summary', 'decision'):
        if not plan.get(key):
            raise ValueError('У плані бракує ' + key)
    decision = plan['decision']
    if decision.get('status') not in DECISIONS or not decision.get('reason'):
        raise ValueError('Потрібне рішення про продовження/зупинку з причиною.')
    if plan['audience'] != 'owner' and not all(plan.get('privacy_review', {}).get(k) for k in ('by', 'scope', 'date')):
        raise ValueError('Для іншої аудиторії потрібна перевірка вмісту й медіа: privacy_review by/scope/date.')
    stats = metrics(*(rows[k] for k in ('people', 'links', 'sources', 'searches')), plan['root_person_id'])
    indexes = {kind: {record['id']: record for record in rows[name]}
               for kind, name in [('P', 'people'), ('S', 'sources'), ('C', 'claims'), ('L', 'links')]}
    refs = {('P', plan['root_person_id'])}
    links = [indexes['L'][ident] for ident in stats['ancestry']['link_ids']]
    source_ids, claim_ids = set(), set()
    for link in links:
        refs.add(('L', link['id']))
        refs.update(('P', ident) for ident in link['person_ids'])
        claim_ids.update(link['claim_ids'])
    for section in plan.get('sections', []):
        if not section.get('claim_ids') and not section.get('link_ids'):
            raise ValueError('Змістовний розділ потребує claim_ids або link_ids.')
        claim_ids.update(section.get('claim_ids', []))
        for ident in section.get('link_ids', []):
            link = indexes['L'][ident]
            refs.add(('L', ident))
            refs.update(('P', item) for item in link['person_ids'])
            claim_ids.update(link['claim_ids'])
    for ident in claim_ids:
        claim = indexes['C'][ident]
        refs.add(('C', ident))
        refs.update(('P', item) for item in claim['subject_person_ids'])
        source_ids.add(claim['source_id'])
    documents = {item['source_id']: item for item in plan.get('documents', [])}
    if len(documents) != len(plan.get('documents', [])):
        raise ValueError('Повтор source_id у документах плану.')
    source_ids.update(documents)
    refs.update(('S', ident) for ident in source_ids)
    for kind, ident in refs:
        if ident not in indexes[kind]:
            raise ValueError('Невідомий ID: ' + kind + ':' + ident)
    # Сталі безпечні внутрішні імена; ID джерела не вставляється в PDF markup.
    anchors = {ident: 'source' + str(n) for n, ident in enumerate(sorted(source_ids))}
    prepared = {}
    for ident in sorted(source_ids):
        source, item = indexes['S'][ident], documents.get(ident, {})
        url = web_url((source.get('digital_locator') or {}).get('viewer_url') or source.get('url'))
        images = []
        registered = {entry['path']: entry for entry in source.get('files', [])}
        for value in item.get('image_paths', []):
            if value not in registered:
                raise ValueError('Зображення не зареєстровано в джерелі ' + ident + ': ' + value)
            path = local_file(root, value)
            if path.suffix.lower() not in {'.png', '.jpg', '.jpeg'}:
                raise ValueError('Для PDF використайте перевірений PNG/JPEG.')
            images.append(path)
            current_hash = digest(path.read_bytes())
            if current_hash != registered[value]['sha256']:
                raise ValueError('Зображення змінилося після перевірки: ' + value)
            input_hashes[path] = current_hash
        prepared[ident] = (url, images, item.get('access_note', ''))
    pdfmetrics.registerFont(TTFont('Kit', str(font)))
    pdfmetrics.registerFont(TTFont('KitBold', str(bold_font or font)))
    pdfmetrics.registerFontFamily('Kit', normal='Kit', bold='KitBold', italic='Kit', boldItalic='KitBold')
    ink, muted, teal = colors.HexColor('#18313c'), colors.HexColor('#51636b'), colors.HexColor('#126b69')
    styles = {
        'body': ParagraphStyle('body', fontName='Kit', fontSize=10, leading=15, textColor=ink, spaceAfter=8),
        'small': ParagraphStyle('small', fontName='Kit', fontSize=8, leading=11, textColor=muted, spaceAfter=6),
        'title': ParagraphStyle('title', fontName='KitBold', fontSize=25, leading=31, textColor=ink, spaceAfter=18),
        'h1': ParagraphStyle('h1', fontName='KitBold', fontSize=17, leading=22, textColor=teal, spaceBefore=10, spaceAfter=10, keepWithNext=True),
        'h2': ParagraphStyle('h2', fontName='KitBold', fontSize=12, leading=17, textColor=ink, spaceBefore=8, spaceAfter=7, keepWithNext=True)}
    story = []

    def para(value, style='body'):
        return Paragraph(escape(str(value)).replace('\n', '<br/>'), styles[style])

    def add(value, style='body'):
        story.append(para(value, style))

    def assessment(value):
        return LEVELS.get(value['level'], value['level']) + ': ' + value['reason']

    def source_link(ident):
        return '<link href="#' + anchors[ident] + '" color="#126b69">' + escape(ident) + '</link>'

    add(plan['title'], 'title')
    add('Зріз: ' + plan['snapshot_at'] + ' • Початкова особа: ' + indexes['P'][plan['root_person_id']]['display_name'], 'small')
    add(plan['summary'])
    if plan.get('changes'):
        add('Що змінилося', 'h2')
        add(plan['changes'])
    add('Дослідження в цифрах', 'h1')
    for label, value in [('Карток осіб у реєстрі', stats['people_cards']),
                         ('Предків у біологічних та усиновлювальних лініях разом із робочими', stats['ancestors_including_working']),
                         ('Із них: лише через біологічні переходи', stats['biological_ancestors_including_working']),
                         ('Із них: доступні тільки через усиновлення', stats['adoptive_only_ancestors_including_working']),
                         ('Предків лише з добре обґрунтованими переходами', stats['ancestors_supported_only']),
                         ('Осіб лише в контекстній схемі, поза числом предків', stats['context_only_people']),
                         ('Глибина родовідних ліній разом із робочими / лише добре обґрунтовані',
                          str(stats['ancestry']['depth_including_working']) + ' / ' + str(stats['ancestry']['depth_supported_only'])),
                         ('Записів джерел у реєстрі (не число незалежних актів)', stats['source_records'])]:
        add(str(value) + ' — ' + label)
    known = stats['coverage']['known_units']['visual']
    units = {'frame': 'кадри', 'page': 'сторінки', 'folio': 'аркуші'}
    add('Візуально переглянуте однозначне покриття: ' +
        (', '.join(units.get(k, k) + ': ' + str(v) for k, v in sorted(known.items())) if known else 'не встановлено'), 'small')
    add(stats['coverage']['note'], 'small')
    if stats['coverage']['excluded']:
        add('Не включено до підрахунку покриття: ' + '; '.join(item['id'] + ' — ' + item['reason'] for item in stats['coverage']['excluded']), 'small')
    add('Як читати', 'h2')
    add('Картки осіб включають кандидатів. Предки й глибина рахуються за прийнятими біологічними та усиновлювальними переходами. Інші типи й невстановлена природа залишаються в контекстній схемі; старша лінія за таким переходом також не додається до числа предків без іншого родовідного шляху. Робочий місток обмежує всю старшу лінію. Три оцінки збережено окремо.', 'small')
    story.append(PageBreak())
    add('Схема прийнятих зв’язків', 'h1')
    add('Блоки ведуть від початкової особи до старших або пов’язаних осіб. Читайте підпис природи кожного зв’язку: стрілка сама по собі не означає біологічного походження. Кандидати не приєднані.', 'small')
    if not links:
        add('Прийнятих родовідних переходів від початкової особи ще немає.')
    for link in links:
        child, parent = (indexes['P'][link['roles'][role]]['display_name'] for role in ('child', 'parent'))
        table = Table([[para(child), para('→'), para(parent)],
                       [para(link['id'], 'small'), '', para(STATUS[link['status']], 'small')]], colWidths=[205, 25, 265])
        table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#edf4f2')),
                                   ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 10),
                                   ('TOPPADDING', (0, 0), (-1, -1), 8)]))
        story.extend([table, Spacer(1, 10)])
        add('Природа зв’язку: ' + NATURES[link.get('relationship_nature', 'unspecified')], 'small')
        if link['id'] not in stats['ancestry']['family_link_ids']:
            add('Контекстний перехід: цей шлях не збільшує число предків або глибину родоводу.', 'small')
        add(link.get('basis', ''), 'small')
        add('Тотожність — ' + assessment(link['identity_confidence']), 'small')
        add('Спорідненість — ' + assessment(link['relationship_confidence']), 'small')
        if link.get('conflicts'):
            add('Суперечності: ' + '; '.join(link['conflicts']))
        add('Межі альтернатив: ' + str(link.get('alternative_search_scope', link.get('alternatives', 'не зазначено'))), 'small')
        add('Переглянути рішення, якщо: ' + str(link.get('revisit_if', 'з’явиться новий доказ')), 'small')
    shown_links = set(stats['ancestry']['link_ids'])
    for section in plan.get('sections', []):
        add(section['title'], 'h1')
        add(section['text'])
        add('Підстава: ' + ', '.join(section.get('claim_ids', []) + section.get('link_ids', [])), 'small')
        for ident in section.get('link_ids', []):
            if ident not in shown_links:
                link = indexes['L'][ident]
                add(ident + ' — ' + STATUS[link['status']], 'small')
                if link['kind'] == 'parent_child':
                    add('Природа зв’язку: ' + NATURES[link.get('relationship_nature', 'unspecified')], 'small')
                add('Тотожність — ' + assessment(link['identity_confidence']), 'small')
                add('Спорідненість — ' + assessment(link['relationship_confidence']), 'small')
                if link.get('conflicts'):
                    add('Суперечності: ' + '; '.join(link['conflicts']))
                shown_links.add(ident)
    add('Поточна межа й наступна дія', 'h1')
    add(DECISIONS[decision['status']])
    add(decision['reason'])
    if decision.get('next_action'):
        add('Далі: ' + decision['next_action'])
    if decision.get('reopen_when'):
        add('Умова повернення: ' + decision['reopen_when'])
    story.append(PageBreak())
    add('Твердження й докази', 'h1')
    for ident in sorted(claim_ids):
        claim = indexes['C'][ident]
        add(ident + ' — ' + claim['normalized_statement'])
        story.append(Paragraph('Джерело: ' + source_link(claim['source_id']) + '; ' + escape(str(claim['locator'])), styles['small']))
        add('Прочитання — ' + assessment(claim['reading_confidence']), 'small')
        if claim.get('derivation'):
            add('Виведення: ' + claim['derivation'], 'small')
    for ident in sorted(source_ids):
        source = indexes['S'][ident]
        url, images, access_note = prepared[ident]
        if images:
            story.append(PageBreak())
        story.append(Paragraph('<a name="' + anchors[ident] + '"/>' + escape(ident + ' — ' + source['title']), styles['h1']))
        add('Тип джерела: ' + SOURCE_KINDS.get(source['kind'], source['kind']), 'small')
        add('Локатор: ' + str(source['locator']))
        if url:
            story.append(Paragraph('<link href="' + escape(url, {'"': '&quot;'}) + '" color="#126b69">Відкрити повний документ</link>', styles['body']))
            add(url, 'small')
        else:
            add('Публічної адреси немає; повернення до джерела — за наведеним локатором.', 'small')
        if access_note:
            add(access_note, 'small')
        for path in images:
            pic = Image(str(path))
            factor = min(495 / pic.imageWidth, 540 / pic.imageHeight, 1)
            pic.drawWidth, pic.drawHeight = pic.imageWidth * factor, pic.imageHeight * factor
            story.extend([pic, Spacer(1, 12)])
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.pdf-', dir=output.parent))
    try:
        pdf = staging / 'report.pdf'
        doc = SimpleDocTemplate(str(pdf), pagesize=A4, leftMargin=50, rightMargin=50,
                                topMargin=43, bottomMargin=43, title=plan['title'], author='genealogy-kit')
        def footer(canvas, document):
            canvas.setFont('Kit', 8)
            canvas.setFillColor(muted)
            canvas.drawString(50, 25, 'Зріз ' + plan['snapshot_at'])
            canvas.drawRightString(A4[0] - 50, 25, str(document.page))
        doc.build(story, onFirstPage=footer, onLaterPages=footer)
        (staging / 'metrics.json').write_text(json.dumps(stats, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        if any(digest(path.read_bytes()) != before for path, before in input_hashes.items()):
            raise ValueError('Вхідний зріз змінився під час побудови; повторіть зі сталими даними.')
        manifest = {'snapshot_at': plan['snapshot_at'], 'topic': plan['title'], 'audience': plan['audience'],
                    'record_refs': [{'type': kind, 'id': ident, 'sha256': digest(json.dumps(indexes[kind][ident], ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode())} for kind, ident in sorted(refs)],
                    'input_files': [{'path': str(path.relative_to(root)), 'sha256': value} for path, value in sorted(input_hashes.items())],
                    'files': [{'path': str((output / path.name).relative_to(root)), 'sha256': digest(path.read_bytes())} for path in sorted(staging.iterdir())],
                    'privacy_revision': plan.get('privacy_review', {}).get('scope', 'owner-local'),
                    'local_status': 'draft', 'deployed_status': 'not_deployed',
                    'visual_qa': 'pending: перевірити всі сторінки й посилання перед передаванням'}
        (staging / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        staging.rename(output)
    except Exception:
        shutil.rmtree(staging)
        raise
    return output / 'report.pdf'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('plan', help='Відносний до root шлях редакційного JSON-плану')
    parser.add_argument('output', help='Нова папка exports/<назва>')
    parser.add_argument('--font', required=True, type=Path, help='Локальний TTF із українськими літерами')
    parser.add_argument('--bold-font', type=Path)
    args = parser.parse_args()
    try:
        print(build(args.root, args.plan, args.output, args.font, args.bold_font))
    except (ValueError, OSError, KeyError, TypeError, ImportError) as error:
        parser.exit(1, str(error) + '\n')
