# Примеры

```bash
# Карточка ЖК в рекламе долевого строительства
fz168 check examples/card.txt --surface advertisement \
  --object-type residential_complex --ddu-ad

# HTML-кнопка в публичном интерфейсе
fz168 check examples/button.html --input html --surface public_information

# Markdown: код и ссылки игнорируются
fz168 check examples/snippet.md --input markdown --surface public_information

# JSON для CI
fz168 check examples/card.txt --surface advertisement \
  --object-type residential_complex --ddu-ad --format json
```

Ожидаемое поведение:

- в `card.txt` — `LIKELY_VIOLATION` на латинское название ЖК и `NEEDS_REVIEW`
  на заимствования;
- в `button.html` — срабатывание только на видимый текст `Sale`, но не на
  `class="sale"` и не на `href`;
- в `snippet.md` — ни одного срабатывания на код и URL.
