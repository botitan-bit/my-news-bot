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
import random
import subprocess
import tempfile
import traceback
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime, timezone, timedelta
import vk_api
from vk_api.upload import VkUpload
from PIL import Image, ImageStat
import pytesseract
from io import BytesIO

# Принудительный сброс буфера, чтобы все print доходили до логов GitHub
sys.stdout.reconfigure(line_buffering=True)
print = functools.partial(print, flush=True)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

print("=== БОТ ЗАПУСТИЛСЯ ===")

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
NK_MAX_ATTEMPTS = 10

# --- Подписи для ОСНОВНОГО канала ---
SIGNATURE_TG = '<b><a href="https://t.me/+l7bgzfXgngBkN2My">ПЕРВЫЕ НОВОСТИ</a></b>'
SIGNATURE_MAX = '**[ПЕРВЫЕ НОВОСТИ](https://max.ru/channel_pervonovosti)**'

# --- ПОДПИСИ ДЛЯ КАНАЛА НОВОКУЗНЕЦКА ---
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

LOCAL_CHANNELS = {"novokuznetsk": "Новокузнецк"}

NK_RSS_FEEDS = [
    "https://ria.ru/export/rss2/index.xml",
    "http://www.kuzbassfm.ru/rss/news.xml",
    "https://kemerovo42.info/feed/",
    "https://kuzbass.media/feed/",
    "https://vse42.ru/rss/news.xml",
    "https://www.kem.kp.ru/rss/",
]

TG_CHANNELS = ["novosti_efir", "slavaded1337", "botcharov", "mnogonazi", "zhest_na_dorogah"]

NK_KEYWORDS = ["новокузнецк", "кузбасс", "кемерово", "белово", "прокопьевск", "ленинск-кузнецкий", "междуреченск", "мыски", "осинники", "киселевск", "юрга", "анжеро-судженск", "мариинск", "тайга", "гуьевск", "таштагол", "полысаево", "калтан", "березовский", "топки"]

