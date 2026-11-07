import os
import sys
import functools
import feedparser
import requests
import re
import html
import time
import io
import urllib3
import hashlib
import tempfile
import traceback
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime, timezone, timedelta
from PIL import Image, ImageStat
import pytesseract
from io import BytesIO

sys.stdout.reconfigure(line_buffering=True)
print = functools.partial(print, flush=True)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

print("=== БОТ ЗАПУСТИЛСЯ ===")

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
MAX_BOT_TOKEN = os.environ.get("MAX_BOT_TOKEN", "").strip()
MAX_CHANNEL_ID = os.environ.get("MAX_CHANNEL_ID", "").strip()

TG_NK_CHANNEL_ID = os.environ.get("TG_NK_CHANNEL_ID", "").strip()
MAX_NK_CHANNEL_ID = os.environ.get("MAX_NK_CHANNEL_ID", "").strip()

REQUEST_TIMEOUT = 15
NK_MAX_ATTEMPTS = 10

SIGNATURE_TG = '<b><a href="https://t.me/+l7bgzfXgngBkN2My">ПЕРВЫЕ НОВОСТИ</a></b>'
SIGNATURE_MAX = '**[ПЕРВЫЕ НОВОСТИ](https://max.ru/channel_pervonovosti)**'

SIGNATURE_NK_TG = (
    '<b><a href="https://t.me/nashNVKZ">Телеграм</a></b>\n'
    '-----\n'
    '<b><a href="https://vk.ru/nash_nvk">ВКонтакте</a></b>\n'
    '-----\n'
    '<b><a href="https://max.ru/channel_nashNVKZ">МАХ</a></b>'
)

SIGNATURE_NK_MAX = (
    '**[МАХ](https://max.ru/channel_nashNVKZ)**\n'
    '-----\n'
    '**[ВКонтакте](https://vk.ru/nash_nvk)**\n'
    '-----\n'
    '**[Телеграм](https://t.me/nashNVKZ)**'
)

NK_RSS_FEEDS = [
    "https://ria.ru/export/rss2/index.xml",
    "http://www.kuzbassfm.ru/rss/news.xml",
    "https://kemerovo42.info/feed/",
    "https://kuzbass.media/feed/",
    "https://vse42.ru/rss/news.xml",
    "https://www.kem.kp.ru/rss/",
]

# Каналы для основного канала
TG_CHANNELS = ["novosti_efir", "slavaded1337", "botcharov", "mnogonazi", "zhest_na_dorogah"]

# НОВЫЙ СПИСОК КАНАЛОВ ДЛЯ НОВОКУЗНЕЦКА
TG_NK_CHANNELS = [
    "novokuznetsklife",      # Бардокин NEWS Новокузнецк
    "news_novokuznetsk",     # Новости Новокузнецк
    "kuzpress",              # КузПресс
    "wwwcitynru",            # Город Новостей (Новокузнецк)
    "NWD_xcWbz_g3Zjcy",      # Новокузнецк 24/7
    "kuzbassinfo",           # Кузбасс инфо
    "mediakailo",            # Кузнецкое кайло
    "region42_kuzbass",      # Регион 42 | Кузбасс
    "kuzbass_now"            # Кузбасс сейчас
]

NK_KEYWORDS = ["новокузнецк", "кузбасс", "кемерово", "белово", "прокопьевск", "ленинск-кузнецкий", "междуреченск", "мыски", "осинники", "киселевск", "юрга", "анжеро-судженск", "мариинск", "тайга", "гуьевск", "таштагол", "полысаево", "калтан", "березовский", "топки"]

AD_WORDS = [
    "реклама", "промокод", "скидка", "erid", "маркировка",
    "казино", "ставки", "криптовалюта", "инвестиции", "заработок",
    "подписывайтесь", "подписаться", "подпишись", "перейти по ссылке", 
    "спонсор", "распродажа", "бонус", "читать далее", "читать полностью", 
    "подарок", "бесплатно", "только сегодня", "успей", "торопись", "оформить заказ",
    "заказать", "купить", "магазин", "акция", "промо", "розыгрыш",
    "партнерство", "партнёрство", "альянс", "кэшбэк", "кэшбек", "депозит", "привилегии",
    "альфа", "альфа-банк", "альфа банк", "сбер", "сбербанк", "тинькофф", "т-банк", "втб", "росбанк", "банк", "кредит", "ипотека"
]

