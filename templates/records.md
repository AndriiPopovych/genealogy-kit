# Шаблони людей, джерел і висновків

Це формати для заповнення, не дослідницькі дані. Значення в кутових дужках замініть; невідомі додаткові поля — `null` з поясненням або порожній список там, де він означає відсутність елементів. У прикладах немає справжньої людини чи архівного шифру. Початкові реєстри в `data/` вже створені порожніми.

У паралельному режимі ці головні реєстри редагує тільки координатор. Працівники повертають пропозиції у власних папках за [шаблоном задачі](worker_task.md); постійні ID з прикладів самостійно не займають.

Дати запису в базу — `YYYY-MM-DD`; дати історичних подій зберігайте також словами оригіналу, з приблизністю й календарем. Не підставляйте день чи місяць заради формату.


## Контракт схеми 1

Нові реєстри мають `data/format.json` з `{"schema_version": 1}`. Версія схеми окрема від VERSION. Старі бази без marker читаються в legacy-режимі. Поля нижче обов’язкові для нових записів; інші показані поля додаткові, крім явно зазначених умов.

| Запис | Обов’язково | Умовно |
|---|---|---|
| P | id, display_name, living_status | unknown не означає deceased |
| S | id, title, kind, provenance, locator | Для отриманих files: path, provenance, received_at, sha256, bytes, role; старе невідоме null із notes, legacy-діагностика |
| C | id, source_id, subject_person_ids, text_as_written, statement_kind, normalized_statement, locator, reading_confidence | inference потребує derivation; text_as_written може бути позначеним викладом підстави, не вигаданою цитатою |
| L | id, kind, person_ids, roles, claim_ids, status, identity_confidence, relationship_confidence, assessed_by/at | accepted_working/supported: basis, conflicts, alternatives або alternative_search_scope, revisit_if |
| SEARCH | id, date, question_id, repository, query_or_route, method, coverage, gaps, result, next_step | За повтору repeat_of та repeat_reason |
| CHANGE | id, date, target_id, field, old_value, new_value, reason, evidence_refs, confidence, author, applied | target_type потрібний, якщо ID неоднозначний між просторами |

Унікальність ID — усередині P/S/C/L/SEARCH/CHANGE; історичні namespaces і написання не змінювати. Типізоване посилання: `{"type":"C","id":"C0001"}`. `depends_on` — додатковий масив таких посилань; C→S і L→C уже виводяться зі штатних полів. Це черга для перегляду, не каскад зміни статусів. Q ведеться в state/questions.md; його наявність звіряється з рядком таблиці.

Оцінки — `{"level":"high|medium|low|undetermined","reason":"коротке пояснення"}`. Не переносіть упевненість між прочитанням, тотожністю та спорідненістю. Два батьки — два окремі parent_child L, кожен зі своїм рішенням, без parent2. Відсутність акта народження або другого джерела не є структурною помилкою.

### Огляд зображення

Для S/C із `review_status=reviewed` потрібні `reviewed_scope`, `reviewer`, `reviewer_type` (human/model), `reviewed_at`, `illegible_parts` (порожній масив — нерозбірливого в цьому обсязі не виявлено). C може натомість мати `review_ref={"type":"S","id":"S0001","scope":"акт 1, рядки 1–3"}` та той самий `reviewed_scope`; S має містити повні метадані саме цього обсягу. Посилання на всю книгу не покриває один акт. Для метаданих лише в транскрипції перенесіть точний обсяг і атрибуцію в S з transcript_path; валідатор не вгадує їх із довільного Markdown. Це мінімальна перевірювана форма review_ref.

Усна розповідь без зображення не потребує review_status; provenance/спосіб фіксації й локатор потрібні. Модельна перевірка не є людською експертизою.

### Пошукові координати

Необов’язкові: document_key, resource_channel, access_status, coverage_parts, positive_control, repeat_of/repeat_reason. `coverage_parts=[{"unit":"frame","from":1,"to":3,"fields":["імена"],"section":"шлюби","method":"field_review"}]`. Пропуск окремо в gaps, різні нумерації окремими частинами. Один DGS може містити кілька document_key. OCR-only не дорівнює прочитаному зображенню; access_blocked/not_checked не має фактично оглянутих кадрів. Старий текст coverage незмінний.

