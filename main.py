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
from bs4 import BeautifulSoup
from vk_api.upload import VkUpload
from urllib.parse import urljoin
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(line_buffering=True)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
VK_TOKEN = os.environ.get("VK_TOKEN", "").strip()
VK_GROUP_ID = os.environ.get("VK_GROUP_ID", "").strip()
MAX_BOT_TOKEN = os.environ.get("MAX_BOT_TOKEN", "").strip()
MAX_CHANNEL_ID = os.environ.get("MAX_CHANNEL_ID", "").strip()

POST_PHOTO_TO_VK = True

PRIORITY_FEEDS = [
    "https://rss-bridge.org/bridge01/?action=display&bridge=TelegramBridge&username=pilachzx&format=Atom",
    "https://rss-bridge.org/bridge01/?action=display&bridge=TelegramBridge&username=slavaded1337&format=Atom",
    "https://rss-bridge.org/bridge01/?action=display&bridge=TelegramBridge&username=novosti_efir&format=Atom",
    "https://rss-bridge.org/bridge01/?action=display&bridge=TelegramBridge&username=botcharov&format=Atom",
    "https://rss-bridge.org/bridge01/?action=display&bridge=TelegramBridge&username=mnogonazi&format=Atom",
    "https://rss-bridge.org/bridge01/?action=display&bridge=TelegramBridge&username=SHOCKkzn&format=Atom",
]

RSS_FEEDS = [
    "https://lenta.ru/rss/news",
    "https://ria.ru/export/rss2/archive/index.xml",
    "https://www.mk.ru/rss/index.xml",
    "https://life.ru/rss.xml",
    "https://ren.tv/rss",
    "https://rss-bridge.org/bridge01/?action=display&bridge=TelegramBridge&username=mash&format=Atom",
    "https://rss-bridge.org/bridge01/?action=display&bridge=TelegramBridge&username=bazabazon&format=Atom",
    "https://rss-bridge.org/bridge01/?action=display&bridge=TelegramBridge&username=shot_shot&format=Atom",
]

SIGNATURE_TG = '<b><a href="https://t.me/+l7bgzfXgngBkN2My">ПЕРВЫЕ НОВОСТИ</a></b>'
SIGNATURE_MAX = '**[ПЕРВЫЕ НОВОСТИ](https://t.me/+l7bgzfXgngBkN2My)**'

THEMES = {
    "СВО и Армия": ["сво", "дрон", "бпла", "ракета", "фронт", "минобороны", "всу", "штурм", "обстрел", "пво", "сводка", "наступление", "потери", "мобилизация", "армия", "военный", "беспилотник"],
    "Катастрофы": ["погиб", "жертв", "катастрофа", "крушение", "авиакатастрофа", "обрушение", "наводнение", "ураган", "смерч", "теракт", "взрыв", "пожар", "спасатели", "мчс", "эвакуация", "чрезвычайный"],
    "Криминал": ["убийство", "труп", "задержан", "арестован", "банда", "наркотик", "коррупция", "взятка", "мошенничество", "суд", "приговор", "разбой", "ограбление", "стрельба", "погоня", "разборка", "конфликт", "маньяк", "расчленил", "избил", "изнасиловал"],
    "Мигранты": ["мигрант", "миграция", "иностранц", "депортация", "патент", "гастарбайтер", "диаспора", "приезж", "гражданство", "нелегал", "инородец"],
    "Иноагенты": ["иноагент", "нежелательная организация", "экстремист", "госдеп", "иностранное финансирование", "пособник", "шпион", "предатель"],
    "ДТП и Аварии": ["дтп", "авария", "лобовое", "столкновение", "сбил", "насмерть", "травмы", "скорая", "госпитализирован", "перевернулся", "врезался", "мотоцикл", "пьяный водитель", "сбил пешехода"]
}
THEME_ORDER = ["СВО и Армия", "Катастрофы", "Криминал", "Мигранты", "Иноагенты", "ДТП и Аварии"]

