import os
import feedparser
import requests

# Ключи из «сейфа» GitHub Secrets
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID")

# Источники новостей (можно добавлять свои)
RSS_FEEDS = [
    "https://lenta.ru/rss/news",
    "https://ria.ru/export/rss2/archive/index.xml",
]


def get_latest_news():
    """Берёт первую попавшуюся свежую новость из списка RSS-лент."""
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            if feed.entries:
                entry = feed.entries[0]
                title = entry.get("title", "")
                summary = entry.get("summary", entry.get("description", ""))
                return title, summary
        except Exception as e:
            print(f"Ошибка чтения {feed_url}: {e}")
    return None, None


def rewrite_with_gemini(title, summary):
    """Переписывает новость через Gemini."""
    # --- ИЗМЕНЕНИЕ: Убираем ключ из URL и добавляем заголовок ---
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
    
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY,
    }

    prompt = f"""Ты — редактор новостного Telegram-канала.
Перепиши новость кратко, живым языком, до 500 символов.
Добавь 1-2 эмодзи в начало. Дай только готовый пост, без пояснений.

Заголовок: {title}
Текст: {summary}
"""
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    # --- ИЗМЕНЕНИЕ: Передаем заголовки в запросе ---
    response = requests.post(url, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    data = response.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


def send_to_telegram(text):
    """Отправляет готовый пост в канал."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHANNEL_ID,
        "text": text,
        "parse_mode": "HTML",
    }
    response = requests.post(url, json=payload, timeout=30)
    response.raise_for_status()


def main():
    title, summary = get_latest_news()
    if not title:
        print("Не удалось получить новости. Проверьте RSS-ленты.")
        return

    print(f"Взята новость: {title}")
    post = rewrite_with_gemini(title, summary)
    print(f"Готовый пост:\n{post}")

    send_to_telegram(post)
    print("Пост отправлен в Telegram.")


if __name__ == "__main__":
    main()