`locator_variants=[{"system":"каталог","value":"умовний шифр","provenance":"де прочитано","source_ref":{"type":"S","id":"S0001"},"relation":"unresolved"}]` — додатковий формат. Еквівалентність шифрів встановлюється доказом, не схожістю числа. Фонд/справа/кадр/аркуш/двір/акт — різні поля.

### Сумісність

Валідатор лише читає. `--legacy` зберігає всі поля, показує застереження щодо браку нових метаданих, старих enum і рядкових оцінок. Дублікати, биті JSON та висячі посилання лишаються помилками. Старі historical_copy/catalog/reference_work допустимі без перекласифікації. Відомі альтернативні назви лише в пам’яті: literal_text→text_as_written, kinship_confidence→relationship_confidence, alternative_search_limits→alternative_search_scope, parentage_type→relationship_nature, resource→repository, review_scope→reviewed_scope, reviewed_by→reviewer. Два суперечливі значення — помилка; автоматичного переписування немає. Інші aliases/невідомі поля зберігаються, їхній зміст не вгадується.

`tools/validate_registry.py` має текст/--json, optional --hashes; коди 0/1/2 описані в guide/tools_and_memory.md. Структурно коректна база не є сертифікатом генеалогії. `render_links.py` генерує лише позначений блок; пояснення лишаються поза ним.

## Людина

Запис додається до масиву `data/people.json`. Ім’я картки — зручна назва, а не підміна джерельних написань. Присвоюйте ID лише особі, про яку є хоча б початкове свідчення; не створюйте вигаданих батьків.

```json
{
  "id": "P0001",
  "display_name": "<ім’я або псевдонім>",
  "living_status": "unknown",
  "name_variants": [],
  "claim_ids": [],
  "link_ids": [],
  "merged_into": null,
  "notes": "",
  "updated_at": "<дата>"
}
```

`living_status`: `living`, `deceased`, `unknown`. Варіант імені записуйте об’єктом `{"text": "...", "source_id": "S0001", "kind": "as_written"}`; для пошукової нормалізації — `kind: "search_variant"` і пояснення. Не робіть автоматичних висновків про живу людину з віку.

Якщо тотожність двох згадок невирішена, можна створити окремі кандидатні картки й пов’язати їх рішенням `identity`. Не об’єднуйте всі події в одну особу до оцінки.

## Джерело

Запис у `data/sources.json`. Для скану S означає конкретний історичний запис або визначений документ із точним локатором. Для опису книги можна створити окремий S із `kind: "catalog"`, а знайденому акту дати наступний ID. Один файл може містити кілька джерельних записів; один запис може мати кілька цифрових копій.

```json
{
  "id": "S0001",
  "title": "<назва документа або свідчення>",
  "kind": "original_record",
  "provenance": "<хто передав / URL / спосіб фіксації>",
  "locator": "<точний доступний локатор або причина невідомого>",
  "creator_or_informant": null,
  "creation_date_as_written": null,
  "received_at": "<дата>",
  "accessed_at": null,
  "url": null,
  "archive_locator": {
    "archive": null,
    "fond": null,
    "inventory": null,
    "file": null,
    "folio": null,
    "provenance": null
  },
  "digital_locator": {
    "viewer_url": null,
    "collection": null,
    "dgs": null,
    "ark": null,
    "frame": null,
    "pdf_page": null,
    "entry_number": null
  },
  "files": [],
  "derived_from_source_ids": [],
  "dependency_note": "",
  "review_status": "unread",
  "reviewed_scope": "",
  "reviewer": null,
  "reviewer_type": null,
  "illegible_parts": [],
  "reviewed_at": null,
  "transcript_path": null,
  "locator_conflicts": [],
  "notes": ""
}
```

Допустимі `kind`: `family_testimony`, `original_record`, `historical_copy`, `derivative_index`, `tree_assertion`, `research_report`, `catalog`, `reference_work`. Вони описують походження, не автоматичний рейтинг достовірності.

Елемент `files`: `{"path": "originals/S0001/<файл>", "original_name": "<назва при отриманні>", "sha256": "<64 hex після обчислення>", "bytes": 0, "role": "full_scan", "provenance": "<URL або отримано від кого>", "received_at": "<фактична дата>"}`. Після обчислення внесіть справжню суму й розмір.

