# SMM Agent 🖤

AI-агент для генерации СММ-контента. Ищет виральные темы, пишет посты в авторском стиле, создаёт карусели с генерацией изображений. Работает через CLI и веб-интерфейс.

## Возможности

- **research** — поиск виральных тем (тру-крайм, кино) через Brave Search + LLM-фильтрация
- **post** — генерация постов для Telegram, Instagram, Threads с учётом платформы и стиля автора
- **hooks** — цепляющие хуки по 9 паттернам (contrarian, question, story, statistic, etc.)
- **carousel** — карусели: текст + рендер слайдов с изображениями (`--design dark_modern`)
- **repurpose** — переработка контента под разные платформы и форматы
- **context** — управление голосом, тоном и контент-пилларами

Два профильных направления:
- 🎬 **Кино** — обзоры, подборки, рекомендации
- 🔍 **Тру-крайм** — нераскрытые дела, расследования

## Установка

```bash
cd smm-agent
pip install -r requirements.txt
```

## Настройка

1. Заполни `config.yaml` — провайдер LLM, модель, тема контента, платформы
2. Задай переменные окружения:

```bash
export OPENAI_API_KEY=your-key        # LLM API (по умолчанию ProxyAPI → OpenAI)
export BRAVE_API_KEY=your-key         # Brave Search для research
```

3. (Опционально) Добавь примеры стиля в `data/style_samples/`
4. (Опционально) Отредактируй `data/social-media-context.md` — голос и тон
5. (Опционально) Отредактируй `data/system_prompt.md` — системный промпт

## Веб-интерфейс

```bash
python main.py web
# → http://localhost:8000
```

Страницы: посты, хуки, карусели (с рендером), research, переработка, настройки (контекст, промпт, примеры стиля).

### Запуск как сервис (systemd)

```bash
cat > ~/.config/systemd/user/smm-agent.service << 'EOF'
[Unit]
Description=SMM Agent Web
After=network-online.target

[Service]
WorkingDirectory=/path/to/smm-agent
ExecStart=/usr/bin/python3 -c "from src.web.app import run; run(host='0.0.0.0', port=8000)"
Restart=always
EnvironmentFile=/path/to/smm-agent/.env

[Install]
WantedBy=default.target
EOF

systemctl --user enable --now smm-agent
```

## CLI

```bash
# Поиск виральных тем
python main.py research "тру-крайм новости"
python main.py research --save

# Генерация поста
python main.py post "Почему сериал всё убил" -p telegram
python main.py post "5 фильмов для пересмотра" -p instagram -t educational

# Генерация хуков
python main.py hooks "новый фильм с Хоакином Фениксом" -n 7

# Карусель (только текст)
python main.py carousel "10 жутких нераскрытых дел" -p instagram -s 10

# Карусель (текст + рендер слайдов)
python main.py carousel "10 жутких нераскрытых дел" --design dark_modern

# Переработка контента
python main.py repurpose "текст поста..." --platforms telegram,instagram --formats post,carousel

# Управление контекстом
python main.py context --show
python main.py context --edit

# Веб-сервер
python main.py web
```

## Структура

```
smm-agent/
├── main.py                    # CLI entry point
├── config.yaml                # Конфигурация (LLM, Brave, пути, генерация)
├── requirements.txt
├── skills/                    # SMM-скиллы (промпты и правила)
│   ├── hook-writer-sms/       # 9 паттернов хуков
│   ├── post-writer-sms/       # Генерация постов под платформу
│   ├── carousel-writer-sms/   # Структура слайдов (cover → CTA)
│   ├── content-repurposer-sms/# Переработка контента
│   ├── social-media-context-sms/
│   ├── cinema-post-writer/    # Кастомный скилл: кино-посты
│   └── truecrime-post-writer/ # Кастомный скилл: тру-крайм
├── src/
│   ├── api/llm.py             # LLM-клиент (OpenAI-compatible)
│   ├── research/researcher.py # Поиск + LLM-фильтрация тем
│   ├── writers/               # Генераторы контента
│   │   ├── post_writer.py
│   │   ├── hook_writer.py
│   │   ├── carousel_writer.py # Текст + рендер изображений (Pillow)
│   │   └── content_repurposer.py
│   └── web/                   # FastAPI веб-интерфейс
│       ├── app.py             # Роуты, API, шаблоны
│       ├── templates/         # Jinja2: post, hooks, carousel, research, ...
│       └── static/
├── data/
│   ├── style_samples/         # Профили стиля (кино, тру-крайм) + примеры
│   ├── output/                # Сгенерированный контент и карусели
│   ├── social-media-context.md
│   ├── system_prompt.md
│   └── generations.jsonl      # Лог всех генераций
└── _social-media-skills/      # Git-субмодуль (исходные скиллы BlackTwist)
```

## Скиллы

Основа — [blacktwist/social-media-skills](https://github.com/blacktwist/social-media-skills). Кастомные скиллы:

- **cinema-post-writer** — обзоры фильмов и сериалов, подборки, рекомендации
- **truecrime-post-writer** — дела, расследования, нераскрытые преступления

## Конфигурация

Основные поля `config.yaml`:

| Параметр | Описание |
|---|---|
| `llm.provider` | Провайдер (`openai` / `custom`) |
| `llm.model` | Модель (по умолчанию `gpt-5.4-nano`) |
| `llm.base_url` | URL API (ProxyAPI, OpenAI, совместимый) |
| `brave.api_key` | Ключ Brave Search для research |
| `platforms` | Целевые платформы: telegram, instagram, threads |
| `generation.temperature` | Креативность (0.8 по умолчанию) |
| `generation.carousel_slides` | Кол-во слайдов по умолчанию (10) |
| `research.max_topics` | Сколько тем искать за раз (5) |

## TODO

- [ ] Автопостинг (Telegram Bot API, Instagram Graph API)
- [ ] Scheduled generation через cron
- [ ] A/B тестирование хуков
- [ ] Аналитика вовлечённости
