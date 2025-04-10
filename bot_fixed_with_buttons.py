# بداية ملف bot.py
import os
import logging
import re
import time # للتخزين المؤقت
import json # <<<--- لإضافة التعامل مع Redis
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_UP, Context as DecimalContext # للتقريب الدقيق والتحكم بالدقة
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Any, Set, Optional, Union # لتحسين Type Hinting

# --- تحميل المتغيرات من ملف .env ---
# تأكد من تثبيت المكتبة: pip install python-dotenv
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("🔎 TELEGRAM_BOT_TOKEN =", os.getenv("TELEGRAM_BOT_TOKEN"))
    # Initialize logger here after potential load_dotenv success
    logger = logging.getLogger(__name__)
    logger.info("تم تحميل ملف .env (إذا كان موجوداً).")
except ImportError:
    print("تحذير: مكتبة python-dotenv غير مثبتة. لن يتم تحميل ملف .env.")
    print("pip install python-dotenv")
    # Initialize logger here as well in case of import error
    logger = logging.getLogger(__name__)
# Removed stray load_dotenv(dotenv_path=env_path)


# --- استيراد مكتبات البوت والـ API ---
# تأكد من تثبيت المكتبات: pip install python-telegram-bot python-binance python-dateutil upstash-redis
try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.constants import ParseMode
    from telegram.error import TelegramError # لالتقاط أخطاء تليجرام
    from telegram.ext import (
        Application,
        CommandHandler,
        MessageHandler,
        filters,
        ContextTypes,
        CallbackQueryHandler,
        ConversationHandler,
        PicklePersistence # <<<--- لإضافة الحفظ المستمر (اختياري)
    )
    from binance.client import Client
    from binance.enums import *
    from binance.exceptions import BinanceAPIException, BinanceOrderException, BinanceRequestException
    from upstash_redis import Redis # <<<--- استيراد Upstash Redis
    # from dateutil.parser import parse as parse_datetime
except ImportError as e:
    # Use logger if initialized, otherwise print
    log_func = logger.error if 'logger' in globals() else print
    log_func(f"خطأ: لم يتم العثور على مكتبة ضرورية: {e}. يرجى تثبيت المكتبات المطلوبة.")
    log_func("pip install python-telegram-bot[persistence] python-binance python-dateutil upstash-redis") # إضافة [persistence]
    exit()


# --- إعداد التسجيل ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
# Logger is already initialized above
# Set higher precision for Decimal operations if needed
decimal_context = DecimalContext(prec=28) # Adjust precision as needed

# --- تحميل الإعدادات الآمنة ---
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
BINANCE_API_KEY = os.environ.get('BINANCE_API_KEY')
BINANCE_SECRET_KEY = os.environ.get('BINANCE_SECRET_KEY')
UPSTASH_URL = os.environ.get('UPSTASH_URL') # <<<--- تحميل Upstash URL
UPSTASH_TOKEN = os.environ.get('UPSTASH_TOKEN') # <<<--- تحميل Upstash Token

# --- التحقق وتهيئة Binance Client ---
binance_client: Optional[Client] = None
if not TELEGRAM_BOT_TOKEN:
    logger.critical("TELEGRAM_BOT_TOKEN غير موجود في متغيرات البيئة أو ملف .env!")
    exit("Token Error")
if BINANCE_API_KEY and BINANCE_SECRET_KEY:
    try:
        binance_client = Client(BINANCE_API_KEY, BINANCE_SECRET_KEY)
        binance_client.ping() # Check connection
        logger.info("تم الاتصال بنجاح بـ Binance.")
    except (BinanceAPIException, BinanceRequestException) as e:
         logger.error(f"فشل الاتصال بـ Binance (API Error): {e}")
         binance_client = None
    except Exception as e:
        logger.error(f"فشل الاتصال بـ Binance (General Error): {e}")
        binance_client = None
else:
    logger.warning("مفاتيح Binance API غير موجودة. وظائف التداول معطلة.")

# --- تهيئة Upstash Redis Client --- <<<--- تعديل
redis_client: Optional[Redis] = None
if UPSTASH_URL and UPSTASH_TOKEN:
    try:
        redis_client = Redis(url=UPSTASH_URL, token=UPSTASH_TOKEN)
        # Test connection with a simple command (e.g., get time or a known key)
        redis_client.time() # Or use redis_client.get("test_connection") after setting it once
        # upstash-redis handles decoding by default if no encoding is specified
        logger.info("تم الاتصال بنجاح بـ Upstash Redis.")

    except Exception as e: # Catch broader exceptions as specific Upstash errors might vary
        logger.error(f"فشل الاتصال بـ Upstash Redis: {e}")
        redis_client = None
else:
    logger.warning("UPSTASH_URL أو UPSTASH_TOKEN غير موجود. سيتم استخدام التخزين المؤقت في الذاكرة.")


# --- تعريف بيانات الاستدعاء (Callback Data) ---
# (نفس تعريفات الـ Callbacks السابقة)
CALLBACK_MAIN_MENU = "main_menu"; CALLBACK_GOTO_TRADING = "goto_trading"; CALLBACK_GOTO_ACCOUNT = "goto_account"
CALLBACK_GOTO_SEARCH = "goto_search"; CALLBACK_GOTO_HISTORY = "goto_history"; CALLBACK_GOTO_ANALYSIS = "goto_analysis"
CALLBACK_GOTO_FAVORITES = "goto_favorites"; CALLBACK_GOTO_SETTINGS = "goto_settings" # جديد: إعدادات
CALLBACK_SHOW_HELP = "show_help"; CALLBACK_SHOW_BALANCE = "show_balance"; CALLBACK_SHOW_ORDERS = "show_orders"
CALLBACK_SHOW_PNL = "show_pnl"; CALLBACK_START_BUY = "start_buy"; CALLBACK_START_SELL = "start_sell"
CALLBACK_SHOW_GAINERS = "show_gainers"; CALLBACK_SHOW_LOSERS = "show_losers"; CALLBACK_SEARCH_MANUAL_START = "search_manual_start"
CALLBACK_HISTORY_TODAY = "history_today"; CALLBACK_HISTORY_BY_PAIR_START = "history_by_pair_start"
CALLBACK_CONFIRM_TRADE = "confirm_trade_final"; CALLBACK_CANCEL_TRADE = "cancel_trade_conv"
CALLBACK_ADD_SLTP_YES = "add_sltp_yes"; CALLBACK_ADD_SLTP_NO = "add_sltp_no"; CALLBACK_ADD_SLTP_PERCENT = "add_sltp_percent"
CALLBACK_SKIP_TP = "skip_tp"; CALLBACK_CANCEL = "cancel_action"
# المفضلة
CALLBACK_ADD_FAVORITE_START = "fav_add_start"
CALLBACK_REMOVE_FAVORITE_START = "fav_rem_start"
CALLBACK_REMOVE_FAVORITE_PREFIX = "fav_rem_pair_"
# الشراء من المفضلة
CALLBACK_BUY_FAVORITE_PREFIX = "buy_fav_"
CALLBACK_BUY_OTHER_PAIR = "buy_other"
# البيع
CALLBACK_SELL_ASSET_PREFIX = "sell_asset_"
CALLBACK_SELL_AMOUNT_ALL = "sell_all"
CALLBACK_SELL_AMOUNT_PARTIAL = "sell_partial"
# نسب SL/TP
CALLBACK_SL_PERCENT_PREFIX = "sl_perc_"
CALLBACK_TP_PERCENT_PREFIX = "tp_perc_"
# الإعدادات
CALLBACK_SET_MAX_BUY_START = "set_max_buy_start"
# إلغاء الأوامر
CALLBACK_CANCEL_ORDER_PREFIX = "cancel_order_" # <<<--- جديد


# --- تعريف حالات المحادثة ---
(
    T_ASK_PAIR, T_ASK_AMOUNT, T_ASK_SLTP_CHOICE, T_ASK_SL_PRICE, T_ASK_TP_PRICE, T_CONFIRM_TRADE_STATE, # تداول
    S_ASK_PAIR, # بحث
    H_ASK_PAIR, # سجل
    T_CHOOSE_SELL_ASSET, T_ASK_SELL_AMOUNT, # بيع
    T_ASK_SL_PERCENT, T_ASK_TP_PERCENT, # نسب SL/TP
    FAV_ASK_ADD_PAIR, # إضافة مفضلة
    SET_ASK_MAX_BUY_AMOUNT, # إعدادات: حد الشراء
) = range(14) # <<<--- *** تم التصحيح هنا ***


# --- ثوابت للتخزين المؤقت وإعدادات المفضلة ---
CACHE_DURATION_SECONDS = 300 # 5 دقائق
MAX_FAVORITES = 15
MAX_FAVORITE_BUTTONS = 5
EXCHANGE_INFO_CACHE_KEY = "exchange_info"
SYMBOLS_CACHE_KEY = "valid_symbols"
TICKERS_CACHE_KEY = "tickers_cache" # لتخزين أسعار Ticker
DEFAULT_MAX_BUY_USDT = Decimal('1000') # حد شراء افتراضي بالدولار

# --- دوال مساعدة ---

