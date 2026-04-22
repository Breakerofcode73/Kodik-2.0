# Kodik-2.0/getters.py
# Модуль получения данных с внешних источников

from anime_parsers_ru import KodikParser, ShikimoriParser, errors
import requests
from time import sleep, time
from typing import Optional, Union
import config

# Импорт lxml если включено в конфиге
if config.USE_LXML:
    try:
        import lxml
    except ImportError:
        print("[GETTERS] Warning: lxml not installed, falling back to default parser")

# Глобальные переменные для парсеров
kodik_parser = None
shiki_parser = None
USE_KODIK_SEARCH = False


def _init_parsers():
    """Инициализация парсеров с обработкой ошибок."""
    global kodik_parser, shiki_parser, USE_KODIK_SEARCH

    # Инициализация Kodik парсера
    if config.KODIK_TOKEN is None:
        try:
            token = KodikParser.get_token()
            kodik_parser = KodikParser(
                token=token,
                use_lxml=config.USE_LXML,
                validate_token=False
            )
            USE_KODIK_SEARCH = True
            print("[GETTERS] Kodik parser initialized with auto token")
        except Exception as e:
            print(f"[GETTERS] Warning: Kodik auto token failed: {e}")
            kodik_parser = None
            USE_KODIK_SEARCH = False
    else:
        try:
            kodik_parser = KodikParser(
                token=config.KODIK_TOKEN,
                use_lxml=config.USE_LXML,
                validate_token=True
            )
            USE_KODIK_SEARCH = True
            print("[GETTERS] Kodik parser initialized with config token")
        except Exception as e:
            print(f"[GETTERS] Error: Config token invalid: {e}")
            kodik_parser = None
            USE_KODIK_SEARCH = False

    # Инициализация Shikimori парсера
    try:
        shiki_parser = ShikimoriParser(
            use_lxml=config.USE_LXML,
            mirror=config.SHIKIMORI_MIRROR
        )
        print(f"[GETTERS] Shikimori parser initialized with mirror: {config.SHIKIMORI_MIRROR}")
    except Exception as e:
        print(f"[GETTERS] Error: Shikimori parser failed: {e}")
        shiki_parser = None


def test_shiki():
    """Проверка доступности Шикимори."""
    if not shiki_parser:
        raise Warning("Shikimori parser not initialized")

    try:
        # Тестовый запрос к известному аниме
        shiki_parser.anime_info(shiki_parser.link_by_id('z20'))
        print("[GETTERS] Shikimori connection test passed")
        return True
    except (requests.exceptions.HTTPError, requests.exceptions.SSLError,
            requests.exceptions.Timeout, requests.exceptions.ReadTimeout) as ex:
        raise Warning(
            f"Shikimori connection error.\n"
            f"Check site/mirror availability.\n"
            f"Current domain: {shiki_parser._dmn}\n"
            f"Error: {ex}"
        )
    except Exception as ex:
        raise Warning(f"Unexpected Shikimori error: {ex}")


def get_url_data(url: str, headers: dict = None, session=None) -> str:
    """Получает данные по URL."""
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        print(f"[GETTERS] URL fetch error: {e}")
        return ""


def get_serial_info(id: str, id_type: str, token: str) -> dict:
    """Получает информацию о доступных переводах."""
    if not kodik_parser:
        raise Exception("Kodik parser not initialized")

    try:
        return kodik_parser.get_info(id, id_type)
    except Exception as e:
        print(f"[GETTERS] get_serial_info error: {e}")
        return {'translations': [], 'series_count': 0}


def get_download_link(id: str, id_type: str, seria_num: int,
                      translation_id: str, token: str) -> str:
    """Получает ссылку на скачивание/просмотр серии."""
    if not kodik_parser:
        raise Exception("Kodik parser not initialized")

    try:
        result = kodik_parser.get_link(id, id_type, seria_num, translation_id)
        return result[0] if isinstance(result, (list, tuple)) else result
    except Exception as e:
        print(f"[GETTERS] get_download_link error: {e}")
        raise


def get_search_data(search_query: str, token: Optional[str], ch=None) -> tuple:
    """
    Выполняет поиск аниме.

    :return: кортеж (items, others) с результатами поиска
    """
    items = []
    others = []
    used_ids = set()

    # Определяем какой парсер использовать
    if USE_KODIK_SEARCH and kodik_parser:
        try:
            search_res = kodik_parser.search(search_query, limit=50)
        except Exception as e:
            print(f"[GETTERS] Kodik search error: {e}")
            search_res = []
    else:
        if not shiki_parser:
            return ([], [])
        search_res = shiki_parser.search(search_query)

    for item in search_res:
        try:
            # Обработка результатов с Shikimori ID
            if 'shikimori_id' in item and item['shikimori_id'] and item['shikimori_id'] not in used_ids:
                # Попытка получить данные из кеша
                if ch and ch.is_id("sh" + item['shikimori_id']):
                    ser_data = ch.get_data_by_id("sh" + item['shikimori_id'])
                else:
                    ser_data = get_shiki_data(item['shikimori_id'])
                    if ch:
                        ch.add_id(
                            "sh" + item['shikimori_id'],
                            ser_data['title'], ser_data['image'], ser_data['score'],
                            ser_data['status'], ser_data['date'], ser_data['year'],
                            ser_data['type'], ser_data['rating'], ser_data['description']
                        )

                dd = {
                    'image': ser_data['image'] if ser_data['image'] else config.IMAGE_NOT_FOUND,
                    'id': item['shikimori_id'],
                    'type': ser_data['type'],
                    'date': ser_data['date'],
                    'title': item['title'],
                    'status': ser_data['status'],
                    'year': ser_data['year'],
                    'description': ser_data['description']
                }
                items.append(dd)
                used_ids.add(item['shikimori_id'])

            # Обработка результатов с Кинопоиск ID
            elif "kinopoisk_id" in item and item['kinopoisk_id'] and item['kinopoisk_id'] not in used_ids:
                type_map = {
                    "foreign-movie": "Иностранный фильм",
                    "foreign-serial": "Иностранный сериал",
                    "russian-movie": "Русский фильм",
                    "russian-serial": "Русский сериал"
                }
                others.append({
                    "id": item['kinopoisk_id'],
                    "title": item['title'],
                    "type": type_map.get(item['type'], item['type']),
                    "date": item.get('year', 'Неизвестно')
                })
                used_ids.add(item['kinopoisk_id'])

        except Exception as e:
            print(f"[GETTERS] Search item processing error: {e}")
            continue

    # Сортируем "прочее" по дате
    others.sort(key=lambda x: str(x['date']), reverse=True)

    return (items, others)