AD_WORDS = [
    "реклама", "промокод", "скидка", "erid", "маркировка",
    "казино", "ставки", "криптовалюта", "инвестиции", "заработок",
    "подписывайтесь", "перейти по ссылке", "спонсор", "распродажа", "бонус",
    "подарок", "бесплатно", "только сегодня", "успей", "торопись", "оформить заказ",
    "заказать", "купить", "магазин", "акция", "промо", "розыгрыш"
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

def normalize_url(url, base=""):
    if not url: return None
    if url.startswith('//'): return 'https:' + url
    if not url.startswith('http'): return urljoin(base, url)
    return url

def is_bad_image_url(url):
    if not url: return True
    lower = url.lower()
    return any(k in lower for k in ['banner', 'reklama', 'ad_', 'adv', 'logo', 'icon', 'avatar', 'pixel', 'stub'])

def is_text_image(image_bytes, title_text=""):
    try:
        img = Image.open(BytesIO(image_bytes))
        W, H = img.size
        if W * H == 0:
            return False

        img_gray = img.convert('L')
        stat = ImageStat.Stat(img_gray)
        stddev = stat.stddev[0] if stat.stddev else 0

        data = pytesseract.image_to_data(
            img, lang='rus+eng', output_type=pytesseract.Output.DICT
        )

        words = []
        total_area = 0
        n = len(data.get('text', []))
        for i in range(n):
            w = (data['text'][i] or '').strip()
            if not w:
                continue
            try:
                conf = int(float(data['conf'][i]))
            except (ValueError, TypeError):
                conf = -1
            if conf < 50:
                continue
            ww = int(data['width'][i] or 0)
            hh = int(data['height'][i] or 0)
            words.append(w)
            total_area += ww * hh

        clean_text = re.sub(r'[^\w\s]', '', ' '.join(words)).strip()
        if len(clean_text) <= 40:
            return False

        coverage = total_area / float(W * H)
        snippet = clean_text[:80].replace('\n', ' ')
        
        print(f"    [OCR-проверка] {len(clean_text)} симв., покрытие {coverage:.0%}, StdDev {stddev:.0f}: {snippet!r}")

        if stddev < 25:
            print(f"    [Отклонено: однотонная графика/обложка]")
            return True

        if title_text and len(clean_text) > 10:
            clean_t = re.sub(r'[^\w\s]', '', title_text.lower())
            t_words = set(clean_t.split())
            o_words = set(clean_text.lower().split())
            if t_words:
                overlap = len(t_words.intersection(o_words)) / len(t_words)
                if overlap > 0.5:
                    print(f"    [Отклонено: обложка содержит заголовок новости]")
                    return True

        lower_text = clean_text.lower()
        for phrase in IMG_AD_PHRASES:
            if phrase in lower_text:
                print(f"    [Отклонено: рекламный баннер на картинке]")
                return True

        if len(clean_text) > 150 and coverage > 0.25:
            print(f"    [Отклонено: картинка с большим текстом]")
            return True

    except Exception as e:
        print(f"    ⚠️ Ошибка OCR: {e}")
    return False

def get_text_hash(text):
    clean = re.sub(r'[^\w\s]', '', text.lower())
    words = sorted(set([w for w in clean.split() if len(w) > 4]))
    return " ".join(words[:40])

def is_duplicate_text(text, hashes):
    clean = re.sub(r'[^\w\s]', '', text.lower())
    new_words = set(sorted(set([w for w in clean.split() if len(w) > 4]))[:40])
    if not new_words: return False
    for old in hashes[-500:]:
        old_words = set(old.split())
        if not old_words: continue
        inter = new_words.intersection(old_words)
        union = new_words.union(old_words)
        if len(union) > 0 and (len(inter) / len(union)) > 0.4: return True
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
def save_posted_video(h): append_line("posted_videos.txt", h)
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

def is_ad_with_reason(text):
    lower = text.lower()
    for w in AD_WORDS:
        pattern = r'(?<![а-яёa-z])' + re.escape(w)
        if re.search(pattern, lower): return w
    return None

def is_ad(text): return is_ad_with_reason(text) is not None

def extract_direct_video_url(url):
    headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://t.me/'}
    try:
        resp = requests.get(url, headers=headers, timeout=30, allow_redirects=True, verify=False)
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
    except Exception as e: print(f"    ⚠️ Ошибка извлечения видео: {e}")
    return None

def extract_image_from_url(url):
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True, verify=False)
        if resp.status_code != 200: return None
        soup = BeautifulSoup(resp.text, "html.parser")
        
        og_img = soup.select_one('meta[property="og:image"]')
        if og_img and og_img.get("content"):
            img_url = normalize_url(og_img.get("content"), url)
            if img_url and not is_bad_image_url(img_url): 
                return img_url
            
        tw_img = soup.select_one('meta[name="twitter:image"]')
        if tw_img and tw_img.get("content"):
            img_url = normalize_url(tw_img.get("content"), url)
            if img_url and not is_bad_image_url(img_url): 
                return img_url
                
        # Добавлен поиск по тегам <img> на странице, если og:image нет
        for img in soup.find_all('img'):
            src = img.get('src') or img.get('data-src')
            if not src: continue
            img_url = normalize_url(src, url)
            if img_url and not is_bad_image_url(img_url):
                return img_url
    except Exception as e: print(f"    ⚠️ Ошибка извлечения картинки: {e}")
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
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, timeout=10, headers=headers, verify=False)
        if resp.status_code != 200:
            print(f"  [{channel_name}] HTTP {resp.status_code}")
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        posts = soup.select(".tgme_widget_message[data-post]")
        if not posts:
            print(f"  [{channel_name}] Постов не найдено")
            return []
        print(f"  [{channel_name}] Найдено постов: {len(posts)}")
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
            if len(clean) < 20: continue
            th = get_text_hash(clean)
            pid = post.get("data-post", "")
            if is_ad(clean): continue
            
            # Ищем первое предложение для заголовка
            first_sentence_match = re.search(r'^([^.!?\n]+[.!?])', clean)
            if first_sentence_match and len(first_sentence_match.group(1)) < 120:
                title = first_sentence_match.group(1).strip()
            else:
                title = clean[:80].strip() + "..."
                
            videos.append({
                "title": title, "summary": clean, "age_hours": age,
                "media_type": "video", "media_url": v_url,
                "link": f"https://t.me/{pid}", "text_hash": th, "channel": channel_name
            })
    except Exception as e:
        print(f"❌ КРИТИЧЕСКАЯ ОШИБКА видео {channel_name}: {e}")
        traceback.print_exc()
    return videos