async def fetch_and_cache_exchange_info(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fetches and caches exchange information including valid symbols (using Redis if available)."""
    if not binance_client:
        logger.warning("Binance client not initialized. Cannot fetch exchange info.")
        return
    try:
        logger.info("Fetching exchange information from Binance...")
        exchange_info = binance_client.get_exchange_info()
        valid_symbols = {s['symbol'] for s in exchange_info.get('symbols', []) if s.get('status') == 'TRADING'}

        if redis_client:
            try:
                # Store in Redis with expiry
                # upstash-redis set returns the result, check for errors if needed
                redis_client.set(EXCHANGE_INFO_CACHE_KEY, json.dumps(exchange_info), ex=CACHE_DURATION_SECONDS * 2)
                redis_client.set(SYMBOLS_CACHE_KEY, json.dumps(list(valid_symbols)), ex=CACHE_DURATION_SECONDS * 2)
                logger.info(f"Cached exchange info and {len(valid_symbols)} valid symbols in Redis.")
            except Exception as redis_e: # Catch broader exceptions
                logger.error(f"Upstash Redis Error caching exchange info: {redis_e}. Falling back to bot_data.")
                # Fallback to bot_data if Redis fails
                context.bot_data[EXCHANGE_INFO_CACHE_KEY] = exchange_info
                context.bot_data[SYMBOLS_CACHE_KEY] = valid_symbols
        else:
            # Use bot_data if Redis is not configured
            context.bot_data[EXCHANGE_INFO_CACHE_KEY] = exchange_info
            context.bot_data[SYMBOLS_CACHE_KEY] = valid_symbols
            logger.info(f"Cached exchange info and {len(valid_symbols)} valid symbols in bot_data.")

    except (BinanceAPIException, BinanceRequestException) as e:
        logger.error(f"Binance API Error fetching exchange info: {e}")
    except Exception as e:
        logger.error(f"Error fetching exchange info: {e}", exc_info=True)

def is_valid_symbol(symbol: str, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Checks if a symbol is valid and trading based on cached info (Redis or bot_data)."""
    valid_symbols: Set[str] = set()
    source = "unknown"
    if redis_client:
        try:
            cached_symbols_json = redis_client.get(SYMBOLS_CACHE_KEY)
            if cached_symbols_json:
                # upstash-redis might decode automatically, ensure it's loaded as list then set
                loaded_list = json.loads(cached_symbols_json)
                valid_symbols = set(loaded_list)
                source = "Redis"
        except Exception as redis_e: # Catch broader exceptions
            logger.error(f"Upstash Redis Error reading symbols cache: {redis_e}. Trying bot_data.")
            # Fallback to bot_data if Redis read fails
            valid_symbols = context.bot_data.get(SYMBOLS_CACHE_KEY, set())
            source = "bot_data (Redis fallback)"
    else:
        # Use bot_data if Redis is not configured
        valid_symbols = context.bot_data.get(SYMBOLS_CACHE_KEY, set())
        source = "bot_data"

    if not valid_symbols:
        logger.warning(f"Valid symbols cache ({source}) is empty. Cannot validate symbol.")
        # Consider fetching here as a fallback, but might slow down requests
        return False
    return symbol in valid_symbols

def get_symbol_filters(symbol: str, context: ContextTypes.DEFAULT_TYPE) -> Dict[str, Dict[str, Any]]:
    """Gets all filters for a symbol from cached exchange info (Redis or bot_data)."""
    exchange_info = None
    source = "unknown"
    if redis_client:
        try:
            cached_info_json = redis_client.get(EXCHANGE_INFO_CACHE_KEY)
            if cached_info_json:
                # upstash-redis might decode automatically
                exchange_info = json.loads(cached_info_json)
                source = "Redis"
        except Exception as redis_e: # Catch broader exceptions
            logger.error(f"Upstash Redis Error reading exchange info cache: {redis_e}. Trying bot_data.")
            exchange_info = context.bot_data.get(EXCHANGE_INFO_CACHE_KEY)
            source = "bot_data (Redis fallback)"
    else:
        exchange_info = context.bot_data.get(EXCHANGE_INFO_CACHE_KEY)
        source = "bot_data"

    symbol_filters = {}
    if exchange_info and 'symbols' in exchange_info:
        for symbol_data in exchange_info['symbols']:
            if symbol_data['symbol'] == symbol:
                for f in symbol_data.get('filters', []):
                    symbol_filters[f.get('filterType')] = f
                break

    if not symbol_filters:
        logger.warning(f"Filters not found for {symbol} in cache ({source}). Fetching directly.")
        # Fallback to individual fetch if needed, but less efficient
        info = get_symbol_info_direct(symbol, context) # Use direct fetch helper
        if info:
             for f in info.get('filters', []):
                 symbol_filters[f.get('filterType')] = f
    return symbol_filters

def get_symbol_info_direct(symbol: str, context: ContextTypes.DEFAULT_TYPE) -> Optional[Dict[str, Any]]:
    """Directly fetches symbol info (used as fallback or if cache is unreliable). Uses simple bot_data cache."""
    if not binance_client: return None
    cache_key = f"symbol_info_direct_{symbol}" # Separate cache key for direct fetches
    # This uses bot_data for simplicity, could also be moved to Redis if desired
    cached_info = context.bot_data.get(cache_key)
    # Add timestamp check for cache validity if needed, e.g., cache for 1 minute
    # current_time = time.time()
    # if cached_info and cached_info.get('timestamp', 0) > current_time - 60:
    #    return cached_info.get('data')
    if cached_info: return cached_info # Simple cache check for now

    try:
        logger.warning(f"Fetching individual symbol info for {symbol} (direct)")
        info = binance_client.get_symbol_info(symbol)
        if info:
            # Cache for a short duration
            context.bot_data[cache_key] = info # Store directly or with timestamp: {'data': info, 'timestamp': time.time()}
            return info
        return None
    except (BinanceAPIException, BinanceRequestException) as e:
        logger.error(f"Binance API Error fetching direct symbol info for {symbol}: {e}")
        return None
    except Exception as e:
        logger.error(f"Generic error fetching direct symbol info for {symbol}: {e}")
        return None

async def get_cached_tickers(context: ContextTypes.DEFAULT_TYPE, quote_asset: str = 'USDT', force_refresh: bool = False) -> Dict[str, Decimal]:
    """Gets cached ticker prices, refreshing if needed or forced (using Redis/bot_data)."""
    if not binance_client: return {}
    cache_key = f"{TICKERS_CACHE_KEY}_{quote_asset}"
    current_time = time.time()
    cached_data = context.bot_data.get(cache_key, {})
    tickers = cached_data.get('data')
    cache_time = cached_data.get('timestamp', 0)

    if not force_refresh and tickers and (current_time - cache_time < 60): # Cache tickers for 1 min
        logger.debug("Using cached tickers.")
        return tickers

    logger.info(f"Fetching new tickers for {quote_asset} pairs...")
    try:
        # Fetch all tickers is often simpler and sometimes required if filtering isn't supported well
        all_tickers_raw = binance_client.get_symbol_ticker()
        new_tickers = {
            t['symbol']: decimal_context.create_decimal(t['price'])
            for t in all_tickers_raw # Process all tickers first
        }
        # Filter for the desired quote asset if needed, but caching all might be okay
        # filtered_tickers = {k: v for k, v in new_tickers.items() if k.endswith(quote_asset)}

        # Ensure essential pairs like BTCUSDT, ETHUSDT are present if needed elsewhere
        for base in ['BTC', 'ETH', 'BNB']:
             pair = f"{base}USDT"
             if pair not in new_tickers:
                  try:
                       ticker_info = binance_client.get_symbol_ticker(symbol=pair)
                       if ticker_info: new_tickers[pair] = decimal_context.create_decimal(ticker_info['price'])
                  except Exception: pass # Ignore if specific pair fails

        context.bot_data[cache_key] = {'data': new_tickers, 'timestamp': current_time}
        logger.info(f"Cached {len(new_tickers)} tickers (all pairs).")
        # Return all tickers, filtering can happen at the call site if necessary
        return new_tickers
    except (BinanceAPIException, BinanceRequestException) as e:
        logger.error(f"Binance API Error fetching tickers: {e}")
        return tickers or {} # Return old cache on error if available
    except Exception as e:
        logger.error(f"Error fetching tickers: {e}", exc_info=True)
        return tickers or {} # Return old cache on error if available

async def get_account_balances(context: ContextTypes.DEFAULT_TYPE, min_value_usd: Decimal = Decimal('1.0')) -> List[Dict[str, Any]]:
    """
    Fetches account balances with significant value (approx. > min_value_usd).
    Uses short-term caching and cached tickers for value estimation.
    """
    if not binance_client: return []
    cache_key = "account_balances"
    current_time = time.time()
    cached_data = context.bot_data.get(cache_key, {})
    balances = cached_data.get('data')
    cache_time = cached_data.get('timestamp', 0)

    # Use cache if recent (e.g., within 60 seconds)
    if balances and (current_time - cache_time < 60):
        logger.info("Using cached account balances.")
        return balances

    logger.info("Fetching new account balances...")
    try:
        account_info = binance_client.get_account()
        all_balances = account_info.get('balances', [])
        significant_balances = []

        # Get cached USDT tickers for value estimation (using the function that caches all)
        tickers_all = await get_cached_tickers(context, quote_asset='USDT') # Get cache containing USDT pairs

        for balance in all_balances:
            asset = balance['asset']
            # Use Decimal context for precision
            free = decimal_context.create_decimal(balance['free'])
            locked = decimal_context.create_decimal(balance['locked'])
            total = free + locked

            if total > 0:
                value_usdt = decimal_context.create_decimal(0)
                # Estimate value in USDT
                usdt_pair = f"{asset}USDT"
                if asset == 'USDT': value_usdt = total
                elif usdt_pair in tickers_all: value_usdt = total * tickers_all[usdt_pair]
                # Add fallbacks for major pairs if direct USDT pair is missing
                elif asset == 'BTC' and 'BTCUSDT' in tickers_all: value_usdt = total * tickers_all['BTCUSDT']
                elif asset == 'ETH' and 'ETHUSDT' in tickers_all: value_usdt = total * tickers_all['ETHUSDT']
                elif asset == 'BNB' and 'BNBUSDT' in tickers_all: value_usdt = total * tickers_all['BNBUSDT']


                # Include if value > threshold or it's a major stablecoin/base with some balance
                if value_usdt >= min_value_usd or (asset in ['USDT', 'BUSD', 'BTC', 'ETH', 'BNB'] and total > Decimal('0.00001')):
                    significant_balances.append({
                        'asset': asset, 'free': free, 'locked': locked,
                        'total': total, 'value_usdt': value_usdt
                    })

        # Sort by estimated value
        significant_balances.sort(key=lambda x: x.get('value_usdt', 0), reverse=True)
        context.bot_data[cache_key] = {'data': significant_balances, 'timestamp': current_time}
        return significant_balances

    except (BinanceAPIException, BinanceRequestException) as e:
        logger.error(f"Binance API Error fetching account balances: {e}")
        return [] # Return empty on API error
    except Exception as e:
        logger.error(f"Error fetching account balances: {e}", exc_info=True)
        return [] # Return empty on general error

async def get_current_price(symbol: str, context: ContextTypes.DEFAULT_TYPE) -> Optional[Decimal]:
    """Fetches the current ticker price for a symbol, using Redis/bot_data cache."""
    if not binance_client: return None

    # Use the cache that stores all tickers (which now uses Redis)
    tickers = await get_cached_tickers(context)

    if symbol in tickers:
        return tickers[symbol]
    else:
        # If not in cache, try a direct fetch as fallback
        logger.warning(f"Price for {symbol} not in main ticker cache, fetching directly.")
        try:
            ticker_info = binance_client.get_symbol_ticker(symbol=symbol)
            if ticker_info and 'price' in ticker_info:
                price = decimal_context.create_decimal(ticker_info['price'])
                # Optionally update cache here? Be careful about cache structure.
                # context.bot_data[TICKERS_CACHE_KEY + '_USDT']['data'][symbol] = price # Risky if structure changes
                return price
            logger.warning(f"Direct price fetch failed for {symbol}")
            return None
        except (BinanceAPIException, BinanceRequestException) as e:
             logger.error(f"Binance API Error fetching direct price for {symbol}: {e}")
             return None
        except Exception as e:
             logger.error(f"Generic error fetching direct price for {symbol}: {e}")
             return None

async def get_quote_asset_balance(pair: str, context: ContextTypes.DEFAULT_TYPE) -> Optional[Decimal]:
    """Gets the free balance of the quote asset for a given pair."""
    quote_asset = ""
    # Improved logic to find quote asset (handles BTC, ETH etc. as quote)
    # Uses the Redis-enabled get_symbol_filters logic indirectly
    exchange_info = None
    if redis_client:
        try:
            cached_info_json = redis_client.get(EXCHANGE_INFO_CACHE_KEY)
            if cached_info_json: exchange_info = json.loads(cached_info_json)
        except (redis.RedisError, json.JSONDecodeError): pass # Ignore error, will fallback
    if not exchange_info: exchange_info = context.bot_data.get(EXCHANGE_INFO_CACHE_KEY)

    if exchange_info:
         for symbol_data in exchange_info.get('symbols', []):
             if symbol_data['symbol'] == pair:
                  quote_asset = symbol_data.get('quoteAsset')
                  break
    else:
         # Fallback basic detection if exchange info is missing
         possible_quotes = ["USDT", "BUSD", "USDC", "TUSD", "DAI", "BTC", "ETH", "BNB", "EUR", "GBP"] # Add more if needed
         for pq in possible_quotes:
             if pair.endswith(pq): quote_asset = pq; break
         if not quote_asset and len(pair) > 3: quote_asset = pair[-3:]

    if not quote_asset:
        logger.warning(f"Could not determine quote asset for pair: {pair}")
        return None

    logger.debug(f"Determined quote asset for {pair} as {quote_asset}")
    try:
        balances = await get_account_balances(context) # Use cached balances
        for balance in balances:
            if balance['asset'] == quote_asset:
                logger.debug(f"Found balance for {quote_asset}: {balance['free']}")
                return balance['free']
        logger.warning(f"Quote asset {quote_asset} not found in significant balances.")
        return Decimal(0) # Return 0 if quote asset not found
    except Exception as e:
        logger.error(f"Error getting quote asset balance for {quote_asset}: {e}")
        return None

def get_significant_digits(number_str: str) -> int:
    """Calculates significant decimal places."""
    if '.' in number_str:
        cleaned = number_str.rstrip('0')
        return len(cleaned.split('.')[-1]) if '.' in cleaned else 0
    return 0

def adjust_price(price: Decimal, symbol_filters: Dict[str, Dict[str, Any]]) -> Decimal:
    """Adjusts price according to PRICE_FILTER (tickSize)."""
    price_filter = symbol_filters.get('PRICE_FILTER')
    adjusted_price = price
    min_price_limit = Decimal('-Infinity') # Default no min limit
    max_price_limit = Decimal('Infinity')  # Default no max limit

    if price_filter:
        min_price_limit = decimal_context.create_decimal(price_filter.get('minPrice', '0'))
        max_price_limit = decimal_context.create_decimal(price_filter.get('maxPrice', 'inf'))
        tick_size_str = price_filter.get('tickSize')

        if tick_size_str:
            try:
                tick_size = decimal_context.create_decimal(tick_size_str)
                if tick_size > 0:
                    # Quantize to the tick size, rounding down (usually safer for limits)
                    adjusted_price = (price / tick_size).quantize(Decimal('1'), rounding=ROUND_DOWN) * tick_size
            except (InvalidOperation, TypeError) as e:
                logger.warning(f"Could not apply tick_size {tick_size_str} to price {price}: {e}")

    # Ensure price respects min/max limits after adjustment
    if adjusted_price < min_price_limit:
        logger.warning(f"Adjusted price {adjusted_price} below minPrice {min_price_limit}. Clamping.")
        adjusted_price = min_price_limit
    if adjusted_price > max_price_limit:
         logger.warning(f"Adjusted price {adjusted_price} above maxPrice {max_price_limit}. Clamping.")
         adjusted_price = max_price_limit


    # Ensure price doesn't become zero or negative if it was positive, unless minPrice allows it
    if price > 0 and adjusted_price <= 0 and min_price_limit > 0:
        logger.warning(f"Adjusted price became <= 0 for {price}. Using minPrice {min_price_limit}.")
        adjusted_price = min_price_limit

    return adjusted_price

def adjust_quantity(quantity: Decimal, symbol_filters: Dict[str, Dict[str, Any]]) -> Decimal:
    """Adjusts quantity according to LOT_SIZE filter (stepSize, minQty, maxQty)."""
    lot_filter = symbol_filters.get('LOT_SIZE')
    adjusted_quantity = quantity
    min_qty_limit = Decimal('0') # Default min quantity
    max_qty_limit = Decimal('Infinity') # Default max quantity

    if lot_filter:
        min_qty_limit = decimal_context.create_decimal(lot_filter.get('minQty', '0'))
        max_qty_limit = decimal_context.create_decimal(lot_filter.get('maxQty', 'inf'))
        step_size_str = lot_filter.get('stepSize')

        if step_size_str:
            try:
                step_size = decimal_context.create_decimal(step_size_str)
                if step_size > 0:
                    # Quantize to the step size, rounding down
                    adjusted_quantity = (quantity / step_size).quantize(Decimal('1'), rounding=ROUND_DOWN) * step_size
                    logger.debug(f"Applied step_size {step_size_str}, adjusted quantity: {adjusted_quantity}")
            except (InvalidOperation, TypeError) as e:
                logger.warning(f"Could not apply step_size {step_size_str} to quantity {quantity}: {e}")

    # Ensure quantity respects min/max limits after adjustment
    if adjusted_quantity < min_qty_limit:
         logger.warning(f"Adjusted quantity {adjusted_quantity} below minQty {min_qty_limit}. Clamping to 0 (or minQty?).")
         # Clamping to 0 might be safer if the intent was invalid, rather than forcing minQty.
         adjusted_quantity = Decimal(0)
         # Alternatively, clamp to min_qty_limit, but this might place an unintended order.
         # adjusted_quantity = min_qty_limit
    if adjusted_quantity > max_qty_limit:
          logger.warning(f"Adjusted quantity {adjusted_quantity} above maxQty {max_qty_limit}. Clamping.")
          adjusted_quantity = max_qty_limit

    # Ensure quantity doesn't become zero if it was positive, unless minQty allows it
    if quantity > 0 and adjusted_quantity <= 0 and min_qty_limit > 0:
        logger.warning(f"Adjusted quantity became <= 0 for {quantity}. Returning 0.")
        adjusted_quantity = Decimal(0)

    return adjusted_quantity

def format_decimal(value: Decimal, symbol_filters: Dict[str, Dict[str, Any]], filter_type: str) -> str:
    """Formats a Decimal value (price or quantity) according to its filter's precision."""
    precision = 8 # Default precision
    filter_data = symbol_filters.get(filter_type)
    size_key = 'tickSize' if filter_type == 'PRICE_FILTER' else 'stepSize' if filter_type == 'LOT_SIZE' else None

    if filter_data and size_key and size_key in filter_data:
        size_str = filter_data[size_key]
        try:
            # Attempt to calculate precision from the size string
            precision = get_significant_digits(size_str)
        except Exception as e:
            logger.warning(f"Could not determine precision from {size_key} '{size_str}': {e}. Using default {precision}.")

    # Format the value to the determined precision, avoiding scientific notation for common ranges
    try:
        # Use quantize for proper rounding based on precision
        quantizer = Decimal('1e-' + str(precision))
        formatted_value = str(value.quantize(quantizer, rounding=ROUND_DOWN).normalize()) # Use normalize to remove trailing zeros
        return formatted_value
    except Exception as e:
        logger.error(f"Error formatting decimal {value} with precision {precision}: {e}")
        # Fallback to simple string conversion or normalize
        return str(value.normalize())


def format_trade_history(trades: list, limit: int = 20) -> str:
    """Formats a list of trades into a readable string."""
    if not trades: return "لا توجد صفقات مسجلة تطابق البحث."
    text = "📜 <b>سجل الصفقات (الأحدث أولاً):</b>\n\n"; count = 0
    for trade in reversed(trades): # Show most recent first
        if count >= limit: text += f"\n... (تم عرض آخر {limit} صفقة)"; break
        try:
            dt_object = datetime.fromtimestamp(trade['time'] / 1000)
            time_str = dt_object.strftime('%Y-%m-%d %H:%M:%S')
            side_emoji = "📈" if trade.get('isBuyer') else "📉"
            side_text = "شراء" if trade.get('isBuyer') else "بيع"
            symbol = trade.get('symbol', 'N/A')
            qty_str = trade.get('qty', '0')
            price_str = trade.get('price', '0')
            quote_qty_str = trade.get('quoteQty', '0')
            commission_str = trade.get('commission', '0')
            commission_asset = trade.get('commissionAsset', '')

            # Use Decimal for calculations and formatting where appropriate
            qty = decimal_context.create_decimal(qty_str).normalize()
            price = decimal_context.create_decimal(price_str).normalize()
            quote_qty = decimal_context.create_decimal(quote_qty_str).normalize()
            commission = decimal_context.create_decimal(commission_str).normalize()

            text += f"{side_emoji} <b>{symbol}</b> - {side_text}\n"
            # Use :f formatting for potentially simpler output if normalize causes issues
            text += f"  الكمية: {qty:f}\n  السعر: {price:f}\n  الإجمالي: {quote_qty:f} {symbol.replace(trade.get('baseAsset',''),'')}\n"
            if commission > 0: text += f"  العمولة: {commission:f} {commission_asset}\n"
            text += f"  الوقت: {time_str}\n"
            text += f"  <i>ID: {trade.get('id')}</i>\n---\n"
            count += 1
        except Exception as e:
            logger.error(f"خطأ في تنسيق الصفقة {trade.get('id')}: {e}")
            text += f"<i>خطأ في عرض الصفقة ID: {trade.get('id')}</i>\n---\n"
    return text

def format_market_movers(movers: list, title: str, limit: int = 10) -> str:
    """Formats market movers (gainers/losers/search results) into a readable string."""
    if not movers: return f"لم يتم العثور على بيانات لـ {title} حاليًا."
    text = f"📊 <b>{title} (آخر 24 ساعة):</b>\n\n"; count = 0
    for mover in movers:
        if count >= limit: break
        try:
            symbol = mover.get('symbol', 'N/A')
            change_percent_str = mover.get('priceChangePercent', '0')
            last_price_str = mover.get('lastPrice', '0')
            change_percent = decimal_context.create_decimal(change_percent_str)
            last_price = decimal_context.create_decimal(last_price_str).normalize()
            emoji = "⬆️" if change_percent > 0 else "⬇️" if change_percent < 0 else "➡️"
            text += f"{count + 1}. {emoji} <b>{symbol}</b>: {change_percent:+.2f}% (السعر: {last_price:f})\n"
            count += 1
        except Exception as e:
            logger.error(f"خطأ في تنسيق بيانات السوق لـ {mover.get('symbol')}: {e}")
    if count == 0: return f"لم يتم العثور على بيانات لـ {title} حاليًا." # Should be caught earlier, but as safety
    return text


# --- بناء لوحات المفاتيح (Keyboards) ---
def build_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Builds the main menu keyboard."""
    keyboard = [
        [InlineKeyboardButton("📊 التداول", callback_data=CALLBACK_GOTO_TRADING)],
        [InlineKeyboardButton("⭐ المفضلة", callback_data=CALLBACK_GOTO_FAVORITES)],
        [InlineKeyboardButton("🔍 بحث عن عملة", callback_data=CALLBACK_GOTO_SEARCH)],
        [InlineKeyboardButton("💼 الحساب", callback_data=CALLBACK_GOTO_ACCOUNT)],
        [InlineKeyboardButton("📜 سجل التداول", callback_data=CALLBACK_GOTO_HISTORY)],
        [InlineKeyboardButton("⚙️ الإعدادات", callback_data=CALLBACK_GOTO_SETTINGS)], # زر جديد
        [InlineKeyboardButton("❓ المساعدة", callback_data=CALLBACK_SHOW_HELP)],
    ]
    return InlineKeyboardMarkup(keyboard)

def build_trading_menu_keyboard() -> InlineKeyboardMarkup:
    """Builds the trading menu keyboard."""
    keyboard = [
        [ InlineKeyboardButton("📈 شراء", callback_data=CALLBACK_START_BUY),
          InlineKeyboardButton("📉 بيع", callback_data=CALLBACK_START_SELL), ],
        [InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data=CALLBACK_MAIN_MENU)], ]
    return InlineKeyboardMarkup(keyboard)

def build_account_menu_keyboard() -> InlineKeyboardMarkup:
    """Builds the account menu keyboard."""
    keyboard = [
        [InlineKeyboardButton("💰 عرض الرصيد", callback_data=CALLBACK_SHOW_BALANCE)],
        [InlineKeyboardButton("📋 الأوامر المفتوحة", callback_data=CALLBACK_SHOW_ORDERS)],
        # [InlineKeyboardButton("📊 الأرباح والخسائر (قيد التطوير)", callback_data=CALLBACK_SHOW_PNL)],
        [InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data=CALLBACK_MAIN_MENU)],
    ]
    return InlineKeyboardMarkup(keyboard)

def build_search_menu_keyboard() -> InlineKeyboardMarkup:
    """Builds the search menu keyboard."""
    keyboard = [
        [InlineKeyboardButton("⬆️ الأكثر ربحاً", callback_data=CALLBACK_SHOW_GAINERS)],
        [InlineKeyboardButton("⬇️ الأكثر خسارة", callback_data=CALLBACK_SHOW_LOSERS)],
        [InlineKeyboardButton("⌨️ بحث يدوي عن عملة", callback_data=CALLBACK_SEARCH_MANUAL_START)],
        [InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data=CALLBACK_MAIN_MENU)],
    ]
    return InlineKeyboardMarkup(keyboard)

def build_history_menu_keyboard() -> InlineKeyboardMarkup:
    """Builds the trade history menu keyboard."""
    keyboard = [
        [InlineKeyboardButton("📅 صفقات اليوم", callback_data=CALLBACK_HISTORY_TODAY)],
        [InlineKeyboardButton("🪙 صفقات عملة محددة", callback_data=CALLBACK_HISTORY_BY_PAIR_START)],
        [InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data=CALLBACK_MAIN_MENU)], ]
    return InlineKeyboardMarkup(keyboard)

def build_cancel_keyboard(callback_data=CALLBACK_CANCEL) -> InlineKeyboardMarkup:
    """Builds a simple cancel button keyboard."""
    keyboard = [[InlineKeyboardButton("❌ إلغاء", callback_data=callback_data)]]
    return InlineKeyboardMarkup(keyboard)

def build_sltp_choice_keyboard() -> InlineKeyboardMarkup:
    """Builds the keyboard for choosing SL/TP method."""
    keyboard = [
         [ InlineKeyboardButton("SL/TP %", callback_data=CALLBACK_ADD_SLTP_PERCENT),
           InlineKeyboardButton("SL/TP يدوي", callback_data=CALLBACK_ADD_SLTP_YES), ],
         [ InlineKeyboardButton("لا، تخطَّ SL/TP", callback_data=CALLBACK_ADD_SLTP_NO), ],
         [InlineKeyboardButton("❌ إلغاء العملية بالكامل", callback_data=CALLBACK_CANCEL_TRADE)],
     ]
    return InlineKeyboardMarkup(keyboard)

def build_percent_keyboard(prefix: str, percentages: List[int] = [1, 2, 3, 5]) -> InlineKeyboardMarkup: # Added 5%
    """Builds a keyboard with percentage options."""
    keyboard = []; row = []
    for perc in percentages:
        row.append(InlineKeyboardButton(f"{perc}%", callback_data=f"{prefix}{perc}"))
        if len(row) == 4: # Adjust number per row if needed
             keyboard.append(row)
             row = []
    if row: keyboard.append(row)
    keyboard.append([InlineKeyboardButton("❌ إلغاء العملية", callback_data=CALLBACK_CANCEL_TRADE)])
    return InlineKeyboardMarkup(keyboard)

def build_sell_asset_keyboard(balances: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """Builds the keyboard for selecting an asset to sell."""
    keyboard = []
    # Display a limited number of assets as buttons (e.g., top 6 by value)
    for i, balance in enumerate(balances[:6]):
        asset = balance['asset']
        free_qty = balance['free'].normalize()
        value_usdt = balance.get('value_usdt')
        value_text = f" (${value_usdt:.2f})" if value_usdt and value_usdt > 0 else ""
        # Format quantity appropriately (consider significant digits)
        qty_display = f"{free_qty:f}" if free_qty < 1000 else f"{free_qty:.4f}" # Basic formatting
        button_text = f"{asset} ({qty_display}{value_text})"
        callback = f"{CALLBACK_SELL_ASSET_PREFIX}{asset}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback)])

    # Add pagination buttons here if needed for more assets
    keyboard.append([InlineKeyboardButton("🔙 رجوع لقائمة التداول", callback_data=CALLBACK_GOTO_TRADING)])
    return InlineKeyboardMarkup(keyboard)

def build_sell_amount_keyboard() -> InlineKeyboardMarkup:
    """Builds the keyboard for choosing sell amount (all/partial)."""
    keyboard = [
        [ InlineKeyboardButton("💰 بيع الكمية كلها", callback_data=CALLBACK_SELL_AMOUNT_ALL),
          InlineKeyboardButton(" جزء من الكمية", callback_data=CALLBACK_SELL_AMOUNT_PARTIAL), ],
        [InlineKeyboardButton("❌ إلغاء العملية", callback_data=CALLBACK_CANCEL_TRADE)],
    ]
    return InlineKeyboardMarkup(keyboard)

def build_favorites_menu_keyboard(favorites: Set[str]) -> Tuple[InlineKeyboardMarkup, str]:
    """Builds the favorites menu keyboard and text."""
    keyboard = []
    text = ""
    if favorites:
        text = "⭐ الأزواج المفضلة لديك (اضغط للشراء):"
        fav_list = sorted(list(favorites))
        row = []
        for pair in fav_list:
            row.append(InlineKeyboardButton(f"{pair}", callback_data=f"{CALLBACK_BUY_FAVORITE_PREFIX}{pair}"))
            if len(row) == 3: # 3 buttons per row
                keyboard.append(row)
                row = []
        if row: keyboard.append(row)
    else:
        text = "قائمة المفضلة فارغة حاليًا."

    keyboard.append([
        InlineKeyboardButton("➕ إضافة للمفضلة", callback_data=CALLBACK_ADD_FAVORITE_START),
        InlineKeyboardButton("➖ إزالة من المفضلة", callback_data=CALLBACK_REMOVE_FAVORITE_START)
    ])
    keyboard.append([InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data=CALLBACK_MAIN_MENU)])
    return InlineKeyboardMarkup(keyboard), text

def build_remove_favorite_keyboard(favorites: Set[str]) -> InlineKeyboardMarkup:
    """Builds the keyboard for removing a favorite pair."""
    keyboard = []
    if not favorites:
        keyboard.append([InlineKeyboardButton("لا يوجد مفضلة للإزالة", callback_data="none")]) # Placeholder callback
    else:
        fav_list = sorted(list(favorites))
        row = []
        for pair in fav_list:
            row.append(InlineKeyboardButton(f"❌ {pair}", callback_data=f"{CALLBACK_REMOVE_FAVORITE_PREFIX}{pair}"))
            if len(row) == 3:
                keyboard.append(row)
                row = []
        if row: keyboard.append(row)

    keyboard.append([InlineKeyboardButton("🔙 رجوع لقائمة المفضلة", callback_data=CALLBACK_GOTO_FAVORITES)])
    return InlineKeyboardMarkup(keyboard)

def build_buy_favorites_keyboard(favorites: Set[str]) -> InlineKeyboardMarkup:
    """Builds the keyboard for buying from favorites."""
    keyboard = []
    fav_list = sorted(list(favorites))
    row = []
    # Display a limited number of buttons
    for pair in fav_list[:MAX_FAVORITE_BUTTONS]:
         row.append(InlineKeyboardButton(f"📈 {pair}", callback_data=f"{CALLBACK_BUY_FAVORITE_PREFIX}{pair}"))
         if len(row) == 2: # 2 buttons per row
              keyboard.append(row)
              row = []
    if row: keyboard.append(row)

    keyboard.append([InlineKeyboardButton("⌨️ إدخال زوج آخر...", callback_data=CALLBACK_BUY_OTHER_PAIR)])
    keyboard.append([InlineKeyboardButton("🔙 رجوع لقائمة التداول", callback_data=CALLBACK_GOTO_TRADING)])
    return InlineKeyboardMarkup(keyboard)

def build_settings_menu_keyboard(context: ContextTypes.DEFAULT_TYPE) -> InlineKeyboardMarkup:
    """Builds the settings menu keyboard."""
    user_id = context._user_id # Get user ID for user-specific settings
    max_buy = context.user_data.get('max_buy_usdt', DEFAULT_MAX_BUY_USDT)
    keyboard = [
        [InlineKeyboardButton(f"💰 حد الشراء الأقصى (${max_buy:.2f})", callback_data=CALLBACK_SET_MAX_BUY_START)],
        # Add other settings buttons here (e.g., default SL/TP %)
        [InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data=CALLBACK_MAIN_MENU)],
    ]
    return InlineKeyboardMarkup(keyboard)


# --- دوال عرض القوائم والمعلومات ---
async def _send_or_edit(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    parse_mode: Optional[str] = ParseMode.HTML,
    edit: bool = True
) -> None:
    """Helper function to send or edit a message, handling potential errors."""
    chat_id = update.effective_chat.id
    message_id = update.effective_message.message_id if update.effective_message else None
    query = update.callback_query

    try:
        if edit and query and message_id:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        elif query and not edit: # Send new message after callback
             await context.bot.send_message(
                 chat_id=chat_id,
                 text=text,
                 reply_markup=reply_markup,
                 parse_mode=parse_mode
             )
        elif update.message: # Reply to a command/message
            await update.message.reply_html(text, reply_markup=reply_markup)
        elif chat_id: # Fallback send if no query/message
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
    except TelegramError as e:
        logger.warning(f"Telegram Error sending/editing message: {e}")
        # Handle specific errors like "message is not modified" silently
        if "message is not modified" in str(e).lower():
            pass # Ignore this specific error
        elif chat_id: # Attempt fallback send for other errors
             try:
                  await context.bot.send_message(
                       chat_id=chat_id,
                       text=text, # Send original text on error
                       reply_markup=reply_markup,
                       parse_mode=parse_mode
                  )
             except Exception as send_e:
                  logger.error(f"Fallback send failed: {send_e}")
    except Exception as e:
         logger.error(f"Generic error sending/editing message: {e}", exc_info=True)
         # Attempt fallback send
         if chat_id:
              try:
                   await context.bot.send_message(chat_id=chat_id, text="حدث خطأ أثناء عرض الرسالة.", reply_markup=build_main_menu_keyboard())
              except Exception as send_e:
                   logger.error(f"Fallback send after generic error failed: {send_e}")


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, edit_message: bool = True) -> None:
    """Displays the main menu."""
    text = "القائمة الرئيسية. اختر أحد الخيارات:"; keyboard = build_main_menu_keyboard()
    await _send_or_edit(update, context, text, keyboard, edit=edit_message)

async def show_trading_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the trading menu."""
    text = "قائمة التداول. اختر العملية:"; keyboard = build_trading_menu_keyboard()
    await _send_or_edit(update, context, text, keyboard, edit=True)

async def show_account_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the account menu."""
    text = "قائمة الحساب. اختر الإجراء:"; keyboard = build_account_menu_keyboard()
    await _send_or_edit(update, context, text, keyboard, edit=True)

async def show_search_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the search menu."""
    text = "قائمة البحث عن العملات. اختر الإجراء:"; keyboard = build_search_menu_keyboard()
    await _send_or_edit(update, context, text, keyboard, edit=True)

async def show_history_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the history menu."""
    text = "قائمة سجل التداول. اختر الإجراء:"; keyboard = build_history_menu_keyboard()
    await _send_or_edit(update, context, text, keyboard, edit=True)

async def show_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the settings menu."""
    text = "⚙️ قائمة الإعدادات:"
    keyboard = build_settings_menu_keyboard(context)
    await _send_or_edit(update, context, text, keyboard, edit=True)


async def show_placeholder_message(update: Update, context: ContextTypes.DEFAULT_TYPE, feature_name: str) -> None:
    """Displays a placeholder message for features under development."""
    query = update.callback_query
    if query: await query.answer(f"{feature_name} (قيد التطوير)")
    text = f"🚧 ميزة \"{feature_name}\" قيد التطوير حاليًا وستتوفر قريبًا."
    back_callback = CALLBACK_MAIN_MENU # Default back button
    # Try to determine the correct back button based on context
    # This logic might need refinement depending on how placeholders are accessed
    if query and query.message and query.message.reply_markup and query.message.reply_markup.inline_keyboard:
         # Look for a back button in the previous message's keyboard
         for row in query.message.reply_markup.inline_keyboard:
              for button in row:
                   if "رجوع" in button.text:
                        back_callback = button.callback_data
                        break
              if back_callback != CALLBACK_MAIN_MENU: break

    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data=back_callback)]]
    await _send_or_edit(update, context, text, InlineKeyboardMarkup(keyboard), edit=True)


