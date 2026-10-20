import os
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response, status
from fastapi.responses import PlainTextResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

# Загрузка переменных окружения
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

from app.index import handler

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
# Настройка шаблонов (убедитесь, что папка "templates" находится рядом с файлом)
templates = Jinja2Templates(directory="templates")
static = Jinja2Templates(directory='static')

PROCESSED_EVENTS = []
MAX_CACHE_SIZE = 100

@app.post('/vk-bot/webhook')
async def handle_post(request: Request):
    try:
        # Проверяем, является ли контент JSON-данными
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            data = await request.json()
            
            # Обработка подтверждения VK
            if data.get('type') == 'confirmation':
                confirmation_code = os.getenv("CONFIRMATION_CODE", "").strip()
                return PlainTextResponse(content=confirmation_code, status_code=200)
            
            event_id = data.get('event_id')
            if event_id:
                if event_id in PROCESSED_EVENTS:
                    # Если ID дублируется — возвращаем 'ok'
                    return PlainTextResponse(content='ok')
                
                # Запоминаем новый ID
                PROCESSED_EVENTS.append(event_id)
                if len(PROCESSED_EVENTS) > MAX_CACHE_SIZE:
                    PROCESSED_EVENTS.pop(0) 
            
            # Передаем данные в ваш хендлер
            await handler(data, {})
            
        return PlainTextResponse(content='ok')
        
    except Exception as e:
        # Возвращаем текст ошибки в случае сбоя
        return PlainTextResponse(content=str(e), status_code=500)


@app.get('/', response_class=HTMLResponse)
async def hello_index(request: Request, name: str = None):
    variant = "Hello"
    # В FastAPI контекст Jinja2 обязательно должен содержать "request"
    return templates.TemplateResponse(
        request=request,  # Рекомендуется также явно передать request первым аргументом
        name="index.html",
        context={"name": name, "variant": variant}
    )


if __name__ == "__main__":
    import uvicorn
    # Запуск сервера uvicorn вместо app.run()
    uvicorn.run("flask_app:app", host="0.0.0.0", port=5000, reload=True)



# @app.route('/vk-bot/webhook', methods=['POST'])
# def handle_post():
#     # 1. Если данные отправлены как JSON (часто используется для Telegram-ботов)
#     # data = request.get_json(silent=True)
#     try:
#         if request.is_json:
#             data = request.get_json()
        
#             # Обработка подтверждения
#             if data.get('type') == 'confirmation':
#                 return Response(os.getenv("CONFIRMATION_CODE", "").strip(), status=200, content_type="text/plain; charset=utf-8")
            
#             event_id = data.get('event_id')
#             if event_id:
#                 if event_id in PROCESSED_EVENTS:
#                     # Если этот ID мы уже видели секунду назад — это дубликат от ВК!
#                     # Мгновенно возвращаем 'ok', игнорируя повторное выполнение кода
#                     return Response('ok', mimetype='text/plain')
                
#                 # Если ID новый, запоминаем его
#                 PROCESSED_EVENTS.append(event_id)
#                 if len(PROCESSED_EVENTS) > MAX_CACHE_SIZE:
#                     PROCESSED_EVENTS.pop(0) 
#             handler(data, {})
#             # return jsonify({"status": "success", "received_json_user": username}), 200
#         return Response('ok', mimetype='text/plain')
#     except Exception as e:
#         return Response(e, mimetype='text/plain')


# @app.route('/')
# def hello_index(name=None):
#     variant = "Hello"
#     return render_template('index.html', name=name, variant=variant)



# @app.route('/study/')
# def study():
#     return render_template('index.html', variant="Вариант не найден")

# @app.route('/study/<name>')
# def stud_name(name=None):
#     header = ['ФИО', 'Профиль обучения', 'Группа', 'Подгруппа', 'Вариант', 'Вариант Д1']
#     infos = {}
    

#     return render_template('index.html', name=name, infos=infos)

# if __name__ == "__main__":
#     app.run(host="0.0.0.0", port=5000) 