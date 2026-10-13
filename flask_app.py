
# A very simple Flask Hello World app for you to get started with...

from flask import Flask, render_template
from telefunc import sql_base_read_, admin
import gspread

app = Flask(__name__)

def base_select(request):
    with sql_base_read_() as connection:
        cursor = connection.cursor()
        cursor.execute(request)
        result = cursor.fetchall()
        return result

def var(user_id):
    try:
        show_select = f"SELECT name, profile, name_group, section, variant, variant_D1 FROM data_user WHERE user_id = {user_id}"
        return base_select(show_select)[0]

    except:
        return "Вариант не найден"


def rater(user_id):
    gc = gspread.service_account(filename='termex-bot-0ea77baf201b.json') # Указываем путь к JSON
    sh = gc.open("Термех 2/2024") #Открываем тестовую таблицу
    worksheet = sh.worksheet("rate")
    all_rows = worksheet.get_all_values()

    try:
        show_select = f"SELECT name FROM data_user WHERE user_id = {user_id}"
        res = base_select(show_select)
        for row in all_rows:
            if row[0] == res[0][0]:
                row_name = row
                break

        return row_name[16], row_name[17]

    except:
        return 0, 0

@app.route('/')
def hello_index(name=None):

    variant = "Hello"
    return render_template('index.html', name=name, variant=variant)

@app.route('/study/')
def study():
    return render_template('index.html', variant="Вариант не найден")

@app.route('/study/<name>')
def stud_name(name=None):
    header = ['ФИО', 'Профиль обучения', 'Группа', 'Подгруппа', 'Вариант', 'Вариант Д1']
    namer = var(name)
    infos = {}
    for nm in range(len(namer)):
        infos.update({header[nm]: namer[nm]})

    return render_template('index.html', name=name, infos=infos)

@app.route('/telegram/')
def telega():
    return render_template('telegram.html', variant="Вариант не найден")

@app.route('/telegram/<name>')
def telega_name(name=None):
    def star_rate(rating):
        rate = {2: 5, 5: 4, 10: 3, 13: 2}
        for key, value in rate.items():
            if rating <= key:
                return value

        return 1

    def rang_rate(ball):
        rate = {
            18: ["Лосяш", "https://img.razrisyika.ru/kart/125/499535-smeshariki-losyash-35.jpg"], #150
            15: ["Пин", "https://crosti.ru/patterns/00/0e/40/71_picture_5deec7b0.jpg"], #120
            9: ["Копатыч", "https://prixoxo.ru/uploads/posts/2023-10/prixoxo.ru_krasivaja-kartinka-kopatycha-72.jpg"], #60
            5: ["Нюша", "https://sun9-29.userapi.com/c656/u18268279/89959677/x_70261d7a.jpg"], #30
            2: ["Бараш", "https://sun6-22.userapi.com/s/v1/if1/ySgP-BKkHdVj_oAfPI_on0wjMEQtVMN-HlrFg_ZcHou610Uh2fkVIFi3yW_XeeUqOKbEMcOA.jpg?size=627x646&quality=96&crop=80,0,627,646&ava=1"], #10
            -20: ["Крош", "https://img.razrisyika.ru/kart/90/1200/356946-krosha-22.jpg"],
            }

        for key, value in rate.items():
            if ball > key:
                return value

    header = ['ФИО', 'Профиль', 'Группа', 'Подгруппа', 'Вариант', 'Вариант Д1', 'Место в рейтинге']
    namer = list(var(name))
    rate = rater(name)
    namer.append(rate[1])
    star = star_rate(float(rate[1]))
    rang = rang_rate(int(rate[0].split(sep=",")[0]))
    infos = {}
    fio = namer[0]
    for nm in range(1, len(namer)):
        infos.update({header[nm]: namer[nm]})

    return render_template('telegram.html', name=name, fio=fio, star=star, rate=rate, rang=rang, infos=infos)
