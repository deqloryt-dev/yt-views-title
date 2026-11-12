import glob
import json
import os
import sys
import time

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

VIDEO_ID = "wYnV_yGp_Mo"           # из ссылки youtube.com/watch?v=XXXX
TITLE_TEMPLATE = "this video has {views} views"
# Строки превью; {views} заменяется на число просмотров
THUMB_LINES = ["this video has", "{views}", "views"]
INTERVAL_SEC = 10 * 60              # раз в 10 минут (чаще — упрётесь в квоту API)
SCOPES = ["https://www.googleapis.com/auth/youtube"]

HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(HERE, "token.json")
SECRET_PATH = os.path.join(HERE, "client_secret.json")
LOG_PATH = os.path.join(HERE, "views_title.log")
THUMB_PATH = os.path.join(HERE, "thumbnail.png")


def log(*parts):
    line = time.strftime("%Y-%m-%d %H:%M:%S") + " " + " ".join(str(p) for p in parts)
    print(line)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def get_youtube(interactive=True):
    # В облаке (GitHub Actions) токен приходит из секрета через переменную окружения YT_TOKEN
    env_token = os.environ.get("YT_TOKEN", "").lstrip("\ufeff").strip()
    if env_token:
        creds = Credentials.from_authorized_user_info(json.loads(env_token), SCOPES)
        if not creds.valid:
            creds.refresh(Request())
        return build("youtube", "v3", credentials=creds)

    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None
        if not creds or not creds.valid:
            if not interactive:
                raise RuntimeError("Нужно войти заново: запустите python views_title.py вручную")
            flow = InstalledAppFlow.from_client_secrets_file(SECRET_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
    return build("youtube", "v3", credentials=creds)


def get_video(yt):
    resp = yt.videos().list(part="snippet,statistics", id=VIDEO_ID).execute()
    if not resp.get("items"):
        raise RuntimeError(f"Видео {VIDEO_ID} не найдено")
    item = resp["items"][0]
    return int(item["statistics"]["viewCount"]), item["snippet"]


def update_title(yt, views, snippet):
    new_title = TITLE_TEMPLATE.format(views=f"{views:,}")
    if snippet["title"] == new_title:
        log("Без изменений:", new_title)
        return False

    # В update нужно передать snippet целиком, иначе описание и теги сотрутся
    new_snippet = {
        "title": new_title,
        "categoryId": snippet["categoryId"],
        "description": snippet.get("description", ""),
        "tags": snippet.get("tags", []),
    }
    if snippet.get("defaultLanguage"):
        new_snippet["defaultLanguage"] = snippet["defaultLanguage"]

    yt.videos().update(part="snippet", body={"id": VIDEO_ID, "snippet": new_snippet}).execute()
    log("Обновлено:", new_title)
    return True


def find_font():
    # IBM Plex Sans как на исходном превью; в облаке ставится пакетом fonts-ibm-plex
    patterns = [
        "/usr/share/fonts/**/IBMPlexSans-Regular.*",
        os.path.join(HERE, "fonts", "*.[ot]tf"),
        "/usr/share/fonts/**/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for p in patterns:
        found = glob.glob(p, recursive=True)
        if found:
            return found[0]
    raise RuntimeError("Не найден шрифт для превью")


def render_thumbnail(views, path=THUMB_PATH):
    from PIL import Image, ImageDraw, ImageFont

    W, H, MARGIN = 1280, 720, 40
    lines = [s.format(views=f"{views:,}") for s in THUMB_LINES]
    font_path = find_font()

    # Все строки одного размера, как на исходном превью; уменьшаем, если длинное число не влезает
    size = 175
    while size > 40:
        font = ImageFont.truetype(font_path, size)
        if max(font.getlength(s) for s in lines) <= W - 2 * MARGIN:
            break
        size -= 5

    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)
    step = size * 1.45
    top = H / 2 - step * (len(lines) - 1) / 2
    for i, s in enumerate(lines):
        draw.text((W / 2, top + i * step), s, font=font, fill="black", anchor="mm")
    img.save(path, optimize=True)
    return path, os.path.basename(font_path)


def update_thumbnail(yt, views):
    path, font_name = render_thumbnail(views)
    yt.thumbnails().set(videoId=VIDEO_ID, media_body=MediaFileUpload(path, mimetype="image/png")).execute()
    log(f"Превью обновлено: {views:,} views (шрифт {font_name})")


if __name__ == "__main__":
    # python views_title.py --once              -> одно обновление заголовка и выход
    # python views_title.py --once --thumbnail  -> заголовок + превью (превью — только если число изменилось)
    # python views_title.py --once --thumbnail --force-thumbnail -> превью в любом случае
    # python views_title.py --render 1234       -> только нарисовать thumbnail.png для проверки
    if "--render" in sys.argv:
        n = int(sys.argv[sys.argv.index("--render") + 1])
        print(render_thumbnail(n))
        sys.exit(0)

    if "--once" in sys.argv:
        failed = False
        try:
            yt = get_youtube(interactive=False)
            views, snippet = get_video(yt)
        except Exception as e:
            log("Ошибка:", repr(e))
            sys.exit(1)
        changed = False
        try:
            changed = update_title(yt, views, snippet)
        except Exception as e:
            log("Ошибка заголовка:", repr(e))
            failed = True
        # Превью меняем вместе с заголовком: если число не изменилось, не тратим 50 единиц квоты
        if "--thumbnail" in sys.argv and (changed or "--force-thumbnail" in sys.argv):
            try:
                update_thumbnail(yt, views)
            except Exception as e:
                log("Ошибка превью:", repr(e))
                failed = True
        sys.exit(1 if failed else 0)

    yt = get_youtube()
    while True:
        try:
            views, snippet = get_video(yt)
            update_title(yt, views, snippet)
        except Exception as e:
            log("Ошибка:", repr(e))
        time.sleep(INTERVAL_SEC)
