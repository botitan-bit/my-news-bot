import os
import feedparser
import requests
import re
import sys
import html
import time
import io
import urllib3
import hashlib
import random
import subprocess
import tempfile
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime, timezone, timedelta
import vk_api
from vk_api.upload import VkUpload

sys.stdout.reconfigure(line_buffering=True)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
MAX_BOT_TOKEN = os.environ.get("MAX_BOT_TOKEN", "").strip()
MAX_CHANNEL_ID = os.environ.get("MAX_CHANNEL_ID", "").strip()
VK_TOKEN = os.environ.get("VK_TOKEN", "").strip()
VK_GROUP_ID = os.environ.get("VK_GROUP_ID", "").strip()

LOGO_WIDTH = 80
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
SIGNATURE_MAX = '**[ПЕРВЫЕ НОВОСТИ](https://max.ru/channel_pervonovosti)**'

LOCAL_CHANNELS = {}

BLACKLIST_WORDS = [
    # ПРИВЕТСТВИЯ И ЛИЧНЫЕ ОБРАЩЕНИЯ (мемы оставляем)
    "доброе утро", "добрый день", "добрый вечер", "доброй ночи", "всем привет", 
    "приветствую", "друзья", "подписчики", "дорогие", "хорошего дня", "хорошего настроения",
    "отличного дня", "продуктивного дня", "с богом", "берегите себя", "с праздником",
    "с днем рождения", "напоминаю", "делюсь", "личное мнение", "мысли вслух",

    # ЖИВОТНЫЕ И ПРИРОДА
    "котят", "котенок", "кошка", "кот ", "щенок", "собак", "животн", "зоопарк", 
    "заповедник", "фотоловушк", "барс", "тигр", "лев ", "медвед", "природ", 
    "турист", "путешеств", "заповедн", "нацпарк", "красив", "умилен", "милота",

    # СПОРТ
    "спорт", "футбол", "хоккей", "баскетбол", "волейбол", "теннис", "бокс", "мма", "ufc", 
    "матч", "турнир", "чемпионат", "олимпиад", "тренер", "стадион", "болельщик", "фанат", 
    "финальный свисток", "забил", "гол ", "очко", "рубин", "крылья советов", "крылышки", 
    "спартак", "зенит", "цска", "динамо", "локомотив", "рфпл", "кхл", "нхл", "лига чемпионов",
    "гонщик", "гонка", "автоспорт", "клуб", "победа", "поражение", "проиграл", "выиграл",
    
    # РЕКЛАМА И СПАМ
    "реклама", "промокод", "скидка", "erid", "маркировка", 
    "казино", "ставки", "криптовалюта", "инвестиции", "заработок", 
    "подписывайтесь", "перейти по ссылке", "спонсор", "распродажа", "бонус", 
    "подарок", "бесплатно", "только сегодня", "успей", "торопись", "оформить заказ",
    
    # МУСОРНЫЕ НОВОСТИ И КЛИКБЕЙТ
    "какой сегодня", "какой праздник", "гороскоп", "день рождения", "история дня", 
    "в этот день", "народные приметы", "церковный календарь", "лунный календарь", "именины",
    "заседание", "законопроект", "бюджет", "форум", "выставка", "конференция", "экономика", "инфляция", "курс валют",
    "шоу-бизнес", "актер", "актриса", "певец", "певица", "звезда", "сериал", "фильм", "премьера", "инстаграм", "тикток",
    "спектакль", "ледовый", "фигурист", "авербух", "петросян", "концерт", "развлечение", "шоу", "праздник", "фестиваль", "выступление",
    "продолжают спецоперацию", "выполняют задачи", "боевая готовность", "полная готовность", "активные действия", "выполняют боевые задачи", "решают задачи", "контроль над ситуацией",
    "автобус", "маршрутка", "прямой эфир", "прямая трансляция", "смотрите эфир", "ожидается эфир",
    "визит", "совещание", "рабочая поездка", "подписал", "вручил", "обсудил", "поздравил", "открыл", "посетил", "заявление", "пресс-конференция", "круглый стол",
    "трамп", "байден", "зеленский", "сша", "америк", "белый дом", "конгресс сша",
    "айфон", "iphone", "смартфон", "гаджет", "дуо", "duo",
    "макаревич", "нетаньяху", "израил", "палестин", "сионизм", "бен-гвир", "бенгвир", "смотрич"
]