def get_tg_web_photos(channel_name, now):
    photos = []
    url = f"https://t.me/s/{channel_name}"
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, timeout=10, headers=headers, verify=False)
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
            if len(clean) < 20: continue
            th = get_text_hash(clean)
            pid = post.get("data-post", "")
            if is_ad(clean): continue
            
            first_sentence_match = re.search(r'^([^.!?\n]+[.!?])', clean)
            if first_sentence_match and len(first_sentence_match.group(1)) < 120:
                title = first_sentence_match.group(1).strip()
            else:
                title = clean[:80].strip() + "..."
                
            photos.append({
                "title": title, "summary": clean, "age_hours": age,
                "media_type": "photo", "media_url": p_url,
                "link": f"https://t.me/{pid}", "text_hash": th, "channel": channel_name
            })
    except Exception as e:
        print(f"❌ КРИТИЧЕСКАЯ ОШИБКА фото {channel_name}: {e}")
        traceback.print_exc()
    return photos

def get_novokuznetsk_rss_candidates(now):
    posted_hashes = get_posted_nk_hashes()
    posted_photos = get_posted_nk_photos()
    posted_videos = get_posted_nk_videos()
    candidates = []
    print("\n--- Диагностика RSS Новокузнецка ---")
    for feed_url in NK_RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            if not feed.entries:
                print(f"  [{feed_url[:40]}...] пусто")
                continue
            entries_count = len(feed.entries)
            city_matches = 0
            drop_no_media = 0
            drop_old = 0
            drop_ad = 0
            drop_short = 0
            drop_dup = 0
            candidates_found = 0
            for entry in feed.entries:
                title = entry.get('title', '')
                summary = entry.get('summary', '') or entry.get('description', '')
                full_text = f"{title} {summary}"
                if not any(k in full_text.lower() for k in NK_KEYWORDS): continue
                city_matches += 1
                pub_date = now
                if 'published_parsed' in entry: pub_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                elif 'updated_parsed' in entry: pub_date = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
                age_hours = (now - pub_date).total_seconds() / 3600
                if age_hours > 24:
                    drop_old += 1
                    continue
                
                media_url = None
                media_type = None
                link = entry.get('link', '')

                if 'media_content' in entry:
                    for m in entry.media_content:
                        if m.get('type', '').startswith('video'): media_url = normalize_url(m.get('url'), link); media_type = 'video'; break
                if not media_url and 'links' in entry:
                    for l in entry.links:
                        if l.get('rel') == 'enclosure' and l.get('type', '').startswith('video'): media_url = normalize_url(l.get('href'), link); media_type = 'video'; break
                
                if not media_url:
                    for m in entry.get('media_content', []):
                        if m.get('type', '').startswith('image'):
                            u = normalize_url(m.get('url'), link)
                            if u and not is_bad_image_url(u): media_url = u; media_type = 'photo'; break
                    if not media_url:
                        for m in entry.get('media_thumbnail', []):
                            u = normalize_url(m.get('url'), link)
                            if u and not is_bad_image_url(u): media_url = u; media_type = 'photo'; break
                    if not media_url and 'links' in entry:
                        for l in entry.links:
                            if l.get('rel') == 'enclosure' and l.get('type', '').startswith('image'):
                                u = normalize_url(l.get('href'), link)
                                if u and not is_bad_image_url(u): media_url = u; media_type = 'photo'; break
                
                if not media_url and summary:
                    soup = BeautifulSoup(summary, 'html.parser')
                    for img in soup.find_all('img'):
                        src = img.get('src', '')
                        parent_a = img.find_parent('a')
                        href = parent_a.get('href', '') if parent_a else ''
                        u = normalize_url(src, link)
                        if u and not is_bad_image_url(u) and not is_bad_image_url(href):
                            media_url = u
                            media_type = 'photo'
                            break
                
                if not media_url and link:
                    fetched_img = extract_image_from_url(link)
                    if fetched_img:
                        media_url = fetched_img
                        media_type = 'photo'

                if not media_url:
                    drop_no_media += 1
                    continue

                if media_type == 'video' and media_url in posted_videos:
                    drop_dup += 1
                    continue
                if media_type == 'photo' and media_url in posted_photos:
                    drop_dup += 1
                    continue
                clean_text = BeautifulSoup(summary, 'html.parser').get_text(separator='\n', strip=True)
                if len(clean_text) < 20:
                    drop_short += 1
                    continue
                th = get_text_hash(clean_text)
                if is_duplicate_text(clean_text, posted_hashes):
                    drop_dup += 1
                    continue
                if is_ad(clean_text):
                    drop_ad += 1
                    continue
                candidates.append({
                    'title': title, 'summary': clean_text, 'age_hours': age_hours,
                    'media_type': media_type, 'media_url': media_url,
                    'link': link, 'text_hash': th, 'channel': 'rss',
                    'priority': get_nk_priority(full_text),
                    'source_priority': 1 if "novokuznetsk-news" in feed_url else 0
                })
                candidates_found += 1
            print(f"  [{feed_url[:40]}...] Всего: {entries_count} | Города: {city_matches} | Без медиа: {drop_no_media} | Старые: {drop_old} | Реклама: {drop_ad} | Короткие: {drop_short} | Дубли: {drop_dup} | Подошло: {candidates_found}")
        except Exception as e:
            print(f"❌ ОШИБКА RSS {feed_url}: {e}")
            traceback.print_exc()
    return candidates