async def show_help_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the help text."""
    query = update.callback_query
    if query: await query.answer()
    help_text = """
<b>المساعدة العامة:</b>
- استخدم الأزرار للتنقل وتنفيذ الإجراءات.
- عند بدء شراء أو بيع، اتبع تعليمات البوت وتحقق من القيود.
- يمكنك إضافة إيقاف خسارة (SL) وجني أرباح (TP) اختياريًا.
- /start للعودة للقائمة الرئيسية.
- /cancel لإلغاء أي عملية جارية.
- /settings للوصول إلى الإعدادات.

<b>الأوامر النصية:</b>
/start, /help, /balance [asset], /orders [pair], /cancel, /settings

<b>تحذير:</b> التداول ينطوي على مخاطر. استخدم البوت على مسؤوليتك.
"""
    keyboard = [[InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data=CALLBACK_MAIN_MENU)]]
    await _send_or_edit(update, context, help_text, InlineKeyboardMarkup(keyboard), edit=True, parse_mode=ParseMode.HTML)


async def show_balance_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays account balance information."""
    query = update.callback_query
    if query: await query.answer()
    chat_id = update.effective_chat.id
    if not binance_client:
        await _send_or_edit(update, context, "⚠️ عذرًا، اتصال Binance غير متاح حاليًا.", edit=bool(query))
        return

    loading_message = None
    if query:
        try:
            # Send "typing" action instead of editing to loading message
            await context.bot.send_chat_action(chat_id=chat_id, action='typing')
        except Exception as e: logger.debug(f"Failed to send typing action: {e}")
    else:
        loading_message = await context.bot.send_message(chat_id=chat_id, text="⏳ جاري جلب الرصيد...")

    asset_filter = context.args[0].upper() if context.args and not query else None
    logger.info(f"Requesting balance for {asset_filter or 'all assets'}")
    try:
        significant_balances = await get_account_balances(context) # Uses updated function
        balance_message = "<b>أرصدة Binance (ذات قيمة):</b>\n\n"; found_asset = False; non_zero_balances = bool(significant_balances)

        for asset_info in significant_balances:
            asset_name = asset_info['asset']
            if asset_filter is None or asset_name == asset_filter:
                found_asset = True
                total = asset_info['total'].normalize()
                free = asset_info['free'].normalize()
                locked = asset_info['locked'].normalize()
                value_usdt = asset_info['value_usdt']
                value_text = f" (≈ ${value_usdt:.2f})" if value_usdt > 0 else ""
                balance_message += (f"<b>{asset_name}:</b> {total:f}{value_text}\n"
                                    f"  (متاح: {free:f}, محجوز: {locked:f})\n")

        final_text = ""
        if not non_zero_balances: final_text = "لا يوجد لديك أرصدة ذات قيمة معتبرة."
        elif asset_filter and not found_asset: final_text = f"لم يتم العثور على رصيد للأصل: {asset_filter}"
        else: final_text = balance_message
        if len(final_text) > 4000: final_text = final_text[:4000] + "\n...(المزيد)"

        keyboard = [[InlineKeyboardButton("🔙 رجوع لقائمة الحساب", callback_data=CALLBACK_GOTO_ACCOUNT)]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Edit the original message if it was a callback, otherwise send new
        await _send_or_edit(update, context, final_text, reply_markup, edit=bool(query))
        # Delete loading message if it was sent separately
        if loading_message and not query:
             try: await context.bot.delete_message(chat_id=chat_id, message_id=loading_message.message_id)
             except Exception: pass

    except (BinanceAPIException, BinanceRequestException) as e:
         logger.error(f"Binance API Error showing balance: {e}")
         error_text = f"⚠️ حدث خطأ من Binance أثناء جلب الرصيد:\n<code>{e.message}</code>"
         keyboard = [[InlineKeyboardButton("🔙 رجوع لقائمة الحساب", callback_data=CALLBACK_GOTO_ACCOUNT)]]
         await _send_or_edit(update, context, error_text, InlineKeyboardMarkup(keyboard), edit=bool(query), parse_mode=ParseMode.HTML)
         if loading_message and not query:
              try: await context.bot.delete_message(chat_id=chat_id, message_id=loading_message.message_id)
              except Exception: pass

    except Exception as e:
        logger.error(f"خطأ عام عند عرض الرصيد: {e}", exc_info=True)
        error_text = "⚠️ حدث خطأ غير متوقع أثناء عرض الرصيد."
        keyboard = [[InlineKeyboardButton("🔙 رجوع لقائمة الحساب", callback_data=CALLBACK_GOTO_ACCOUNT)]]
        await _send_or_edit(update, context, error_text, InlineKeyboardMarkup(keyboard), edit=bool(query))
        if loading_message and not query:
             try: await context.bot.delete_message(chat_id=chat_id, message_id=loading_message.message_id)
             except Exception: pass


async def show_orders_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays open orders information with cancel buttons."""
    query = update.callback_query
    if query: await query.answer()
    chat_id = update.effective_chat.id
    if not binance_client:
        await _send_or_edit(update, context, "⚠️ عذرًا، اتصال Binance غير متاح حاليًا.", edit=bool(query))
        return

    loading_message = None
    if query:
        try: await context.bot.send_chat_action(chat_id=chat_id, action='typing')
        except Exception as e: logger.debug(f"Failed to send typing action: {e}")
    else:
        loading_message = await context.bot.send_message(chat_id=chat_id, text="⏳ جاري جلب الأوامر المفتوحة...")

    symbol_filter = context.args[0].upper() if context.args and not query else None
    logger.info(f"Requesting open orders for {symbol_filter or 'all symbols'}")
    try:
        open_orders = binance_client.get_open_orders(symbol=symbol_filter) if symbol_filter else binance_client.get_open_orders()
        final_text = ""
        keyboard_rows = [] # Build keyboard dynamically

        if not open_orders:
            message = "لا توجد أوامر مفتوحة حاليًا"; final_text = message + (f" للزوج {symbol_filter}." if symbol_filter else ".")
            keyboard_rows.append([InlineKeyboardButton("🔄 تحديث", callback_data=CALLBACK_SHOW_ORDERS)]) # Add refresh button
        else:
            orders_text = f"<b>الأوامر المفتوحة{' لـ ' + symbol_filter if symbol_filter else ''}:</b>\n\n"
            # Limit the number of orders displayed with buttons to avoid exceeding Telegram limits
            orders_with_buttons_count = 0
            max_orders_with_buttons = 10 # Limit cancel buttons to first 10 orders shown

            for order in open_orders:
                try:
                    symbol = order['symbol']
                    filters = get_symbol_filters(symbol, context) # Use cached filters
                    orig_qty = decimal_context.create_decimal(order['origQty'])
                    exec_qty = decimal_context.create_decimal(order['executedQty'])
                    price = decimal_context.create_decimal(order.get('price','0'))
                    stop_price = decimal_context.create_decimal(order.get('stopPrice','0'))
                    order_id = order['orderId']
                    order_type = order['type'].replace('_', ' ').title() # Nicer formatting
                    order_side = order['side'].title()
                    order_status = order['status'].title()

                    order_time = datetime.fromtimestamp(order['time'] / 1000).strftime('%H:%M:%S')
                    orders_text += (f"🆔 {order_id} | {symbol} | {order_side} | {order_type}\n"
                                    f"  Qty:{format_decimal(orig_qty, filters, 'LOT_SIZE')} | "
                                    f"Price:{format_decimal(price, filters, 'PRICE_FILTER') if price>0 else 'Market'} | "
                                    f"Exec:{format_decimal(exec_qty, filters, 'LOT_SIZE')}\n")
                    if stop_price > 0:
                         orders_text += f"  Stop:{format_decimal(stop_price, filters, 'PRICE_FILTER')} | "
                    orders_text += f"Status:{order_status} | Time: {order_time}\n"

                    # Add Cancel Button if within limit
                    if orders_with_buttons_count < max_orders_with_buttons:
                         cancel_callback_data = f"{CALLBACK_CANCEL_ORDER_PREFIX}{symbol}_{order_id}"
                         orders_text += f"[ <a href='tg://btn/{cancel_callback_data}'>إلغاء الأمر {order_id}</a> ]\n" # Inline link style (might not work everywhere)
                         # Alternative: Add button row
                         keyboard_rows.append([InlineKeyboardButton(f"❌ إلغاء الأمر {order_id} ({symbol})", callback_data=cancel_callback_data)])
                         orders_with_buttons_count += 1
                    else:
                         orders_text += "(إلغاء المزيد من الأوامر غير متاح في هذه الرسالة)\n"


                    orders_text += "---\n"
                except Exception as format_e:
                     logger.error(f"Error formatting order {order.get('orderId')}: {format_e}")
                     orders_text += f"<i>خطأ في عرض الأمر ID: {order.get('orderId')}</i>\n---\n"


            if len(orders_text) > 4000: orders_text = orders_text[:4000] + "\n...(المزيد)"
            final_text = orders_text
            if len(open_orders) > max_orders_with_buttons:
                 final_text += f"\n<i>(يتم عرض أزرار الإلغاء لأول {max_orders_with_buttons} أمر فقط.)</i>"
            keyboard_rows.append([InlineKeyboardButton("🔄 تحديث القائمة", callback_data=CALLBACK_SHOW_ORDERS)]) # Add refresh button

        keyboard_rows.append([InlineKeyboardButton("🔙 رجوع لقائمة الحساب", callback_data=CALLBACK_GOTO_ACCOUNT)])
        reply_markup = InlineKeyboardMarkup(keyboard_rows)

        await _send_or_edit(update, context, final_text, reply_markup, edit=bool(query), parse_mode=ParseMode.HTML)
        if loading_message and not query:
             try: await context.bot.delete_message(chat_id=chat_id, message_id=loading_message.message_id)
             except Exception: pass

    except (BinanceAPIException, BinanceRequestException) as e:
         logger.error(f"Binance API Error fetching open orders: {e}")
         error_text = f"⚠️ حدث خطأ من Binance أثناء جلب الأوامر:\n<code>{e.message}</code>"
         keyboard = [[InlineKeyboardButton("🔄 تحديث", callback_data=CALLBACK_SHOW_ORDERS)], [InlineKeyboardButton("🔙 رجوع لقائمة الحساب", callback_data=CALLBACK_GOTO_ACCOUNT)]]
         await _send_or_edit(update, context, error_text, InlineKeyboardMarkup(keyboard), edit=bool(query), parse_mode=ParseMode.HTML)
         if loading_message and not query:
              try: await context.bot.delete_message(chat_id=chat_id, message_id=loading_message.message_id)
              except Exception: pass
    except Exception as e:
        logger.error(f"خطأ عام عند جلب الأوامر: {e}", exc_info=True)
        error_text = "⚠️ حدث خطأ غير متوقع أثناء جلب الأوامر المفتوحة."
        keyboard = [[InlineKeyboardButton("🔄 تحديث", callback_data=CALLBACK_SHOW_ORDERS)],[InlineKeyboardButton("🔙 رجوع لقائمة الحساب", callback_data=CALLBACK_GOTO_ACCOUNT)]]
        await _send_or_edit(update, context, error_text, InlineKeyboardMarkup(keyboard), edit=bool(query))
        if loading_message and not query:
             try: await context.bot.delete_message(chat_id=chat_id, message_id=loading_message.message_id)
             except Exception: pass


# --- معالجات الأوامر النصية ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command."""
    # Check if user is in a conversation and cancel it
    # This requires knowing the conversation names or checking state keys
    # A simpler approach is not needed if fallbacks handle /start correctly
    # active_conversations = [key for key in context.user_data if key.startswith(('trade_', 'history_', 'search_', 'fav_', 'settings_'))]
    # if active_conversations:
    #     logger.info("Clearing previous conversation state on /start")
    #     await cancel_conversation(update, context, "العملية السابقة", clear_only=True)
    await show_main_menu(update, context, edit_message=False)

async def help_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /help command."""
    await show_help_text(update, context)

async def balance_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /balance command."""
    await show_balance_info(update, context)

async def orders_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /orders command."""
    await show_orders_info(update, context)

async def settings_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /settings command."""
    await show_settings_menu(update, context)


# --- معالج ردود الأزرار الرئيسية وقوائم التنقل ---
async def navigation_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles main navigation button presses."""
    query = update.callback_query
    if not query: return
    callback_data = query.data
    logger.info(f"Navigation button pressed: {callback_data}")
    await query.answer() # Acknowledge callback quickly

    if callback_data == CALLBACK_MAIN_MENU: await show_main_menu(update, context, edit_message=True)
    elif callback_data == CALLBACK_GOTO_TRADING: await show_trading_menu(update, context)
    elif callback_data == CALLBACK_GOTO_ACCOUNT: await show_account_menu(update, context)
    elif callback_data == CALLBACK_GOTO_SEARCH: await show_search_menu(update, context)
    elif callback_data == CALLBACK_GOTO_HISTORY: await show_history_menu(update, context)
    elif callback_data == CALLBACK_GOTO_FAVORITES: await show_favorites_menu(update, context)
    elif callback_data == CALLBACK_GOTO_SETTINGS: await show_settings_menu(update, context)
    elif callback_data == CALLBACK_SHOW_HELP: await show_help_text(update, context)
    elif callback_data == CALLBACK_SHOW_BALANCE: await show_balance_info(update, context)
    elif callback_data == CALLBACK_SHOW_ORDERS: await show_orders_info(update, context)
    else: logger.warning(f"Unknown navigation callback_data: {callback_data}")


# --- وظائف جلب بيانات السوق وعرضها ---
async def fetch_and_get_market_movers(context: ContextTypes.DEFAULT_TYPE, quote_asset: str = 'USDT', limit: int = 10, sort_key: str = 'priceChangePercent') -> List[Dict[str, Any]]:
    """Fetches and sorts market movers based on 24hr ticker data."""
    if not binance_client: return []
    try:
        # Fetch 24hr ticker data which includes priceChangePercent
        tickers_24hr = binance_client.get_ticker() # Fetches all tickers
        movers = []
        for ticker in tickers_24hr:
            symbol = ticker['symbol']
            if symbol.endswith(quote_asset):
                try:
                    movers.append({
                        'symbol': symbol,
                        'priceChangePercent': decimal_context.create_decimal(ticker['priceChangePercent']),
                        'lastPrice': decimal_context.create_decimal(ticker['lastPrice'])
                        # Add other fields like 'volume' if needed
                    })
                except (InvalidOperation, KeyError, TypeError) as e:
                     logger.warning(f"Skipping ticker {symbol} due to data issue: {e}")

        # Sort by the specified key (default: priceChangePercent)
        movers.sort(key=lambda x: x.get(sort_key, Decimal(0)), reverse=True) # reverse=True for gainers
        return movers # Return sorted list, limit applied by caller
    except (BinanceAPIException, BinanceRequestException) as e:
        logger.error(f"Binance API Error fetching 24hr tickers: {e}")
        return []
    except Exception as e:
        logger.error(f"Error fetching market movers: {e}", exc_info=True)
        return []

async def show_gainers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays top gainers."""
    query = update.callback_query
    if query: await query.answer()
    await _send_or_edit(update, context, "⏳ جاري جلب الأكثر ارتفاعًا...", edit=bool(query))
    movers = await fetch_and_get_market_movers(context, quote_asset='USDT', sort_key='priceChangePercent')
    # Filter only positive changes for gainers
    gainers = [m for m in movers if m.get('priceChangePercent', Decimal(0)) > 0]
    text = format_market_movers(gainers, "الأكثر ارتفاعاً", limit=10)
    keyboard = [[InlineKeyboardButton("🔙 رجوع لقائمة البحث", callback_data=CALLBACK_GOTO_SEARCH)]]
    await _send_or_edit(update, context, text, InlineKeyboardMarkup(keyboard), edit=True, parse_mode=ParseMode.HTML)

async def show_losers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays top losers."""
    query = update.callback_query
    if query: await query.answer()
    await _send_or_edit(update, context, "⏳ جاري جلب الأكثر انخفاضًا...", edit=bool(query))
    movers = await fetch_and_get_market_movers(context, quote_asset='USDT', sort_key='priceChangePercent')
    # Filter only negative changes and sort ascending (most negative first)
    losers = sorted(
        [m for m in movers if m.get('priceChangePercent', Decimal(0)) < 0],
        key=lambda x: x.get('priceChangePercent', Decimal(0)) # Sort ascending
    )
    text = format_market_movers(losers, "الأكثر انخفاضاً", limit=10)
    keyboard = [[InlineKeyboardButton("🔙 رجوع لقائمة البحث", callback_data=CALLBACK_GOTO_SEARCH)]]
    await _send_or_edit(update, context, text, InlineKeyboardMarkup(keyboard), edit=True, parse_mode=ParseMode.HTML)


# --- وظائف سجل التداول ---
async def show_today_trades(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays trades from the last 24 hours."""
    query = update.callback_query
    if query: await query.answer()
    chat_id = update.effective_chat.id
    if not binance_client:
        await _send_or_edit(update, context, "⚠️ عذرًا، اتصال Binance غير متاح حاليًا.", edit=bool(query))
        return

    await _send_or_edit(update, context, "⏳ جاري جلب صفقات اليوم...", edit=bool(query))
    try:
        # Get trades from the last 24 hours
        start_time_dt = datetime.now() - timedelta(days=1)
        start_time_ms = int(start_time_dt.timestamp() * 1000)
        # Fetch trades for all symbols within the time range (might be slow if many trades)
        # Consider fetching per symbol if needed, but get_my_trades allows time range
        trades = binance_client.get_my_trades(startTime=start_time_ms) # No symbol specified
        text = format_trade_history(trades, limit=50) # Display more trades
        keyboard = [[InlineKeyboardButton("🔙 رجوع لقائمة السجل", callback_data=CALLBACK_GOTO_HISTORY)]]
        await _send_or_edit(update, context, text, InlineKeyboardMarkup(keyboard), edit=True, parse_mode=ParseMode.HTML)

    except (BinanceAPIException, BinanceRequestException) as e:
        logger.error(f"Binance API Error fetching today's trades: {e}")
        error_text = f"⚠️ خطأ من Binance أثناء جلب صفقات اليوم:\n<code>{e.message}</code>"
        await _send_or_edit(update, context, error_text, InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع لقائمة السجل", callback_data=CALLBACK_GOTO_HISTORY)]]), edit=True, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Error showing today's trades: {e}", exc_info=True)
        error_text = "⚠️ حدث خطأ غير متوقع أثناء جلب صفقات اليوم."
        await _send_or_edit(update, context, error_text, InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع لقائمة السجل", callback_data=CALLBACK_GOTO_HISTORY)]]), edit=True)


async def history_by_pair_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the conversation to get history for a specific pair."""
    query = update.callback_query
    if query: await query.answer()
    text = "الرجاء إدخال زوج العملات لعرض سجله (مثال: BTCUSDT):"
    await _send_or_edit(update, context, text, build_cancel_keyboard(CALLBACK_CANCEL), edit=bool(query))
    return H_ASK_PAIR

async def history_ask_pair_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles pair input for trade history and validates it."""
    if not update.message or not update.message.text: return H_ASK_PAIR
    pair = update.message.text.strip().upper()

    # <<-- Validate Symbol -->>
    if not is_valid_symbol(pair, context):
        await update.message.reply_text(f"⚠️ الرمز '{pair}' غير صالح أو غير متداول حاليًا. الرجاء إدخال رمز صحيح:", reply_markup=build_cancel_keyboard(CALLBACK_CANCEL))
        return H_ASK_PAIR

    if not binance_client:
        await update.message.reply_text("⚠️ عذرًا، اتصال Binance غير متاح حاليًا.")
        return ConversationHandler.END

    try:
        # Send typing action while fetching
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
        trades = binance_client.get_my_trades(symbol=pair, limit=50)
        text = format_trade_history(trades, limit=50)
        keyboard = [[InlineKeyboardButton("🔙 رجوع لقائمة السجل", callback_data=CALLBACK_GOTO_HISTORY)]]
        await update.message.reply_html(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except (BinanceAPIException, BinanceRequestException) as e:
         logger.error(f"Binance API Error fetching history for {pair}: {e}")
         await update.message.reply_text(f"⚠️ خطأ من Binance أثناء جلب سجل {pair}:\n<code>{e.message}</code>", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Error showing history for {pair}: {e}", exc_info=True)
        await update.message.reply_text(f"⚠️ حدث خطأ غير متوقع أثناء جلب سجل {pair}.")
    return ConversationHandler.END


# --- وظائف البحث عن عملة ---
async def search_manual_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the manual symbol search conversation."""
    query = update.callback_query
    if query: await query.answer()
    text = "الرجاء إدخال رمز العملة أو جزء منه للبحث (مثال: BTC أو ETHUSDT):"
    await _send_or_edit(update, context, text, build_cancel_keyboard(CALLBACK_CANCEL), edit=bool(query))
    return S_ASK_PAIR

async def search_ask_pair_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles symbol input for search."""
    if not update.message or not update.message.text: return S_ASK_PAIR
    search_term = update.message.text.strip().upper()
    # Basic validation for search term length
    if not (2 <= len(search_term) <= 15):
        await update.message.reply_text("مصطلح البحث قصير جدًا أو طويل جدًا. أعد الإدخال:", reply_markup=build_cancel_keyboard(CALLBACK_CANCEL))
        return S_ASK_PAIR

    if not binance_client:
        await update.message.reply_text("⚠️ عذرًا، اتصال Binance غير متاح حاليًا.")
        return ConversationHandler.END

    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
        # Use cached exchange info for faster filtering
        exchange_info = context.bot_data.get(EXCHANGE_INFO_CACHE_KEY)
        valid_symbols = context.bot_data.get(SYMBOLS_CACHE_KEY, set())
        matches_symbols = set()

        if valid_symbols:
             matches_symbols = {s for s in valid_symbols if search_term in s}
        elif exchange_info: # Fallback if only exchange_info is cached
             matches_symbols = {s['symbol'] for s in exchange_info.get('symbols', []) if s.get('status') == 'TRADING' and search_term in s['symbol']}
        else: # Slowest fallback: fetch all tickers if cache failed
             all_tickers_raw = binance_client.get_symbol_ticker()
             matches_symbols = {t['symbol'] for t in all_tickers_raw if search_term in t['symbol']}


        matches_data = []
        if matches_symbols:
             # Fetch 24hr data only for matching symbols
             # This can still be many API calls if search term is broad
             # Consider limiting the number of symbols to fetch details for
             symbols_to_fetch = list(matches_symbols)[:30] # Limit details fetch
             logger.info(f"Fetching 24hr ticker for {len(symbols_to_fetch)} search matches...")
             try:
                 # Binance API might allow fetching multiple tickers at once? Check documentation.
                 # If not, fetch one by one (can be slow)
                 for symbol in symbols_to_fetch:
                      try:
                           ticker_24hr = binance_client.get_ticker(symbol=symbol)
                           matches_data.append({
                               'symbol': symbol,
                               'priceChangePercent': decimal_context.create_decimal(ticker_24hr.get('priceChangePercent', '0')),
                               'lastPrice': decimal_context.create_decimal(ticker_24hr.get('lastPrice', '0'))
                           })
                      except Exception: # Ignore errors for single symbols during search
                           logger.warning(f"Failed to get 24hr ticker for {symbol} in search.")
                           pass # Optionally add symbol with price 0 or skip
             except (BinanceAPIException, BinanceRequestException) as multi_e:
                  logger.error(f"API error fetching multiple tickers for search: {multi_e}")
                  # Proceed with potentially incomplete data or show error

        if matches_data:
            matches_data.sort(key=lambda x: x['priceChangePercent'], reverse=True)
            text = format_market_movers(matches_data, f"نتائج البحث عن '{search_term}'", limit=20)
        else:
            text = f"لم يتم العثور على أزواج تداول نشطة تحتوي على '{search_term}'."

        keyboard = [[InlineKeyboardButton("🔙 رجوع لقائمة البحث", callback_data=CALLBACK_GOTO_SEARCH)]]
        await update.message.reply_html(text, reply_markup=InlineKeyboardMarkup(keyboard))

    except (BinanceAPIException, BinanceRequestException) as e:
         logger.error(f"Binance API Error searching for {search_term}: {e}")
         await update.message.reply_text(f"⚠️ خطأ من Binance أثناء البحث:\n<code>{e.message}</code>", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Error searching for {search_term}: {e}", exc_info=True)
        await update.message.reply_text(f"⚠️ حدث خطأ غير متوقع أثناء البحث عن {search_term}.")
    return ConversationHandler.END


# --- وظائف قائمة المفضلة ---
async def show_favorites_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the favorites menu."""
    query = update.callback_query
    if query: await query.answer()
    favorites: Set[str] = context.user_data.setdefault('favorite_pairs', set())
    keyboard, text = build_favorites_menu_keyboard(favorites)
    await _send_or_edit(update, context, text, keyboard, edit=bool(query), parse_mode=ParseMode.HTML)

async def add_favorite_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the conversation to add a favorite pair."""
    query = update.callback_query
    if query: await query.answer()
    text = "الرجاء إدخال رمز زوج العملات لإضافته للمفضلة (مثال: BTCUSDT):"
    await _send_or_edit(update, context, text, build_cancel_keyboard(CALLBACK_CANCEL), edit=bool(query))
    return FAV_ASK_ADD_PAIR

async def add_favorite_pair_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles pair input for adding to favorites and validates it."""
    if not update.message or not update.message.text: return FAV_ASK_ADD_PAIR
    pair = update.message.text.strip().upper()

    # <<-- Validate Symbol -->>
    if not is_valid_symbol(pair, context):
         await update.message.reply_text(f"⚠️ الرمز '{pair}' غير صالح أو غير متداول حاليًا. الرجاء إدخال رمز صحيح:", reply_markup=build_cancel_keyboard(CALLBACK_CANCEL))
         return FAV_ASK_ADD_PAIR

    favorites: Set[str] = context.user_data.setdefault('favorite_pairs', set())
    if len(favorites) >= MAX_FAVORITES:
         await update.message.reply_text(f"⚠️ لقد وصلت للحد الأقصى لعدد المفضلة ({MAX_FAVORITES}). قم بإزالة زوج أولاً.", reply_markup=build_cancel_keyboard(CALLBACK_CANCEL))
         # Don't automatically show menu, let cancel handle return
         return ConversationHandler.END

    if pair in favorites:
        await update.message.reply_text(f"ℹ️ الزوج {pair} موجود بالفعل في المفضلة.")
    else:
        favorites.add(pair)
        # Ensure the set is saved back if persistence is used (it's mutable)
        context.user_data['favorite_pairs'] = favorites
        await update.message.reply_text(f"✅ تم إضافة {pair} إلى المفضلة.")
        logger.info(f"Added {pair} to favorites for user {update.effective_user.id}")

    # Show updated menu and end conversation
    await show_favorites_menu(update, context)
    return ConversationHandler.END

async def remove_favorite_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: # No state transition needed
    """Displays the interface to remove a favorite pair."""
    query = update.callback_query
    if query: await query.answer()
    favorites: Set[str] = context.user_data.get('favorite_pairs', set())
    if not favorites:
        text = "قائمة المفضلة فارغة. لا يوجد شيء للإزالة."
        keyboard = [[InlineKeyboardButton("🔙 رجوع لقائمة المفضلة", callback_data=CALLBACK_GOTO_FAVORITES)]]
    else:
        text = "اختر الزوج الذي تريد إزالته من المفضلة:"
        keyboard = build_remove_favorite_keyboard(favorites)

    await _send_or_edit(update, context, text, keyboard, edit=bool(query))
    # No state transition, next action handled by remove_favorite_pair_handler

async def remove_favorite_pair_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the button press to remove a specific favorite pair."""
    query = update.callback_query
    if not query: return
    callback_data = query.data
    await query.answer() # Acknowledge callback

    if not callback_data.startswith(CALLBACK_REMOVE_FAVORITE_PREFIX):
        logger.warning(f"Unexpected callback_data for favorite removal: {callback_data}")
        return

    pair_to_remove = callback_data.split(CALLBACK_REMOVE_FAVORITE_PREFIX, 1)[1]
    favorites: Set[str] = context.user_data.setdefault('favorite_pairs', set())

    if pair_to_remove in favorites:
        favorites.remove(pair_to_remove)
        context.user_data['favorite_pairs'] = favorites # Save changes
        logger.info(f"Removed {pair_to_remove} from favorites for user {update.effective_user.id}")
        await query.answer(f"تم إزالة {pair_to_remove}") # Show confirmation toast
        # Show updated favorites menu
        await show_favorites_menu(update, context)
    else:
        logger.warning(f"Attempted to remove non-existent favorite: {pair_to_remove}")
        await query.answer("الزوج غير موجود في المفضلة بالفعل.")
        # Optionally refresh menu even if no change occurred
        await show_favorites_menu(update, context)


# --- محادثة الإعدادات ---
async def settings_set_max_buy_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the conversation to set max buy amount."""
    query = update.callback_query
    if query: await query.answer()
    current_max = context.user_data.get('max_buy_usdt', DEFAULT_MAX_BUY_USDT)
    text = (f"الإعداد الحالي لحد الشراء الأقصى لكل صفقة هو: ${current_max:.2f}\n\n"
            f"أدخل القيمة الجديدة بالدولار (USDT) أو أرسل /cancel للإلغاء:")
    await _send_or_edit(update, context, text, build_cancel_keyboard(CALLBACK_CANCEL), edit=bool(query))
    return SET_ASK_MAX_BUY_AMOUNT

async def settings_ask_max_buy_amount_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the input for max buy amount."""
    if not update.message or not update.message.text: return SET_ASK_MAX_BUY_AMOUNT
    amount_str = update.message.text.strip()
    try:
        amount = decimal_context.create_decimal(amount_str)
        if amount <= 0: raise ValueError("المبلغ يجب أن يكون أكبر من صفر.")
        context.user_data['max_buy_usdt'] = amount
        logger.info(f"User {update.effective_user.id} set max buy amount to {amount:.2f} USDT")
        await update.message.reply_text(f"✅ تم تحديث حد الشراء الأقصى إلى ${amount:.2f}")
        await show_settings_menu(update, context) # Show updated settings menu
        return ConversationHandler.END
    except (InvalidOperation, ValueError) as e:
        logger.warning(f"Invalid max buy amount input: {amount_str} - {e}")
        await update.message.reply_text(f"⚠️ قيمة غير صالحة ({amount_str}). الرجاء إدخال رقم موجب صحيح:", reply_markup=build_cancel_keyboard(CALLBACK_CANCEL))
        return SET_ASK_MAX_BUY_AMOUNT
    except Exception as e:
         logger.error(f"Unexpected error setting max buy amount: {e}", exc_info=True)
         await update.message.reply_text("⚠️ حدث خطأ غير متوقع.", reply_markup=build_cancel_keyboard(CALLBACK_CANCEL))
         return SET_ASK_MAX_BUY_AMOUNT


# --- محادثة التداول ---
async def trade_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    """Starts the trading conversation (buy or sell)."""
    query = update.callback_query
    if not query: return ConversationHandler.END # Should be triggered by button
    await query.answer()
    callback_data = query.data

    if callback_data == CALLBACK_START_BUY:
        context.user_data['trade_side'] = SIDE_BUY
        logger.info("Starting BUY conversation")
        favorites: Set[str] = context.user_data.get('favorite_pairs', set())
        if favorites:
            text = "عملية الشراء. اختر زوجًا من المفضلة أو أدخل زوجًا آخر:"; keyboard = build_buy_favorites_keyboard(favorites)
            await _send_or_edit(update, context, text, keyboard, edit=True)
            # No state transition here, next step handled by favorite/other buttons
            return None # Stay in entry point logic, effectively ending this handler instance
        else:
            text = "عملية الشراء.\n\nالرجاء إدخال زوج العملات (مثال: BTCUSDT):"; keyboard = build_cancel_keyboard(CALLBACK_CANCEL_TRADE)
            await _send_or_edit(update, context, text, keyboard, edit=True)
            return T_ASK_PAIR

    elif callback_data == CALLBACK_START_SELL:
        context.user_data['trade_side'] = SIDE_SELL
        logger.info("Starting SELL conversation")
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
        balances = await get_account_balances(context)
        # Filter out stablecoins and assets with zero free balance
        sellable_balances = [
            b for b in balances
            if b['asset'] not in ['USDT', 'BUSD', 'USDC', 'DAI', 'TUSD'] and b['free'] > 0
        ]
        if not sellable_balances:
            text = "لا يوجد لديك أرصدة عملات (غير مستقرة) متاحة للبيع حاليًا."; keyboard = [[InlineKeyboardButton("🔙 رجوع لقائمة التداول", callback_data=CALLBACK_GOTO_TRADING)]]
            await _send_or_edit(update, context, text, InlineKeyboardMarkup(keyboard), edit=True)
            return ConversationHandler.END
        else:
            text = "عملية البيع. اختر الأصل الذي تريد بيعه:"; keyboard = build_sell_asset_keyboard(sellable_balances)
            await _send_or_edit(update, context, text, keyboard, edit=True)
            return T_CHOOSE_SELL_ASSET
    else:
        logger.warning(f"Unexpected callback_data to start trade: {callback_data}")
        return ConversationHandler.END


async def handle_buy_favorite_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles selection of a favorite pair to buy."""
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    callback_data = query.data
    pair = callback_data.split(CALLBACK_BUY_FAVORITE_PREFIX, 1)[1]

    # <<-- Validate Symbol just in case -->>
    if not is_valid_symbol(pair, context):
         await _send_or_edit(update, context, f"⚠️ الرمز المفضل '{pair}' لم يعد صالحًا للتداول.", InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=CALLBACK_GOTO_TRADING)]]), edit=True)
         return ConversationHandler.END

    context.user_data['trade_pair'] = pair
    context.user_data['trade_side'] = SIDE_BUY # Ensure side is set
    logger.info(f"Buying favorite pair selected: {pair}")

    available_balance_text = ""
    quote_balance = await get_quote_asset_balance(pair, context)
    if quote_balance is not None:
         quote_asset = ""; # Determine quote asset (improved logic in get_quote_asset_balance)
         # Find quote asset again for display text
         exchange_info = context.bot_data.get(EXCHANGE_INFO_CACHE_KEY)
         if exchange_info:
              for symbol_data in exchange_info.get('symbols', []):
                   if symbol_data['symbol'] == pair: quote_asset = symbol_data.get('quoteAsset'); break
         if quote_asset: available_balance_text = f"\n<i>(رصيد {quote_asset} المتاح: {quote_balance.normalize():f})</i>"

    text = f"الشراء لـ {pair}{available_balance_text}\n\nالرجاء إدخال الكمية:"
    await _send_or_edit(update, context, text, build_cancel_keyboard(CALLBACK_CANCEL_TRADE), edit=True, parse_mode=ParseMode.HTML)
    return T_ASK_AMOUNT

async def handle_buy_other_pair(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles pressing 'Enter other pair' button."""
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    context.user_data['trade_side'] = SIDE_BUY # Ensure side is set
    text = "عملية الشراء.\n\nالرجاء إدخال زوج العملات (مثال: BTCUSDT):"
    await _send_or_edit(update, context, text, build_cancel_keyboard(CALLBACK_CANCEL_TRADE), edit=True)
    return T_ASK_PAIR

async def choose_sell_asset_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles selection of an asset to sell."""
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    callback_data = query.data

    if not callback_data.startswith(CALLBACK_SELL_ASSET_PREFIX):
        logger.warning(f"Unexpected callback_data for choosing sell asset: {callback_data}")
        return T_CHOOSE_SELL_ASSET # Re-ask

    selected_asset = callback_data.split(CALLBACK_SELL_ASSET_PREFIX, 1)[1]
    context.user_data['sell_asset'] = selected_asset
    logger.info(f"Asset selected for selling: {selected_asset}")

    # Fetch balance again to be sure
    balances = await get_account_balances(context)
    asset_balance_info = next((b for b in balances if b['asset'] == selected_asset), None)

    if not asset_balance_info or asset_balance_info['free'] <= 0:
        text = f"خطأ أو لا يوجد رصيد متاح من {selected_asset} للبيع."; keyboard = [[InlineKeyboardButton("🔙 رجوع لقائمة التداول", callback_data=CALLBACK_GOTO_TRADING)]]
        await _send_or_edit(update, context, text, InlineKeyboardMarkup(keyboard), edit=True)
        return ConversationHandler.END

    available_qty = asset_balance_info['free'].normalize()
    context.user_data['sell_available_qty'] = available_qty

    text = f"الأصل: {selected_asset}\nالكمية المتاحة: {available_qty:f}\n\nهل تريد بيع الكمية كلها أم جزء منها؟"
    keyboard = build_sell_amount_keyboard()
    await _send_or_edit(update, context, text, keyboard, edit=True)
    return T_ASK_SELL_AMOUNT

async def ask_sell_amount_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    """Handles the choice between selling all or a partial amount."""
    query = update.callback_query
    if not query: return ConversationHandler.END # Should be button press
    await query.answer()
    choice = query.data

    selected_asset = context.user_data.get('sell_asset')
    available_qty = context.user_data.get('sell_available_qty')

    if not selected_asset or available_qty is None:
        logger.error("Missing asset/quantity in ask_sell_amount_handler")
        await _send_or_edit(update, context, "⚠️ خطأ داخلي.", build_main_menu_keyboard(), edit=True)
        return ConversationHandler.END

    if choice == CALLBACK_SELL_AMOUNT_ALL:
        # Assume USDT pairing, validate it
        pair = f"{selected_asset}USDT"
        if not is_valid_symbol(pair, context):
             # Try BUSD as fallback? Or ask user for pair?
             pair_busd = f"{selected_asset}BUSD"
             if is_valid_symbol(pair_busd, context):
                  pair = pair_busd
             else:
                  await _send_or_edit(update, context, f"⚠️ لم أجد زوج تداول شائع (مقابل USDT أو BUSD) لـ {selected_asset}. لا يمكن البيع تلقائيًا.", InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=CALLBACK_GOTO_TRADING)]]), edit=True)
                  return ConversationHandler.END

        symbol_filters = get_symbol_filters(pair, context)
        adjusted_qty = adjust_quantity(available_qty, symbol_filters)
        min_qty = decimal_context.create_decimal(symbol_filters.get('LOT_SIZE', {}).get('minQty', '0'))

        if adjusted_qty < min_qty:
             await _send_or_edit(update, context, f"⚠️ الكمية المتاحة من {selected_asset} ({available_qty:f}) بعد التعديل ({adjusted_qty:f}) أقل من الحد الأدنى للبيع ({min_qty:f}).", InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=CALLBACK_GOTO_TRADING)]]), edit=True)
             return ConversationHandler.END

        context.user_data['trade_amount'] = adjusted_qty
        context.user_data['trade_pair'] = pair
        logger.info(f"Selling ALL: {adjusted_qty} {selected_asset} via {pair}")

        formatted_qty = format_decimal(adjusted_qty, symbol_filters, 'LOT_SIZE')
        text = f"سيتم بيع {formatted_qty} {selected_asset} (كل المتاح المعدل) مقابل {pair.replace(selected_asset, '')} (أمر سوق).\n\nهل ترغب في إضافة SL/TP؟"
        await _send_or_edit(update, context, text, build_sltp_choice_keyboard(), edit=True)
        return T_ASK_SLTP_CHOICE

    elif choice == CALLBACK_SELL_AMOUNT_PARTIAL:
        text = f"الأصل: {selected_asset}\nالمتاح: {available_qty:f}\n\nأدخل الكمية من {selected_asset} للبيع:"
        await _send_or_edit(update, context, text, build_cancel_keyboard(CALLBACK_CANCEL_TRADE), edit=True)
        return T_ASK_SELL_AMOUNT # Wait for text input in ask_amount_handler
    else:
        logger.warning(f"Unexpected callback_data for sell amount choice: {choice}")
        return await cancel_trade_conversation(update, context)


async def ask_pair_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles manual pair input for BUY, including validation."""
    if not update.message or not update.message.text:
        logger.warning("Update without message text in T_ASK_PAIR")
        return T_ASK_PAIR
    pair = update.message.text.strip().upper()

    # <<-- Validate Symbol -->>
    if not is_valid_symbol(pair, context):
        await update.message.reply_text(f"⚠️ الرمز '{pair}' غير صالح أو غير متداول حاليًا. الرجاء إدخال رمز صحيح:", reply_markup=build_cancel_keyboard(CALLBACK_CANCEL_TRADE))
        return T_ASK_PAIR

    context.user_data['trade_pair'] = pair
    # trade_side should already be SIDE_BUY from entry point
    logger.info(f"Manual pair entered for BUY: {pair}")

    available_balance_text = ""
    quote_balance = await get_quote_asset_balance(pair, context)
    if quote_balance is not None:
         quote_asset = ""; # Determine quote asset
         exchange_info = context.bot_data.get(EXCHANGE_INFO_CACHE_KEY)
         if exchange_info:
              for symbol_data in exchange_info.get('symbols', []):
                   if symbol_data['symbol'] == pair: quote_asset = symbol_data.get('quoteAsset'); break
         if quote_asset: available_balance_text = f"\n<i>(رصيد {quote_asset} المتاح: {quote_balance.normalize():f})</i>"

    text = f"الزوج: {pair}{available_balance_text}\n\nالرجاء إدخال الكمية للشراء:"
    await update.message.reply_html(text, reply_markup=build_cancel_keyboard(CALLBACK_CANCEL_TRADE))
    return T_ASK_AMOUNT


async def ask_amount_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles amount input for BUY or PARTIAL SELL with validation and max amount info."""
    if not update.message or not update.message.text:
        logger.warning("Update without message text in T_ASK_AMOUNT/T_ASK_SELL_AMOUNT")
        return T_ASK_AMOUNT # Re-ask (or determine state more precisely)

    amount_str = update.message.text.strip()
    current_trade_side = context.user_data.get('trade_side')
    pair = context.user_data.get('trade_pair')
    next_state = T_ASK_SLTP_CHOICE # Default next state
    error_return_state = T_ASK_AMOUNT if current_trade_side == SIDE_BUY else T_ASK_SELL_AMOUNT

    if not pair:
         logger.error("Pair not found in context for amount handling.")
         await update.message.reply_text("⚠️ خطأ داخلي: لم يتم تحديد زوج العملات.", reply_markup=build_main_menu_keyboard())
         return ConversationHandler.END

    symbol_filters = get_symbol_filters(pair, context)
    if not symbol_filters:
         logger.error(f"Could not get filters for {pair} in amount handler.")
         await update.message.reply_text(f"⚠️ لم أتمكن من جلب قيود التداول لـ {pair}. لا يمكن المتابعة.", reply_markup=build_cancel_keyboard(CALLBACK_CANCEL_TRADE))
         return error_return_state # Stay in amount state

    lot_filter = symbol_filters.get('LOT_SIZE')
    min_qty = decimal_context.create_decimal(lot_filter.get('minQty', '0')) if lot_filter else Decimal(0)
    max_qty = decimal_context.create_decimal(lot_filter.get('maxQty', 'inf')) if lot_filter else Decimal('inf')

    try:
        amount_input = decimal_context.create_decimal(amount_str)
        if amount_input <= 0: raise ValueError("الكمية يجب أن تكون أكبر من صفر.")

        # Validate against LOT_SIZE filters (minQty, maxQty) before adjustment
        if amount_input < min_qty:
             raise ValueError(f"الكمية ({amount_input:f}) أقل من الحد الأدنى المسموح به ({min_qty:f}).")
        if amount_input > max_qty:
             raise ValueError(f"الكمية ({amount_input:f}) أكبر من الحد الأقصى المسموح به ({max_qty:f}).")

        # Adjust quantity according to stepSize
        amount = adjust_quantity(amount_input, symbol_filters)
        if amount <= 0 and amount_input > 0:
             # This case means stepSize adjustment made it zero
             raise ValueError(f"الكمية ({amount_input:f}) صغيرة جدًا بالنسبة لدقة الزوج (stepSize: {lot_filter.get('stepSize', 'N/A')}).")
        # Final check if adjusted amount is still valid
        if amount < min_qty:
             logger.warning(f"Adjusted quantity {amount} fell below minQty {min_qty}. Input was {amount_input}.")
             raise ValueError(f"الكمية بعد التعديل ({amount:f}) أصبحت أقل من الحد الأدنى ({min_qty:f}).")


        logger.info(f"Input Qty: {amount_input}, Adjusted Qty: {amount}")

        # Check max buy limit (for BUY side)
        if current_trade_side == SIDE_BUY:
            max_buy_setting = context.user_data.get('max_buy_usdt', DEFAULT_MAX_BUY_USDT)
            current_price = await get_current_price(pair, context)
            if current_price:
                estimated_cost = amount * current_price
                logger.info(f"Estimated cost: {estimated_cost}, Max buy setting: {max_buy_setting}")
                if estimated_cost > max_buy_setting:
                    await update.message.reply_text(f"⚠️ تحذير: القيمة التقديرية للصفقة (${estimated_cost:.2f}) تتجاوز حد الشراء المحدد (${max_buy_setting:.2f}).")
            else:
                 logger.warning(f"Could not get price to check max buy limit for {pair}.")

        # Check available balance (for PARTIAL SELL side)
        elif current_trade_side == SIDE_SELL:
            available_qty = context.user_data.get('sell_available_qty')
            if available_qty is not None and amount > available_qty:
                # Check if the input amount (before adjustment) was also > available
                if amount_input > available_qty:
                     await update.message.reply_text(f"⚠️ الكمية المطلوبة ({amount_input:f}) أكبر من المتاح ({available_qty:f}). أدخل كمية أقل:", reply_markup=build_cancel_keyboard(CALLBACK_CANCEL_TRADE))
                     return T_ASK_SELL_AMOUNT
                else:
                     # Input was okay, but adjustment made it slightly > available (rounding issues?)
                     # Or maybe the check should be on amount_input vs available_qty primarily
                     await update.message.reply_text(f"⚠️ الكمية ({amount:f}) أكبر من المتاح ({available_qty:f}) بعد التعديل. أدخل كمية أقل:", reply_markup=build_cancel_keyboard(CALLBACK_CANCEL_TRADE))
                     return T_ASK_SELL_AMOUNT

            # Set pair for partial sell if not already set
            if not context.user_data.get('trade_pair'):
                 sell_asset = context.user_data.get('sell_asset')
                 pair = f"{sell_asset}USDT" # Assume USDT pairing
                 if not is_valid_symbol(pair, context):
                      pair_busd = f"{sell_asset}BUSD" # Try BUSD
                      if is_valid_symbol(pair_busd, context): pair = pair_busd
                      else:
                           await update.message.reply_text(f"⚠️ لم أتمكن من تحديد زوج صالح لبيع {sell_asset}. الرجاء الإلغاء.", reply_markup=build_cancel_keyboard(CALLBACK_CANCEL_TRADE))
                           return ConversationHandler.END
                 context.user_data['trade_pair'] = pair
                 logger.info(f"Partial sell pair set: {pair}")


    except (InvalidOperation, ValueError) as e:
        logger.warning(f"Invalid amount input: {amount_str} - {e}")
        await update.message.reply_text(f"⚠️ قيمة الكمية غير صالحة: {e}\nالرجاء إدخال رقم صحيح صالح:", reply_markup=build_cancel_keyboard(CALLBACK_CANCEL_TRADE))
        return error_return_state
    except Exception as e:
         logger.error(f"Unexpected error handling amount: {e}", exc_info=True)
         await update.message.reply_text("⚠️ حدث خطأ غير متوقع. الرجاء المحاولة مرة أخرى.", reply_markup=build_cancel_keyboard(CALLBACK_CANCEL_TRADE))
         return error_return_state


    context.user_data['trade_amount'] = amount # Store adjusted amount
    # Display max buy info (for BUY side)
    max_buy_info = ""
    if current_trade_side == SIDE_BUY:
         quote_balance = await get_quote_asset_balance(pair, context)
         current_price = await get_current_price(pair, context)
         if quote_balance is not None and current_price is not None and current_price > 0:
              approx_max_qty_raw = (quote_balance / current_price) * Decimal('0.999') # Approx fee
              approx_max_qty_adj = adjust_quantity(approx_max_qty_raw, symbol_filters)
              if approx_max_qty_adj > min_qty: # Only show if max > min
                   max_buy_info = f"\n<i>(الكمية القصوى التقديرية للشراء: {format_decimal(approx_max_qty_adj, symbol_filters, 'LOT_SIZE')})</i>"


    text = f"تم تحديد الكمية: {format_decimal(amount, symbol_filters, 'LOT_SIZE')}{max_buy_info}\n\nهل ترغب في إضافة أمر إيقاف خسارة (SL) أو جني أرباح (TP)؟"
    await update.message.reply_html(text, reply_markup=build_sltp_choice_keyboard())
    return next_state


async def ask_sltp_choice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the choice of SL/TP method (manual, percent, none)."""
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    choice = query.data
    pair = context.user_data.get('trade_pair')

    if not pair:
         logger.error("Pair missing in ask_sltp_choice_handler")
         await _send_or_edit(update, context, "⚠️ خطأ داخلي.", build_main_menu_keyboard(), edit=True)
         return ConversationHandler.END

    if choice == CALLBACK_ADD_SLTP_YES: # Manual input
        logger.info("User chose manual SL/TP input.")
        text = "الرجاء إدخال سعر إيقاف الخسارة (Stop-Loss).\nأدخل 0 أو أرسل /skip لتخطيه."
        await _send_or_edit(update, context, text, build_cancel_keyboard(CALLBACK_CANCEL_TRADE), edit=True)
        return T_ASK_SL_PRICE

    elif choice == CALLBACK_ADD_SLTP_PERCENT: # Percentage input
        logger.info("User chose percentage SL/TP input.")
        current_price = await get_current_price(pair, context)
        if current_price is None:
            await _send_or_edit(update, context, "⚠️ لم أتمكن من جلب السعر الحالي لحساب النسب. حاول مرة أخرى أو اختر الإدخال اليدوي.", build_sltp_choice_keyboard(), edit=True)
            return T_ASK_SLTP_CHOICE # Stay in choice state

        context.user_data['current_price_for_sltp'] = current_price
        symbol_filters = get_symbol_filters(pair, context) # Needed for formatting price
        formatted_price = format_decimal(current_price, symbol_filters, 'PRICE_FILTER')
        text = f"السعر الحالي لـ {pair} هو {formatted_price}\n\nاختر نسبة إيقاف الخسارة (SL):"
        keyboard = build_percent_keyboard(CALLBACK_SL_PERCENT_PREFIX, [1, 2, 3, 5]) # Use updated keyboard
        await _send_or_edit(update, context, text, keyboard, edit=True)
        return T_ASK_SL_PERCENT

    elif choice == CALLBACK_ADD_SLTP_NO: # Skip
        logger.info("User skipped SL/TP."); context.user_data['sl_price'] = None; context.user_data['tp_price'] = None
        return await build_and_show_confirmation(update, context)
    else:
        logger.warning(f"Unexpected callback_data in SL/TP choice: {choice}")
        return await cancel_trade_conversation(update, context)


async def ask_sl_percent_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles SL percentage selection."""
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    choice = query.data

    current_price = context.user_data.get('current_price_for_sltp')
    trade_side = context.user_data.get('trade_side')
    pair = context.user_data.get('trade_pair')

    if not all([current_price, trade_side, pair]):
        logger.error("Missing data for SL percentage calculation.")
        return await cancel_trade_conversation(update, context)

    try:
        percentage = int(choice.split(CALLBACK_SL_PERCENT_PREFIX, 1)[1])
        percentage_decimal = Decimal(percentage) / 100
        sl_price_raw = current_price * (1 - percentage_decimal) if trade_side == SIDE_BUY else current_price * (1 + percentage_decimal)

        # Adjust and validate calculated SL price
        symbol_filters = get_symbol_filters(pair, context)
        sl_price = adjust_price(sl_price_raw, symbol_filters)

        # Validate against price filters again after calculation
        price_filter = symbol_filters.get('PRICE_FILTER')
        min_price = decimal_context.create_decimal(price_filter.get('minPrice', '0')) if price_filter else Decimal(0)
        max_price = decimal_context.create_decimal(price_filter.get('maxPrice', 'inf')) if price_filter else Decimal('inf')
        if sl_price < min_price or sl_price > max_price:
             raise ValueError(f"السعر المحسوب ({sl_price:f}) خارج حدود الفلتر ({min_price:f} - {max_price:f}).")
        if sl_price <= 0 and min_price > 0:
             raise ValueError("السعر المحسوب أصبح صفرًا أو أقل.")


        context.user_data['sl_price'] = sl_price # Store adjusted price
        logger.info(f"Calculated SL price at {percentage}%: Raw={sl_price_raw}, Adjusted={sl_price}")

        formatted_sl = format_decimal(sl_price, symbol_filters, 'PRICE_FILTER')
        text = f"تم تحديد SL بنسبة {percentage}% ({formatted_sl}).\n\nاختر نسبة جني الأرباح (TP) (أو تخطَّ):"
        keyboard = build_percent_keyboard(CALLBACK_TP_PERCENT_PREFIX, [2, 3, 5, 10]) # Different TP options
        keyboard.inline_keyboard.append([InlineKeyboardButton("➡️ تخطَّ TP", callback_data=CALLBACK_SKIP_TP)]) # Clearer skip text

        await _send_or_edit(update, context, text, keyboard, edit=True)
        return T_ASK_TP_PERCENT

    except (ValueError, IndexError, TypeError, InvalidOperation) as e:
        logger.error(f"Error processing SL percentage '{choice}': {e}")
        await _send_or_edit(update, context, f"⚠️ خطأ في حساب أو التحقق من سعر SL: {e}\nحاول مرة أخرى أو اختر طريقة أخرى.", build_sltp_choice_keyboard(), edit=True)
        return T_ASK_SLTP_CHOICE # Go back to choice
    except Exception as e:
         logger.error(f"Unexpected error in ask_sl_percent_handler: {e}", exc_info=True)
         return await cancel_trade_conversation(update, context)


async def ask_tp_percent_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles TP percentage selection."""
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    choice = query.data

    current_price = context.user_data.get('current_price_for_sltp')
    trade_side = context.user_data.get('trade_side')
    pair = context.user_data.get('trade_pair')
    sl_price = context.user_data.get('sl_price') # Get SL for comparison

    if choice == CALLBACK_SKIP_TP:
        logger.info("Skipping TP percentage.")
        context.user_data['tp_price'] = None
        return await build_and_show_confirmation(update, context)

    elif choice.startswith(CALLBACK_TP_PERCENT_PREFIX):
        if not all([current_price, trade_side, pair]):
            logger.error("Missing data for TP percentage calculation.")
            return await cancel_trade_conversation(update, context)

        try:
            percentage = int(choice.split(CALLBACK_TP_PERCENT_PREFIX, 1)[1])
            percentage_decimal = Decimal(percentage) / 100
            tp_price_raw = current_price * (1 + percentage_decimal) if trade_side == SIDE_BUY else current_price * (1 - percentage_decimal)

            # Adjust and validate calculated TP price
            symbol_filters = get_symbol_filters(pair, context)
            tp_price = adjust_price(tp_price_raw, symbol_filters)

            # Validate against price filters
            price_filter = symbol_filters.get('PRICE_FILTER')
            min_price = decimal_context.create_decimal(price_filter.get('minPrice', '0')) if price_filter else Decimal(0)
            max_price = decimal_context.create_decimal(price_filter.get('maxPrice', 'inf')) if price_filter else Decimal('inf')
            if tp_price < min_price or tp_price > max_price:
                 raise ValueError(f"السعر المحسوب ({tp_price:f}) خارج حدود الفلتر ({min_price:f} - {max_price:f}).")
            if tp_price <= 0 and min_price > 0:
                 raise ValueError("السعر المحسوب أصبح صفرًا أو أقل.")

            # Logical check against SL price
            if sl_price:
                 if trade_side == SIDE_BUY and tp_price <= sl_price:
                      raise ValueError(f"سعر TP المحسوب ({tp_price:f}) أقل من أو يساوي سعر SL ({sl_price:f}).")
                 if trade_side == SIDE_SELL and tp_price >= sl_price:
                      raise ValueError(f"سعر TP المحسوب ({tp_price:f}) أعلى من أو يساوي سعر SL ({sl_price:f}).")

            context.user_data['tp_price'] = tp_price # Store adjusted price
            logger.info(f"Calculated TP price at {percentage}%: Raw={tp_price_raw}, Adjusted={tp_price}")
            return await build_and_show_confirmation(update, context)

        except (ValueError, IndexError, TypeError, InvalidOperation) as e:
            logger.error(f"Error processing TP percentage '{choice}': {e}")
            # Rebuild SL percentage keyboard for TP selection retry
            sl_perc_text = f"تم تحديد SL: {format_decimal(sl_price, get_symbol_filters(pair, context), 'PRICE_FILTER') if sl_price else 'لم يحدد'}.\n\n"
            error_text = f"⚠️ خطأ في حساب أو التحقق من سعر TP: {e}\nاختر نسبة TP مرة أخرى (أو تخطَّ):"
            keyboard = build_percent_keyboard(CALLBACK_TP_PERCENT_PREFIX, [2, 3, 5, 10])
            keyboard.inline_keyboard.append([InlineKeyboardButton("➡️ تخطَّ TP", callback_data=CALLBACK_SKIP_TP)])
            await _send_or_edit(update, context, sl_perc_text + error_text, keyboard, edit=True)
            return T_ASK_TP_PERCENT # Stay in TP percent state
        except Exception as e:
             logger.error(f"Unexpected error in ask_tp_percent_handler: {e}", exc_info=True)
             return await cancel_trade_conversation(update, context)
    else:
        logger.warning(f"Unexpected callback_data in TP percentage: {choice}")
        return await cancel_trade_conversation(update, context)


async def ask_sl_price_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles manual SL price input with validation."""
    if not update.message or not update.message.text: return T_ASK_SL_PRICE
    sl_price_str = update.message.text.strip(); sl_price_input_val = None
    pair = context.user_data.get('trade_pair'); trade_side = context.user_data.get('trade_side')
    current_price = await get_current_price(pair, context) # Fetch current price for validation

    if not pair or not trade_side:
         logger.error("Missing pair/side for SL price validation.")
         await update.message.reply_text("⚠️ خطأ داخلي. لا يمكن التحقق من السعر.", reply_markup=build_cancel_keyboard(CALLBACK_CANCEL_TRADE))
         return ConversationHandler.END

    symbol_filters = get_symbol_filters(pair, context)
    price_filter = symbol_filters.get('PRICE_FILTER')
    min_price = decimal_context.create_decimal(price_filter.get('minPrice', '0')) if price_filter else Decimal(0)
    max_price = decimal_context.create_decimal(price_filter.get('maxPrice', 'inf')) if price_filter else Decimal('inf')

    if sl_price_str.lower() == '/skip':
        logger.info("Skipping SL via /skip.")
        context.user_data['sl_price'] = None
    else:
        try:
            sl_price_input_val = decimal_context.create_decimal(sl_price_str)
            if sl_price_input_val < 0: raise ValueError("السعر يجب أن يكون موجبًا.")
            if sl_price_input_val == 0:
                 logger.info("Skipping SL via 0.")
                 context.user_data['sl_price'] = None
            else:
                # Validate against PRICE_FILTER limits
                if sl_price_input_val < min_price: raise ValueError(f"السعر ({sl_price_input_val:f}) أقل من الحد الأدنى ({min_price:f}).")
                if sl_price_input_val > max_price: raise ValueError(f"السعر ({sl_price_input_val:f}) أكبر من الحد الأقصى ({max_price:f}).")

                # Logical validation against current price
                if current_price:
                    if trade_side == SIDE_BUY and sl_price_input_val >= current_price:
                         await update.message.reply_text(f"⚠️ تحذير: سعر SL ({sl_price_input_val:f}) أعلى من أو يساوي السعر الحالي ({current_price:f}) لصفقة شراء. هل أنت متأكد؟ أدخل السعر مرة أخرى أو /skip.", reply_markup=build_cancel_keyboard(CALLBACK_CANCEL_TRADE))
                         return T_ASK_SL_PRICE
                    if trade_side == SIDE_SELL and sl_price_input_val <= current_price:
                         await update.message.reply_text(f"⚠️ تحذير: سعر SL ({sl_price_input_val:f}) أقل من أو يساوي السعر الحالي ({current_price:f}) لصفقة بيع. هل أنت متأكد؟ أدخل السعر مرة أخرى أو /skip.", reply_markup=build_cancel_keyboard(CALLBACK_CANCEL_TRADE))
                         return T_ASK_SL_PRICE
                else: logger.warning(f"Could not get current price for logical SL check on {pair}.")

                # Adjust price according to tickSize (do this *after* logical checks on input value)
                sl_price_adjusted = adjust_price(sl_price_input_val, symbol_filters)
                logger.info(f"Input SL: {sl_price_input_val}, Adjusted SL: {sl_price_adjusted}")
                if sl_price_adjusted <= 0 and min_price > 0:
                     raise ValueError("السعر بعد التعديل أصبح صفرًا أو أقل.")
                context.user_data['sl_price'] = sl_price_adjusted # Store adjusted

        except (InvalidOperation, ValueError) as e:
            logger.warning(f"Invalid SL price input: {sl_price_str} - {e}")
            await update.message.reply_text(f"⚠️ قيمة سعر SL غير صالحة: {e}\nأدخل رقمًا صحيحًا (أو 0 أو /skip للتخطي):", reply_markup=build_cancel_keyboard(CALLBACK_CANCEL_TRADE))
            return T_ASK_SL_PRICE
        except Exception as e:
             logger.error(f"Unexpected error handling SL price: {e}", exc_info=True)
             await update.message.reply_text("⚠️ حدث خطأ غير متوقع. الرجاء المحاولة مرة أخرى.", reply_markup=build_cancel_keyboard(CALLBACK_CANCEL_TRADE))
             return T_ASK_SL_PRICE

    # Proceed to ask for TP price
    sl_price_stored = context.user_data.get('sl_price') # Get potentially adjusted or None value
    sl_price_display = format_decimal(sl_price_stored, symbol_filters, 'PRICE_FILTER') if sl_price_stored else "لم يتم التحديد"
    text = f"تم تحديد SL: {sl_price_display}\n\nالرجاء إدخال سعر جني الأرباح (Take-Profit).\nأدخل 0 أو أرسل /skip لتخطيه."
    await update.message.reply_html(text, reply_markup=build_cancel_keyboard(CALLBACK_CANCEL_TRADE))
    return T_ASK_TP_PRICE


async def ask_tp_price_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles manual TP price input with validation."""
    if not update.message or not update.message.text: return T_ASK_TP_PRICE
    tp_price_str = update.message.text.strip(); tp_price_input_val = None
    pair = context.user_data.get('trade_pair'); trade_side = context.user_data.get('trade_side')
    sl_price = context.user_data.get('sl_price') # Adjusted SL price from previous step
    current_price = await get_current_price(pair, context) # Fetch current price for validation

    if not pair or not trade_side:
         logger.error("Missing pair/side for TP price validation.")
         await update.message.reply_text("⚠️ خطأ داخلي. لا يمكن التحقق من السعر.", reply_markup=build_cancel_keyboard(CALLBACK_CANCEL_TRADE))
         return ConversationHandler.END

    symbol_filters = get_symbol_filters(pair, context)
    price_filter = symbol_filters.get('PRICE_FILTER')
    min_price = decimal_context.create_decimal(price_filter.get('minPrice', '0')) if price_filter else Decimal(0)
    max_price = decimal_context.create_decimal(price_filter.get('maxPrice', 'inf')) if price_filter else Decimal('inf')

    if tp_price_str.lower() == '/skip':
        logger.info("Skipping TP via /skip.")
        context.user_data['tp_price'] = None
    else:
        try:
            tp_price_input_val = decimal_context.create_decimal(tp_price_str)
            if tp_price_input_val < 0: raise ValueError("السعر يجب أن يكون موجبًا.")
            if tp_price_input_val == 0:
                 logger.info("Skipping TP via 0.")
                 context.user_data['tp_price'] = None
            else:
                # Validate against PRICE_FILTER limits
                if tp_price_input_val < min_price: raise ValueError(f"السعر ({tp_price_input_val:f}) أقل من الحد الأدنى ({min_price:f}).")
                if tp_price_input_val > max_price: raise ValueError(f"السعر ({tp_price_input_val:f}) أكبر من الحد الأقصى ({max_price:f}).")

                # Logical validation against current price
                if current_price:
                    if trade_side == SIDE_BUY and tp_price_input_val <= current_price:
                         await update.message.reply_text(f"⚠️ تحذير: سعر TP ({tp_price_input_val:f}) أقل من أو يساوي السعر الحالي ({current_price:f}) لصفقة شراء. هل أنت متأكد؟ أدخل السعر مرة أخرى أو /skip.", reply_markup=build_cancel_keyboard(CALLBACK_CANCEL_TRADE))
                         return T_ASK_TP_PRICE
                    if trade_side == SIDE_SELL and tp_price_input_val >= current_price:
                         await update.message.reply_text(f"⚠️ تحذير: سعر TP ({tp_price_input_val:f}) أعلى من أو يساوي السعر الحالي ({current_price:f}) لصفقة بيع. هل أنت متأكد؟ أدخل السعر مرة أخرى أو /skip.", reply_markup=build_cancel_keyboard(CALLBACK_CANCEL_TRADE))
                         return T_ASK_TP_PRICE
                else: logger.warning(f"Could not get current price for logical TP check on {pair}.")

                # Logical validation against SL price
                if sl_price: # Check only if SL was set
                    if trade_side == SIDE_BUY and tp_price_input_val <= sl_price:
                         await update.message.reply_text(f"⚠️ تحذير: سعر TP ({tp_price_input_val:f}) أقل من أو يساوي سعر SL ({sl_price:f}). هل أنت متأكد؟ أدخل السعر مرة أخرى أو /skip.", reply_markup=build_cancel_keyboard(CALLBACK_CANCEL_TRADE))
                         return T_ASK_TP_PRICE
                    if trade_side == SIDE_SELL and tp_price_input_val >= sl_price:
                         await update.message.reply_text(f"⚠️ تحذير: سعر TP ({tp_price_input_val:f}) أعلى من أو يساوي سعر SL ({sl_price:f}). هل أنت متأكد؟ أدخل السعر مرة أخرى أو /skip.", reply_markup=build_cancel_keyboard(CALLBACK_CANCEL_TRADE))
                         return T_ASK_TP_PRICE

                # Adjust price according to tickSize
                tp_price_adjusted = adjust_price(tp_price_input_val, symbol_filters)
                logger.info(f"Input TP: {tp_price_input_val}, Adjusted TP: {tp_price_adjusted}")
                if tp_price_adjusted <= 0 and min_price > 0:
                     raise ValueError("السعر بعد التعديل أصبح صفرًا أو أقل.")
                context.user_data['tp_price'] = tp_price_adjusted # Store adjusted

        except (InvalidOperation, ValueError) as e:
            logger.warning(f"Invalid TP price input: {tp_price_str} - {e}")
            await update.message.reply_text(f"⚠️ قيمة سعر TP غير صالحة: {e}\nأدخل رقمًا صحيحًا (أو 0 أو /skip للتخطي):", reply_markup=build_cancel_keyboard(CALLBACK_CANCEL_TRADE))
            return T_ASK_TP_PRICE
        except Exception as e:
             logger.error(f"Unexpected error handling TP price: {e}", exc_info=True)
             await update.message.reply_text("⚠️ حدث خطأ غير متوقع. الرجاء المحاولة مرة أخرى.", reply_markup=build_cancel_keyboard(CALLBACK_CANCEL_TRADE))
             return T_ASK_TP_PRICE

    # Proceed to confirmation
    return await build_and_show_confirmation(update, context)


async def build_and_show_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Builds the confirmation message, including MIN_NOTIONAL check and formatting."""
    trade_side=context.user_data.get('trade_side'); pair=context.user_data.get('trade_pair'); amount=context.user_data.get('trade_amount') # Adjusted amount
    sl_price=context.user_data.get('sl_price'); tp_price=context.user_data.get('tp_price') # Adjusted prices or None
    trade_action_text = "البيع" if trade_side == SIDE_SELL else "الشراء"

    if not all([trade_side, pair, amount]):
        logger.error("Missing trade details in build_and_show_confirmation!")
        await _send_or_edit(update, context, "❌ خطأ داخلي: تفاصيل الصفقة مفقودة.", build_main_menu_keyboard(), edit=True)
        return ConversationHandler.END

    symbol_filters = get_symbol_filters(pair, context)
    if not symbol_filters:
         logger.error(f"Could not get filters for {pair} in confirmation.")
         await _send_or_edit(update, context, f"⚠️ لم أتمكن من جلب قيود التداول لـ {pair}. لا يمكن المتابعة.", build_cancel_keyboard(CALLBACK_CANCEL_TRADE), edit=True)
         return ConversationHandler.END # End conversation

    # <<-- MIN_NOTIONAL Check -->>
    min_notional_filter = symbol_filters.get('MIN_NOTIONAL')
    min_notional_value = None
    apply_min_notional_to_market = True
    if min_notional_filter:
        min_notional_value = decimal_context.create_decimal(min_notional_filter.get('minNotional', '0'))
        apply_min_notional_to_market = min_notional_filter.get('applyToMarket', True)

    if apply_min_notional_to_market and min_notional_value is not None and min_notional_value > 0:
        current_price = await get_current_price(pair, context)
        if current_price:
            estimated_notional = amount * current_price # Use adjusted amount
            if estimated_notional < min_notional_value:
                error_text = (
                    f"⚠️ **قيمة الصفقة صغيرة جدًا!**\n\n"
                    f"الحد الأدنى لقيمة الصفقة لـ {pair} هو {min_notional_value:f} (تقريبًا).\n"
                    f"القيمة التقديرية لصفقتك هي {estimated_notional:.4f}.\n\n"
                    f"الرجاء إلغاء العملية وتعديل الكمية."
                )
                logger.warning(f"MIN_NOTIONAL check failed for {pair}. Estimated: {estimated_notional}, Min: {min_notional_value}")
                keyboard = [[InlineKeyboardButton("❌ إلغاء العملية", callback_data=CALLBACK_CANCEL_TRADE)]]
                await _send_or_edit(update, context, error_text, InlineKeyboardMarkup(keyboard), edit=True, parse_mode=ParseMode.HTML)
                return ConversationHandler.END # End conversation here
        else:
            logger.warning(f"Could not get current price for {pair} to check MIN_NOTIONAL.")
            await _send_or_edit(update, context, f"⚠️ لم أتمكن من التحقق من الحد الأدنى لقيمة الصفقة لـ {pair}. الرجاء الإلغاء والمحاولة لاحقًا.", build_cancel_keyboard(CALLBACK_CANCEL_TRADE), edit=True)
            return ConversationHandler.END

    # Build confirmation text using formatted values
    formatted_amount = format_decimal(amount, symbol_filters, 'LOT_SIZE')
    formatted_sl = format_decimal(sl_price, symbol_filters, 'PRICE_FILTER') if sl_price else "لم يحدد"
    formatted_tp = format_decimal(tp_price, symbol_filters, 'PRICE_FILTER') if tp_price else "لم يحدد"

    confirm_text = f"<b>تأكيد أمر {trade_action_text} (سوق):</b>\n\n"
    confirm_text += f"<b>الزوج:</b> {pair}\n"
    confirm_text += f"<b>الكمية:</b> {formatted_amount}\n"
    confirm_text += f"<b>النوع:</b> Market\n"
    if sl_price: confirm_text += f"<b>إيقاف الخسارة (SL):</b> {formatted_sl}\n"
    if tp_price: confirm_text += f"<b>جني الأرباح (TP):</b> {formatted_tp}\n"
    confirm_text += "\nهل أنت متأكد؟\n<i>(سيتم استخدام القيم المعدلة حسب قيود المنصة.)</i>"

    keyboard = [[ InlineKeyboardButton(f"✅ تأكيد {trade_action_text}", callback_data=CALLBACK_CONFIRM_TRADE),
                  InlineKeyboardButton("❌ إلغاء العملية", callback_data=CALLBACK_CANCEL_TRADE), ]]
    await _send_or_edit(update, context, confirm_text, InlineKeyboardMarkup(keyboard), edit=True, parse_mode=ParseMode.HTML)
    return T_CONFIRM_TRADE_STATE


async def _place_sltp_orders(
    context: ContextTypes.DEFAULT_TYPE,
    pair: str,
    trade_side: str,
    executed_qty: Decimal,
    sl_price: Optional[Decimal], # Already adjusted price
    tp_price: Optional[Decimal], # Already adjusted price
    symbol_filters: Dict[str, Dict[str, Any]]
) -> str:
    """
    Helper function to place Stop Loss (SL) and Take Profit (TP) orders (OCO or individual).
    Uses adjusted values and specific error handling. Returns a status message string.
    """
    if not binance_client: return "\n\n⚠️ اتصال Binance غير متاح لوضع SL/TP."
    if executed_qty <= 0: return "\n\nℹ️ لم يتم تنفيذ كمية لوضع SL/TP."
    if not sl_price and not tp_price: return "" # No SL/TP requested

    opposite_side = SIDE_SELL if trade_side == SIDE_BUY else SIDE_BUY
    status_msg = ""
    lot_filter = symbol_filters.get('LOT_SIZE')
    min_qty = decimal_context.create_decimal(lot_filter.get('minQty', '0')) if lot_filter else Decimal(0)

    try:
        # Adjust executed quantity according to LOT_SIZE filter for SL/TP orders
        adjusted_exec_qty = adjust_quantity(executed_qty, symbol_filters)
        logger.info(f"Adjusted executed quantity for SL/TP orders: {adjusted_exec_qty}")

        if adjusted_exec_qty < min_qty:
            logger.warning(f"Adjusted SL/TP quantity {adjusted_exec_qty} is below minQty {min_qty}.")
            return f"\n\n⚠️ الكمية المنفذة بعد التعديل ({adjusted_exec_qty:f}) أقل من الحد الأدنى ({min_qty:f}) لوضع SL/TP."

        adjusted_exec_qty_str = format_decimal(adjusted_exec_qty, symbol_filters, 'LOT_SIZE')

        # --- OCO Order (SL and TP) ---
        if sl_price and tp_price:
            # Prices are already adjusted, just format them
            sl_stop_price_str = format_decimal(sl_price, symbol_filters, 'PRICE_FILTER') # Trigger price
            sl_limit_price_str = format_decimal(sl_price, symbol_filters, 'PRICE_FILTER') # Limit price (can be same as trigger for OCO stop)
            tp_limit_price_str = format_decimal(tp_price, symbol_filters, 'PRICE_FILTER') # Limit price for TP leg

            oco_params = {
                'symbol': pair,
                'side': opposite_side,
                'quantity': adjusted_exec_qty_str,
                'price': tp_limit_price_str,          # Limit price for the TP leg
                'stopPrice': sl_stop_price_str,       # Trigger price for SL
                'stopLimitPrice': sl_limit_price_str, # Limit price for the SL leg after trigger
                'stopLimitTimeInForce': TIME_IN_FORCE_GTC, # Required for stopLimitPrice
            }
            logger.info(f"--- Attempting OCO order: {oco_params}")
            binance_client.create_oco_order(**oco_params)
            status_msg = "\n\n✅ تم وضع أمر OCO (SL/TP) بنجاح."

        # --- Individual SL Order (STOP_LOSS_LIMIT) ---
        elif sl_price:
            sl_stop_price_str = format_decimal(sl_price, symbol_filters, 'PRICE_FILTER') # Trigger
            sl_limit_price_str = format_decimal(sl_price, symbol_filters, 'PRICE_FILTER') # Limit

            sl_params = {
                'symbol': pair,
                'side': opposite_side,
                'type': ORDER_TYPE_STOP_LOSS_LIMIT,
                'quantity': adjusted_exec_qty_str,
                'stopPrice': sl_stop_price_str, # Trigger price
                'price': sl_limit_price_str, # Limit price after trigger
                'timeInForce': TIME_IN_FORCE_GTC, # Required for limit price
            }
            logger.info(f"--- Attempting SL Limit order: {sl_params}")
            binance_client.create_order(**sl_params)
            status_msg = "\n\n✅ تم وضع أمر SL بنجاح."

        # --- Individual TP Order (TAKE_PROFIT_LIMIT) ---
        elif tp_price:
            tp_stop_price_str = format_decimal(tp_price, symbol_filters, 'PRICE_FILTER') # Trigger
            tp_limit_price_str = format_decimal(tp_price, symbol_filters, 'PRICE_FILTER') # Limit

            tp_params = {
                'symbol': pair,
                'side': opposite_side,
                'type': ORDER_TYPE_TAKE_PROFIT_LIMIT,
                'quantity': adjusted_exec_qty_str,
                'stopPrice': tp_stop_price_str, # Trigger price for TP
                'price': tp_limit_price_str, # Limit price after trigger
                'timeInForce': TIME_IN_FORCE_GTC, # Required for limit price
            }
            logger.info(f"--- Attempting TP Limit order: {tp_params}")
            binance_client.create_order(**tp_params)
            status_msg = "\n\n✅ تم وضع أمر TP بنجاح."

    except (BinanceAPIException, BinanceOrderException) as e:
        logger.error(f"--- Failed to place SL/TP order: Code={e.code}, Msg={e.message}")
        error_detail = f"<code>{e.message}</code> (Code: {e.code})"
        if e.code == -2010: error_detail = "خطأ في الرصيد أو قيود التداول (Code: -2010)"
        elif e.code == -1013: error_detail = "خطأ في قيود السعر/الكمية (Code: -1013)"
        status_msg = f"\n\n⚠️ فشل وضع أمر SL/TP: {error_detail}"
    except Exception as e:
        logger.error(f"--- Generic error placing SL/TP order: {e}", exc_info=True)
        status_msg = "\n\n⚠️ حدث خطأ غير متوقع أثناء محاولة وضع SL/TP."

    return status_msg


async def confirm_trade_final_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handles the final trade confirmation and execution.
    Executes the main market order and then attempts to place SL/TP orders.
    Uses specific Binance exception handling and clearer messages.
    """
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer() # Acknowledge callback quickly
    user_choice = query.data

    trade_side = context.user_data.get('trade_side')
    pair = context.user_data.get('trade_pair')
    amount = context.user_data.get('trade_amount') # Adjusted amount
    sl_price = context.user_data.get('sl_price') # Adjusted price or None
    tp_price = context.user_data.get('tp_price') # Adjusted price or None
    trade_action_text = "البيع" if trade_side == SIDE_SELL else "الشراء"

    if user_choice == CALLBACK_CANCEL_TRADE:
        logger.info(f"User cancelled {trade_action_text} at final confirmation.")
        return await cancel_trade_conversation(update, context)

    if user_choice != CALLBACK_CONFIRM_TRADE:
         logger.warning(f"Unexpected callback_data in final confirmation: {query.data}")
         return await cancel_trade_conversation(update, context)

    # --- Parameter & Client Check ---
    if not all([trade_side, pair, amount]):
        logger.error("Missing trade details at final confirmation!")
        await _send_or_edit(update, context, "❌ خطأ داخلي: تفاصيل الصفقة مفقودة.", build_main_menu_keyboard(), edit=True)
        return ConversationHandler.END
    if not binance_client:
        await _send_or_edit(update, context, "❌ خطأ: اتصال Binance غير مهيأ.", build_main_menu_keyboard(), edit=True)
        return ConversationHandler.END

    # --- Get Filters ---
    symbol_filters = get_symbol_filters(pair, context)
    if not symbol_filters:
         logger.error(f"Could not get filters for {pair} before placing order.")
         await _send_or_edit(update, context, f"⚠️ لم أتمكن من جلب قيود التداول لـ {pair}. لا يمكن المتابعة.", build_main_menu_keyboard(), edit=True)
         return ConversationHandler.END

    # --- Execute Market Order ---
    order_response = None
    sl_tp_status_msg = ""
    final_keyboard = build_main_menu_keyboard()
    final_message = ""

    try:
        await _send_or_edit(update, context, f"⏳ جاري تنفيذ أمر {trade_action_text} (سوق)...", reply_markup=None, edit=True)

        # Format quantity for the order using adjusted amount
        formatted_amount_str = format_decimal(amount, symbol_filters, 'LOT_SIZE')
        logger.info(f"Sending market order: Side={trade_side}, Symbol={pair}, Quantity={formatted_amount_str}")

        # Final quantity check (should be redundant if adjust_quantity is correct)
        if decimal_context.create_decimal(formatted_amount_str) <= 0:
             raise ValueError(f"الكمية النهائية ({formatted_amount_str}) غير صالحة لأمر السوق.")

        order_params = {
            'symbol': pair,
            'side': trade_side,
            'type': ORDER_TYPE_MARKET,
            'quantity': formatted_amount_str
        }
        order_response = binance_client.create_order(**order_params)
        logger.info(f"Binance main order response: {order_response}")

        # --- Build Success Message ---
        executed_qty_dec = decimal_context.create_decimal(order_response.get('executedQty', '0'))
        cummulative_quote_qty = decimal_context.create_decimal(order_response.get('cummulativeQuoteQty', '0'))
        avg_price = (cummulative_quote_qty / executed_qty_dec) if executed_qty_dec > 0 else Decimal(0)
        status = order_response.get('status')
        order_id = order_response.get('orderId')

        final_message = f"✅ <b>تم {trade_action_text} بنجاح!</b>\n\n"
        final_message += f"<b>الزوج:</b> {pair}\n"
        final_message += f"<b>الكمية المنفذة:</b> {format_decimal(executed_qty_dec, symbol_filters, 'LOT_SIZE')}\n"
        if avg_price > 0:
            final_message += f"<b>متوسط السعر:</b> {format_decimal(avg_price, symbol_filters, 'PRICE_FILTER')}\n"
        final_message += f"<b>الحالة:</b> {status}\n"
        final_message += f"<b>معرف الأمر:</b> {order_id}\n"

        # --- Place SL/TP Orders ---
        if status == ORDER_STATUS_FILLED and executed_qty_dec > 0:
            sl_tp_status_msg = await _place_sltp_orders(
                context, pair, trade_side, executed_qty_dec, sl_price, tp_price, symbol_filters
            )
        elif status != ORDER_STATUS_FILLED:
             sl_tp_status_msg = f"\n\nℹ️ لم يتم تنفيذ أمر السوق بالكامل ({status})، تم تخطي وضع SL/TP."
        else:
             sl_tp_status_msg = "\n\nℹ️ لم يتم تنفيذ كمية في أمر السوق، تم تخطي وضع SL/TP."

        final_message += sl_tp_status_msg
        await _send_or_edit(update, context, final_message, final_keyboard, edit=True, parse_mode=ParseMode.HTML)

    # --- Specific Binance Error Handling ---
    except (BinanceAPIException, BinanceOrderException) as e:
        logger.error(f"Binance API/Order Error ({trade_action_text}): Code={e.code}, Msg={e.message}")
        error_msg = f"❌ **خطأ من Binance ({trade_action_text}):**\n\n"
        if e.code == -2010: error_msg += "رصيد غير كافٍ أو خطأ في قيود التداول."
        elif e.code == -1013: error_msg += "خطأ في قيود السعر/الكمية (مثل MIN_NOTIONAL)."
        elif e.code == -1121: error_msg += "زوج العملات غير صالح."
        elif e.code == -2015: error_msg += "مفتاح API غير صالح أو صلاحيات غير كافية."
        else: error_msg += f"<code>{e.message}</code>"
        error_msg += f"\n(Code: {e.code})"
        await _send_or_edit(update, context, error_msg, final_keyboard, edit=True, parse_mode=ParseMode.HTML)

    # --- Other Error Handling ---
    except ValueError as e:
         logger.error(f"Value Error ({trade_action_text}): {e}")
         error_msg = f"❌ **خطأ في البيانات:**\n\n<code>{e}</code>"
         await _send_or_edit(update, context, error_msg, final_keyboard, edit=True, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Unexpected Error ({trade_action_text}): {e}", exc_info=True)
        error_msg = "❌ حدث خطأ غير متوقع أثناء تنفيذ الأمر."
        await _send_or_edit(update, context, error_msg, final_keyboard, edit=True)

    # --- Cleanup ---
    finally:
        # Always end the conversation and clear data after attempt
        return await cancel_trade_conversation(update, context, clear_only=True)


async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE, conv_name: str = "العملية", clear_only: bool = False) -> int:
    """Cancels the current conversation and clears relevant user_data."""
    keys_to_clear = [
        'trade_side', 'trade_pair', 'trade_amount', 'sl_price', 'tp_price',
        'history_pair', 'search_pair', 'sell_asset', 'sell_available_qty',
        'current_price_for_sltp'
        # 'max_buy_usdt' # Don't clear user settings on cancel
    ]
    cleared_keys = []
    for key in keys_to_clear:
        if context.user_data.pop(key, None) is not None:
             cleared_keys.append(key)
    if cleared_keys:
        logger.debug(f"Cleared user_data for conversation {conv_name}. Keys: {cleared_keys}")
    else:
        logger.debug(f"No specific data to clear in user_data for conversation {conv_name}.")

    if not clear_only:
        logger.info(f"User cancelled conversation: {conv_name}.")
        message_text = f"تم إلغاء {conv_name}."
        # Send cancellation message and show main menu
        await _send_or_edit(update, context, message_text, reply_markup=None, edit=True) # Edit current message first
        await show_main_menu(update, context, edit_message=False) # Then send main menu as new message

    return ConversationHandler.END

async def cancel_trade_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE, clear_only: bool = False) -> int:
    """Specific cancel function for the trade conversation."""
    return await cancel_conversation(update, context, conv_name="التداول", clear_only=clear_only)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log Errors caused by Updates."""
    logger.error(f"Update {update} caused error: {context.error}", exc_info=context.error)
    # Optionally inform user about the error
    # if isinstance(update, Update) and update.effective_chat:
    #    await context.bot.send_message(chat_id=update.effective_chat.id, text="⚠️ حدث خطأ ما. يرجى المحاولة مرة أخرى لاحقًا.")


# --- معالج إلغاء الأوامر ---
async def cancel_order_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the cancellation of a specific open order."""
    query = update.callback_query
    if not query or not query.data: return
    callback_data = query.data

    if not callback_data.startswith(CALLBACK_CANCEL_ORDER_PREFIX):
        logger.warning(f"Unexpected callback data for order cancellation: {callback_data}")
        await query.answer("خطأ: بيانات غير متوقعة.", show_alert=True)
        return

    try:
        # Extract symbol and orderId
        # Format: cancel_order_{SYMBOL}_{ORDER_ID}
        parts = callback_data.split('_', 3) # Split max 3 times
        if len(parts) != 4 or parts[0] != 'cancel' or parts[1] != 'order':
             raise ValueError("Invalid cancel order callback format")
        symbol = parts[2]
        order_id_str = parts[3]
        order_id = int(order_id_str) # Convert order ID to integer

        await query.answer(f"⏳ جاري إلغاء الأمر {order_id}...")

        if not binance_client:
            await query.edit_message_text("⚠️ اتصال Binance غير متاح لإلغاء الأمر.", reply_markup=query.message.reply_markup) # Keep old buttons
            return

        logger.info(f"Attempting to cancel order: Symbol={symbol}, OrderID={order_id}")
        cancel_result = binance_client.cancel_order(symbol=symbol, orderId=order_id)
        logger.info(f"Cancel order result: {cancel_result}")

        await query.answer(f"✅ تم إلغاء الأمر {order_id} بنجاح!", show_alert=True)

        # Refresh the orders list after cancellation
        await show_orders_info(update, context) # This will edit the message

    except (BinanceAPIException, BinanceOrderException) as e:
        logger.error(f"Failed to cancel order {order_id_str} on {symbol}: Code={e.code}, Msg={e.message}")
        error_msg = f"فشل إلغاء الأمر {order_id_str}: "
        if e.code == -2011: error_msg += "الأمر غير موجود أو تم إلغاؤه بالفعل."
        else: error_msg += f"{e.message} (Code: {e.code})"
        await query.answer(error_msg, show_alert=True)
        # Optionally refresh the list even on error to show the current state
        await show_orders_info(update, context)
    except ValueError:
         logger.error(f"Invalid order ID format in callback: {callback_data}")
         await query.answer("خطأ في بيانات معرف الأمر.", show_alert=True)
    except Exception as e:
        logger.error(f"Generic error cancelling order {order_id_str} on {symbol}: {e}", exc_info=True)
        await query.answer(f"⚠️ حدث خطأ غير متوقع أثناء إلغاء الأمر {order_id_str}.", show_alert=True)
        # Optionally refresh the list
        await show_orders_info(update, context)


# --- الدالة الرئيسية ---
def main() -> None:
    """Main function to set up and run the bot."""
    if not TELEGRAM_BOT_TOKEN:
        logger.critical("Token Error! TELEGRAM_BOT_TOKEN not found.")
        return
    if not binance_client:
         logger.warning("Binance client not initialized. Trading functions will be disabled.")
    if not redis_client:
         logger.warning("Redis client not initialized. Caching will use bot_data.")

    # --- Application Setup ---
    # persistence = PicklePersistence(filepath='bot_persistence.pkl')
    # NOTE on Persistence: See comment above persistence variable definition.
    # application = Application.builder().token(TELEGRAM_BOT_TOKEN).persistence(persistence).build()
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # --- Fetch Exchange Info on Startup & Periodically --- <<<--- تعديل
    # Run once on startup
    application.job_queue.run_once(fetch_and_cache_exchange_info, when=timedelta(seconds=2))
    # Run periodically (e.g., every hour)
    application.job_queue.run_repeating(fetch_and_cache_exchange_info, interval=timedelta(hours=1), first=timedelta(hours=1))

    # --- Conversation Handlers ---
    trade_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(trade_start, pattern=f"^{CALLBACK_START_BUY}$"),
            CallbackQueryHandler(trade_start, pattern=f"^{CALLBACK_START_SELL}$"),
            CallbackQueryHandler(handle_buy_favorite_selection, pattern=f"^{CALLBACK_BUY_FAVORITE_PREFIX}"),
            CallbackQueryHandler(handle_buy_other_pair, pattern=f"^{CALLBACK_BUY_OTHER_PAIR}$"),
        ],
        states={
            T_ASK_PAIR: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_pair_handler)],
            T_ASK_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_amount_handler)],
            T_CHOOSE_SELL_ASSET: [CallbackQueryHandler(choose_sell_asset_handler, pattern=f"^{CALLBACK_SELL_ASSET_PREFIX}")],
            T_ASK_SELL_AMOUNT: [
                CallbackQueryHandler(ask_sell_amount_handler, pattern=f"^{CALLBACK_SELL_AMOUNT_ALL}$|^{CALLBACK_SELL_AMOUNT_PARTIAL}$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, ask_amount_handler) # Handles partial amount input
            ],
            T_ASK_SLTP_CHOICE: [CallbackQueryHandler(ask_sltp_choice_handler, pattern=f"^{CALLBACK_ADD_SLTP_YES}$|^{CALLBACK_ADD_SLTP_NO}$|^{CALLBACK_ADD_SLTP_PERCENT}$")],
            T_ASK_SL_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND | filters.Regex(r'^/skip$'), ask_sl_price_handler)],
            T_ASK_TP_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND | filters.Regex(r'^/skip$'), ask_tp_price_handler)],
            T_ASK_SL_PERCENT: [CallbackQueryHandler(ask_sl_percent_handler, pattern=f"^{CALLBACK_SL_PERCENT_PREFIX}")],
            T_ASK_TP_PERCENT: [CallbackQueryHandler(ask_tp_percent_handler, pattern=f"^{CALLBACK_TP_PERCENT_PREFIX}|^({CALLBACK_SKIP_TP})$")],
            T_CONFIRM_TRADE_STATE: [CallbackQueryHandler(confirm_trade_final_handler, pattern=f"^{CALLBACK_CONFIRM_TRADE}$")],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_trade_conversation, pattern=f"^{CALLBACK_CANCEL_TRADE}$"),
            CommandHandler("start", cancel_trade_conversation), # Allow /start to cancel
            CommandHandler("cancel", cancel_trade_conversation) # Allow /cancel to cancel
        ],
        allow_reentry=True, name="trade_conv"
        # , persistent=True, block=False
    )

    fav_add_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_favorite_start, pattern=f"^{CALLBACK_ADD_FAVORITE_START}$")],
        states={ FAV_ASK_ADD_PAIR: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_favorite_pair_handler)] },
        fallbacks=[
            CallbackQueryHandler(lambda u, c: cancel_conversation(u, c, "إضافة المفضلة"), pattern=f"^{CALLBACK_CANCEL}$"),
            CommandHandler("start", lambda u, c: cancel_conversation(u, c, "إضافة المفضلة")),
            CommandHandler("cancel", lambda u, c: cancel_conversation(u, c, "إضافة المفضلة"))
        ],
        allow_reentry=True, name="fav_add_conv"
        # , persistent=True, block=False
    )

    settings_conv = ConversationHandler(
         entry_points=[CallbackQueryHandler(settings_set_max_buy_start, pattern=f"^{CALLBACK_SET_MAX_BUY_START}$")],
         states={ SET_ASK_MAX_BUY_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, settings_ask_max_buy_amount_handler)] },
         fallbacks=[
             CallbackQueryHandler(lambda u, c: cancel_conversation(u, c, "الإعدادات"), pattern=f"^{CALLBACK_CANCEL}$"),
             CommandHandler("start", lambda u, c: cancel_conversation(u, c, "الإعدادات")),
             CommandHandler("cancel", lambda u, c: cancel_conversation(u, c, "الإعدادات")),
             CommandHandler("settings", lambda u, c: cancel_conversation(u, c, "الإعدادات")) # Allow /settings to cancel
         ],
         allow_reentry=True, name="settings_conv"
         # , persistent=True, block=False
     )

    search_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(search_manual_start, pattern=f"^{CALLBACK_SEARCH_MANUAL_START}$")],
        states={ S_ASK_PAIR: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_ask_pair_handler)] },
        fallbacks=[
            CallbackQueryHandler(lambda u, c: cancel_conversation(u, c, "البحث"), pattern=f"^{CALLBACK_CANCEL}$"),
            CommandHandler("start", lambda u, c: cancel_conversation(u, c, "البحث")),
            CommandHandler("cancel", lambda u, c: cancel_conversation(u, c, "البحث"))
        ],
        allow_reentry=True, name="search_conv"
        # , persistent=True, block=False
    )

    history_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(history_by_pair_start, pattern=f"^{CALLBACK_HISTORY_BY_PAIR_START}$")],
        states={ H_ASK_PAIR: [MessageHandler(filters.TEXT & ~filters.COMMAND, history_ask_pair_handler)] },
        fallbacks=[
            CallbackQueryHandler(lambda u, c: cancel_conversation(u, c, "السجل"), pattern=f"^{CALLBACK_CANCEL}$"),
            CommandHandler("start", lambda u, c: cancel_conversation(u, c, "السجل")),
            CommandHandler("cancel", lambda u, c: cancel_conversation(u, c, "السجل"))
        ],
        allow_reentry=True, name="history_conv"
        # , persistent=True, block=False
    )

    # --- Add Handlers ---
    # Conversation Handlers (Group 1 - lower priority)
    application.add_handler(trade_conv, group=1)
    application.add_handler(fav_add_conv, group=1)
    application.add_handler(search_conv, group=1)
    application.add_handler(history_conv, group=1)
    application.add_handler(settings_conv, group=1)

    # Command Handlers (Group 0 - higher priority)
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command_handler))
    application.add_handler(CommandHandler("balance", balance_command_handler))
    application.add_handler(CommandHandler("orders", orders_command_handler))
    application.add_handler(CommandHandler("settings", settings_command_handler))
    # General cancel command (should have lower priority than conversation fallbacks)
    # Handled by fallbacks within conversations, add a general one for outside conv?
    application.add_handler(CommandHandler("cancel", lambda u, c: cancel_conversation(u, c, "العملية الحالية")))


    # Callback Query Handlers (Group 0 - higher priority than conversations)
    # Navigation
    application.add_handler(CallbackQueryHandler(navigation_button_handler, pattern=f"^{CALLBACK_MAIN_MENU}$"))
    application.add_handler(CallbackQueryHandler(navigation_button_handler, pattern=f"^{CALLBACK_GOTO_TRADING}$"))
    application.add_handler(CallbackQueryHandler(navigation_button_handler, pattern=f"^{CALLBACK_GOTO_ACCOUNT}$"))
    application.add_handler(CallbackQueryHandler(navigation_button_handler, pattern=f"^{CALLBACK_GOTO_SEARCH}$"))
    application.add_handler(CallbackQueryHandler(navigation_button_handler, pattern=f"^{CALLBACK_GOTO_HISTORY}$"))
    application.add_handler(CallbackQueryHandler(navigation_button_handler, pattern=f"^{CALLBACK_GOTO_FAVORITES}$"))
    application.add_handler(CallbackQueryHandler(navigation_button_handler, pattern=f"^{CALLBACK_GOTO_SETTINGS}$"))
    application.add_handler(CallbackQueryHandler(navigation_button_handler, pattern=f"^{CALLBACK_SHOW_HELP}$"))
    application.add_handler(CallbackQueryHandler(navigation_button_handler, pattern=f"^{CALLBACK_SHOW_BALANCE}$"))
    application.add_handler(CallbackQueryHandler(navigation_button_handler, pattern=f"^{CALLBACK_SHOW_ORDERS}$"))

    # Specific actions
    application.add_handler(CallbackQueryHandler(show_gainers, pattern=f"^{CALLBACK_SHOW_GAINERS}$"))
    application.add_handler(CallbackQueryHandler(show_losers, pattern=f"^{CALLBACK_SHOW_LOSERS}$"))
    application.add_handler(CallbackQueryHandler(show_today_trades, pattern=f"^{CALLBACK_HISTORY_TODAY}$"))

    # Favorite removal (handled outside conversation)
    application.add_handler(CallbackQueryHandler(remove_favorite_start, pattern=f"^{CALLBACK_REMOVE_FAVORITE_START}$"))
    application.add_handler(CallbackQueryHandler(remove_favorite_pair_handler, pattern=f"^{CALLBACK_REMOVE_FAVORITE_PREFIX}"))

    # Order Cancellation Handler (Group 0 - high priority) <<<--- جديد
    application.add_handler(CallbackQueryHandler(cancel_order_handler, pattern=f"^{CALLBACK_CANCEL_ORDER_PREFIX}"))

    # Placeholders
    application.add_handler(CallbackQueryHandler(lambda u, c: show_placeholder_message(u, c, "الأرباح والخسائر"), pattern=f"^{CALLBACK_SHOW_PNL}$"))
    application.add_handler(CallbackQueryHandler(lambda u, c: show_placeholder_message(u, c, "التحليل الفني"), pattern=f"^{CALLBACK_GOTO_ANALYSIS}$"))

    # General Cancel Button (if pressed outside a conversation context)
    application.add_handler(CallbackQueryHandler(lambda u, c: cancel_conversation(u, c, "العملية"), pattern=f"^{CALLBACK_CANCEL}$"))


    # Error Handler (always good to have)
    application.add_error_handler(error_handler)

    # --- Start Bot ---
    logger.info("Starting bot polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
    logger.info("Bot stopped.")

# --- Entry Point ---
if __name__ == '__main__':
    main()