def ensure_state_files_exist():
    for file in ["last_theme.txt", "posted_news.txt", "published_titles.txt", "posted_images.txt", "posted_videos.txt", "posted_hashes.txt"]:
        if not os.path.exists(file):
            open(file, 'a').close()

def get_text_hash(text):
    clean_text = re.sub(r'[^\w\s]', '', text.lower())
    words = clean_text.split()
    long_words = [w for w in words if len(w) > 4]
    long_words.sort()
    return " ".join(long_words[:20])

def get_posted_hashes():
    if os.path.exists("posted_hashes.txt"):
        with open("posted_hashes.txt", "r", encoding="utf-8") as f:
            return f.read().splitlines()
    return []

def save_posted_hash(text_hash):
    if not text_hash: return
    with open("posted_hashes.txt", "a", encoding="utf-8") as f:
        f.write(text_hash + "\n")

def is_duplicate_text(text, posted_hashes):
    new_words = set([w for w in re.sub(r'[^\w\s]', '', text.lower()).split() if len(w) > 4])
    if not new_words:
        return False
    
    for old_hash in posted_hashes[-150:]:
        old_words = set(old_hash.split())
        if not old_words:
            continue
        
        intersection = new_words.intersection(old_words)
        union = new_words.union(old_words)
        
        if len(union) > 0 and (len(intersection) / len(union)) > 0.5:
            return True
            
    return False

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

def get_posted_photos():
    if os.path.exists("posted_images.txt"):
        with open("posted_images.txt", "r", encoding="utf-8") as f:
            return f.read().splitlines()
    return []

def save_posted_photo(photo_url):
    if not photo_url: return
    with open("posted_images.txt", "a", encoding="utf-8") as f:
        f.write(photo_url + "\n")

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

def is_blacklisted(text):
    text_lower = text.lower()
    return any(word in text_lower for word in BLACKLIST_WORDS)

def get_tg_web_photos(channel_name, now):
    photos = []
    posted_photos = get_posted_photos()
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
            
        print(f"  [{channel_name}] Найдено постов (фото): {len(posts)}")
        
        count_photo_tags = 0
        count_blacklisted = 0
        count_too_old = 0
        count_duplicate = 0
        
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
            
            photo_url = None
            photo_wrap = post.select_one(".tgme_widget_message_photo_wrap")
            if photo_wrap and photo_wrap.get("style"):
                match = re.search(r"url\('([^']+)'\)", photo_wrap["style"])
                if match:
                    photo_url = match.group(1)
            
            if not photo_url:
                img_tag = post.select_one("img.tgme_widget_message_photo")
                if img_tag and img_tag.get("src"):
                    photo_url = img_tag.get("src")
            
            if not photo_url:
                continue
                
            count_photo_tags += 1
            photo_url = urljoin("https://t.me", photo_url)
            
            if photo_url in posted_photos:
                count_duplicate += 1
                continue
                
            text_tag = post.select_one(".tgme_widget_message_text")
            if not text_tag:
                continue
            
            clean_text = text_tag.get_text("\n", strip=True)
            if len(clean_text) < 20:
                continue
            
            text_hash = get_text_hash(clean_text)
            if is_duplicate_text(clean_text, posted_hashes):
                count_duplicate += 1
                continue
                
            post_id = post.get("data-post", "")
            post_link = f"https://t.me/{post_id}"
            
            if is_blacklisted(clean_text): 
                count_blacklisted += 1
                continue
            
            photos.append({
                "title": clean_text[:60] + "...",
                "summary": clean_text,
                "age_hours": age_hours,
                "media_type": "photo",
                "media_url": photo_url,
                "link": post_link,
                "text_hash": text_hash,
                "channel": channel_name
            })
        
        if len(photos) == 0:
            print(f"  [{channel_name}] С фото: {count_photo_tags} | Реклама/Мусор: {count_blacklisted} | Старше 24ч: {count_too_old} | Дубли: {count_duplicate}")
        
    except Exception as e:
        print(f"Ошибка парсинга фото {channel_name}: {e}")
    return photos

