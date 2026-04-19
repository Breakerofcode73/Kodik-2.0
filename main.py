from flask import Flask, render_template, request, redirect, abort, session, send_file, g
from flask_socketio import SocketIO, send, emit
from flask_mobility import Mobility
from getters import *
from fast_download import clear_tmp, fast_download, get_path
import watch_together
from json import load
import config
import os
import uuid
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = config.APP_SECRET_KEY
socketio = SocketIO(app)
Mobility(app)

# Менеджер комнат совместного просмотра
watch_manager = watch_together.Manager(config.REMOVE_TIME)

token = config.KODIK_TOKEN

with open("translations.json", 'r', encoding='utf-8') as f:
    translations = load(f)

if config.USE_SAVED_DATA or config.SAVE_DATA:
    from cache import Cache
    ch = Cache(config.SAVED_DATA_FILE, config.SAVING_PERIOD, config.CACHE_LIFE_TIME)
ch_save = config.SAVE_DATA
ch_use = config.USE_SAVED_DATA

# Очистка tmp
clear_tmp()

# Проверка доступности шикимори (если мешает - закомментируйте)
try:
    test_shiki()
except Exception as e:
    print(f"⚠️ Shikimori test failed: {e}")

# -------------------- Вспомогательная функция для совместного просмотра --------------------
def get_seria_url(seria_id, seria, quality):
    """Возвращает прямую ссылку на видео для заданной серии и качества."""
    # Определяем тип ID по префиксу
    if seria_id.startswith('sh'):
        id_type = 'shikimori'
        clean_id = seria_id[2:]
        serv = 'sh'
    elif seria_id.startswith('kp'):
        id_type = 'kinopoisk'
        clean_id = seria_id[2:]
        serv = 'kp'
    else:
        # Без префикса - по умолчанию Shikimori
        id_type = 'shikimori'
        clean_id = seria_id
        serv = 'sh'

    try:
        serial_data = get_serial_info(clean_id, id_type, token)
        if not serial_data:
            return None

        # Обработка переводов (иногда приходит список, иногда словарь)
        translations = serial_data.get('translations', {})
        if isinstance(translations, list):
            translations = {str(i): v for i, v in enumerate(translations)}
        if not translations:
            translation_id = '0'
        else:
            translation_id = list(translations.keys())[0]

        cache_id = f"sh{clean_id}" if serv == 'sh' else f"kp{clean_id}"
        if ch_use and ch.is_seria(cache_id, translation_id, seria):
            url_part = ch.get_seria(cache_id, translation_id, seria)
        else:
            url_part = get_download_link(clean_id, id_type, seria, translation_id, token)
            if ch_save:
                try:
                    ch.add_seria(cache_id, translation_id, seria, url_part)
                except KeyError:
                    pass

        return f"https:{url_part}{quality}.mp4"
    except Exception as e:
        print(f"Ошибка получения ссылки для серии {seria} сериала {seria_id}: {e}")
        return None
def get_seria_info(seria_id):
    """
    Возвращает словарь с данными о сериале и прямой ссылкой на видео.
    """
    # Определяем тип ID по префиксу
    if seria_id.startswith('sh'):
        id_type = 'shikimori'
        clean_id = seria_id[2:]
        serv = 'sh'
    elif seria_id.startswith('kp'):
        id_type = 'kinopoisk'
        clean_id = seria_id[2:]
        serv = 'kp'
    else:
        id_type = 'shikimori'
        clean_id = seria_id
        serv = 'sh'

    try:
        serial_data = get_serial_info(clean_id, id_type, token)
        if not serial_data:
            return None

        # Определяем количество серий
        max_series = serial_data.get('series_count', 1)
        if isinstance(max_series, list):
            max_series = max_series[1] if len(max_series) > 1 else 1

        # Получаем прямую ссылку на первую серию (качество по умолчанию 720)
        video_url = get_seria_url(seria_id, 1, 720)

        return {
            'video_url': video_url,
            'id_type': id_type,
            'max_series': max_series
        }
    except Exception as e:
        print(f"Ошибка получения данных сериала {seria_id}: {e}")
        return None

