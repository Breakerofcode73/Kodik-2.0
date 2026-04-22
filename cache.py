# Kodik-2.0/cache.py
# Модуль кеширования данных с обработкой ошибок

from json import load, dump, JSONDecodeError
from time import time
import os


class Cache:
    """
    Класс для кеширования данных аниме.

    Структура данных:
    {
        "title": "Название аниме",
        "image": "https://example.com/image.jpg",
        "score": "7.25",
        "status": "онгоинг",
        "date": "c 5 декабря 2023 г",
        "year": "2023",
        "type": "ТВ сериал",
        "rating": "PG",
        "description": "Описание",
        "last_updated": 123456789.0168159,
        "related": [...],
        "serial_data": {
            "translations": [...],
            "series_count": 24
        },
        "urls": {
            "610": {
                1: "//example.com/video/"
            }
        }
    }
    """

    def __init__(self, SAVED_DATA_FILE: str, SAVING_PERIOD: int, CACHE_LIVE_TIME: int):
        self._path = SAVED_DATA_FILE
        self.data = {}

        # Попытка загрузить данные из файла с обработкой всех возможных ошибок
        try:
            self.data = self.get_data_from_file()
        except (JSONDecodeError, FileNotFoundError, PermissionError, OSError) as e:
            # Создаём новый пустой файл кеша при любой ошибке чтения
            try:
                # Убедимся, что директория существует
                dir_path = os.path.dirname(self._path)
                if dir_path and not os.path.exists(dir_path):
                    os.makedirs(dir_path, exist_ok=True)

                with open(self._path, 'w', encoding='utf-8') as f:
                    dump({}, f, ensure_ascii=False, indent=2)
                self.data = {}
                print(f"[CACHE] Created new cache file: {self._path}")
            except Exception as create_error:
                print(f"[CACHE] ERROR creating cache file: {create_error}")
                self.data = {}

        self.__t = time()
        self.period = SAVING_PERIOD * 60  # Перевод в секунды из минут
        self.life_time = CACHE_LIVE_TIME * 24 * 60 * 60  # Перевод в секунды из дней
        print(f"[CACHE] USING CACHE. SAVE_PERIOD: {self.period}s. LIFE_TIME: {self.life_time}s. FILE: {self._path}")

    def get_data_from_file(self) -> dict:
        """Возвращает данные из файла кеша."""
        if not os.path.exists(self._path):
            raise FileNotFoundError(f"Cache file not found: {self._path}")

        with open(self._path, 'r', encoding='UTF-8') as f:
            content = f.read().strip()
            if not content:
                return {}
            return load(f)

    def save_data_to_file(self):
        """Сохраняет данные в файл кеша."""
        try:
            # Создаём директорию если не существует
            dir_path = os.path.dirname(self._path)
            if dir_path and not os.path.exists(dir_path):
                os.makedirs(dir_path, exist_ok=True)

            # Временный файл для атомарной записи
            temp_path = self._path + '.tmp'
            with open(temp_path, 'w', encoding='utf-8') as f:
                dump(self.data, f, ensure_ascii=False, indent=2)

            # Атомарная замена файла
            os.replace(temp_path, self._path)
            print(f"[CACHE] Data saved to \"{self._path}\"")
        except Exception as e:
            print(f"[CACHE] ERROR saving data: {e}")
            # Удаляем временный файл если он остался
            if os.path.exists(self._path + '.tmp'):
                try:
                    os.remove(self._path + '.tmp')
                except:
                    pass

    def get_data_by_id(self, id: str) -> dict:
        """Получение информации по id тайтла."""
        if id in self.data:
            return self.data[id]
        raise KeyError(f"Id not found: {id}")

    def get_seria(self, id: str, translation_id: str, seria_num: int) -> str:
        """Получение ссылки на серию."""
        if id not in self.data:
            raise KeyError(f"Id not found: {id}")
        if translation_id not in self.data[id].get('urls', {}):
            raise KeyError(f"Translation not found: {translation_id}")
        if seria_num not in self.data[id]['urls'][translation_id]:
            raise KeyError(f"Seria not found: {seria_num}")
        return self.data[id]['urls'][translation_id][seria_num]

    def add_seria(self, id: str, translation_id: str, seria_num: int, url: str):
        """Добавляет ссылку на серию в заданном качестве."""
        if id not in self.data:
            raise KeyError(f"Id not found: {id}")

        if 'urls' not in self.data[id]:
            self.data[id]['urls'] = {}
        if translation_id not in self.data[id]['urls']:
            self.data[id]['urls'][translation_id] = {}

        self.data[id]['urls'][translation_id][seria_num] = url

        if time() - self.__t > self.period:
            self.__t = time()
            self.save_data_to_file()

    def add_id(self, id: str, title: str, img_url: str, score: str, status: str,
               dates: str, year: int, ttype: str, mpaa_rating: str = 'Неизвестно',
               description: str = '', related: list = None, serial_data: dict = None):
        """Добавляет или обновляет данные тайтла в кеше."""
        if related is None:
            related = []
        if serial_data is None:
            serial_data = {}

        data = {
            "title": title,
            "image": img_url,
            "score": score,
            "status": status,
            "date": dates,
            "year": str(year),
            "type": ttype,
            "rating": mpaa_rating,
            "description": description,
            "last_updated": time(),
            "related": related,
            "serial_data": serial_data,
            "urls": {}
        }

        # Удаляем старую запись если существует
        if id in self.data:
            del self.data[id]

        self.data[id] = data

        if time() - self.__t > self.period:
            self.__t = time()
            self.save_data_to_file()

    def add_translation(self, id: str, translation_id: str):
        """Добавляет перевод для тайтла."""
        if id not in self.data:
            raise KeyError(f"Id not found: {id}")

        if 'urls' not in self.data[id]:
            self.data[id]['urls'] = {}
        self.data[id]['urls'][translation_id] = {}

        if time() - self.__t > self.period:
            self.__t = time()
            self.save_data_to_file()

    def add_serial_data(self, id: str, serial_data: dict):
        """Добавляет данные о сериях."""
        if id not in self.data:
            raise KeyError(f"Id not found: {id}")
        self.data[id]["serial_data"] = serial_data

        if time() - self.__t > self.period:
            self.__t = time()
            self.save_data_to_file()

    def add_related(self, id: str, related: list):
        """Добавляет связанные тайтлы."""
        if id not in self.data:
            raise KeyError(f"Id not found: {id}")
        self.data[id]['related'] = related

        if time() - self.__t > self.period:
            self.__t = time()
            self.save_data_to_file()

    def change_image(self, id: str, image_src: str):
        """Обновляет изображение тайтла."""
        if self.is_id(id):
            self.data[id]['image'] = image_src

    def is_id(self, id: str) -> bool:
        """Проверяет наличие id в кеше и его актуальность."""
        try:
            if id in self.data:
                if self._is_expired(self.data[id].get('last_updated', 0)):
                    del self.data[id]
                    return False
                return True
            return False
        except Exception:
            return False

    def is_translation(self, id: str, translation_id: str) -> bool:
        """Проверяет наличие перевода."""
        try:
            if id in self.data and 'urls' in self.data[id]:
                if translation_id in self.data[id]['urls']:
                    if self._is_expired(self.data[id].get('last_updated', 0)):
                        del self.data[id]
                        return False
                    return True
            return False
        except Exception:
            return False

    def is_seria(self, id: str, translation_id: str, seria_num: int) -> bool:
        """Проверяет наличие серии."""
        try:
            if (id in self.data and
                    'urls' in self.data[id] and
                    translation_id in self.data[id]['urls'] and
                    seria_num in self.data[id]['urls'][translation_id]):
                if self._is_expired(self.data[id].get('last_updated', 0)):
                    del self.data[id]
                    return False
                return True
            return False
        except Exception:
            return False

    def _is_expired(self, cache_time: float) -> bool:
        """Проверяет истёк ли срок жизни кеша."""
        return (time() - cache_time) > self.life_time if cache_time else True