def process_video(video_bytes, is_nk=False):
    if video_bytes.startswith(b'<!DOCTYPE html>') or b'<html' in video_bytes[:1000]: return None, None
    if is_nk:
        logo_input = None
        fc = 'fps=30,scale=ceil(iw/2)*2:ceil(ih/2)*2,format=yuv420p'
    else:
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
        cmd.extend(['-filter_complex', fc, '-c:v', 'libx264', '-profile:v', 'baseline', '-level', '3.0', '-crf', '23', '-preset', 'ultrafast', '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', tout])
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
        if res.returncode != 0: return None, None
        subprocess.run(['ffmpeg', '-y', '-ss', '00:00:01.000', '-i', tout, '-vf', 'scale=320:-1', '-vfps', '1', '-q:v', '2', tthumb], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        out_bytes = None; thumb_bytes = None
        if os.path.exists(tout):
            with open(tout, 'rb') as f: out_bytes = f.read()
        if os.path.exists(tthumb):
            with open(tthumb, 'rb') as f: thumb_bytes = f.read()
        return out_bytes, thumb_bytes
    except Exception as e:
        print(f"❌ ОШИБКА FFMPEG: {e}")
        traceback.print_exc()
        return None, None
    finally:
        for p in [tin_path, tout, tthumb]:
            if 'p' in locals() and os.path.exists(p): os.remove(p)

def send_video_tg(video_url, caption, chat_id, is_nk=False):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"
    direct_url = extract_direct_video_url(video_url)
    if not direct_url: return False
    try:
        resp = requests.get(direct_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=60, verify=False)
        ctype = resp.headers.get('Content-Type', '')
        video_data = resp.content
        if len(video_data) == 0 or 'video/' not in ctype or len(video_data) > 50 * 1024 * 1024: return False
        video_data, thumb_data = process_video(video_data, is_nk)
        if video_data is None: return False
        video_hash = hashlib.md5(video_data).hexdigest()
        files = {'video': ('video.mp4', video_data, 'video/mp4')}
        data = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML", "supports_streaming": True}
        if thumb_data: files['thumbnail'] = ('thumb.jpg', thumb_data, 'image/jpeg')
        r = requests.post(url, data=data, files=files, timeout=90)
        if r.status_code == 200:
            if is_nk: save_posted_nk_video(video_url)
            else: save_posted_video(video_hash)
            return True
    except Exception as e:
        print(f"❌ ОШИБКА ОТПРАВКИ ВИДЕО TG: {e}")
        traceback.print_exc()
    return False

def send_photo_tg(photo_url, caption, chat_id, title="", is_nk=False):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    try:
        resp = requests.get(photo_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=30, verify=False)
        ctype = resp.headers.get('Content-Type', '')
        if 'image' not in ctype: return False
        photo_data = resp.content
        if len(photo_data) == 0 or len(photo_data) > 10 * 1024 * 1024: return False
        if is_text_image(photo_data, title): return False
        files = {'photo': ('photo.jpg', photo_data, 'image/jpeg')}
        data = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}
        r = requests.post(url, data=data, files=files, timeout=60)
        if r.status_code == 200:
            if is_nk: save_posted_nk_photo(photo_url)
            else: save_posted_photo(photo_url)
            return True
    except Exception as e:
        print(f"❌ ОШИБКА ОТПРАВКИ ФОТО TG: {e}")
        traceback.print_exc()
    return False

