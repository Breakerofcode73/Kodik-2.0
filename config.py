# Kodik-2.0/config.py
# Конфигурация приложения

KODIK_TOKEN = None
SHIKIMORI_MIRROR = "shikimori.io"
APP_SECRET_KEY = "TvoyaMamashaSosetUKrasnoluda"  # ЗАМЕНИТЕ НА СВОЙ СЕКРЕТНЫЙ КЛЮЧ!
DEBUG = True

# Настройки кеширования
SAVE_DATA = True
USE_SAVED_DATA = True
SAVED_DATA_FILE = "cache.json"
SAVING_PERIOD = 5  # минут
CACHE_LIFE_TIME = 3  # дней

# Настройки совместного просмотра
ALLOW_WATCH_TOGETHER = True
REMOVE_TIME = 5  # минут неактивности до удаления комнаты

# Другие настройки
ALLOW_NSAW = True
IMAGE_NOT_FOUND = "/resources/no-image.png"
IMAGE_AGE_RESTRICTED = "/resources/age-restricted.png"
FAVICON_PATH = "resources/favicon.ico"
HOST = '0.0.0.0'
PORT = 5000
USE_LXML = True

# Настройки WebSocket для синхронизации
WS_SYNC_INTERVAL = 0.5  # секунд между проверками синхронизации
WS_RECONNECT_ATTEMPTS = 3  # попыток переподключения при обрыве
WS_TIMEOUT = 30  # секунд таймаута соединения
