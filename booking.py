
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    filters,
)
import logging
import datetime
import re


logger = logging.getLogger(__name__)

# Состояния ConversationHandler
CHOOSE_TYPE, CHOOSE_DIRECTION, ENTER_ADDRESS_FROM, CHOOSE_POINT_TO, ENTER_DATE, ENTER_TIME, CONFIRM_BOOKING, EXTRA = range(8)

# Главное меню
main_menu = ReplyKeyboardMarkup([
    ["🚕 Забронировать поездку", "📅 Мои брони"],
    ["👤 Мой профиль", "👨‍✈️ Стать водителем"],
    ["ℹ️ Помощь / Контакты"]
], resize_keyboard=True)

# Список пунктов назначения и цен
DESTINATIONS = {
    "Метро проспект победы": 1000,
    "РКБ": 1000,
    "ДРКБ": 1100,
    "ЖД вокзал 1": 1400,
    "ЖД вокзал 2": 1500,
    "Аэропорт Казани": 1400,
    "Онкоцентр": 1300,
    "Глазной центр": 1400,
    "Бутлерова 14 и 41": 1400,
    "Баумана центр": 1400,
    "Аквапарк Ривьера": 1500,
    "Речной порт": 1400,
    "Автовокзал центр": 1400,
    "ул. Чистопольская": 1400,
    "МКДЦ": 1200,
    "Казан Молл": 1400,
    "Парк Хаус": 1500,
    "Тандем": 1500,
    "Аквапарк Брионикс": 1500,
    "Южный вокзал": 1100,
    "Восточный автовокзал": 1400,
    "Северный вокзал": 1500,
}

# Шаг 1 — выбор типа поездки
async def choose_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    selected = update.message.text.strip()
    if selected not in ["🚗 Место в машине", "🚘 Вся машина"]:
        await update.message.reply_text("🚕 Выберите способ поездки:", reply_markup=ReplyKeyboardMarkup([
            ["🚗 Место в машине", "🚘 Вся машина"]
        ], resize_keyboard=True))
        return CHOOSE_TYPE

    context.user_data['ride_type'] = selected
    await update.message.reply_text("🏙 Откуда вы едете? Введите 'Казань' или 'Нижнекамск'")
    return CHOOSE_DIRECTION

# Шаг 2 — выбор города отправления
async def choose_direction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from_city = update.message.text.strip().capitalize()
    if from_city not in ["Казань", "Нижнекамск"]:
        await update.message.reply_text("❌ Мы работаем только между Казанью и Нижнекамском.")
        return CHOOSE_DIRECTION

    to_city = "Казань" if from_city == "Нижнекамск" else "Нижнекамск"
    context.user_data['from_city'] = from_city
    context.user_data['to_city'] = to_city

    if from_city == "Нижнекамск":
        await update.message.reply_text("📍 Укажите адрес, откуда вас забрать в Нижнекамске:")
    else:
        await update.message.reply_text(
            "📍 Выберите точку отправления в Казани:",
            reply_markup=ReplyKeyboardMarkup(
                [list(DESTINATIONS.keys())[i:i+2] for i in range(0, len(DESTINATIONS), 2)],
                resize_keyboard=True
            )
        )
    return ENTER_ADDRESS_FROM

