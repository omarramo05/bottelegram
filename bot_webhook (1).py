
import os
import logging
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, ContextTypes, CallbackQueryHandler
)

# تسجيل الأحداث
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# قراءة التوكن والرابط من المتغيرات البيئية
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
PORT = int(os.environ.get("PORT", 5000))

# أوامر الاختبار
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("البوت شغال ✅")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أرسل /start لتبدأ 🚀")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text=f"🔘 تم الضغط على: {query.data}")

# إعداد التطبيق
application = Application.builder().token(TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("help", help_command))
application.add_handler(CallbackQueryHandler(button_handler))

# تشغيل باستخدام Webhook
if __name__ == "__main__":
    logger.info(f"🔗 Webhook URL: {WEBHOOK_URL}/webhook")
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=f"{WEBHOOK_URL}/webhook"
    )
