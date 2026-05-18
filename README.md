# SMM Agent 🖤

AI-агент для генерации СММ-контента. Ищет виральные темы, пишет посты в авторском стиле, создаёт карусели.

## Что умеет

- **research** — поиск виральных тем (тру-крайм, кино, что угодно) через web search + LLM-фильтрация
- **post** — генерация постов для Telegram, Instagram, Threads с учётом платформы
- **hooks** — генерация цепляющих хуков по 9 паттернам
- **carousel** — создание каруселей (текст + дизайн слайдов)
- **repurpose** — переработка контента под разные платформы/форматы
- **context** — управление стилем и голосом

## Установка

```bash
cd smm-agent
pip install -r requirements.txt
```

## Настройка

1. Скопируй и заполни конфиг:
```bash
cp config.yaml config.yaml
# Отредактируй: API ключ, модель, тему
```

2. Установи API ключ:
```bash
export OPENAI_API_KEY=sk-...
# Или для Brave Search:
export BRAVE_API_KEY=...
```

3. (Опционально) Добавь примеры своего стиля в `data/style_samples/`

4. (Опционально) Создай `data/social-media-context.md` с описанием голоса/тона

## Использование

```bash
# Поиск виральных тем
python main.py research "тру-крайм новости"
python main.py research --save

# Генерация поста
python main.py post "Почему сериал Делла Гоут оф всё убил" -p telegram
python main.py post "5 фильмов которые стоит пересмотреть" -p instagram -t educational

# Генерация хуков
python main.py hooks "новый фильм с Хоакином Фениксом" -n 7

# Карусель (только текст)
python main.py carousel "10 самых жутких нераскрытых дел" -p instagram -s 10

# Карусель (текст + генерация картинок)
python main.py carousel "10 самых жутких нераскрытых дел" --design dark_modern

# Переработка контента
python main.py repurpose "текст поста..." --platforms telegram,instagram --formats post,carousel

# Управление контекстом стиля
python main.py context --show
python main.py context --edit
```

## Структура

```
smm-agent/
├── main.py              # CLI entry point
├── config.yaml          # Конфигурация
├── requirements.txt
├── skills/              # BlackTwist SMM skills
│   ├── hook-writer-sms/
│   ├── carousel-writer-sms/
│   ├── post-writer-sms/
│   ├── content-repurposer-sms/
│   └── social-media-context-sms/
├── src/
│   ├── api/llm.py       # LLM API клиент
│   ├── research/         # Поиск виральных тем
│   └── writers/          # Посты, хуки, карусели, переработка
├── data/
│   ├── style_samples/   # Примеры стиля автора
│   ├── output/          # Сгенерированный контент
│   ├── social-media-context.md  # Голос, тон, контент-пиллары
│   └── system_prompt.md # Кастомный системный промпт
└── _social-media-skills/ # Git-субмодуль (исходные скиллы)
```

## Скиллы

Используются скиллы из [blacktwist/social-media-skills](https://github.com/blacktwist/social-media-skills):

- **hook-writer-sms** — 9 паттернов хуков (contrarian, question, story, statistic, etc.)
- **post-writer-sms** — генерация постов под платформу
- **carousel-writer-sms** — структура слайдов (cover → context → body → CTA)
- **content-repurposer-sms** — переработка контента между форматами
- **social-media-context-sms** — контекст голоса/тона

## TODO

- [ ] Автопостинг (Telegram Bot API, Instagram Graph API)
- [ ] Scheduled generation через cron
- [ ] A/B тестирование хуков
- [ ] Аналитика вовлечённости
- [ ] DALL-E / Midjourney генерация обложек каруселей
