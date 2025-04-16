import base64
from cryptography.fernet import Fernet
import os
from typing import Optional

# مفتاح التشفير - يتم إنشاؤه مرة واحدة
ENCRYPTION_KEY = Fernet.generate_key() if not os.path.exists('key.key') else open('key.key', 'rb').read()
if not os.path.exists('key.key'):
    with open('key.key', 'wb') as key_file:
        key_file.write(ENCRYPTION_KEY)

cipher_suite = Fernet(ENCRYPTION_KEY)

def encrypt(text: str) -> str:
    """تشفير النص"""
    return cipher_suite.encrypt(text.encode()).decode()

def decrypt(encrypted_text: str) -> str:
    """فك تشفير النص"""
    return cipher_suite.decrypt(encrypted_text.encode()).decode()

# إعدادات التداول
MAX_TRADE_AMOUNT_USDT = 1000  # الحد الأقصى لقيمة الصفقة الواحدة بالدولار
RESTRICTED_PAIRS = []  # أزواج التداول المقيدة
LOG_TRADES = True  # تسجيل عمليات التداول

def get_env_var(var_name: str) -> Optional[str]:
    """الحصول على قيمة متغير البيئة بشكل آمن"""
    value = os.getenv(var_name)
    if not value:
        print(f"تحذير: {var_name} غير موجود في متغيرات البيئة")
    return value

# المفاتيح من متغيرات البيئة
TELEGRAM_BOT_TOKEN = get_env_var('TELEGRAM_BOT_TOKEN')
BINANCE_API_KEY = get_env_var('BINANCE_API_KEY')
BINANCE_SECRET_KEY = get_env_var('BINANCE_SECRET_KEY')

# Security Settings
AUTHORIZED_USERS = [
    # Add your Telegram user IDs here
]

MAX_DAILY_TRADES = 50  # Maximum number of trades per day

# Security Flags
ENABLE_IP_CHECK = False  # Set to True to enable IP verification
ENABLE_2FA = False  # Set to True to enable 2FA (requires additional setup)
LOG_ALL_ACTIONS = True  # Log all user actions

# Rate Limiting
RATE_LIMIT = {
    'trades_per_minute': 5,
    'orders_per_minute': 10,
    'api_calls_per_minute': 60
} 