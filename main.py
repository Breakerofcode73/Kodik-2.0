# Kodik-2.0/main.py
# Основной файл Flask приложения — ИСПРАВЛЕННАЯ ВЕРСИЯ
# Версия: 2.0.1 | Исправление: 404 на неверных URL + стабильность

# khunaruag test

from flask import Flask, render_template, request, redirect, abort, session, send_file, g, jsonify, url_for
from flask_socketio import SocketIO, send, emit, join_room, leave_room
from flask_mobility import Mobility
from getters import *
from fast_download import clear_tmp, fast_download, get_path
import watch_together
from json import load, dump, JSONDecodeError
import config
import os
import re
import threading
import sys

# ============================================================================
# Инициализация приложения
# ============================================================================

app = Flask(__name__)
Mobility(app)
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    ping_timeout=30,
    ping_interval=25,
    async_mode='threading',
    logger=True,
    engineio_logger=True
)

# Настройки приложения
token = config.KODIK_TOKEN
app.config['SECRET_KEY'] = config.APP_SECRET_KEY
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload

# ============================================================================
# Загрузка переводов
# ============================================================================

translations = {}
TRANSLATIONS_PATH = "translations.json"


def load_translations():
    """Загружает переводы с обработкой ошибок."""
    global translations
    try:
        if os.path.exists(TRANSLATIONS_PATH):
            with open(TRANSLATIONS_PATH, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    translations = load(f) if content else {}
                else:
                    # Пустой файл — создаём базовые переводы
                    translations = {"1978": "AniLibria", "610": "SovetRomantica"}
                    with open(TRANSLATIONS_PATH, 'w', encoding='utf-8') as fw:
                        dump(translations, fw, ensure_ascii=False, indent=2)
        else:
            # Файл не существует — создаём с базовыми значениями
            translations = {"1978": "AniLibria", "610": "SovetRomantica"}
            with open(TRANSLATIONS_PATH, 'w', encoding='utf-8') as f:
                dump(translations, f, ensure_ascii=False, indent=2)
            print(f"[MAIN] Created {TRANSLATIONS_PATH} with defaults")
    except (JSONDecodeError, PermissionError, OSError) as e:
        print(f"[MAIN] Warning: Could not load translations: {e}")
        translations = {"1978": "AniLibria", "610": "SovetRomantica"}


load_translations()

# ============================================================================
# Инициализация кеша
# ============================================================================

ch = None
ch_save = config.SAVE_DATA
ch_use = config.USE_SAVED_DATA


def ensure_cache_file(path: str):
    """Гарантирует существование файла кеша."""
    try:
        dir_path = os.path.dirname(path)
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)

        if not os.path.exists(path):
            with open(path, 'w', encoding='utf-8') as f:
                dump({}, f, ensure_ascii=False, indent=2)
            print(f"[MAIN] Created cache file: {path}")
            return True
        return True
    except Exception as e:
        print(f"[MAIN] ERROR creating cache: {e}")
        return False


if ch_use or ch_save:
    try:
        from cache import Cache

        # Гарантируем существование файла перед инициализацией
        if config.SAVED_DATA_FILE:
            ensure_cache_file(config.SAVED_DATA_FILE)
        ch = Cache(config.SAVED_DATA_FILE, config.SAVING_PERIOD, config.CACHE_LIFE_TIME)
        print(f"[MAIN] Cache initialized: {config.SAVED_DATA_FILE}")
    except ImportError:
        print("[MAIN] Warning: cache.py not found, caching disabled")
        ch_use = False
        ch_save = False
    except Exception as e:
        print(f"[MAIN] Warning: Cache initialization failed: {e}")
        ch_use = False
        ch_save = False

# ============================================================================
# Менеджер совместного просмотра
# ============================================================================

watch_manager = watch_together.Manager(config.REMOVE_TIME * 60 if hasattr(config, 'REMOVE_TIME') else 300)


# ============================================================================
# Инициализация при старте
# ============================================================================

def on_startup():
    """Выполняется при запуске приложения."""
    clear_tmp()

    # Проверка доступности Шикимори (не блокирующая)
    try:
        test_shiki()
        print("[MAIN] ✓ Shikimori connection OK")
    except Warning as w:
        print(f"[MAIN] ⚠ Shikimori: {w}")
    except Exception as e:
        print(f"[MAIN] ⚠ Shikimori test error: {e}")

    # Вывод зарегистрированных маршрутов в дебаг-режиме
    if getattr(config, 'DEBUG', False):
        print("\n📋 Registered routes (watch/download):")
        for rule in sorted(app.url_map.iter_rules(), key=lambda x: str(x)):
            try:
                methods = ','.join(sorted(rule.methods - {'HEAD', 'OPTIONS'}))
                rule_str = str(rule).lower()
                if methods and ('watch' in rule_str or 'download' in rule_str):
                    print(f"  [{methods:6}] {rule.rule}")
            except Exception:
                continue  # Пропускаем если ошибка
        print()


# ============================================================================
# Вспомогательные функции
# ============================================================================