RUSSIA_KEYWORDS = [
    "росси", "рф", "путин", "кремл", "москв", "петербург", "ленинград", "курск", "белгород", 
    "донбасс", "донецк", "луганск", "крым", "севастопол", "херсон", "запорож", "госдум", 
    "совфед", "мид", "минобороны", "росгвард", "фсб", "мвд", "мчс", "чечн", "татарстан", 
    "башкир", "сибир", "урал", "кавказ", "ростов", "краснодар", "самара", "екатеринбург", 
    "новосибирск", "омск", "томск", "иркутск", "якут", "владивосток", "хабаровск", 
    "фронт", "шойгу", "белоусов", "губернатор", "сочи", "камчатк", "чукотк", "перм", "геленджик", "иванов", "нижний новгород", "певек"
]

# 👇 РАСШИРЕННЫЙ ЧЕРНЫЙ СПИСОК (Добавлен официальный канцелярит и скука)
BLACKLIST_WORDS = [
    "какой сегодня", "какой праздник", "гороскоп", "день рождения", "история дня", 
    "в этот день", "народные приметы", "церковный календарь", "лунный календарь", "именины",
    "заседание", "законопроект", "бюджет", "форум", "выставка", "конференция", "экономика", "инфляция", "курс валют",
    "спорт", "гонщик", "гонка", "автоспорт", "футбол", "хоккей", "олимпиад", "чемпионат", "турнир", "матч", "клуб", "тренер",
    "шоу-бизнес", "актер", "актриса", "певец", "певица", "звезда", "сериал", "фильм", "премьера", "инстаграм", "тикток",
    "спектакль", "ледовый", "фигурист", "авербух", "петросян", "концерт", "развлечение", "шоу", "праздник", "фестиваль", "выступление",
    "продолжают спецоперацию", "выполняют задачи", "боевая готовность", "полная готовность", "активные действия", "выполняют боевые задачи", "решают задачи", "контроль над ситуацией",
    "автобус", "маршрутка", "прямой эфир", "прямая трансляция", "смотрите эфир", "ожидается эфир",
    "визит", "совещание", "рабочая поездка", "подписал", "вручил", "обсудил", "поздравил", "открыл", "посетил", "заявление", "пресс-конференция", "круглый стол" # 👈 НОВЫЕ СЛОВА
]

def ensure_state_files_exist():
    for file in ["last_theme.txt", "posted_news.txt", "published_titles.txt", "posted_images.txt", "posted_videos.txt", "posted_hashes.txt"]:
        if not os.path.exists(file):
            open(file, 'a').close()

def get_text_hash(text):
    clean_text = re.sub(r'[^\w\s]', '', text.lower())
    words = clean_text.split()
    return " ".join(words[:10])

def get_posted_hashes():
    if os.path.exists("posted_hashes.txt"):
        with open("posted_hashes.txt", "r", encoding="utf-8") as f:
            return f.read().splitlines()
    return []

def save_posted_hash(text_hash):
    if not text_hash: return
    with open("posted_hashes.txt", "a", encoding="utf-8") as f:
        f.write(text_hash + "\n")

def get_posted_links():
    if os.path.exists("posted_news.txt"):
        with open("posted_news.txt", "r", encoding="utf-8") as f:
            return f.read().splitlines()
    return []

def save_posted_link(link):
    with open("posted_news.txt", "a", encoding="utf-8") as f:
        f.write(link + "\n")

def get_posted_videos():
    if os.path.exists("posted_videos.txt"):
        with open("posted_videos.txt", "r", encoding="utf-8") as f:
            return f.read().splitlines()
    return []

def save_posted_video(url):
    if not url: return
    with open("posted_videos.txt", "a", encoding="utf-8") as f:
        f.write(url + "\n")

def get_posted_images():
    if os.path.exists("posted_images.txt"):
        with open("posted_images.txt", "r", encoding="utf-8") as f:
            return f.read().splitlines()
    return []

def clean_image_url(url):
    if not url: return ""
    return url.split('?')[0].strip()

def save_posted_image(url):
    clean_url = clean_image_url(url)
    if not clean_url: return
    with open("posted_images.txt", "a", encoding="utf-8") as f:
        f.write(clean_url + "\n")

