import asyncio
import random
import uuid
from dataclasses import dataclass, field

from fastapi import Cookie, FastAPI, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse

app = FastAPI()

CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # 헷갈리는 문자(0,O,1,I) 제외
AI_NAME = "AI 오라클 (초급)"


@dataclass
class Player:
    id: str
    name: str
    ws: WebSocket | None = None
    attempts: int = 0
    low: int = 1
    high: int = 100
    history: list[dict] = field(default_factory=list)
    is_ai: bool = False


@dataclass
class Room:
    code: str
    answer: int
    players: dict[str, Player] = field(default_factory=dict)
    winner_id: str | None = None
    phase: str = "waiting"  # waiting -> playing -> over
    ai_started: bool = False


rooms: dict[str, Room] = {}


def generate_code() -> str:
    while True:
        code = "".join(random.choices(CODE_ALPHABET, k=4))
        if code not in rooms:
            return code


def is_connected(p: Player) -> bool:
    return p.is_ai or p.ws is not None


def reset_room(room: Room) -> None:
    room.answer = random.randint(1, 100)
    room.winner_id = None
    connected = sum(1 for p in room.players.values() if is_connected(p))
    room.phase = "playing" if connected == 2 else "waiting"
    for p in room.players.values():
        p.attempts = 0
        p.low, p.high = 1, 100
        p.history = []


def handle_guess(room: Room, player_id: str, value: int) -> None:
    if room.phase != "playing" or room.winner_id is not None:
        return
    if not isinstance(value, int) or not (1 <= value <= 100):
        return

    p = room.players[player_id]
    p.attempts += 1

    if value < room.answer:
        p.low = max(p.low, value + 1)
        p.history.append({"value": value, "dir": "up"})
    elif value > room.answer:
        p.high = min(p.high, value - 1)
        p.history.append({"value": value, "dir": "down"})
    else:
        p.history.append({"value": value, "dir": "win"})
        room.winner_id = player_id
        room.phase = "over"


def snapshot(room: Room, viewer_id: str) -> dict:
    players = list(room.players.values())
    self_p = room.players.get(viewer_id)
    opp_p = next((p for p in players if p.id != viewer_id), None)

    def pdata(p: Player | None):
        if p is None:
            return None
        return {
            "name": p.name,
            "attempts": p.attempts,
            "low": p.low,
            "high": p.high,
            "history": p.history[-8:],
        }

    winner = None
    if room.winner_id:
        winner = "self" if room.winner_id == viewer_id else "opp"

    return {
        "type": "state",
        "code": room.code,
        "phase": room.phase,
        "self": pdata(self_p),
        "opp": pdata(opp_p),
        "winner": winner,
        "answer": room.answer if room.phase == "over" else None,
    }


async def broadcast(room: Room) -> None:
    for p in list(room.players.values()):
        if p.ws is not None:
            try:
                await p.ws.send_json(snapshot(room, p.id))
            except Exception:
                p.ws = None


async def ai_loop(room: Room, ai_id: str) -> None:
    while True:
        await asyncio.sleep(random.uniform(1.1, 2.4))
        if room.code not in rooms or room.phase != "playing":
            continue
        ai = room.players.get(ai_id)
        if ai is None:
            return
        # 실력이 낮은 AI: 절반 정도의 확률로만 힌트(범위)를 제대로 활용한다.
        if random.random() < 0.55:
            guess = random.randint(ai.low, ai.high)
        else:
            guess = random.randint(1, 100)
        handle_guess(room, ai_id, guess)
        await broadcast(room)