def send_to_telegram(text, media_type, media_url, channel_id=None, signature=None, title="", is_nk=False):
    if channel_id is None: channel_id = TELEGRAM_CHANNEL_ID
    if signature is None: signature = SIGNATURE_TG
    full_text = f"{text}\n\n{signature}"
    
    if media_type == 'video' and media_url:
        return send_video_tg(media_url, full_text, channel_id, is_nk)
    elif media_type == 'photo' and media_url:
        return send_photo_tg(media_url, full_text, channel_id, title, is_nk)
    return False

def send_to_max(text, media_type, media_url, channel_id=None, signature=None, title="", is_nk=False):
    if channel_id is None: channel_id = MAX_CHANNEL_ID
    if signature is None: signature = SIGNATURE_MAX
    if not MAX_BOT_TOKEN or not channel_id or media_type not in ('video', 'photo') or not media_url: return False
    
    clean_text = text.replace('<b>', '**').replace('</b>', '**')
    clean_text = f"{html.unescape(clean_text).strip()}\n\n{signature}"
    headers = {"Authorization": MAX_BOT_TOKEN, "Content-Type": "application/json"}
    attachments = []
    
    try:
        if media_type == 'video':
            direct_url = extract_direct_video_url(media_url)
            if not direct_url: return False
            vr = requests.get(direct_url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://t.me/'}, timeout=60, allow_redirects=True, verify=False)
            if len(vr.content) < 100 * 1024 or 'video/' not in vr.headers.get('Content-Type', '') or len(vr.content) > 250 * 1024 * 1024: return False
            vdata, _ = process_video(vr.content, is_nk)
            if vdata is None: return False
            up = requests.post("https://platform-api2.max.ru/uploads?type=video", headers={"Authorization": MAX_BOT_TOKEN}, timeout=15, verify=False)
            ud = up.json()
            if not (ud.get("url") and ud.get("token")): return False
            ur = requests.post(ud["url"], headers={"Authorization": MAX_BOT_TOKEN}, files={'data': ('video.mp4', vdata, 'video/mp4')}, timeout=180)
            if ur.status_code in [200, 201]:
                time.sleep(10)
                attachments.append({"type": "video", "payload": {"token": ud["token"]}})
            else: return False
        elif media_type == 'photo':
            pr = requests.get(media_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=60, allow_redirects=True, verify=False)
            if 'image' not in pr.headers.get('Content-Type', '') or len(pr.content) > 10 * 1024 * 1024: return False
            if is_text_image(pr.content, title): return False
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
        print(f"❌ ОШИБКА ПОДГОТОВКИ МЕДИА MAX: {e}")
        return False

    if not attachments: return False
    payload = {"text": clean_text, "format": "markdown", "attachments": attachments}
    for attempt in range(3):
        try:
            r = requests.post(f"https://platform-api2.max.ru/messages?chat_id={channel_id}", headers=headers, json=payload, timeout=20, verify=False)
            if r.status_code == 200: return True
            elif r.status_code == 400:
                err = r.json()
                if err.get("code") == "attachment.not.ready" and attempt < 2: time.sleep((attempt + 1) * 10); continue
                return False
        except Exception as e:
            if attempt == 2: return False
            time.sleep(10)
    return False

def call_groq(prompt):
    if not GROQ_API_KEY: return ""
    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                          headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                          json={"model": "openai/gpt-oss-120b", "messages": [{"role": "user", "content": prompt}]}, timeout=15)
        r.raise_for_status()
        return r.json()['choices'][0]['message']['content'].strip()
    except Exception as e:
        print(f"⚠️ Ошибка Groq: {e}")
        return ""