def get_recent_titles():
    if os.path.exists("published_titles.txt"):
        with open("published_titles.txt", "r", encoding="utf-8") as f:
            return f.read().splitlines()
    return []

def save_published_title(title):
    with open("published_titles.txt", "a", encoding="utf-8") as f:
        f.write(title + "\n")
    titles = get_recent_titles()
    if len(titles) > 15:
        with open("published_titles.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(titles[-15:]) + "\n")

def get_last_theme():
    if os.path.exists("last_theme.txt"):
        with open("last_theme.txt", "r", encoding="utf-8") as f:
            return f.read().strip()
    return THEME_ORDER[-1]

def save_last_theme(theme):
    with open("last_theme.txt", "w", encoding="utf-8") as f:
        f.write(theme)

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

def get_tg_web_videos(channel_name, theme, now):
    videos = []
    posted_videos = get_posted_videos()
    posted_hashes = get_posted_hashes()
    
    url = f"https://t.me/s/{channel_name}"
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        resp = requests.get(url, timeout=10, headers=headers)
        if resp.status_code != 200:
            return []
        
        soup = BeautifulSoup(resp.text, "html.parser")
        posts = soup.select(".tgme_widget_message[data-post]")
        
        if not posts:
            return []
        
        for post in reversed(posts):
            video_url = None
            
            video_tag = post.select_one("video[src]")
            if video_tag and video_tag.get("src"):
                video_url = video_tag.get("src")
            
            if not video_url:
                video_link = post.select_one("a.tgme_widget_message_video_player")
                if video_link and video_link.get("href"):
                    video_url = video_link.get("href")
            
            if not video_url:
                video_thumb = post.select_one("i.tgme_widget_message_video_thumb")
                if video_thumb and video_thumb.get("style"):
                    match = re.search(r"url\('([^']+)'\)", video_thumb.get("style", ""))
                    if match:
                        video_url = match.group(1)
            
            if not video_url:
                continue
            
            if video_url.startswith("//"):
                video_url = "https:" + video_url
            
            if video_url in posted_videos:
                continue
            
            text_tag = post.select_one(".tgme_widget_message_text")
            if not text_tag:
                continue
            
            clean_text = text_tag.get_text("\n", strip=True)
            if len(clean_text) < 20:
                continue
                
            text_hash = get_text_hash(clean_text)
            if text_hash in posted_hashes:
                continue
                
            post_id = post.get("data-post", "")
            post_link = f"https://t.me/{post_id}"
            
            if is_blacklisted(clean_text): continue
            if not is_russia_related(clean_text): continue
            if not is_theme_match(clean_text, theme): continue
            
            videos.append({
                "title": clean_text[:60] + "...",
                "summary": clean_text,
                "age_hours": 1.0,
                "media_type": "video",
                "media_url": video_url,
                "link": post_link,
                "text_hash": text_hash,
                "theme_match": True,
                "russia_match": True,
                "has_media": True
            })
        
    except Exception as e:
        pass
    return videos

def process_feeds(feed_list, theme, posted_links, posted_images, posted_hashes, now):
    entries = []
    for feed_url in feed_list:
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            resp = requests.get(feed_url, timeout=10, headers=headers)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
            
            for entry in feed.entries[:60]:
                link = entry.get("link", "")
                if link in posted_links: continue
                
                title = entry.get("title", "")
                
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    pub_time = time.mktime(entry.published_parsed)
                    pub_date = datetime.fromtimestamp(pub_time, timezone.utc)
                    age_hours = (now - pub_date).total_seconds() / 3600
                else:
                    age_hours = 8.0
                
                summary = entry.get("summary", entry.get("description", ""))
                summary_clean = re.sub(r'<[^>]+>', '', summary).strip()
                
                if is_old_news(title, summary): continue
                if len(summary_clean) < 20: continue
                if is_blacklisted(f"{title} {summary_clean}"): continue
                
                full_raw_text = f"{title} {summary_clean}"
                text_hash = get_text_hash(full_raw_text)
                if text_hash in posted_hashes:
                    continue
                
                media_type = None
                media_url = None
                
                if 'enclosures' in entry:
                    for enc in entry.enclosures:
                        url = enc.get('href', '')
                        if url:
                            url = urljoin(feed_url, url)
                            if 'video' in enc.get('type', ''): 
                                media_type, media_url = 'video', url
                                break
                            if 'image' in enc.get('type', ''):
                                media_type, media_url = 'image', url

                if not media_type:
                    html_to_search = ""
                    if 'content' in entry:
                        for content_block in entry.content:
                            html_to_search += content_block.get('value', '')
                    html_to_search += entry.get('summary', entry.get('description', ''))
                    
                    vid_match = re.search(r'(https?://[^\s"<>]+\.mp4)', html_to_search)
                    if vid_match:
                        media_type, media_url = 'video', vid_match.group(1)
                    else:
                        vid_tag_match = re.search(r'<video[^>]+src="([^">]+)"', html_to_search)
                        if vid_tag_match:
                            media_type, media_url = 'video', urljoin(feed_url, vid_tag_match.group(1))
                        else:
                            img_match = re.search(r'<img[^>]+src="([^">]+)"', html_to_search)
                            if img_match:
                                media_type, media_url = 'image', urljoin(feed_url, img_match.group(1))

                if not media_type:
                    continue
                
                if media_type == 'image' and media_url and clean_image_url(media_url) in posted_images:
                    continue
                
                full_text = f"{title} {summary}"
                
                entries.append({
                    "title": title,
                    "summary": summary_clean,
                    "age_hours": age_hours,
                    "media_type": media_type,
                    "media_url": media_url,
                    "link": link,
                    "text_hash": text_hash,
                    "theme_match": is_theme_match(full_text, theme),
                    "russia_match": is_russia_related(full_text),
                    "has_media": True
                })
        except Exception as e:
            pass
    return entries

def get_news_candidates(theme):
    posted_links = get_posted_links()
    posted_images = [clean_image_url(img) for img in get_posted_images()]
    posted_hashes = get_posted_hashes()
    now = datetime.now(timezone.utc)
    
    print(f"  -> Ищем видео в веб-версиях Telegram-каналов...")
    tg_videos = []
    tg_channels = ["pilachzx", "slavaded1337", "novosti_efir", "botcharov", "mnogonazi", "SHOCKkzn", "mash", "bazabazon", "shot_shot"]
    for ch in tg_channels:
        vids = get_tg_web_videos(ch, theme, now)
        tg_videos.extend(vids)
        if len(tg_videos) >= 5:
            break
            
    if tg_videos:
        print(f"🔥 Найдено {len(tg_videos)} ВИДЕО в веб-версиях Telegram!")
        return tg_videos[:5]

    print("  -> Видео в веб-версиях не найдено. Проверяем RSS...")
    priority_entries = process_feeds(PRIORITY_FEEDS, theme, posted_links, posted_images, posted_hashes, now)
    general_entries = process_feeds(RSS_FEEDS, theme, posted_links, posted_images, posted_hashes, now)
    
    all_entries = priority_entries + general_entries
    print(f"Собрано всего новостей (с медиа): {len(all_entries)}")
    
    c_video = [e for e in all_entries if e['age_hours'] <= 12 and e['russia_match'] and e['theme_match'] and e['media_type'] == 'video']
    if c_video: return sorted(c_video, key=lambda e: e['age_hours'])[:5]

    c_img_priority = [e for e in priority_entries if e['age_hours'] <= 12 and e['russia_match'] and e['theme_match'] and e['media_type'] == 'image']
    if c_img_priority: return sorted(c_img_priority, key=lambda e: e['age_hours'])[:5]
    
    c_img_priority_24 = [e for e in priority_entries if e['age_hours'] <= 24 and e['russia_match'] and e['theme_match'] and e['media_type'] == 'image']
    if c_img_priority_24: return sorted(c_img_priority_24, key=lambda e: e['age_hours'])[:5]

    c_img_general = [e for e in general_entries if e['age_hours'] <= 12 and e['russia_match'] and e['theme_match'] and e['media_type'] == 'image']
    if c_img_general: return sorted(c_img_general, key=lambda e: e['age_hours'])[:5]

    c_img_general_24 = [e for e in general_entries if e['age_hours'] <= 24 and e['russia_match'] and e['theme_match'] and e['media_type'] == 'image']
    if c_img_general_24: return sorted(c_img_general_24, key=lambda e: e['age_hours'])[:5]
    
    return []

def call_groq(prompt):
    if not GROQ_API_KEY: return ""
        
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {"model": "openai/gpt-oss-120b", "messages": [{"role": "user", "content": prompt}]}
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content'].strip()
    except Exception as e:
        print(f"⚠️ Ошибка Groq: {e}")
        return ""

def pick_most_important(candidates):
    if not candidates: return None
    
    # 👇 ПЕРЕДАЕМ ИИ ИНФОРМАЦИЮ О ТИПЕ МЕДИА
    titles_list = "\n".join([f"{i}. [{c['media_type']}] {c['title']}" for i, c in enumerate(candidates)])
    
    recent_titles = get_recent_titles()
    history_text = ""
    if recent_titles:
        history_text = "УЖЕ ОПУБЛИКОВАНО РАНЕЕ:\n" + "\n".join(recent_titles) + "\n"
    
    # 👇 ЖЕСТКИЙ ПРОМПТ: ВИДЕО ВСЕГДА В ПРИОРИТЕТЕ
    prompt = f"""Ты — редактор жесткого новостного канала. 
Выбери ОДИН самый интересный заголовок из списка.

ПРАВИЛА ВЫБОРА:
1. Если в списке есть новость с меткой [video] — ОБЯЗАТЕЛЬНО выбирай её. Видео всегда интереснее и важнее для канала.
2. Игнорируй новости про шоу-бизнес, актеров, спорт, концерты, визиты чиновников и скучные совещания.
3. Выбирай только то, что содержит экшн: СВО, криминал, ДТП, катастрофы.

{history_text}

Если ВСЕ новости в списке — это скучный мусор (политика, визиты, спорт) или ОНИ УЖЕ БЫЛИ ОПУБЛИКОВАНЫ, ответь NONE.
В противном случае ответь ТОЛЬКО цифрой (от 0 до {len(candidates)-1}).

Список:
{titles_list}"""
    
    answer = call_groq(prompt)
    
    if "NONE" in answer.upper():
        return None
        
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
    prompt = f"""Ты — профессиональный редактор. Перепиши новость так, чтобы она была понятной, цепляющей и ТОЛЬКО НА РУССКОМ ЯЗЫКЕ.
КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНЫ любые английские слова и фразы вроде "ожидается прямой эфир".
ВНИМАТЕЛЬНО ПРОВЕРЯЙ СЛОВА. Не заменяй правильные слова на похожие по звучанию.
Если в исходном тексте ТОЛЬКО общие фразы про визиты, совещания или заявления чиновников, напиши слово NONE.

Формат ответа:
1. Заголовок в теге <b>...</b>. Сделай его громким и понятным.
2. ДВА переноса строки.
3. 1-2 эмодзи и краткий текст с фактами (строго на русском).

Исходный заголовок: {title}
Исходный текст: {summary}
"""
    raw_text = call_groq(prompt)
    
    if not raw_text or "NONE" in raw_text.upper():
        print("⚠️ ИИ отклонил новость (нет конкретики).")
        return None
        
    raw_text = re.sub(r'^(Category|Рубрика|Категория):.*?\n', '', raw_text, flags=re.IGNORECASE)
    for pattern in [r'—\s*в материале[^.]*\.', r'—\s*подробнее[^.]*\.', r'—\s*читайте[^.]*\.', r'—\s*на сайте[^.]*\.']:
        raw_text = re.sub(pattern, '', raw_text, flags=re.IGNORECASE)

    raw_text = re.sub(r'</b>\s*', '</b>\n\n', raw_text)
    raw_text = raw_text.replace('\\n', '\n')
    raw_text = raw_text[:900]
    
    plain_body = re.sub(r'<[^>]+>', '', raw_text)
    if re.search(r'[a-zA-Z]', plain_body):
        print("❌ Отклонено: в тексте обнаружены английские буквы.")
        return None

    if len(plain_body.strip()) < 40:
         return None

    return sanitize_html(raw_text)

def send_photo(photo_url, caption):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    payload = {"chat_id": TELEGRAM_CHANNEL_ID, "photo": photo_url, "caption": caption, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200: return True
    except: pass
    try:
        img_data = requests.get(photo_url, timeout=10).content
        files = {'photo': ('image.jpg', img_data)}
        data = {"chat_id": TELEGRAM_CHANNEL_ID, "caption": caption, "parse_mode": "HTML"}
        r = requests.post(url, data=data, files=files, timeout=15)
        if r.status_code == 200: return True
    except: pass
    return False

def send_video(video_url, caption):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"
    payload = {"chat_id": TELEGRAM_CHANNEL_ID, "video": video_url, "caption": caption, "parse_mode": "HTML", "supports_streaming": True}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200: return True
    except: pass
    try:
        video_data = requests.get(video_url, timeout=15).content
        if len(video_data) > 50 * 1024 * 1024: return False
        files = {'video': ('video.mp4', video_data)}
        data = {"chat_id": TELEGRAM_CHANNEL_ID, "caption": caption, "parse_mode": "HTML", "supports_streaming": True}
        r = requests.post(url, data=data, files=files, timeout=15)
        if r.status_code == 200: return True
    except: pass
    return False

def send_to_telegram(text, media_type, media_url):
    full_text = f"{text}\n\n{SIGNATURE_TG}"
    if media_type == 'video' and media_url:
        if send_video(media_url, full_text): return True
    elif media_type == 'image' and media_url:
        if send_photo(media_url, full_text): return True
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHANNEL_ID, "text": full_text, "parse_mode": "HTML", "disable_web_page_preview": True}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200: return True
    except: pass
    return False

def send_to_vk(text, media_type, media_url):
    if not VK_TOKEN or not VK_GROUP_ID: return False
        
    print("Отправляем пост во ВКонтакте...")
    clean_text = re.sub(r'<[^>]+>', '', text)
    clean_text = html.unescape(clean_text).strip()
    
    try:
        vk_session = vk_api.VkApi(token=VK_TOKEN)
        vk = vk_session.get_api()
        attachments = ""
        
        if POST_PHOTO_TO_VK and media_type == 'image' and media_url:
            try:
                img_data = requests.get(media_url, timeout=10).content
                upload = VkUpload(vk_session)
                photo = upload.photo_wall(io.BytesIO(img_data), group_id=int(VK_GROUP_ID))[0]
                attachments = f"photo{photo['owner_id']}_{photo['id']}"
            except Exception as e:
                pass
        
        vk.wall.post(owner_id=f"-{VK_GROUP_ID}", message=clean_text, attachments=attachments, from_group=1)
        print("✅ ВК: Успешно опубликовано!")
        return True
    except Exception as e:
        print(f"❌ ВК Ошибка: {e}")
        return False

def send_to_max(text, media_type, media_url):
    if not MAX_BOT_TOKEN or not MAX_CHANNEL_ID: return False
        
    print("Отправляем пост в MAX...")
    clean_text = text.replace('<b>', '**').replace('</b>', '**')
    clean_text = html.unescape(clean_text).strip()
    clean_text = f"{clean_text}\n\n{SIGNATURE_MAX}"
    
    headers = {
        "Authorization": MAX_BOT_TOKEN,
        "Content-Type": "application/json"
    }
    
    attachments = []
    
    try:
        if media_type == 'video' and media_url:
            print("  -> Скачиваем видео для MAX...")
            video_data = requests.get(media_url, timeout=30).content
            
            if len(video_data) > 250 * 1024 * 1024:
                print("  ❌ Видео больше 250 МБ, MAX его не примет.")
                return False
            
            print("  -> Запрашиваем URL для загрузки в MAX...")
            upload_url_resp = requests.post(
                "https://platform-api2.max.ru/uploads?type=video",
                headers={"Authorization": MAX_BOT_TOKEN},
                timeout=15,
                verify=False
            )
            upload_url_resp.raise_for_status()
            upload_data = upload_url_resp.json()
            
            upload_url = upload_data.get("url")
            media_token = upload_data.get("token")
            
            if not upload_url or not media_token:
                print("  ❌ MAX не вернул URL или токен для загрузки.")
                return False
            
            print("  -> Загружаем видео в MAX...")
            upload_resp = requests.post(
                upload_url,
                headers={"Authorization": MAX_BOT_TOKEN},
                files={'data': ('video.mp4', video_data)},
                timeout=60
            )
            upload_resp.raise_for_status()
            
            print("  ✅ Видео загружено. Ждем обработки...")
            time.sleep(3)
            
            attachments.append({
                "type": "video",
                "payload": {"token": media_token}
            })
            
        elif media_type == 'image' and media_url:
            attachments.append({
                "type": "image",
                "payload": {"url": media_url}
            })
    
    except Exception as e:
        print(f"  ⚠️ Ошибка подготовки медиа для MAX: {e}")
        attachments = []

    payload = {"text": clean_text, "format": "markdown"}
    if attachments:
        payload["attachments"] = attachments

    try:
        url = f"https://platform-api2.max.ru/messages?chat_id={MAX_CHANNEL_ID}"
        response = requests.post(url, headers=headers, json=payload, timeout=20, verify=False)
        response.raise_for_status()
        print("✅ MAX: Успешно опубликовано!")
        return True
    except Exception as e:
        print(f"❌ MAX Ошибка: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print("Ответ сервера MAX:", e.response.text)
        return False

def main():
    ensure_state_files_exist()
    
    last_theme = get_last_theme()
    try:
        last_index = THEME_ORDER.index(last_theme)
    except ValueError:
        last_index = -1
    next_index = (last_index + 1) % len(THEME_ORDER)
    
    for i in range(len(THEME_ORDER)):
        current_index = (next_index + i) % len(THEME_ORDER)
        theme = THEME_ORDER[current_index]
        
        print(f"\n=== Ищем новости по теме: {theme} ===")
        candidates = get_news_candidates(theme)
        
        if candidates:
            print(f"Отправляем {len(candidates)} кандидатов на оценку ИИ...")
            best_news = pick_most_important(candidates)
            
            if best_news:
                print(f"✅ Выбрана новость: {best_news['title']}")
                post_body = rewrite_with_ai(best_news['title'], best_news['summary'], theme)
                
                if post_body is None:
                    print("❌ Новость отклонена. Ищем в следующей теме...")
                    continue

                print(f"Сгенерированный текст:\n{post_body}\n")
                
                tg_success = send_to_telegram(post_body, best_news['media_type'], best_news['media_url'])
                print(f"Telegram: {'OK' if tg_success else 'FAIL'}")
                
                if tg_success:
                    save_last_theme(theme)
                    save_posted_link(best_news['link'])
                    save_published_title(best_news['title'])
                    save_posted_hash(best_news['text_hash'])
                    
                    if best_news.get('media_url'):
                        if best_news['media_type'] == 'video':
                            save_posted_video(best_news['media_url'])
                        else:
                            save_posted_image(best_news['media_url'])
                        
                    vk_result = send_to_vk(post_body, best_news['media_type'], best_news['media_url'])
                    print(f"ВКонтакте: {'OK' if vk_result else 'FAIL'}")
                    
                    max_result = send_to_max(post_body, best_news['media_type'], best_news['media_url'])
                    print(f"MAX: {'OK' if max_result else 'FAIL'}")
                    
                    print(f"\n🎉 Готово! Следующая тема: {theme}")
                    return
            else:
                 print("ИИ отклонил всех кандидатов. Ищем в следующей теме.")

    print("\n❌ Не удалось найти подходящих новостей.")
    sys.exit(0)

if __name__ == "__main__":
    main()
