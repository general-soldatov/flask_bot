import os
import secrets
import hashlib
import hmac
import time
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import PlainTextResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field

from urllib.parse import parse_qs

# Загрузка переменных окружения
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

# Ключ подписи куки. Если не задан, создаётся при старте (после перезапуска все сессии сбросятся).
SECRET_KEY = (os.getenv("SECRET_KEY") or secrets.token_hex(32)).encode()
COOKIE_NAME = "admin_session"
COOKIE_SECURE = os.getenv("COOKIE_SECURE") == "1"  # включите за HTTPS
SESSION_TTL = 12 * 3600          # сессия без «Запомнить меня»
REMEMBER_TTL = 30 * 24 * 3600    # с «Запомнить меня»
MAX_FAILS, FAIL_WINDOW = 5, 300  # 5 неудачных попыток за 5 минут, затем блокировка
_fails: dict[str, list[float]] = {}

# from app.ydb_connect import ManageVK
from app.index import dp, db, Students

from site_app.vk_handler import get_data
from site_app.rate_maker import rate_score_vk, SCORES, Scores

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
# Настройка шаблонов (убедитесь, что папка "templates" находится рядом с файлом)
templates = Jinja2Templates(directory="templates")
static = Jinja2Templates(directory='static')

PROCESSED_EVENTS = []
MAX_CACHE_SIZE = 100

information = {
    'denied': 'Permission denied',
    'style': [
        'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css',
        '/static/style_tel.css'
    ]
}
# ---------- Сессия в подписанной куке ----------
 
def _sign(payload: str) -> str:
    return hmac.new(SECRET_KEY, payload.encode(), hashlib.sha256).hexdigest()
 
 
def make_token(user: str, ttl: int) -> str:
    payload = f"{user}|{int(time.time()) + ttl}"
    return f"{payload}|{_sign(payload)}"

def require_api_user(request: Request) -> str:
    user = current_user(request)
    if not user:
        raise HTTPException(401, "Нужно войти в систему")
    return user
 
 
def safe_next(value: Optional[str]) -> str:
    """Редирект только на путь внутри сайта."""
    if value and value.startswith("/") and not value.startswith("//") and "\\" not in value:
        return value
    return "/admin"
 
 
def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"
 
 
def is_locked(ip: str) -> bool:
    now = time.time()
    recent = [t for t in _fails.get(ip, []) if now - t < FAIL_WINDOW]
    _fails[ip] = recent
    return len(recent) >= MAX_FAILS
 
 
def read_token(token: Optional[str]) -> Optional[str]:
    """Возвращает имя пользователя, если подпись верна и срок не вышел."""
    if not token:
        return None
    try:
        user, exp, sig = token.rsplit("|", 2)
        valid = hmac.compare_digest(sig, _sign(f"{user}|{exp}")) and int(exp) > time.time()
    except ValueError:
        return None
    return user if valid and user == ADMIN_USER else None
 
 
def current_user(request: Request) -> Optional[str]:
    return read_token(request.cookies.get(COOKIE_NAME))

security = HTTPBasic()

def require_admin(creds: HTTPBasicCredentials = Depends(security)) -> None:
    if not ADMIN_PASSWORD:
        raise HTTPException(503, "Не задана переменная окружения ADMIN_PASSWORD")
    user_ok = secrets.compare_digest(creds.username.encode(), ADMIN_USER.encode())
    pass_ok = secrets.compare_digest(creds.password.encode(), ADMIN_PASSWORD.encode())
    if not (user_ok and pass_ok):
        raise HTTPException(
            401, "Неверный логин или пароль", headers={"WWW-Authenticate": "Basic"}
        )


async def load_payload() -> dict:
    """Сводные данные: студенты, задачи и баллы одним запросом на таблицу."""
    # students = [{'id': 1, 'full_name': "Алексеев Иван", "type_learn": "online",  "subject": "phys", 'group_id': "ИВТ-21", 'profile': "Разработка ПО", "bonus": {0: 5}}]
    students = []
    scores = await Scores.model_construct(SCORES)
    tasks = [{'id': 0, 'title': 'Пропуск лекций', 'max_score': 15}, {'id': 1, 'title': 'Штрафы', 'max_score': 20}, {'id': 2, 'title': 'Бонусы', 'max_score': 30}]
    return {"students": students, "tasks": tasks, 
            "scores": scores.model_dump()}

def get_student() -> dict:
    pass

def render_login(request: Request, status_code: int = 200, **ctx) -> HTMLResponse:
    ctx.setdefault("error", None)
    ctx.setdefault("username", "")
    ctx.setdefault("next", safe_next(request.query_params.get("next")))
    return templates.TemplateResponse(request, "login.html", ctx, status_code=status_code)

