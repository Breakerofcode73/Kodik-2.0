/**
 * Kodik-2.0 — Основные клиентские скрипты
 * Версия: 2.0
 */

// Глобальные утилиты
const Utils = {
    /**
     * Показывает уведомление о статусе синхронизации
     */
    showSyncStatus: function(message, type = 'syncing', duration = 2000) {
        let status = document.getElementById('syncStatus');
        if (!status) {
            status = document.createElement('div');
            status.id = 'syncStatus';
            status.className = 'sync-status';
            document.body.appendChild(status);
        }

        status.textContent = message;
        status.className = `sync-status ${type} visible`;

        setTimeout(() => {
            status.classList.remove('visible');
        }, duration);
    },

    /**
     * Копирует текст в буфер обмена
     */
    copyToClipboard: async function(text) {
        try {
            await navigator.clipboard.writeText(text);
            return true;
        } catch (err) {
            // Fallback для старых браузеров
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.position = 'fixed';
            textarea.style.left = '-9999px';
            document.body.appendChild(textarea);
            textarea.focus();
            textarea.select();
            try {
                document.execCommand('copy');
                document.body.removeChild(textarea);
                return true;
            } catch (e) {
                document.body.removeChild(textarea);
                return false;
            }
        }
    },

    /**
     * Форматирует время в мм:сс
     */
    formatTime: function(seconds) {
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    },

    /**
     * Генерирует уникальный ID пользователя
     */
    generateUserId: function() {
        return 'user_' + Math.random().toString(36).substr(2, 9);
    }
};

// Инициализация при загрузке
document.addEventListener('DOMContentLoaded', function() {
    // Обработка кликов по ссылкам с подтверждением
    document.querySelectorAll('a[data-confirm]').forEach(link => {
        link.addEventListener('click', function(e) {
            if (!confirm(this.dataset.confirm)) {
                e.preventDefault();
            }
        });
    });

    // Авто-скрытие уведомлений
    document.querySelectorAll('.alert.auto-hide').forEach(alert => {
        setTimeout(() => {
            alert.style.opacity = '0';
            setTimeout(() => alert.remove(), 300);
        }, 5000);
    });

    // Улучшение форм
    document.querySelectorAll('input[autofocus]').forEach(input => {
        // Фокус с небольшой задержкой для надёжности
        setTimeout(() => input.focus(), 100);
    });

    // Обработка горячих клавиш на странице поиска
    if (document.querySelector('.search-input')) {
        document.addEventListener('keydown', function(e) {
            // Ctrl+K или / для фокуса на поиске
            if ((e.ctrlKey && e.key === 'k') || e.key === '/') {
                e.preventDefault();
                document.querySelector('.search-input').focus();
            }
        });
    }

    console.log('🎬 Kodik-2.0 loaded');
});

// Функция для копирования ссылки на комнату
function copyShareUrl() {
    const input = document.getElementById('shareUrl');
    if (input) {
        Utils.copyToClipboard(input.value).then(success => {
            if (success) {
                Utils.showSyncStatus('Ссылка скопирована!', 'synced');
            } else {
                Utils.showSyncStatus('Не удалось скопировать', 'error');
            }
        });
    }
}
