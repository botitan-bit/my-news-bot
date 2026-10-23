import os
import feedparser
import requests
import re
import sys
import html
import time
import io
import vk_api
import urllib3
from vk_api.upload import VkUpload
from urllib.parse import urljoin
from datetime import datetime, timezone, timedelta

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
VK_TOKEN = os.environ.get("VK_TOKEN", "").strip()
VK_GROUP_ID = os.environ.get("VK_GROUP_ID", "").strip()
MAX_BOT_TOKEN = os.environ.get("MAX_BOT_TOKEN", "").strip()
MAX_CHANNEL_ID = os.environ.get("MAX_CHANNEL_ID", "").strip()

POST_PHOTO_TO_VK = True

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
    "СВО": ["спецоперация", "специальная военная", "военный", "армия", "всу", "дрон", "бпла", "беспилотник", "ракета", "обстрел", "фронт", "мобилизация", "минобороны", "шойгу", "белоусов", "курск", "донбасс", "авдеевка", "артемовск", "бахмут", "херсон", "запорожье", "наступление", "штурм", "снаряд", "танк", "авиация", "пво", "боевик", "разведка"],
    "Мигранты": ["мигрант", "миграция", "иностранц", "приезж", "гражданство", "патент", "гастарбайтер", "диаспора", "депортация", "вид на жительство", "рвп", "квота", "трудовые ресурсы", "нелегал"],
    "Происшествия": ["происшеств", "авария", "дтп", "пожар", "взрыв", "чп", "катастрофа", "погиб", "пострадал", "крушение", "чрезвычайный", "преступление", "убийство", "теракт", "уголовное дело", "задержан", "суд", "следствие", "скорая", "спасатели", "мчс", "мвд", "фсб", "розыск", "эвакуация"]
}
THEME_ORDER = ["Политика", "СВО", "Мигранты", "Происшествия"]

RUSSIA_KEYWORDS = [
    "росси", "рф", "путин", "кремл", "москв", "петербург", "ленинград", "курск", "белгород", 
    "донбасс", "донецк", "луганск", "крым", "севастопол", "херсон", "запорож", "госдум", 
    "совфед", "мид", "минобороны", "росгвард", "фсб", "мвд", "мчс", "чечн", "татарстан", 
    "башкир", "сибир", "урал", "кавказ", "ростов", "краснодар", "самара", "екатеринбург", 
    "новосибирск", "омск", "томск", "иркутск", "якут", "владивосток", "хабаровск", 
    "фронт", "шойгу", "белоусов", "губернатор", "сочи", "камчатк", "чукотк", "перм", "геленджик", "иванов", "нижний новгород", "певек"
]

BLACKLIST_WORDS = [
    "какой сегодня", "какой праздник", "гороскоп", "день рождения", "история дня", 
    "в этот день", "народные приметы", "церковный календарь", "лунный календарь", "именины"
]

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
        if re.search(r'(?:^|[^а-яё])' + re.escape(keyword), text_lower):
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

def is_russia_related(text):
    text_lower = text.lower()
    return any(kw in text_lower for kw in RUSSIA_KEYWORDS)

def is_blacklisted(text):
    text_lower = text.lower()
    return any(word in text_lower for word in BLACKLIST_WORDS)