BASE_CSS = """
        :root {
            --gold: #c9971e;
            --gold-deep: #9c6f0a;
            --gold-bright: #eab63e;
            --ink: #262220;
            --panel: #ffffff;
            --panel-light: #fffaf1;
            --text: #2b2620;
            --muted: #93876f;
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            background: radial-gradient(circle at 50% 0%, #fff8ec 0%, #f3e9d8 60%);
            font-family: 'Poppins', sans-serif;
            color: var(--text);
            padding: 40px 16px;
        }
        .card {
            position: relative;
            width: 420px;
            max-width: 100%;
            padding: 44px 36px 36px;
            background: linear-gradient(160deg, var(--panel), var(--panel-light));
            border-radius: 22px;
            border: 1px solid rgba(201, 151, 30, 0.28);
            box-shadow: 0 30px 60px -24px rgba(120, 90, 20, 0.28), 0 0 0 1px rgba(0,0,0,0.02) inset;
        }
        .eyebrow { text-align: center; letter-spacing: 3px; font-size: 11px; color: var(--gold-deep); text-transform: uppercase; margin-bottom: 6px; font-weight: 600; }
        h1 {
            font-family: 'Playfair Display', serif;
            text-align: center;
            font-size: 28px;
            margin: 0 0 4px;
            background: linear-gradient(120deg, var(--gold-deep), var(--gold) 60%, #7a5810);
            -webkit-background-clip: text;
            background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .tagline { text-align: center; color: var(--muted); font-size: 13px; margin-bottom: 26px; }
        input[type=number], input[type=text] {
            background: #fffaf1; border: 1px solid rgba(201,151,30,0.35); color: var(--text);
            font-size: 15px; padding: 11px 12px; border-radius: 8px; outline: none; font-family: 'Poppins', sans-serif;
        }
        input[type=number]:focus, input[type=text]:focus {
            border-color: var(--gold); box-shadow: 0 0 0 3px rgba(201,151,30,0.15);
        }
        button {
            background: linear-gradient(135deg, var(--gold-bright), var(--gold));
            border: none; color: #2b2005; font-weight: 600; font-size: 15px;
            padding: 12px 24px; border-radius: 10px; cursor: pointer; letter-spacing: 0.5px;
            transition: transform 0.15s ease, box-shadow 0.15s ease;
        }
        button:hover { transform: translateY(-1px); box-shadow: 0 8px 18px -6px rgba(201,151,30,0.45); }
"""