# -------------------- Основные маршруты (без изменений) --------------------
@app.route('/')
def index():
    return render_template('index.html',
                           is_dark=session['is_dark'] if "is_dark" in session.keys() else False,
                           is_kodik_search=USE_KODIK_SEARCH)

@app.route('/', methods=['POST'])
def index_form():
    data = dict(request.form)
    if 'shikimori_id' in data.keys():
        return redirect(f"/download/sh/{data['shikimori_id']}/")
    if 'kinopoisk_id' in data.keys():
        return redirect(f"/download/kp/{data['kinopoisk_id']}/")
    elif 'kdk' in data.keys():
        return redirect(f"/search/kdk/{data['kdk']}/")
    else:
        return abort(400)

@app.route("/change_theme/", methods=['POST'])
def change_theme():
    if "is_dark" in session.keys():
        session['is_dark'] = not(session['is_dark'])
    else:
        session['is_dark'] = True
    return redirect(request.referrer)

@app.route('/search/<string:db>/<string:query>/')
def search_page(db, query):
    if db == "kdk":
        try:
            s_data = get_search_data(query, token, ch if ch_save or ch_use else None)
            return render_template('search.html', items=s_data[0], others=s_data[1],
                                   is_dark=session['is_dark'] if "is_dark" in session.keys() else False,
                                   is_mobile=g.is_mobile, is_kodik_search=USE_KODIK_SEARCH)
        except:
            return render_template('search.html',
                                   is_dark=session['is_dark'] if "is_dark" in session.keys() else False,
                                   is_mobile=g.is_mobile, is_kodik_search=USE_KODIK_SEARCH)
    else:
        return abort(400)

@app.route('/download/<string:serv>/<string:id>/')
def download_shiki_choose_translation(serv, id):
    # Оставлено без изменений
    if serv == "sh":
        if ch_use and ch.is_id("sh"+id) and ch.get_data_by_id("sh"+id)['serial_data'] != {}:
            serial_data = ch.get_data_by_id("sh"+id)['serial_data']
        else:
            try:
                serial_data = get_serial_info(id, "shikimori", token)
            except Exception as ex:
                return f"""
                <h1>По данному запросу нет данных</h1>
                {f'<p>Exception type: {ex}</p>' if config.DEBUG else ''}
                """
        cache_used = False
        if ch_use and ch.is_id("sh"+id):
            cached = ch.get_data_by_id("sh"+id)
            name = cached['title']
            pic = cached['image']
            score = cached['score']
            dtype = cached['type']
            date = cached['date']
            status = cached['status']
            rating = cached['rating']
            year = cached['year']
            description = cached['description']
            if is_good_quality_image(pic):
                cache_used = True
        if not cache_used:
            try:
                data = get_shiki_data(id)
                name = data['title']
                pic = data['image']
                score = data['score']
                dtype = data['type']
                date = data['date']
                status = data['status']
                rating = data['rating']
                year = data['year']
                description = data['description']
            except:
                name = 'Неизвестно'
                pic = config.IMAGE_NOT_FOUND
                score = 'Неизвестно'
                dtype = 'Неизвестно'
                date = 'Неизвестно'
                status = 'Неизвестно'
                rating = 'Неизвестно'
                year = 'Неизвестно'
                description = 'Неизвестно'
                data = False
            finally:
                if ch_save and not ch.is_id("sh"+id):
                    ch.add_id("sh"+id, name, pic, score, data['status'] if data else "Неизвестно",
                              data['date'] if data else "Неизвестно", data['year'] if data else 1970,
                              data['type'] if data else "Неизвестно", data['rating'] if data else "Неизвестно",
                              data['description'] if data else '', serial_data=serial_data)
        if ch_use and ch_save and ch.is_id("sh"+id) and ch.get_data_by_id("sh"+id)['serial_data'] == {}:
            ch.add_serial_data("sh"+id, serial_data)
        try:
            if ch_use and ch.is_id("sh"+id) and ch.get_data_by_id("sh"+id)['related'] != []:
                related = ch.get_data_by_id("sh"+id)['related']
            else:
                related = get_related(id, 'shikimori', sequel_first=True)
                ch.add_related("sh"+id, related)
        except:
            related = []
        return render_template('info.html',
            title=name, image=pic, score=score, translations=serial_data['translations'], series_count=serial_data["series_count"], id=id,
            dtype=dtype, date=date, status=status, rating=rating, related=related, description=description, is_shiki=True,
            is_dark=session['is_dark'] if "is_dark" in session.keys() else False, is_mobile=g.is_mobile,
            shiki_mirror=config.SHIKIMORI_MIRROR if config.SHIKIMORI_MIRROR else "shikimori.one")
    elif serv == "kp":
        try:
            serial_data = get_serial_info(id, "kinopoisk", token)
        except Exception as ex:
            return f"""
            <h1>По данному запросу нет данных</h1>
            {f'<p>Exception type: {ex}</p>' if config.DEBUG else ''}
            """
        return render_template('info.html',
            title="...", image=config.IMAGE_NOT_FOUND, score="...", translations=serial_data['translations'], series_count=serial_data["series_count"], id=id,
            dtype="...", date="...", status="...", description='...', is_shiki=False,
            is_dark=session['is_dark'] if "is_dark" in session.keys() else False, is_mobile=g.is_mobile)
    else:
        return abort(400)