def get_news_candidates(theme):
    posted_links = get_posted_links()
    now = datetime.now(timezone.utc)
    
    all_entries = []
    for feed_url in RSS_FEEDS:
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            resp = requests.get(feed_url, timeout=10, headers=headers)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
            
            for entry in feed.entries[:60]:
                link = entry.get("link", "")
                if link in posted_links: continue
                
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    pub_time = time.mktime(entry.published_parsed)
                    pub_date = datetime.fromtimestamp(pub_time, timezone.utc)
                    age_hours = (now - pub_date).total_seconds() / 3600
                else:
                    age_hours = 8.0
                
                title = entry.get("title", "")
                summary = entry.get("summary", entry.get("description", ""))
                summary_clean = re.sub(r'<[^>]+>', '', summary).strip()
                
                if is_old_news(title, summary): continue
                if len(summary_clean) < 40: continue
                
                if is_blacklisted(f"{title} {summary_clean}"):
                    continue
                
                media_type, media_url = get_media_from_entry(entry, feed_url)
                full_text = f"{title} {summary}"
                
                all_entries.append({
                    "title": title,
                    "summary": summary_clean,
                    "age_hours": age_hours,
                    "media_type": media_type,
                    "media_url": media_url,
                    "link": link,
                    "theme_match": is_theme_match(full_text, theme),
                    "russia_match": is_russia_related(full_text),
                    "has_media": media_type is not None
                })
        except Exception as e:
            print(f"Ошибка чтения {feed_url}: {e}")
    
    print(f"Собрано всего новостей (прошли базовый фильтр): {len(all_entries)}")
    
    c = [e for e in all_entries if e['age_hours'] <= 6 and e['russia_match'] and e['theme_match'] and e['has_media']]
    if c: return sorted(c, key=lambda e: e['age_hours'])[:5]
    
    c = [e for e in all_entries if e['age_hours'] <= 12 and e['russia_match'] and e['theme_match'] and e['has_media']]
    if c: return sorted(c, key=lambda e: e['age_hours'])[:5]
    
    c = [e for e in all_entries if e['age_hours'] <= 24 and e['russia_match'] and e['theme_match'] and e['has_media']]
    if c: return sorted(c, key=lambda e: e['age_hours'])[:5]

    c = [e for e in all_entries if e['age_hours'] <= 24 and e['russia_match'] and e['has_media']]
    if c: return sorted(c, key=lambda e: e['age_hours'])[:5]
        
    c = [e for e in all_entries if e['age_hours'] <= 24 and e['russia_match']]
    if c: return sorted(c, key=lambda e: e['age_hours'])[:5]
    
    return []

def call_groq(prompt):
    if not GROQ_API_KEY: return ""
        
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    # 👇 АКТУАЛЬНАЯ МОДЕЛЬ GROQ
    payload = {"model": "openai/gpt-oss-120b", "messages": [{"role": "user", "content": prompt}]}
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content'].strip()
    except Exception as e:
        print(f"⚠️ Ошибка или таймаут Groq: {e}")
        return ""

def pick_most_important(candidates):
    if not candidates: return None
    titles_list = "\n".join([f"{i}. {c['title']}" for i, c in enumerate(candidates)])
    
    prompt = f"""Ты главный редактор. Выбери ОДИН самый важный заголовок. 
Игнорируй спорт и мелкие бытовые новости. Ответь ТОЛЬКО цифрой (от 0 до {len(candidates)-1}).
Список:
{titles_list}"""
    
    answer = call_groq(prompt)
    if answer:
        match = re.search(r'\d+', answer)
        if match:
            idx = int(match.group())
            if 0 <= idx < len(candidates): return candidates[idx]
            
    return candidates[0]

def sanitize_html(text):
    text = text.replace('<b>', '||BOLD_START||').replace('</b>', '||BOLD_END||')
    text = html.escape(text)
    text = text.replace('||BOLD_START||', '<b>').replace('||BOLD_END||', '</b>')
    return text

def rewrite_with_ai(title, summary, theme):
    prompt = f"""Ты — профессиональный редактор. Перепиши новость кратко.
Запрещено упоминать источники и писать служебные слова.
Формат ответа:
1. Заголовок в теге <b>...</b>.
2. ДВА переноса строки.
3. 1-2 эмодзи и краткий текст.

Исходный заголовок: {title}
Исходный текст: {summary}
"""
    raw_text = call_groq(prompt)
    
    if not raw_text:
        print("⚠️ ИИ недоступен. Применяем страховку (сырой текст).")
        # 👇 ОЧИЩАЕМ ЗАГОЛОВОК ОТ ТЕГОВ ПЕРЕД СТРАХОВКОЙ
        clean_title = re.sub(r'<[^>]+>', '', title).strip()
        clean_summary = summary.strip()
        if len(clean_summary) > 600: clean_summary = clean_summary[:600] + "..."
        return sanitize_html(f"<b>{clean_title}</b>\n\n📰 {clean_summary}")
        
    raw_text = re.sub(r'^(Category|Рубрика|Категория):.*?\n', '', raw_text, flags=re.IGNORECASE)
    for pattern in [r'—\s*в материале[^.]*\.', r'—\s*подробнее[^.]*\.', r'—\s*читайте[^.]*\.', r'—\s*на сайте[^.]*\.', r'сообщает[^.]*\.', r'источник:[^\n]*']:
        raw_text = re.sub(pattern, '', raw_text, flags=re.IGNORECASE)

    raw_text = re.sub(r'</b>\s*', '</b>\n\n', raw_text)
    raw_text = raw_text.replace('\\n', '\n')
    raw_text = raw_text[:900]
    
    return sanitize_html(raw_text)
# ... (остальные функции send_photo, send_video, send_to_telegram, send_to_vk, send_to_max и main остаются без изменений)
