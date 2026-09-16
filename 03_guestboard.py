import asyncio
import hashlib
import html
import json
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

app = FastAPI()

DATA_FILE = Path(__file__).parent / "guestboard.json"
MAX_NAME_LEN = 20
MAX_MESSAGE_LEN = 500
entries_lock = asyncio.Lock()


def load_entries() -> list[dict]:
    if not DATA_FILE.exists():
        return []
    with DATA_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_entries(entries: list[dict]) -> None:
    with DATA_FILE.open("w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


BASE_CSS = """
        :root {
            --black: #1c1c1c;
            --charcoal: #2c2c2c;
            --line: #d8d5cf;
            --ink: #262422;
            --paper: #f7f5f1;
            --muted: #8c8880;
            --accent: #55534e;
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            min-height: 100vh;
            background: radial-gradient(circle at 50% -10%, #3a3a3a 0%, #161616 60%);
            font-family: 'Noto Serif KR', serif;
            color: var(--ink);
            padding: 48px 16px 80px;
            display: flex;
            justify-content: center;
        }
        .scroll {
            width: 620px;
            max-width: 100%;
        }
        .banner {
            background: linear-gradient(160deg, var(--charcoal), var(--black));
            border-radius: 16px 16px 0 0;
            padding: 34px 20px 24px;
            text-align: center;
            position: relative;
            border: 1px solid #444;
            border-bottom: none;
        }
        .ribbon-line {
            height: 2px;
            background: linear-gradient(90deg, transparent, #6b6b6b, transparent);
            opacity: 0.7;
        }
        .candle-icon { font-size: 26px; margin: 8px 0 4px; opacity: 0.9; }
        .brush-title {
            font-family: 'Noto Serif KR', serif;
            font-weight: 700;
            font-size: 32px;
            color: #f2f0ea;
            margin: 6px 0 6px;
            letter-spacing: 2px;
        }
        .subtitle {
            color: #b8b5ae;
            letter-spacing: 2px;
            font-size: 13px;
            opacity: 0.9;
            margin-bottom: 4px;
        }
        .condolence-phrase {
            color: #8f8c85;
            font-size: 12px;
            letter-spacing: 3px;
            margin-top: 6px;
        }
        .panel {
            background: var(--paper);
            border: 1px solid #444;
            border-top: none;
            border-radius: 0 0 16px 16px;
            padding: 28px 26px 34px;
            box-shadow: 0 30px 60px -24px rgba(0,0,0,0.6);
        }
        .error-msg {
            background: rgba(0,0,0,0.05);
            border: 1px solid rgba(0,0,0,0.25);
            color: var(--accent);
            padding: 10px 14px;
            border-radius: 8px;
            font-size: 13px;
            margin-bottom: 18px;
            text-align: center;
        }
        .write-form {
            background: #ffffff;
            border: 1px solid var(--line);
            border-radius: 12px;
            padding: 18px;
            margin-bottom: 28px;
        }
        .write-form .row { display: flex; gap: 10px; margin-bottom: 10px; }
        .write-form input, .write-form textarea {
            font-family: 'Noto Serif KR', serif;
            background: #fff;
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 10px 12px;
            font-size: 14px;
            color: var(--ink);
            outline: none;
        }
        .write-form input:focus, .write-form textarea:focus {
            border-color: var(--accent);
            box-shadow: 0 0 0 3px rgba(0,0,0,0.08);
        }
        .write-form input[name="name"] { flex: 1; min-width: 0; }
        .write-form input[name="password"] { flex: 1; min-width: 0; }
        .write-form textarea {
            width: 100%;
            min-height: 90px;
            resize: vertical;
            margin-bottom: 12px;
        }
        .write-form button, .delete-form button {
            background: linear-gradient(135deg, var(--charcoal), var(--black));
            border: none;
            color: #f2f0ea;
            font-weight: 700;
            font-family: 'Noto Serif KR', serif;
            padding: 10px 22px;
            border-radius: 8px;
            cursor: pointer;
            letter-spacing: 1px;
        }
        .write-form button:hover, .delete-form button:hover { filter: brightness(1.2); }
        .count-line {
            text-align: center;
            color: var(--muted);
            font-size: 12px;
            letter-spacing: 2px;
            margin-bottom: 18px;
        }
        .entries { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 16px; }
        .entry {
            background: #ffffff;
            border: 1px solid var(--line);
            border-left: 4px solid var(--charcoal);
            border-radius: 4px 10px 10px 4px;
            padding: 16px 18px;
            position: relative;
        }
        .entry-header {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 8px;
        }
        .seal {
            width: 26px;
            height: 26px;
            border-radius: 50%;
            background: var(--paper);
            border: 1px solid var(--line);
            color: var(--accent);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 13px;
            flex-shrink: 0;
        }
        .entry-name { font-weight: 700; color: var(--ink); font-size: 15px; }
        .entry-date { margin-left: auto; color: var(--muted); font-size: 11px; }
        .entry-message {
            white-space: pre-wrap;
            word-break: break-word;
            line-height: 1.6;
            font-size: 14px;
            color: var(--ink);
            margin-bottom: 10px;
        }
        .delete-form { display: flex; gap: 8px; justify-content: flex-end; }
        .delete-form input {
            font-family: 'Noto Serif KR', serif;
            background: #fff;
            border: 1px solid var(--line);
            border-radius: 6px;
            padding: 6px 10px;
            font-size: 12px;
            width: 130px;
        }
        .delete-form button { padding: 6px 14px; font-size: 12px; }
        .empty-state {
            text-align: center;
            color: var(--muted);
            padding: 30px 0;
            font-size: 14px;
        }
"""

PAGE_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>추모합니다 · 故 김영균 차장님</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@400;600;700&display=swap" rel="stylesheet">
    <style>__BASE_CSS__</style>
</head>
<body>
    <div class="scroll">
        <div class="banner">
            <div class="ribbon-line"></div>
            <div class="candle-icon">🕯️</div>
            <div class="brush-title">추모합니다</div>
            <div class="subtitle">KT 로밍서비스팀 · 故 김영균 차장님</div>
            <div class="condolence-phrase">삼가 고인의 명복을 빕니다</div>
            <div class="ribbon-line"></div>
        </div>
        <div class="panel">
            __ERROR__
            <form method="post" action="/add" class="write-form">
                <div class="row">
                    <input type="text" name="name" placeholder="이름" maxlength="__MAX_NAME__" required>
                    <input type="password" name="password" placeholder="비밀번호 (삭제 시 필요)" maxlength="20" required>
                </div>
                <textarea name="message" placeholder="故人을 追慕하며 마음을 담아 글을 남겨주세요" maxlength="__MAX_MESSAGE__" required></textarea>
                <div style="text-align:right">
                    <button type="submit">추모글 남기기</button>
                </div>
            </form>

            <div class="count-line">지금까지 __COUNT__개의 추모글이 모였습니다</div>

            __ENTRIES__
        </div>
    </div>
</body>
</html>
"""

ENTRY_TEMPLATE = """
    <li class="entry">
        <div class="entry-header">
            <span class="seal">🕯️</span>
            <span class="entry-name">__NAME__</span>
            <span class="entry-date">__DATE__</span>
        </div>
        <div class="entry-message">__MESSAGE__</div>
        <form method="post" action="/delete/__ID__" class="delete-form">
            <input type="password" name="password" placeholder="비밀번호" maxlength="20" required>
            <button type="submit">삭제</button>
        </form>
    </li>
"""


def render_page(error: str | None = None) -> str:
    entries = load_entries()

    error_html = ""
    if error == "empty":
        error_html = '<div class="error-msg">이름, 비밀번호, 내용을 모두 입력해주세요.</div>'
    elif error == "wrongpw":
        error_html = '<div class="error-msg">비밀번호가 일치하지 않습니다.</div>'
    elif error == "notfound":
        error_html = '<div class="error-msg">존재하지 않는 글입니다.</div>'

    if entries:
        entries_html = '<ul class="entries">' + "".join(
            ENTRY_TEMPLATE.replace("__NAME__", html.escape(e["name"]))
            .replace("__DATE__", html.escape(e["created_at"]))
            .replace("__MESSAGE__", html.escape(e["message"]))
            .replace("__ID__", e["id"])
            for e in reversed(entries)
        ) + "</ul>"
    else:
        entries_html = '<div class="empty-state">아직 남겨진 추모의 글이 없습니다.<br>고인을 기리는 첫 마음을 남겨주세요.</div>'

    return (
        PAGE_TEMPLATE.replace("__BASE_CSS__", BASE_CSS)
        .replace("__ERROR__", error_html)
        .replace("__MAX_NAME__", str(MAX_NAME_LEN))
        .replace("__MAX_MESSAGE__", str(MAX_MESSAGE_LEN))
        .replace("__COUNT__", str(len(entries)))
        .replace("__ENTRIES__", entries_html)
    )


@app.get("/", response_class=HTMLResponse)
def index(error: str | None = None):
    return HTMLResponse(render_page(error))


@app.post("/add")
async def add_entry(
    request: Request,
    name: str = Form(...),
    password: str = Form(...),
    message: str = Form(...),
):
    name = name.strip()[:MAX_NAME_LEN]
    message = message.strip()[:MAX_MESSAGE_LEN]
    password = password.strip()

    if not name or not password or not message:
        return RedirectResponse(url="/?error=empty", status_code=303)

    entry = {
        "id": uuid.uuid4().hex,
        "name": name,
        "message": message,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "ip": get_client_ip(request),
        "password_hash": hash_password(password),
    }

    async with entries_lock:
        entries = load_entries()
        entries.append(entry)
        save_entries(entries)

    return RedirectResponse(url="/", status_code=303)


@app.post("/delete/{entry_id}")
async def delete_entry(entry_id: str, password: str = Form(...)):
    async with entries_lock:
        entries = load_entries()
        target = next((e for e in entries if e["id"] == entry_id), None)

        if target is None:
            return RedirectResponse(url="/?error=notfound", status_code=303)

        if target["password_hash"] != hash_password(password.strip()):
            return RedirectResponse(url="/?error=wrongpw", status_code=303)

        entries = [e for e in entries if e["id"] != entry_id]
        save_entries(entries)

    return RedirectResponse(url="/", status_code=303)