@app.route('/download/<string:serv>/<string:id>/<string:data>/')
def download_choose_seria(serv, id, data):
    if data == "None":
        return
    data = data.split('-')
    series = [int(x) for x in data[0].split(":")]
    return render_template('download.html', series=series, backlink=f"/download/{serv}/{id}/",
                           is_dark=session['is_dark'] if "is_dark" in session.keys() else False, is_mobile=g.is_mobile)

@app.route('/download/<string:serv>/<string:id>/<string:data>/<string:download_type>-<string:quality>-<int:seria>/')
def redirect_to_download(serv, id, data, download_type, quality, seria):
    data = data.split('-')
    series = [int(x) for x in data[0].split(":")]
    translation_id = str(data[1])
    if download_type == 'fast':
        return redirect(f'/fast_download/{serv}-{id}-{seria}-{translation_id}-{quality}-{series[1]}/')
    try:
        if serv == "sh":
            if ch_use and ch.is_seria("sh"+id, translation_id, seria):
                url = ch.get_seria("sh"+id, translation_id, seria)
            else:
                url = get_download_link(id, "shikimori", seria, translation_id, token)
                if ch_save:
                    try:
                        ch.add_seria("sh"+id, translation_id, seria, url)
                    except KeyError:
                        pass
        elif serv == "kp":
            if ch_use and ch.is_seria("kp"+id, translation_id, seria):
                url = ch.get_seria("kp"+id, translation_id, seria)
            else:
                url = get_download_link(id, "kinopoisk", seria, translation_id, token)
                if ch_save:
                    try:
                        ch.add_seria("kp"+id, translation_id, seria, url)
                    except KeyError:
                        pass
        else:
            return abort(400)
        translation = translations[translation_id] if translation_id in translations else "Неизвестно"
        if seria == 0:
            return redirect(f"https:{url}{quality}.mp4:Перевод-{translation}:.mp4")
        else:
            return redirect(f"https:{url}{quality}.mp4:Серия-{seria}:Перевод-{translation}:.mp4")
    except Exception as ex:
        return abort(500, f'Exception: {ex}')

@app.route('/download/<string:serv>/<string:id>/<string:data>/watch-<int:num>/')
def redirect_to_player(serv, id, data, num):
    series = [int(x) for x in data.split("-")[0].split(':')]
    if series[0] == 0 and series[1] == 0:
        return redirect(f'/watch/{serv}/{id}/{data}/0/')
    else:
        return redirect(f'/watch/{serv}/{id}/{data}/{num}/')

@app.route('/watch/<string:serv>/<string:id>/<string:data>/<int:seria>/<string:old_quality>/q-<string:quality>/')
@app.route('/watch/<string:serv>/<string:id>/<string:data>/<int:seria>/<string:old_quality>/<int:timing>/q-<string:quality>/')
def change_watch_quality(serv, id, data, seria, old_quality, quality, timing = None):
    return redirect(f"/watch/{serv}/{id}/{data}/{seria}/{quality}/{str(timing)+'/' if timing else ''}")

