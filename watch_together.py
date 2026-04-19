import time
import threading

class Room:
    def __init__(self, rid, seria_id, quality='720p', max_series=1):
        self.rid = rid
        self.seria_id = seria_id
        self.current_series = 1
        self.max_series = max_series
        self.quality = quality
        self.play_time = 0
        self.last_update = time.time()

    def to_dict(self):
        return {
            'rid': self.rid,
            'seria_id': self.seria_id,
            'seria': self.current_series,
            'max_series': self.max_series,
            'quality': self.quality,
            'play_time': self.play_time
        }


class Manager:
    def __init__(self, remove_time=300):
        """
        remove_time : int
            Время в секундах, после которого неактивная комната удаляется.
        """
        self.rooms = {}
        self.lock = threading.Lock()
        self.remove_time = remove_time

    def create_room(self, rid, seria_id, quality='720p', max_series=1):
        with self.lock:
            if rid in self.rooms:
                return False
            self.rooms[rid] = Room(rid, seria_id, quality, max_series)
            return True

    def is_room(self, rid):
        with self.lock:
            return rid in self.rooms

    def get_room(self, rid):
        with self.lock:
            return self.rooms.get(rid)

    def get_room_data(self, rid):
        room = self.get_room(rid)
        if room:
            return room.to_dict()
        return None

    def room_used(self, rid):
        room = self.get_room(rid)
        if room:
            room.last_update = time.time()

    def update_play_time(self, rid, play_time):
        room = self.get_room(rid)
        if room:
            room.play_time = play_time
            self.room_used(rid)

    def remove_old_rooms(self):
        """Удаляет комнаты, которые не использовались дольше self.remove_time секунд."""
        with self.lock:
            now = time.time()
            to_remove = [rid for rid, room in self.rooms.items()
                         if now - room.last_update > self.remove_time]
            for rid in to_remove:
                del self.rooms[rid]