def render_lobby(error: str | None = None) -> str:
    error_html = ""
    if error == "notfound":
        error_html = '<div class="error">존재하지 않는 방 코드입니다.</div>'
    elif error == "full":
        error_html = '<div class="error">이미 대결이 진행 중인 방입니다.</div>'

    return f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>NUMBER ORACLE · Battle</title>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&family=Poppins:wght@300;400;500;600&display=swap" rel="stylesheet">
        <style>{BASE_CSS}
            .mode-tabs {{ display: flex; gap: 8px; margin-bottom: 20px; background: #f3e9d8; padding: 4px; border-radius: 12px; }}
            .tab-btn {{ flex: 1; background: transparent; color: var(--muted); font-weight: 500; padding: 10px 8px; border-radius: 9px; box-shadow: none; }}
            .tab-btn:hover {{ transform: none; box-shadow: none; }}
            .tab-btn.active {{ background: linear-gradient(135deg, var(--gold-bright), var(--gold)); color: #2b2005; }}
            .forms {{ display: flex; flex-direction: column; gap: 22px; }}
            .panel {{ background: rgba(201,151,30,0.06); border: 1px solid rgba(201,151,30,0.18); border-radius: 14px; padding: 20px; }}
            .panel h2 {{ margin: 0 0 6px; font-size: 15px; color: var(--gold-deep); font-weight: 600; letter-spacing: 0.5px; }}
            .panel p.desc {{ margin: 0 0 14px; font-size: 12px; color: var(--muted); }}
            .panel input {{ width: 100%; margin-bottom: 10px; }}
            .panel button {{ width: 100%; }}
            .error {{ text-align: center; color: #c0392b; font-size: 13px; margin-bottom: 16px; }}
        </style>
    </head>
    <body>
        <div class="card">
            <div class="eyebrow">Number Oracle · Battle Mode</div>
            <h1>숫자의 신탁: 대결</h1>
            <div class="tagline">AI와 실력을 겨루거나, 친구와 실시간으로 대결하세요</div>
            {error_html}

            <div class="mode-tabs">
                <button type="button" class="tab-btn active" id="tab-ai">🤖 AI와 대결</button>
                <button type="button" class="tab-btn" id="tab-net">🌐 네트워크 대결</button>
            </div>

            <div id="panel-ai">
                <div class="panel">
                    <h2>🤖 컴퓨터(초급 AI)와 대결</h2>
                    <p class="desc">실력이 낮은 AI 오라클과 1:1로 먼저 정답을 맞혀보세요.</p>
                    <form method="post" action="/create-ai">
                        <input type="text" name="name" maxlength="12" placeholder="닉네임" required>
                        <button type="submit">대결 시작</button>
                    </form>
                </div>
            </div>

            <div id="panel-net" class="forms" hidden>
                <div class="panel">
                    <h2>⚔️ 새 대결방 만들기</h2>
                    <p class="desc">방 코드를 만들어 친구에게 공유하세요.</p>
                    <form method="post" action="/create">
                        <input type="text" name="name" maxlength="12" placeholder="닉네임" required>
                        <button type="submit">방 만들기</button>
                    </form>
                </div>
                <div class="panel">
                    <h2>🔑 코드로 참가하기</h2>
                    <p class="desc">친구가 만든 방 코드를 입력하세요.</p>
                    <form method="post" action="/join">
                        <input type="text" name="name" maxlength="12" placeholder="닉네임" required>
                        <input type="text" name="code" maxlength="4" placeholder="방 코드 (예: A7QX)" style="text-transform:uppercase" required>
                        <button type="submit">참가하기</button>
                    </form>
                </div>
            </div>
        </div>
        <script>
            const tabAi = document.getElementById("tab-ai");
            const tabNet = document.getElementById("tab-net");
            const panelAi = document.getElementById("panel-ai");
            const panelNet = document.getElementById("panel-net");
            tabAi.addEventListener("click", () => {{
                tabAi.classList.add("active"); tabNet.classList.remove("active");
                panelAi.hidden = false; panelNet.hidden = true;
            }});
            tabNet.addEventListener("click", () => {{
                tabNet.classList.add("active"); tabAi.classList.remove("active");
                panelNet.hidden = false; panelAi.hidden = true;
            }});
        </script>
    </body>
    </html>
    """


ROOM_PAGE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>NUMBER ORACLE · Battle Room</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&family=Poppins:wght@300;400;500;600&display=swap" rel="stylesheet">
    <style>__BASE_CSS__
        .card { width: 480px; }
        .code-badge { text-align: center; font-size: 13px; color: var(--muted); margin-bottom: 20px; letter-spacing: 1px; }
        .code-badge b { color: var(--gold-deep); font-size: 16px; letter-spacing: 3px; }
        .arena { display: flex; gap: 14px; margin-bottom: 20px; }
        .side { flex: 1; background: rgba(201,151,30,0.05); border: 1px solid rgba(201,151,30,0.18); border-radius: 14px; padding: 16px; min-width: 0; }
        .side.me { border-color: rgba(201,151,30,0.45); background: rgba(201,151,30,0.09); }
        .side h3 { margin: 0 0 10px; font-size: 13px; color: var(--text); display: flex; align-items: center; justify-content: space-between; }
        .side h3 .tag { font-size: 10px; color: var(--gold-deep); font-weight: 600; }
        .attempts { font-size: 26px; font-weight: 600; color: var(--gold-deep); font-family: 'Playfair Display', serif; }
        .attempts small { font-size: 11px; color: var(--muted); font-weight: 400; margin-left: 4px; }
        .mini-range { position: relative; height: 6px; border-radius: 4px; background: #ece0c6; margin: 10px 0; overflow: hidden; }
        .mini-fill { position: absolute; top: 0; bottom: 0; background: linear-gradient(90deg, var(--gold), var(--gold-bright)); border-radius: 4px; transition: all 0.35s ease; }
        .mini-hist { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; max-height: 100px; overflow-y: auto; }
        .mini-hist li { font-size: 11px; color: var(--muted); display: flex; justify-content: space-between; }
        .mini-hist li b { color: var(--text); }
        .mini-hist .up { color: #2f9e44; }
        .mini-hist .down { color: #d64545; }
        .status { text-align: center; font-size: 14px; min-height: 20px; margin-bottom: 14px; color: var(--text); }
        .guess-form { display: flex; gap: 10px; margin-bottom: 6px; }
        .waiting-overlay, .win-overlay { text-align: center; padding: 20px 0 6px; }
        .waiting-overlay .spinner { font-size: 40px; animation: pulse 1.4s ease-in-out infinite; }
        @keyframes pulse { 0%,100% { opacity: 0.4; transform: scale(0.95); } 50% { opacity: 1; transform: scale(1.05); } }
        .win-icon { font-size: 50px; animation: pop 0.5s ease; }
        @keyframes pop { 0% { transform: scale(0.4); opacity: 0; } 60% { transform: scale(1.1); opacity: 1; } 100% { transform: scale(1); } }
        .win-title { font-family: 'Playfair Display', serif; font-size: 24px; margin-top: 6px; }
        .win-title.win { color: var(--gold-deep); }
        .win-title.lose { color: var(--muted); }
        .win-detail { color: var(--muted); font-size: 13px; margin: 8px 0 16px; }
        [hidden] { display: none !important; }
        .copy-hint { text-align: center; font-size: 11px; color: var(--muted); margin-top: 10px; }
    </style>
</head>
<body>
    <div class="card">
        <div class="eyebrow">Number Oracle · Battle Mode</div>
        <h1>실시간 대결</h1>
        <div class="code-badge">방 코드 <b id="room-code">__CODE__</b></div>

        <div id="waiting" class="waiting-overlay">
            <div class="spinner">⏳</div>
            <div class="win-title win">상대방을 기다리는 중...</div>
            <div class="copy-hint">친구에게 방 코드 <b>__CODE__</b> 를 알려주세요</div>
        </div>

        <div id="arena-wrap" hidden>
            <div class="arena">
                <div class="side me">
                    <h3><span id="self-name">나</span><span class="tag">YOU</span></h3>
                    <div class="attempts"><span id="self-attempts">0</span><small>번 시도</small></div>
                    <div class="mini-range"><div class="mini-fill" id="self-fill"></div></div>
                    <ul class="mini-hist" id="self-hist"></ul>
                </div>
                <div class="side opp">
                    <h3><span id="opp-name">상대</span><span class="tag">RIVAL</span></h3>
                    <div class="attempts"><span id="opp-attempts">0</span><small>번 시도</small></div>
                    <div class="mini-range"><div class="mini-fill" id="opp-fill"></div></div>
                    <ul class="mini-hist" id="opp-hist"></ul>
                </div>
            </div>

            <div class="status" id="status"></div>

            <form id="guess-form" class="guess-form">
                <input type="number" id="guess-input" min="1" max="100" placeholder="1 ~ 100" required autofocus>
                <button type="submit">도전</button>
            </form>

            <div id="win-overlay" class="win-overlay" hidden>
                <div class="win-icon" id="win-icon">🏆</div>
                <div class="win-title" id="win-title"></div>
                <div class="win-detail" id="win-detail"></div>
                <button id="rematch-btn" style="width:100%">재대결</button>
            </div>
        </div>
    </div>

    <script>
        const CODE = "__CODE__";
        const proto = location.protocol === "https:" ? "wss://" : "ws://";
        const ws = new WebSocket(proto + location.host + "/ws/" + CODE);

        const waiting = document.getElementById("waiting");
        const arenaWrap = document.getElementById("arena-wrap");
        const guessForm = document.getElementById("guess-form");
        const guessInput = document.getElementById("guess-input");
        const winOverlay = document.getElementById("win-overlay");
        const statusEl = document.getElementById("status");

        function renderSide(prefix, data) {
            if (!data) return;
            document.getElementById(prefix + "-name").textContent = data.name;
            document.getElementById(prefix + "-attempts").textContent = data.attempts;
            const left = (data.low - 1) / 99 * 100;
            const right = (100 - data.high) / 99 * 100;
            const fill = document.getElementById(prefix + "-fill");
            fill.style.left = left + "%";
            fill.style.right = right + "%";
            const hist = document.getElementById(prefix + "-hist");
            hist.innerHTML = data.history.slice().reverse().map(h => {
                const cls = h.dir === "up" ? "up" : (h.dir === "down" ? "down" : "up");
                const label = h.dir === "up" ? "▲ 더 큼" : (h.dir === "down" ? "▼ 더 작음" : "🎯 정답");
                return `<li class="${cls}"><b>${h.value}</b><span>${label}</span></li>`;
            }).join("");
        }

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type !== "state") return;

            if (data.phase === "waiting") {
                waiting.hidden = false;
                arenaWrap.hidden = true;
                return;
            }

            waiting.hidden = true;
            arenaWrap.hidden = false;
            renderSide("self", data.self);
            renderSide("opp", data.opp);

            if (data.phase === "playing") {
                winOverlay.hidden = true;
                guessForm.hidden = false;
                statusEl.textContent = "먼저 정답을 맞히는 사람이 승리합니다!";
            } else if (data.phase === "over") {
                guessForm.hidden = true;
                winOverlay.hidden = false;
                statusEl.textContent = "";
                const won = data.winner === "self";
                document.getElementById("win-icon").textContent = won ? "🏆" : "🥈";
                const titleEl = document.getElementById("win-title");
                titleEl.textContent = won ? "승리!" : "패배...";
                titleEl.className = "win-title " + (won ? "win" : "lose");
                document.getElementById("win-detail").textContent =
                    `정답은 ${data.answer} · 나 ${data.self.attempts}번 / 상대 ${data.opp.attempts}번`;
            }
        };

        ws.onclose = () => {
            statusEl.textContent = "연결이 끊어졌습니다. 새로고침 해주세요.";
        };

        guessForm.addEventListener("submit", (e) => {
            e.preventDefault();
            const value = parseInt(guessInput.value, 10);
            if (!value) return;
            ws.send(JSON.stringify({ action: "guess", value: value }));
            guessInput.value = "";
            guessInput.focus();
        });

        document.getElementById("rematch-btn").addEventListener("click", () => {
            ws.send(JSON.stringify({ action: "rematch" }));
        });
    </script>
</body>
</html>
"""


def render_room(code: str) -> str:
    return ROOM_PAGE.replace("__BASE_CSS__", BASE_CSS).replace("__CODE__", code)


@app.get("/", response_class=HTMLResponse)
def lobby(error: str | None = None, player_id: str | None = Cookie(default=None)):
    response = HTMLResponse(render_lobby(error))
    if player_id is None:
        response.set_cookie("player_id", str(uuid.uuid4()))
    return response


@app.post("/create-ai")
def create_ai_room(name: str = Form(...), player_id: str | None = Cookie(default=None)):
    pid = player_id or str(uuid.uuid4())
    code = generate_code()
    room = Room(code=code, answer=random.randint(1, 100))
    room.players[pid] = Player(id=pid, name=(name.strip()[:12] or "Player1"))
    ai_id = f"ai-{uuid.uuid4()}"
    room.players[ai_id] = Player(id=ai_id, name=AI_NAME, is_ai=True)
    rooms[code] = room

    response = RedirectResponse(url=f"/room/{code}", status_code=303)
    response.set_cookie("player_id", pid)
    return response


@app.post("/create")
def create_room(name: str = Form(...), player_id: str | None = Cookie(default=None)):
    pid = player_id or str(uuid.uuid4())
    code = generate_code()
    room = Room(code=code, answer=random.randint(1, 100))
    room.players[pid] = Player(id=pid, name=(name.strip()[:12] or "Player1"))
    rooms[code] = room

    response = RedirectResponse(url=f"/room/{code}", status_code=303)
    response.set_cookie("player_id", pid)
    return response


@app.post("/join")
def join_room(name: str = Form(...), code: str = Form(...), player_id: str | None = Cookie(default=None)):
    pid = player_id or str(uuid.uuid4())
    code = code.strip().upper()
    room = rooms.get(code)

    if room is None:
        response = RedirectResponse(url="/?error=notfound", status_code=303)
        response.set_cookie("player_id", pid)
        return response

    if pid not in room.players and len(room.players) >= 2:
        response = RedirectResponse(url="/?error=full", status_code=303)
        response.set_cookie("player_id", pid)
        return response

    if pid not in room.players:
        room.players[pid] = Player(id=pid, name=(name.strip()[:12] or "Player2"))

    response = RedirectResponse(url=f"/room/{code}", status_code=303)
    response.set_cookie("player_id", pid)
    return response


@app.get("/room/{code}")
def room_page(code: str, player_id: str | None = Cookie(default=None)):
    code = code.upper()
    room = rooms.get(code)
    if room is None or player_id not in room.players:
        return RedirectResponse(url="/?error=notfound", status_code=303)
    return HTMLResponse(render_room(code))


@app.websocket("/ws/{code}")
async def ws_endpoint(websocket: WebSocket, code: str):
    code = code.upper()
    player_id = websocket.cookies.get("player_id")
    room = rooms.get(code)

    if room is None or player_id not in room.players:
        await websocket.close(code=4404)
        return

    await websocket.accept()
    room.players[player_id].ws = websocket

    connected = sum(1 for p in room.players.values() if is_connected(p))
    if len(room.players) == 2 and connected == 2 and room.phase == "waiting":
        room.phase = "playing"

    if not room.ai_started and any(p.is_ai for p in room.players.values()):
        room.ai_started = True
        ai_id = next(p.id for p in room.players.values() if p.is_ai)
        asyncio.create_task(ai_loop(room, ai_id))

    await broadcast(room)

    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            if action == "guess":
                handle_guess(room, player_id, data.get("value"))
                await broadcast(room)
            elif action == "rematch":
                reset_room(room)
                await broadcast(room)
    except WebSocketDisconnect:
        room.players[player_id].ws = None
        if room.phase == "playing":
            room.phase = "waiting"
        await broadcast(room)
