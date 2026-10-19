# Примеры

```bash
# HTML-страница: техническая латиница игнорируется, видимая метка — нет
fz168 check examples/page.html --input html --surface public_information

# Markdown: код и ссылки игнорируются
fz168 check examples/article.md --input markdown --surface public_information

# Рекламный текст
fz168 check examples/ad.txt --surface advertisement

# Контекст недвижимости включается явно
fz168 check examples/card.txt --surface advertisement \
  --object-type residential_complex --ddu-ad

# JSON для CI
fz168 check examples/page.html --input html --surface public_information --format json
```

Ожидаемое поведение:

- `page.html` — срабатывание только на видимый текст `Sale`, но не на классы,
  `href` и URL;
- `article.md` — срабатывание только на видимую метку, но не на код и ссылки;
- `ad.txt` — `NEEDS_REVIEW` как иностранный текст в рекламе;
- `card.txt` — правила 214-ФЗ применяются только к названию объекта, остальная
  латиница идёт как рекламный текст.
