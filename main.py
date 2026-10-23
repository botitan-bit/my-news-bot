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

# 👇 1. СПИСОК ПРИОРИТЕТНЫХ КАНАЛОВ (RSS)
PRIORITY_FEEDS = [
    "https://rss-bridge.org/bridge01/?action=display&bridge=TelegramBridge&username=pilachzx&format=Atom", # 👈 Новый канал
    "https://rss-bridge.org/bridge01/?action=display&bridge=TelegramBridge&username=slavaded1337&format=Atom",
    "https://rss-bridge.org/bridge01/?action=display&bridge=TelegramBridge&username=novosti_efir&format=Atom",
    "https://rss-bridge.org/bridge01/?action=display&bridge=TelegramBridge&username=botcharov&format=Atom",
    "https://rss-bridge.org/bridge01/?action=display&bridge=TelegramBridge&username=mnogonazi&format=Atom",
    "https://rss-bridge.org/bridge01/?action=display&bridge=TelegramBridge&username=SHOCKkzn&format=Atom",
]

# 👇 2. ОБЩИЙ СПИСОК ИСТОЧНИКОВ
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

BLACKLIST_WORDS = [
    "какой сегодня", "какой праздник", "гороскоп", "день рождения", "история дня", 
    "в этот день", "народные приметы", "церковный календарь", "лунный календарь", "именины",
    "заседание", "законопроект", "бюджет", "форум", "выставка", "конференция", "экономика", "инфляция", "курс валют",
    "спорт", "гонщик", "гонка", "автоспорт", "футбол", "хоккей", "олимпиад", "чемпионат", "турнир", "матч", "клуб", "тренер",
    "шоу-бизнес", "актер", "актриса", "певец", "певица", "звезда", "сериал", "фильм", "премьера", "инстаграм", "тикток",
    "спектакль", "ледовый", "фигурист", "авербух", "петросян", "концерт", "развлечение", "шоу", "праздник", "фестиваль", "выступление",
    "продолжают спецоперацию", "выполняют задачи", "боевая готовность", "полная готовность", "активные действия", "выполняют боевые задачи", "решают задачи", "контроль над ситуацией",
    "автобус", "маршрутка"
]

def get_posted_links():
    if os.path.exists("posted_news.txt"):
        with open("posted_news.txt", "r", encoding="utf-8") as f:
            return f.read().splitlines()
    return []

def save_posted_link(link):
    with open("posted_news.txt", "a", encoding="utf-8") as f:
        f.write(link + "\n")

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

def get_tg_web_videos(channel_name, theme, now):
    videos = []
    url = f"https://t.me/s/{channel_name}"
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        resp = requests.get(url, timeout=10, headers=headers)
        if resp.status_code != 200:
            return []
        
        html_content = resp.text
        posts = re.split(r'<div class="tgme_widget_message_wrap', html_content)
        
        for post in posts[1:]:
            video_match = re.search(r'<video[^>]+src="([^"]+)"', post)
            if not video_match:
                continue
                
            video_url = video_match.group(1)
            
            text_match = re.search(r'<div class="tgme_widget_message_text[^>]*>(.*?)</div>', post, re.DOTALL)
            link_match = re.search(r'data-post="([^"]+)"', post)
            
            if not text_match or not link_match:
                continue
                
            raw_text = text_match.group(1)
            clean_text = re.sub(r'<[^>]+>', ' ', raw_text)
            clean_text = html.unescape(clean_text).strip()
            
            if len(clean_text) < 20:
                continue
                
            post_link = f"https://t.me/{link_match.group(1)}"
            
            if is_blacklisted(clean_text): continue
            
            full_text = clean_text
            if not is_russia_related(full_text): continue
            
            if is_theme_match(full_text, theme):
                videos.append({
                    "title": clean_text[:60] + "...",
                    "summary": clean_text,
                    "age_hours": 1.0, 
                    "media_type": "video",
                    "media_url": video_url,
                    "link": post_link,
                    "theme_match": True,
                    "russia_match": True,
                    "has_media": True
                })
    except Exception as e:
        pass
    return videos

def process_feeds(feed_list, theme, posted_links, posted_images, now):
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
    now = datetime.now(timezone.utc)
    
    print(f"  -> Ищем видео в веб-версиях Telegram-каналов...")
    tg_videos = []
    # 👇 Добавили pilachzx на первое место!
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
    priority_entries = process_feeds(PRIORITY_FEEDS, theme, posted_links, posted_images, now)
    general_entries = process_feeds(RSS_FEEDS, theme, posted_links, posted_images, now)
    
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
    titles_list = "\n".join([f"{i}. {c['title']}" for i, c in enumerate(candidates)])
    
    recent_titles = get_recent_titles()
    history_text = ""
    if recent_titles:
        history_text = "УЖЕ ОПУБЛИКОВАНО РАНЕЕ:\n" + "\n".join(recent_titles) + "\n"
    
    prompt = f"""Ты — редактор жесткого новостного канала. Выбери ОДИН самый интересный, конкретный или трагичный заголовок из списка.
КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО выбирать новости про шоу-бизнес, актеров, фигуристов, спектакли, концерты, спорт или развлечения.
ИГНОРИРУЙ обычные бытовые аварии (например, столкновение автобуса и грузовика с пострадавшими).
Выбери самое достойное из того, что есть (СВО, криминал, крупные ЧП).

{history_text}

Если ВСЕ новости в списке — это шоу-бизнес, спорт или пустые сводки, ответь NONE.
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
КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНЫ любые английские слова.
Если в исходном тексте ТОЛЬКО общие фразы, напиши слово NONE.

Формат ответа:
1. Заголовок в теге <b>...</b>. Сделай его громким и понятным.
2. ДВА переноса строки.
3. 1-2 эмодзи и краткий текст с фактами (строго на русском).

Исходный заголовок: {title}
Исходный текст: {summary}
"""
    raw_text = call_groq(prompt)
    
    if not raw_text or "NONE" in raw_text.upper():
        print("⚠️ ИИ отклонил новость.")
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
    
    url = f"https://platform-api2.max.ru/messages?chat_id={MAX_CHANNEL_ID}"
    headers = {"Authorization": MAX_BOT_TOKEN, "Content-Type": "application/json"}
    
    attachments = []
    if media_type == 'image' and media_url:
        attachments.append({"type": "image", "payload": {"url": media_url}})
    
    payload = {"text": clean_text, "format": "markdown"}
    if attachments: payload["attachments"] = attachments

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10, verify=False)
        response.raise_for_status()
        print("✅ MAX: Успешно опубликовано!")
        return True
    except Exception as e:
        print(f"❌ MAX Ошибка: {e}")
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
                    
                    if best_news.get('media_url'):
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
