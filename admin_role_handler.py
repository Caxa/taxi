from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
import psycopg2

ADMIN_MENU = ReplyKeyboardMarkup(
    [
        ["📋 Подтвердить бронь"],
        ["📂 Активные брони", "📜 История броней"],
        ["↩️ Назад"]
    ],
    resize_keyboard=True
)

AWAIT_ADMIN_ACTION = 99
AWAIT_BOOKING_ID = 100

async def confirm_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    cursor = context.application.bot_data["cursor"]

    cursor.execute("SELECT role FROM users WHERE telegram_id = %s", (telegram_id,))
    result = cursor.fetchone()

    if result and result[0] == "admin":
        await update.message.reply_text("🔐 Добро пожаловать в админ-панель.", reply_markup=ADMIN_MENU)
        return AWAIT_ADMIN_ACTION
    else:
        await update.message.reply_text("🚫 У вас нет прав администратора.")
        return ConversationHandler.END


async def admin_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    cursor = context.application.bot_data["cursor"]

    if text == "📋 Подтвердить бронь":
        await update.message.reply_text("🔢 Введите ID брони для подтверждения:")
        return AWAIT_BOOKING_ID

    elif text == "📂 Активные брони":
        cursor.execute("""
            SELECT b.id, u.full_name, u.phone, u.telegram_id, b.scheduled_time, b.status
            FROM bookings b
            JOIN users u ON b.client_id = u.id
            WHERE b.status IN ('pending', 'confirmed')
            ORDER BY b.scheduled_time DESC
        """)
        rows = cursor.fetchall()

        if not rows:
            await update.message.reply_text("📭 Нет активных броней.")
        else:
            for row in rows:
                booking_id, full_name, phone, telegram_id, scheduled_time, status = row
                message = (
                    f"🆔 Бронь #{booking_id}\n"
                    f"👤 Клиент: {full_name}\n"
                    f"📞 Телефон: {phone}\n"
                    f"📅 Время: {scheduled_time}\n"
                    f"📌 Статус: {status}"
                )
                buttons = []
                if telegram_id:
                    buttons.append(
                        [InlineKeyboardButton("💬 Написать в Telegram", url=f"tg://user?id={telegram_id}")]
                    )
                await update.message.reply_text(
                    message,
                    reply_markup=InlineKeyboardMarkup(buttons) if buttons else None
                )

        return AWAIT_ADMIN_ACTION

    elif text == "📜 История броней":
        cursor.execute("""
            SELECT b.id, u.full_name, u.phone, u.telegram_id, b.scheduled_time, b.status
            FROM bookings b
            JOIN users u ON b.client_id = u.id
            ORDER BY b.scheduled_time DESC
            LIMIT 30
        """)
        rows = cursor.fetchall()

        if not rows:
            await update.message.reply_text("📭 История пуста.")
        else:
            for row in rows:
                booking_id, full_name, phone, telegram_id, scheduled_time, status = row
                message = (
                    f"🆔 Бронь #{booking_id}\n"
                    f"👤 Клиент: {full_name}\n"
                    f"📞 Телефон: {phone}\n"
                    f"📅 Время: {scheduled_time}\n"
                    f"📌 Статус: {status}"
                )
                buttons = []
                if telegram_id:
                    buttons.append(
                        [InlineKeyboardButton("💬 Написать в Telegram", url=f"tg://user?id={telegram_id}")]
                    )
                await update.message.reply_text(
                    message,
                    reply_markup=InlineKeyboardMarkup(buttons) if buttons else None
                )

        return AWAIT_ADMIN_ACTION

    elif text == "↩️ Назад":
        await update.message.reply_text(
            "🔙 Возвращение в главное меню.",
            reply_markup=ReplyKeyboardMarkup(
                [["📅 Мои брони", "🚕 Забронировать поездку"]],
                resize_keyboard=True
            )
        )
        return ConversationHandler.END


async def approve_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        booking_id = int(update.message.text)
    except ValueError:
        await update.message.reply_text("❌ Введите корректный ID.")
        return AWAIT_BOOKING_ID

    cursor = context.application.bot_data["cursor"]
    conn = context.application.bot_data["conn"]

    cursor.execute("SELECT status FROM bookings WHERE id = %s", (booking_id,))
    result = cursor.fetchone()

    if not result:
        await update.message.reply_text("❌ Бронь не найдена.")
        return AWAIT_BOOKING_ID

    if result[0] == "confirmed":
        await update.message.reply_text("✅ Бронь уже подтверждена.")
        return AWAIT_ADMIN_ACTION

    cursor.execute("UPDATE bookings SET status = 'confirmed' WHERE id = %s", (booking_id,))
    conn.commit()

    await update.message.reply_text(f"✅ Бронь #{booking_id} подтверждена.")
    return AWAIT_ADMIN_ACTION
