# booking.py

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
import logging
import re

logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
CHOOSE_TYPE, CHOOSE_CITY, CHOOSE_POINT, ENTER_TIME, CONFIRM_BOOKING = range(1, 6)

# Главное меню (экспортируем в main.py)
main_menu = ReplyKeyboardMarkup([
    ["🚕 Забронировать поездку", "📅 Мои брони"],
    ["👤 Мой профиль", "👨‍✈️ Стать водителем"],
    ["ℹ️ Помощь / Контакты"]
], resize_keyboard=True)

# Передаём состояния в main.py
def get_states_range():
    return CHOOSE_TYPE, CHOOSE_CITY, CHOOSE_POINT, ENTER_TIME, CONFIRM_BOOKING

# Шаг 1: Выбор типа поездки
async def choose_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    selected = update.message.text.strip()
    logger.info("Выбран тип поездки: %s", selected)

    if selected not in ["🚗 Место в машине", "🚘 Вся машина"]:
        await update.message.reply_text(
            "🚕 Выберите, как хотите ехать:",
            reply_markup=ReplyKeyboardMarkup([
                ["🚗 Место в машине", "🚘 Вся машина"]
            ], resize_keyboard=True)
        )
        return CHOOSE_TYPE

    context.user_data['ride_type'] = selected
    await update.message.reply_text("🏙 Куда вы хотите поехать? (например, Казань)")
    logger.info("Переход к выбору города.")
    return CHOOSE_CITY

# Шаг 2: Выбор города
async def choose_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = update.message.text.strip().lower()
    logger.info("Введён город: %s", city)

    if city not in ["казань", "нижнекамск"]:
        await update.message.reply_text("❌ Мы обслуживаем только Казань и Нижнекамск.")
        return CHOOSE_CITY

    context.user_data['city_to'] = city.capitalize()
    await update.message.reply_text(
        "📍 Выберите точку назначения:",
        reply_markup=ReplyKeyboardMarkup([
            ["🚉 Вокзал 1", "🚉 Вокзал 2"],
            ["✈️ Аэропорт", "📍 Другое место"]
        ], resize_keyboard=True)
    )
    return CHOOSE_POINT

# Шаг 3: Выбор точки назначения
async def choose_point(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()

    if user_input not in DESTINATIONS:
        # Показываем список в сообщении, а не кнопках
        destinations_list = "\n".join(
            [f"{i+1}. {name} — {price} р" for i, (name, price) in enumerate(DESTINATIONS.items())]
        )
        await update.message.reply_text(
            f"❌ Некорректная точка.\n\n📍 Выберите одну из точек:\n\n{destinations_list}"
        )
        return CHOOSE_POINT

    context.user_data['point'] = user_input
    context.user_data['price'] = DESTINATIONS[user_input]

    await update.message.reply_text("🕒 Когда вы хотите быть на месте? (в формате HH:MM, например, 09:30)")
    return ENTER_TIME


# Шаг 4: Ввод времени

async def enter_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    time = update.message.text.strip()

    # Проверка формата времени
    if not re.match(r"^(?:[01]\d|2[0-3]):[0-5]\d$", time):
        await update.message.reply_text("❗ Пожалуйста, введите время в формате HH:MM (например, 08:45)")
        return ENTER_TIME

    context.user_data['time'] = time

    await update.message.reply_text(
        f"🔒 Подтвердите бронирование:\n\n"
        f"Тип: {context.user_data['ride_type']}\n"
        f"Город: {context.user_data['city_to']}\n"
        f"Точка: {context.user_data['point']}\n"
        f"Время: {context.user_data['time']}\n"
        f"💰 Стоимость: {context.user_data['price']} р\n\n"
        f"Напишите 'Подтверждаю' или 'Отмена'"
    )
    return CONFIRM_BOOKING

# Шаг 5: Подтверждение и сохранение в БД
async def confirm_booking(update: Update, context: ContextTypes.DEFAULT_TYPE, conn, cursor):
    text = update.message.text.strip().lower()

    if text != "подтверждаю":
        await update.message.reply_text("❌ Бронирование отменено.", reply_markup=main_menu)
        return ConversationHandler.END

    telegram_id = update.effective_user.id
    cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (telegram_id,))
    user_row = cursor.fetchone()

    if not user_row:
        await update.message.reply_text("⚠️ Ошибка: пользователь не найден. Попробуйте /start заново.")
        return ConversationHandler.END

    user_id = user_row[0]

    try:
        cursor.execute("""
            INSERT INTO bookings (client_id, schedule_id, booked_seats, pickup_point, destination_point, status)
            VALUES (%s, NULL, 1, %s, %s, 'pending')
        """, (
            user_id,
            context.user_data.get('point'),
            context.user_data.get('city_to')
        ))
        conn.commit()

        await update.message.reply_text(
            "✅ Ваша заявка принята! Администратор назначит поездку в ближайшее время.",
            reply_markup=main_menu
        )
        logger.info("Бронирование успешно для пользователя %s", telegram_id)

    except Exception as e:
        logger.error("Ошибка при записи брони: %s", str(e))
        conn.rollback()
        await update.message.reply_text("❌ Ошибка при отправке заявки. Попробуйте позже.", reply_markup=main_menu)

    return ConversationHandler.END

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
