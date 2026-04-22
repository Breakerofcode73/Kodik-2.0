/**
 * Kodik-2.0 — Логика комнаты совместного просмотра
 * Версия: 2.0
 *
 * Особенности:
 * - Автоматическая синхронизация воспроизведения
 * - Коррекция рассинхронизации >2 сек
 * - Мгновенное обновление серии/качества у всех участников
 * - Индикация статуса синхронизации
 */

class RoomClient {
    constructor(roomData) {
        this.data = roomData;
        this.socket = null;
        this.player = null;
        this.userId = roomData.userId || Utils.generateUserId();
        this.isConnected = false;
        this.lastServerTime = 0;

        this.init();
    }

    init() {
        // Инициализация Socket.IO
        this.socket = io({
            transports: ['websocket', 'polling'],
            reconnection: true,
            reconnectionAttempts: 3,
            reconnectionDelay: 1000,
            timeout: 30000
        });

        // Обработчики событий сокетов
        this.socket.on('connect', () => this.onConnect());
        this.socket.on('disconnect', () => this.onDisconnect());
        this.socket.on('connect_error', (err) => this.onConnectError(err));

        // События комнаты
        this.socket.on('room_state', (state) => this.onRoomState(state));
        this.socket.on('sync_event', (event) => this.onSyncEvent(event));
        this.socket.on('force_sync', (data) => this.onForceSync(data));
        this.socket.on('error', (err) => this.onError(err));
        this.initSmartOverlay();
        // Ждём инициализации плеера
        const initPlayer = () => {
            const video = document.getElementById('videoPlayer');
            if (video && !this.player) {
                this.player = new VideoPlayer(video, {
                    syncThreshold: 2.0,
                    heartbeatInterval: 3000
                });
                // Переопределяем broadcast для отправки в комнату
                this.player.broadcast = (action, time) => {
                    this.sendAction(action, time);
                };

                // Присоединяемся к комнате после инициализации
                this.joinRoom();
            } else {
                setTimeout(initPlayer, 100);
            }
        };
        initPlayer();
         setTimeout(() => this.setupAudioHint(), 1000);
        // Обработчики кнопок навигации
        this.setupNavButtons();

        console.log('👥 RoomClient initialized:', this.data.roomId);
    }

    onConnect() {
        this.isConnected = true;
        console.log('🔌 Socket connected');
    }

    onDisconnect() {
        this.isConnected = false;
        console.log('🔌 Socket disconnected');
        Utils.showSyncStatus('Потеряно соединение', 'error', 3000);
    }

    onConnectError(err) {
        console.error('Connection error:', err);
        Utils.showSyncStatus('Ошибка подключения', 'error', 5000);
    }

        joinRoom() {
        if (!this.isConnected || !this.data.roomId) return;

        this.socket.emit('join_room', {
            rid: this.data.roomId,
            user_id: this.userId
        });

        console.log('🚪 Joined room:', this.data.roomId);

        // Принудительно пытаемся запустить видео сразу после подключения
        setTimeout(() => this.forcePlayIfReady(), 800);
    }

    leaveRoom() {
        if (this.socket) {
            this.socket.emit('leave_room', {
                rid: this.data.roomId,
                user_id: this.userId
            });
        }
    }

        onRoomState(state) {
        console.log('📦 Room state received:', state);

        this.updateUserCount(state.user_count);

        // Применяем состояние
        this.applyState(state);

        // Если сервер говорит "воспроизводится" → запускаем сразу
        if (state.is_playing) {
            this.forcePlayIfReady();
        }
    }

    onSyncEvent(event) {
        console.log('🔄 Sync event:', event.type, event);

        switch (event.type) {
            case 'playback_update':
                this.handlePlaybackUpdate(event);
                break;
            case 'seria_change':
                this.handleSeriaChange(event);
                break;
            case 'quality_change':
                this.handleQualityChange(event);
                break;
        }
    }

    onForceSync(data) {
        console.log('⚡ Force sync:', data);

        if (this.player) {
            this.player.forceSync(data);
        }

    }

    onError(err) {
        console.error('Room error:', err);
        Utils.showSyncStatus(err.message || 'Ошибка', 'error', 4000);
    }

    /**
     * Отправка действия в комнату
     */
    sendAction(action, time) {
        if (!this.isConnected || !this.data.roomId) return;

        this.socket.emit('playback_action', {
            rid: this.data.roomId,
            action: action,
            time: time,
            user_id: this.userId
        });
    }

    /**
     * Обработка обновления воспроизведения
     */
    handlePlaybackUpdate(event) {
        if (!this.player) return;

        // Игнорируем если это наше собственное событие
        if (event.source_user === this.userId) return;

        const video = this.player.video;

        // Синхронизируем состояние
        if (event.is_playing && video.paused) {
            video.play().catch(() => {});
        } else if (!event.is_playing && !video.paused) {
            video.pause();
        }

        // Корректируем время если рассинхронизация значительная
        const timeDiff = Math.abs(video.currentTime - event.play_time);
        if (timeDiff > 2.0) {
            video.currentTime = event.play_time;
            Utils.showSyncStatus('Синхронизация времени', 'syncing', 1500);
        }
    }

    /**
     * Обработка смены серии
     */
    handleSeriaChange(event) {
        if (event.source_user === this.userId) return;

        Utils.showSyncStatus('Смена серии...', 'syncing');

        // Перенаправляем на новую серию
        const pdata = window.PLAYER_DATA;
        if (pdata) {
            const parts = pdata.data.split('-');
            const newUrl = `/room/${this.data.roomId}/cs-${event.seria}/`;
            // Используем replace для истории браузера
            window.location.replace(newUrl);
        }
    }

