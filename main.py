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

# --- Ключи ---
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
MAX_BOT_TOKEN = os.environ.get("MAX_BOT_TOKEN", "").strip()
MAX_CHANNEL_ID = os.environ.get("MAX_CHANNEL_ID", "").strip()
VK_TOKEN = os.environ.get("VK_TOKEN", "").strip()
VK_GROUP_ID = os.environ.get("VK_GROUP_ID", "").strip()

TG_NK_CHANNEL_ID = os.environ.get("TG_NK_CHANNEL_ID", "").strip()
MAX_NK_CHANNEL_ID = os.environ.get("MAX_NK_CHANNEL_ID", "").strip()

LOGO_WIDTH = 80
POST_PHOTO_TO_VK = True

SIGNATURE_TG = '<b><a href="https://t.me/+l7bgzfXgngBkN2My">ПЕРВЫЕ НОВОСТИ</a></b>'
SIGNATURE_MAX = '**[ПЕРВЫЕ НОВОСТИ](https://max.ru/channel_pervonovosti)**'

SIGNATURE_NK_TG = '<b><a href="https://t.me/+l7bgzfXgngBkN2My">НОВОКУЗНЕЦК | ПЕРВЫЕ НОВОСТИ</a></b>'
SIGNATURE_NK_MAX = '**[НОВОКУЗНЕЦК | ПЕРВЫЕ НОВОСТИ](https://max.ru/channel_pervonovosti)**'

LOCAL_CHANNELS = {"novokuznetsk": "Новокузнецк"}

NK_RSS_FEEDS = [
    "https://www.city-n.ru/rss/news.xml",
    "https://vashgorod.ru/rss/news",
    "https://nk-tv.ru/rss",
    "https://kuzbassnews.ru/rss",
    "https://www.kem.kp.ru/rss/",
    "https://lenta.ru/rss/news",
    "https://ria.ru/export/rss2/archive/index.xml",
]

# Только рекламные слова
AD_WORDS = [
    "реклама", "промокод", "скидка", "erid", "маркировка",
    "казино", "ставки", "криптовалюта", "инвестиции", "заработок",
    "подписывайтесь", "перейти по ссылке", "спонсор", "распродажа", "бонус",
    "подарок", "бесплатно", "только сегодня", "успей", "торопись", "оформить заказ",
    "заказать", "купить", "магазин", "акция", "промо", "розыгрыш"
]

def ensure_state_files_exist():
    for file in [
        "last_theme.txt", "posted_news.txt", "published_titles.txt",
        "posted_images.txt", "posted_videos.txt", "posted_hashes.txt",
        "posted_nk_hashes.txt", "posted_nk_images.txt", "published_nk_titles.txt"
    ]:
        if not os.path.exists(file):
            open(file, 'a').close()

# --- Дедупликация ---
def get_text_hash(text):
    clean = re.sub(r'[^\w\s]', '', text.lower())
    words = sorted(set([w for w in clean.split() if len(w) > 4]))
    return " ".join(words[:30])

def is_duplicate_text(text, hashes):
    clean = re.sub(r'[^\w\s]', '', text.lower())
    new_words = set(sorted(set([w for w in clean.split() if len(w) > 4]))[:30])
    if not new_words:
        return False
    for old in hashes[-200:]:
        old_words = set(old.split())
        if not old_words:
            continue
        inter = new_words.intersection(old_words)
        union = new_words.union(old_words)
        if len(union) > 0 and (len(inter) / len(union)) > 0.4:
            return True
    return False

# --- Файловые хелперы ---
def load_lines(fn):
    if os.path.exists(fn):
        with open(fn, "r", encoding="utf-8") as f:
            return f.read().splitlines()
    return []

