import os
import logging
import psycopg2
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton,InlineKeyboardButton, InlineKeyboardMarkup
from datetime import datetime, timedelta
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ConversationHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from datetime import datetime, timedelta


import booking  # логика бронирования только тут


# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения из .env
load_dotenv()

# Подключение к базе данных
conn = psycopg2.connect(
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    host=os.getenv("DB_HOST"),
    port=os.getenv("DB_PORT")
)
cursor = conn.cursor()

# Состояния бронирования берём из booking.py
WAIT_PHONE = 0
CHOOSE_TYPE, CHOOSE_CITY, CHOOSE_POINT, ENTER_TIME, CONFIRM_BOOKING = booking.get_states_range()

# Главное меню (из booking.py)
main_menu = booking.main_menu


STATUS_MAP = {
    "pending": "⏳ В ожидании",
    "confirmed": "✅ Подтверждено",
    "cancelled": "❌ Отменено",
    "completed": "🏁 Завершено",
}


# /start — приветствие и регистрация
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    logger.info("/start от пользователя %s", telegram_id)
    cursor.execute("SELECT * FROM users WHERE telegram_id = %s", (telegram_id,))
    user = cursor.fetchone()

    if not user:
        await update.message.reply_text(
            "📱 Пожалуйста, подтвердите номер телефона:",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("📞 Отправить номер телефона", request_contact=True)]],
                resize_keyboard=True
            )
        )
        return WAIT_PHONE
    else:
        await update.message.reply_text("Добро пожаловать! Выберите действие:", reply_markup=main_menu)
        return ConversationHandler.END

# Получение номера телефона
async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    telegram_id = update.effective_user.id
    full_name = f"{update.effective_user.first_name or ''} {update.effective_user.last_name or ''}".strip()
    phone = contact.phone_number

    cursor.execute(
        "INSERT INTO users (telegram_id, full_name, phone) VALUES (%s, %s, %s) ON CONFLICT (telegram_id) DO NOTHING",
        (telegram_id, full_name, phone)
    )
    conn.commit()

    await update.message.reply_text("✅ Номер подтверждён. Выберите действие:", reply_markup=main_menu)
    return ConversationHandler.END


async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    telegram_id = update.effective_user.id
    logger.info("Меню: '%s' от пользователя %s", text, telegram_id)

    if text == "📅 Мои брони":
        cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (telegram_id,))
        user_id_row = cursor.fetchone()

        if not user_id_row:
            await update.message.reply_text("⚠️ Пользователь не найден. Попробуйте /start", reply_markup=main_menu)
            return

        user_id = user_id_row[0]
        cursor.execute("""
            SELECT pickup_point, destination_point, status, id, scheduled_time
            FROM bookings
            WHERE client_id = %s AND status != 'cancelled'
            ORDER BY scheduled_time NULLS LAST
        """, (user_id,))
        bookings = cursor.fetchall()

        if bookings:
            for i, (pickup, destination, status, booking_id, scheduled_time) in enumerate(bookings):
                time_str = scheduled_time.strftime("%Y-%m-%d %H:%M") if scheduled_time else "время не указано"
                status_text = STATUS_MAP.get(status, status)

                msg = (
                    f"📅 *Бронь #{i+1}:*\n"
                    f"{pickup} → {destination}\n"
                    f"⏰ Время: {time_str} | Статус: {status_text}\n\n"
                    "❗ Если до поездки < 12 часов — предоплата не возвращается."
                )


                if status in ("pending", "confirmed"):
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton(f"❌ Отменить бронь #{booking_id}", callback_data=f"cancel:{booking_id}")]
                    ])
                else:
                    keyboard = None

                await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=keyboard or main_menu)
        else:
            await update.message.reply_text("📭 У вас нет активных броней.", reply_markup=main_menu)

    elif text.startswith("Отменить"):
        try:
            booking_id = int(text.split()[1])
        except (IndexError, ValueError):
            await update.message.reply_text("❌ Укажите ID брони корректно. Пример: Отменить 123", reply_markup=main_menu)
            return

        cursor.execute("""
            SELECT scheduled_time, status
            FROM bookings
            WHERE id = %s AND client_id = (SELECT id FROM users WHERE telegram_id = %s)
        """, (booking_id, telegram_id))
        result = cursor.fetchone()

        if not result:
            await update.message.reply_text("❌ Бронь не найдена или вы не являетесь её владельцем.", reply_markup=main_menu)
            return

        scheduled_time, status = result
        if status == "cancelled":
            await update.message.reply_text("ℹ️ Эта бронь уже отменена.", reply_markup=main_menu)
            return

        now = datetime.now()
        if scheduled_time and (scheduled_time - now < timedelta(hours=12)):
            refund_msg = "⚠️ До поездки осталось менее 12 часов — предоплата не возвращается."
        else:
            refund_msg = "✅ Предоплата будет возвращена в полном объёме."

        cursor.execute("UPDATE bookings SET status = 'cancelled' WHERE id = %s", (booking_id,))
        conn.commit()

        await update.message.reply_text(
            f"🚫 Бронь #{booking_id} успешно отменена.\n{refund_msg}",
            reply_markup=main_menu
        )

    elif text == "👤 Мой профиль":
        cursor.execute("SELECT full_name, phone FROM users WHERE telegram_id = %s", (telegram_id,))
        user = cursor.fetchone()
        if user:
            await update.message.reply_text(
                f"👤 Ваш профиль:\n\nИмя: {user[0]}\nТелефон: {user[1]}",
                reply_markup=main_menu
            )
        else:
            await update.message.reply_text("⚠️ Профиль не найден. Попробуйте /start", reply_markup=main_menu)

    elif text == "👨‍✈️ Стать водителем":
        await update.message.reply_text("🚘 Чтобы стать водителем, свяжитесь с админом: @admin", reply_markup=main_menu)

    elif text == "ℹ️ Помощь / Контакты":
        await update.message.reply_text("📞 Поддержка: +7-999-123-4567", reply_markup=main_menu)


