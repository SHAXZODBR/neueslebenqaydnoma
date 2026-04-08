"""Internationalization (i18n) — Strings for Russian and Uzbek."""

# Labels for Buttons (Pure Russian)
BUTTON_TODAY = "📊 Отчет за сегодня"
BUTTON_EXCEL = "📥 Скачать Excel"
BUTTON_WEEKLY = "📅 Недельная аналитика"
BUTTON_EXPORT_ALL = "📁 Экспорт всех данных"
BUTTON_HELP = "⚙️ Помощь"

# Bot Responses (Pure Russian)
START_MESSAGE = (
    "👋 *Бот посещаемости (Cloud)*\n\n"
    "Добавьте меня в группы, и сотрудники смогут отправлять 📸 фото + 📍 локацию "
    "для учета посещаемости."
)

ADMIN_WELCOME = "Используйте кнопки ниже для управления."
USER_WELCOME = "Используйте /help для просмотра команд."

MEDIA_RECEIVED = "✅ {} получено и сохранено!"
SEND_LOCATION = "📍 Если есть локация, отправьте её сейчас."
LOCATION_LINKED = "📍 Локация привязана к медиа! ✅"
LOCATION_ONLY = "📍 Локация сохранена! (Медиа не найдено)"

GENERATE_EXPORT = "⏳ Генерация экспорта для {}..."
NO_DATA = "Нет данных."

# Analytics / Reports (Bilingual RU/UZ)
REPORT_TITLE = "📋 *Отчет по посещаемости на {}* / *{} uchun qatnashuv hisoboti*"
NO_WORKERS = "Нет зарегистрированных сотрудников. / Ro'yxatdan o'tgan xodimlar yo'q."
STATS_TITLE = "📊 *Статистика / Statistika*"
TOTAL_WORKERS = "👤 Всего сотрудников / Jami xodimlar"
PRESENT = "✅ Присутствуют / Qatnashganlar"
LATE = "⚠️ Опоздали / Kechikkanlar"
ABSENT = "❌ Отсутствуют / Kelmaganlar"
ABSENT_LIST_TITLE = "❌ *Отсутствующие / Kelmaganlar*"

# Statuses (Bilingual for reports)
STATUS_ON_TIME = "✅ Вовремя / Vaqtida"
STATUS_LATE = "⚠️ Опоздал / Kechikdi"
STATUS_PRESENT = "✅ Присутствует / Qatnashdi"
STATUS_ABSENT = "❌ Отсутствует / Kelmadi"

def get_media_received(m_type: str) -> str:
    ru = "Фото" if m_type == "photo" else "Видео"
    return MEDIA_RECEIVED.format(ru)
