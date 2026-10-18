import os
from flask import Flask, request, render_template, Response
from dotenv import load_dotenv
from pathlib import Path
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

from app.index import handler

app = Flask(__name__)

PROCESSED_EVENTS = []
MAX_CACHE_SIZE = 100

@app.route('/vk-bot/webhook', methods=['POST'])
def handle_post():
    # 1. Если данные отправлены как JSON (часто используется для Telegram-ботов)
    # data = request.get_json(silent=True)
    try:
        if request.is_json:
            data = request.get_json()
        
            # Обработка подтверждения
            if data.get('type') == 'confirmation':
                return Response(os.getenv("CONFIRMATION_CODE", "").strip(), status=200, content_type="text/plain; charset=utf-8")
            
            event_id = data.get('event_id')
            if event_id:
                if event_id in PROCESSED_EVENTS:
                    # Если этот ID мы уже видели секунду назад — это дубликат от ВК!
                    # Мгновенно возвращаем 'ok', игнорируя повторное выполнение кода
                    return Response('ok', mimetype='text/plain')
                
                # Если ID новый, запоминаем его
                PROCESSED_EVENTS.append(event_id)
                if len(PROCESSED_EVENTS) > MAX_CACHE_SIZE:
                    PROCESSED_EVENTS.pop(0) 
            handler(data, {})
            # return jsonify({"status": "success", "received_json_user": username}), 200
        return Response('ok', mimetype='text/plain')
    except Exception as e:
        return Response(e, mimetype='text/plain')


@app.route('/')
def hello_index(name=None):
    variant = "Hello"
    return render_template('index.html', name=name, variant=variant)



# @app.route('/study/')
# def study():
#     return render_template('index.html', variant="Вариант не найден")

# @app.route('/study/<name>')
# def stud_name(name=None):
#     header = ['ФИО', 'Профиль обучения', 'Группа', 'Подгруппа', 'Вариант', 'Вариант Д1']
#     infos = {}
    

#     return render_template('index.html', name=name, infos=infos)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)