def get_tg_web_videos(channel_name, now):
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
        count_too_old = 0
        count_duplicate = 0
        
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
            video_tag = post.select_one("video")
            if video_tag:
                video_url = video_tag.get("src") or video_tag.get("data-src")
                
            if not video_url:
                source_tag = post.select_one("video source")
                if source_tag:
                    video_url = source_tag.get("src") or source_tag.get("data-src")
            
            if not video_url:
                video_link = post.select_one("a.tgme_widget_message_video_player")
                if video_link and video_link.get("href"):
                    video_url = video_link.get("href")
            
            if video_url and 't.me/' in video_url and '?embed' not in video_url:
                embed_url = video_url.split('?')[0] + '?embed=1'
                try:
                    emb_resp = requests.get(embed_url, headers=headers, timeout=10)
                    html_text = html.unescape(emb_resp.text)
                    mp4_matches = re.findall(r'(https?://[^\s"\'<>]+?\.(?:mp4|webm)[^\s"\'<>]*)', html_text)
                    if mp4_matches:
                        video_url = mp4_matches[0].replace('\\/', '/')
                        print(f"  [{channel_name}] Извлечена прямая ссылка из embed: {video_url[:50]}...")
                    else:
                        video_url = None
                except:
                    video_url = None

            if not video_url:
                continue
                
            count_video_tags += 1
            video_url = urljoin("https://t.me", video_url)
            
            if video_url in posted_videos:
                count_duplicate += 1
                continue
            
            text_tag = post.select_one(".tgme_widget_message_text")
            if not text_tag:
                continue
            
            clean_text = text_tag.get_text("\n", strip=True)
            if len(clean_text) < 20:
                continue
            
            text_hash = get_text_hash(clean_text)
            if is_duplicate_text(clean_text, posted_hashes):
                count_duplicate += 1
                continue
                
            post_id = post.get("data-post", "")
            post_link = f"https://t.me/{post_id}"
            
            if is_blacklisted(clean_text): 
                count_blacklisted += 1
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
                "has_media": True,
                "channel": channel_name
            })
        
        if len(videos) == 0:
            print(f"  [{channel_name}] С видео: {count_video_tags} | Реклама/Мусор: {count_blacklisted} | Старше 24ч: {count_too_old} | Дубли: {count_duplicate}")
        
    except Exception as e:
        print(f"Ошибка парсинга {channel_name}: {e}")
    return videos

def get_news_candidates():
    now = datetime.now(timezone.utc)
    
    tg_channels = [
        "ragulaku",
        "pilachzx",
        "novosti_efir",
        "slavaded1337",
        "botcharov",
        "mnogonazi"
    ]
    
    print(f"  -> Ищем видео в веб-версиях Telegram-каналов...")
    all_videos = []
    for ch in tg_channels:
        vids = get_tg_web_videos(ch, now)
        all_videos.extend(vids)
        
    if all_videos:
        all_videos = sorted(all_videos, key=lambda x: x['age_hours'])
        candidates = []
        channel_counts = {}
        for v in all_videos:
            ch = v['channel']
            if channel_counts.get(ch, 0) < 2:
                candidates.append(v)
                channel_counts[ch] = channel_counts.get(ch, 0) + 1
            if len(candidates) >= 10:
                break
                
        print(f"🔥 Найдено {len(candidates)} ВИДЕО (с учетом разнообразия)! Берем самые свежие.")
        return candidates

    print("  ❌ Видео не найдено. Переключаемся на поиск ФОТО...")
    all_photos = []
    for ch in tg_channels:
        pics = get_tg_web_photos(ch, now)
        all_photos.extend(pics)
        
    if all_photos:
        all_photos = sorted(all_photos, key=lambda x: x['age_hours'])
        candidates = []
        channel_counts = {}
        for p in all_photos:
            ch = p['channel']
            if channel_counts.get(ch, 0) < 2:
                candidates.append(p)
                channel_counts[ch] = channel_counts.get(ch, 0) + 1
            if len(candidates) >= 10:
                break
                
        print(f"🔥 Найдено {len(candidates)} ФОТО (с учетом разнообразия)! Берем самые свежие.")
        return candidates

    print("  ❌ Ни видео, ни фото не найдено. Пропускаем запуск.")
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

def sanitize_html(text):
    text = text.replace('<b>', '||BOLD_START||').replace('</b>', '||BOLD_END||')
    text = html.escape(text)
    text = text.replace('||BOLD_START||', '<b>').replace('||BOLD_END||', '</b>')
    return text