Необов’язкове `digital_locator.viewer_url` — перевірена адреса переглядача конкретного документа/кадру; `url` може вести до каталогу. Генератор PDF не конструює адресу з номера кадру й не перевіряє сайт. Правила — guide/pdf_reports.md.

Для сімейного свідчення архівні поля лишаються порожніми. У `creator_or_informant` зазначте людину або псевдонім; у `notes` — прямий спогад, переказ чи невідоме походження. Збережіть текст свідчення в `transcripts/`.

`derived_from_source_ids` указує відомий зв’язок індексу/звіту/копії з джерелом. Якщо спільне походження лише ймовірне, так і напишіть у `dependency_note`. Не робіть висновку про незалежність тільки через різні S.

## Окреме твердження

Запис у `data/claims.json`. Один C — одна подія, ознака або формула спорідненості з конкретного джерела. Суперечливі відомості створюють окремі C, а не стирають попередні.

```json
{
  "id": "C0001",
  "source_id": "S0001",
  "subject_person_ids": ["P0001"],
  "text_as_written": "<цитата або точний переказ із позначенням>",
  "statement_kind": "source_statement",
  "normalized_statement": "<що саме стверджується>",
  "event_type": null,
  "event_date": {
    "as_written": null,
    "normalized": null,
    "precision": "unknown",
    "calendar": "unknown",
    "derivation": null
  },
  "place_as_written": null,
  "locator": "<рядки, акт, ділянка або фрагмент свідчення>",
  "review_status": "partial_review",
  "reading_confidence": {"level": "undetermined", "reason": "<межа прочитання>"},
  "uncertainties": [],
  "recorded_at": "<дата>"
}
```

`statement_kind`: `source_statement` або `inference`. Для розрахованого року народження збережіть вихідний вік і розрахунок у `derivation`, а `precision` зробіть `approximate` чи `range`. Інші значення: `exact`, `before`, `after`, `unknown`. Якщо календар не встановлений, лишайте `unknown`.

`subject_person_ids` допомагає навігації, але сам по собі не доводить ідентифікації; її оцінка живе в L. Для запису без прив’язаної людини допустимий порожній список.

## Рішення про тотожність або спорідненість

Запис у `data/links.json`. `identity` пов’язує документальні згадки з особою або порівнює дві кандидатні картки. `parent_child`, `spouses`, `siblings`, `family_circle` описують різні зв’язки; коло родини не дорівнює встановленому ступеню споріднення.

```json
{
  "id": "L0001",
  "kind": "parent_child",
  "person_ids": ["P0001", "P0002"],
  "roles": {"parent": "P0002", "child": "P0001"},
  "relationship_nature": "unspecified",
  "claim_ids": ["C0001"],
  "status": "candidate",
  "identity_confidence": {"level": "undetermined", "reason": "<межа ототожнення>"},
  "relationship_confidence": {"level": "undetermined", "reason": "<межа спорідненості>"},
  "basis": "<найсильніший аргумент>",
  "support": [],
  "conflicts": [],
  "missing_evidence": [],
  "alternatives": [],
  "alternative_search_scope": "",
  "next_discriminating_check": "",
  "revisit_if": "",
  "assessed_by": "<LLM або людина>",
  "assessed_at": "<дата>"
}
```

Для `identity` у `roles` можна зазначити `{"target": "P0001"}`, а level у `relationship_confidence` залишити `undetermined` із поясненням. Для невизначеного сімейного кола не вигадуйте ролей.

`relationship_nature`: `unspecified`, `biological`, `adoptive`, `step`, `household`, `other`; заповнюйте за змістом і доказом. Записане батьківство не слід мовчки перетворювати на генетичне підтвердження.

Дозволені статуси й рівні впевненості описані в [AGENTS.md](../AGENTS.md). Для прийнятого зв’язку достатньо стислого аргументу; порожній список альтернатив без пояснення обсягу перевірки не означає, що тезок немає.

## Транскрипція

Окремий Markdown-файл у `transcripts/`, наприклад `S0001_reading.md`. Довгий документ можна поділити на кадри, зберігши єдину навігацію.

```text
Джерело: S…
Файл і локатор:
Розмір вихідного кадру:
Координати фрагмента, початок відліку:
Повний заявлений обсяг читання:
Статус: unread / machine_ocr_unverified / partial_review / reviewed
Хто читав і коли:

Транскрипція зі збереженням рядків
L01 …
L02 … [нерозбірливо]

Нормалізований зміст
…

Ключові поля
Поле | буквальне читання | впевненість | альтернатива

Спірні місця й порівняння почерку
…

Що це може дати родоводу
C… / L…; відокремити факт документа від ототожнення
```

