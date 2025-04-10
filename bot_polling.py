
import os
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📊 التداول", callback_data="trade")],
        [InlineKeyboardButton("⭐️ المفضلة", callback_data="favorites")],
        [InlineKeyboardButton("🧾 سجل التداول", callback_data="history")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("مرحبًا بك في بوت التداول 👋", reply_markup=reply_markup)

# عندما يتم الضغط على زر
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "trade":
        await query.edit_message_text("📈 خيارات التداول ستظهر هنا")
    elif data == "favorites":
        await query.edit_message_text("⭐️ العملات المفضلة لديك:")
    elif data == "history":
        await query.edit_message_text("🧾 هذا هو سجل التداول الخاص بك.")
    else:
        await query.edit_message_text("❓ أمر غير معروف.")

# إعداد التطبيق
app = Application.builder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(handle_buttons))

# تشغيل البوت بالـ polling
if __name__ == "__main__":
    app.run_polling()