IMG_AD_PHRASES = ["8-800", "8 800", "ооо", "реклама", "заказать", "erid", "промокод", "скидка", "змппсм", "агротрак"]

def ensure_state_files_exist():
    for file in [
        "last_theme.txt", "posted_news.txt", "published_titles.txt",
        "posted_images.txt", "posted_videos.txt", "posted_hashes.txt",
        "posted_nk_hashes.txt", "posted_nk_images.txt", "posted_nk_videos.txt",
        "published_nk_titles.txt"
    ]:
        if not os.path.exists(file):
            open(file, 'a').close()

def clean_text_junk(text):
    if not text: return ""
    text = html.unescape(text)
    
    lines = text.split('\n')
    if lines:
        last_line = lines[-1].strip()
        if len(last_line) < 50 and any(k in last_line.lower() for k in ['max', 'мах', 'tg', 'тг', 'телеграм', 'telegram', 'подпишись']):
            lines = lines[:-1]
    text = '\n'.join(lines)

    text = re.split(r'\|\s*(?=.*?(?:MAX|МАКС|TG|ТГ|Телеграм|Telegram|@))', text, flags=re.IGNORECASE)[0]

    patterns = [
        r'📣?\s*прямой\s+эфир',
        r'🔴?\s*прямой\s+эфир',
        r'💰\s*деньги\s+в\s+эфире',
        r'📺\s*наш\s+max',
        r'наш\s+max',
        r'😊\s*tg\s+замедляют',
        r'видосы\s+и\s+оперативные\s+новости',
        r'смотри\s+в\s+нашем',
        r'смотрите\s+в\s+нашем',
        r'подписывайтесь\s+на\s+наш',
        r'подписывайся\s+на\s+наш',
        r'переходите\s+в\s+наш',
        r'переходи\s+в\s+наш',
        r'все\s+самое\s+важное',
        r'больше\s+новостей\s+на',
        r'читайте\s+также',
        r'источник\s*:',
        r'наши\s+соцсети',
    ]
    for p in patterns:
        text = re.split(r'(?i)' + p, text)[0]
        
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'@\w+', '', text)
    
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
    text = re.sub(r'[\u2600-\u27BF]', '', text)
    
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'^[\.\,\-\:\s\|]+', '', text)
    text = re.sub(r'[\.\,\-\:\s\|]+$', '', text)
    return text

def normalize_url(url, base=""):
    if not url: return None
    if url.startswith('//'): return 'https:' + url
    if not url.startswith('http'): return urljoin(base, url)
    return url

def is_bad_image_url(url):
    if not url: return True
    lower = url.lower()
    return any(k in lower for k in ['banner', 'reklama', 'ad_', 'adv', 'logo', 'icon', 'avatar', 'pixel', 'stub', 'thumb'])

