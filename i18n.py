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
STATUS_ON_TIME = "✅ Вовремя"
STATUS_LATE = "⚠️ Опоздал"
STATUS_PRESENT = "✅ Присутствует"
STATUS_ABSENT = "❌ Отсутствует"

# Check-in Details
FIRST = "первый"
LAST = "последний"
DAYS_PRESENT = "{}/7 дней"

# Extended RU Strings
HELP_TEXT = (
    "📋 *Команды администратора:*\n\n"
    "  /export `[ГГГГ-ММ-ДД]` — Экспорт в Excel за дату\n"
    "  /summary `[ГГГГ-ММ-ДД]` — Текстовый отчет за день\n"
    "  /weekly — Недельная статистика\n"
    "  /set\\_channel `ID` — Установить канал для отчетов\n"
    "  /refresh\\_summary — Отправить отчет сейчас\n"
    "  /myid — Узнать свой Telegram ID\n"
    "  /workers — Список сотрудников\n"
    "  /groups — Список групп\n"
)

MY_ID = "Ваш ID: `{}`"
ADMIN_REGISTERED = "✅ Вы зарегистрированы как администратор! ID: `{}`"
NEW_GROUP_MEMBER = "👋 Здравствуйте! Здесь сотрудники могут отмечаться, отправляя фото и локацию."
GENERATING_FULL_EXPORT = "⏳ Генерация полного экспорта всех данных..."
EXCEL_SHEET_CHECKINS = "Все чекины"
EXCEL_SHEET_SUMMARY = "Дневной отчет"

def get_media_received(m_type: str) -> str:
    if m_type == "photo":
        ru = "Фото"
    elif m_type == "video_note":
        ru = "Видео-сообщение (кружок)"
    else:
        ru = "Видео"
    return MEDIA_RECEIVED.format(ru)
