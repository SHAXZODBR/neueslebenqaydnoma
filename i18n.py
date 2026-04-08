"""Internationalization (i18n) — Strings for Russian and Uzbek."""

# Labels for Buttons
BUTTON_TODAY = "📊 Отчет за сегодня / Bugungi hisobot"
BUTTON_EXCEL = "📥 Скачать Excel / Excel yuklab olish"
BUTTON_WEEKLY = "📅 Недельная аналитика / Haftalik tahlil"
BUTTON_EXPORT_ALL = "📁 Экспорт данных / Mal'umotlarni eksport"
BUTTON_HELP = "⚙️ Помощь / Yordam"

# Bot Responses
START_MESSAGE = (
    "👋 *Бот посещаемости (Cloud)*\n\n"
    "Добавьте меня в группы, и сотрудники смогут отправлять 📸 фото + 📍 локацию "
    "для учета посещаемости.\n\n"
    "Qatnashuvni hisobga olish boti. Meni guruhlarga qo'shing, xodimlar 📸 rasm + 📍 manzillarini yuborishlari mumkin."
)

ADMIN_WELCOME = "Используйте кнопки ниже для управления / Boshqarish uchun quyidagi tugmalardan foydalaning."
USER_WELCOME = "Используйте /help для просмотра команд / Buyruqlarni ko'rish uchun /help dan foydalaning."

MEDIA_RECEIVED = "✅ {} получено и сохранено! / {} qabul qilindi va saqlandi!"
SEND_LOCATION = "📍 Если есть локация, отправьте её сейчас. / Agar manzilingiz bo'lsa, uni hozir yuboring."
LOCATION_LINKED = "📍 Локация привязана к медиа! ✅ / Manzil rasm/videoga biriktirildi!"
LOCATION_ONLY = "📍 Локация сохранена! (Медиа не найдено) / Manzil saqlandi! (Rasm topilmadi)"

GENERATE_EXPORT = "⏳ Генерация экспорта для {}... / {} uchun eksport yaratilmoqda..."
NO_DATA = "Нет данных. / Ma'lumot yo'q."

# Analytics / Reports
REPORT_TITLE = "📋 *Отчет по посещаемости на {}* / *{} uchun qatnashuv hisoboti*"
NO_WORKERS = "Нет зарегистрированных сотрудников. / Ro'yxatdan o'tgan xodimlar yo'q."
STATS_TITLE = "📊 *Статистика / Statistika*"
TOTAL_WORKERS = "👤 Всего сотрудников / Jami xodimlar"
PRESENT = "✅ Присутствуют / Qatnashganlar"
LATE = "⚠️ Опоздали / Kechikkanlar"
ABSENT = "❌ Отсутствуют / Kelmaganlar"
ABSENT_LIST_TITLE = "❌ *Отсутствующие / Kelmaganlar*"

# Statuses
STATUS_ON_TIME = "✅ Вовремя / Vaqtida"
STATUS_LATE = "⚠️ Опоздал / Kechikdi"
STATUS_PRESENT = "✅ Присутствует / Qatnashdi"
STATUS_ABSENT = "❌ Отсутствует / Kelmadi"

def get_media_received(m_type: str) -> str:
    ru = "Фото" if m_type == "photo" else "Видео"
    uz = "Rasm" if m_type == "photo" else "Video"
    return MEDIA_RECEIVED.format(ru, uz)