def is_bad_image(image_bytes, title_text=""):
    try:
        img = Image.open(BytesIO(image_bytes))
        W, H = img.size
        
        if W < 300 or H < 200:
            print(f"    [Отклонено: слишком маленькая] {W}x{H} (нужно 300x200)")
            return True

        if W * H == 0: return True

        img_gray = img.convert('L')
        stat = ImageStat.Stat(img_gray)
        stddev = stat.stddev[0] if stat.stddev else 0

        data = pytesseract.image_to_data(img, lang='rus+eng', output_type=pytesseract.Output.DICT)

        words = []
        total_area = 0
        for i in range(len(data.get('text', []))):
            w = (data['text'][i] or '').strip()
            if not w: continue
            try: conf = int(float(data['conf'][i]))
            except: conf = -1
            if conf < 50: continue
            ww = int(data['width'][i] or 0)
            hh = int(data['height'][i] or 0)
            words.append(w)
            total_area += ww * hh

        clean_text = re.sub(r'[^\w\s]', '', ' '.join(words)).strip()
        if len(clean_text) <= 40: return False

        coverage = total_area / float(W * H)
        snippet = clean_text[:80].replace('\n', ' ')
        print(f"    [OCR] {len(clean_text)} симв., покрытие {coverage:.0%}, StdDev {stddev:.0f}: {snippet!r}")

        if stddev < 25: 
            print("    [Отклонено: однотонная графика/обложка]")
            return True

        if title_text and len(clean_text) > 10:
            clean_t = re.sub(r'[^\w\s]', '', title_text.lower())
            t_words = set(clean_t.split())
            o_words = set(clean_text.lower().split())
            if t_words:
                overlap = len(t_words.intersection(o_words)) / len(t_words)
                if overlap > 0.5: 
                    print("    [Отклонено: обложка содержит заголовок новости]")
                    return True

        lower_text = clean_text.lower()
        for phrase in IMG_AD_PHRASES:
            if phrase in lower_text: 
                print("    [Отклонено: рекламный баннер]")
                return True

        if len(clean_text) > 150 and coverage > 0.25: 
            print("    [Отклонено: картинка с большим текстом]")
            return True
    except Exception as e:
        print(f"    [Отклонено: ошибка чтения картинки] {e}")
        return True
        
    return False

def get_text_hash(text):
    clean = re.sub(r'[^\w\s]', '', text.lower())
    return " ".join(sorted(set([w for w in clean.split() if len(w) > 4]))[:40])

def is_duplicate_text(text, hashes):
    clean = re.sub(r'[^\w\s]', '', text.lower())
    new_words = set(sorted(set([w for w in clean.split() if len(w) > 4]))[:40])
    if not new_words: return False
    for old in hashes[-500:]:
        old_words = set(old.split())
        if not old_words: continue
        inter = new_words.intersection(old_words)
        union = new_words.union(old_words)
        if len(union) > 0 and (len(inter) / len(union)) > 0.25: return True
    return False

def is_duplicate_title(title, recent_titles):
    if not title or len(title) < 15: return False
    clean = re.sub(r'[^\w\s]', '', title.lower()).strip()
    for t in recent_titles:
        clean_t = re.sub(r'[^\w\s]', '', t.lower()).strip()
        if clean == clean_t: return True
        if len(clean) >= 20 and len(clean_t) >= 20 and clean[:20] == clean_t[:20]: return True
    return False

def load_lines(fn):
    if os.path.exists(fn):
        with open(fn, "r", encoding="utf-8") as f: return f.read().splitlines()
    return []

def append_line(fn, line):
    if not line: return
    with open(fn, "a", encoding="utf-8") as f: f.write(line + "\n")

def get_posted_hashes(): return load_lines("posted_hashes.txt")
def save_posted_hash(h): append_line("posted_hashes.txt", h)
def get_posted_links(): return load_lines("posted_news.txt")
def save_posted_link(l): append_line("posted_news.txt", l)
def get_posted_videos(): return load_lines("posted_videos.txt")
def save_posted_video(u): append_line("posted_videos.txt", u)
def get_posted_photos(): return load_lines("posted_images.txt")
def save_posted_photo(u): append_line("posted_images.txt", u)
def get_recent_titles(): return load_lines("published_titles.txt")

