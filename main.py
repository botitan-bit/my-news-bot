import os
import sys
import functools
import requests
import re
import html
import time
import io
import urllib3
import hashlib
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

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
MAX_BOT_TOKEN = os.environ.get("MAX_BOT_TOKEN", "").strip()
MAX_CHANNEL_ID = os.environ.get("MAX_CHANNEL_ID", "").strip()

REQUEST_TIMEOUT = 15

SIGNATURE_TG = '<b><a href="https://t.me/+l7bgzfXgngBkN2My">ПЕРВЫЕ НОВОСТИ</a></b>'
SIGNATURE_MAX = '**[ПЕРВЫЕ НОВОСТИ](https://max.ru/channel_pervonovosti)**'

TG_CHANNELS = ["novosti_efir", "slavaded1337", "botcharov", "mnogonazi", "zhest_na_dorogah"]

AD_WORDS = [
    "реклама", "промокод", "скидка", "erid", "маркировка",
    "казино", "ставки", "криптовалюта", "инвестиции", "заработок",
    "подписывайтесь", "подписаться", "подпишись", "перейти по ссылке", 
    "спонсор", "распродажа", "бонус", "читать далее", "читать полностью", 
    "подарок", "бесплатно", "только сегодня", "успей", "торопись", "оформить заказ",
    "заказать", "купить", "магазин", "акция", "промо", "розыгрыш",
    "партнерство", "партнёрство", "альянс", "кэшбэк", "кэшбек", "депозит", "привилегии",
    "альфа", "альфа-банк", "альфа банк", "сбер", "сбербанк", "тинькофф", "т-банк", "втб", "росбанк", "банк", "кредит", "ипотека",
    "смотрите здесь", "rutube", "радио", "трансляция", "бочарик",
    "тариф", "тарифы", "абонент", "абонентам", "оператор", "связи", "гигабайт", "гигабайты", "минуты", "смс", 
    "т2", "теле2", "мтс", "билайн", "мегафон"
]

IMG_AD_PHRASES = ["8-800", "8 800", "ооо", "реклама", "заказать", "erid", "промокод", "скидка", "змппсм", "агротрак", "подпишись", "подписаться", "т2", "тариф"]

def ensure_state_files_exist():
    for file in [
        "posted_news.txt", "published_titles.txt",
        "posted_images.txt", "posted_videos.txt", "posted_hashes.txt", "last_channel.txt"
    ]:
        if not os.path.exists(file):
            open(file, 'a').close()

