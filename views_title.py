import json
import os
import sys
import time

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

VIDEO_ID = "wYnV_yGp_Mo"           # из ссылки youtube.com/watch?v=XXXX
TITLE_TEMPLATE = "this video has {views} views"
INTERVAL_SEC = 10 * 60              # раз в 10 минут (чаще — упрётесь в квоту API)
SCOPES = ["https://www.googleapis.com/auth/youtube"]

HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(HERE, "token.json")
SECRET_PATH = os.path.join(HERE, "client_secret.json")
LOG_PATH = os.path.join(HERE, "views_title.log")


def log(*parts):
    line = time.strftime("%Y-%m-%d %H:%M:%S") + " " + " ".join(str(p) for p in parts)
    print(line)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def get_youtube(interactive=True):
    # В облаке (GitHub Actions) токен приходит из секрета через переменную окружения YT_TOKEN
    env_token = os.environ.get("YT_TOKEN")
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


def update_once(yt):
    resp = yt.videos().list(part="snippet,statistics", id=VIDEO_ID).execute()
    if not resp.get("items"):
        raise RuntimeError(f"Видео {VIDEO_ID} не найдено")
    item = resp["items"][0]
    views = int(item["statistics"]["viewCount"])
    snippet = item["snippet"]
    new_title = TITLE_TEMPLATE.format(views=f"{views:,}")

    if snippet["title"] == new_title:
        log("Без изменений:", new_title)
        return

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


if __name__ == "__main__":
    # python views_title.py --once  -> одно обновление и выход (для Планировщика заданий)
    if "--once" in sys.argv:
        try:
            update_once(get_youtube(interactive=False))
        except Exception as e:
            log("Ошибка:", repr(e))
            sys.exit(1)
        sys.exit(0)
    yt = get_youtube()
    while True:
        try:
            update_once(yt)
        except Exception as e:
            log("Ошибка:", repr(e))
        time.sleep(INTERVAL_SEC)