def save_published_title(t):
    append_line("published_titles.txt", t)
    titles = get_recent_titles()
    if len(titles) > 50:
        with open("published_titles.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(titles[-50:]) + "\n")

def get_posted_nk_hashes(): return load_lines("posted_nk_hashes.txt")
def save_posted_nk_hash(h): append_line("posted_nk_hashes.txt", h)
def get_posted_nk_photos(): return load_lines("posted_nk_images.txt")
def save_posted_nk_photo(u): append_line("posted_nk_images.txt", u)
def get_posted_nk_videos(): return load_lines("posted_nk_videos.txt")
def save_posted_nk_video(u): append_line("posted_nk_videos.txt", u)
def get_recent_nk_titles(): return load_lines("published_nk_titles.txt")

def save_nk_published_title(t):
    append_line("published_nk_titles.txt", t)
    titles = get_recent_nk_titles()
    if len(titles) > 50:
        with open("published_nk_titles.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(titles[-50:]) + "\n")

def is_ad(text):
    lower = text.lower()
    for w in AD_WORDS:
        pattern = r'(?<![а-яёa-z])' + re.escape(w) + r'(?![а-яёa-z])'
        if re.search(pattern, lower): 
            print(f"    [Найдена реклама: '{w}']")
            return True
    return False

def is_valid_image_url(url, title):
    if not url: return False
    try:
        resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=REQUEST_TIMEOUT, verify=False)
        if resp.status_code != 200 or 'image' not in resp.headers.get('Content-Type', ''): return False
        if len(resp.content) == 0 or len(resp.content) > 10 * 1024 * 1024: return False
        if is_bad_image(resp.content, title): return False
        return True
    except Exception as e:
        return False

def extract_direct_video_url(url):
    headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://t.me/'}
    try:
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT, allow_redirects=True, verify=False)
        ctype = resp.headers.get('Content-Type', '')
        if 'video/' in ctype: return url
        html_text = html.unescape(resp.text)
        soup = BeautifulSoup(html_text, "html.parser")
        v_tag = soup.select_one("video")
        if v_tag and (v_tag.get("src") or v_tag.get("data-src")): return v_tag.get("src") or v_tag.get("data-src")
        s_tag = soup.select_one("video source")
        if s_tag and (s_tag.get("src") or s_tag.get("data-src")): return s_tag.get("src") or s_tag.get("data-src")
        meta_v = soup.select_one('meta[property="og:video"]')
        if meta_v and meta_v.get("content"): return html.unescape(meta_v.get("content"))
        matches = re.findall(r'(https?://[^\s"\'<>]+?\.(?:mp4|webm)[^\s"\'<>]*)', html_text)
        if matches: return html.unescape(matches[0]).replace('\\/', '/')
        if 't.me/' in url and '?embed' not in url: return extract_direct_video_url(url.split('?')[0] + '?embed=1')
    except Exception as e: 
        pass
    return None

def get_nk_priority(text):
    text_lower = text.lower()
    if "новокузнецк" in text_lower: return 1
    if "кузбасс" in text_lower: return 2
    if any(city in text_lower for city in NK_KEYWORDS[2:]): return 3
    return 99

def get_tg_web_videos(channel_name, now):
    videos = []
    url = f"https://t.me/s/{channel_name}"
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT, headers={'User-Agent': 'Mozilla/5.0'}, verify=False)
        if resp.status_code != 200: return []
        soup = BeautifulSoup(resp.text, "html.parser")
        posts = soup.select(".tgme_widget_message[data-post]")
        if not posts: return []
        
        for post in reversed(posts):
            tt = post.select_one(".tgme_widget_message_date time")
            if not tt: continue
            try: pub = datetime.fromisoformat(tt.get("datetime").replace("Z", "+00:00"))
            except: pub = now
            age = (now - pub).total_seconds() / 3600
            if age > 24: continue
            
            v_url = None
            vt = post.select_one("video")
            if vt: v_url = vt.get("src") or vt.get("data-src")
            if not v_url:
                st = post.select_one("video source")
                if st: v_url = st.get("src") or st.get("data-src")
            if not v_url:
                vl = post.select_one("a.tgme_widget_message_video_player")
                if vl: v_url = vl.get("href")
            if not v_url: continue
            
            v_url = urljoin("https://t.me", v_url)
            txt = post.select_one(".tgme_widget_message_text")
            if not txt: continue
            
            clean = txt.get_text("\n", strip=True)
            clean = clean_text_junk(clean)
            
            if len(clean) < 20: continue
            if is_ad(clean): continue
            
            th = get_text_hash(clean)
            pid = post.get("data-post", "")
            
            lines = [l.strip() for l in clean.split('\n') if l.strip()]
            if len(lines) > 1:
                title = lines[0]
            else:
                first_sentence = re.search(r'^([^.!?\n]+[.!?])', clean)
                if first_sentence and len(first_sentence.group(1)) < 120:
                    title = first_sentence.group(1).strip()
                else:
                    title = clean[:80].strip()
                    last_space = title.rfind(' ')
                    if last_space > 40:
                        title = title[:last_space] + "..."
                    else:
                        title += "..."
                
            videos.append({
                "title": title, "summary": clean, "age_hours": age,
                "media_type": "video", "media_url": v_url,
                "link": f"https://t.me/{pid}", "text_hash": th, "channel": channel_name
            })
    except Exception as e:
        pass
    return videos

