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
import hashlib
import random
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
    "СВО и Армия": ["сво", "дрон", "бпла", "ракета", "фронт", "минобороны", "всу", "штурм", "обстрел", "пво", "сводка", "наступление", "потери", "мобилизация", "армия", "военный", "беспилотник", "наши", "прилет", "хлопок", "боевик", "уничтожен", "ликвидирован"],
    "Катастрофы": ["погиб", "жертв", "катастрофа", "крушение", "авиакатастрофа", "обрушение", "наводнение", "ураган", "смерч", "теракт", "взрыв", "пожар", "спасатели", "мчс", "эвакуация", "чрезвычайный", "трагедия", "погибли", "рухнул"],
    "Криминал": ["убийство", "труп", "задержан", "арестован", "банда", "наркотик", "коррупция", "взятка", "мошенничество", "суд", "приговор", "разбой", "ограбление", "стрельба", "погоня", "разборка", "конфликт", "маньяк", "расчленил", "избил", "изнасиловал", "посадили", "следствие", "фсб", "полиция"],
    "Мигранты": ["мигрант", "миграция", "иностранц", "депортация", "патент", "гастарбайтер", "диаспора", "приезж", "гражданство", "нелегал", "инородец", "узбек", "таджик", "киргиз", "армянин", "азербайджанец"],
    "Иноагенты": ["иноагент", "нежелательная организация", "экстремист", "госдеп", "иностранное финансирование", "пособник", "шпион", "предатель", "госизмена", "финансирование", "цру"],
    "ДТП и Аварии": ["дтп", "авария", "лобовое", "столкновение", "сбил", "насмерть", "травмы", "скорая", "госпитализирован", "перевернулся", "врезался", "мотоцикл", "пьяный водитель", "сбил пешехода", "машина", "камаз", "фура", "разбился", "погибли", "смерть"]
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

BLACKLIST_WORDS = [
    "какой сегодня", "какой праздник", "гороскоп", "день рождения", "история дня", 
    "в этот день", "народные приметы", "церковный календарь", "лунный календарь", "именины",
    "заседание", "законопроект", "бюджет", "форум", "выставка", "конференция", "экономика", "инфляция", "курс валют",
    "спорт", "гонщик", "гонка", "автоспорт", "футбол", "хоккей", "олимпиад", "чемпионат", "турнир", "матч", "клуб", "тренер",
    "шоу-бизнес", "актер", "актриса", "певец", "певица", "звезда", "сериал", "фильм", "премьера", "инстаграм", "тикток",
    "спектакль", "ледовый", "фигурист", "авербух", "петросян", "концерт", "развлечение", "шоу", "праздник", "фестиваль", "выступление",
    "продолжают спецоперацию", "выполняют задачи", "боевая готовность", "полная готовность", "активные действия", "выполняют боевые задачи", "решают задачи", "контроль над ситуацией",
    "автобус", "маршрутка", "прямой эфир", "прямая трансляция", "смотрите эфир", "ожидается эфир",
    "визит", "совещание", "рабочая поездка", "подписал", "вручил", "обсудил", "поздравил", "открыл", "посетил", "заявление", "пресс-конференция", "круглый стол"
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

def save_posted_video(video_hash):
    if not video_hash: return
    with open("posted_videos.txt", "a", encoding="utf-8") as f:
        f.write(video_hash + "\n")

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
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,ru;q=0.8'
        }
        resp = requests.get(url, timeout=10, headers=headers)
        if resp.status_code != 200:
            return []
        
        soup = BeautifulSoup(resp.text, "html.parser")
        posts = soup.select(".tgme_widget_message[data-post]")
        
        if not posts:
            return []
            
        print(f"  [{channel_name}] Найдено постов: {len(posts)}")
        
        count_video_tags = 0
        count_blacklisted = 0
        count_not_theme = 0
        count_too_old = 0
        
        for post in reversed(posts):
            time_tag = post.select_one(".tgme_widget_message_date time")
            if not time_tag:
                continue
            dt_str = time_tag.get("datetime")
            try:
                pub_date = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            except:
                pub_date = now
                
            age_hours = (now - pub_date).total_seconds() / 3600
            
            if age_hours > 24:
                count_too_old += 1
                continue
            
            video_url = None
            
            video_tag = post.select_one("video[src]")
            if video_tag and video_tag.get("src"):
                video_url = video_tag.get("src")
                
            if not video_url:
                source_tag = post.select_one("video source[src]")
                if source_tag and source_tag.get("src"):
                    video_url = source_tag.get("src")
            
            if not video_url:
                video_link = post.select_one("a.tgme_widget_message_video_player")
                if video_link and video_link.get("href"):
                    video_url = video_link.get("href")
            
            # Убрали блок с превью (video_thumb), так как это картинка, а не видео
            
            if not video_url:
                continue
                
            count_video_tags += 1
            
            video_url = urljoin("https://t.me", video_url)
            
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
            
            if is_blacklisted(clean_text): 
                count_blacklisted += 1
                continue
            if not is_theme_match(clean_text, theme): 
                count_not_theme += 1
                continue
            
            videos.append({
                "title": clean_text[:60] + "...",
                "summary": clean_text,
                "age_hours": age_hours,
                "media_type": "video",
                "media_url": video_url,
                "link": post_link,
                "text_hash": text_hash,
                "theme_match": True,
                "russia_match": True,
                "has_media": True
            })
        
        if len(videos) == 0:
            print(f"  [{channel_name}] С видео: {count_video_tags} | Блэклист: {count_blacklisted} | Не тема: {count_not_theme} | Старше 24ч: {count_too_old}")
        
    except Exception as e:
        print(f"Ошибка парсинга {channel_name}: {e}")
    return videos