@app.route('/watch/<string:serv>/<string:id>/<string:data>/<int:seria>/q-<string:quality>/')
@app.route('/watch/<string:serv>/<string:id>/<string:data>/<int:seria>/q-<string:quality>/<int:timing>/')
def redirect_to_old_type_quality(serv, id, data, seria, quality, timing = 0):
    return redirect(f"/watch/{serv}/{id}/{data}/{seria}/{quality}/{str(timing)+'/' if timing else ''}")

@app.route('/watch/<string:serv>/<string:id>/<string:data>/<int:seria>/')
@app.route('/watch/<string:serv>/<string:id>/<string:data>/<int:seria>/<string:quality>/')
@app.route('/watch/<string:serv>/<string:id>/<string:data>/<int:seria>/<string:quality>/<int:timing>/')
def watch(serv, id, data, seria, quality = "720", timing = 0):
    try:
        data = data.split('-')
        series = [int(x) for x in data[0].split(":")]
        translation_id = str(data[1])
        title = None
        if serv == "sh":
            id_type = "shikimori"
            if ch_use:
                try:
                    title = ch.get_data_by_id("sh"+id)['title'] if ch.get_data_by_id("sh"+id) else None
                except:
                    title = None
            if ch_use and ch.is_seria("sh"+id, translation_id, seria):
                url = ch.get_seria("sh"+id, translation_id, seria)
            else:
                url = get_download_link(id, "shikimori", seria, translation_id, token)
                if ch_save and not ch.is_seria("sh"+id, translation_id, seria):
                    try:
                        ch.add_seria("sh"+id, translation_id, seria, url)
                    except KeyError:
                        pass
        elif serv == "kp":
            id_type = "kinopoisk"
            if ch_use:
                try:
                    title = ch.get_data_by_id("kp"+id)['title'] if ch.get_data_by_id("kp"+id) else None
                except:
                    title = None
            if ch_use and ch.is_seria("kp"+id, translation_id, seria):
                url = ch.get_seria("kp"+id, translation_id, seria)
            else:
                url = get_download_link(id, "kinopoisk", seria, translation_id, token)
                if ch_save and not ch.is_seria("kp"+id, translation_id, seria):
                    try:
                        ch.add_seria("kp"+id, translation_id, seria, url)
                    except KeyError:
                        pass
        else:
            return abort(400)
        straight_url = f"https:{url}{quality}.mp4"
        url = f"/download/{serv}/{id}/{'-'.join(data)}/old-{quality}-{seria}"
        return render_template('watch.html',
            url=url, seria=seria, series=series, id=id, id_type=id_type, data="-".join(data), quality=quality, serv=serv, straight_url=straight_url,
            allow_watch_together=config.ALLOW_WATCH_TOGETHER,
            is_dark=session['is_dark'] if "is_dark" in session.keys() else False,
            timing=timing, title=title, is_mobile=g.is_mobile)
    except:
        return abort(404)

@app.route('/watch/<string:serv>/<string:id>/<string:data>/<int:seria>/', methods=['POST'])
@app.route('/watch/<string:serv>/<string:id>/<string:data>/<int:seria>/<string:quality>/', methods=['POST'])
def change_seria(serv, id, data, seria, quality=None):
    try:
        new_seria = int(dict(request.form)['seria'])
    except:
        return abort(400)
    data = data.split('-')
    series = int(data[0])
    if new_seria > series or new_seria < 1:
        return abort(400, "Данная серия не существует")
    else:
        return redirect(f"/watch/{serv}/{id}/{'-'.join(data)}/{new_seria}{'/'+quality if quality != None else ''}")