def get_tg_web_photos(channel_name, now):
    photos = []
    url = f"https://t.me/s/{channel_name}"
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT, headers={'User-Agent': 'Mozilla/5.0'}, verify=False)
        if resp.status_code != 200: return []
        soup = BeautifulSoup(resp.text, "html.parser")
        posts = soup.select(".tgme_widget_message[data-post]")
        if not posts: return []
        
        for post in reversed(posts):
            tt = post.select_one(".tgme_widget_message_date time")
            if not tt: continue
            try: pub = datetime.fromisoformat(tt.get("datetime").replace("Z", "+00:00"))
            except: pub = now
            age = (now - pub).total_seconds() / 3600
            if age > 24: continue
            
            p_url = None
            pw = post.select_one(".tgme_widget_message_photo_wrap")
            if pw and pw.get("style"):
                m = re.search(r"url\('([^']+)'\)", pw["style"])
                if m: p_url = m.group(1)
            if not p_url:
                img = post.select_one("img.tgme_widget_message_photo")
                if img and img.get("src"): p_url = img.get("src")
            if not p_url: continue
            p_url = urljoin("https://t.me", p_url)
            
            txt = post.select_one(".tgme_widget_message_text")
            if not txt: continue
            
            clean = txt.get_text("\n", strip=True)
            clean = clean_text_junk(clean)
            
            if len(clean) < 20: continue
            if is_ad(clean): continue
            
            th = get_text_hash(clean)
            pid = post.get("data-post", "")
            
            lines = [l.strip() for l in clean.split('\n') if l.strip()]
            if len(lines) > 1:
                title = lines[0]
            else:
                first_sentence = re.search(r'^([^.!?\n]+[.!?])', clean)
                if first_sentence and len(first_sentence.group(1)) < 120:
                    title = first_sentence.group(1).strip()
                else:
                    title = clean[:80].strip()
                    last_space = title.rfind(' ')
                    if last_space > 40:
                        title = title[:last_space] + "..."
                    else:
                        title += "..."
                
            photos.append({
                "title": title, "summary": clean, "age_hours": age,
                "media_type": "photo", "media_url": p_url,
                "link": f"https://t.me/{pid}", "text_hash": th, "channel": channel_name
            })
    except Exception as e:
        pass
    return photos

# НОВАЯ ФУНКЦИЯ: Сбор кандидатов для Новокузнецка ТОЛЬКО из Telegram-каналов
def get_novokuznetsk_tg_candidates(now):
    candidates = []
    posted_nk_videos = get_posted_nk_videos()
    posted_nk_photos = get_posted_nk_photos()
    posted_nk_hashes = get_posted_nk_hashes()
    recent_nk_titles = get_recent_nk_titles()
    
    print("\n--- Сбор новостей Новокузнецка из Telegram-каналов ---")
    
    # Проходим по каждому каналу из нового списка
    for ch in TG_NK_CHANNELS:
        print(f"  Сканируем @{ch}...")
        # Собираем видео и фото из канала
        ch_videos = get_tg_web_videos(ch, now)
        ch_photos = get_tg_web_photos(ch, now)
        
        for item in ch_videos + ch_photos:
            # Ищем ключевые слова в тексте поста
            if not any(k in item['summary'].lower() for k in NK_KEYWORDS):
                continue
                
            # Проверяем на дубликаты
            if item['media_url'] in posted_nk_videos or item['media_url'] in posted_nk_photos:
                continue
            if is_duplicate_text(item['summary'], posted_nk_hashes):
                continue
            if is_duplicate_title(item['title'], recent_nk_titles):
                continue
                
            # Определяем приоритет (насколько это "новокузнецкая" новость)
            item['priority'] = get_nk_priority(item['summary'])
            item['source_priority'] = 0
            
            candidates.append(item)
            
    print(f"  Собрано кандидатов из TG: {len(candidates)}")
    return candidates