def clean_text_junk(text):
    if not text: return ""
    text = html.unescape(text)
    
    # Удаляем ссылки, хэштеги, домены
    text = re.sub(r'(?i)\b(?:https?://|www\.)\S+', ' ', text)
    text = re.sub(r'(?i)\b[a-z0-9_-]+\.(?:ru|com|net|org|info|su|io|me|tv|biz|pro|рф)(?:/\S*)?\b', ' ', text)
    text = re.sub(r'#\w+', ' ', text)
    text = re.sub(r'@\w+', ' ', text)
    text = re.sub(r'<[^>]+>', ' ', text)
    
    # Отрезаем рекламу
    text = re.sub(r'(?i)\b(подписаться|подписывайтесь|подпишись)\b.*', '', text)
    text = re.sub(r'\|\s*(?=.*?(?:MAX|МАКС|TG|ТГ|Телеграм|Telegram|@|ВК|RUTUBE|ОК|rutube)).*', '', text, flags=re.IGNORECASE)
    
    # Убираем эмодзи
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
    text = re.sub(r'[\u2600-\u27BF]', '', text)
    
    # ФИКС: Склеиваем строки, если знак препинания перенесся на новую строку
    text = re.sub(r'\n([.,;:!?»"”])', r'\1', text)
    text = re.sub(r',\s*\n\s*', ', ', text) # Запятая и перенос - склеиваем
    
    text = re.sub(r'\s+([.,;:!?])', r'\1', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n\s*\n', '\n\n', text)
    text = text.strip()

    # Безопасное удаление хвостов (МАХ, ТГ и т.д.)
    lines = text.split('\n')
    while lines:
        last_line = lines[-1].strip().lower()
        if not last_line:
            lines.pop()
            continue
        if len(last_line) < 50 and any(k in last_line for k in ['max', 'мах', 'tg', 'тг', 'телеграм', 'telegram', 'подпишись', 'газета', 'rutube', 'вк', 'vk', 'ок', 'кайло', 'прямой эфир']):
            lines.pop()
            continue
        break
        
    return '\n'.join(lines).strip()

def is_bad_image(image_bytes, title_text=""):
    try:
        img = Image.open(BytesIO(image_bytes))
        W, H = img.size
        if W < 300 or H < 200: return True
        if W * H == 0: return True
        img_gray = img.convert('L')
        stddev = ImageStat.Stat(img_gray).stddev[0]
        data = pytesseract.image_to_data(img, lang='rus+eng', output_type=pytesseract.Output.DICT)
        words = [data['text'][i].strip() for i in range(len(data.get('text', []))) if data['text'][i].strip()]
        clean_text = re.sub(r'[^\w\s]', '', ' '.join(words)).strip().lower()
        for phrase in IMG_AD_PHRASES:
            if phrase in clean_text: return True
        if stddev < 15: return True
    except: return True
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

def save_last_channel(ch):
    with open("last_channel.txt", "w", encoding="utf-8") as f:
        f.write(ch + "\n")

def is_ad(text):
    lower = text.lower()
    if re.search(r'\b\d{2}:\d{2}\b', lower) and any(w in lower for w in ['радио', 'эфир', 'трансляция', 'спутник']):
        return True
    for w in AD_WORDS:
        if re.search(r'(?<![а-яёa-z])' + re.escape(w) + r'(?![а-яёa-z])', lower): 
            return True
    return False

def extract_direct_video_url(url):
    headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://t.me/'}
    try:
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT, allow_redirects=True, verify=False)
        ctype = resp.headers.get('Content-Type', '')
        if 'video/' in ctype: return url
        soup = BeautifulSoup(html.unescape(resp.text), "html.parser")
        v_tag = soup.select_one("video") or soup.select_one("video source")
        if v_tag and (v_tag.get("src") or v_tag.get("data-src")): return v_tag.get("src") or v_tag.get("data-src")
        meta_v = soup.select_one('meta[property="og:video"]')
        if meta_v and meta_v.get("content"): return html.unescape(meta_v.get("content"))
        matches = re.findall(r'(https?://[^\s"\'<>]+?\.(?:mp4|webm)[^\s"\'<>]*)', html.unescape(resp.text))
        if matches: return html.unescape(matches[0]).replace('\\/', '/')
        if 't.me/' in url and '?embed' not in url: return extract_direct_video_url(url.split('?')[0] + '?embed=1')
    except: pass
    return None

def fetch_full_text(url):
    try:
        resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=REQUEST_TIMEOUT, verify=False)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            article = soup.select_one('article') or soup.select_one('.article-body') or soup.select_one('.news-text') or soup.select_one('.entry-content')
            if article:
                text = "\n\n".join([p.get_text(strip=True) for p in article.find_all('p') if len(p.get_text(strip=True)) > 20])
                if len(text) > 50: return text
            og_desc = soup.select_one('meta[property="og:description"]')
            if og_desc and og_desc.get('content') and len(og_desc.get('content').strip()) > 50: return og_desc.get('content').strip()
            text = "\n\n".join([p.get_text(strip=True) for p in soup.find_all('p') if len(p.get_text(strip=True)) > 30])
            if len(text) > 50: return text
    except: pass
    return None

def get_tg_web_videos(channel_name, now):
    videos = []
    try:
        resp = requests.get(f"https://t.me/s/{channel_name}", timeout=REQUEST_TIMEOUT, headers={'User-Agent': 'Mozilla/5.0'}, verify=False)
        if resp.status_code != 200: return []
        soup = BeautifulSoup(resp.text, "html.parser")
        
        for post in reversed(soup.select(".tgme_widget_message[data-post]")):
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
            clean = txt.get_text("\n", strip=True) if txt else ""
            original_title = clean.split('\n')[0].strip() if clean else ""
            
            if clean and (len(clean) < 300 or "читать далее" in clean.lower() or clean.endswith("...")):
                for l in txt.find_all('a', href=True):
                    if 'http' in l['href'] and 't.me' not in l['href'] and 'tg://' not in l['href']:
                        full_text = fetch_full_text(l['href'])
                        if full_text and len(full_text) > len(clean):
                            if full_text.lower().startswith(original_title.lower()): full_text = full_text[len(original_title):].strip()
                            clean = f"{original_title}\n\n{full_text}"
                            break
                            
            clean = clean_text_junk(clean)
            
            if not clean or len(clean) < 2:
                clean = "Видео с места событий"
                
            if is_ad(clean): continue
            
            videos.append({
                "title": original_title, "summary": clean, "age_hours": age,
                "media_type": "video", "media_url": v_url,
                "link": f"https://t.me/{post.get('data-post', '')}", "text_hash": get_text_hash(clean), "channel": channel_name
            })
    except: pass
    return videos