    /**
     * Обработка смены качества
     */
    handleQualityChange(event) {
        if (event.source_user === this.userId) return;

        Utils.showSyncStatus('Смена качества...', 'syncing');

        const pdata = window.PLAYER_DATA;
        if (pdata) {
            const newUrl = `/room/${this.data.roomId}/cq-${event.quality}/`;
            window.location.replace(newUrl);
        }
    }

    /**
     * Применение состояния комнаты
     */
    applyState(state) {
        if (!this.player) return;

        const video = this.player.video;

        // Устанавливаем время
        if (state.play_time && state.play_time > 0) {
            video.currentTime = state.play_time;
        }

        // Устанавливаем состояние воспроизведения
        if (state.is_playing && video.paused) {
            // Небольшая задержка для надёжности
            setTimeout(() => {
                video.play().catch(() => {});
            }, 100);
        }
    }

    /**
     * Обновление счётчика участников
     */
    updateUserCount(count) {
        const el = document.getElementById('userCount');
        if (el) {
            const text = count === 1 ? '1 участник' :
                        count < 5 ? `${count} участника` :
                        `${count} участников`;
            el.textContent = text;
        }

        // Обновляем индикатор синхронизации
        const indicator = document.getElementById('syncIndicator');
        if (indicator) {
            indicator.style.display = count > 1 ? 'flex' : 'none';
        }
    }

    /**
     * Настройка кнопок навигации
     */
    setupNavButtons() {
        // Предыдущая серия
        const prevBtn = document.getElementById('prevSeriaBtn');
        if (prevBtn) {
            prevBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.sendAction('seria', this.data.seria - 1);
            });
        }

        // Следующая серия
        const nextBtn = document.getElementById('nextSeriaBtn');
        if (nextBtn) {
            nextBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.sendAction('seria', this.data.seria + 1);
            });
        }
    }

    /**
     * Очистка ресурсов
     */
    destroy() {
        this.leaveRoom();
        if (this.player) {
            this.player.destroy();
        }
        if (this.socket) {
            this.socket.disconnect();
        }
        console.log('👥 RoomClient destroyed');
    }
    forcePlayIfReady() {
        if (!this.player || !this.player.video) return;

        const video = this.player.video;

        // Если видео уже играет или загружается → выходим
        if (!video.paused || video.readyState < 2) return;

        const playPromise = video.play();

        if (playPromise !== undefined) {
            playPromise
                .then(() => {
                    console.log('🎬 Video auto-play started');
                    this.sendAction('play', video.currentTime);

                    // Показываем подсказку про звук
                    const hint = document.getElementById('audioHint');
                    if (hint) hint.classList.add('visible');
                })
                .catch(error => {
                    // Браузер заблокировал autoplay (редко, если muted)
                    console.warn('⚠️ Autoplay blocked:', error.name);
                });
        }
    }

    /**
     * Инициализация обработчика клика для включения звука
     */
    setupAudioHint() {
        const video = this.player?.video;
        const hint = document.getElementById('audioHint');
        if (!video || !hint) return;

        const enableAudio = () => {
            video.muted = false;
            hint.classList.remove('visible');
            video.removeEventListener('click', enableAudio);
            video.removeEventListener('play', enableAudio);
        };

        video.addEventListener('click', enableAudio);
        video.addEventListener('play', enableAudio);
    }
       /**
     * Умное управление оверлеем загрузки:
     - Скрыт по умолчанию
     - Появляется ТОЛЬКО при реальной буферизации (waiting/stalled)
     - Мгновенно скрывается, если видео уже загружено (canplay/loadeddata)
     */
    initSmartOverlay() {
        const video = this.player?.video;
        const overlay = document.getElementById('videoOverlay');
        const overlayText = document.getElementById('overlayText');

        if (!video || !overlay) return;

        // Гарантированно скрываем при старте
        overlay.style.display = 'none';

        // ✅ СКРЫВАТЬ: когда видео готово к воспроизведению
        const hideOverlay = () => {
            overlay.style.display = 'none';
        };
        video.addEventListener('canplay', hideOverlay);
        video.addEventListener('canplaythrough', hideOverlay);
        video.addEventListener('loadeddata', hideOverlay);
        video.addEventListener('playing', hideOverlay);
        video.addEventListener('play', hideOverlay);

        // ✅ ПОКАЗЫВАТЬ: только при реальной остановке из-за буфера
        video.addEventListener('waiting', () => {
            if (overlayText) overlayText.textContent = 'Буферизация...';
            overlay.style.display = 'flex';
        });

        // ✅ ПОКАЗЫВАТЬ: если сеть "зависла" (с задержкой 1.5с, чтобы не мелькало)
        let stalledTimeout;
        video.addEventListener('stalled', () => {
            stalledTimeout = setTimeout(() => {
                if (video.readyState < 3 && video.networkState > 1) {
                    if (overlayText) overlayText.textContent = 'Ожидание сети...';
                    overlay.style.display = 'flex';
                }
            }, 1500);
        });
        video.addEventListener('progress', () => clearTimeout(stalledTimeout));
        video.addEventListener('playing', () => clearTimeout(stalledTimeout));
        video.addEventListener('pause', hideOverlay);
    }
}

// Инициализация при загрузке
document.addEventListener('DOMContentLoaded', function() {
    if (window.ROOM_DATA) {
        window.room = new RoomClient(window.ROOM_DATA);

        // Очистка при выгрузке страницы
        window.addEventListener('beforeunload', () => {
            if (window.room) {
                window.room.destroy();
            }
        });
    }
});