def get_news_candidates(theme):
    now = datetime.now(timezone.utc)
    
    print(f"  -> Ищем видео в веб-версиях Telegram-каналов...")
    tg_videos = []
    tg_channels = ["pilachzx", "slavaded1337", "novosti_efir", "botcharov", "mnogonazi", "SHOCKkzn", "mash", "bazabazon", "shot_shot"]
    for ch in tg_channels:
        vids = get_tg_web_videos(ch, theme, now)
        tg_videos.extend(vids)
        
    if tg_videos:
        tg_videos = sorted(tg_videos, key=lambda x: x['age_hours'])
        print(f"🔥 Найдено {len(tg_videos)} ВИДЕО в веб-версиях Telegram! Берем самые свежие.")
        return tg_videos[:5]

    print("  ❌ Видео не найдено. Пропускаем запуск (картинки отключены).")
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
    
    titles_list = "\n".join([f"{i}. {c['title']}" for i, c in enumerate(candidates)])
    
    recent_titles = get_recent_titles()
    history_text = ""
    if recent_titles:
        history_text = "УЖЕ ОПУБЛИКОВАНО РАНЕЕ:\n" + "\n".join(recent_titles) + "\n"
    
    prompt = f"""Ты — редактор жесткого новостного канала. 
Выбери ОДИН самый интересный заголовок из списка.
КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО выбирать новости про шоу-бизнес, актеров, спорт, концерты, визиты чиновников и скучные совещания.
Выбирай только то, что содержит экшн: СВО, криминал, ДТП, катастрофы.

{history_text}

Ответь ТОЛЬКО цифрой (от 0 до {len(candidates)-1}). Не пиши никаких слов, только цифру.

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
    prompt = f"""Ты — профессиональный редактор новостного канала. Твоя задача — отредактировать текст, исправив грамматические, синтаксические и стилистические ошибки, НО СОХРАНИВ ВСЕ ДЕТАЛИ И КОНТЕКСТ.

ЗАДАЧА:
1. Исправь все ошибки в склонениях, падежах, числах, предлогах и роде.
2. Приведи предложения к литературной русской речи.
3. ВАЖНО: Если исходный текст обрывается на полуслове, НЕ ВЫДУМЫВАЙ окончание и не добавляй факты, которых нет. Просто удали этот незаконченный обрывок текста, оставив только ту часть, которая имеет логическое завершение.
4. Не дублируй заголовок в первом предложении текста. Переходи сразу к сути.
5. ОБЯЗАТЕЛЬНО сохрани все географические названия (города, улицы, регионы) и имена.
6. Убери только канцелярские фразы-филлеры ("По сведениям местных СМИ", "Дальнейшие детали пока неизвестны", "Ведется проверка").
7. Заголовок выдели тегом <b>...</b>.
8. После заголовка сделай ДВА переноса строки.
9. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать любые эмодзи, смайлики и графические символы.

ОГРАНИЧЕНИЯ:
- Не добавляй факты, которых нет в исходном тексте.
- Даже если текст очень короткий, сделай из него нормальный пост.