def get_shiki_data(id: str, retries: int = 3) -> dict:
    """
    Получает подробные данные аниме с Шикимори.

    :param retries: количество попыток при ошибке
    """
    if retries <= 0:
        print(f"[GETTERS] Max retries exceeded for id: {id}")
        raise RuntimeWarning(f"Max retries exceeded. Id: {id}")

    if not shiki_parser:
        raise Exception("Shikimori parser not initialized")

    try:
        data = shiki_parser.anime_info(shiki_parser.link_by_id(id))

        # Парсинг года из даты
        dates = data.get('dates', '')
        year = 1970
        if dates and len(dates) >= 4:
            # Ищем 4-значное число (год)
            import re
            match = re.search(r'\b(19|20)\d{2}\b', dates)
            if match:
                year = int(match.group())

        return {
            'title': data.get('title', 'Неизвестно'),
            'image': data.get('picture', config.IMAGE_NOT_FOUND),
            'type': data.get('type', 'Неизвестно'),
            'date': data.get('dates', 'Неизвестно'),
            'status': data.get('status', 'Неизвестно'),
            'score': data.get('score', 'Неизвестно'),
            'rating': data.get('rating', 'Неизвестно'),
            'description': data.get('description', ''),
            'year': year
        }

    except errors.AgeRestricted:
        # Обработка возрастного ограничения
        if config.ALLOW_NSAW:
            try:
                d = shiki_parser.deep_anime_info(id, [
                    'russian', 'kind', 'rating', 'status',
                    'releasedOn { year, date }', 'score',
                    'poster { originalUrl }', 'description'
                ])

                dates = d.get('releasedOn', {}).get('date', '')
                year = d.get('releasedOn', {}).get('year', 1970) or 1970

                return {
                    'title': d.get('russian', f"18+ (ID: {id})"),
                    'image': d.get('poster', {}).get('originalUrl', config.IMAGE_AGE_RESTRICTED),
                    'type': d.get('kind', 'Неизвестно'),
                    'date': dates or 'Неизвестно',
                    'status': d.get('status', 'Неизвестно'),
                    'score': d.get('score', 'Неизвестно'),
                    'rating': d.get('rating', '18+'),
                    'description': d.get('description', 'Неизвестно'),
                    'year': year
                }
            except:
                pass

        # Возвращаем заглушку если не удалось получить данные
        return {
            'title': f"18+ (Shikimori id: {id})",
            'image': config.IMAGE_AGE_RESTRICTED,
            'type': 'Неизвестно',
            'date': 'Неизвестно',
            'status': 'Неизвестно',
            'score': 'Неизвестно',
            'rating': '18+',
            'description': 'Неизвестно',
            'year': 1970
        }

    except errors.TooManyRequests:
        # Ждём и повторяем при ограничении запросов
        sleep(0.5)
        return get_shiki_data(id, retries=retries - 1)

    except errors.NoResults:
        raise RuntimeWarning("No results found")

    except Exception as e:
        print(f"[GETTERS] get_shiki_data error: {e}")
        if retries > 1:
            sleep(0.3)
            return get_shiki_data(id, retries=retries - 1)
        raise


def get_related(id: str, id_type: str, sequel_first: bool = False) -> list:
    """Получает список связанных аниме."""
    if id_type not in ('sh', 'shikimori'):
        return []

    if not shiki_parser:
        return []

    try:
        link = shiki_parser.link_by_id(id)
        data = shiki_parser.additional_anime_info(link).get('related', [])

        res = []
        for x in data:
            if x.get('date') is None:
                x['date'] = 'Неизвестно'

            # Определяем внутреннюю ссылку
            if x.get('type') in ['Манга', 'Ранобэ', 'Клип']:
                x['internal_link'] = x.get('url', '#')
            else:
                sid = shiki_parser.id_by_link(x.get('url', ''))
                x['internal_link'] = f'/download/sh/{sid}/' if sid else x.get('url', '#')

            res.append(x)

        # Сортировка: сначала продолжения, потом предыстории
        if sequel_first:
            priority = {'Продолжение': 0, 'Предыстория': 1}
            res.sort(key=lambda x: priority.get(x.get('relation'), 2))

        return res

    except Exception as e:
        print(f"[GETTERS] get_related error: {e}")
        return []


def is_good_quality_image(src: str) -> bool:
    """Проверяет является ли изображение высокого качества."""
    if not src:
        return False
    return "preview" not in src.lower()


# Инициализация парсеров при импорте модуля
_init_parsers()
