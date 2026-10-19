# fz168-linter — проверка текстов на 168-ФЗ (закон о государственном языке)

[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Status: beta](https://img.shields.io/badge/status-beta-orange.svg)](https://github.com/thebestbaduser/fz168-linter/releases)

**Линтер и skill для проверки русских текстов на 168-ФЗ: англицизмы, латиница,
смешанные алфавиты, равнозначный перевод.** Python CLI, валидатор Django,
правила для LLM-агентов (Claude Code, Cursor).

Подходит для сайтов, интерфейсов, CMS, документации, рекламы, каталогов и карточек
товаров. Находит иностранные слова и заимствования, латинские надписи без русского
дубля, проверяет кириллицу в официальных названиях объектов.

> Результат — предварительная проверка по формализованным правилам.
> Это не юридическое заключение.

---

## Возможности

- находит латиницу в текстах, HTML/JSX-шаблонах и Markdown, не реагируя на `class`,
  `id`, `href`, URL, e-mail и код;
- проверяет статические подписи `placeholder`, `alt`, `title`, `aria-label`,
  значения текстовых полей и строковые выражения JSX;
- понимает Django-шаблоны: `{% ... %}`, `{{ ... }}` и `{# ... #}` маскируются,
  видимый текст проверяется;
- обнаруживает **смешанные алфавиты** (гомоглифы): латинская `a` внутри кириллического слова;
- сверяет кириллические заимствования с локальным словарём и выдаёт варианты замены;
- учитывает **правовой контекст**: реклама, публичная информация, внутренний интерфейс,
  товарные знаки; при необходимости — объекты недвижимости и реклама долевого строительства;
- возвращает машинно-читаемый отчёт с `legal_basis`, `rule_id`, `confidence` и позициями
  символов **в исходной строке** (до любой нормализации).

## Область применения

- проверка контента и UI перед публикацией;
- CI-проверка шаблонов, словарей и текстов;
- валидатор в админке Django;
- skill для LLM-агента: единые правила вместо «как модель придумает»;
- массовый аудит существующего контента.

## Проверка текста на англицизмы и 168-ФЗ

Если нужно проверить текст на англицизмы, латиницу и заимствования:

```bash
fz168 check page.html --input html --surface public_information
```

Линтер находит иностранные слова и латинские надписи, сверяет их с локальным
словарём, показывает норму и варианты замены. Работает без внешних API и без
передачи текста в облако.

Типовые задачи:

- проверить сайт или отдельную страницу на иностранные слова;
- проверить рекламный текст и вывески;
- проверить официальные названия на кириллицу;
- проверить интерфейс на латинские кнопки и подписи;
- добавить проверку в CI, pre-commit или админку Django.

## Сверка с официальным наименованием

Отдельный режим — сравнить текст с эталоном из ЕИСЖС или проектной декларации:

```bash
fz168 name-audit "Test Object" \
  --official-name "Тестовый Объект" \
  --alias "Test Object" \
  --object-type residential_complex --ddu-ad --role developer
```

Как читать результат:

- латинский алиас при кириллическом официальном имени — `NEEDS_REVIEW`
  (расхождение с эталоном, а не автоматическое нарушение);
- если роль — застройщик и контекст — реклама ДДУ, это `LIKELY_VIOLATION`;
- официальное имя на латинице отмечается отдельно;
- в режиме аудита отсутствие эталонного имени в тексте — `name-not-found`,
  наличие — `name-official-present`.

Для каталога-агрегатора роль `aggregator` не превращает карточку в рекламу
застройщика: расхождение остаётся поводом для проверки, а не готовым выводом.

---

## Поддерживаемые нормы

| Норма | Что проверяется | Когда применяется |
|---|---|---|
| ЗоЗПП, ст. 10.1 (введена ст. 1 168-ФЗ) | Русский язык публичной нерекламной информации; иностранный — только как дубль | `legal_surface=public_information` |
| 38-ФЗ, ч. 11 ст. 5 | Русский язык рекламы | `legal_surface=advertisement` |
| 53-ФЗ, ч. 2 ст. 3 | Идентичность содержания и равнозначность оформления дубля | при дублировании текста |
| 214-ФЗ, п. 7 ст. 2 (введён ст. 4 168-ФЗ) | Кириллица в наименовании объекта в рекламе ДДУ | `object_type=residential_complex` или `building` + `ddu_fundraising_ad=true` |

Применимость норм задаётся контекстом вызывающей стороны. `public_information`
обозначает информацию в сфере ст. 10.1 ЗоЗПП, а не любой открытый текст сайта;
реклама и информация по ст. 8–10 требуют отдельной квалификации.
Санкции и нерешённые вопросы — [docs/LEGAL.md](docs/LEGAL.md).

## Статусы

| Статус | Значение |
|---|---|
| `LIKELY_VIOLATION` | Применимая норма указывает на вероятное нарушение при данном контексте |
| `NEEDS_REVIEW` | Без уточнения обстоятельств вывод невозможен: нужен человек |
| `NO_ISSUE_FOUND` | По реализованным правилам нарушений не найдено; это **не** «юридически разрешено» |
| `NOT_APPLICABLE` | Норма не распространяется на объект (например, переходное исключение) |

---

## Установка

Пакет пока не опубликован в PyPI — установка из исходников.

```bash
git clone https://github.com/thebestbaduser/fz168-linter.git
cd fz168-linter
pip install -e .             # ядро, без внешних зависимостей
pip install -e ".[morph]"    # + pymorphy3 для лемматизации
pip install -e ".[django]"   # + валидатор для моделей Django
pip install -e ".[dev]"      # тесты и линтер кода
python -m unittest discover -s tests -v
```

После установки доступна команда `fz168`.

## CLI

```bash
# HTML-страница
fz168 check page.html --input html --surface public_information

# рекламный текст
fz168 check ad.txt --surface advertisement

# контекст недвижимости включается явно
fz168 check card.txt --surface advertisement \
  --object-type residential_complex --ddu-ad

# JSON-отчёт для CI
fz168 check README.md --input markdown --format json
```

Пример вывода:

```
LIKELY_VIOLATION public-info-not-russian 12:7 "Sale"
  Публичная информация потребителя без русского текста (ЗоЗПП ст. 10.1 п. 2).
  Варианты: Распродажа, Акция
```

Код выхода по умолчанию: `1`, если есть `LIKELY_VIOLATION`, иначе `0`.
`--fail-on review` блокирует также `NEEDS_REVIEW`, `--fail-on never` сохраняет отчёт
без блокировки. Ошибка аргументов, чтения файла или UTF-8 даёт код `2`.

## Python API

```python
from fz168_linter import Context, check_text

report = check_text(
    "Купить / Sale",
    Context(legal_surface="public_information"),
)

for f in report.findings:
    print(f.status.value, f.code, f.text, f.replacements, f.legal_basis)
```

`report.to_dict()` — сериализуемый отчёт:

```json
{
  "rules_version": "2026.10.19.1",
  "dictionary_version": "1102-р + 757-р + 1406-р",
  "has_likely_violation": true,
  "context": {"legal_surface": "public_information"},
  "findings": [
    {"code": "public-info-not-russian", "status": "LIKELY_VIOLATION",
     "line": 1, "column": 10,
     "legal_basis": ["ЗоЗПП ст. 10.1 п. 2", "53-ФЗ ч. 2 ст. 3"], "confidence": "medium"}
  ]
}
```

## Django

```python
from django.db import models
from fz168_linter.django_validators import FZ168Validator

class Page(models.Model):
    title = models.CharField(
        max_length=200,
        validators=[FZ168Validator(legal_surface="public_information")],
    )
```

Валидатор пропускает `NO_ISSUE_FOUND`/`NOT_APPLICABLE` и блокирует `LIKELY_VIOLATION`.
`NEEDS_REVIEW` не блокируется — это сигнал для редактора.

## Skill для LLM-агентов

- **Claude Code:** скопировать `skills/fz168-compliance` в `.claude/skills/`.
- **Cursor:** правила уже в `.cursor/rules/fz168-compliance.mdc`.
- **Другие агенты:** вставить `skills/fz168-compliance/SKILL.md` в системный контекст.

Skill задаёт агенту порядок: определить контекст, вызвать линтер, не выдумывать нормы
и санкции, не переписывать официальные названия автоматически и отдавать результат
в формате «статус + норма + вариант + что уточнить».

## Модель контекста

```json
{
  "legal_surface": "advertisement | public_information | internal | unknown",
  "entity_roles": ["developer", "advertiser", "seller"],
  "object_type": "residential_complex | building | other | unknown",
  "ddu_fundraising_ad": true,
  "commissioned_before": "2025-01-31",
  "trademark_status": "registered | application | none | unknown"
}
```

Все поля опциональны. Если контекст не задан, латиница получает `NEEDS_REVIEW`,
а не приговор.

Дата ввода принимается строго в формате `YYYY-MM-DD`. Ошибки значений и названий
полей контекста отклоняются. Для исключения товарного знака укажите одновременно
`trademark_status="registered"` и конкретное обозначение в `extra_trademarks`.
В CLI это `--trademark registered --trademark-word "Your Brand"`. Заявка и
неподтверждённый статус не дают автоматического исключения.

Русский дубль ищется как полная соседняя фраза в одном текстовом блоке.
Линтер не вычисляет CSS и динамический JavaScript. Поддержка исходной разметки
и её ограничения описаны в [docs/PARSING.md](docs/PARSING.md).

## Данные и лицензии

- Код — MIT.
- Словарные данные — **отдельно** от кода: в репозитории только небольшой проверяемый
  набор правил, без массового извлечения из словарей.
- Перечень нормативных словарей и их версии — [docs/DATA.md](docs/DATA.md).
- Свои бренды — `extra_trademarks` в API или `--trademark-word` в CLI вместе
  с подтверждённым статусом регистрации; новые
  правила — JSON в пакете (см. [docs/RULES.md](docs/RULES.md)).

## Источники

- 168-ФЗ: [публикация № 0001202506240035](http://publication.pravo.gov.ru/document/0001202506240035)
- нормативные словари: [ruslang.ru](https://ruslang.ru/normativnyje_slovari)
- [1102-р](https://publication.pravo.gov.ru/document/0001202505060013),
  [757-р](https://publication.pravo.gov.ru/document/0001202604100026),
  [1406-р](https://publication.pravo.gov.ru/document/0001202606090042)
- [приказ ФАС № 1079/23](https://fas.gov.ru/attachment/743635/download?1706184971)
- руководство Роспотребнадзора от 02.03.2026 и статус проверки всех источников —
  в [docs/SOURCES.md](docs/SOURCES.md), обновлено 19.10.2026

## Разработка

```bash
python -m unittest discover -s tests -v
```

Правила добавляются в `src/fz168_linter/data/rules_re.json`. Требования к правилу:
`id`, `reason`, `legal_basis`, `confidence`, `source`. Без источника правило не принимается.

Готовые сценарии — в [examples/](examples/README.md).

## Лицензия

MIT. См. [LICENSE](LICENSE).
