# Kodik-2.0/watch_together.py
# Модуль управления совместным просмотром с автоматической синхронизацией
# Версия: 2.1 | Исправления: автозапуск, точный синхронизатор времени, стабильность

import time
import threading
import uuid
from typing import Dict, Optional, Any


class Room:
    """
    Класс комнаты для совместного просмотра.
    Хранит состояние плеера и управляет синхронизацией.
    """

    def __init__(self, rid: str, serv: str, anime_id: str, series_count: int,
                 translation_id: str, seria: int, quality: int, is_playing: bool = True):
        self.rid = rid
        self.serv = serv
        self.anime_id = anime_id
        self.series_count = series_count
        self.translation_id = translation_id
        self.current_seria = seria
        self.quality = quality

        # Состояние воспроизведения
        self.is_playing = is_playing
        self.play_time = 0.0  # Базовое время (точка отсчета)
        self.last_update = time.time()
        self.last_action_by = None

        # Пользователи в комнате
        self.users: Dict[str, Dict[str, Any]] = {}

        # Блокировка для потокобезопасности
        self.lock = threading.RLock()

        # Флаги синхронизации
        self.force_sync = False
        self.sync_threshold = 2.0  # допустимая рассинхронизация в секундах
        self.sync_cooldown = 0.0  # защита от спама синхронизацией

    def get_live_time(self) -> float:
        """
        Возвращает расчетное текущее время воспроизведения с учетом пауз.
        """
        if self.is_playing:
            elapsed = time.time() - self.last_update
            return self.play_time + elapsed
        return self.play_time

    def to_dict(self) -> dict:
        """Возвращает состояние комнаты в виде словаря."""
        with self.lock:
            return {
                'rid': self.rid,
                'serv': self.serv,
                'id': self.anime_id,
                'series_count': self.series_count,
                'translation_id': self.translation_id,
                'seria': self.current_seria,
                'quality': self.quality,
                'is_playing': self.is_playing,
                'play_time': self.get_live_time(),  # Живое время
                'last_update': self.last_update,
                'user_count': len(self.users)
            }

    def add_user(self, user_id: str, user_data: dict = None) -> bool:
        with self.lock:
            if user_id in self.users:
                return False
            self.users[user_id] = user_data or {}
            self.last_update = time.time()
            return True

    def remove_user(self, user_id: str) -> bool:
        with self.lock:
            if user_id not in self.users:
                return False
            del self.users[user_id]
            self.last_update = time.time()
            return True

    def has_users(self) -> bool:
        with self.lock:
            return len(self.users) > 0

    def update_playback(self, is_playing: bool, play_time: float, user_id: Optional[str] = None) -> dict:
        with self.lock:
            self.is_playing = is_playing

            # Фиксируем точное время и сбрасываем таймер live-расчета
            self.play_time = max(0.0, play_time)
            self.last_update = time.time()
            self.last_action_by = user_id
            self.sync_cooldown = 0.0  # Сброс кулдауна при явном действии

            return {
                'type': 'playback_update',
                'is_playing': is_playing,
                'play_time': self.play_time,
                'seria': self.current_seria,
                'quality': self.quality,
                'timestamp': time.time(),
                'source_user': user_id
            }

    def change_seria(self, new_seria: int, user_id: Optional[str] = None) -> dict:
        with self.lock:
            if 1 <= new_seria <= self.series_count:
                self.current_seria = new_seria
                self.play_time = 0.0
                self.is_playing = True  # ✅ Автостарт при смене серии
                self.last_update = time.time()
                self.last_action_by = user_id
                self.force_sync = True
                self.sync_cooldown = 0.0

                return {
                    'type': 'seria_change',
                    'seria': new_seria,
                    'play_time': 0.0,
                    'is_playing': True,
                    'timestamp': time.time(),
                    'source_user': user_id
                }
            return None

    def change_quality(self, new_quality: int, user_id: Optional[str] = None) -> dict:
        with self.lock:
            if new_quality in (360, 480, 720, 1080):
                self.quality = new_quality
                self.last_update = time.time()
                self.last_action_by = user_id
                self.force_sync = True
                self.sync_cooldown = 0.0

                return {
                    'type': 'quality_change',
                    'quality': new_quality,
                    'timestamp': time.time(),
                    'source_user': user_id
                }
            return None

    def get_sync_data(self, current_user_time: float, current_user_playing: bool) -> Optional[dict]:
        """Проверяет необходимость синхронизации."""
        with self.lock:
            # Защита от спама: не синхронизировать чаще раза в 1 сек
            now = time.time()
            if now - self.sync_cooldown < 1.0:
                return None

            # Принудительная синхронизация (смена серии/качества)
            if self.force_sync:
                self.force_sync = False
                self.sync_cooldown = now
                return {
                    'sync': True,
                    'play_time': self.get_live_time(),
                    'is_playing': self.is_playing,
                    'seria': self.current_seria,
                    'quality': self.quality,
                    'reason': 'force'
                }

            # Проверка рассинхронизации по живому времени
            live_time = self.get_live_time()
            time_diff = abs(live_time - current_user_time)
            state_diff = self.is_playing != current_user_playing

            if time_diff > self.sync_threshold or state_diff:
                self.sync_cooldown = now
                return {
                    'sync': True,
                    'play_time': live_time,
                    'is_playing': self.is_playing,
                    'seria': self.current_seria,
                    'quality': self.quality,
                    'reason': 'drift' if time_diff > self.sync_threshold else 'state'
                }

            return None

    def mark_active(self):
        with self.lock:
            self.last_update = time.time()