def rewrite_with_ai(title, summary, channel_name=""):
    summary = re.sub(r'@[a-zA-Z0-9_]+', '', summary)
    summary = re.sub(r'https?://t\.me/[a-zA-Z0-9_]+', '', summary)

    if channel_name in LOCAL_CHANNELS:
        city = LOCAL_CHANNELS[channel_name]
        city_instruction = f'Новость из местного канала "{channel_name}" (город {city}). Если в тексте есть улица, но нет города, можешь добавить город {city}.'
    else:
        city_instruction = 'Не добавляй города, если их нет в исходном тексте.'

    prompt = f"""Ты — строгий редактор. Твоя задача — оформить новость.
Выполняй ТОЛЬКО эти правила:
1. Не меняй смысл и факты. Оставь текст практически без изменений.
2. Удали только явные оскорбления, нецензурную брань, призывы к насилию или экстремизму. Если их нет — ничего не трогай.
3. Если исходный текст очень длинный (больше 800 символов), сократи его, оставив только самую суть.
4. Сверху добавь жирный заголовок (максимум 80 символов), отражающий суть, выдели его тегом <b>...</b>.
5. После заголовка сделай ДВА переноса строки и выведи основной текст.
6. Удали упоминания других каналов, авторов и ссылки на Telegram.
7. {city_instruction}
8. Запрещено использовать любые эмодзи, смайлики и графические символы.
9. 🆕 КРИТИЧЕСКИ ВАЖНО: Отклоняй (возвращай пустую строку) ТОЛЬКО если текст состоит ИСКЛЮЧИТЕЛЬНО из утреннего приветствия (например, "Доброе утро", "Всем привет", "Хорошего дня") или пустой рекламы. Во ВСЕХ остальных случаях (даже если это короткий мем, шутка, обрывок фразы или странный текст) — ОБЯЗАТЕЛЬНО оформи его: придумай заголовок и выведи текст.

ФОРМАТ ОТВЕТА:
Только готовый пост (заголовок + текст), без твоих комментариев.

ИСХОДНЫЙ ТЕКСТ:
{summary}
"""
    raw_text = call_groq(prompt)
    
    if not raw_text:
        print("⚠️ ИИ вернул пустоту (это было чистое приветствие). Пропускаем.")
        return None
        
    raw_text = re.sub(r'^(Category|Рубрика|Категория):.*?\n', '', raw_text, flags=re.IGNORECASE)
    raw_text = re.sub(r'</b>\s*', '</b>\n\n', raw_text)
    raw_text = raw_text.replace('\\n', '\n')
    raw_text = raw_text[:1000] 
    
    raw_text = re.sub(r'[^.!?\n]+$', '', raw_text).strip()
    
    raw_text = re.sub(r'(?i)перейти в канал\.?', '', raw_text)
    raw_text = re.sub(r'(?i)подписывайтесь.*', '', raw_text)
    raw_text = re.sub(r'(?i)читайте нас.*', '', raw_text)
    raw_text = re.sub(r'\n{3,}', '\n\n', raw_text)

    raw_text = re.sub(r'[^\w\sа-яА-ЯёЁ.,;:!?()\[\]{}<>="\'/\-+#*&%$@|~^]', '', raw_text)

    plain_body = re.sub(r'<[^>]+>', '', raw_text)
    
    if len(plain_body.strip()) < 20:
         return None

    return sanitize_html(raw_text)

