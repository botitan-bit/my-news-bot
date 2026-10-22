import os
import feedparser
import requests
import re
import sys
import html
import time
from urllib.parse import urljoin
from datetime import datetime, timezone, timedelta

API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()

RSS_FEEDS = [
    "https://lenta.ru/rss/news",
    "https://ria.ru/export/rss2/archive/index.xml",
    "https://tass.ru/rss/v2.xml",
    "https://rss-bridge.org/bridge01/?action=display&bridge=TelegramBridge&username=mchs_official&format=Atom",
    "https://rss-bridge.org/bridge01/?action=display&bridge=TelegramBridge&username=mvd_official&format=Atom",
    "https://rss-bridge.org/bridge01/?action=display&bridge=TelegramBridge&username=fsb_official&format=Atom",
]

SIGNATURE = '<b><a href="https://t.me/+l7bgzfXgngBkN2My">ПЕРВЫЕ НОВОСТИ</a></b>'

THEMES = {
    "Политика": ["политик", "власть", "кремль", "госдума", "президент", "путин", "правительство", "мишустин", "выборы", "санкции", "переговоры", "мид", "лавров", "песков", "законопроект", "депутат", "сенатор", "оппозиция", "протест", "нато", "сша", "европа", "брифинг", "саммит", "дипломат", "парламент"],
    "СВО": ["сво", "спецоперация", "специальная военная", "военный", "армия", "всу", "дрон", "бпла", "беспилотник", "ракета", "обстрел", "фронт", "мобилизация", "минобороны", "шойгу", "белоусов", "курск", "донбасс", "авдеевка", "артемовск", "бахмут", "херсон", "запорожье", "наступление", "штурм", "снаряд", "танк", "авиация", "пво", "боевик", "разведка"],
    "Мигранты": ["мигрант", "миграция", "иностранц", "приезж", "гражданство", "патент", "гастарбайтер", "диаспора", "депортация", "вид на жительство", "рвп", "квота", "трудовые ресурсы", "нелегал"],
    "Происшествия": ["происшеств", "авария", "дтп", "пожар", "взрыв", "чп", "катастрофа", "погиб", "пострадал", "крушение", "чрезвычайный", "преступление", "убийство", "теракт", "уголовное дело", "задержан", "суд", "следствие", "скорая", "спасатели", "мчс", "мвд", "фсб", "розыск", "эвакуация"]
}
THEME_ORDER = ["Политика", "СВО", "Мигранты", "Происшествия"]

PRIMARY_MODEL = "qwen/qwen3.6-plus-preview:free"
FALLBACK_MODEL = "openrouter/free"

def get_posted_links():
    if os.path.exists("posted_news.txt"):
        with open("posted_news.txt", "r", encoding="utf-8") as f:
            return f.read().splitlines()
    return []

def save_posted_link(link):
    with open("posted_news.txt", "a", encoding="utf-8") as f:
        f.write(link + "\n")

def get_last_theme():
    if os.path.exists("last_theme.txt"):
        with open("last_theme.txt", "r", encoding="utf-8") as f:
            return f.read().strip()
    return THEME_ORDER[-1]

def save_last_theme(theme):
    with open("last_theme.txt", "w", encoding="utf-8") as f:
        f.write(theme)

def get_media_from_entry(entry, feed_url):
    if 'enclosures' in entry:
        for enc in entry.enclosures:
            url = enc.get('href', '')
            if url:
                url = urljoin(feed_url, url)
                if 'video' in enc.get('type', ''): return 'video', url
                if 'image' in enc.get('type', ''): return 'image', url

    if 'media_content' in entry:
        for media in entry.media_content:
            url = media.get('url', '')
            if url:
                url = urljoin(feed_url, url)
                if media.get('medium') == 'image' or 'image' in media.get('type', ''): return 'image', url
                if media.get('medium') == 'video' or 'video' in media.get('type', ''): return 'video', url

    if 'media_thumbnail' in entry:
        for thumb in entry.media_thumbnail:
            url = thumb.get('url', '')
            if url: return 'image', urljoin(feed_url, url)

    html_to_search = ""
    if 'content' in entry:
        for content_block in entry.content:
            html_to_search += content_block.get('value', '')
    html_to_search += entry.get('summary', entry.get('description', ''))

    img_match = re.search(r'<img[^>]+src="([^">]+)"', html_to_search)
    if img_match:
        return 'image', urljoin(feed_url, img_match.group(1))

    return None, None

