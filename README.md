# 🎙️ Alice + Gemini Skill (Алиса на базе Google Gemini)

[![CI Test Suite](https://github.com/egle282/alisagemini/actions/workflows/ci.yml/badge.svg)](https://github.com/egle282/alisagemini/actions)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Google GenAI](https://img.shields.io/badge/Google-GenAI%20SDK-4285F4.svg)](https://ai.google.dev/)
[![Yandex Dialogs](https://img.shields.io/badge/Yandex-Dialogs-red.svg)](https://dialogs.yandex.ru/)

Полнофункциональный приватный навык для голосового помощника **Яндекс Алиса** (Яндекс Станции, умные колонки, ТВ и приложения Яндекса), подключенный напрямую к моделям **Google Gemini 3.5 / 2.5** через современный официальный SDK `google-genai`.

---

## ✨ Возможности

- 🚀 **Мгновенный голосовой доступ к Gemini**: решение сложных задач, генерация кода, объяснение концепций и диалоги через умную колонку.
- ⚡ **Соблюдение жесткого SLA Алисы**: строгий таймаут генерации (~2.5–3.5 сек) с превентивной защитой от обрыва сессии.
- 🎯 **Специализированный System Prompt**:
  - Без markdown-символов (`*`, `#`, `_`), которые ломают синтез речи (TTS) Алисы.
  - Ограничение до 600 символов для комфортного озвучивания голосом.
  - По запросу «напиши код» выдается чистый код без лишних вступлений.
- 🧠 **Память диалога**: локальное хранение контекста последних реплик пользователя.
- 🌍 **Готовое решение для РФ (Bypass Geoblock)**: встроенная поддержка проксирования через бесплатный **Cloudflare Worker** для обхода ошибки Google `400 User location is not supported`.
- ☁️ **Двойной сценарий развертывания**:
  - Бессерверный запуск 24/7 в **Yandex Cloud Functions** (`main.handler`).
  - Локальный запуск или VPS через **FastAPI** + **Uvicorn** (`main.app`).

---

## 🏗️ Архитектура

```
Пользователь (Яндекс Станция)
         │
         ▼
 Яндекс.Диалоги (Webhook)
         │
         ▼
 Yandex Cloud Functions (или FastAPI на VPS / ngrok)
         │
         ▼
 Cloudflare Worker (Прокси для обхода геоблокировки Google в РФ)
         │
         ▼
 Google Gemini API (gemini-3.5-flash-lite)
```

---

## 🚀 Быстрый старт (За 10 минут)

### 1. Предварительные требования
- Python 3.12+
- Бесплатный API-ключ Google AI Studio ([aistudio.google.com](https://aistudio.google.com/))
- Аккаунт Яндекс (к которому привязана колонка)

---

### 2. Клонирование и локальная установка

```bash
git clone https://github.com/egle282/alisagemini.git
cd alisagemini/alice-gemini-skill

# Создание виртуального окружения
python3 -m venv .venv
source .venv/bin/activate

# Установка зависимостей
pip install -r requirements.txt
```

---

### 3. Настройка переменных окружения

Скопируйте шаблон:
```bash
cp .env.example .env
```

Заполните `.env`:
```ini
GEMINI_API_KEY=ваш_ключ_из_Google_AI_Studio
GEMINI_MODEL=gemini-3.5-flash-lite
TEMPERATURE=0.3
MAX_OUTPUT_TOKENS=350
MAX_RESPONSE_LENGTH=600
GEMINI_TIMEOUT_SECONDS=3.5
PORT=8000

# Если запускаете из РФ без прямого VPN, укажите URL вашего Cloudflare Worker:
# GEMINI_BASE_URL=https://your-proxy.workers.dev
```

---

### 4. Решение проблемы с геоблокировкой (для РФ)

Если бессерверная функция запускается в **Yandex Cloud** (серверы в РФ), Google API вернет ошибку `400 User location is not supported`.  
Решается за 2 минуты через бесплатный **Cloudflare Worker**:

1. Зайдите в [dash.cloudflare.com](https://dash.cloudflare.com/) → **Workers & Pages** → **Create Application**.
2. Вставьте код:
```javascript
export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    url.hostname = 'generativelanguage.googleapis.com';
    url.port = '443';
    url.protocol = 'https:';

    const modifiedRequest = new Request(url.toString(), {
      method: request.method,
      headers: request.headers,
      body: request.body,
      redirect: 'follow',
    });

    return fetch(modifiedRequest);
  },
};
```
3. Нажмите **Deploy** и скопируйте URL воркера: `https://your-worker-name.workers.dev`.
4. Укажите этот адрес в переменной окружения `GEMINI_BASE_URL`.

---

### 5. Развертывание в Yandex Cloud Functions (Production 24/7)

1. Соберите архив для деплоя:
```bash
cd alice-gemini-skill
zip -r skill.zip main.py config.py gemini_client.py requirements.txt
```
2. Откройте [Yandex Cloud Console](https://console.yandex.cloud/) → выберите каталог → **Cloud Functions** → **Создать функцию**.
   - **Имя**: `alice-gemini-skill`
   - **Среда выполнения**: `Python 3.12`
   - **Способ загрузки**: `ZIP-архив` (загрузите `skill.zip`)
   - **Точка входа**: `main.handler`
   - **Таймаут**: `5` сек
   - **Память**: `512` МБ
3. В блоке **Переменные окружения** добавьте:
   - `GEMINI_API_KEY`: ваш ключ
   - `GEMINI_MODEL`: `gemini-3.5-flash-lite`
   - `GEMINI_BASE_URL`: `https://your-worker.workers.dev` *(при необходимости обхода гео-ограничений)*
4. Нажмите **Сохранить изменения**.
5. Во вкладке **Обзор** включите **«Публичная функция»** и скопируйте **Ссылку для вызова** (`https://functions.yandexcloud.net/...`).

---

### 6. Настройка в Яндекс.Диалогах (Подключение к колонке)

1. Откройте [dialogs.yandex.ru/developer](https://dialogs.yandex.ru/developer) под тем же аккаунтом, к которому привязана ваша Яндекс Станция.
2. Нажмите **Создать диалог** → **Навык в Алисе**:
   - **Название**: `Джемини` (или любое желаемое имя активации)
   - **Активационные фразы**: `запусти навык джемини`, `включи навык джемини`
   - **Backend**: выберите **Webhook URL** и вставьте ссылку на Cloud Function
   - **Тип доступа**: **Приватный** *(не требует модерации, сразу работает на всех ваших устройствах)*
3. Нажмите **Сохранить**.

---

### 7. Использование голосом 🎙️

Подойдите к умной колонке:
> 🗣️ **— «Алиса, запусти навык Джемини»**  
> 🤖 *— «Привет! Я подключена к Gemini. Спроси меня о чём угодно, включая код.»*  
>  
> 🗣️ **— «Объясни квантовую запутанность простыми словами»**  
> 🗣️ **— «Напиши функцию сортировки списка на Python»**  
>  
> 🗣️ **— «Хватит»** *(выход из навыка)*

---

## 🧪 Тестирование

Проект покрыт полным набором модульных и интеграционных тестов:

```bash
cd alice-gemini-skill
pytest -v
```

Тестируются:
- Обработка новых сессий и приветствия.
- Корректная очистка markdown-тегов под голосовой синтез.
- Обработка таймаутов API и гарантированный возврат фразы-заглушки.
- Корректная работа точки входа `main.handler` для форматов Yandex Cloud Functions и Яндекс.Диалогов.

---

## 🔒 Безопасность

- Никакие приватные ключи (`.env`, `*.zip`, кэши) не отслеживаются в Git (настроены правила `.gitignore`).
- Для передачи секретов в продакшене используются переменные окружения облачной платформы или Yandex Lockbox.

---

## 📄 Лицензия

Распространяется под лицензией [MIT](LICENSE).
