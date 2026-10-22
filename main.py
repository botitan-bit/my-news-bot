import os
import feedparser
import requests
import re

API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()

RSS_FEEDS = [
    "https://lenta.ru/rss/news",
    "https://ria.ru/export/rss2/archive/index.xml",
    # Ваши Telegram-каналы через RSS-Bridge
]

SIGNATURE = '<a href="https://t.me/ваш_канал">Ваш канал</a>'

def get_media_from_entry(entry):
    """Ищет видео или картинку в записи RSS."""
    # 1. Ищем видео в enclosures (самый надежный источник)
    if 'enclosures' in entry:
        for enc in entry.enclosures:
            enc_type = enc.get('type', '')
            if 'video' in enc_type:
                return 'video', enc.get('href')
    
    # 2. Если видео нет, ищем картинку в HTML
    summary = entry.get('summary', entry.get('description', ''))
    img_match = re.search(r'<img[^>]+src="([^">]+)"', summary)
    if img_match:
        return 'image', img_match.group(1)
    
    return None, None

def get_latest_news():
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            if feed.entries:
                entry = feed.entries[0]
                title = entry.get("title", "")
                summary = entry.get("summary", entry.get("description", ""))
                
                media_type, media_url = get_media_from_entry(entry)
                
                # Очищаем текст
                summary = re.sub(r'<[^>]+>', '', summary)
                return title, summary, media_type, media_url
        except Exception as e:
            print(f"Ошибка чтения {feed_url}: {e}")
    return None, None, None, None

def rewrite_with_ai(title, summary):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/",
        "X-Title": "News Bot",
    }

    prompt = f"""Ты — редактор новостного Telegram-канала.
Перепиши новость кратко, живым языком, до 400 символов.
Начни пост с заголовка, обернув его в HTML-тег <b>...</b>.
Затем добавь 1-2 эмодзи и краткий текст новости.
Не используй другие HTML-теги, кроме <b>.
Дай только готовый пост, без пояснений.

Заголовок: {title}
Текст: {summary}
"""
    payload = {
        "model": "openrouter/free",
        "messages": [{"role": "user", "content": prompt}]
    }
    response = requests.post(url, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    data = response.json()
    post_text = data["choices"][0]["message"]["content"]
    return f"{post_text}\n\n{SIGNATURE}"

def send_video(video_url, caption):
    """Пытается отправить видео. Если не получается — возвращает False."""
    # Пробуем отправить по URL (лимит 20 МБ)
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"
    payload = {
        "chat_id": TELEGRAM_CHANNEL_ID,
        "video": video_url,
        "caption": caption,
        "parse_mode": "HTML",
        "supports_streaming": True
    }
    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        return True
    except requests.exceptions.HTTPError as e:
        print(f"Не удалось отправить видео по URL: {e}. Пробуем скачать...")
    
    # Если по URL не вышло (например, файл >20 МБ), скачиваем и отправляем файлом (лимит 50 МБ)
    try:
        print("Скачиваем видео...")
        video_data = requests.get(video_url, timeout=60).content
        
        if len(video_data) > 50 * 1024 * 1024:
            print("Видео слишком большое (>50 МБ), пропускаем.")
            return False
            
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"
        files = {'video': ('video.mp4', video_data)}
        data = {
            "chat_id": TELEGRAM_CHANNEL_ID,
            "caption": caption,
            "parse_mode": "HTML",
            "supports_streaming": True
        }
        response = requests.post(url, data=data, files=files, timeout=60)
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"Ошибка при скачивании/отправке файла: {e}")
        return False

def send_to_telegram(text, media_type, media_url):
    # Если есть видео — пробуем отправить его
    if media_type == 'video' and media_url:
        if send_video(media_url, text):
            print("Видео успешно отправлено.")
            return
        else:
            print("Не удалось отправить видео, отправляем только текст.")

    # Если есть картинка — отправляем фото
    elif media_type == 'image' and media_url:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        payload = {
            "chat_id": TELEGRAM_CHANNEL_ID,
            "photo": media_url,
            "caption": text,
            "parse_mode": "HTML",
        }
        try:
            response = requests.post(url, json=payload, timeout=30)
            response.raise_for_status()
            print("Фото успешно отправлено.")
            return
        except Exception as e:
            print(f"Не удалось отправить фото: {e}, отправляем текст.")

    # Резервный вариант — только текст
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHANNEL_ID,
        "text": text,
        "parse_mode": "HTML",
    }
    response = requests.post(url, json=payload, timeout=30)
    response.raise_for_status()
    print("Текст отправлен.")

def main():
    title, summary, media_type, media_url = get_latest_news()
    if not title:
        print("Не удалось получить новости. Проверьте RSS-ленты.")
        return

    print(f"Взята новость: {title}")
    if media_type:
        print(f"Найдено медиа: {media_type} -> {media_url}")
    else:
        print("Медиа не найдено, будет только текст.")

    post = rewrite_with_ai(title, summary)
    send_to_telegram(post, media_type, media_url)

if __name__ == "__main__":
    main()