Буквальна транскрипція з нормалізованими літерами чи розкритими скороченнями має це зазначати. «Дослівно» не використовуйте для переказу.

## Пошук

Додайте один об’єкт на один рядок у `data/searches.jsonl`; нижче його показано розгорнуто лише для читабельності.

```json
{
  "id": "SEARCH0001",
  "date": "<дата>",
  "question_id": "Q0001",
  "repository": "<установа або локальна папка>",
  "url_or_path": "<адреса>",
  "query_or_route": "<точний запит або маршрут каталогу>",
  "coverage": "<роки, парафія, частина книги, кадри, поля>",
  "method": "<index / ocr / page_survey / field_review / full_transcription>",
  "gaps": [],
  "result": "<що знайдено або не знайдено саме в цьому обсязі>",
  "source_ids": [],
  "next_step": ""
}
```

Якщо сайт не відкрився, записуйте проблему доступу. Не записуйте такий результат як відсутність потрібного документа.

## Виправлення

Додайте рядок у `data/corrections.jsonl` перед зміною актуального висновку.

```json
{
  "id": "CHANGE0001",
  "date": "<дата>",
  "target_id": "<P / S / C / L>",
  "field": "<поле або висновок>",
  "old_value": null,
  "new_value": null,
  "reason": "<новий доказ або виправлене читання>",
  "evidence_refs": [],
  "confidence": {"level": "undetermined", "reason": "<підстава оцінки>"},
  "author": "<хто перевірив>",
  "applied": false
}
```

`old_value` і `new_value` можуть бути текстом, числом або повним об’єктом. Для поточного pending-запису змініть лише `applied` після фактичного оновлення, зберігши old/new та підставу. Завершені рядки не переписуйте. Слова померлого оповідача не переписуйте під нову версію: виправляється наша оцінка, а його свідчення залишається.

## Архівний запит

Нижче чернетка для уточнення й погодження; вона не надіслана.

> Добрий день!
>
> Досліджую родину [ім’я/прізвище] з [поселення, історична адміністративна належність, парафія, якщо відомо]. Шукаю [конкретний акт або тип відомостей] за [обґрунтований інтервал].
>
> Відомі дані: [особа, родичі, приблизна дата, інші ознаки для розрізнення тезок]. Уже перевірено: [короткий перелік].
>
> У каталозі виявлено [назва та точний шифр, якщо встановлено; інакше цей абзац прибрати]. Прошу повідомити, чи є потрібні матеріали, чи доступні цифрові копії та яким є порядок їх отримання.
>
> Якщо запис буде локалізовано, мене цікавить копія повного акта з необхідними заголовками й підтвердженням архівних реквізитів. Перед виконанням платних робіт прошу повідомити обсяг і вартість.
>
> [Ім’я та погоджений контакт]

Для обмежених у доступі актів порядок підтвердження спорідненості уточнюйте в установи. Не додавайте копії сучасних посвідчень до неперевіреної адреси.

## Перевірка перед збереженням підсумку

Чи існують усі P/S/C/L, на які посилається запис? Чи лежить файл за вказаним шляхом? Чи цитата відповідає саме цьому акту? Чи відділено джерельне твердження від нашого рішення? Чи старий висновок лишився в історії? Чи робочий зв’язок видимий у `state/links.md`? Після цих перевірок оновіть `state/current.md`.

## Матеріали для людей й контейнери

Видання має export_manifest.json: topic/audience/snapshot_at, типізовані record_refs, input_files і files з хешами, privacy_revision, local_status/deployed_status. Залежне видання після CHANGE позначає координатор outdated; джерело й рішення мають різні позначки. Приклад — examples/synthetic/exports/cards.

Складний вхід описує material_inventory.json. S.container/member зберігають адресу вкладення; вкладений оригінал має власний S і тип. C.assertion_context — додатковий об’єкт `{speaker, role, recorded_at, asserted_event_date, nature, locator}` для заяв/рішень/виконання. Невідомі дати не вигадуються. Старі IDs з різних систем зберігаються в source_namespace/old_id і окремій mapping-таблиці; автоматичного злиття немає.