def send_video_tg(video_url, caption, chat_id, is_nk=False):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"
    direct_url = extract_direct_video_url(video_url)
    if not direct_url: return False
    try:
        resp = requests.get(direct_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=60, verify=False)
        if resp.status_code != 200: return False
        video_data = resp.content
        if len(video_data) == 0 or len(video_data) > 50 * 1024 * 1024: return False
        
        files = {'video': ('video.mp4', video_data, 'video/mp4')}
        data = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML", "supports_streaming": True}
        r = requests.post(url, data=data, files=files, timeout=90)
        if r.status_code == 200:
            if is_nk: save_posted_nk_video(video_url)
            else: save_posted_video(video_url)
            return True
    except Exception as e:
        print(f"❌ ОШИБКА ОТПРАВКИ ВИДЕО TG: {e}")
    return False

def send_photo_tg(photo_url, caption, chat_id, title="", is_nk=False):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    try:
        resp = requests.get(photo_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=REQUEST_TIMEOUT, verify=False)
        ctype = resp.headers.get('Content-Type', '')
        if 'image' not in ctype: return False
        photo_data = resp.content
        if len(photo_data) == 0 or len(photo_data) > 10 * 1024 * 1024: return False
        
        if is_bad_image(photo_data, title): return False
        
        files = {'photo': ('photo.jpg', photo_data, 'image/jpeg')}
        data = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}
        r = requests.post(url, data=data, files=files, timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            if is_nk: save_posted_nk_photo(photo_url)
            else: save_posted_photo(photo_url)
            return True
    except Exception as e:
        print(f"❌ ОШИБКА ОТПРАВКИ ФОТО TG: {e}")
    return False

def send_to_telegram(text, media_type, media_url, channel_id=None, signature=None, title="", is_nk=False):
    if channel_id is None: channel_id = TELEGRAM_CHANNEL_ID
    if signature is None: signature = SIGNATURE_TG
    
    full_text = f"{text}\n\n{signature}"
    
    if len(full_text) > 1000:
        print("    ⚠️ Текст слишком длинный. Оставляем только заголовок.")
        clean_title = clean_text_junk(title) if title else clean_text_junk(text.split('\n')[0])
        full_text = f"<b>{clean_title}</b>\n\n{signature}"
        
    if media_type == 'video' and media_url:
        return send_video_tg(media_url, full_text, channel_id, is_nk)
    elif media_type == 'photo' and media_url:
        return send_photo_tg(media_url, full_text, channel_id, title, is_nk)
    return False

def send_to_max(text, media_type, media_url, channel_id=None, signature=None, title="", is_nk=False):
    if channel_id is None: channel_id = MAX_CHANNEL_ID
    if signature is None: signature = SIGNATURE_MAX
    if not MAX_BOT_TOKEN or not channel_id or not media_url: return False
    
    clean_text = text.replace('<b>', '**').replace('</b>', '**')
    full_text = f"{html.unescape(clean_text).strip()}\n\n{signature}"
    
    if len(full_text) > 1000:
        print("    ⚠️ Текст слишком длинный (MAX). Оставляем только заголовок.")
        clean_title = clean_text_junk(title) if title else clean_text_junk(text.split('\n')[0])
        full_text = f"**{clean_title}**\n\n{signature}"

    headers = {"Authorization": MAX_BOT_TOKEN, "Content-Type": "application/json"}
    attachments = []
    
    try:
        if media_type == 'video':
            direct_url = extract_direct_video_url(media_url)
            if not direct_url: return False
            vr = requests.get(direct_url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://t.me/'}, timeout=60, allow_redirects=True, verify=False)
            if len(vr.content) < 100 * 1024 or 'video/' not in vr.headers.get('Content-Type', '') or len(vr.content) > 250 * 1024 * 1024: return False
            
            up = requests.post("https://platform-api2.max.ru/uploads?type=video", headers={"Authorization": MAX_BOT_TOKEN}, timeout=15, verify=False)
            ud = up.json()
            if not (ud.get("url") and ud.get("token")): return False
            
            ur = requests.post(ud["url"], headers={"Authorization": MAX_BOT_TOKEN}, files={'data': ('video.mp4', vr.content, 'video/mp4')}, timeout=180)
            if ur.status_code in [200, 201]:
                time.sleep(10)
                attachments.append({"type": "video", "payload": {"token": ud["token"]}})
            else: return False
            
        elif media_type == 'photo':
            pr = requests.get(media_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=REQUEST_TIMEOUT, allow_redirects=True, verify=False)
            if 'image' not in pr.headers.get('Content-Type', '') or len(pr.content) > 10 * 1024 * 1024: return False
            if is_bad_image(pr.content, title): return False
                
            up = requests.post("https://platform-api2.max.ru/uploads?type=image", headers={"Authorization": MAX_BOT_TOKEN}, timeout=15, verify=False)
            ud = up.json()
            if not ud.get("url"): return False
            
            ur = requests.post(ud["url"], headers={"Authorization": MAX_BOT_TOKEN}, files={'data': ('photo.jpg', pr.content, 'image/jpeg')}, timeout=60)
            if ur.status_code not in [200, 201]: return False
            
            token = None
            try:
                rj = ur.json()
                if "photos" in rj:
                    for _, v in rj["photos"].items():
                        if isinstance(v, dict) and "token" in v: token = v["token"]; break
                elif "token" in rj: token = rj["token"]
            except: pass
            if not token: return False
            
            attachments.append({"type": "image", "payload": {"token": token}})
    except Exception as e:
        return False

    if not attachments: return False
    payload = {"text": full_text, "format": "markdown", "attachments": attachments}
    for attempt in range(3):
        try:
            r = requests.post(f"https://platform-api2.max.ru/messages?chat_id={channel_id}", headers=headers, json=payload, timeout=REQUEST_TIMEOUT, verify=False)
            if r.status_code == 200: return True
            elif r.status_code == 400:
                err = r.json()
                if err.get("code") == "attachment.not.ready" and attempt < 2: time.sleep(5); continue
                return False
        except Exception as e:
            pass
    return False

def make_hybrid_post(title, summary):
    clean_title = clean_text_junk(title)
    clean_summary = clean_text_junk(summary)
    
    if clean_title and clean_summary.startswith(clean_title):
        clean_summary = clean_summary[len(clean_title):].strip()
        
    clean_summary = re.sub(r'^[\.\,\-\:\s]+', '', clean_summary)

    if not clean_summary:
        return f"<b>{clean_title}</b>"
        
    return f"<b>{clean_title}</b>\n\n{clean_summary}"

def process_novokuznetsk(tg_videos, tg_photos):
    if not TG_NK_CHANNEL_ID and not MAX_NK_CHANNEL_ID: 
        return
        
    now = datetime.now(timezone.utc)
    
    # 1. Собираем кандидатов из Telegram-каналов Новокузнецка/Кузбасса
    nk_candidates = get_novokuznetsk_tg_candidates(now)
    
    if not nk_candidates:
        print("Новокузнецк: после фильтрации ничего не осталось.")
        return
        
    # Сортируем: сначала видео, потом по приоритету (Новокузнецк > Кузбасс) и свежести
    nk_candidates.sort(key=lambda x: (0 if x['media_type'] == 'video' else 1, x['priority'], x['age_hours']))
    
    seen = set()
    unique_nk = []
    for c in nk_candidates:
        if c['text_hash'] in seen: continue
        seen.add(c['text_hash'])
        unique_nk.append(c)
        
    print(f"\n=== Новости Новокузнецка (К публикации: {len(unique_nk)}) ===")
    for c in unique_nk[:NK_MAX_ATTEMPTS]:
        print(f"Кандидат ({c['media_type']}, Приоритет {c['priority']}): {c['title'][:50]}")
        body = make_hybrid_post(c['title'], c['summary'])
        
        tg_ok = False
        if TG_NK_CHANNEL_ID:
            tg_ok = send_to_telegram(body, c['media_type'], c['media_url'], channel_id=TG_NK_CHANNEL_ID, signature=SIGNATURE_NK_TG, title=c['title'], is_nk=True)
            print(f"Новокузнецк TG: {'OK' if tg_ok else 'FAIL'}")
            
        max_ok = False
        if MAX_NK_CHANNEL_ID:
            max_ok = send_to_max(body, c['media_type'], c['media_url'], channel_id=MAX_NK_CHANNEL_ID, signature=SIGNATURE_NK_MAX, title=c['title'], is_nk=True)
            print(f"Новокузнецк MAX: {'OK' if max_ok else 'FAIL'}")
            
        if tg_ok or max_ok:
            save_posted_nk_hash(c['text_hash'])
            save_nk_published_title(c['title'])
            return

def main():
    ensure_state_files_exist()
    now = datetime.now(timezone.utc)
    
    print(">>> Сбор видео и фото из Telegram для Основного канала...")
    all_videos = []
    all_photos = []
    for ch in TG_CHANNELS:
        all_videos.extend(get_tg_web_videos(ch, now))
        all_photos.extend(get_tg_web_photos(ch, now))
    print(f"Собрано: {len(all_videos)} видео, {len(all_photos)} фото.")

    print(">>> Обработка Новокузнецка (только Telegram)...")
    process_novokuznetsk([], []) # Передаем пустые списки, так как Новокузнецк теперь собирает сам

    print(">>> Обработка основного канала...")
    main_candidates = all_videos + all_photos
    
    main_candidates.sort(key=lambda x: (0 if x['media_type'] == 'video' else 1, x['age_hours']))

    posted_hashes = get_posted_hashes()
    posted_photos_urls = get_posted_photos()
    posted_videos_urls = get_posted_videos()
    recent_titles = get_recent_titles()

    seen = set()
    unique_main = []
    for c in main_candidates:
        if c['text_hash'] in seen: continue
        if c['media_type'] == 'photo' and c['media_url'] in posted_photos_urls: continue
        if c['media_type'] == 'video' and c['media_url'] in posted_videos_urls: continue
        if is_duplicate_text(c['summary'], posted_hashes): continue
        if is_duplicate_title(c['title'], recent_titles): continue
        seen.add(c['text_hash'])
        unique_main.append(c)

    if unique_main:
        print(f"🔥 Найдено {len(unique_main)} кандидатов для основного канала.")
        for c in unique_main[:5]:
            print(f"\nКандидат: {c['title'][:50]}... ({c['media_type']})")
            body = make_hybrid_post(c['title'], c['summary'])
            
            tg_ok = send_to_telegram(body, c['media_type'], c['media_url'], title=c['title'])
            print(f"Telegram: {'OK' if tg_ok else 'FAIL'}")
            if not tg_ok: continue
            
            save_posted_link(c['link'])
            save_published_title(c['title'])
            save_posted_hash(c['text_hash'])
            
            max_ok = send_to_max(body, c['media_type'], c['media_url'], title=c['title'])
            print(f"MAX: {'OK' if max_ok else 'FAIL'}")
            print("\n🎉 Готово!")
            return
    else:
        print("❌ Для основного канала ничего нового не найдено.")
        
    sys.exit(0)

if __name__ == "__main__":
    main()