# УЛУЧШЕННАЯ ФУНКЦИЯ: Убирает дублирование заголовка и текста
def make_hybrid_post(title, summary):
    # 1. Чистим заголовок
    clean_title = html.unescape(title or "").strip()
    clean_title = re.sub(r'<[^>]+>', '', clean_title)
    clean_title = re.sub(r'https?://\S+', '', clean_title)
    clean_title = re.sub(r'@\w+', '', clean_title)
    clean_title = re.sub(r'\s+', ' ', clean_title).strip()
    
    if len(clean_title) > 100:
        clean_title = clean_title[:100] + "..."
        
    if not clean_title:
        clean_title = "Новость"

    # 2. Чистим текст новости
    clean_summary = html.unescape(summary or "").strip()
    clean_summary = re.sub(r'<[^>]+>', ' ', clean_summary)
    clean_summary = re.sub(r'https?://\S+', '', clean_summary)
    clean_summary = re.sub(r'@\w+', '', clean_summary)
    clean_summary = re.sub(r'\s+', ' ', clean_summary).strip()

    # 3. Убираем заголовок из начала текста, чтобы не было дубля
    if clean_title in clean_summary:
        clean_summary = clean_summary.replace(clean_title, "", 1).strip()

    if not clean_summary or len(clean_summary) < 10:
        return f"<b>{clean_title}</b>"

    # 4. Отдаем в ИИ (только текст, заголовок запрещен)
    prompt = f"""Ты — редактор. Сделай краткую сводку текста ниже.
1. Сохрани все факты, имена, цифры.
2. Убери "воду", ссылки, рекламу.
3. Максимальная длина: 400-500 символов.
4. Если текст уже короткий, просто верни его как есть.
5. НЕ пиши заголовок. Только текст.
6. Запрещены эмодзи.
ТЕКСТ:
{clean_summary}"""
    
    ai_text = call_groq(prompt)
    if not ai_text:
        ai_text = clean_summary
        if len(ai_text) > 800:
            ai_text = ai_text[:800] + "..."
            
    ai_text = html.escape(ai_text.strip())
    return f"<b>{clean_title}</b>\n\n{ai_text}"

def process_novokuznetsk(tg_videos, tg_photos):
    if not TG_NK_CHANNEL_ID and not MAX_NK_CHANNEL_ID: return
    now = datetime.now(timezone.utc)
    nk_candidates = []
    posted_nk_videos = get_posted_nk_videos()
    posted_nk_photos = get_posted_nk_photos()
    posted_nk_hashes = get_posted_nk_hashes()
    recent_nk_titles = get_recent_nk_titles()
    for v in tg_videos:
        if any(k in v['summary'].lower() for k in NK_KEYWORDS):
            if v['media_url'] in posted_nk_videos: continue
            if is_duplicate_text(v['summary'], posted_nk_hashes): continue
            if is_duplicate_title(v['title'], recent_nk_titles): continue
            v['priority'] = get_nk_priority(v['summary'])
            v['source_priority'] = 0
            nk_candidates.append(v)
    for p in tg_photos:
        if any(k in p['summary'].lower() for k in NK_KEYWORDS):
            if p['media_url'] in posted_nk_photos: continue
            if is_duplicate_text(p['summary'], posted_nk_hashes): continue
            if is_duplicate_title(p['title'], recent_nk_titles): continue
            p['priority'] = get_nk_priority(p['summary'])
            p['source_priority'] = 0
            nk_candidates.append(p)
    nk_candidates.extend(get_novokuznetsk_rss_candidates(now))
    if not nk_candidates:
        print("\nНовокузнецк: после фильтрации ничего не осталось.")
        return
    nk_candidates.sort(key=lambda x: (0 if x['media_type'] == 'video' else 1, x['priority'], x['source_priority'], x['age_hours']))
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
    print("\n=== Сбор данных из Telegram ===")
    all_videos = []
    all_photos = []
    for ch in TG_CHANNELS:
        all_videos.extend(get_tg_web_videos(ch, now))
        all_photos.extend(get_tg_web_photos(ch, now))
    print(f"Собрано (сырых): {len(all_videos)} видео, {len(all_photos)} фото.")

    process_novokuznetsk(all_videos, all_photos)

    print("\n=== Основной канал ===")
    main_candidates = all_videos + all_photos
    main_candidates.sort(key=lambda x: (0 if x['media_type'] == 'video' else 1, x['age_hours']))

    posted_hashes = get_posted_hashes()
    posted_photos_urls = get_posted_photos()
    recent_titles = get_recent_titles()

    seen = set()
    unique_main = []
    for c in main_candidates:
        if c['text_hash'] in seen: continue
        if c['media_type'] == 'photo' and c['media_url'] in posted_photos_urls: continue
        if is_duplicate_text(c['summary'], posted_hashes): continue
        if is_duplicate_title(c['title'], recent_titles): continue
        seen.add(c['text_hash'])
        unique_main.append(c)

    final_candidates = unique_main

    if final_candidates:
        print(f"🔥 Найдено {len(final_candidates)} кандидатов для основного канала.")
        for c in final_candidates[:5]:
            print(f"\nКандидат: {c['title']} ({c['media_type']})")
            
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