def append_line(fn, line):
    if not line: return
    with open(fn, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def get_posted_hashes(): return load_lines("posted_hashes.txt")
def save_posted_hash(h): append_line("posted_hashes.txt", h)
def get_posted_links(): return load_lines("posted_news.txt")
def save_posted_link(l): append_line("posted_news.txt", l)
def get_posted_videos(): return load_lines("posted_videos.txt")
def save_posted_video(h): append_line("posted_videos.txt", h)
def get_posted_photos(): return load_lines("posted_images.txt")
def save_posted_photo(u): append_line("posted_images.txt", u)
def get_recent_titles(): return load_lines("published_titles.txt")

def save_published_title(t):
    append_line("published_titles.txt", t)
    titles = get_recent_titles()
    if len(titles) > 15:
        with open("published_titles.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(titles[-15:]) + "\n")

# NK хелперы
def get_posted_nk_hashes(): return load_lines("posted_nk_hashes.txt")
def save_posted_nk_hash(h): append_line("posted_nk_hashes.txt", h)
def get_posted_nk_photos(): return load_lines("posted_nk_images.txt")
def save_posted_nk_photo(u): append_line("posted_nk_images.txt", u)
def get_recent_nk_titles(): return load_lines("published_nk_titles.txt")

def save_nk_published_title(t):
    append_line("published_nk_titles.txt", t)
    titles = get_recent_nk_titles()
    if len(titles) > 15:
        with open("published_nk_titles.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(titles[-15:]) + "\n")

# --- Проверка на рекламу ---
def is_ad_with_reason(text):
    lower = text.lower()
    for w in AD_WORDS:
        pattern = r'(?<![а-яёa-z])' + re.escape(w)
        if re.search(pattern, lower):
            return w
    return None

def is_ad(text):
    return is_ad_with_reason(text) is not None

# --- Извлечение прямых ссылок на видео ---
def extract_direct_video_url(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Referer': 'https://t.me/'
    }
    try:
        resp = requests.get(url, headers=headers, timeout=30, allow_redirects=True)
        ctype = resp.headers.get('Content-Type', '')
        if 'video/' in ctype:
            return url
        html_text = html.unescape(resp.text)
        soup = BeautifulSoup(html_text, "html.parser")
        v_tag = soup.select_one("video")
        if v_tag and (v_tag.get("src") or v_tag.get("data-src")):
            return v_tag.get("src") or v_tag.get("data-src")
        s_tag = soup.select_one("video source")
        if s_tag and (s_tag.get("src") or s_tag.get("data-src")):
            return s_tag.get("src") or s_tag.get("data-src")
        meta_v = soup.select_one('meta[property="og:video"]')
        if meta_v and meta_v.get("content"):
            return html.unescape(meta_v.get("content"))
        matches = re.findall(r'(https?://[^\s"\'<>]+?\.(?:mp4|webm)[^\s"\'<>]*)', html_text)
        if matches:
            return html.unescape(matches[0]).replace('\\/', '/')
        if 't.me/' in url and '?embed' not in url:
            embed_url = url.split('?')[0] + '?embed=1'
            return extract_direct_video_url(embed_url)
    except Exception as e:
        print(f"  ⚠️ extract_direct_video_url: {e}")
    return None

# --- Новокузнецк ---
def get_novokuznetsk_candidates():
    now = datetime.now(timezone.utc)
    keywords = ["новокузнецк", "кузбасс", "кемерово"]
    posted_hashes = get_posted_nk_hashes()
    posted_photos = get_posted_nk_photos()
    candidates = []
    for feed_url in NK_RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            if not feed.entries: continue
            for entry in feed.entries:
                title = entry.get('title', '')
                summary = entry.get('summary', '') or entry.get('description', '')
                if not any(k in f"{title} {summary}".lower() for k in keywords): continue
                pub_date = now
                if 'published_parsed' in entry:
                    pub_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                elif 'updated_parsed' in entry:
                    pub_date = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
                age_hours = (now - pub_date).total_seconds() / 3600
                if age_hours > 24: continue
                
                media_url = None
                media_type = None
                if 'media_content' in entry:
                    for m in entry.media_content:
                        if m.get('type', '').startswith('video'):
                            media_url = m.get('url'); media_type = 'video'; break
                if not media_url and 'links' in entry:
                    for link in entry.links:
                        if link.get('rel') == 'enclosure' and link.get('type', '').startswith('video'):
                            media_url = link.get('href'); media_type = 'video'; break
                if not media_url:
                    if 'media_content' in entry:
                        for m in entry.media_content:
                            if m.get('type', '').startswith('image'):
                                media_url = m.get('url'); media_type = 'photo'; break
                    if not media_url and 'media_thumbnail' in entry:
                        for m in entry.media_thumbnail:
                            if m.get('url'):
                                media_url = m.get('url'); media_type = 'photo'; break
                    if not media_url and 'links' in entry:
                        for link in entry.links:
                            if link.get('rel') == 'enclosure' and link.get('type', '').startswith('image'):
                                media_url = link.get('href'); media_type = 'photo'; break
                if not media_url and summary:
                    soup = BeautifulSoup(summary, 'html.parser')
                    img = soup.find('img')
                    if img and img.get('src'):
                        media_url = img['src']; media_type = 'photo'
                if not media_url: continue
                
                clean_text = BeautifulSoup(summary, 'html.parser').get_text(separator='\n', strip=True)
                if len(clean_text) < 20: continue
                if media_url in posted_photos: continue
                th = get_text_hash(clean_text)
                if is_duplicate_text(clean_text, posted_hashes): continue
                if is_ad(clean_text): continue
                
                candidates.append({
                    'title': title, 'summary': clean_text, 'age_hours': age_hours,
                    'media_type': media_type, 'media_url': media_url,
                    'link': entry.get('link', ''), 'text_hash': th, 'channel': 'novokuznetsk'
                })
        except Exception as e:
            print(f"Ошибка RSS {feed_url}: {e}")
    seen = set()
    unique = []
    for c in candidates:
        if c['text_hash'] in seen: continue
        seen.add(c['text_hash'])
        unique.append(c)
    return unique

# --- Обработка видео ---
def process_video(video_bytes):
    if video_bytes.startswith(b'<!DOCTYPE html>') or b'<html' in video_bytes[:1000]:
        print("  ❌ HTML вместо видео. Пропускаем обработку.")
        return None, None
    if not os.path.exists("logo.png"):
        logo_input = None
        fc = 'fps=30,scale=ceil(iw/2)*2:ceil(ih/2)*2,format=yuv420p'
    else:
        logo_input = 'logo.png'
        fc = f'[1:v]scale={LOGO_WIDTH}:-1[logo];[0:v][logo]overlay=W-w-20:20,fps=30,scale=ceil(iw/2)*2:ceil(ih/2)*2,format=yuv420p'
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tin:
            tin.write(video_bytes)
            tin_path = tin.name
        tout = tin_path.replace(".mp4", "_out.mp4")
        tthumb = tin_path.replace(".mp4", "_thumb.jpg")
        cmd = ['ffmpeg', '-y', '-i', tin_path]
        if logo_input: cmd.extend(['-i', logo_input])
        cmd.extend(['-filter_complex', fc, '-c:v', 'libx264', '-profile:v', 'baseline',
                    '-level', '3.0', '-crf', '23', '-preset', 'ultrafast',
                    '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', tout])
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
        if res.returncode != 0:
            print(f"  ❌ Ошибка FFmpeg ({res.returncode}).")
            return None, None
        thumb_cmd = ['ffmpeg', '-y', '-ss', '00:00:01.000', '-i', tout,
                     '-vf', 'scale=320:-1', '-vframes', '1', '-q:v', '2', tthumb]
        subprocess.run(thumb_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        out_bytes = None; thumb_bytes = None
        if os.path.exists(tout):
            with open(tout, 'rb') as f: out_bytes = f.read()
        if os.path.exists(tthumb):
            with open(tthumb, 'rb') as f: thumb_bytes = f.read()
        print("  ✅ Видео перекодировано и миниатюра сгенерирована.")
        return out_bytes, thumb_bytes
    except Exception as e:
        print(f"  ⚠️ Ошибка обработки видео: {e}")
        return None, None
    finally:
        for p in [tin_path, tout, tthumb]:
            if 'p' in locals() and os.path.exists(p): os.remove(p)

# --- Отправка в Telegram ---
def send_video(video_url, caption, chat_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"
    direct_url = extract_direct_video_url(video_url)
    if not direct_url:
        print("  ❌ Не удалось извлечь прямую ссылку на видео.")
        return False
    print(f"  -> Скачиваем видео: {direct_url[:60]}...")
    headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://t.me/'}
    try:
        resp = requests.get(direct_url, headers=headers, timeout=60)
        ctype = resp.headers.get('Content-Type', '')
        video_data = resp.content
        if len(video_data) == 0 or 'video/' not in ctype or len(video_data) > 50 * 1024 * 1024:
            print(f"  ❌ Не видео (size={len(video_data)}, ctype={ctype}).")
            return False
        video_data, thumb_data = process_video(video_data)
        if video_data is None:
            return False
        video_hash = hashlib.md5(video_data).hexdigest()
        files = {'video': ('video.mp4', video_data, 'video/mp4')}
        data = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML", "supports_streaming": True}
        if thumb_data:
            files['thumbnail'] = ('thumb.jpg', thumb_data, 'image/jpeg')
        print("  -> Загружаем видео в Telegram...")
        r = requests.post(url, data=data, files=files, timeout=90)
        if r.status_code == 200:
            save_posted_video(video_hash)
            return True
        print(f"  ❌ TG API: {r.text[:200]}")
    except Exception as e:
        print(f"  ⚠️ Ошибка TG видео: {e}")
    return False

def send_photo(photo_url, caption, chat_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(photo_url, headers=headers, timeout=30)
        ctype = resp.headers.get('Content-Type', '')
        if 'image' not in ctype:
            print(f"  ❌ Не фото (ctype={ctype}).")
            return False
        photo_data = resp.content
        if len(photo_data) == 0 or len(photo_data) > 10 * 1024 * 1024:
            print(f"  ❌ Фото слишком большое ({len(photo_data)} байт).")
            return False
        files = {'photo': ('photo.jpg', photo_data, 'image/jpeg')}
        data = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}
        print("  -> Загружаем фото в Telegram...")
        r = requests.post(url, data=data, files=files, timeout=60)
        if r.status_code == 200:
            save_posted_photo(photo_url)
            return True
        print(f"  ❌ TG API (фото): {r.text[:200]}")
    except Exception as e:
        print(f"  ⚠️ Ошибка TG фото: {e}")
    return False

def send_to_telegram(text, media_type, media_url, channel_id=None, signature=None):
    if channel_id is None: channel_id = TELEGRAM_CHANNEL_ID
    if signature is None: signature = SIGNATURE_TG
    full_text = f"{text}\n\n{signature}"
    if media_type == 'video' and media_url:
        return send_video(media_url, full_text, channel_id)
    elif media_type == 'photo' and media_url:
        return send_photo(media_url, full_text, channel_id)
    return False

# --- Отправка в MAX ---
def send_to_max(text, media_type, media_url, channel_id=None, signature=None):
    if channel_id is None: channel_id = MAX_CHANNEL_ID
    if signature is None: signature = SIGNATURE_MAX
    if not MAX_BOT_TOKEN or not channel_id: return False
    if media_type not in ('video', 'photo') or not media_url: return False
    clean_text = text.replace('<b>', '**').replace('</b>', '**')
    clean_text = html.unescape(clean_text).strip()
    clean_text = f"{clean_text}\n\n{signature}"
    headers = {"Authorization": MAX_BOT_TOKEN, "Content-Type": "application/json"}
    attachments = []
    
    try:
        if media_type == 'video':
            direct_url = extract_direct_video_url(media_url)
            if not direct_url:
                print("  ❌ MAX: не удалось извлечь ссылку на видео.")
                return False
            dl = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://t.me/'}
            vr = requests.get(direct_url, headers=dl, timeout=60, allow_redirects=True)
            ctype = vr.headers.get('Content-Type', '')
            vdata = vr.content
            if len(vdata) < 100 * 1024 or 'video/' not in ctype:
                print(f"  ❌ MAX: не видео (size={len(vdata)}, ctype={ctype}).")
                return False
            if len(vdata) > 250 * 1024 * 1024:
                print("  ❌ MAX: видео > 250 МБ.")
                return False
            vdata, _ = process_video(vdata)
            if vdata is None: return False
            up = requests.post(
                "https://platform-api2.max.ru/uploads?type=video",
                headers={"Authorization": MAX_BOT_TOKEN}, timeout=15, verify=False
            )
            ud = up.json()
            if not (ud.get("url") and ud.get("token")):
                return False
            ur = requests.post(
                ud["url"], headers={"Authorization": MAX_BOT_TOKEN},
                files={'data': ('video.mp4', vdata, 'video/mp4')}, timeout=180
            )
            if ur.status_code in [200, 201]:
                print("  ✅ MAX: видео загружено.")
                time.sleep(10)
                attachments.append({"type": "video", "payload": {"token": ud["token"]}})
            else:
                return False
                
        elif media_type == 'photo':
            dl = {'User-Agent': 'Mozilla/5.0'}
            pr = requests.get(media_url, headers=dl, timeout=60, allow_redirects=True)
            ctype = pr.headers.get('Content-Type', '')
            if 'image' not in ctype:
                print(f"  ❌ MAX: не фото (ctype={ctype}).")
                return False
            if len(pr.content) > 10 * 1024 * 1024:
                print("  ❌ MAX: фото > 10 МБ.")
                return False
            up = requests.post(
                "https://platform-api2.max.ru/uploads?type=image",
                headers={"Authorization": MAX_BOT_TOKEN}, timeout=15, verify=False
            )
            ud = up.json()
            if not ud.get("url"): return False
            ur = requests.post(
                ud["url"], headers={"Authorization": MAX_BOT_TOKEN},
                files={'data': ('photo.jpg', pr.content, 'image/jpeg')}, timeout=60
            )
            if ur.status_code not in [200, 201]: return False
            token = None
            try:
                rj = ur.json()
                if "photos" in rj:
                    for _, v in rj["photos"].items():
                        if isinstance(v, dict) and "token" in v:
                            token = v["token"]; break
                elif "token" in rj:
                    token = rj["token"]
            except: pass
            if not token: return False
            attachments.append({"type": "image", "payload": {"token": token}})
    except Exception as e:
        print(f"  ⚠️ Ошибка медиа MAX: {e}")
        return False
        
    if not attachments:
        return False
        
    payload = {"text": clean_text, "format": "markdown", "attachments": attachments}
    for attempt in range(3):
        try:
            url = f"https://platform-api2.max.ru/messages?chat_id={channel_id}"
            r = requests.post(url, headers=headers, json=payload, timeout=20, verify=False)
            if r.status_code == 200:
                print("  ✅ MAX: опубликовано.")
                return True
            elif r.status_code == 400:
                err = r.json()
                if err.get("code") == "attachment.not.ready" and attempt < 2:
                    time.sleep((attempt + 1) * 10); continue
                print(f"  ❌ MAX: {err}")
                return False
            else:
                r.raise_for_status()
        except Exception as e:
            if attempt == 2: return False
            time.sleep(10)
    return False

# --- Основной парсинг TG ---
def get_tg_web_videos(channel_name, now):
    videos = []
    posted_videos = get_posted_videos()
    posted_hashes = get_posted_hashes()
    url = f"https://t.me/s/{channel_name}"
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'}
        resp = requests.get(url, timeout=10, headers=headers)
        if resp.status_code != 200:
            print(f"  [{channel_name}] HTTP {resp.status_code}")
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        posts = soup.select(".tgme_widget_message[data-post]")
        if not posts:
            print(f"  [{channel_name}] Постов не найдено")
            return []
        print(f"  [{channel_name}] Найдено постов: {len(posts)}")
        c_v = c_ad = c_old = c_dup = 0
        reasons = {}
        for post in reversed(posts):
            tt = post.select_one(".tgme_widget_message_date time")
            if not tt: continue
            try:
                pub = datetime.fromisoformat(tt.get("datetime").replace("Z", "+00:00"))
            except: pub = now
            age = (now - pub).total_seconds() / 3600
            if age > 24:
                c_old += 1; continue
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
            c_v += 1
            v_url = urljoin("https://t.me", v_url)
            if v_url in posted_videos:
                c_dup += 1; continue
            txt = post.select_one(".tgme_widget_message_text")
            if not txt: continue
            clean = txt.get_text("\n", strip=True)
            if len(clean) < 20: continue
            th = get_text_hash(clean)
            if is_duplicate_text(clean, posted_hashes):
                c_dup += 1; continue
            pid = post.get("data-post", "")
            reason = is_ad_with_reason(clean)
            if reason:
                c_ad += 1
                reasons[reason] = reasons.get(reason, 0) + 1
                continue
            videos.append({
                "title": clean[:60] + "...", "summary": clean, "age_hours": age,
                "media_type": "video", "media_url": v_url,
                "link": f"https://t.me/{pid}", "text_hash": th, "channel": channel_name
            })
        if not videos:
            print(f"  [{channel_name}] Видео: {c_v} | Реклама: {c_ad} | Старше 24ч: {c_old} | Дубли: {c_dup}")
            if reasons:
                print(f"    Причины: {reasons}")
    except Exception as e:
        print(f"Ошибка {channel_name}: {e}")
    return videos

def get_news_candidates():
    now = datetime.now(timezone.utc)
    # 🆕 Добавлен канал zhest_na_dorogah
    channels = ["novosti_efir", "slavaded1337", "botcharov", "mnogonazi", "zhest_na_dorogah"]
    print("  -> Ищем видео в Telegram-каналах...")
    all_v = []
    for ch in channels:
        all_v.extend(get_tg_web_videos(ch, now))
    if all_v:
        all_v.sort(key=lambda x: x['age_hours'])
        out = []
        counts = {}
        batch_hashes = []
        for v in all_v:
            ch = v['channel']
            if counts.get(ch, 0) >= 2:
                continue
            if is_duplicate_text(v['summary'], batch_hashes):
                print(f"    (дубль внутри батча: {v['channel']} — {v['title'][:40]})")
                continue
            batch_hashes.append(v['text_hash'])
            out.append(v)
            counts[ch] = counts.get(ch, 0) + 1
            if len(out) >= 10: break
        print(f"🔥 Найдено {len(out)} ВИДЕО.")
        return out
    print("  ❌ Видео не найдено.")
    return []

# --- ИИ ---
def call_groq(prompt):
    if not GROQ_API_KEY: return ""
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": "openai/gpt-oss-120b", "messages": [{"role": "user", "content": prompt}]}
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=15)
        r.raise_for_status()
        return r.json()['choices'][0]['message']['content'].strip()
    except Exception as e:
        print(f"⚠️ Ошибка Groq: {e}")
        return ""

def sanitize_html(text):
    text = text.replace('<b>', '||BOLD_S||').replace('</b>', '||BOLD_E||')
    text = html.escape(text)
    return text.replace('||BOLD_S||', '<b>').replace('||BOLD_E||', '</b>')

def rewrite_with_ai(title, summary, channel_name=""):
    summary = re.sub(r'@[a-zA-Z0-9_]+', '', summary)
    summary = re.sub(r'https?://t\.me/[a-zA-Z0-9_]+', '', summary)
    if channel_name in LOCAL_CHANNELS:
        city = LOCAL_CHANNELS[channel_name]
        ci = f'Новость из "{channel_name}" (город {city}). Если есть улица без города — добавь {city}.'
    else:
        ci = 'Не добавляй города, если их нет.'
    prompt = f"""Ты — строгий редактор. Оформи новость.
1. Не меняй смысл и факты.
2. Удали явные оскорбления и призывы к насилию.
3. Если текст >800 символов — сократи до сути.
4. Сверху жирный заголовок (до 80 символов) в <b>...</b>.
5. После заголовка — ДВА переноса и текст.
6. Удали упоминания каналов и ссылки на Telegram.
7. {ci}
8. Запрещены эмодзи.
9. Оформляй любой текст, даже если это короткая фраза, мем или приветствие. Не отклоняй посты.

ФОРМАТ: только готовый пост.

ТЕКСТ:
{summary}"""
    raw = call_groq(prompt)
    if not raw:
        print("⚠️ ИИ вернул пустоту.")
        return None
    raw = re.sub(r'^(Category|Рубрика|Категория):.*?\n', '', raw, flags=re.IGNORECASE)
    raw = re.sub(r'</b>\s*', '</b>\n\n', raw)
    raw = raw.replace('\\n', '\n')[:1000]
    raw = re.sub(r'[^.!?\n]+$', '', raw).strip()
    raw = re.sub(r'(?i)перейти в канал\.?', '', raw)
    raw = re.sub(r'(?i)подписывайтесь.*', '', raw)
    raw = re.sub(r'(?i)читайте нас.*', '', raw)
    raw = re.sub(r'\n{3,}', '\n\n', raw)
    raw = re.sub(r'[^\w\sа-яА-ЯёЁ.,;:!?()\[\]{}<>="\'/\-+#*&%$@|~^]', '', raw)
    plain = re.sub(r'<[^>]+>', '', raw)
    if len(plain.strip()) < 15:
        print("⚠️ После заголовка нет текста.")
        return None
    return sanitize_html(raw)

# --- Процесс Новокузнецка ---
def process_novokuznetsk():
    if not TG_NK_CHANNEL_ID and not MAX_NK_CHANNEL_ID:
        print("Новокузнецк: ID каналов не заданы.")
        return
    print("\n=== Новости Новокузнецка ===")
    cands = get_novokuznetsk_candidates()
    if not cands:
        print("Новокузнецк: ничего не найдено.")
        return
    cands.sort(key=lambda x: x['age_hours'])
    for c in cands[:5]:
        print(f"Кандидат: {c['title'][:60]}")
        body = rewrite_with_ai(c['title'], c['summary'], 'novokuznetsk')
        if not body:
            print("Новокузнецк: ИИ отклонил.")
            continue
        tg_ok = False
        if TG_NK_CHANNEL_ID:
            tg_ok = send_to_telegram(body, c['media_type'], c['media_url'],
                                     channel_id=TG_NK_CHANNEL_ID, signature=SIGNATURE_NK_TG)
            print(f"Новокузнецк TG: {'OK' if tg_ok else 'FAIL (медиа не ушло)'}")
        max_ok = False
        if MAX_NK_CHANNEL_ID:
            max_ok = send_to_max(body, c['media_type'], c['media_url'],
                                 channel_id=MAX_NK_CHANNEL_ID, signature=SIGNATURE_NK_MAX)
            print(f"Новокузнецк MAX: {'OK' if max_ok else 'FAIL (медиа не ушло)'}")
        if tg_ok or max_ok:
            save_posted_nk_hash(c['text_hash'])
            save_nk_published_title(c['title'])
            if c['media_type'] == 'photo':
                save_posted_nk_photo(c['media_url'])
            print(f"Новокузнецк: опубликовано '{c['title'][:50]}'")
            return
        else:
            print("Новокузнецк: медиа не ушло, пробуем следующего.")

# --- Main ---
def main():
    ensure_state_files_exist()
    if not os.path.exists("logo.png"):
        print("⚠️ Файл logo.png не найден.")
        
    process_novokuznetsk()
    
    print("\n=== Ищем свежие новости (основной канал) ===")
    cands = get_news_candidates()
    
    if cands:
        for c in cands:
            print(f"\nКандидат: {c['title']}")
            body = rewrite_with_ai(c['title'], c['summary'], c.get('channel', ''))
            if not body:
                print("❌ Отклонено ИИ, пробуем следующего.")
                continue
                
            print(f"✅ Новость: {c['title']}")
            tg_ok = send_to_telegram(body, c['media_type'], c['media_url'])
            print(f"Telegram: {'OK' if tg_ok else 'FAIL'}")
            
            if not tg_ok:
                print("⚠️ Медиа не отправлено в Telegram. Пробуем следующего кандидата.")
                continue
                
            save_posted_link(c['link'])
            save_published_title(c['title'])
            save_posted_hash(c['text_hash'])
            
            print("Запускаем отправку в MAX...")
            max_ok = send_to_max(body, c['media_type'], c['media_url'])
            print(f"MAX: {'OK' if max_ok else 'FAIL'}")
            
            print("ВКонтакте временно отключен.")
            print("\n🎉 Готово!")
            return
            
        print("\n❌ Все кандидаты отклонены или медиа не ушло.")
    else:
        print("\n❌ Новостей не найдено.")
    sys.exit(0)

if __name__ == "__main__":
    main()