ФОРМАТ ОТВЕТА:
Только готовый исправленный пост, без твоих комментариев.

ИСХОДНЫЙ ТЕКСТ:
Заголовок: {title}
Текст: {summary}
"""
    raw_text = call_groq(prompt)
    
    if not raw_text:
        print("⚠️ ИИ вернул пустоту. Используем оригинальный текст.")
        clean_title = re.sub(r'<[^>]+>', '', title).strip()
        clean_summary = summary.strip()
        raw_text = f"<b>{clean_title}</b>\n\n{clean_summary}"
        
    raw_text = re.sub(r'^(Category|Рубрика|Категория):.*?\n', '', raw_text, flags=re.IGNORECASE)
    for pattern in [r'—\s*в материале[^.]*\.', r'—\s*подробнее[^.]*\.', r'—\s*читайте[^.]*\.', r'—\s*на сайте[^.]*\.']:
        raw_text = re.sub(pattern, '', raw_text, flags=re.IGNORECASE)

    raw_text = re.sub(r'</b>\s*', '</b>\n\n', raw_text)
    raw_text = raw_text.replace('\\n', '\n')
    raw_text = raw_text[:1000] 
    
    raw_text = re.sub(r'[^\w\sа-яА-ЯёЁ.,;:!?()\[\]{}<>="\'/\-+#*&%$@|~^]', '', raw_text)

    plain_body = re.sub(r'<[^>]+>', '', raw_text)
    if re.search(r'[a-zA-Z]', plain_body):
        print("❌ Отклонено: в тексте обнаружены английские буквы.")
        return None

    if len(plain_body.strip()) < 20:
         return None

    return sanitize_html(raw_text)

def get_video_hash(video_data):
    return hashlib.md5(video_data).hexdigest()

def send_video(video_url, caption):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"
    payload = {"chat_id": TELEGRAM_CHANNEL_ID, "video": video_url, "caption": caption, "parse_mode": "HTML", "supports_streaming": True}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200: return True
    except: pass
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Referer': 'https://web.telegram.org/'
        }
        video_data = requests.get(video_url, headers=headers, timeout=30).content
        
        if len(video_data) == 0:
            print("  ❌ Скачалось пустое видео (0 байт).")
            return False
            
        if len(video_data) > 50 * 1024 * 1024: 
            print("  ❌ Видео больше 50 МБ для Telegram.")
            return False
            
        video_hash = get_video_hash(video_data)
        
        files = {'video': ('video.mp4', video_data, 'video/mp4')}
        data = {"chat_id": TELEGRAM_CHANNEL_ID, "caption": caption, "parse_mode": "HTML", "supports_streaming": True}
        r = requests.post(url, data=data, files=files, timeout=30)
        if r.status_code == 200: 
            save_posted_video(video_hash)
            return True
    except Exception as e:
        print(f"  ⚠️ Ошибка скачивания/отправки видео в TG: {e}")
    return False

def send_to_telegram(text, media_type, media_url):
    full_text = f"{text}\n\n{SIGNATURE_TG}"
    if media_type == 'video' and media_url:
        if send_video(media_url, full_text): return True
        
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
        
        delay = random.randint(5, 15)
        print(f"  ⏳ Ждем {delay} сек. перед публикацией в ВК (защита от флуда)...")
        time.sleep(delay)
        
        vk.wall.post(owner_id=f"-{VK_GROUP_ID}", message=clean_text, from_group=1)
        print("✅ ВК: Успешно опубликовано!")
        return True
    except Exception as e:
        print(f"❌ ВК Ошибка: {e}")
        return False

def send_to_max(text, media_type, media_url):
    if not MAX_BOT_TOKEN or not MAX_CHANNEL_ID: 
        print("MAX: Нет токена или ID канала.")
        return False
        
    print(f"Отправляем пост в MAX (канал: {MAX_CHANNEL_ID})...")
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
            download_headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Referer': 'https://web.telegram.org/'
            }
            
            video_resp = requests.get(media_url, headers=download_headers, timeout=60, allow_redirects=True)
            content_type = video_resp.headers.get('Content-Type', '')
            
            if 'text/html' in content_type:
                print("  ⚠️ Получен HTML вместо видео. Пытаемся извлечь прямую ссылку...")
                soup_html = BeautifulSoup(video_resp.text, "html.parser")
                v_tag = soup_html.select_one("video[src]")
                if not v_tag:
                    v_tag = soup_html.select_one("video source[src]")
                if not v_tag:
                    # Иногда прямая ссылка спрятана в мета-тегах
                    meta_video = soup_html.select_one('meta[property="og:video"]')
                    if meta_video and meta_video.get("content"):
                         direct_url = meta_video.get("content")
                         print(f"  -> Найдена ссылка в мета-теге, качаем заново...")
                         video_resp = requests.get(direct_url, headers=download_headers, timeout=60, allow_redirects=True)
                         content_type = video_resp.headers.get('Content-Type', '')
                
                if v_tag and v_tag.get("src"):
                    direct_url = v_tag.get("src")
                    if direct_url.startswith("/"):
                        direct_url = urljoin("https://t.me", direct_url)
                    print(f"  -> Найдена прямая ссылка, качаем заново...")
                    video_resp = requests.get(direct_url, headers=download_headers, timeout=60, allow_redirects=True)
                    content_type = video_resp.headers.get('Content-Type', '')
            
            video_data = video_resp.content
            
            if len(video_data) < 100 * 1024 or 'video/' not in content_type:
                print(f"  ❌ Видео не скачалось (размер: {len(video_data)} байт, тип: {content_type}). Постим только текст в MAX.")
            else:
                if len(video_data) > 250 * 1024 * 1024:
                    print("  ❌ Видео больше 250 МБ, MAX его не примет.")
                else:
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
                    
                    if upload_url and media_token:
                        print(f"  -> Загружаем видео в MAX (размер: {len(video_data) // (1024*1024)} МБ)...")
                        upload_headers = {"Authorization": MAX_BOT_TOKEN}
                        
                        upload_resp = requests.post(
                            upload_url,
                            headers=upload_headers,
                            files={'data': ('video.mp4', video_data, 'video/mp4')},
                            timeout=180 
                        )
                        
                        if upload_resp.status_code in [200, 201]:
                            print("  ✅ Видео загружено. Ждем обработки...")
                            time.sleep(15) 
                            attachments.append({
                                "type": "video",
                                "payload": {"token": media_token}
                            })
                        else:
                            print(f"  ❌ Ошибка загрузки видео: {upload_resp.status_code}")
                    else:
                        print("  ❌ MAX не вернул URL или токен.")
    
    except Exception as e:
        print(f"  ⚠️ Ошибка подготовки медиа для MAX: {e}")

    payload = {"text": clean_text, "format": "markdown"}
    if attachments:
        payload["attachments"] = attachments

    max_retries = 3
    for attempt in range(max_retries):
        try:
            url = f"https://platform-api2.max.ru/messages?chat_id={MAX_CHANNEL_ID}"
            response = requests.post(url, headers=headers, json=payload, timeout=20, verify=False)
            
            print(f"  DEBUG: Ответ MAX (попытка {attempt+1}): {response.status_code} - {response.text}")
            
            if response.status_code == 200:
                print("✅ MAX: Успешно опубликовано!")
                return True
            elif response.status_code == 400:
                error_data = response.json()
                if error_data.get("code") == "attachment.not.ready":
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 10
                        print(f"  ⏳ Файл ещё не обработан (попытка {attempt+1}/{max_retries}). Ждем {wait_time} секунд...")
                        time.sleep(wait_time)
                        continue
                    else:
                        print(f"  ❌ Файл так и не обработался после {max_retries} попыток.")
                        return False
                else:
                    print(f"  ❌ Ошибка MAX: {error_data}")
                    return False
            else:
                response.raise_for_status()
                
        except Exception as e:
            print(f"  ❌ Ошибка отправки в MAX (попытка {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(10)
            else:
                return False
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
                    
                    vk_result = send_to_vk(post_body, best_news['media_type'], best_news['media_url'])
                    print(f"ВКонтакте: {'OK' if vk_result else 'FAIL'}")
                    
                    max_result = send_to_max(post_body, best_news['media_type'], best_news['media_url'])
                    print(f"MAX: {'OK' if max_result else 'FAIL'}")
                    
                    print(f"\n🎉 Готово! Следующая тема: {theme}")
                    return
            else:
                 print("ИИ отклонил всех кандидатов. Ищем в следующей теме.")

    print("\n❌ Не удалось найти видео. Пропускаем запуск.")
    sys.exit(0)

if __name__ == "__main__":
    main()