# -------------------- Watch Together (исправленные маршруты) --------------------
@app.route('/create_room/', methods=["POST", "GET"])
def create_room():
    # Поддержка и GET, и POST
    if request.method == "POST":
        data = request.form
    else:
        data = request.args

    # Пробуем получить ID сериала из разных возможных полей
    seria_id = (data.get('seria_id') or
                data.get('id') or
                data.get('shikimori_id') or
                data.get('kinopoisk_id'))

    quality = data.get('quality', '720').replace('p', '')  # убираем 'p' на всякий случай
    raw_series = data.get('series_count') or data.get('max_series', '')

    if not seria_id:
        return "Не указан ID сериала (ожидался seria_id, id, shikimori_id или kinopoisk_id)", 400
    if not raw_series:
        return "Не указано количество серий (series_count)", 400

    # Извлекаем общее количество серий (формат "текущая:всего")
    if ':' in raw_series:
        total_series_str = raw_series.split(':')[1]
    else:
        total_series_str = raw_series

    try:
        max_series = int(total_series_str)
    except ValueError:
        return "Некорректное количество серий", 400

    # Генерируем уникальный ID комнаты
    rid = str(uuid.uuid4())[:8]
    if not watch_manager.create_room(rid, seria_id, quality, max_series):
        return "Не удалось создать комнату", 500

    return redirect(f"/room/{rid}/")

@app.route('/room/<string:rid>/')
def room(rid):
    room = watch_manager.get_room(rid)
    if not room:
        return "Комната не найдена или устарела", 404

    seria_info = get_seria_info(room.seria_id)
    if not seria_info:
        return "Информация о сериале недоступна", 503

    straight_url = seria_info.get('video_url', '')
    start_time = room.play_time or 0

    return render_template('room.html',
                           rid=rid,
                           id=room.seria_id,
                           id_type=seria_info.get('id_type', ''),
                           seria=room.current_series,
                           series=room.max_series,
                           quality=room.quality,
                           straight_url=straight_url,
                           start_time=start_time,
                           is_dark=session.get('is_dark', False))

@app.route('/room/<string:rid>/', methods=["POST"])
def change_room_seria_form(rid):
    data = dict(request.form).get('seria')
    if not data:
        return redirect(f"/room/{rid}/")
    try:
        seria = int(data)
    except ValueError:
        return redirect(f"/room/{rid}/")
    return redirect(f"/room/{rid}/cs-{seria}/")

@app.route('/room/<string:rid>/cs-<int:seria>/')
def change_room_seria(rid, seria):
    if not watch_manager.is_room(rid):
        return abort(404)
    room = watch_manager.get_room(rid)
    if seria < 1 or seria > room.max_series:
        return abort(400)

    room.current_series = seria
    room.play_time = 0
    watch_manager.room_used(rid)

    socketio.emit('update_video', {
        'seria': seria,
        'quality': room.quality,
        'play_time': 0
    }, to=rid)

    return redirect(f"/room/{rid}/")

@app.route('/room/<string:rid>/cq-<int:quality>/')
def change_room_quality(rid, quality):
    if not watch_manager.is_room(rid):
        return abort(404)

    allowed = [360, 480, 720, 1080]
    if quality not in allowed:
        return abort(400)

    room = watch_manager.get_room(rid)
    room.quality = quality
    watch_manager.room_used(rid)

    socketio.emit('update_video', {
        'seria': room.current_series,
        'quality': quality,
        'play_time': room.play_time
    }, to=rid)

    return redirect(f"/room/{rid}/")


# -------------------- WebSocket обработчики --------------------
@socketio.on('join')
def on_join(data):
    rid = data.get('room')
    if watch_manager.is_room(rid):
        room = watch_manager.get_room(rid)
        video_url = get_seria_url(room.seria_id, room.current_series, room.quality)
        emit('update_video', {
            'seria': room.current_series,
            'quality': room.quality,
            'play_time': room.play_time,
            'video_url': video_url},
             to=request.sid)

@socketio.on('broadcast')
def handle_broadcast(data):
    rid = data.get('room')
    if not rid or not watch_manager.is_room(rid):
        return

    event_type = data.get('type')
    value = data.get('value')

    if event_type in ('pause', 'seek'):
        watch_manager.update_play_time(rid, value)

    watch_manager.room_used(rid)
    # Рассылаем всем в комнате
    socketio.emit('broadcast', data, to=rid)