def get_tg_web_photos(channel_name, now):
    photos = []
    try:
        resp = requests.get(f"https://t.me/s/{channel_name}", timeout=REQUEST_TIMEOUT, headers={'User-Agent': 'Mozilla/5.0'}, verify=False)
        if resp.status_code != 200: return []
        soup = BeautifulSoup(resp.text, "html.parser")
        
        for post in reversed(soup.select(".tgme_widget_message[data-post]")):
            tt = post.select_one(".tgme_widget_message_date time")
            if not tt: continue
            try: pub = datetime.fromisoformat(tt.get("datetime").replace("Z", "+00:00"))
            except: pub = now
            age = (now - pub).total_seconds() / 3600
            if age > 24: continue
            
            pw = post.select_one(".tgme_widget_message_photo_wrap")
            p_url = None
            if pw and pw.get("style"):
                m = re.search(r"url\('([^']+)'\)", pw["style"])
                if m: p_url = m.group(1)
            if not p_url:
                img = post.select_one("img.tgme_widget_message_photo")
                if img: p_url = img.get("src")
            if not p_url: continue
            p_url = urljoin("https://t.me", p_url)
            
            txt = post.select_one(".tgme_widget_message_text")
            clean = txt.get_text("\n", strip=True) if txt else ""
            original_title = clean.split('\n')[0].strip() if clean else ""
            
            if clean and (len(clean) < 300 or "читать далее" in clean.lower() or clean.endswith("...")):
                for l in txt.find_all('a', href=True):
                    if 'http' in l['href'] and 't.me' not in l['href'] and 'tg://' not in l['href']:
                        full_text = fetch_full_text(l['href'])
                        if full_text and len(full_text) > len(clean):
                            if full_text.lower().startswith(original_title.lower()): full_text = full_text[len(original_title):].strip()
                            clean = f"{original_title}\n\n{full_text}"
                            break
                            
            clean = clean_text_junk(clean)
            
            if not clean or len(clean) < 10: continue
            if is_ad(clean): continue
            
            photos.append({
                "title": original_title, "summary": clean, "age_hours": age,
                "media_type": "photo", "media_url": p_url,
                "link": f"https://t.me/{post.get('data-post', '')}", "text_hash": get_text_hash(clean), "channel": channel_name
            })
    except: pass
    return photos

def send_video_tg(video_url, caption, chat_id):
    direct_url = extract_direct_video_url(video_url)
    if not direct_url: return False
    try:
        # Проверяем размер до скачивания
        head_resp = requests.head(direct_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15, verify=False)
        if head_resp.status_code == 200:
            cl = int(head_resp.headers.get('Content-Length', 0))
            if cl > 50 * 1024 * 1024:
                print(f"    [Отклонено] Видео > 50 МБ ({cl / (1024*1024):.1f} МБ)")
                return False
                
        resp = requests.get(direct_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=60, verify=False)
        if resp.status_code != 200: return False
        if len(resp.content) > 50 * 1024 * 1024: return False
            
        r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo", 
                          data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML", "supports_streaming": True}, 
                          files={'video': ('video.mp4', resp.content, 'video/mp4')}, timeout=90)
        if r.status_code == 200:
            save_posted_video(video_url)
            return True
    except: pass
    return False

def send_photo_tg(photo_url, caption, chat_id, title=""):
    try:
        resp = requests.get(photo_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=REQUEST_TIMEOUT, verify=False)
        if 'image' not in resp.headers.get('Content-Type', '') or len(resp.content) > 10 * 1024 * 1024: return False
        if is_bad_image(resp.content, title): return False
        r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto", 
                          data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}, 
                          files={'photo': ('photo.jpg', resp.content, 'image/jpeg')}, timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            save_posted_photo(photo_url)
            return True
    except: pass
    return False