# Обработка отмены
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⛔ Действие отменено.", reply_markup=main_menu)
    return ConversationHandler.END

# Обёртка для confirm_booking из booking.py
async def confirm_booking_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = context.application.bot_data["conn"]
    cursor = context.application.bot_data["cursor"]
    return await booking.confirm_booking(update, context, conn, cursor)

async def cancel_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    message = update.message.text
    match = re.match(r"/cancel_(\d+)", message)

    if not match:
        await update.message.reply_text("❌ Неверная команда.")
        return

    booking_id = int(match.group(1))

    # Получаем бронь
    cursor.execute("""
        SELECT client_id, ride_time, status FROM bookings WHERE id = %s
    """, (booking_id,))
    result = cursor.fetchone()

    if not result:
        await update.message.reply_text("❌ Бронь не найдена.")
        return

    client_id, ride_time, status = result

    # Проверяем владельца
    cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (telegram_id,))
    user_id = cursor.fetchone()[0]

    if client_id != user_id:
        await update.message.reply_text("🚫 Это не ваша бронь.")
        return

    # Проверка времени
    if ride_time is not None:
        now = datetime.now()
        hours_diff = (ride_time - now).total_seconds() / 3600

        if hours_diff < 12:
            warning = "❗️ Вы отменяете поездку менее чем за 12 часов. Предоплата не возвращается."
        else:
            warning = "✅ Бронь успешно отменена."

    else:
        warning = "⚠️ Время поездки не указано. Бронь отменена без расчёта возврата."

    # Обновляем статус
    cursor.execute("UPDATE bookings SET status = 'cancelled' WHERE id = %s", (booking_id,))
    conn.commit()

    await update.message.reply_text(warning, reply_markup=main_menu)


async def handle_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    telegram_id = update.effective_user.id
    data = query.data

    if data.startswith("cancel:"):
        booking_id = int(data.split(":")[1])

        cursor.execute("""
            SELECT scheduled_time, status
            FROM bookings
            WHERE id = %s AND client_id = (SELECT id FROM users WHERE telegram_id = %s)
        """, (booking_id, telegram_id))
        result = cursor.fetchone()

        if not result:
            await query.edit_message_text("❌ Бронь не найдена или вы не являетесь её владельцем.", reply_markup=main_menu)
            return

        scheduled_time, status = result
        if status == "cancelled":
            await query.edit_message_text("ℹ️ Эта бронь уже отменена.", reply_markup=main_menu)
            return

        now = datetime.now()
        if scheduled_time and (scheduled_time - now < timedelta(hours=12)):
            refund_msg = "⚠️ До поездки осталось менее 12 часов — предоплата не возвращается."
        else:
            refund_msg = "✅ Предоплата будет возвращена в полном объёме."

        cursor.execute("UPDATE bookings SET status = 'cancelled' WHERE id = %s", (booking_id,))
        conn.commit()

        await query.edit_message_text(f"🚫 Бронь #{booking_id} успешно отменена.\n{refund_msg}", reply_markup=main_menu)

# Главная функция запуска бота
def main():
    logger.info("Запуск Telegram Taxi Bot...")

    app = ApplicationBuilder().token(os.getenv("BOT_TOKEN")).build()

    # Сохраняем conn и cursor в bot_data для глобального доступа
    app.bot_data["conn"] = conn
    app.bot_data["cursor"] = cursor

    # ConversationHandler для бронирования (запускается через пункт меню "🚕 Забронировать поездку")
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🚕 Забронировать поездку$"), booking.choose_type)],
        states={
            WAIT_PHONE: [MessageHandler(filters.CONTACT, get_phone)],
            CHOOSE_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, booking.choose_type)],
            CHOOSE_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, booking.choose_city)],
            CHOOSE_POINT: [MessageHandler(filters.TEXT & ~filters.COMMAND, booking.choose_point)],
            ENTER_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, booking.enter_time)],
            CONFIRM_BOOKING: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_booking_wrapper)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Регистрируем хендлеры
    app.add_handler(CallbackQueryHandler(handle_cancel_callback, pattern=r'^cancel:\d+$'))

    app.add_handler(MessageHandler(filters.Regex(r"^/cancel_\d+$"), cancel_booking))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)  # Conversation handler бронирования
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_main_menu))

    # Запуск бота
    app.run_polling()

if __name__ == "__main__":
    main()