def process_video(video_bytes):
    if video_bytes.startswith(b'<!DOCTYPE html>') or b'<html' in video_bytes[:1000]:
        print("  ❌ Скачан HTML вместо видео. Пропускаем обработку.")
        return video_bytes, None

    if not os.path.exists("logo.png"):
        print("  ⚠️ Логотип logo.png не найден. Пропускаем наложение.")
        logo_input = None
        filter_complex = 'fps=30,scale=ceil(iw/2)*2:ceil(ih/2)*2,format=yuv420p'
    else:
        logo_input = 'logo.png'
        filter_complex = f'[1:v]scale={LOGO_WIDTH}:-1[logo];[0:v][logo]overlay=W-w-20:20,fps=30,scale=ceil(iw/2)*2:ceil(ih/2)*2,format=yuv420p'

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_in:
            temp_in.write(video_bytes)
            temp_in_path = temp_in.name

        temp_out_path = temp_in_path.replace(".mp4", "_out.mp4")
        temp_thumb_path = temp_in_path.replace(".mp4", "_thumb.jpg")

        command = [
            'ffmpeg', '-y',
            '-i', temp_in_path,
        ]
        if logo_input:
            command.extend(['-i', logo_input])
        
        command.extend([
            '-filter_complex', filter_complex,
            '-c:v', 'libx264',
            '-profile:v', 'baseline',
            '-level', '3.0',
            '-crf', '23',
            '-preset', 'ultrafast',
            '-c:a', 'aac',
            '-b:a', '128k',
            '-movflags', '+faststart',
            temp_out_path
        ])

        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
        
        if result.returncode != 0:
            print(f"  ❌ Ошибка FFmpeg (код {result.returncode}).")
            err_msg = result.stderr.decode('utf-8', errors='ignore')
            print(f"  Детали: {err_msg[-200:]}")
            return video_bytes, None

        thumb_cmd = [
            'ffmpeg', '-y',
            '-ss', '00:00:01.000',
            '-i', temp_out_path,
            '-vframes', '1',
            '-q:v', '2',
            temp_thumb_path
        ]
        subprocess.run(thumb_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)

        processed_bytes = None
        thumb_bytes = None

        if os.path.exists(temp_out_path):
            with open(temp_out_path, 'rb') as f:
                processed_bytes = f.read()

        if os.path.exists(temp_thumb_path):
            with open(temp_thumb_path, 'rb') as f:
                thumb_bytes = f.read()

        print("  ✅ Видео перекодировано и миниатюра сгенерирована.")
        return processed_bytes, thumb_bytes

    except Exception as e:
        print(f"  ⚠️ Ошибка обработки видео: {e}")
        return video_bytes, None
    finally:
        for p in [temp_in_path, temp_out_path, temp_thumb_path]:
            if 'p' in locals() and os.path.exists(p):
                os.remove(p)

def get_video_hash(video_data):
    return hashlib.md5(video_data).hexdigest()

def send_video(video_url, caption):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Referer': 'https://t.me/'
        }
        
        if 't.me/' in video_url and '?embed' not in video_url:
            embed_url = video_url.split('?')[0] + '?embed=1'
            print(f"  -> Запрашиваем embed-версию для TG: {embed_url}")
            video_resp = requests.get(embed_url, headers=headers, timeout=30)
            html_text = html.unescape(video_resp.text)
            mp4_matches = re.findall(r'(https?://[^\s"\'<>]+?\.(?:mp4|webm)[^\s"\'<>]*)', html_text)
            if mp4_matches:
                video_url = mp4_matches[0].replace('\\/', '/')
                print(f"  -> Найдена прямая ссылка для TG: {video_url[:50]}...")

        video_data = requests.get(video_url, headers=headers, timeout=30).content
        
        if len(video_data) == 0:
            print("  ❌ Скачалось пустое видео (0 байт).")
            return False
            
        if len(video_data) > 50 * 1024 * 1024: 
            print("  ❌ Видео больше 50 МБ для Telegram.")
            return False

        video_data, thumb_data = process_video(video_data)
            
        video_hash = get_video_hash(video_data)
        
        files = {'video': ('video.mp4', video_data, 'video/mp4')}
        data = {"chat_id": TELEGRAM_CHANNEL_ID, "caption": caption, "parse_mode": "HTML", "supports_streaming": True}
        
        if thumb_data:
            files['thumbnail'] = ('thumb.jpg', thumb_data, 'image/jpeg')

        print("  -> Загружаем видео в Telegram...")
        r = requests.post(url, data=data, files=files, timeout=60)
        
        if r.status_code == 200: 
            save_posted_video(video_hash)
            return True
        else:
            print(f"  ❌ Ошибка Telegram API: {r.text}")
    except Exception as e:
        print(f"  ⚠️ Ошибка скачивания/отправки видео в TG: {e}")
    return False

def send_photo(photo_url, caption):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'}
        photo_data = requests.get(photo_url, headers=headers, timeout=30).content
        
        files = {'photo': ('photo.jpg', photo_data, 'image/jpeg')}
        data = {"chat_id": TELEGRAM_CHANNEL_ID, "caption": caption, "parse_mode": "HTML"}
        
        print("  -> Загружаем фото в Telegram...")
        r = requests.post(url, data=data, files=files, timeout=60)
        
        if r.status_code == 200:
            save_posted_photo(photo_url)
            return True
        else:
            print(f"  ❌ Ошибка Telegram API (фото): {r.text}")
    except Exception as e:
        print(f"  ⚠️ Ошибка отправки фото в TG: {e}")
    return False

