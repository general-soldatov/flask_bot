import os
from flask import Flask, request, jsonify, render_template, Response
from dotenv import load_dotenv
from pathlib import Path
from app.index import handler

env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

app = Flask(__name__)

@app.route('/vk-bot/webhook', methods=['POST'])
def handle_post():
    # 1. Если данные отправлены как JSON (часто используется для Telegram-ботов)
    # data = request.get_json(silent=True)
    if request.is_json:
        data = request.get_json()
    
        # Обработка подтверждения
        if data.get('type') == 'confirmation':
            return Response(os.getenv("CONFIRMATION_CODE"), mimetype='text/plain')
        handler(data)
        # return jsonify({"status": "success", "received_json_user": username}), 200
    return Response('ok', mimetype='text/plain')


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
