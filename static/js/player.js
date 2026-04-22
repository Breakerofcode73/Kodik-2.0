/**
 * Kodik-2.0 — Логика видео плеера
 * Версия: 2.0
 */

class VideoPlayer {
    constructor(videoElement, config = {}) {
        this.video = videoElement;
        this.config = {
            syncThreshold: 2.0, // Допустимая рассинхронизация в секундах
            heartbeatInterval: 5000, // Интервал проверки синхронизации
            ...config
        };

        this.isInitialized = false;
        this.heartbeatTimer = null;
        this.lastSyncTime = 0;

        this.init();
    }

    init() {
        if (this.isInitialized) return;

        // Обработчики событий видео
        this.video.addEventListener('play', () => this.onPlay());
        this.video.addEventListener('pause', () => this.onPause());
        this.video.addEventListener('seeked', () => this.onSeek());
        this.video.addEventListener('timeupdate', () => this.onTimeUpdate());
        this.video.addEventListener('error', (e) => this.onError(e));
        this.video.addEventListener('loadedmetadata', () => this.onLoaded());

        // Горячие клавиши
        document.addEventListener('keydown', (e) => this.handleKeydown(e));

        // Установка начального времени если указано
        const startTime = this.video.dataset.startTime;
        if (startTime && !isNaN(parseFloat(startTime))) {
            this.video.currentTime = parseFloat(startTime);
        }

        this.isInitialized = true;
        console.log('🎬 VideoPlayer initialized');
    }

    onLoaded() {
        // Скрыть оверлей загрузки
        const overlay = document.getElementById('videoOverlay');
        if (overlay) {
            overlay.style.display = 'none';
        }
    }

    onError(e) {
        console.error('Video error:', e);
        const overlay = document.getElementById('videoOverlay');
        if (overlay) {
            overlay.innerHTML = '<p style="color:#ff3b30">❌ Ошибка загрузки видео. Попробуйте сменить качество.</p>';
        }
    }

    onPlay() {
        this.broadcast('play', this.video.currentTime);
        this.startHeartbeat();
    }

    onPause() {
        this.broadcast('pause', this.video.currentTime);
        this.stopHeartbeat();
    }

    onSeek() {
        this.broadcast('seek', this.video.currentTime);
    }

    onTimeUpdate() {
        // Обновляем UI времени если есть
        const timeDisplay = document.getElementById('currentTime');
        if (timeDisplay) {
            timeDisplay.textContent = Utils.formatTime(this.video.currentTime);
        }
    }

    /**
     * Обработка горячих клавиш
     */
    handleKeydown(e) {
        // Игнорируем если фокус в поле ввода
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
            return;
        }

        switch (e.key.toLowerCase()) {
            case ' ':
            case 'k':
                e.preventDefault();
                this.togglePlay();
                break;
            case 'f':
                e.preventDefault();
                this.toggleFullscreen();
                break;
            case 'm':
                e.preventDefault();
                this.toggleMute();
                break;
            case 'a':
            case 'arrowleft':
                e.preventDefault();
                this.seek(-80);
                break;
            case 'd':
            case 'arrowright':
                e.preventDefault();
                this.seek(80);
                break;
            case 'j':
                e.preventDefault();
                this.navigateSeries(-1);
                break;
            case 'l':
                e.preventDefault();
                this.navigateSeries(1);
                break;
        }
    }

    /**
     * Переключение воспроизведения
     */
    togglePlay() {
        if (this.video.paused) {
            this.video.play().catch(e => console.error('Play failed:', e));
        } else {
            this.video.pause();
        }
    }

    /**
     * Перемотка
     */
    seek(seconds) {
        const newTime = Math.max(0, Math.min(this.video.duration, this.video.currentTime + seconds));
        this.video.currentTime = newTime;
    }

    /**
     * Переключение полноэкранного режима
     */
    toggleFullscreen() {
        if (document.fullscreenElement) {
            document.exitFullscreen();
        } else {
            this.video.requestFullscreen?.();
        }
    }

    /**
     * Переключение звука
     */
    toggleMute() {
        this.video.muted = !this.video.muted;
    }

    /**
     * Навигация по сериям
     */
    navigateSeries(direction) {
        const data = window.PLAYER_DATA;
        if (!data) return;

        const newSeria = data.curSer + direction;
        if (newSeria >= 1 && newSeria <= data.maxSer) {
            // Формируем новый URL
            const parts = data.data.split('-');
            const newUrl = `/watch/${data.serv}/${data.id}/${parts[0]}-${parts[1]}/${newSeria}/${data.curQuality}/`;
            window.location.href = newUrl;
        }
    }

    /**
     * Рассылка событий (для совместного просмотра)
     */
    broadcast(action, time) {
        if (!window.socket || !window.ROOM_DATA) return;

        window.socket.emit('playback_action', {
            rid: window.ROOM_DATA.roomId,
            action: action,
            time: time,
            user_id: window.ROOM_DATA.userId
        });
    }

    /**
     * Запуск периодической проверки синхронизации
     */
    startHeartbeat() {
        if (this.heartbeatTimer) return;

        this.heartbeatTimer = setInterval(() => {
            if (window.socket && window.ROOM_DATA) {
                window.socket.emit('heartbeat', {
                    rid: window.ROOM_DATA.roomId,
                    user_id: window.ROOM_DATA.userId,
                    time: this.video.currentTime,
                    playing: !this.video.paused
                });
            }
        }, this.config.heartbeatInterval);
    }

    /**
     * Остановка проверки синхронизации
     */
    stopHeartbeat() {
        if (this.heartbeatTimer) {
            clearInterval(this.heartbeatTimer);
            this.heartbeatTimer = null;
        }
    }

    /**
     * Принудительная синхронизация
     */
    forceSync(data) {
        console.log('🔄 Force sync:', data);

        // Показываем статус
        Utils.showSyncStatus('Синхронизация...', 'syncing');

        // Меняем серию если нужно
        if (data.seria && data.seria !== window.PLAYER_DATA?.curSer) {
            // Перенаправляем на новую серию
            const pdata = window.PLAYER_DATA;
            if (pdata) {
                const parts = pdata.data.split('-');
                const newUrl = `/watch/${pdata.serv}/${pdata.id}/${parts[0]}-${parts[1]}/${data.seria}/${pdata.curQuality}/${data.play_time}/`;
                window.location.href = newUrl;
                return;
            }
        }

        // Меняем качество если нужно
        if (data.quality && data.quality !== parseInt(window.PLAYER_DATA?.curQuality)) {
            const pdata = window.PLAYER_DATA;
            if (pdata) {
                const newUrl = `/watch/${pdata.serv}/${pdata.id}/${pdata.data}/${pdata.curSer}/q-${data.quality}/${data.play_time}/`;
                window.location.href = newUrl;
                return;
            }
        }

        // Синхронизируем время и состояние
        if (Math.abs(this.video.currentTime - data.play_time) > 0.5) {
            this.video.currentTime = data.play_time;
        }

        if (data.is_playing && this.video.paused) {
            this.video.play().catch(() => {});
        } else if (!data.is_playing && !this.video.paused) {
            this.video.pause();
        }

        // Скрываем статус через задержку
        setTimeout(() => {
            Utils.showSyncStatus('Синхронизировано ✓', 'synced');
        }, 500);
    }

    /**
     * Очистка
     */
    destroy() {
        this.stopHeartbeat();
        this.isInitialized = false;
        console.log('🎬 VideoPlayer destroyed');
    }
}

// Инициализация плеера при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    const video = document.getElementById('videoPlayer');
    if (video) {
        window.player = new VideoPlayer(video);
    }
});
