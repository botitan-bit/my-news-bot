import os
import feedparser
import requests
import re
import sys

API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()

# 👇 ТУТ ВАШИ ИСТОЧНИКИ (СМИ + Телеграм-каналы ведомств)
RSS_FEEDS = [
    "https://lenta.ru/rss/news",
    "https://ria.ru/export/rss2/archive/index.xml",
    "https://tass.ru/rss/v2.xml",
    # Официальные каналы через RSS-Bridge (МЧС, МВД, ФСБ)
    "https://rss-bridge.org/bridge01/?action=display&bridge=TelegramBridge&username=mchs_official&format=Atom",
    "https://rss-bridge.org/bridge01/?action=display&bridge=TelegramBridge&username=mvd_official&format=Atom",
    "https://rss-bridge.org/bridge01/?action=display&bridge=TelegramBridge&username=fsb_official&format=Atom",
]

# 👇 ВАША ПОДПИСЬ (ссылка уже вставлена)
SIGNATURE = '<a href="https://t.me/pervonovosti">👉 Первый новостной</a>'

# 👇 ТЕМЫ И КЛЮЧЕВЫЕ СЛОВА
THEMES = {
    "Политика": ["политик", "власть", "кремль", "госдума", "президент", "правительство", "выборы", "санкции", "переговоры", "мид"],
    "СВО": ["сво", "специальная военная операция", "военный", "армия", "всу", "дрон", "бпла", "ракета", "обстрел", "фронт", "мобилизация", "минобороны"],
    "Мигранты": ["мигрант", "миграция", "иностранц", "приезж", "гражданство", "патент", "гастарбайтер"],
    "Происшествия": ["происшеств", "авария", "дтп", "пожар", "взрыв", "чп", "катастрофа", "погиб", "пострадал", "крушение", "чрезвычайный", "преступление"]
}

# Порядок чередования
THEME_ORDER = ["Политика", "СВО", "Мигранты", "Происшествия"]

def get_media_from_entry(entry):
    """Ищет видео или картинку в записи RSS."""
    if 'enclosures' in entry:
        for enc in entry.enclosures:
            if 'video' in enc.get('type', ''):
                return 'video', enc.get('href')
    
    summary = entry.get('summary', entry.get('description', ''))
    img_match = re.search(r'<img[^>]+src="([^">]+)"', summary)
    if img_match:
        return 'image', img_match.group(1)
    return None, None

def is_theme_match(text, theme):
    """Проверяет текст на наличие ключевых слов."""
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in THEMES[theme])

def get_news_for_theme(theme):
    """Ищет новость с медиа по заданной теме."""
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:20]: # Проверяем 20 последних новостей
                title = entry.get("title", "")
                summary = entry.get("summary", entry.get("description", ""))
                full_text = f"{title} {summary}"
                
                if is_theme_match(full_text, theme):
                    media_type, media_url = get_media_from_entry(entry)
                    if media_type: 
                        summary_clean = re.sub(r'<[^>]+>', '', summary)
                        return title, summary_clean, media_type, media_url
        except Exception as e:
            print(f"Ошибка чтения {feed_url}: {e}")
    return None, None, None, None

def rewrite_with_ai(title, summary, theme):
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
Рубрика новости: {theme}.
Не используй другие HTML-теги, кроме <b>.
Дай только готовый пост, без пояснений.

Заголовок: {title}
Текст: {summary}
"""
    payload = {"model": "openrouter/free", "messages": [{"role": "user", "content": prompt}]}
    response = requests.post(url, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    return f"{response.json()['choices'][0]['message']['content']}\n\n{SIGNATURE}"

def send_video(video_url, caption):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"
    payload = {"chat_id": TELEGRAM_CHANNEL_ID, "video": video_url, "caption": caption, "parse_mode": "HTML", "supports_streaming": True}
    try:
        requests.post(url, json=payload, timeout=30).raise_for_status()
        return True
    except requests.exceptions.HTTPError:
        pass
    
    try:
        video_data = requests.get(video_url, timeout=60).content
        if len(video_data) > 50 * 1024 * 1024: return False
        files = {'video': ('video.mp4', video_data)}
        data = {"chat_id": TELEGRAM_CHANNEL_ID, "caption": caption, "parse_mode": "HTML", "supports_streaming": True}
        requests.post(url, data=data, files=files, timeout=60).raise_for_status()
        return True
    except Exception:
        return False

def send_to_telegram(text, media_type, media_url):
    if media_type == 'video' and media_url:
        if send_video(media_url, text): return
        print("Не удалось отправить видео. Пост отменен.")
    elif media_type == 'image' and media_url:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        payload = {"chat_id": TELEGRAM_CHANNEL_ID, "photo": media_url, "caption": text, "parse_mode": "HTML"}
        try:
            requests.post(url, json=payload, timeout=30).raise_for_status()
        except Exception:
            print("Не удалось отправить фото. Пост отменен.")

def get_last_theme():
    if os.path.exists("last_theme.txt"):
        with open("last_theme.txt", "r", encoding="utf-8") as f:
            return f.read().strip()
    return THEME_ORDER[-1]

def save_last_theme(theme):
    with open("last_theme.txt", "w", encoding="utf-8") as f:
        f.write(theme)

def main():
    last_theme = get_last_theme()
    try:
        last_index = THEME_ORDER.index(last_theme)
    except ValueError:
        last_index = -1
    next_index = (last_index + 1) % len(THEME_ORDER)
    
    for i in range(len(THEME_ORDER)):
        current_index = (next_index + i) % len(THEME_ORDER)
        theme = THEME_ORDER[current_index]
        
        print(f"Ищем новость по теме: {theme}")
        title, summary, media_type, media_url = get_news_for_theme(theme)
        
        if title:
            print(f"Найдена: {title}")
            post = rewrite_with_ai(title, summary, theme)
            send_to_telegram(post, media_type, media_url)
            save_last_theme(theme)
            print(f"Опубликовано! Следующая тема: {theme}")
            return
        
    print("Не найдено новостей с медиа. Пропускаем.")
    sys.exit(0)

if __name__ == "__main__":
    main()