@app.post('/vk-bot/webhook')
async def handle_post(request: Request): # Убрали async
    try:
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            # В синхронной функции FastAPI нужно использовать специальный фокус 
            # или запустить асинхронный метод через loop, но проще сделать так:
            data = await request.json()
            
            if data.get('type') == 'confirmation':
                confirmation_code = os.getenv("CONFIRMATION_CODE", "").strip()
                return PlainTextResponse(content=confirmation_code, status_code=200)
            
            event_id = data.get('event_id')
            if event_id:
                if event_id in PROCESSED_EVENTS:
                    return PlainTextResponse(content='ok')
                
                PROCESSED_EVENTS.append(event_id)
                if len(PROCESSED_EVENTS) > MAX_CACHE_SIZE:
                    PROCESSED_EVENTS.pop(0) 
            
            text = await dp.feed_webhook(data, context_data={'db': db})
            
        return PlainTextResponse(content=text)
        
    except Exception as e:
        # Логируем ошибку в консоль Amvera, чтобы вы её видели!
        print(f"Ошибка в вебхуке: {e}") 
        return PlainTextResponse(content=str(e), status_code=500)

@app.get("/vk_bot/bot={name}")
async def vk_bot(request: Request, name: str):
    name = int(name)
    student = await get_data(name)
    return templates.TemplateResponse(request, 'students.html',
                                      context={'request': request,
                                               'student': student,
                                               'information': information})

@app.get("/vk_bot/rate")
async def dev_rate():
    return await rate_score_vk()


@app.get('/', response_class=HTMLResponse)
async def hello_index(request: Request, name: str = None):
    variant = "Hello"
    # В FastAPI контекст Jinja2 обязательно должен содержать "request"
    return templates.TemplateResponse(
        request=request,  # Рекомендуется также явно передать request первым аргументом
        name="index.html",
        context={"name": name, "variant": variant}
    )

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if current_user(request):
        return RedirectResponse(safe_next(request.query_params.get("next")), status_code=303)
    return render_login(request)

@app.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request):
    raw = await request.body()
    if len(raw) > 4096:
        raise HTTPException(413, "Слишком большой запрос")
    form = {
        k: v[0]
        for k, v in parse_qs(raw.decode("utf-8", "replace"), keep_blank_values=True).items()
    }
    username = form.get("username", "").strip()
    password = form.get("password", "")
    next_url = safe_next(form.get("next"))
    ctx = {"username": username, "next": next_url}
 
    if not ADMIN_PASSWORD:
        return render_login(
            request, 503, error="Вход не настроен: не задана переменная ADMIN_PASSWORD", **ctx
        )
 
    ip = client_ip(request)
    if is_locked(ip):
        return render_login(
            request, 429, error="Слишком много попыток. Подождите несколько минут.", **ctx
        )
 
    # Обе проверки выполняются всегда, чтобы время ответа не выдавало, что именно неверно
    user_ok = secrets.compare_digest(username.encode(), ADMIN_USER.encode())
    pass_ok = secrets.compare_digest(password.encode(), ADMIN_PASSWORD.encode())
    if not (user_ok and pass_ok):
        _fails.setdefault(ip, []).append(time.time())
        return render_login(request, 401, error="Неверный логин или пароль", **ctx)
 
    _fails.pop(ip, None)
    remember = form.get("remember") == "1"
    response = RedirectResponse(next_url, status_code=303)
    response.set_cookie(
        COOKIE_NAME,
        make_token(ADMIN_USER, REMEMBER_TTL if remember else SESSION_TTL),
        max_age=REMEMBER_TTL if remember else None,  # None = кука живёт до закрытия браузера
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
        path="/",
    )
    return response
 
 
@app.post("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(COOKIE_NAME, path="/")
    return response

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    if not current_user(request):
        return RedirectResponse("/login?next=/admin", status_code=303)
    return templates.TemplateResponse(request, "admin.html", {"payload": await load_payload()})

class ScoreIn(BaseModel):
    student_id: int
    task_id: int
    score: Optional[int] = Field(default=None, ge=0)  # None = убрать оценку
 
 
class ScoresIn(BaseModel):
    items: list[ScoreIn] = Field(min_length=1, max_length=2000)

@app.post("/api/scores", dependencies=[Depends(require_api_user)])
async def save_scores(body: ScoresIn):
    for item in body.items:
        print(item)
        await db.add_bonus(**item.model_dump())
    
    return {"saved": len(body.items)}

class State(BaseModel):
    key: str
    dir: int
    task: int
    group: str
    profile: str
    q: str
    subject: str
    type_learn: str

    def get_condition(self):
        keys = {}
        if self.key != 'full_name':
            keys['full_name'] = self.key
        if self.group:
            keys['group_id'] = self.group
        if self.profile:
            keys['profile'] = self.profile
        if self.subject:
            keys['subject'] = self.subject
        if self.type_learn:
            keys['form_study'] = ['offline', 'online'].index(self.type_learn)
        return keys

@app.post("/api/students", dependencies=[Depends(require_api_user)])
async def get_students(body: State):
    scores = await Scores.model_construct(SCORES)
    keys = body.get_condition()
    if not keys:
        students = await db.get_all_student()
    else:
        students: list = await db.select_keys(Students, **keys)
    if not students:
        return
    elems = []
    for student in students:
        elem = student.model_dump()
        step = await db.get_score_stepik(student.id)
        elem['step'] = 0
        if step:
            elem['step'] = step.score
        elem.update(scores.get_mark(student, step))
        elems.append(elem)

    return elems

if __name__ == "__main__":
    import uvicorn
    # Запуск сервера uvicorn вместо app.run()
    uvicorn.run("flask_app:app", host="0.0.0.0", port=5000, reload=True)