def is_theme_match(text, theme):
    text_lower = text.lower()
    for keyword in THEMES[theme]:
        if re.search(r'\b' + re.escape(keyword), text_lower):
            return True
    return False

def is_old_news(title, summary):
    current_year = datetime.now().year
    text = f"{title} {summary}".lower()
    
    years = re.findall(r'\b(20\d{2})\b', text)
    for year in years:
        if int(year) < current_year:
            return True
    return False

def get_news_candidates(theme):
    posted_links = get_posted_links()
    now = datetime.now(timezone.utc)
    candidates = []
    
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:30]:
                link = entry.get("link", "")
                if link in posted_links:
                    continue

                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    pub_time = time.mktime(entry.published_parsed)
                    pub_date = datetime.fromtimestamp(pub_time, timezone.utc)
                    # 👇 ТУТ ИЗМЕНЕНО НА 6 ЧАСОВ
                    if now - pub_date > timedelta(hours=6):
                        continue
                else:
                    continue

                title = entry.get("title", "")
                summary = entry.get("summary", entry.get("description", ""))
                
                if is_old_news(title, summary):
                    print(f"Отсеяна старая новость (упоминание прошлых лет): {title}")
                    continue

                full_text = f"{title} {summary}"
                
                if is_theme_match(full_text, theme):
                    media_type, media_url = get_media_from_entry(entry, feed_url)
                    if media_type:
                        summary_clean = re.sub(r'<[^>]+>', '', summary)
                        candidates.append({
                            "title": title,
                            "summary": summary_clean,
                            "media_type": media_type,
                            "media_url": media_url,
                            "link": link
                        })
                        if len(candidates) >= 5:
                            return candidates
        except Exception as e:
            print(f"Ошибка чтения {feed_url}: {e}")
    return candidates

def call_openrouter(prompt):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/",
        "X-Title": "News Bot",
    }
    
    for model in [PRIMARY_MODEL, FALLBACK_MODEL]:
        payload = {"model": model, "messages": [{"role": "user", "content": prompt}]}
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            return response.json()['choices'][0]['message']['content'].strip()
        except Exception as e:
            print(f"⚠️ Ошибка при использовании модели {model}: {e}")
            print("🔄 Пробуем следующую модель...")
            
    print("❌ Все доступные модели вернули ошибку.")
    return ""

def pick_most_important(candidates):
    if not candidates:
        return None
    
    titles_list = "\n".join([f"{i}. {c['title']}" for i, c in enumerate(candidates)])
    
    prompt = f"""Ты — главный редактор новостного канала.
Вот список заголовков новостей:
{titles_list}

Выбери ОДИН самый важный, значимый и интересный для страны/мира заголовок. 
Игнорируй мелкие бытовые происшествия, желтуху, шоу-бизнес и незначительные события.
Ответь ТОЛЬКО цифрой (от 0 до {len(candidates)-1}), без лишних слов."""
    
    answer = call_openrouter(prompt)
    match = re.search(r'\d+', answer)
    if match:
        idx = int(match.group())
        if 0 <= idx < len(candidates):
            return candidates[idx]
            
    return candidates[0]

def sanitize_html(text):
    text = text.replace('<b>', '||BOLD_START||').replace('</b>', '||BOLD_END||')
    text = html.escape(text)
    text = text.replace('||BOLD_START||', '<b>').replace('||BOLD_END||', '</b>')
    return text