def send_to_telegram(text, media_type, media_url):
    full_text = f"{text}\n\n{SIGNATURE_TG}"
    if media_type == 'video' and media_url:
        if send_video(media_url, full_text): return True
    elif media_type == 'photo' and media_url:
        if send_photo(media_url, full_text): return True
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHANNEL_ID, "text": full_text, "parse_mode": "HTML", "disable_web_page_preview": True}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200: return True
    except: pass
    return False

def send_to_vk(text, media_type, media_url):
    if not VK_TOKEN or not VK_GROUP_ID: 
        print("ВК: Нет токена или ID группы.")
        return False
        
    print("Отправляем пост во ВКонтакте...")
    clean_text = re.sub(r'<[^>]+>', '', text)
    clean_text = html.unescape(clean_text).strip()
    
    try:
        vk_session = vk_api.VkApi(token=VK_TOKEN)
        vk = vk_session.get_api()
        
        delay = random.randint(30, 60)
        print(f"  ⏳ Ждем {delay} сек. перед публикацией в ВК...")
        time.sleep(delay)
        
        vk.wall.post(owner_id=f"-{VK_GROUP_ID}", message=clean_text, from_group=1)
        print("✅ ВК: Успешно опубликовано!")
        return True
    except Exception as e:
        error_msg = str(e)
        if "9" in error_msg or "Flood" in error_msg:
            print("  ⚠️ ВК: Flood control. Пропускаем этот пост, попробуем через 2 часа.")
        else:
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
                'Accept': '*/*',
                'Referer': 'https://t.me/'
            }
            
            video_resp = requests.get(media_url, headers=download_headers, timeout=60, allow_redirects=True)
            content_type = video_resp.headers.get('Content-Type', '')
            
            if 'text/html' in content_type or len(video_resp.content) < 100 * 1024:
                print("  ⚠️ Получен HTML вместо видео. Пытаемся извлечь прямую ссылку...")
                
                if 't.me/' in media_url and '/s/' not in media_url and '?embed' not in media_url:
                    embed_url = media_url.split('?')[0] + '?embed=1'
                    print(f"  -> Запрашиваем embed-версию поста: {embed_url}")
                    video_resp = requests.get(embed_url, headers=download_headers, timeout=60, allow_redirects=True)
                
                html_text = html.unescape(video_resp.text)
                soup_html = BeautifulSoup(html_text, "html.parser")
                
                direct_url = None
                
                v_tag = soup_html.select_one("video")
                if v_tag:
                    direct_url = v_tag.get("src") or v_tag.get("data-src")
                
                if not direct_url:
                    meta_video = soup_html.select_one('meta[property="og:video"]')
                    if meta_video and meta_video.get("content"):
                        direct_url = html.unescape(meta_video.get("content"))
                
                if not direct_url:
                    mp4_matches = re.findall(r'(https?://[^\s"\'<>]+?\.(?:mp4|webm)[^\s"\'<>]*)', html_text)
                    if mp4_matches:
                        direct_url = mp4_matches[0].replace('\\/', '/')
                        print(f"  -> Найдена ссылка через Regex: {direct_url[:50]}...")
                
                if direct_url:
                    if direct_url.startswith("/"):
                        direct_url = urljoin("https://t.me", direct_url)
                    print(f"  -> Качаем по прямой ссылке...")
                    video_resp = requests.get(direct_url, headers=download_headers, timeout=60, allow_redirects=True)
                    content_type = video_resp.headers.get('Content-Type', '')
                else:
                    print("  ❌ Не удалось найти ссылку на видео в HTML.")
            
            video_data = video_resp.content
            
            if len(video_data) < 100 * 1024 or 'video/' not in content_type:
                print(f"  ❌ Видео не скачалось (размер: {len(video_data)} байт, тип: {content_type}). Постим только текст в MAX.")
            else:
                if len(video_data) > 250 * 1024 * 1024:
                    print("  ❌ Видео больше 250 МБ, MAX его не примет.")
                else:
                    video_data, _ = process_video(video_data)

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
                        
        elif media_type == 'photo' and media_url:
            print("  -> Скачиваем фото для MAX...")
            download_headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'}
            photo_resp = requests.get(media_url, headers=download_headers, timeout=60, allow_redirects=True)
            
            if len(photo_resp.content) > 10 * 1024 * 1024:
                print("  ❌ Фото больше 10 МБ, MAX его не примет.")
            else:
                print("  -> Запрашиваем URL для загрузки фото в MAX...")
                upload_url_resp = requests.post(
                    "https://platform-api2.max.ru/uploads?type=image",
                    headers={"Authorization": MAX_BOT_TOKEN},
                    timeout=15,
                    verify=False
                )
                upload_url_resp.raise_for_status()
                upload_data = upload_url_resp.json()
                
                upload_url = upload_data.get("url")
                
                if upload_url:
                    print("  -> Загружаем фото в MAX...")
                    upload_headers = {"Authorization": MAX_BOT_TOKEN}
                    upload_resp = requests.post(
                        upload_url,
                        headers=upload_headers,
                        files={'data': ('photo.jpg', photo_resp.content, 'image/jpeg')},
                        timeout=60 
                    )
                    
                    if upload_resp.status_code in [200, 201]:
                        media_token = None
                        try:
                            res_json = upload_resp.json()
                            if "photos" in res_json:
                                photos_data = res_json.get("photos", {})
                                if isinstance(photos_data, dict):
                                    for key, value in photos_data.items():
                                        if isinstance(value, dict) and "token" in value:
                                            media_token = value["token"]
                                            break
                            elif "token" in res_json:
                                media_token = res_json["token"]
                        except:
                            pass
                            
                        if media_token:
                            attachments.append({
                                "type": "image",
                                "payload": {"token": media_token}
                            })
                        else:
                            print("  ⚠️ Не удалось извлечь токен из ответа, пробуем использовать URL.")
                            attachments.append({
                                "type": "image",
                                "payload": {"url": media_url}
                            })
                    else:
                        print(f"  ❌ Ошибка загрузки фото: {upload_resp.status_code}")
                else:
                    print("  ❌ MAX не вернул URL для загрузки фото.")
    
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
            
            print(f"  DEBUG: Ответ MAX (попытка {attempt+1}): {response.status_code} - {response.text[:100]}...")
            
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
    
    if not os.path.exists("logo.png"):
        print("⚠️ ВНИМАНИЕ: Файл logo.png не найден в корне репозитория! Видео будут без логотипа.")

    print(f"\n=== Ищем свежие новости ===")
    candidates = get_news_candidates()
    
    if candidates:
        for candidate in candidates:
            print(f"\nОтправляем кандидата на оценку ИИ: {candidate['title']}")
            post_body = rewrite_with_ai(candidate['title'], candidate['summary'], candidate.get('channel', ''))
            
            if post_body is None:
                print("❌ Кандидат отклонен ИИ (возможно, приветствие). Пробуем следующего...")
                continue 

            print(f"✅ Выбрана и обработана новость: {candidate['title']} (из канала {candidate.get('channel', 'неизвестно')})")
            print(f"Сгенерированный текст:\n{post_body}\n")
            
            tg_success = send_to_telegram(post_body, candidate['media_type'], candidate['media_url'])
            print(f"Telegram: {'OK' if tg_success else 'FAIL'}")
            
            if tg_success:
                save_posted_link(candidate['link'])
                save_published_title(candidate['title'])
                save_posted_hash(candidate['text_hash'])
                
                print("\nЗапускаем отправку в MAX...")
                max_result = send_to_max(post_body, candidate['media_type'], candidate['media_url'])
                print(f"MAX: {'OK' if max_result else 'FAIL'}")
                
                print("\nЗапускаем отправку в ВК...")
                vk_result = send_to_vk(post_body, candidate['media_type'], candidate['media_url'])
                print(f"ВКонтакте: {'OK' if vk_result else 'FAIL'}")
                
                print(f"\n🎉 Готово! Бот успешно отработал.")
                return
        
        print("\n❌ Все кандидаты отклонены ИИ (приветствия/мусор). Пропускаем запуск.")
    else:
        print("\n❌ Не удалось найти ни видео, ни фото. Пропускаем запуск.")
        
    sys.exit(0)

if __name__ == "__main__":
    main()