def send_to_telegram(text, media_type, media_url, title=""):
    full_text = f"{text}\n\n{SIGNATURE_TG}"
    if len(full_text) > 1000:
        clean_title = clean_text_junk(title) if title else clean_text_junk(text.split('\n')[0])
        full_text = f"<b>{clean_title}</b>\n\n{SIGNATURE_TG}"
        
    if media_type == 'video' and media_url: return send_video_tg(media_url, full_text, TELEGRAM_CHANNEL_ID)
    elif media_type == 'photo' and media_url: return send_photo_tg(media_url, full_text, TELEGRAM_CHANNEL_ID, title)
    return False

def send_to_max(text, media_type, media_url, title=""):
    if not MAX_BOT_TOKEN or not MAX_CHANNEL_ID or not media_url: return False
    clean_text = text.replace('<b>', '**').replace('</b>', '**')
    full_text = f"{html.unescape(clean_text).strip()}\n\n{SIGNATURE_MAX}"
    if len(full_text) > 1000:
        clean_title = clean_text_junk(title) if title else clean_text_junk(text.split('\n')[0])
        full_text = f"**{clean_title}**\n\n{SIGNATURE_MAX}"

    headers = {"Authorization": MAX_BOT_TOKEN, "Content-Type": "application/json"}
    attachments = []
    
    try:
        if media_type == 'video':
            direct_url = extract_direct_video_url(media_url)
            if direct_url:
                vr = requests.get(direct_url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://t.me/'}, timeout=60, allow_redirects=True, verify=False)
                if 100 * 1024 <= len(vr.content) <= 250 * 1024 * 1024 and 'video/' in vr.headers.get('Content-Type', ''):
                    ud = requests.post("https://platform-api2.max.ru/uploads?type=video", headers={"Authorization": MAX_BOT_TOKEN}, timeout=15, verify=False).json()
                    if ud.get("url") and ud.get("token"):
                        ur = requests.post(ud["url"], headers={"Authorization": MAX_BOT_TOKEN}, files={'data': ('video.mp4', vr.content, 'video/mp4')}, timeout=180)
                        if ur.status_code in [200, 201]:
                            time.sleep(10)
                            attachments.append({"type": "video", "payload": {"token": ud["token"]}})
        elif media_type == 'photo':
            pr = requests.get(media_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=REQUEST_TIMEOUT, allow_redirects=True, verify=False)
            if 'image' in pr.headers.get('Content-Type', '') and len(pr.content) <= 10 * 1024 * 1024 and not is_bad_image(pr.content, title):
                ud = requests.post("https://platform-api2.max.ru/uploads?type=image", headers={"Authorization": MAX_BOT_TOKEN}, timeout=15, verify=False).json()
                if ud.get("url"):
                    ur = requests.post(ud["url"], headers={"Authorization": MAX_BOT_TOKEN}, files={'data': ('photo.jpg', pr.content, 'image/jpeg')}, timeout=60)
                    if ur.status_code in [200, 201]:
                        token = None
                        try:
                            rj = ur.json()
                            if "photos" in rj:
                                for _, v in rj["photos"].items():
                                    if isinstance(v, dict) and "token" in v: token = v["token"]; break
                            elif "token" in rj: token = rj["token"]
                        except: pass
                        if token: attachments.append({"type": "image", "payload": {"token": token}})
    except: pass

    if not attachments: return False
    payload = {"text": full_text, "format": "markdown", "attachments": attachments}
    for attempt in range(3):
        try:
            r = requests.post(f"https://platform-api2.max.ru/messages?chat_id={MAX_CHANNEL_ID}", headers=headers, json=payload, timeout=REQUEST_TIMEOUT, verify=False)
            if r.status_code == 200: return True
            elif r.status_code == 400:
                err = r.json()
                if err.get("code") == "attachment.not.ready" and attempt < 2: time.sleep(5); continue
                return False
        except: pass
    return False

def make_hybrid_post(title, summary):
    text = summary.strip()
    
    # ФИКС: Берем весь текст, разделяем только если есть четкий заголовок
    if title and text.startswith(title):
        body = text[len(title):].strip()
        if body and body[0] in '.,;:!?':
            title += body[0]
            body = body[1:].strip()
        if body:
            return f"<b>{title}</b>\n\n{body}"
        return f"<b>{title}</b>"

    # Если первой строкой идет заголовок, но она не закончена
    parts = text.split('\n', 1)
    if len(parts) == 2:
        potential_title = parts[0].strip()
        body = parts[1].strip()
        
        # Склеиваем со следующим предложением, если есть запятая или тире
        if potential_title.endswith((',', '-', '—', ':')):
            match = re.match(r'^([^.!?]+[.!?])\s*(.*)', body, re.DOTALL)
            if match:
                potential_title = f"{potential_title} {match.group(1).strip()}"
                body = match.group(2).strip()
                
        if len(potential_title) < 150 and body:
            return f"<b>{potential_title}</b>\n\n{body}"
        return f"<b>{potential_title}</b> {body}"

    match = re.search(r'^([^.!?]+[.!?])\s*(.*)', text, re.DOTALL)
    if match:
        first, rest = match.group(1).strip(), match.group(2).strip()
        return f"<b>{first}</b> {rest}" if rest else f"<b>{first}</b>"
        
    match = re.search(r'^([^:–—-]+[:–—-])\s*(.*)', text, re.DOTALL)
    if match:
        first, rest = match.group(1).strip(), match.group(2).strip()
        if rest and len(rest) > 20: return f"<b>{first}</b> {rest}"
        return f"<b>{first}</b>"

    return f"<b>{text}</b>" if len(text) < 100 else text

def main():
    ensure_state_files_exist()
    now = datetime.now(timezone.utc)
    
    all_videos, all_photos = [], []
    for ch in TG_CHANNELS:
        all_videos.extend(get_tg_web_videos(ch, now))
        all_photos.extend(get_tg_web_photos(ch, now))

    main_candidates = all_videos + all_photos

    posted_hashes, posted_photos_urls, posted_videos_urls = get_posted_hashes(), get_posted_photos(), get_posted_videos()
    recent_titles = get_recent_titles()

    # ФИКС: Группируем по каналам, чтобы обеспечить честную очередь
    channel_pools = {ch: [] for ch in TG_CHANNELS}
    for c in main_candidates:
        if c['channel'] in channel_pools:
            if c['media_type'] == 'photo' and c['media_url'] in posted_photos_urls: continue
            if c['media_type'] == 'video' and c['media_url'] in posted_videos_urls: continue
            if is_duplicate_text(c['summary'], posted_hashes) or is_duplicate_title(c['title'], recent_titles): continue
            channel_pools[c['channel']].append(c)

    # Берем по 2 лучших кандидата с каждого канала
    best_candidates = []
    for ch, pool in channel_pools.items():
        pool.sort(key=lambda x: x['age_hours'])
        best_candidates.extend(pool[:2])
        
    # Узнаем, какой канал был прошлым
    last_ch = ""
    if os.path.exists("last_channel.txt"):
        lines = load_lines("last_channel.txt")
        if lines: last_ch = lines[-1]
        
    # Сортируем так, чтобы канал, который публиковался в прошлый раз, был в самом конце
    best_candidates.sort(key=lambda x: (0 if x['channel'] != last_ch else 1, 0 if x['media_type'] == 'video' else 1))

    print(f"Найдено кандидатов: {len(best_candidates)}")
    
    if best_candidates:
        for c in best_candidates:
            print(f"\nКандидат: {c['title'][:50]}... ({c['media_type']}) из {c['channel']}")
            body = make_hybrid_post(c['title'], c['summary'])
            tg_ok = send_to_telegram(body, c['media_type'], c['media_url'], title=c['title'])
            
            if tg_ok:
                print("Telegram: OK")
                save_posted_link(c['link'])
                save_published_title(c['title'])
                save_posted_hash(c['text_hash'])
                save_last_channel(c['channel']) # Запоминаем канал
                send_to_max(body, c['media_type'], c['media_url'], title=c['title'])
                print("\n🎉 Готово!")
                return
            else:
                print("Telegram: FAIL (пропускаем)")
                
    print("❌ Ничего нового не удалось опубликовать.")
    sys.exit(0)

if __name__ == "__main__":
    main()