def rewrite_with_ai(title, summary, theme):
    prompt = f"""Ты — профессиональный, строгий редактор крупного новостного Telegram-канала.
Перепиши новость информативно, литературным русским языком, без сленга и желтухи.
Исправь грамматические и фактические ошибки исходного текста.
Будь деликатен. Не используй вульгарные или нецензурные выражения.

Требования к посту:
1. Начни с краткого и понятного заголовка, обернутого в HTML-тег <b>...</b>. Без кликбейта.
2. После закрывающего тега </b> ОБЯЗАТЕЛЬНО сделай ДВА переноса строки (оставь пустую строку).
3. Затем добавь 1-2 уместных эмодзи и краткий текст новости (суть, факты).
4. Объем текста — до 400 символов.
5. Дай только готовый пост, без твоих комментариев и вступлений.

Рубрика: {theme}
Заголовок: {title}
Текст: {summary}
"""
    raw_text = call_openrouter(prompt)
    
    if not raw_text:
        raw_text = f"<b>{title}</b>\n\n{summary}"
        
    raw_text = re.sub(r'</b>\s*', '</b>\n\n', raw_text)
    raw_text = raw_text[:800]
    safe_text = sanitize_html(raw_text)
    
    return f"{safe_text}\n\n{SIGNATURE}"

def send_photo(photo_url, caption):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    payload = {"chat_id": TELEGRAM_CHANNEL_ID, "photo": photo_url, "caption": caption, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=30)
        if r.status_code == 200: return True
    except: pass
    
    try:
        img_data = requests.get(photo_url, timeout=60).content
        files = {'photo': ('image.jpg', img_data)}
        data = {"chat_id": TELEGRAM_CHANNEL_ID, "caption": caption, "parse_mode": "HTML"}
        r = requests.post(url, data=data, files=files, timeout=60)
        if r.status_code == 200: return True
    except: pass
    return False

def send_video(video_url, caption):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"
    payload = {"chat_id": TELEGRAM_CHANNEL_ID, "video": video_url, "caption": caption, "parse_mode": "HTML", "supports_streaming": True}
    try:
        r = requests.post(url, json=payload, timeout=30)
        if r.status_code == 200: return True
    except: pass
    
    try:
        video_data = requests.get(video_url, timeout=60).content
        if len(video_data) > 50 * 1024 * 1024: return False
        files = {'video': ('video.mp4', video_data)}
        data = {"chat_id": TELEGRAM_CHANNEL_ID, "caption": caption, "parse_mode": "HTML", "supports_streaming": True}
        r = requests.post(url, data=data, files=files, timeout=60)
        if r.status_code == 200: return True
    except: pass
    return False

def send_to_telegram(text, media_type, media_url):
    if media_type == 'video' and media_url:
        if send_video(media_url, text): return True
    elif media_type == 'image' and media_url:
        if send_photo(media_url, text): return True

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHANNEL_ID, 
        "text": text, 
        "parse_mode": "HTML",
        "disable_web_page_preview": True 
    }
    try:
        r = requests.post(url, json=payload, timeout=30)
        if r.status_code == 200: return True
        else: print(f"Ошибка отправки текста: {r.text}")
    except Exception as e:
        print(f"Критическая ошибка: {e}")
    return False

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
        
        print(f"Ищем кандидатов по теме: {theme}")
        candidates = get_news_candidates(theme)
        
        if candidates:
            print(f"Найдено {len(candidates)} кандидатов. Отправляем ИИ на оценку важности...")
            best_news = pick_most_important(candidates)
            
            if best_news:
                print(f"ИИ выбрал самую важную: {best_news['title']}")
                post = rewrite_with_ai(best_news['title'], best_news['summary'], theme)
                print(f"Сгенерированный текст:\n{post}\n")
                
                success = send_to_telegram(post, best_news['media_type'], best_news['media_url'])
                
                if success:
                    save_last_theme(theme)
                    save_posted_link(best_news['link'])
                    print(f"Опубликовано! Следующая тема: {theme}")
                    return
        
    print("Не удалось найти свежие новости (моложе 6 часов). Пропускаем запуск.")
    sys.exit(0)

if __name__ == "__main__":
    main()
