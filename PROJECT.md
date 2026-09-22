# SMM Agent — Описание проекта

## Общая информация

AI-агент для генерации СММ-контента. Ищет виральные темы, пишет посты в авторском стиле, создаёт кино-карусели с постерами.

**Веб-интерфейс:** `http://7589191-dy849118.twc1.net:8000`

**Репозиторий:** `/root/.openclaw/workspace/smm-agent/`

## Стек

| Компонент | Технология |
|---|---|
| LLM | OpenAI-совместимый API (gpt-5.4-nano) через proxyapi.ru |
| Поиск | Brave Search API |
| Бэкенд | Python, FastAPI, uvicorn |
| Фронтенд | Jinja2 + Tailwind CSS |
| Рендер слайдов | Pillow (PIL) + numpy |
| Шрифты | DejaVu Sans (Bold/Regular) |

## Модели

Все задачи работают через одну модель — **gpt-5.4-nano** через proxyapi.ru.

| Задача | Модель | Провайдер |
|---|---|---|
| Поиск тем (research) | gpt-5.4-nano | proxyapi.ru |
| Написание постов | gpt-5.4-nano | proxyapi.ru |
| Хуки | gpt-5.4-nano | proxyapi.ru |
| Карусели (текст) | gpt-5.4-nano | proxyapi.ru |
| Переработка контента | gpt-5.4-nano | proxyapi.ru |

> Не связан с z.ai/GLM — отдельный счёт через OpenAI API ключ.

## Структура проекта

```
smm-agent/
├── main.py                    # CLI entry point + web server launch
├── config.yaml                # Конфигурация (модель, API, пути)
├── requirements.txt
├── AGENTS.md                  # Инструкции для OpenClaw-агента + правила учётных файлов
├── PROJECT.md                 # ← Описание и состояние проекта
├── PROGRESS.md                # Журнал прогресса: снимок статуса, вехи, фокус
├── feature-list.json          # Машиночитаемый реестр фич и статусов
├── CHANGELOG.md               # Ежедневник правок
├── .env                       # API ключи (OPENAI_API_KEY, BRAVE_API_KEY, GITHUB_TOKEN)
│
├── src/
│   ├── api/
│   │   └── llm.py             # LLM-клиент (OpenAI chat completions)
│   ├── research/
│   │   └── researcher.py      # Поиск виральных тем через Brave + LLM
│   ├── writers/
│   │   ├── carousel_writer.py # Генерация каруселей (текст + рендер PNG-слайдов)
│   │   ├── content_repurposer.py  # Переработка контента
│   │   ├── hook_writer.py     # Генерация хуков
│   │   └── post_writer.py     # Генерация постов
│   └── web/
│       ├── app.py             # FastAPI приложение (роуты, API)
│       ├── static/            # CSS, JS
│       └── templates/         # Jinja2 шаблоны страниц
│
├── skills/                    # Скиллы (промпты для LLM)
│   ├── cinema-post-writer/    # Кино-посты (Threads формат)
│   ├── truecrime-post-writer/ # Тру-крайм посты (развёрнутый формат)
│   ├── carousel-writer-sms/   # Структура каруселей
│   ├── hook-writer-sms/       # 9 паттернов хуков
│   ├── post-writer-sms/       # Универсальный пост-райтер
│   ├── content-repurposer-sms/# Переработка контента
│   └── social-media-context-sms/  # Контекст голоса/тона
│
├── data/
│   ├── style_samples/         # Профили стиля + примеры постов
│   │   ├── style-profile-cinema.md
│   │   ├── style-profile-true-crime.md
│   │   ├── cinema-examples.md
│   │   ├── STYLE-ANALYSIS-cinema.md
│   │   └── STYLE-ANALYSIS-true-crime.md
│   ├── output/                # Сгенерированные слайды (PNG), логи
│   │   ├── carousels.jsonl    # История каруселей
│   │   └── queue.jsonl        # Очередь задач для OpenClaw-агента
│   ├── social-media-context.md # Описание голоса/тона/контент-пилларов
│   ├── system_prompt.md       # Кастомный системный промпт
│   └── generations.jsonl      # Лог всех генераций
│
└── _social-media-skills/      # Git-субмодуль (исходные скиллы BlackTwist)
```

## Функционал

### Веб-интерфейс (порт 8000)

| Страница | URL | Описание |
|---|---|---|
| Главная | `/` | Быстрая генерация поста |
| Пост | `/post` | Генерация поста с настройками |
| Хуки | `/hooks` | Генерация цепляющих заголовков |
| Карусель | `/carousel` | Кино-карусели: текст → поиск постеров → PNG слайды |
| Ресёрч | `/research` | Поиск виральных тем |
| Переработка | `/repurpose` | Адаптация контента под платформы |
| Настройки | `/settings` | Редактирование контекста и системного промпта |

### API

| Endpoint | Method | Описание |
|---|---|---|
| `/api/post` | POST | Создать задачу на пост (в очередь) |
| `/api/hooks` | POST | Сгенерировать хуки |
| `/api/carousel` | POST | Шаг 1: текст карусели (без картинок) |
| `/api/carousel/correct` | POST | Исправить карусель по тексту |
| `/api/carousel/render` | POST | Шаг 2: рендер PNG слайдов |
| `/api/research` | POST | Поиск виральных тем |
| `/api/repurpose` | POST | Переработка контента |
| `/api/generations` | GET/POST/DELETE | Лог генераций |
| `/api/carousels` | GET/DELETE | История каруселей |
| `/api/style-samples` | GET | Примеры стиля |
| `/api/save-context` | POST | Сохранить контекст |
| `/api/save-system-prompt` | POST | Сохранить системный промпт |
| `/api/upload-style-sample` | POST | Загрузить пример стиля |

## Темы контента

- **Кино** — рецензии, подборки, новости кино. Формат Threads (до 500 символов)
- **Тру-крайм** — нераскрытые дела, серийные убийцы. Развёрнутый формат

## Рендер слайдов каруселей

Формат: 1080×1080 PNG (Instagram square)

Алгоритм `render_poster_slide()`:
1. Постер масштабируется с обрезкой до 1080×1080 (cover crop)
2. Нижние ~33% — гауссов блюр (radius=22) с плавным переходом на нет (~12% зона fade)
3. Нижние ~40% — градиентное затемнение (alpha 0→230)
4. Накладывается текст: название фильма (bold, 52px) + описание (regular, ~31px)
5. Шрифт — DejaVu Sans

## Состояние проекта

**Статус:** Активная разработка

**Что работает:**
- ✅ CLI для всех типов генерации
- ✅ Веб-интерфейс (FastAPI + Tailwind)
- ✅ Два стиля: кино и тру-крайм
- ✅ Кино-карусели с автоматическим поиском постеров и рендером PNG
- ✅ Плавный блюр + затемнение нижней трети слайдов
- ✅ История генераций и каруселей (JSONL)
- ✅ Очередь задач для OpenClaw-агента
- ✅ Корректировка каруселей через веб-интерфейс
- ✅ Автоматическое определение русских названий через Kinopoisk

**TODO (из README):**
- ⬜ Автопостинг (Telegram Bot API, Instagram Graph API)
- ⬜ Scheduled generation через cron
- ⬜ A/B тестирование хуков
- ⬜ Аналитика вовлечённости
- ⬜ DALL-E / Midjourney генерация обложек

**Известные проблемы:**
- Иногда LLM возвращает невалидный JSON при генерации карусели (есть retry × 3)
- Шрифт DejaVu не поддерживает все Unicode-глифы (может потребоваться Noto Sans)