def get_safe_session_value(key: str, default=None):
    """Безопасное получение значения из сессии."""
    try:
        return session.get(key, default)
    except Exception:
        return default


def get_is_dark():
    """Возвращает статус тёмной темы."""
    return get_safe_session_value('is_dark', False)


def safe_int(value, default=0):
    """Безопасное преобразование в int."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def parse_data_param(data: str) -> tuple:
    """
    Парсит параметр data вида '1:13-1978'.
    Возвращает: (series_start, series_end, translation_id)
    """
    try:
        parts = data.split('-')
        if len(parts) < 2:
            return (1, 1, parts[0] if parts else '')

        series_part = parts[0]
        translation_id = parts[1]

        if ':' in series_part:
            start, end = series_part.split(':', 1)
            return (safe_int(start, 1), safe_int(end, 1), translation_id)
        return (1, safe_int(series_part, 1), translation_id)
    except Exception:
        return (1, 1, data.split('-')[-1] if '-' in data else '1978')


# ============================================================================
# Обработчик 404 — перенаправление неверных URL
# ============================================================================

@app.errorhandler(404)
def not_found_error(error):
    """Глобальный обработчик 404 с умным перенаправлением."""
    path = request.path

    # Попытка исправить типичные ошибки в URL
    # Паттерн: /download/.../watch-<seria>/ -> /watch/.../<seria>/
    match = re.match(r'^/download/(sh|kp)/([^/]+)/(.+)/watch-(\d+)/?$', path)
    if match:
        serv, anime_id, data, seria = match.groups()
        new_url = f'/watch/{serv}/{anime_id}/{data}/{seria}/'
        print(f"[404 FIX] Redirecting: {path} -> {new_url}")
        return redirect(new_url, code=302)

    # Паттерн: /download/.../watch-<seria>/<quality>/ -> /watch/.../<seria>/<quality>/
    match = re.match(r'^/download/(sh|kp)/([^/]+)/(.+)/watch-(\d+)/(\d+)/?$', path)
    if match:
        serv, anime_id, data, seria, quality = match.groups()
        new_url = f'/watch/{serv}/{anime_id}/{data}/{seria}/{quality}/'
        print(f"[404 FIX] Redirecting: {path} -> {new_url}")
        return redirect(new_url, code=302)

    # Паттерн: /watch/... с лишними параметрами
    if '/watch/' in path and path.count('/') > 7:
        # Пытаемся извлечь базовый watch URL
        parts = path.strip('/').split('/')
        if len(parts) >= 6 and parts[1] == 'watch':
            # /watch/serv/id/data/seria[/quality][/timing]
            base_url = '/'.join(parts[:6]) + '/'
            print(f"[404 FIX] Normalizing watch URL: {path} -> {base_url}")
            return redirect(base_url, code=302)

    # Стандартная страница 404
    return render_template(
        '404.html' if os.path.exists('templates/404.html') else 'index.html',
        error_message=f"Страница не найдена: {path}",
        suggested_url="Попробуйте: / или /download/sh/54722/",
        is_dark=get_is_dark(),
        is_mobile=g.is_mobile
    ), 404


# ============================================================================
# Основные маршруты
# ============================================================================

@app.route('/')
def index():
    """Главная страница с поиском."""
    return render_template(
        'index.html',
        is_dark=get_is_dark(),
        is_kodik_search=USE_KODIK_SEARCH if 'USE_KODIK_SEARCH' in globals() else False
    )


@app.route('/', methods=['POST'])
def index_form():
    """Обработка формы поиска на главной."""
    try:
        data = dict(request.form)

        if 'shikimori_id' in data and data['shikimori_id']:
            sid = data['shikimori_id'].strip()
            return redirect(f"/download/sh/{sid}/")
        if 'kinopoisk_id' in data and data['kinopoisk_id']:
            kid = data['kinopoisk_id'].strip()
            return redirect(f"/download/kp/{kid}/")
        elif 'kdk' in data and data['kdk']:
            query = data['kdk'].strip()
            return redirect(f"/search/kdk/{query}/")
        else:
            return abort(400, "Укажите название аниме или ID")
    except Exception as e:
        print(f"[MAIN] index_form error: {e}")
        return abort(400, "Ошибка обработки запроса")


@app.route("/change_theme/", methods=['POST'])
def change_theme():
    """Переключение тёмной/светлой темы."""
    try:
        current = get_safe_session_value('is_dark', False)
        session['is_dark'] = not current
        session.modified = True
    except Exception as e:
        print(f"[MAIN] change_theme error: {e}")
    return redirect(request.referrer or '/')


@app.route('/search/<db>/<query>/')
def search_page(db, query):
    """Страница результатов поиска."""
    if db != "kdk":
        return abort(400, "Поддерживается только поиск по Kodik (kdk)")

    try:
        s_data = get_search_data(query, token, ch if (ch_save or ch_use) else None)
        return render_template(
            'search.html',
            items=s_data[0] if s_data else [],
            others=s_data[1] if s_data and len(s_data) > 1 else [],
            is_dark=get_is_dark(),
            is_mobile=g.is_mobile,
            is_kodik_search=USE_KODIK_SEARCH if 'USE_KODIK_SEARCH' in globals() else False
        )
    except Exception as e:
        print(f"[MAIN] search_page error: {e}")
        return render_template(
            'search.html',
            items=[],
            others=[],
            is_dark=get_is_dark(),
            is_mobile=g.is_mobile,
            is_kodik_search=USE_KODIK_SEARCH if 'USE_KODIK_SEARCH' in globals() else False,
            error="Ошибка при выполнении поиска"
        )


@app.route('/download/<serv>/<id>/')
def download_shiki_choose_translation(serv, id):
    """Страница выбора перевода."""
    if serv not in ('sh', 'kp'):
        return abort(400, f"Неподдерживаемый источник: {serv}. Используйте 'sh' или 'kp'")

    id_prefix = "sh" if serv == "sh" else "kp"
    id_type = "shikimori" if serv == "sh" else "kinopoisk"

    # Получение данных о переводах
    try:
        serial_data = get_serial_info(id, id_type, token)
        if not serial_data or 'translations' not in serial_data:
            serial_data = {'translations': [], 'series_count': 0}
    except Exception as ex:
        print(f"[MAIN] get_serial_info error: {ex}")
        serial_data = {'translations': [], 'series_count': 0}
        # Не прерываем — показываем страницу с ошибкой

    # Попытка получить данные из кеша
    cached_data = None
    if ch_use and ch and ch.is_id(id_prefix + id):
        try:
            cached_data = ch.get_data_by_id(id_prefix + id)
        except KeyError:
            cached_data = None

    # Заполнение данных
    if cached_data:
        name = cached_data.get('title', 'Неизвестно')
        pic = cached_data.get('image', config.IMAGE_NOT_FOUND if hasattr(config,
                                                                         'IMAGE_NOT_FOUND') else '/static/img/no-image.png')
        score = cached_data.get('score', 'Неизвестно')
        dtype = cached_data.get('type', 'Неизвестно')
        date = cached_data.get('date', 'Неизвестно')
        status = cached_data.get('status', 'Неизвестно')
        rating = cached_data.get('rating', 'Неизвестно')
        year = cached_data.get('year', 'Неизвестно')
        description = cached_data.get('description', '')
        data = None  # Для совместимости с логикой ниже
    else:
        # Получение данных с Шикимори (только для sh)
        if serv == "sh":
            try:
                data = get_shiki_data(id)
                name = data.get('title', 'Неизвестно')
                pic = data.get('image', config.IMAGE_NOT_FOUND if hasattr(config,
                                                                          'IMAGE_NOT_FOUND') else '/static/img/no-image.png')
                score = data.get('score', 'Неизвестно')
                dtype = data.get('type', 'Неизвестно')
                date = data.get('date', 'Неизвестно')
                status = data.get('status', 'Неизвестно')
                rating = data.get('rating', 'Неизвестно')
                year = data.get('year', 'Неизвестно')
                description = data.get('description', '')
            except Exception as e:
                print(f"[MAIN] get_shiki_data error: {e}")
                name, pic, score = 'Неизвестно', config.IMAGE_NOT_FOUND if hasattr(config,
                                                                                   'IMAGE_NOT_FOUND') else '/static/img/no-image.png', 'Ошибка'
                dtype = date = status = rating = year = description = 'Неизвестно'
                data = None
        else:
            # Для Кинопоиска — заглушка
            name = pic = score = dtype = date = status = rating = year = description = 'Неизвестно'
            data = None

    # Сохранение в кеш если нужно
    if ch_save and ch and name != 'Неизвестно':
        try:
            if not ch.is_id(id_prefix + id):
                ch.add_id(
                    id_prefix + id, name, pic, score,
                    data['status'] if data else "Неизвестно",
                    data['date'] if data else "Неизвестно",
                    data['year'] if data else 1970,
                    data['type'] if data else "Неизвестно",
                    data['rating'] if data else "Неизвестно",
                    data['description'] if data else '',
                    serial_data=serial_data
                )
            elif ch.get_data_by_id(id_prefix + id).get('serial_data') == {}:
                ch.add_serial_data(id_prefix + id, serial_data)
        except Exception as e:
            print(f"[MAIN] Cache save error: {e}")

    # Получение связанных тайтлов
    related = []
    if serv == "sh":
        try:
            if ch_use and ch and ch.is_id("sh" + id):
                cached_related = ch.get_data_by_id("sh" + id).get('related')
                if cached_related:
                    related = cached_related
                else:
                    related = get_related(id, 'shikimori', sequel_first=True)
                    ch.add_related("sh" + id, related)
            else:
                related = get_related(id, 'shikimori', sequel_first=True)
                if ch_save and ch:
                    ch.add_related("sh" + id, related)
        except Exception as e:
            print(f"[MAIN] get_related error: {e}")

    return render_template('info.html',
                           title=name, image=pic, score=score,
                           translations=serial_data.get('translations', []),
                           series_count=serial_data.get("series_count", 0),
                           id=id,
                           dtype=dtype, date=date, status=status, rating=rating,
                           related=related, description=description,
                           is_shiki=(serv == "sh"),
                           is_dark=get_is_dark(),
                           is_mobile=g.is_mobile,
                           shiki_mirror=getattr(config, 'SHIKIMORI_MIRROR', 'shikimori.one')
                           )


@app.route('/download/<serv>/<id>/<data>/')
def download_choose_seria(serv, id, data):
    """Страница выбора серии."""
    if data == "None" or not data:
        return abort(400, "Неверный параметр данных")

    try:
        series_start, series_end, translation_id = parse_data_param(data)
        return render_template(
            'download.html',
            series=[series_start, series_end],
            backlink=f"/download/{serv}/{id}/",
            is_dark=get_is_dark(),
            is_mobile=g.is_mobile,
            translation_id=translation_id,
            anime_id=id,
            serv=serv,
            data=data
        )
    except Exception as e:
        print(f"[MAIN] download_choose_seria error: {e}")
        return abort(400, f"Ошибка разбора данных: {e}")


@app.route('/download/<serv>/<id>/<data>/<download_type>/<quality>/<seria>/')
def redirect_to_download(serv, id, data, download_type, quality, seria):
    """Перенаправление на скачивание или просмотр."""
    try:
        series_start, series_end, translation_id = parse_data_param(data)
        seria_num = safe_int(seria, 1)
        quality_num = safe_int(quality, 720)

        # Быстрая загрузка
        if download_type == 'fast':
            return redirect(f'/fast_download/{serv}-{id}-{seria_num}-{translation_id}-{quality_num}-{series_end}/')

        # Получение ссылки на видео
        id_prefix = "sh" if serv == "sh" else "kp"
        id_type = "shikimori" if serv == "sh" else "kinopoisk"

        url = None
        # Попытка получить из кеша
        if ch_use and ch:
            try:
                if ch.is_seria(id_prefix + id, translation_id, seria_num):
                    url = ch.get_seria(id_prefix + id, translation_id, seria_num)
            except KeyError:
                pass

        if not url:
            url = get_download_link(id, id_type, seria_num, translation_id, token)
            # Сохранение в кеш
            if ch_save and ch:
                try:
                    ch.add_seria(id_prefix + id, translation_id, seria_num, url)
                except KeyError:
                    pass

        translation_name = translations.get(str(translation_id), "Неизвестно")

        # Формирование ссылки для редиректа
        if seria_num == 0:
            redirect_url = f"https:{url}{quality_num}.mp4:Перевод-{translation_name}:.mp4"
        else:
            redirect_url = f"https:{url}{quality_num}.mp4:Серия-{seria_num}:Перевод-{translation_name}:.mp4"

        return redirect(redirect_url)

    except Exception as ex:
        print(f"[MAIN] redirect_to_download error: {ex}")
        return abort(500, f'Ошибка получения видео: {ex}')


# ============================================================================
# МАРШРУТЫ ПРОСМОТРА (/watch/) — ИСПРАВЛЕНО
# ============================================================================

@app.route('/watch/<serv>/<id>/<data>/<seria>/')
@app.route('/watch/<serv>/<id>/<data>/<seria>/<quality>/')
@app.route('/watch/<serv>/<id>/<data>/<seria>/<quality>/<timing>/')
def watch(serv, id, data, seria, quality="720", timing="0"):
    """Страница просмотра видео — основной маршрут."""
    try:
        series_start, series_end, translation_id = parse_data_param(data)
        seria_num = safe_int(seria, 1)
        quality_num = safe_int(quality, 720)
        timing_float = float(timing) if timing and timing != "0" else 0.0

        id_prefix = "sh" if serv == "sh" else "kp"
        id_type = "shikimori" if serv == "sh" else "kinopoisk"

        # Получение ссылки на видео
        url = None
        if ch_use and ch:
            try:
                if ch.is_seria(id_prefix + id, translation_id, seria_num):
                    url = ch.get_seria(id_prefix + id, translation_id, seria_num)
            except KeyError:
                pass

        if not url:
            url = get_download_link(id, id_type, seria_num, translation_id, token)
            if ch_save and ch:
                try:
                    if not ch.is_seria(id_prefix + id, translation_id, seria_num):
                        ch.add_seria(id_prefix + id, translation_id, seria_num, url)
                except KeyError:
                    pass

        # Получение названия из кеша для отображения
        title = None
        if ch_use and ch:
            try:
                if ch.is_id(id_prefix + id):
                    title = ch.get_data_by_id(id_prefix + id).get('title')
            except KeyError:
                pass

        straight_url = f"https:{url}{quality_num}.mp4"
        download_url = f"/download/{serv}/{id}/{data}/old-{quality_num}-{seria_num}"

        return render_template('watch.html',
                               url=download_url,
                               seria=seria_num,
                               series=[series_start, series_end],
                               id=id,
                               id_type=id_type,
                               data=data,
                               quality=quality_num,
                               serv=serv,
                               straight_url=straight_url,
                               allow_watch_together=getattr(config, 'ALLOW_WATCH_TOGETHER', True),
                               is_dark=get_is_dark(),
                               timing=timing_float,
                               title=title,
                               is_mobile=g.is_mobile,
                               translation_id=translation_id
                               )

    except Exception as e:
        print(f"[MAIN] watch error: {e}")
        # Пробуем перенаправить на страницу выбора перевода как запасной вариант
        return redirect(f"/download/{serv}/{id}/")


@app.route('/watch/<serv>/<id>/<data>/<seria>/', methods=['POST'])
def change_seria_form(serv, id, data, seria):
    """Обработка смены серии через форму."""
    try:
        form_data = dict(request.form)
        new_seria = safe_int(form_data.get('seria', seria), 1)
        series_start, series_end, _ = parse_data_param(data)

        if new_seria < series_start or new_seria > series_end:
            return abort(400, f"Серия должна быть от {series_start} до {series_end}")

        return redirect(f"/watch/{serv}/{id}/{data}/{new_seria}/")
    except Exception as e:
        print(f"[MAIN] change_seria_form error: {e}")
        return abort(400, "Ошибка смены серии")


# ============================================================================
# ПЕРЕХОДНИК: ловим старые/неверные URL и перенаправляем
# ============================================================================

@app.route('/download/<serv>/<id>/<data>/watch-<seria>/')
@app.route('/download/<serv>/<id>/<data>/watch-<seria>/<quality>/')
@app.route('/download/<serv>/<id>/<data>/watch-<seria>/<quality>/<timing>/')
def watch_legacy_redirect(serv, id, data, seria, quality="720", timing="0"):
    """
    Перехватывает URL вида /download/.../watch-1/ и перенаправляет на /watch/...
    Решает проблему 404 для устаревших ссылок.
    """
    try:
        seria_num = safe_int(seria, 1)
        quality_num = safe_int(quality, 720)
        timing_val = timing if timing and timing != "0" else "0"

        new_url = f"/watch/{serv}/{id}/{data}/{seria_num}/{quality_num}/{timing_val}/"
        print(f"[LEGACY REDIRECT] {request.path} -> {new_url}")
        return redirect(new_url, code=302)
    except Exception as e:
        print(f"[LEGACY REDIRECT] error: {e}")
        return redirect(f"/download/{serv}/{id}/")


# ============================================================================
# Совместный просмотр - маршруты
# ============================================================================

@app.route('/create_room/', methods=['POST'])
def create_room():
    """Создание комнаты для совместного просмотра."""
    try:
        orig = request.referrer
        if not orig:
            return abort(400, "Не удалось определить источник")

        # Парсинг URL для извлечения параметров
        parts = [p for p in orig.rstrip('/').split("/") if p]
        if len(parts) < 6:
            return abort(400, "Неверный формат ссылки")

        # Ищем watch URL в реферере
        watch_idx = -1
        for i, p in enumerate(parts):
            if p == 'watch':
                watch_idx = i
                break

        if watch_idx == -1 or watch_idx + 4 >= len(parts):
            # Пробуем распарсить как download URL
            if parts[-4] and '-' in parts[-4]:
                data_parts = parts[-4].split('-')
                series_info = data_parts[0].split(':') if ':' in data_parts[0] else ['1', '1']
            else:
                return abort(400, "Не удалось извлечь данные видео")
        else:
            data_parts = parts[watch_idx + 3].split('-')
            series_info = data_parts[0].split(':') if ':' in data_parts[0] else ['1', '1']

        room_data = {
            'serv': parts[watch_idx + 1] if watch_idx != -1 else parts[-6] if len(parts) >= 6 else 'sh',
            'id': parts[watch_idx + 2] if watch_idx != -1 else parts[-5] if len(parts) >= 5 else '',
            'series_count': safe_int(series_info[1], 1) if len(series_info) > 1 else 1,
            'translation_id': data_parts[1] if len(data_parts) > 1 else '1978',
            'seria': safe_int(parts[watch_idx + 4] if watch_idx != -1 else parts[-3], 1),
            'quality': 720,
            'pause': False,
            'play_time': 0.0,
        }

        rid = watch_manager.new_room(room_data)
        watch_manager.remove_old_rooms()

        return redirect(f"/room/{rid}/")

    except Exception as e:
        print(f"[MAIN] create_room error: {e}")
        return abort(500, f"Ошибка создания комнаты: {e}")


@app.route('/room/<rid>/')
def room(rid):
    """Страница комнаты совместного просмотра."""
    if not watch_manager.is_room(rid):
        return abort(404, "Комната не найдена или истекла")

    try:
        rd = watch_manager.get_room_data(rid)
        if not rd:
            return abort(404, "Данные комнаты недоступны")

        watch_manager.room_used(rid)

        id_prefix = "sh" if rd['serv'] == "sh" else "kp"
        id_type = "shikimori" if rd['serv'] == "sh" else "kinopoisk"

        # Получение ссылки на видео
        url = None
        if ch_use and ch:
            try:
                if ch.is_seria(id_prefix + rd['id'], str(rd['translation_id']), rd['seria']):
                    url = ch.get_seria(id_prefix + rd['id'], str(rd['translation_id']), rd['seria'])
            except KeyError:
                pass

        if not url:
            url = get_download_link(rd['id'], id_type, rd['seria'], str(rd['translation_id']), token)
            if ch_save and ch:
                try:
                    ch.add_seria(id_prefix + rd['id'], str(rd['translation_id']), rd['seria'], url)
                except:
                    pass

        straight_url = f"https:{url}{rd['quality']}.mp4"
        data_param = f"{rd['series_count']}-{rd['translation_id']}"
        download_url = f"/download/{rd['serv']}/{rd['id']}/{data_param}/old-{rd['quality']}-{rd['seria']}"

        return render_template('room.html',
                               url=download_url,
                               seria=rd['seria'],
                               series=rd['series_count'],
                               id=rd['id'],
                               id_type=id_type,
                               data=data_param,
                               quality=rd['quality'],
                               serv=rd['serv'],
                               straight_url=straight_url,
                               start_time=rd['play_time'],
                               is_dark=get_is_dark(),
                               is_mobile=g.is_mobile,
                               room_id=rid,
                               translation_id=rd['translation_id']
                               )

    except Exception as e:
        print(f"[MAIN] room error: {e}")
        return abort(500, f"Ошибка загрузки комнаты: {e}")


@app.route('/room/<rid>/', methods=['POST'])
def change_room_seria_form(rid):
    """Смена серии в комнате через форму."""
    try:
        seria = safe_int(dict(request.form).get('seria', 1), 1)
        if watch_manager.is_room(rid):
            event = watch_manager.process_user_action(rid, 'seria', seria, 'form')
            if event:
                socketio.emit('sync_event', event, room=rid)
        return redirect(f"/room/{rid}/")
    except Exception as e:
        print(f"[MAIN] change_room_seria_form error: {e}")
        return redirect(f"/room/{rid}/")


@app.route('/room/<rid>/cs-<int:seria>/')
def change_room_seria(rid, seria):
    """Смена серии в комнате через URL."""
    if watch_manager.is_room(rid):
        event = watch_manager.process_user_action(rid, 'seria', seria, 'url')
        if event:
            socketio.emit('sync_event', event, room=rid)
    return redirect(f"/room/{rid}/")


@app.route('/room/<rid>/cq-<int:quality>/')
def change_room_quality(rid, quality):
    """Смена качества в комнате."""
    if watch_manager.is_room(rid):
        event = watch_manager.process_user_action(rid, 'quality', quality, 'url')
        if event:
            socketio.emit('sync_event', event, room=rid)
    return redirect(f"/room/{rid}/")


# ============================================================================
# Быстрая загрузка
# ============================================================================

@app.route('/fast_download_act/<id_type>-<id>-<seria_num>-<translation_id>-<quality>-<max_series>/')
@app.route('/fast_download_act/<id_type>-<id>-<seria_num>-<translation_id>-<quality>-<max_series>-<extra>/')
def fast_download_work(id_type: str, id: str, seria_num: int, translation_id: str,
                       quality: str, max_series: int = 12, extra: str = None):
    """Обработка быстрой загрузки."""
    try:
        translation = translations.get(str(translation_id), "Неизвестно")
        add_zeros = len(str(max_series))

        # Формирование имени файла
        if seria_num != 0:
            fname = f'Серия-{str(seria_num).zfill(add_zeros)}-Перевод-{translation}-{quality}p'
        else:
            fname = f'Перевод-{translation}-{quality}p'

        # Ограничение длины имени файла
        if len(fname) > 128:
            fname = f'{quality}p' if seria_num == 0 else f'Серия-{str(seria_num).zfill(add_zeros)}-{quality}p'

        # Очистка имени от запрещённых символов
        fname = re.sub(r'[\\/:*?"<>|]', '-', fname)
        fname = re.sub(r'-+', '-', fname).strip('-')

        # Метаданные для встраивания
        metadata = {}
        if ch_use and ch:
            try:
                if ch.is_id('sh' + id):
                    cd = ch.get_data_by_id('sh' + id)
                    metadata = {
                        'title': cd.get('title', '') + (f' - Серия-{seria_num}' if seria_num != 0 else ''),
                        'year': str(cd.get('year', '')),
                        'comment': cd.get('description', ''),
                        'artist': translation,
                        'track': seria_num
                    }
            except KeyError:
                pass

        hsh, link = fast_download(
            id, id_type, seria_num, translation_id, quality, getattr(config, 'KODIK_TOKEN', None),
            filename=fname, metadata=metadata
        )

        # Сохранение ссылки в кеш
        if ch_save and ch:
            try:
                id_prefix = "kp" if id_type == "kinopoisk" else "sh"
                ch.add_seria(id_prefix + id, translation_id, seria_num, link)
            except:
                pass

        file_path = get_path(hsh)
        if not os.path.exists(file_path):
            return abort(404, "Файл не найден на сервере")

        return send_file(file_path, as_attachment=True, download_name=f"{fname}.mp4")

    except ModuleNotFoundError as e:
        print(f"[MAIN] fast_download ModuleNotFoundError: {e}")
        return abort(500, 'FFmpeg не установлен или модуль недоступен')
    except FileNotFoundError as e:
        print(f"[MAIN] fast_download FileNotFoundError: {e}")
        return abort(404, 'Видео не найдено, попробуйте другое качество')
    except Exception as e:
        print(f"[MAIN] fast_download_work error: {e}")
        return abort(500, f'Ошибка обработки: {e}')


@app.route('/fast_download/<id_type>-<id>-<seria_num>-<translation_id>-<quality>-<max_series>/')
@app.route('/fast_download/<id_type>-<id>-<seria_num>-<translation_id>-<quality>-<max_series>-<extra>/')
def fast_download_prepare(id_type: str, id: str, seria_num: int, translation_id: str,
                          quality: str, max_series: int = 12, extra: str = None):
    """Страница подготовки быстрой загрузки."""
    return render_template(
        'fast_download_prepare.html',
        seria_num=seria_num,
        url=f'/fast_download_act/{id_type}-{id}-{seria_num}-{translation_id}-{quality}-{max_series}/',
        past_url=request.referrer or f'/download/{id_type}/{id}/',
        is_dark=get_is_dark(),
        is_mobile=g.is_mobile
    )


# ============================================================================
# WebSocket обработчики для синхронизации
# ============================================================================

@socketio.on('connect')
def on_connect():
    """Обработчик подключения клиента."""
    print(f"[WS] ✓ Client connected: {request.sid}")


@socketio.on('disconnect')
def on_disconnect():
    """Обработчик отключения клиента."""
    print(f"[WS] ✗ Client disconnected: {request.sid}")


@socketio.on('join_room')
def on_join_room(data):
    """Присоединение к комнате."""
    try:
        rid = data.get('rid') if isinstance(data, dict) else None
        user_id = data.get('user_id', request.sid) if isinstance(data, dict) else request.sid

        if not rid or not watch_manager.is_room(rid):
            emit('error', {'message': 'Room not found'})
            return

        room = watch_manager.get_room(rid)
        if room:
            room.add_user(user_id, {'sid': request.sid})
            join_room(rid)
            watch_manager.room_used(rid)

            rd = room.to_dict()
            emit('room_state', {
                'seria': rd['seria'],
                'quality': rd['quality'],
                'play_time': rd['play_time'],
                'is_playing': rd['is_playing'],
                'user_count': rd['user_count']
            })
            print(f"[WS] ✓ User {user_id} joined room {rid}")

    except Exception as e:
        print(f"[WS] join_room error: {e}")
        emit('error', {'message': 'Join failed'})


@socketio.on('leave_room')
def on_leave_room(data):
    """Покидание комнаты."""
    try:
        rid = data.get('rid') if isinstance(data, dict) else None
        user_id = data.get('user_id', request.sid) if isinstance(data, dict) else request.sid

        if rid and watch_manager.is_room(rid):
            room = watch_manager.get_room(rid)
            if room:
                room.remove_user(user_id)
                leave_room(rid)
                print(f"[WS] ✗ User {user_id} left room {rid}")
    except Exception as e:
        print(f"[WS] leave_room error: {e}")


@socketio.on('playback_action')
def on_playback_action(data):
    """Обработка действий воспроизведения."""
    try:
        if not isinstance(data, dict):
            return
        rid = data.get('rid')
        action = data.get('action')
        time_val = float(data.get('time', 0))
        user_id = data.get('user_id', request.sid)

        if not rid or not watch_manager.is_room(rid):
            return

        event = watch_manager.process_user_action(rid, action, time_val, user_id)
        if event:
            emit('sync_event', event, room=rid, include_self=False)
            print(f"[WS] {action} event from {user_id} in room {rid}")
    except Exception as e:
        print(f"[WS] playback_action error: {e}")


@socketio.on('seria_change')
def on_seria_change(data):
    """Обработка смены серии."""
    try:
        if not isinstance(data, dict):
            return
        rid = data.get('rid')
        seria = int(data.get('seria', 1))
        user_id = data.get('user_id', request.sid)

        if not rid or not watch_manager.is_room(rid):
            return

        event = watch_manager.process_user_action(rid, 'seria', seria, user_id)
        if event:
            emit('sync_event', event, room=rid, include_self=False)
    except Exception as e:
        print(f"[WS] seria_change error: {e}")


@socketio.on('quality_change')
def on_quality_change(data):
    """Обработка смены качества."""
    try:
        if not isinstance(data, dict):
            return
        rid = data.get('rid')
        quality = int(data.get('quality', 720))
        user_id = data.get('user_id', request.sid)

        if not rid or not watch_manager.is_room(rid):
            return

        event = watch_manager.process_user_action(rid, 'quality', quality, user_id)
        if event:
            emit('sync_event', event, room=rid, include_self=False)
    except Exception as e:
        print(f"[WS] quality_change error: {e}")


@socketio.on('heartbeat')
def on_heartbeat(data):
    """Периодический сигнал для проверки синхронизации."""
    try:
        if not isinstance(data, dict):
            return
        rid = data.get('rid')
        user_id = data.get('user_id', request.sid)
        user_time = float(data.get('time', 0))
        user_playing = data.get('playing', False)

        if rid and watch_manager.is_room(rid):
            sync_event = watch_manager.get_sync_event(rid, user_id, user_time, user_playing)
            if sync_event:
                emit('force_sync', sync_event)
    except Exception as e:
        print(f"[WS] heartbeat error: {e}")


# ============================================================================
# Служебные маршруты
# ============================================================================

@app.route('/help/')
def help_page():
    """Страница помощи."""
    return redirect("https://github.com/Breakerofcode73/Kodik-2.0/blob/master/README.MD")


@app.route('/resources/<path:path>')
def resources(path: str):
    """Раздача статических ресурсов."""
    try:
        if '..' in path or path.startswith('/') or '\\' in path:
            return abort(403, "Доступ запрещён")

        full_path = os.path.join('resources', path)
        real_path = os.path.realpath(full_path)
        real_base = os.path.realpath('resources')

        if not real_path.startswith(real_base):
            return abort(403, "Доступ запрещён")

        if os.path.exists(real_path) and os.path.isfile(real_path):
            return send_file(real_path)
        return abort(404, "Ресурс не найден")
    except Exception as e:
        print(f"[MAIN] resources error: {e}")
        return abort(404)


@app.route('/favicon.ico')
def favicon():
    """Иконка сайта."""
    try:
        favicon_path = getattr(config, 'FAVICON_PATH', 'resources/favicon.ico')
        if os.path.exists(favicon_path):
            return send_file(favicon_path, mimetype='image/x-icon')
        # Пробуем в static
        static_favicon = os.path.join('static', 'favicon.ico')
        if os.path.exists(static_favicon):
            return send_file(static_favicon, mimetype='image/x-icon')
        return abort(404)
    except:
        return abort(404)


@app.route('/api/health')
def health_check():
    """Проверка здоровья приложения."""
    return jsonify({
        'status': 'ok',
        'version': '2.0.1',
        'cache_enabled': bool(ch_use or ch_save),
        'watch_together': getattr(config, 'ALLOW_WATCH_TOGETHER', True),
        'kodik_search': globals().get('USE_KODIK_SEARCH', False),
        'routes_count': len(app.url_map.iter_rules())
    })


@app.route('/debug/routes')
def debug_routes():
    """Отладочная страница со списком маршрутов (только в DEBUG режиме)."""
    if not getattr(config, 'DEBUG', False):
        return abort(403, "Доступно только в режиме отладки")

    routes = []
    # ✅ Исправлено: используем 'rule' вместо 'r' везде
    for rule in sorted(app.url_map.iter_rules(), key=lambda x: str(x)):
        try:
            # ✅ rule — переменная цикла, она доступна здесь
            methods = ','.join(sorted(rule.methods - {'HEAD', 'OPTIONS'}))
            routes.append({
                'methods': methods,
                'rule': str(rule),
                'endpoint': rule.endpoint
            })
        except Exception:
            continue  # Пропускаем проблемные маршруты
    return jsonify(routes)


# ============================================================================
# Запуск приложения
# ============================================================================

if __name__ == '__main__':
    print(f"""