# -------------------- Остальные маршруты --------------------
@app.route('/fast_download_act/<string:id_type>-<string:id>-<int:seria_num>-<string:translation_id>-<string:quality>/')
@app.route('/fast_download_act/<string:id_type>-<string:id>-<int:seria_num>-<string:translation_id>-<string:quality>-<int:max_series>/')
def fast_download_work(id_type: str, id: str, seria_num: int, translation_id: str, quality: str, max_series: int = 12):
    from fast_download import fast_download, get_path
    translation = translations[translation_id] if translation_id in translations else "Неизвестно"
    add_zeros = len(str(max_series))
    if config.USE_SAVED_DATA and ch.is_id('sh'+id):
        if seria_num != 0:
            fname = str(ch.get_data_by_id('sh'+id)['title'])+'-'+f'Серия-{str(seria_num).zfill(add_zeros)}-Перевод-{translation}-{quality}p'
        else:
            fname = str(ch.get_data_by_id('sh'+id)['title'])+'-'+f'Перевод-{translation}-{quality}p'
        metadata = {
            'title': ch.get_data_by_id('sh'+id)['title']+' - Серия-'+str(seria_num) if seria_num != 0 else ch.get_data_by_id('sh'+id)['title'],
            'year': ch.get_data_by_id('sh'+id)['year'],
            'date': ch.get_data_by_id('sh'+id)['year'],
            'comment': ch.get_data_by_id('sh'+id)['description'],
            'artist': translation,
            'track': seria_num
        }
    else:
        metadata = {}
        fname = f'Перевод-{translation}-{quality}p' if seria_num == 0 else f'Серия-{str(seria_num).zfill(add_zeros)}-Перевод-{translation}-{quality}p'
    if len(fname) > 128:
        if len(translation) > 100:
            fname = f'{quality}p' if seria_num == 0 else f'Серия-{str(seria_num).zfill(add_zeros)}-{quality}p'
        else:
            fname = f'Перевод-{translation}-{quality}p' if seria_num == 0 else f'Серия-{str(seria_num).zfill(add_zeros)}-Перевод-{translation}-{quality}p'
    fname = fname.replace('\\','-').replace('/', '-').replace(':', '-').replace('*','-').replace('"', '\'') \
        .replace('»', '\'').replace('«', '\'').replace('„', '\'').replace('“', '\'').replace('<', '[') \
        .replace(']', ')').replace('|', '-').replace('--', '-').replace('--', '-')
    try:
        hsh, link = fast_download(id, id_type, seria_num, translation_id, quality, config.KODIK_TOKEN,
                            filename=fname, metadata=metadata)
        if ch_save:
            try:
                ch.add_seria("kp"+id, translation_id, seria_num, link)
            except KeyError:
                pass
        return send_file(get_path(hsh), as_attachment=True)
    except ModuleNotFoundError:
        return abort(500, 'Внимание, на сервере не установлен ffmpeg или программа не может получить к нему доступ. Ffmpeg обязателен для использования быстрой загрузки. (Стандартная загрузка работает без ffmpeg)')
    except FileNotFoundError:
        return abort(404, 'Видеофайл не найден, попробуйте сменить качество')

@app.route('/fast_download/<string:id_type>-<string:id>-<int:seria_num>-<string:translation_id>-<string:quality>/')
@app.route('/fast_download/<string:id_type>-<string:id>-<int:seria_num>-<string:translation_id>-<string:quality>-<int:max_series>/')
def fast_download_prepare(id_type: str, id: str, seria_num: int, translation_id: str, quality: str, max_series: int = 12):
    return render_template('fast_download_prepare.html', seria_num=seria_num,
                           url=f'/fast_download_act/{id_type}-{id}-{seria_num}-{translation_id}-{quality}-{max_series}/',
                           past_url=request.referrer if request.referrer else f'/download/{id_type}/{id}/',
                           is_dark=session['is_dark'] if "is_dark" in session.keys() else False, is_mobile=g.is_mobile)

@app.route('/help/')
def help():
    return redirect("https://github.com/YaNesyTortiK/Kodik-Download-Watch/blob/main/README.MD")

@app.route('/resources/<string:path>')
def resources(path: str):
    if os.path.exists(f'resources\\{path}'):
        return send_file(f'resources\\{path}')
    elif os.path.exists(f'resources/{path}'):
        return send_file(f'resources/{path}')
    else:
        return abort(404)

@app.route('/favicon.ico')
def favicon():
    return send_file(config.FAVICON_PATH)


if __name__ == '__main__':
    socketio.run(app, host=config.HOST, port=config.PORT, debug=config.DEBUG, allow_unsafe_werkzeug=True)