class Manager:
    """Менеджер комнат совместного просмотра."""

    def __init__(self, remove_time: int = 300):
        self.rooms: Dict[str, Room] = {}
        self.lock = threading.RLock()
        self.remove_time = remove_time

        # Фоновая очистка
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()

        print(f"[WATCH_TOGETHER] Manager initialized. Remove time: {remove_time}s")

    def _cleanup_loop(self):
        while True:
            try:
                time.sleep(60)
                self.remove_old_rooms()
            except Exception as e:
                print(f"[WATCH_TOGETHER] Cleanup error: {e}")

    def new_room(self, room_data: dict) -> str:
        with self.lock:
            rid = str(uuid.uuid4())[:8]

            room = Room(
                rid=rid,
                serv=room_data.get('serv', 'sh'),
                anime_id=room_data.get('id', ''),
                series_count=room_data.get('series_count', 1),
                translation_id=room_data.get('translation_id', ''),
                seria=room_data.get('seria', 1),
                quality=room_data.get('quality', 720),
                # ✅ АВТОЗАПУСК: по умолчанию комната создается в состоянии "воспроизводится"
                is_playing=not room_data.get('pause', False)
            )

            # Если передано точное время, используем его как базу
            if 'play_time' in room_data:
                room.play_time = max(0.0, float(room_data['play_time']))
                room.last_update = time.time()  # Сброс таймера для корректного live_time

            self.rooms[rid] = room
            print(f"[WATCH_TOGETHER] Room created: {rid} | AutoPlay: {room.is_playing}")
            return rid

    def is_room(self, rid: str) -> bool:
        with self.lock:
            return rid in self.rooms

    def get_room(self, rid: str) -> Optional[Room]:
        with self.lock:
            return self.rooms.get(rid)

    def get_room_data(self, rid: str) -> Optional[dict]:
        room = self.get_room(rid)
        return room.to_dict() if room else None

    def room_used(self, rid: str):
        room = self.get_room(rid)
        if room:
            room.mark_active()

    def update_play_time(self, rid: str, play_time: float):
        room = self.get_room(rid)
        if room:
            with room.lock:
                room.play_time = play_time
                room.last_update = time.time()

    def remove_old_rooms(self):
        """Удаляет только старые пустые комнаты."""
        with self.lock:
            now = time.time()
            to_remove = []

            for rid, room in self.rooms.items():
                # ✅ Исправлено: AND вместо OR. Комната живет пока есть юзеры ИЛИ не истек таймаут
                if not room.has_users() and (now - room.last_update > self.remove_time):
                    to_remove.append(rid)

            for rid in to_remove:
                del self.rooms[rid]
                print(f"[WATCH_TOGETHER] Room removed: {rid}")

    def process_user_action(self, rid: str, action: str, value: Any, user_id: str) -> Optional[dict]:
        room = self.get_room(rid)
        if not room:
            return None

        if action == 'play':
            return room.update_playback(True, value, user_id)
        elif action == 'pause':
            return room.update_playback(False, value, user_id)
        elif action == 'seek':
            return room.update_playback(room.is_playing, value, user_id)
        elif action == 'seria':
            return room.change_seria(int(value), user_id)
        elif action == 'quality':
            return room.change_quality(int(value), user_id)

        return None

    def get_sync_event(self, rid: str, user_id: str, user_time: float, user_playing: bool) -> Optional[dict]:
        room = self.get_room(rid)
        if not room:
            return None

        return room.get_sync_data(user_time, user_playing)
