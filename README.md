# fz168-linter

[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Status: beta](https://img.shields.io/badge/status-beta-orange.svg)](#ограничения)

**Предварительная проверка текстов, интерфейсов и карточек недвижимости на языковые риски
по 168-ФЗ.** Python-линтер + словари правил + skill для LLM-агентов (Claude Code, Cursor).

> Инструмент выявляет **признаки** и указывает правовое основание. Он не является
> юридическим заключением и не гарантирует отсутствие нарушений.

---

## Что делает

- находит латиницу в текстах, HTML/JSX-шаблонах и Markdown, не реагируя на `class`, `id`,
  `href`, URL, e-mail и код;
- обнаруживает **смешанные алфавиты** (гомоглифы): латинская `a` внутри «Пaрк»;
- сверяет кириллические заимствования с локальным словарём и выдаёт варианты замены;
- учитывает **правовой контекст**: реклама, публичная информация потребителя, внутренний
  интерфейс; ЖК в рекламе долевого строительства; зарегистрированный товарный знак;
  дату ввода объекта;
- возвращает машинно-читаемый отчёт с `legal_basis`, `rule_id`, `confidence` и позициями
  символов **в исходной строке** (до любой нормализации).

## Чего инструмент не делает

- не назначает штраф: связка «нарушение → санкция» не автоматическая (см. [docs/LEGAL.md](docs/LEGAL.md));
- не определяет законность названия ЖК: нужны дата ввода, характер рекламы, правовой
  статус обозначения;
- не проверяет визуальное оформление (кегль, цвет, разборчивость) — только текст;
- не заменяет слова в длинных текстах: падежи и смысл проверяет редактор;
- не содержит полного корпуса нормативных словарей (см. [docs/DATA.md](docs/DATA.md)).

---

## Правовая основа: коротко

| Норма | Что требует | Кто проверяет | Реальное последствие |
|---|---|---|---|
| 214-ФЗ, п. 7 ст. 2 (введён ст. 4 168-ФЗ) | Наименование объекта/ЖК, которое застройщик планирует использовать в рекламе привлечения средств дольщиков, — **только кириллица** | УФАС (в части рекламы), органы стройнадзора | Специальный состав в КоАП не установлен; квалификация требует отдельной проверки |
| ЗоЗПП, ст. 10.1 (введена ст. 1 168-ФЗ) | Публичная **нерекламная** информация потребителю — на русском языке; иностранный язык только как дубль по ч. 2 ст. 3 53-ФЗ | Роспотребнадзор | ч. 1 ст. 14.8 КоАП: юрлица 5–10 тыс. ₽, предупреждение; предписание, затем ч. 1 ст. 19.5: 10–20 тыс. ₽ |
| 38-ФЗ, ч. 11 ст. 5 | Реклама — на русском языке | ФАС | ч. 1 ст. 14.3: юрлица 100–500 тыс. ₽, **но** приказ ФАС № 1079/23: дело только по ч. 11 ст. 5 не возбуждается |
| 53-ФЗ, ч. 2 ст. 3 | Дублирование: идентичность содержания и равнозначность размещения/оформления | применяется через ст. 10.1 ЗоЗПП | — |

Полный разбор с цитатами, датами и нерешёнными вопросами — [docs/LEGAL.md](docs/LEGAL.md).

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
# текст из файла, публичная информация потребителю
fz168 check page.html --input html --surface public_information

# карточка ЖК в рекламе долевого строительства
fz168 check card.txt --surface advertisement \
  --object-type residential_complex --ddu-ad --commissioned 2024-05-01

# JSON-отчёт для CI
fz168 check README.md --input markdown --format json
```

Пример вывода:

```
LIKELY_VIOLATION public-info-not-russian 12:7 "Sale"
  Публичная информация потребителя без русского текста (ЗоЗПП ст. 10.1 п. 2).
  Варианты: Распродажа, Акция
```

Код выхода: `1`, если есть `LIKELY_VIOLATION`, иначе `0`.

## Python API

```python
from fz168_linter import Context, check_text

report = check_text(
    "В ЖК Prime Park вас ждёт лобби и отделка White Box.",
    Context(
        legal_surface="advertisement",
        object_type="residential_complex",
        ddu_fundraising_ad=True,
        commissioned_before=None,
        trademark_status="unknown",
    ),
)

for f in report.findings:
    print(f.status.value, f.code, f.text, f.replacements, f.legal_basis)
```

`report.to_dict()` — сериализуемый отчёт:

```json
{
  "rules_version": "2026.10.19",
  "dictionary_version": "1102-р + 757-р + 1406-р",
  "has_likely_violation": true,
  "context": {"legal_surface": "advertisement"},
  "findings": [
    {"code": "naming-214fz", "status": "LIKELY_VIOLATION", "line": 1, "column": 6,
     "legal_basis": ["214-ФЗ п. 7 ст. 2"], "confidence": "high"}
  ]
}
```

## Django

```python
from django.db import models
from fz168_linter.django_validators import FZ168Validator

class ResidentialComplex(models.Model):
    name = models.CharField(
        max_length=200,
        validators=[FZ168Validator(
            legal_surface="advertisement",
            object_type="residential_complex",
            ddu_fundraising_ad=True,
        )],
    )
```

Валидатор пропускает `NO_ISSUE_FOUND`/`NOT_APPLICABLE` и блокирует `LIKELY_VIOLATION`.
`NEEDS_REVIEW` не блокируется — это сигнал для редактора.

## Skill для LLM-агентов

- **Claude Code:** скопировать `skills/fz168-compliance` в `.claude/skills/`.
- **Cursor:** правила уже в `.cursor/rules/fz168-compliance.mdc`.
- **Другие агенты:** вставить `skills/fz168-compliance/SKILL.md` в системный контекст.

Skill заставляет агента: определить контекст, вызвать линтер, не выдумывать штрафы,
не переименовывать ЖК автоматически и отдавать результат в формате «статус + норма +
вариант + что уточнить».

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

Флаги независимы: одна компания может быть застройщиком, продавцом и рекламодателем.

## Данные и лицензии

- Код — MIT.
- Словарные данные — **отдельно** от кода: в репозитории только небольшой проверяемый
  набор правил, без массового извлечения из словарей.
- Перечень нормативных словарей и их версии — [docs/DATA.md](docs/DATA.md).
- Свои бренды — `extra_trademarks` в API или `--trademark-word` в CLI; новые
  правила — JSON в пакете (см. [docs/RULES.md](docs/RULES.md)).

## Ограничения

- равнозначность оформления (кегль, цвет, разборчивость) проверяется только глазами;
- переходное исключение 214-ФЗ содержит неоднозначность даты (разобрано в [docs/LEGAL.md](docs/LEGAL.md));
- применимость ст. 14.28 КоАП к наименованиям требует отдельной квалификации;
- контекст задаётся вызывающей стороной: из текста его не вывести.

## Источники

- 168-ФЗ: [публикация № 0001202506240035](http://publication.pravo.gov.ru/document/0001202506240035)
- нормативные словари: [ruslang.ru](https://ruslang.ru/normativnyje_slovari)
- 1102-р, 757-р, 1406-р: [pravo.gov.ru](http://publication.pravo.gov.ru/document/0001202505060013)
- приказ ФАС № 1079/23 — руководства по соблюдению обязательных требований в сфере рекламы
- разъяснения Роспотребнадзора (март 2026) — в [docs/SOURCES.md](docs/SOURCES.md)

## Разработка

```bash
python -m unittest discover -s tests -v
```

Правила добавляются в `src/fz168_linter/data/rules_re.json`. Требования к правилу:
`id`, `reason`, `legal_basis`, `confidence`, `source`. Без источника правило не принимается.

Готовые сценарии — в [examples/](examples/README.md).

## Лицензия

MIT. См. [LICENSE](LICENSE).