# Шаг 3 — ввод адреса отправления
async def enter_address_from(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from_city = context.user_data['from_city']

    if from_city == "Казань":
        selected_point = update.message.text.strip()
        if selected_point not in DESTINATIONS:
            await update.message.reply_text("❌ Выберите корректную точку из списка.")
            return ENTER_ADDRESS_FROM
        context.user_data['from_address'] = selected_point
        context.user_data['price'] = DESTINATIONS[selected_point]

        await update.message.reply_text("🏠 Укажите точный адрес назначения в Нижнекамске:")
    else:
        context.user_data['from_address'] = update.message.text.strip()
        await update.message.reply_text(
            "📍 Выберите точку назначения в Казани:",
            reply_markup=ReplyKeyboardMarkup(
                [list(DESTINATIONS.keys())[i:i+2] for i in range(0, len(DESTINATIONS), 2)],
                resize_keyboard=True
            )
        )
    return CHOOSE_POINT_TO

# Шаг 4 — выбор точки назначения
async def choose_point_to(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from_city = context.user_data['from_city']

    if from_city == "Нижнекамск":
        selected_point = update.message.text.strip()
        if selected_point not in DESTINATIONS:
            await update.message.reply_text("❌ Выберите корректную точку назначения из списка.")
            return CHOOSE_POINT_TO
        context.user_data['to_address'] = selected_point
        context.user_data['price'] = DESTINATIONS[selected_point]
    else:
        context.user_data['to_address'] = update.message.text.strip()

    await update.message.reply_text("📅 Введите дату поездки (ДД.ММ.ГГГГ):")
    return ENTER_DATE

# Шаг 5 — ввод даты
async def enter_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date_text = update.message.text.strip()
    try:
        ride_date = datetime.datetime.strptime(date_text, "%d.%m.%Y").date()
        if ride_date < datetime.date.today():
            raise ValueError("Дата в прошлом")
        context.user_data['date'] = ride_date
    except Exception:
        await update.message.reply_text("❌ Введите дату в формате ДД.ММ.ГГГГ (например, 24.05.2025)")
        return ENTER_DATE

    await update.message.reply_text("🕒 Когда вы хотите быть на месте? (в формате HH:MM, например, 09:30)")
    return ENTER_TIME  # ← правильный переход на следующий шаг

# Шаг 6 — ввод времени
async def enter_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    time = update.message.text.strip()

    # Проверка формата: одна или две цифры для часов + две цифры для минут
    if not re.match(r"^\d{1,2}:\d{2}$", time):
        await update.message.reply_text("❗ Введите время в формате HH:MM (например, 08:45)")
        return ENTER_TIME

    try:
        # Преобразуем и нормализуем (например, 6:5 -> 06:05)
        hours, minutes = map(int, time.split(":"))
        if not (0 <= hours <= 23 and 0 <= minutes <= 59):
            raise ValueError("Некорректное время")
        normalized_time = f"{hours:02d}:{minutes:02d}"
        context.user_data['time'] = normalized_time
    except Exception:
        await update.message.reply_text("❗ Введите корректное время (например, 08:45)")
        return ENTER_TIME

    await update.message.reply_text(
        f"🔒 Подтвердите бронирование:\n\n"
        f"Тип: {context.user_data['ride_type']}\n"
        f"Из: {context.user_data['from_city']} ({context.user_data['from_address']})\n"
        f"В: {context.user_data['to_city']} ({context.user_data['to_address']})\n"
        f"Дата: {context.user_data['date']}\n"
        f"Время: {context.user_data['time']}\n"
        f"💰 Стоимость: {context.user_data['price']} р\n\n"
        f"Напишите 'Подтверждаю' или 'Отмена'"
    )
    return CONFIRM_BOOKING

# Шаг 7 — подтверждение
async def confirm_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()
    if text != "подтверждаю":
        await update.message.reply_text("❌ Бронирование отменено.", reply_markup=main_menu)
        return ConversationHandler.END

    conn = context.bot_data.get("conn")
    cursor = context.bot_data.get("cursor")

    if not conn or not cursor:
        await update.message.reply_text("⚠️ Ошибка сервера. Повторите позже.", reply_markup=main_menu)
        return ConversationHandler.END

    telegram_id = update.effective_user.id
    cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (telegram_id,))
    user_row = cursor.fetchone()

    if not user_row:
        await update.message.reply_text("⚠️ Пользователь не найден. Попробуйте /start заново.")
        return ConversationHandler.END

    user_id = user_row[0]

    try:
        # Объединяем дату и время в scheduled_time
        ride_date = context.user_data['date']
        ride_time_str = context.user_data['time']
        ride_time = datetime.datetime.strptime(ride_time_str, "%H:%M").time()
        scheduled_datetime = datetime.datetime.combine(ride_date, ride_time)


        # Выполняем корректную вставку
        cursor.execute("""
            INSERT INTO bookings (
                client_id,
                from_city,
                to_city,
                pickup_point,
                destination_point,
                scheduled_time,
                price,
                ride_type,
                status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pending')
        """, (
            user_id,
            context.user_data['from_city'],
            context.user_data['to_city'],
            context.user_data['from_address'],
            context.user_data['to_address'],
            scheduled_datetime,
            context.user_data['price'],
            context.user_data['ride_type']
        ))
        conn.commit()

        await update.message.reply_text(
            "✅ Ваша заявка принята! Ожидайте подтверждения от администратора.",
            reply_markup=main_menu
        )
        logger.info("Бронь создана для пользователя %s", telegram_id)

    except Exception as e:
        logger.exception("Ошибка при записи брони:")
        conn.rollback()
        await update.message.reply_text("❌ Ошибка при бронировании. Попробуйте позже.", reply_markup=main_menu)

    return ConversationHandler.END

# Шаг 8 — необязательный дополнительный ввод
async def extra_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📌 Спасибо за дополнительную информацию!")
    return ConversationHandler.END

# Функция возвращающая все состояния
def get_states_range():
    return CHOOSE_TYPE, CHOOSE_DIRECTION, ENTER_ADDRESS_FROM, CHOOSE_POINT_TO, ENTER_DATE, ENTER_TIME, CONFIRM_BOOKING, EXTRA