╔═══════════════════════════════════════════════════════════╗
║  🎬 Kodik-2.0 v2.0.1 — Anime Streaming Platform          ║
╠═══════════════════════════════════════════════════════════╣
║  Host: {getattr(config, 'HOST', '0.0.0.0'):<15} Port: {getattr(config, 'PORT', 5000):<5}                    ║
║  Debug: {getattr(config, 'DEBUG', True)}                                              ║
║  Cache: {'Enabled' if (ch_use or ch_save) else 'Disabled':<12} Watch Together: {'Yes' if getattr(config, 'ALLOW_WATCH_TOGETHER', True) else 'No':<3}  ║
╠═══════════════════════════════════════════════════════════╣
║  🔧 Исправления:                                          ║
║  • Перехват неверных URL (/download/.../watch-1/)        ║
║  • Авто-создание cache.json и translations.json          ║
║  • Улучшенная обработка ошибок                           ║
║  • Безопасная загрузка файлов                            ║
╚═══════════════════════════════════════════════════════════╝
    """)

    # Проверка наличия templates перед запуском
    if not os.path.isdir('templates'):
        print("⚠ WARNING: Папка 'templates' не найдена! Создайте её и добавьте HTML-шаблоны.")

    socketio.run(
        app,
        host=getattr(config, 'HOST', '0.0.0.0'),
        port=getattr(config, 'PORT', 5000),
        debug=getattr(config, 'DEBUG', True),
        allow_unsafe_werkzeug=True,
        use_reloader=getattr(config, 'DEBUG', True)
    )
