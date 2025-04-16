# بداية ملف bot.py
import os
import logging
import re
import time # للتخزين المؤقت
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_UP, Context as DecimalContext # للتقريب الدقيق والتحكم بالدقة
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Any, Set, Optional, Union # لتحسين Type Hinting
import asyncio
from collections import defaultdict

# --- تحميل المتغيرات من ملف .env ---
# تأكد من تثبيت المكتبة: pip install python-dotenv
try:
    from dotenv import load_dotenv
    load_dotenv()
    logger = logging.getLogger(__name__)
    logger.info("تم تحميل ملف .env (إذا كان موجوداً).")
except ImportError:
    print("تحذير: مكتبة python-dotenv غير مثبتة. لن يتم تحميل ملف .env.")
    print("pip install python-dotenv")
    logger = logging.getLogger(__name__)


# --- استيراد مكتبات البوت والـ API ---
# تأكد من تثبيت المكتبات: pip install python-telegram-bot python-binance python-dateutil
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
    # from dateutil.parser import parse as parse_datetime
except ImportError as e:
    log_func = logger.error if 'logger' in globals() else print
    log_func(f"خطأ: لم يتم العثور على مكتبة ضرورية: {e}. يرجى تثبيت المكتبات المطلوبة.")
    log_func("pip install python-telegram-bot[persistence] python-binance python-dateutil") # إضافة [persistence]
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
try:
    from config import (
        TELEGRAM_BOT_TOKEN, BINANCE_API_KEY,
        BINANCE_SECRET_KEY, MAX_TRADE_AMOUNT_USDT,
        RESTRICTED_PAIRS, LOG_TRADES
    )
except ImportError as e:
    logger.critical(f"فشل في استيراد ملف الإعدادات: {e}")
    exit("Configuration Error")

def log_trade(trade_details: dict) -> None:
    """تسجيل تفاصيل عملية التداول"""
    if LOG_TRADES:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{now}] {trade_details}"
        logger.info(log_entry)
        try:
            with open('trades_log.txt', 'a', encoding='utf-8') as f:
                f.write(f"{log_entry}\n")
        except Exception as e:
            logger.error(f"خطأ في حفظ سجل التداول: {e}")

# --- التحقق وتهيئة Binance Client ---
binance_client: Optional[Client] = None
if not TELEGRAM_BOT_TOKEN:
    logger.critical("TELEGRAM_BOT_TOKEN غير موجود في متغيرات البيئة!")
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

# --- تعريف بيانات الاستدعاء (Callback Data) ---
# (نفس تعريفات الـ Callbacks السابقة)
CALLBACK_MAIN_MENU = "main_menu"; CALLBACK_GOTO_TRADING = "goto_trading"; CALLBACK_GOTO_ACCOUNT = "goto_account"
CALLBACK_GOTO_SEARCH = "goto_search"; CALLBACK_GOTO_HISTORY = "goto_history"; CALLBACK_GOTO_ANALYSIS = "goto_analysis"
CALLBACK_GOTO_FAVORITES = "goto_favorites"; CALLBACK_GOTO_SETTINGS = "goto_settings"
CALLBACK_GOTO_ALERTS = "goto_alerts"
CALLBACK_SHOW_HELP = "show_help"; CALLBACK_SHOW_BALANCE = "show_balance"; CALLBACK_SHOW_ORDERS = "show_orders"
CALLBACK_SHOW_PNL = "show_pnl"; CALLBACK_START_BUY = "start_buy"; CALLBACK_START_SELL = "start_sell"
CALLBACK_SHOW_GAINERS = "show_gainers"; CALLBACK_SHOW_LOSERS = "show_losers"; CALLBACK_SEARCH_MANUAL_START = "search_manual_start"
CALLBACK_HISTORY_TODAY = "history_today"; CALLBACK_HISTORY_BY_PAIR_START = "history_by_pair_start"
CALLBACK_CONFIRM_TRADE = "confirm_trade_final"; CALLBACK_CANCEL_TRADE = "cancel_trade_conv"
CALLBACK_ADD_SLTP_YES = "add_sltp_yes"; CALLBACK_ADD_SLTP_NO = "add_sltp_no"; CALLBACK_ADD_SLTP_PERCENT = "add_sltp_percent"
CALLBACK_SKIP_TP = "skip_tp"; CALLBACK_CANCEL = "cancel_action"
CALLBACK_CANCEL_ALL_SELL_ORDERS = "cancel_all_sell_orders"  # Add new callback constant
# Quick Sell callbacks
CALLBACK_QUICK_SELL_PAIR = "quick_sell_pair_"
CALLBACK_QS_SL_PERC_PREFIX = "qs_sl_perc_"
CALLBACK_QS_TP_PERC_PREFIX = "qs_tp_perc_"
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
# التنبيهات
CALLBACK_TOGGLE_ALERTS = "alert_toggle"
CALLBACK_SET_ALERT_THRESHOLD_START = "alert_set_thresh_start"
CALLBACK_SET_ALERT_INTERVAL_START = "alert_set_intrvl_start"
CALLBACK_SET_ALERT_SPAM_DELAY_START = "alert_set_spam_start"
CALLBACK_ALERT_PERC_PREFIX = "alert_perc_"
# الشراء السريع
CALLBACK_QUICK_BUY_START = "quick_buy_start"
CALLBACK_QB_SL_PERC_PREFIX = "qb_sl_perc_"
CALLBACK_QB_TP_PERC_PREFIX = "qb_tp_perc_"
CALLBACK_QB_SKIP_TP = "qb_skip_tp"
CALLBACK_HISTORY_MANUAL_INPUT = "history_manual_input"
# ثوابت التنبيهات المخصصة
CALLBACK_CUSTOM_ALERT_ADD = "custom_alert_add"
CALLBACK_CUSTOM_ALERT_REMOVE = "custom_alert_remove"
CALLBACK_CUSTOM_ALERT_LIST = "custom_alert_list"
CALLBACK_CUSTOM_ALERT_THRESHOLD = "custom_alert_threshold"
CUSTOM_ALERT_ASK_SYMBOL = "custom_alert_symbol"
CUSTOM_ALERT_ASK_THRESHOLD = "custom_alert_threshold"
# Add new callback constants
CALLBACK_QUICK_SELL_START = "quick_sell_start"
CALLBACK_QUICK_SELL_PAIR = "quick_sell_pair_"
CALLBACK_QUICK_SELL_OCO = "quick_sell_oco_"
CALLBACK_QS_SL_PERC_PREFIX = "qs_sl_perc_"
CALLBACK_QS_TP_PERC_PREFIX = "qs_tp_perc_"


# --- تعريف حالات المحادثة ---
(
    T_ASK_PAIR, T_ASK_AMOUNT, T_ASK_SLTP_CHOICE, T_ASK_SL_PRICE, T_ASK_TP_PRICE, T_CONFIRM_TRADE_STATE, # تداول
    S_ASK_PAIR, # بحث
    H_ASK_PAIR, # سجل
    T_CHOOSE_SELL_ASSET, T_ASK_SELL_AMOUNT, # بيع
    T_ASK_SL_PERCENT, T_ASK_TP_PERCENT, # نسب SL/TP
    FAV_ASK_ADD_PAIR, # إضافة مفضلة
    SET_ASK_MAX_BUY_AMOUNT, # إعدادات: حد الشراء
    ALERT_ASK_THRESHOLD, # إعدادات التنبيهات
    QB_ASK_PAIR, QB_ASK_AMOUNT, QB_ASK_SL_PERCENT, QB_ASK_TP_PERCENT, # حالات الشراء السريع
) = range(19) # تحديث العدد ليطابق عدد الحالات


# --- ثوابت للتخزين المؤقت وإعدادات المفضلة ---
CACHE_DURATION_SECONDS = 300 # 5 دقائق
MAX_FAVORITES = 15
MAX_FAVORITE_BUTTONS = 5
# <<<--- إضافة قائمة المفضلة الافتراضية --- >>>
DEFAULT_FAVORITE_PAIRS: Set[str] = {'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT', 'ADAUSDT'} # 6 عملات USDT افتراضية
EXCHANGE_INFO_CACHE_KEY = "exchange_info"
SYMBOLS_CACHE_KEY = "valid_symbols"
TICKERS_CACHE_KEY = "tickers_cache" # لتخزين أسعار Ticker
DEFAULT_MAX_BUY_USDT = Decimal('1000') # حد شراء افتراضي بالدولار
# إعدادات التنبيهات الافتراضية <<<--- إضافة هذا المقطع
DEFAULT_ALERT_ENABLED = False
DEFAULT_ALERT_THRESHOLD = Decimal('5.0') # نسبة 5%
DEFAULT_ALERT_INTERVAL_MINUTES = 5 # التحقق كل 5 دقائق
DEFAULT_ALERT_SPAM_DELAY_MINUTES = 60 # إرسال تنبيه لنفس الزوج كل 60 دقيقة كحد أقصى

# --- دوال مساعدة ---

async def fetch_and_cache_exchange_info(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fetches and caches exchange information including valid symbols."""
    if not binance_client:
        logger.warning("Binance client not initialized. Cannot fetch exchange info.")
        return
    try:
        logger.info("Fetching exchange information from Binance...")
        exchange_info = binance_client.get_exchange_info()
        context.bot_data[EXCHANGE_INFO_CACHE_KEY] = exchange_info
        valid_symbols = {s['symbol'] for s in exchange_info.get('symbols', []) if s.get('status') == 'TRADING'}
        context.bot_data[SYMBOLS_CACHE_KEY] = valid_symbols
        logger.info(f"Cached exchange info and {len(valid_symbols)} valid symbols.")
    except (BinanceAPIException, BinanceRequestException) as e:
        logger.error(f"Binance API Error fetching exchange info: {e}")
    except Exception as e:
        logger.error(f"Error fetching exchange info: {e}", exc_info=True)

def is_valid_symbol(symbol: str, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Checks if a symbol is valid and trading based on cached info."""
    valid_symbols: Set[str] = context.bot_data.get(SYMBOLS_CACHE_KEY, set())
    if not valid_symbols:
        logger.warning("Valid symbols cache is empty. Cannot validate symbol.")
        # Consider fetching here as a fallback, but might slow down requests
        return False
    return symbol in valid_symbols

def get_symbol_filters(symbol: str, context: ContextTypes.DEFAULT_TYPE) -> Dict[str, Dict[str, Any]]:
    """Gets all filters for a symbol from cached exchange info."""
    exchange_info = context.bot_data.get(EXCHANGE_INFO_CACHE_KEY)
    symbol_filters = {}
    if exchange_info and 'symbols' in exchange_info:
        for symbol_data in exchange_info['symbols']:
            if symbol_data['symbol'] == symbol:
                for f in symbol_data.get('filters', []):
                    symbol_filters[f.get('filterType')] = f
                break
    if not symbol_filters:
         # Fallback to individual fetch if needed, but less efficient
         info = get_symbol_info_direct(symbol, context) # Use direct fetch helper
         if info:
              for f in info.get('filters', []):
                  symbol_filters[f.get('filterType')] = f
    return symbol_filters

def get_symbol_info_direct(symbol: str, context: ContextTypes.DEFAULT_TYPE) -> Optional[Dict[str, Any]]:
    """Directly fetches symbol info (used as fallback or if cache is unreliable)."""
    if not binance_client: return None
    cache_key = f"symbol_info_direct_{symbol}" # Separate cache key for direct fetches
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
    """Gets cached ticker prices, refreshing if needed or forced."""
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
    """Fetches the current ticker price for a symbol, using cache."""
    if not binance_client: return None

    # Use the cache that stores all tickers
    tickers = await get_cached_tickers(context, quote_asset='USDT') # Get the main cache

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
    exchange_info = context.bot_data.get(EXCHANGE_INFO_CACHE_KEY)
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
        formatted_value = f"{value:.{precision}f}"
        # Check if the formatted value resulted in scientific notation (less common with 'f')
        if 'e' in formatted_value.lower():
             # Fallback to normalize() which handles scientific notation better for very small/large numbers
             logger.debug(f"Using normalize() for value {value} due to potential scientific notation.")
             return str(value.normalize())
        return formatted_value
    except Exception as e:
        logger.error(f"Error formatting decimal {value} with precision {precision}: {e}")
        # Fallback to simple string conversion or normalize
        return str(value.normalize())

def format_number(number: Decimal, max_decimals: int = 8, min_decimals: int = 2) -> str:
    """
    Formats a number to be more readable:
    - Reduces decimal places based on number size
    - Adds K/M/B suffixes for large numbers
    - Ensures important precision is not lost
    """
    if number == 0:
        return "0"
    
    abs_num = abs(number)
    sign = "-" if number < 0 else ""
    
    # Handle large numbers
    if abs_num >= 1_000_000_000:  # Billions
        return f"{sign}{abs_num / 1_000_000_000:.2f}B"
    elif abs_num >= 1_000_000:  # Millions
        return f"{sign}{abs_num / 1_000_000:.2f}M"
    elif abs_num >= 1_000:  # Thousands
        return f"{sign}{abs_num / 1_000:.2f}K"
    
    # Handle small numbers
    if abs_num >= 1:
        decimals = min(max_decimals, max(min_decimals, 2))
    elif abs_num >= 0.1:
        decimals = min(max_decimals, max(min_decimals, 4))
    elif abs_num >= 0.01:
        decimals = min(max_decimals, max(min_decimals, 6))
    else:
        decimals = max_decimals
    
    # Format the number with appropriate decimals
    formatted = f"{{:.{decimals}f}}".format(abs_num)
    # Remove trailing zeros after decimal point
    if '.' in formatted:
        formatted = formatted.rstrip('0').rstrip('.')
    
    return sign + formatted

def format_trade_history(trades: list, limit: int = 20, include_stats: bool = True, show_trades: bool = False) -> str:
    """Formats trade statistics with optional trade history."""
    if not trades: return "لا توجد صفقات مسجلة تطابق البحث."
    
    # Calculate statistics
    total_buy_qty = Decimal('0')
    total_sell_qty = Decimal('0')
    total_buy_value = Decimal('0')
    total_sell_value = Decimal('0')
    total_commission = Decimal('0')
    commission_assets = set()
    
    for trade in trades:
        qty = decimal_context.create_decimal(trade['qty'])
        price = decimal_context.create_decimal(trade['price'])
        quote_qty = decimal_context.create_decimal(trade['quoteQty'])
        commission = decimal_context.create_decimal(trade.get('commission', '0'))
        commission_asset = trade.get('commissionAsset', '')
        
        if trade.get('isBuyer'):
            total_buy_qty += qty
            total_buy_value += quote_qty
        else:
            total_sell_qty += qty
            total_sell_value += quote_qty
        
        if commission > 0:
            total_commission += commission
            commission_assets.add(commission_asset)
    
    # Calculate net quantities and values
    net_qty = total_buy_qty - total_sell_qty
    net_value = total_sell_value - total_buy_value # Positive means profit
    avg_buy_price = (total_buy_value / total_buy_qty) if total_buy_qty > 0 else Decimal('0')
    avg_sell_price = (total_sell_value / total_sell_qty) if total_sell_qty > 0 else Decimal('0')
    
    # Determine profit/loss status and emoji
    if net_value > 0:
        status_emoji = "🟢"  # Green circle for profit
        status_text = "ربح"
    elif net_value < 0:
        status_emoji = "🔴"  # Red circle for loss
        status_text = "خسارة"
    else:
        status_emoji = "⚪"  # White circle for neutral
        status_text = "متعادل"
    
    # Build statistics text
    stats_text = f"📊 <b>إحصائيات التداول {status_emoji}</b>\n\n"
    
    # Add trade counts
    buy_trades = sum(1 for t in trades if t.get('isBuyer'))
    sell_trades = sum(1 for t in trades if not t.get('isBuyer'))
    stats_text += f"عدد صفقات الشراء: {buy_trades}\n"
    stats_text += f"عدد صفقات البيع: {sell_trades}\n\n"
    
    # Add volume statistics with formatted numbers
    stats_text += f"إجمالي الشراء: {format_number(total_buy_qty)} "
    stats_text += f"(${format_number(total_buy_value)})\n"
    
    if total_buy_qty > 0:
        stats_text += f"متوسط سعر الشراء: ${format_number(avg_buy_price)}\n"
    
    stats_text += f"\nإجمالي البيع: {format_number(total_sell_qty)} "
    stats_text += f"(${format_number(total_sell_value)})\n"
    
    if total_sell_qty > 0:
        stats_text += f"متوسط سعر البيع: ${format_number(avg_sell_price)}\n"
    
    # Add net results with colored status
    stats_text += f"\nالصافي: {format_number(net_qty)}"
    stats_text += f"\nالنتيجة: {status_emoji} {status_text} (${format_number(net_value, min_decimals=2)})"
    
    if commission_assets:
        commission_text = []
        for asset in commission_assets:
            asset_commission = sum(
                decimal_context.create_decimal(t.get('commission', '0'))
                for t in trades
                if t.get('commissionAsset') == asset
            )
            commission_text.append(f"{format_number(asset_commission)} {asset}")
        stats_text += f"\n\nإجمالي العمولات: {' + '.join(commission_text)}"
    
    # Add trade history if requested
    if show_trades:
        stats_text += "\n\n---\n\n📜 <b>سجل الصفقات:</b>\n\n"
        count = 0
        for trade in reversed(trades):
            if count >= limit: 
                stats_text += f"\n... (تم عرض آخر {limit} صفقة)"
                break
            try:
                dt_object = datetime.fromtimestamp(trade['time'] / 1000)
                time_str = dt_object.strftime('%Y-%m-%d %H:%M:%S')
                side_emoji = "📈" if trade.get('isBuyer') else "📉"
                side_text = "شراء" if trade.get('isBuyer') else "بيع"
                qty = decimal_context.create_decimal(trade['qty'])
                price = decimal_context.create_decimal(trade['price'])
                quote_qty = decimal_context.create_decimal(trade['quoteQty'])
                commission = decimal_context.create_decimal(trade.get('commission', '0'))
                commission_asset = trade.get('commissionAsset', '')

                stats_text += f"{side_emoji} <b>{trade['symbol']}</b> - {side_text}\n"
                stats_text += f"  الكمية: {format_number(qty)}\n  السعر: {format_number(price)}\n  الإجمالي: {format_number(quote_qty)}\n"
                if commission > 0: stats_text += f"  العمولة: {format_number(commission)} {commission_asset}\n"
                stats_text += f"  الوقت: {time_str}\n---\n"
                count += 1
            except Exception as e:
                logger.error(f"خطأ في تنسيق الصفقة {trade.get('id')}: {e}")
                stats_text += f"<i>خطأ في عرض الصفقة ID: {trade.get('id')}</i>\n---\n"
    
    return stats_text

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
    """Builds the main menu keyboard in two columns."""
    keyboard = [
        [
            InlineKeyboardButton("📊 تداول الآن", callback_data=CALLBACK_GOTO_TRADING),
            InlineKeyboardButton("⭐ المفضلة", callback_data=CALLBACK_GOTO_FAVORITES)
        ],
        [
            InlineKeyboardButton("🔍 بحث عن عملة", callback_data=CALLBACK_GOTO_SEARCH),
            InlineKeyboardButton("💼 المحفظة", callback_data=CALLBACK_GOTO_ACCOUNT)
        ],
        [
            InlineKeyboardButton("📜 سجل التداول", callback_data=CALLBACK_GOTO_HISTORY),
            InlineKeyboardButton("⚙️ الإعدادات", callback_data=CALLBACK_GOTO_SETTINGS)
        ],
        [
            InlineKeyboardButton("🔔 التنبيهات", callback_data=CALLBACK_GOTO_ALERTS),
            InlineKeyboardButton("❓ المساعدة", callback_data=CALLBACK_SHOW_HELP)
        ],
    ]
    return InlineKeyboardMarkup(keyboard)

def build_trading_menu_keyboard() -> InlineKeyboardMarkup:
    """Builds the trading menu keyboard."""
    keyboard = [
        [ InlineKeyboardButton("📈 شراء", callback_data=CALLBACK_START_BUY),
          InlineKeyboardButton("📉 بيع", callback_data=CALLBACK_START_SELL), ],
        [InlineKeyboardButton("📋 الأوامر المفتوحة", callback_data=CALLBACK_SHOW_ORDERS)],
        [InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data=CALLBACK_MAIN_MENU)], ]
    return InlineKeyboardMarkup(keyboard)

def build_account_menu_keyboard() -> InlineKeyboardMarkup:
    """Builds the account menu keyboard."""
    keyboard = [
        [InlineKeyboardButton("💰 عرض الرصيد", callback_data=CALLBACK_SHOW_BALANCE)],
        [InlineKeyboardButton("📊 الأرباح والخسائر الكلية", callback_data=CALLBACK_SHOW_PNL)],
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
          InlineKeyboardButton("💵 بيع بقيمة محددة", callback_data=CALLBACK_SELL_AMOUNT_PARTIAL), ],
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


# <<<--- لوحة مفاتيح إعدادات التنبيهات (جديد) --- >>>
def build_alerts_menu_keyboard(context: ContextTypes.DEFAULT_TYPE) -> InlineKeyboardMarkup:
    """Builds the alerts settings menu keyboard."""
    user_id = context._user_id
    config = context.user_data.setdefault('alert_config', {})
    config.setdefault('enabled', DEFAULT_ALERT_ENABLED)
    config.setdefault('threshold_percent', DEFAULT_ALERT_THRESHOLD)
    config.setdefault('interval_minutes', DEFAULT_ALERT_INTERVAL_MINUTES)
    config.setdefault('spam_delay_minutes', DEFAULT_ALERT_SPAM_DELAY_MINUTES)

    is_enabled = config['enabled']
    threshold = config['threshold_percent']

    toggle_text = "❌ تعطيل التنبيهات" if is_enabled else "✅ تفعيل التنبيهات"
    threshold_text = f"📊 نسبة التغير العامة: {threshold:.1f}%"

    keyboard = [
        [InlineKeyboardButton(toggle_text, callback_data=CALLBACK_TOGGLE_ALERTS)],
        [InlineKeyboardButton(threshold_text, callback_data=CALLBACK_SET_ALERT_THRESHOLD_START)],
        [InlineKeyboardButton("🔔 التنبيهات المخصصة", callback_data=CALLBACK_CUSTOM_ALERT_LIST)],
        [InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data=CALLBACK_MAIN_MENU)],
    ]
    return InlineKeyboardMarkup(keyboard)

# <<<--- لوحة مفاتيح اختيار/إدخال نسبة التنبيه (جديد) --- >>>
def build_alert_threshold_keyboard(percentages: List[int] = [1, 2, 5, 10]) -> InlineKeyboardMarkup:
    """Builds a keyboard with alert threshold percentage options."""
    keyboard = []; row = []
    prefix = CALLBACK_ALERT_PERC_PREFIX
    for perc in percentages:
        row.append(InlineKeyboardButton(f"{perc}%", callback_data=f"{prefix}{perc}"))
        if len(row) == 4: # Adjust number per row if needed
             keyboard.append(row)
             row = []
    if row: keyboard.append(row)
    keyboard.append([InlineKeyboardButton("⌨️ إدخال نسبة يدوياً", callback_data="alert_manual_input")])
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data=CALLBACK_GOTO_ALERTS)])
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
    text = "قائمة المحفظة. اختر الإجراء:"; keyboard = build_account_menu_keyboard()
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

async def show_alerts_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """عرض قائمة التنبيهات"""
    query = update.callback_query
    if query: await query.answer()

    # التأكد من وجود الإعدادات الافتراضية
    config = context.user_data.setdefault('alert_config', {})
    config.setdefault('enabled', DEFAULT_ALERT_ENABLED)
    config.setdefault('threshold_percent', DEFAULT_ALERT_THRESHOLD)
    config.setdefault('interval_minutes', DEFAULT_ALERT_INTERVAL_MINUTES)
    config.setdefault('spam_delay_minutes', DEFAULT_ALERT_SPAM_DELAY_MINUTES)

    is_enabled = config['enabled']
    threshold = config['threshold_percent']
    status_text = "مفعلة ✅" if is_enabled else "معطلة ❌"

    # عرض التنبيهات المخصصة
    custom_alerts = context.user_data.setdefault('custom_alerts', {})
    
    text = f"🔔 <b>إعدادات التنبيهات</b>\n\n"
    text += f"الحالة: {status_text}\n"
    text += f"نسبة التغير العامة: {threshold}%\n\n"
    
    if custom_alerts:
        text += "<b>التنبيهات المخصصة النشطة:</b>\n"
        for symbol, settings in custom_alerts.items():
            # جلب السعر الحالي
            try:
                current_price = await get_current_price(symbol, context)
                price_text = f"السعر الحالي: ${current_price:f}" if current_price else "لا يوجد سعر حالي"
            except:
                price_text = "لا يوجد سعر حالي"

            # عرض آخر سعر تم التنبيه عنده
            last_price = settings.get('last_price')
            last_price_text = f"آخر سعر تنبيه: ${last_price:f}" if last_price else "لم يتم التنبيه بعد"

            # عرض وقت آخر تنبيه
            last_alert = settings.get('last_alert')
            if last_alert:
                last_alert_text = last_alert.strftime('%Y-%m-%d %H:%M:%S')
            else:
                last_alert_text = "لم يتم التنبيه بعد"

            text += f"\n• <b>{symbol}</b>\n"
            text += f"  نسبة التنبيه: {settings['threshold']}%\n"
            text += f"  {price_text}\n"
            text += f"  {last_price_text}\n"
            text += f"  آخر تنبيه: {last_alert_text}\n"
            text += "  ──────────\n"
    else:
        text += "لا توجد تنبيهات مخصصة حالياً\n\n"
    
    keyboard = []
    keyboard.append([InlineKeyboardButton("✅ تفعيل التنبيهات" if not is_enabled else "❌ تعطيل التنبيهات", 
                                        callback_data=CALLBACK_TOGGLE_ALERTS)])
    keyboard.append([InlineKeyboardButton(f"📊 تعديل نسبة التغير العامة ({threshold}%)", 
                                        callback_data=CALLBACK_SET_ALERT_THRESHOLD_START)])
    keyboard.append([InlineKeyboardButton("➕ إضافة تنبيه مخصص", callback_data=CALLBACK_CUSTOM_ALERT_ADD)])
    
    if custom_alerts:
        for symbol in custom_alerts:
            keyboard.append([InlineKeyboardButton(f"❌ حذف تنبيه {symbol}", 
                                               callback_data=f"{CALLBACK_CUSTOM_ALERT_REMOVE}_{symbol}")])
    
    keyboard.append([InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data=CALLBACK_MAIN_MENU)])
    await _send_or_edit(update, context, text, InlineKeyboardMarkup(keyboard), edit=True)

async def start_add_custom_alert(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """بدء عملية إضافة تنبيه مخصص"""
    query = update.callback_query
    if query: await query.answer()
    text = "الرجاء إدخال رمز العملة (مثال: BTCUSDT):"
    keyboard = build_cancel_keyboard(CALLBACK_GOTO_ALERTS)
    await _send_or_edit(update, context, text, keyboard, edit=True)
    return CUSTOM_ALERT_ASK_SYMBOL

async def handle_custom_alert_symbol(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """معالجة إدخال رمز العملة للتنبيه المخصص"""
    symbol = update.message.text.strip().upper()
    
    try:
        current_price = await get_current_price(symbol, context)
        if current_price is None:
            raise ValueError("رمز غير صالح")
    except:
        await update.message.reply_text(
            f"⚠️ الرمز '{symbol}' غير صالح أو غير متداول حالياً. الرجاء إدخال رمز صحيح:",
            reply_markup=build_cancel_keyboard(CALLBACK_GOTO_ALERTS)
        )
        return CUSTOM_ALERT_ASK_SYMBOL
    
    context.user_data['temp_custom_alert'] = {'symbol': symbol}
    text = f"الرجاء إدخال نسبة التغير للتنبيه لـ {symbol} (مثال: 5):"
    keyboard = build_cancel_keyboard(CALLBACK_GOTO_ALERTS)
    await update.message.reply_text(text, reply_markup=keyboard)
    return CUSTOM_ALERT_ASK_THRESHOLD

async def handle_custom_alert_threshold(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """معالجة إدخال نسبة التغير للتنبيه المخصص"""
    try:
        threshold = Decimal(update.message.text.strip())
        if threshold <= 0:
            raise ValueError("يجب أن تكون النسبة أكبر من 0")
            
        temp_alert = context.user_data.pop('temp_custom_alert')
        symbol = temp_alert['symbol']
        
        custom_alerts = context.user_data.setdefault('custom_alerts', {})
        custom_alerts[symbol] = {
            'threshold': threshold,
            'last_price': None,
            'last_alert': None
        }
        
        text = f"✅ تم إضافة تنبيه لـ {symbol} عند تغير {threshold}%"
        await update.message.reply_text(text)
        await show_alerts_menu(update, context)
        return ConversationHandler.END
        
    except (ValueError, InvalidOperation) as e:
        text = "❌ خطأ: الرجاء إدخال رقم صحيح أو عشري موجب"
        keyboard = build_cancel_keyboard(CALLBACK_GOTO_ALERTS)
        await update.message.reply_text(text, reply_markup=keyboard)
        return CUSTOM_ALERT_ASK_THRESHOLD

async def remove_custom_alert(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """حذف تنبيه مخصص"""
    query = update.callback_query
    await query.answer()
    
    symbol = query.data.split('_')[-1]
    custom_alerts = context.user_data.get('custom_alerts', {})
    
    if symbol in custom_alerts:
        del custom_alerts[symbol]
        text = f"✅ تم حذف التنبيه لـ {symbol}"
    else:
        text = "❌ لم يتم العثور على التنبيه"
    
    await query.message.reply_text(text)
    await show_alerts_menu(update, context)

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
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=loading_message.message_id)
            except Exception:
                pass

    except (BinanceAPIException, BinanceRequestException) as e:
        logger.error(f"Binance API Error showing balance: {e}")
        error_text = f"⚠️ حدث خطأ من Binance أثناء جلب الرصيد:\n<code>{e.message}</code>"
        keyboard = [[InlineKeyboardButton("🔙 رجوع لقائمة الحساب", callback_data=CALLBACK_GOTO_ACCOUNT)]]
        await _send_or_edit(update, context, error_text, InlineKeyboardMarkup(keyboard), edit=bool(query), parse_mode=ParseMode.HTML)
        if loading_message and not query:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=loading_message.message_id)
            except Exception:
                pass

    except Exception as e:
        logger.error(f"خطأ عام عند عرض الرصيد: {e}", exc_info=True)
        error_text = "⚠️ حدث خطأ غير متوقع أثناء عرض الرصيد."
        keyboard = [[InlineKeyboardButton("🔙 رجوع لقائمة الحساب", callback_data=CALLBACK_GOTO_ACCOUNT)]]
        await _send_or_edit(update, context, error_text, InlineKeyboardMarkup(keyboard), edit=bool(query))
        if loading_message and not query:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=loading_message.message_id)
            except Exception:
                pass


async def show_orders_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays open orders information and quick sell options."""
    query = update.callback_query
    if query: await query.answer()
    chat_id = update.effective_chat.id
    if not binance_client:
        await _send_or_edit(update, context, "⚠️ عذرًا، اتصال Binance غير متاح حالياً.", edit=bool(query))
        return

    loading_message = None
    if query:
        try: await context.bot.send_chat_action(chat_id=chat_id, action='typing')
        except Exception as e: logger.debug(f"Failed to send typing action: {e}")
    else:
        loading_message = await context.bot.send_message(chat_id=chat_id, text="⏳ جاري جلب المعلومات...")

    try:
        # Get current balances and prices
        balances = await get_account_balances(context)
        tickers = await get_cached_tickers(context, quote_asset='USDT')
        
        # Filter sellable assets
        sellable_assets = []
        for balance in balances:
            if balance['asset'] not in ['USDT', 'BUSD', 'USDC', 'DAI', 'TUSD'] and balance['free'] > 0:
                pair = f"{balance['asset']}USDT"
                if pair in tickers:
                    current_price = tickers[pair]
                    sellable_assets.append({
                        'asset': balance['asset'],
                        'free': balance['free'],
                        'locked': balance['locked'],
                        'pair': pair,
                        'current_price': current_price,
                        'value_usdt': balance['free'] * current_price
                    })

        # Get open orders
        open_orders = binance_client.get_open_orders()
        
        # Format message
        final_text = ""
        keyboard = []
        
        # Add open orders section
        if open_orders:
            sell_orders = [order for order in open_orders if order['side'] == 'SELL']
            if sell_orders:
                keyboard.append([InlineKeyboardButton("❌ إلغاء جميع أوامر البيع", callback_data=CALLBACK_CANCEL_ALL_SELL_ORDERS)])
            
            final_text += "<b>📋 الأوامر المفتوحة:</b>\n\n"
            for order in open_orders:
                symbol = order['symbol']
                filters = get_symbol_filters(symbol, context)
                orig_qty = decimal_context.create_decimal(order['origQty'])
                exec_qty = decimal_context.create_decimal(order['executedQty'])
                price = decimal_context.create_decimal(order.get('price','0'))
                stop_price = decimal_context.create_decimal(order.get('stopPrice','0'))

                order_time = datetime.fromtimestamp(order['time'] / 1000).strftime('%H:%M:%S')
                
                # Calculate order value
                order_value = orig_qty * price if price > 0 else orig_qty * stop_price
                value_text = f" (${format_number(order_value)})" if order_value > 0 else ""
                
                final_text += (f"🔸 <b>{symbol}</b> | {order['side']} | {order['type']}\n"
                             f"  الكمية: {format_number(orig_qty)}{value_text}\n"
                             f"  السعر: {format_number(price) if price>0 else 'Market'}\n")
                if stop_price > 0:
                    final_text += f"  إيقاف: {format_number(stop_price)}\n"
                if exec_qty > 0:
                    final_text += f"  المنفذ: {format_number(exec_qty)}\n"
                final_text += f"  الوقت: {order_time}\n"
                final_text += "  ──────────\n"
            final_text += "\n"
        else:
            final_text += "لا توجد أوامر مفتوحة.\n\n"

        # Add available assets section
        if sellable_assets:
            final_text += "<b>💰 العملات المتوفرة:</b>\n\n"
            
            # Sort by USDT value
            sellable_assets.sort(key=lambda x: x['value_usdt'], reverse=True)
            
            for asset in sellable_assets[:8]:  # Show top 8 by value
                pair = asset['pair']
                free_qty = asset['free']
                locked_qty = asset['locked']
                current_price = asset['current_price']
                value_usdt = asset['value_usdt']
                
                # Add to text display with improved formatting
                final_text += f"🔹 <b>{pair}</b>\n"
                final_text += f"  الكمية: {format_number(free_qty)}"
                if locked_qty > 0:
                    final_text += f" (محجوز: {format_number(locked_qty)})"
                final_text += f"\n  السعر: ${format_number(current_price)}\n"
                final_text += f"  القيمة: ${format_number(value_usdt)}\n"
                
                # Add quick sell button with asset name
                keyboard.append([
                    InlineKeyboardButton(f"🔄 بيع سريع {pair}", callback_data=f"{CALLBACK_QUICK_SELL_PAIR}{pair}")
                ])
                final_text += "  ──────────\n"
        else:
            final_text += "لا توجد عملات متوفرة للبيع."

        # Add back button
        keyboard.append([InlineKeyboardButton("🔙 رجوع لقائمة التداول", callback_data=CALLBACK_GOTO_TRADING)])

        # Create reply markup
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Send or edit message
        if len(final_text) > 4000:
            final_text = final_text[:3900] + "\n...(المزيد)"
            
        await _send_or_edit(update, context, final_text, reply_markup, edit=bool(query), parse_mode=ParseMode.HTML)
        if loading_message and not query:
            try: await loading_message.delete()
            except Exception: pass

    except (BinanceAPIException, BinanceRequestException) as e:
        logger.error(f"Binance API Error: {e}")
        error_text = f"⚠️ حدث خطأ من Binance:\n<code>{e.message}</code>"
        keyboard = [[InlineKeyboardButton("🔙 رجوع لقائمة التداول", callback_data=CALLBACK_GOTO_TRADING)]]
        await _send_or_edit(update, context, error_text, InlineKeyboardMarkup(keyboard), edit=bool(query), parse_mode=ParseMode.HTML)
        if loading_message and not query:
            try: await loading_message.delete()
            except Exception: pass
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        error_text = "⚠️ حدث خطأ غير متوقع."
        keyboard = [[InlineKeyboardButton("🔙 رجوع لقائمة التداول", callback_data=CALLBACK_GOTO_TRADING)]]
        await _send_or_edit(update, context, error_text, InlineKeyboardMarkup(keyboard), edit=bool(query))
        if loading_message and not query:
            try: await loading_message.delete()
            except Exception: pass

async def handle_quick_sell_pair(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles quick sell pair selection and shows OCO options."""
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    
    pair = query.data.split(CALLBACK_QUICK_SELL_PAIR, 1)[1]
    context.user_data['quick_sell_pair'] = pair
    
    try:
        # Get current price
        current_price = await get_current_price(pair, context)
        if not current_price:
            await query.message.reply_text(f"⚠️ لم أتمكن من جلب السعر الحالي لـ {pair}")
            return ConversationHandler.END
            
        context.user_data['quick_sell_price'] = current_price
        
        # Get available balance
        base_asset = pair.replace('USDT', '')
        balances = await get_account_balances(context)
        asset_balance = next((b for b in balances if b['asset'] == base_asset), None)
        
        if not asset_balance or asset_balance['free'] <= 0:
            await query.message.reply_text(f"⚠️ لا يوجد رصيد متاح من {base_asset}")
            return ConversationHandler.END
            
        free_qty = asset_balance['free']
        context.user_data['quick_sell_qty'] = free_qty
        
        # Show SL percentage options
        text = (
            f"🔄 إعداد أمر بيع OCO لـ {pair}\n\n"
            f"الكمية المتاحة: {format_number(free_qty)} {base_asset}\n"
            f"السعر الحالي: ${format_number(current_price)}\n\n"
            f"اختر نسبة Stop Loss (SL):"
        )
        
        keyboard = []
        sl_percentages = [1, 2, 3, 5]
        row = []
        for perc in sl_percentages:
            row.append(InlineKeyboardButton(
                f"{perc}%",
                callback_data=f"{CALLBACK_QS_SL_PERC_PREFIX}{perc}"
            ))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
            
        keyboard.append([InlineKeyboardButton("❌ إلغاء", callback_data=CALLBACK_CANCEL_TRADE)])
        
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return T_ASK_SL_PERCENT
        
    except Exception as e:
        logger.error(f"Error in quick sell setup: {e}")
        await query.message.reply_text("⚠️ حدث خطأ في إعداد أمر البيع السريع.")
        return ConversationHandler.END

async def handle_quick_sell_sl_percent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles SL percentage selection for quick sell OCO order."""
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    
    try:
        percentage = int(query.data.split(CALLBACK_QS_SL_PERC_PREFIX, 1)[1])
        pair = context.user_data.get('quick_sell_pair')
        current_price = context.user_data.get('quick_sell_price')
        
        if not all([pair, current_price]):
            await query.message.reply_text("⚠️ بيانات غير مكتملة")
            return ConversationHandler.END
            
        # Calculate SL price
        sl_price = current_price * (1 - Decimal(percentage) / 100)
        context.user_data['quick_sell_sl'] = sl_price
        
        # Show TP percentage options
        text = (
            f"تم تحديد SL عند ${format_number(sl_price)} (-{percentage}%)\n\n"
            f"اختر نسبة Take Profit (TP):"
        )
        
        keyboard = []
        tp_percentages = [2, 3, 5, 8]
        row = []
        for perc in tp_percentages:
            row.append(InlineKeyboardButton(
                f"{perc}%",
                callback_data=f"{CALLBACK_QS_TP_PERC_PREFIX}{perc}"
            ))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
            
        keyboard.append([InlineKeyboardButton("❌ إلغاء", callback_data=CALLBACK_CANCEL_TRADE)])
        
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return T_ASK_TP_PERCENT
        
    except Exception as e:
        logger.error(f"Error setting quick sell SL: {e}")
        await query.message.reply_text("⚠️ حدث خطأ في تحديد SL")
        return ConversationHandler.END

async def handle_quick_sell_tp_percent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles TP percentage selection and places the OCO order."""
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    
    try:
        percentage = int(query.data.split(CALLBACK_QS_TP_PERC_PREFIX, 1)[1])
        pair = context.user_data.get('quick_sell_pair')
        current_price = context.user_data.get('quick_sell_price')
        sl_price = context.user_data.get('quick_sell_sl')
        quantity = context.user_data.get('quick_sell_qty')
        
        if not all([pair, current_price, sl_price, quantity]):
            await query.message.reply_text("⚠️ بيانات غير مكتملة")
            return ConversationHandler.END
            
        # Calculate TP price
        tp_price = current_price * (1 + Decimal(percentage) / 100)
        
        # Get symbol filters
        symbol_filters = get_symbol_filters(pair, context)
        
        # Adjust prices and quantity according to filters
        adjusted_quantity = adjust_quantity(quantity, symbol_filters)
        adjusted_sl_price = adjust_price(sl_price, symbol_filters)
        adjusted_tp_price = adjust_price(tp_price, symbol_filters)
        
        # Format values for display
        formatted_qty = format_decimal(adjusted_quantity, symbol_filters, 'LOT_SIZE')
        formatted_sl = format_decimal(adjusted_sl_price, symbol_filters, 'PRICE_FILTER')
        formatted_tp = format_decimal(adjusted_tp_price, symbol_filters, 'PRICE_FILTER')
        
        # Place OCO order
        try:
            order = binance_client.create_oco_order(
                symbol=pair,
                side=SIDE_SELL,
                quantity=formatted_qty,
                price=formatted_tp,
                stopPrice=formatted_sl,
                stopLimitPrice=formatted_sl,
                stopLimitTimeInForce=TIME_IN_FORCE_GTC
            )
            
            success_text = (
                f"✅ تم وضع أمر OCO بنجاح!\n\n"
                f"الزوج: {pair}\n"
                f"الكمية: {formatted_qty}\n"
                f"Stop Loss: ${formatted_sl}\n"
                f"Take Profit: ${formatted_tp}"
            )
            
            keyboard = [[InlineKeyboardButton("🔙 رجوع لقائمة التداول", callback_data=CALLBACK_GOTO_TRADING)]]
            await query.message.edit_text(success_text, reply_markup=InlineKeyboardMarkup(keyboard))
            
        except BinanceAPIException as e:
            error_text = f"⚠️ خطأ من Binance: {e.message}"
            await query.message.reply_text(error_text)
            
    except Exception as e:
        logger.error(f"Error placing quick sell OCO order: {e}")
        await query.message.reply_text("⚠️ حدث خطأ في وضع أمر البيع")
        
    return ConversationHandler.END

# Define common trading pairs at module level
COMMON_TRADING_PAIRS = {'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT', 'ADAUSDT'}

async def show_total_pnl(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Calculates and displays total PnL across all trading pairs."""
    query = update.callback_query
    if query: await query.answer()
    chat_id = update.effective_chat.id

    if not binance_client:
        await _send_or_edit(update, context, "⚠️ عذرًا، اتصال Binance غير متاح حالياً.", edit=bool(query))
        return

    # Create initial loading message
    loading_message = await context.bot.send_message(
        chat_id=chat_id,
        text="⏳ جاري تحضير البيانات..."
    )

    try:
        # Get cached tickers for price calculations
        await loading_message.edit_text("🔄 جاري تحديث أسعار العملات...")
        tickers = await get_cached_tickers(context, quote_asset='USDT', force_refresh=True)
        
        # Initialize traded symbols with common pairs
        traded_symbols = set()
        
        # Try to identify traded pairs
        try:
            await loading_message.edit_text("🔍 جاري البحث عن الأزواج المتداولة...")
            
            # First check common pairs
            common_pairs = {'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT', 'ADAUSDT'}
            for pair in common_pairs:
                try:
                    trades = binance_client.get_my_trades(symbol=pair, limit=1)
                    if trades:
                        traded_symbols.add(pair)
                except:
                    continue

            # Then check other USDT pairs from exchange info
            exchange_info = context.bot_data.get(EXCHANGE_INFO_CACHE_KEY)
            if exchange_info and 'symbols' in exchange_info:
                usdt_pairs = [
                    s['symbol'] for s in exchange_info['symbols']
                    if s['status'] == 'TRADING' and s['symbol'].endswith('USDT')
                ]
                
                # Process in batches to avoid rate limits
                batch_size = 5
                for i in range(0, len(usdt_pairs), batch_size):
                    batch = usdt_pairs[i:i + batch_size]
                    for pair in batch:
                        if pair not in traded_symbols:
                            try:
                                trades = binance_client.get_my_trades(symbol=pair, limit=1)
                                if trades:
                                    traded_symbols.add(pair)
                            except:
                                continue
                    await asyncio.sleep(0.5)  # Rate limit protection
                    
                    # Update progress
                    progress = (i + batch_size) / len(usdt_pairs) * 100
                    await loading_message.edit_text(
                        f"🔍 جاري البحث عن الأزواج المتداولة...\n"
                        f"تم فحص {min(i + batch_size, len(usdt_pairs))} من {len(usdt_pairs)} زوج\n"
                        f"تم العثور على {len(traded_symbols)} زوج متداول"
                    )
            
        except Exception as e:
            logger.error(f"Error identifying traded pairs: {e}")
            if not traded_symbols:
                traded_symbols = common_pairs

        if not traded_symbols:
            await loading_message.delete()
            await _send_or_edit(update, context, "لم يتم العثور على أي أزواج متداولة.", edit=bool(query))
            return

        await loading_message.edit_text(f"✅ تم تحديد {len(traded_symbols)} زوج متداول، جاري التحليل...")

        # Initialize result containers
        total_pnl = Decimal('0')
        total_buy_value = Decimal('0')
        total_sell_value = Decimal('0')
        total_commission_usdt = Decimal('0')
        total_trades_count = 0
        pnl_by_symbol = {}
        error_pairs = []

        # Process each symbol
        total_symbols = len(traded_symbols)
        processed_symbols = 0
        
        for symbol in sorted(traded_symbols):  # Sort for consistent display
            try:
                processed_symbols += 1
                
                # Update progress message
                progress_text = (
                    f"⏳ جاري تحليل البيانات التاريخية...\n"
                    f"تم معالجة {processed_symbols} من {total_symbols} زوج\n"
                    f"نسبة التقدم: {(processed_symbols / total_symbols * 100):.1f}%\n"
                    f"الزوج الحالي: {symbol}\n"
                    f"عدد الصفقات المحللة: {total_trades_count}"
                )
                
                try:
                    await loading_message.edit_text(progress_text)
                except:
                    pass

                # Fetch complete trade history for symbol
                symbol_trades = []
                last_id = None
                retry_count = 0
                max_retries = 3
                
                while True:
                    try:
                        params = {'symbol': symbol, 'limit': 1000}
                        if last_id:
                            params['fromId'] = last_id
                            
                        batch = binance_client.get_my_trades(**params)
                        if not batch:
                            break
                            
                        symbol_trades.extend(batch)
                        
                        if len(batch) < 1000:
                            break
                            
                        last_id = max(int(trade['id']) for trade in batch) + 1
                        await asyncio.sleep(0.1)  # Rate limit protection
                        
                    except Exception as e:
                        retry_count += 1
                        if retry_count >= max_retries:
                            logger.error(f"Failed to fetch trades for {symbol} after {max_retries} attempts: {e}")
                            error_pairs.append(symbol)
                            break
                        await asyncio.sleep(1)  # Wait before retry
                        continue

                if not symbol_trades:
                    continue

                # Calculate symbol statistics
                symbol_buy_value = Decimal('0')
                symbol_sell_value = Decimal('0')
                symbol_commission_usdt = Decimal('0')

                for trade in symbol_trades:
                    quote_qty = decimal_context.create_decimal(trade['quoteQty'])
                    commission = decimal_context.create_decimal(trade.get('commission', '0'))
                    commission_asset = trade.get('commissionAsset', '')

                    if trade.get('isBuyer'):
                        symbol_buy_value += quote_qty
                    else:
                        symbol_sell_value += quote_qty

                    # Convert commission to USDT
                    if commission > 0:
                        commission_usdt_value = Decimal('0')
                        if commission_asset == 'USDT':
                            commission_usdt_value = commission
                        else:
                            commission_pair = f"{commission_asset}USDT"
                            if commission_pair in tickers:
                                commission_usdt_value = commission * tickers[commission_pair]
                            elif commission_asset == 'BNB' and 'BNBUSDT' in tickers:
                                commission_usdt_value = commission * tickers['BNBUSDT']
                            elif commission_asset == 'BTC' and 'BTCUSDT' in tickers:
                                commission_usdt_value = commission * tickers['BTCUSDT']
                        symbol_commission_usdt += commission_usdt_value

                # Calculate symbol PnL
                symbol_pnl = symbol_sell_value - symbol_buy_value
                
                # Update totals
                total_buy_value += symbol_buy_value
                total_sell_value += symbol_sell_value
                total_commission_usdt += symbol_commission_usdt
                total_trades_count += len(symbol_trades)
                total_pnl += symbol_pnl

                # Store symbol results
                pnl_by_symbol[symbol] = {
                    'pnl': symbol_pnl,
                    'trades': len(symbol_trades),
                    'buy_value': symbol_buy_value,
                    'sell_value': symbol_sell_value,
                    'commission_usdt': symbol_commission_usdt
                }

            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}")
                error_pairs.append(symbol)
                continue

        # Delete loading message
        try:
            await loading_message.delete()
        except:
            pass

        if not pnl_by_symbol:
            await _send_or_edit(update, context, "لم يتم العثور على أي صفقات سابقة.", edit=bool(query))
            return

        # Calculate final statistics
        pnl_percentage = (total_pnl / total_buy_value * 100) if total_buy_value > 0 else Decimal('0')

        # Format response message
        text = "<b>📊 ملخص الأرباح والخسائر الكلي (كامل السجل)</b>\n\n"
        text += f"💵 <b>الإجمالي:</b>\n"
        text += f"عدد الأزواج المحللة: {len(pnl_by_symbol)} من {total_symbols}\n"
        text += f"عدد الصفقات الكلي: {total_trades_count}\n"
        text += f"إجمالي المشتريات: ${format_number(total_buy_value)}\n"
        text += f"إجمالي المبيعات: ${format_number(total_sell_value)}\n"
        text += f"صافي الربح/الخسارة: ${format_number(total_pnl)} ({format_number(pnl_percentage)}%)\n"
        text += f"إجمالي العمولات: ${format_number(total_commission_usdt)}"
        
        if error_pairs:
            text += f"\n\n⚠️ تعذر تحليل {len(error_pairs)} زوج"

        keyboard = [[InlineKeyboardButton("🔙 رجوع لقائمة الحساب", callback_data=CALLBACK_GOTO_ACCOUNT)]]
        await _send_or_edit(update, context, text, InlineKeyboardMarkup(keyboard), edit=bool(query), parse_mode=ParseMode.HTML)

    except Exception as e:
        logger.error(f"Error calculating total PnL: {e}", exc_info=True)
        error_text = "⚠️ حدث خطأ أثناء حساب الأرباح والخسائر."
        keyboard = [[InlineKeyboardButton("🔙 رجوع لقائمة الحساب", callback_data=CALLBACK_GOTO_ACCOUNT)]]
        await _send_or_edit(update, context, error_text, InlineKeyboardMarkup(keyboard), edit=bool(query))
        if loading_message:
            try:
                await loading_message.delete()
            except:
                pass


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
    elif callback_data == CALLBACK_GOTO_ALERTS: await show_alerts_menu(update, context) # <<<--- Add this line
    elif callback_data == CALLBACK_SHOW_HELP: await show_help_text(update, context)
    elif callback_data == CALLBACK_SHOW_BALANCE: await show_balance_info(update, context)
    elif callback_data == CALLBACK_SHOW_ORDERS: await show_orders_info(update, context)
    elif callback_data == CALLBACK_SHOW_PNL: await show_total_pnl(update, context)
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
    """Displays top gainers with quick buy buttons."""
    query = update.callback_query
    if query: await query.answer()
    await _send_or_edit(update, context, "⏳ جاري جلب الأكثر ارتفاعًا...", edit=bool(query))
    movers = await fetch_and_get_market_movers(context, quote_asset='USDT', sort_key='priceChangePercent')
    # Filter only positive changes for gainers
    gainers = [m for m in movers if m.get('priceChangePercent', Decimal(0)) > 0]
    
    if not gainers:
        text = "لم يتم العثور على عملات مرتفعة حالياً."
        keyboard = [[InlineKeyboardButton("🔙 رجوع لقائمة البحث", callback_data=CALLBACK_GOTO_SEARCH)]]
        await _send_or_edit(update, context, text, InlineKeyboardMarkup(keyboard), edit=True)
        return

    text = "📊 <b>الأكثر ارتفاعاً (آخر 24 ساعة):</b>\n\n"
    keyboard = []
    
    for i, mover in enumerate(gainers[:10]):  # Show top 10 only
        try:
            symbol = mover.get('symbol', 'N/A')
            change_percent = mover.get('priceChangePercent', Decimal(0))
            last_price = mover.get('lastPrice', Decimal(0)).normalize()
            
            # Add to text display
            text += f"{i + 1}. ⬆️ <b>{symbol}</b>: {change_percent:+.2f}% (السعر: {last_price:f})\n"
            
            # Add quick buy button for each pair
            keyboard.append([
                InlineKeyboardButton(f"📈 شراء {symbol}", callback_data=f"{CALLBACK_BUY_FAVORITE_PREFIX}{symbol}")
            ])
        except Exception as e:
            logger.error(f"Error formatting gainer {mover.get('symbol')}: {e}")

    # Add navigation buttons
    keyboard.append([InlineKeyboardButton("🔙 رجوع لقائمة البحث", callback_data=CALLBACK_GOTO_SEARCH)])
    
    await _send_or_edit(update, context, text, InlineKeyboardMarkup(keyboard), edit=True, parse_mode=ParseMode.HTML)

async def show_losers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays top losers with quick buy buttons."""
    query = update.callback_query
    if query: await query.answer()
    await _send_or_edit(update, context, "⏳ جاري جلب الأكثر انخفاضًا...", edit=bool(query))
    movers = await fetch_and_get_market_movers(context, quote_asset='USDT', sort_key='priceChangePercent')
    # Filter only negative changes and sort ascending (most negative first)
    losers = sorted(
        [m for m in movers if m.get('priceChangePercent', Decimal(0)) < 0],
        key=lambda x: x.get('priceChangePercent', Decimal(0))  # Sort ascending
    )

    if not losers:
        text = "لم يتم العثور على عملات منخفضة حالياً."
        keyboard = [[InlineKeyboardButton("🔙 رجوع لقائمة البحث", callback_data=CALLBACK_GOTO_SEARCH)]]
        await _send_or_edit(update, context, text, InlineKeyboardMarkup(keyboard), edit=True)
        return

    text = "📊 <b>الأكثر انخفاضاً (آخر 24 ساعة):</b>\n\n"
    keyboard = []
    
    for i, mover in enumerate(losers[:10]):  # Show top 10 only
        try:
            symbol = mover.get('symbol', 'N/A')
            change_percent = mover.get('priceChangePercent', Decimal(0))
            last_price = mover.get('lastPrice', Decimal(0)).normalize()
            
            # Add to text display
            text += f"{i + 1}. ⬇️ <b>{symbol}</b>: {change_percent:+.2f}% (السعر: {last_price:f})\n"
            
            # Add quick buy button for each pair
            keyboard.append([
                InlineKeyboardButton(f"📈 شراء {symbol}", callback_data=f"{CALLBACK_BUY_FAVORITE_PREFIX}{symbol}")
            ])
        except Exception as e:
            logger.error(f"Error formatting loser {mover.get('symbol')}: {e}")

    # Add navigation buttons
    keyboard.append([InlineKeyboardButton("🔙 رجوع لقائمة البحث", callback_data=CALLBACK_GOTO_SEARCH)])
    
    await _send_or_edit(update, context, text, InlineKeyboardMarkup(keyboard), edit=True, parse_mode=ParseMode.HTML)


# --- وظائف سجل التداول ---
async def fetch_all_trades(symbol: str, context: ContextTypes.DEFAULT_TYPE) -> List[Dict]:
    """
    Fetches all historical trades for a symbol using pagination.
    Returns a list of all trades.
    """
    if not binance_client:
        return []
    
    all_trades = []
    last_id = None
    batch_size = 1000  # Maximum allowed by Binance API
    
    try:
        while True:
            # Fetch batch of trades
            params = {
                'symbol': symbol,
                'limit': batch_size
            }
            if last_id:
                params['fromId'] = last_id
            
            batch = binance_client.get_my_trades(**params)
            if not batch:
                break
                
            all_trades.extend(batch)
            
            # Update last_id for next iteration
            last_id = max(int(trade['id']) for trade in batch) + 1
            
            # If we got less than batch_size trades, we've reached the end
            if len(batch) < batch_size:
                break
            
            # Add small delay to avoid rate limits
            await asyncio.sleep(0.1)
        
        logger.info(f"Fetched total of {len(all_trades)} trades for {symbol}")
        return all_trades
        
    except Exception as e:
        logger.error(f"Error fetching all trades for {symbol}: {e}")
        return all_trades  # Return what we have so far

async def show_today_trades(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays trades from the last 24 hours."""
    query = update.callback_query
    if query: await query.answer()
    chat_id = update.effective_chat.id
    if not binance_client:
        await _send_or_edit(update, context, "⚠️ عذرًا، اتصال Binance غير متاح حالياً.", edit=bool(query))
        return

    try:
        # Send initial loading message
        if query:
            loading_message = await query.message.edit_text("⏳ جاري جلب إحصائيات اليوم...")
        else:
            loading_message = await context.bot.send_message(chat_id=chat_id, text="⏳ جاري جلب إحصائيات اليوم...")

        # Get start time for 24 hours ago
        start_time_dt = datetime.now() - timedelta(days=1)
        start_time_ms = int(start_time_dt.timestamp() * 1000)
        
        # Get all valid USDT pairs
        exchange_info = context.bot_data.get(EXCHANGE_INFO_CACHE_KEY)
        valid_pairs = set()
        if exchange_info and 'symbols' in exchange_info:
            valid_pairs = {s['symbol'] for s in exchange_info['symbols'] if s['status'] == 'TRADING' and s['symbol'].endswith('USDT')}
        
        # Initialize variables for progress tracking
        total_pairs = len(valid_pairs)
        processed_pairs = 0
        all_trades = []
        
        # Try common pairs first
        common_pairs = {'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT', 'ADAUSDT'}
        for pair in common_pairs:
            if pair in valid_pairs:
                try:
                    trades = binance_client.get_my_trades(symbol=pair, startTime=start_time_ms)
                    if trades:
                        all_trades.extend(trades)
                        valid_pairs.remove(pair)  # Remove from main set to avoid processing again
                except Exception as e:
                    logger.debug(f"No trades found for common pair {pair}: {e}")
                processed_pairs += 1
                # Update progress every few pairs
                try:
                    await loading_message.edit_text(
                        f"⏳ جاري جلب الصفقات...\n"
                        f"تم معالجة {processed_pairs} من {total_pairs} زوج\n"
                        f"تم العثور على {len(all_trades)} صفقة"
                    )
                except Exception:
                    pass  # Ignore edit errors
        
        # Process remaining pairs in batches
        batch_size = 5
        for i in range(0, len(valid_pairs), batch_size):
            batch = list(valid_pairs)[i:i + batch_size]
            for pair in batch:
                try:
                    trades = binance_client.get_my_trades(symbol=pair, startTime=start_time_ms)
                    if trades:
                        all_trades.extend(trades)
                except Exception as e:
                    logger.debug(f"No trades found for {pair}: {e}")
                processed_pairs += 1
                # Update progress every batch
                try:
                    await loading_message.edit_text(
                        f"⏳ جاري جلب الصفقات...\n"
                        f"تم معالجة {processed_pairs} من {total_pairs} زوج\n"
                        f"تم العثور على {len(all_trades)} صفقة"
                    )
                except Exception:
                    pass  # Ignore edit errors
            await asyncio.sleep(0.5)  # Rate limit protection
        
        if not all_trades:
            text = "لم يتم العثور على صفقات في آخر 24 ساعة."
        else:
            # Sort trades by time
            all_trades.sort(key=lambda x: x['time'])
            
            # Group trades by symbol
            trades_by_symbol = {}
            for trade in all_trades:
                symbol = trade['symbol']
                if symbol not in trades_by_symbol:
                    trades_by_symbol[symbol] = []
                trades_by_symbol[symbol].append(trade)
            
            # Format statistics for each symbol
            text = "<b>📊 إحصائيات تداولات آخر 24 ساعة</b>\n\n"
            for symbol, symbol_trades in trades_by_symbol.items():
                symbol_stats = format_trade_history(symbol_trades, show_trades=False)
                # Remove the header from symbol_stats and add symbol name
                symbol_stats = symbol_stats.split('\n', 2)[2]  # Skip the first two lines
                text += f"<b>{symbol}</b>\n{symbol_stats}\n\n---\n\n"
        
        keyboard = [[InlineKeyboardButton("🔙 رجوع لقائمة السجل", callback_data=CALLBACK_GOTO_HISTORY)]]
        
        # Try to edit the loading message, if it fails send a new message
        try:
            await loading_message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
        except Exception:
            if query:
                await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
            else:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode=ParseMode.HTML
                )

    except Exception as e:
        logger.error(f"Error showing today's trades: {e}", exc_info=True)
        error_text = "⚠️ حدث خطأ غير متوقع أثناء جلب صفقات اليوم."
        await _send_or_edit(update, context, error_text, InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع لقائمة السجل", callback_data=CALLBACK_GOTO_HISTORY)]]), edit=True)

    finally:
        # Clean up loading message if it exists and we're not editing it
        if 'loading_message' in locals() and not query:
            try:
                await loading_message.delete()
            except Exception:
                pass

async def history_by_pair_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the conversation to get history for a specific pair."""
    query = update.callback_query
    if query: await query.answer()

    # Get favorite pairs
    favorites: Set[str] = context.user_data.get('favorite_pairs', set())
    
    # Get wallet assets
    wallet_pairs = set()
    try:
        balances = await get_account_balances(context)
        for balance in balances:
            if balance['asset'] not in ['USDT', 'BUSD', 'USDC', 'DAI', 'TUSD'] and balance['total'] > 0:
                pair = f"{balance['asset']}USDT"
                if is_valid_symbol(pair, context):
                    wallet_pairs.add(pair)
    except Exception as e:
        logger.error(f"Error getting wallet pairs: {e}")
    
    # Get recent trades pairs
    recent_pairs = set()
    if binance_client:
        try:
            # Get trades from last 24 hours
            start_time_dt = datetime.now() - timedelta(days=1)
            start_time_ms = int(start_time_dt.timestamp() * 1000)
            recent_trades = binance_client.get_my_trades(startTime=start_time_ms)
            recent_pairs = {trade['symbol'] for trade in recent_trades}
        except Exception as e:
            logger.error(f"Error getting recent trades: {e}")

    keyboard = []
    
    # Add wallet assets section if available
    if wallet_pairs:
        keyboard.append([InlineKeyboardButton("💼 العملات في المحفظة:", callback_data="header_wallet")])
        row = []
        for pair in sorted(wallet_pairs):
            row.append(InlineKeyboardButton(f"📊 {pair}", callback_data=f"{CALLBACK_HISTORY_BY_PAIR_START}{pair}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:  # Add any remaining buttons
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("─────────", callback_data="separator")])
    
    # Add favorite pairs buttons
    if favorites:
        keyboard.append([InlineKeyboardButton("⭐ العملات المفضلة:", callback_data="header_favorites")])
        row = []
        for pair in sorted(favorites - wallet_pairs):  # Exclude pairs already shown in wallet section
            row.append(InlineKeyboardButton(f"📊 {pair}", callback_data=f"{CALLBACK_HISTORY_BY_PAIR_START}{pair}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:  # Add any remaining buttons
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("─────────", callback_data="separator")])

    # Add recent pairs buttons
    if recent_pairs:
        keyboard.append([InlineKeyboardButton("🕒 العملات المتداولة مؤخراً:", callback_data="header_recent")])
        row = []
        for pair in sorted(recent_pairs - favorites - wallet_pairs):  # Exclude pairs already shown
            row.append(InlineKeyboardButton(f"📊 {pair}", callback_data=f"{CALLBACK_HISTORY_BY_PAIR_START}{pair}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:  # Add any remaining buttons
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("─────────", callback_data="separator")])

    # Add manual input button and back button
    keyboard.append([InlineKeyboardButton("⌨️ إدخال زوج آخر...", callback_data=CALLBACK_HISTORY_MANUAL_INPUT)])
    keyboard.append([InlineKeyboardButton("🔙 رجوع لقائمة السجل", callback_data=CALLBACK_GOTO_HISTORY)])

    text = "اختر الزوج لعرض سجل صفقاته:"
    await _send_or_edit(update, context, text, InlineKeyboardMarkup(keyboard), edit=bool(query))
    return H_ASK_PAIR

async def history_ask_pair_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles manual pair input for trade history."""
    if not update.message or not update.message.text:
        return H_ASK_PAIR
    
    pair = update.message.text.strip().upper()
    
    # Validate Symbol
    if not is_valid_symbol(pair, context):
        await update.message.reply_text(
            f"⚠️ الرمز '{pair}' غير صالح أو غير متداول حالياً. الرجاء إدخال رمز صحيح:",
            reply_markup=build_cancel_keyboard(CALLBACK_CANCEL)
        )
        return H_ASK_PAIR
    
    if not binance_client:
        await update.message.reply_text("⚠️ عذرًا، اتصال Binance غير متاح حالياً.")
        return ConversationHandler.END
    
    try:
        # Send typing action while fetching
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
        
        # Get current price for additional context
        current_price = await get_current_price(pair, context)
        current_price_text = f"\n💰 السعر الحالي: ${current_price:f}" if current_price else ""
        
        # Show loading message
        loading_msg = await update.message.reply_text("⏳ جاري جلب كامل السجل التاريخي للعملة...")
        
        # Get all historical trades
        trades = await fetch_all_trades(pair, context)
        
        # Format trades with statistics only
        trades_text = format_trade_history(trades, show_trades=False)
        
        # Add pair name, current price, and total trades count to the message
        trades_text = (
            f"<b>تحليل تداولات {pair}</b>{current_price_text}\n"
            f"إجمالي عدد الصفقات: {len(trades)}\n\n"
            + trades_text
        )
        
        # Delete loading message
        await loading_msg.delete()
        
        keyboard = [[InlineKeyboardButton("🔙 رجوع لقائمة السجل", callback_data=CALLBACK_GOTO_HISTORY)]]
        await update.message.reply_html(trades_text, reply_markup=InlineKeyboardMarkup(keyboard))
        
    except Exception as e:
        logger.error(f"Error showing history for {pair}: {e}")
        await update.message.reply_text(
            f"⚠️ حدث خطأ أثناء جلب سجل {pair}.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=CALLBACK_GOTO_HISTORY)]])
        )
    return ConversationHandler.END

async def handle_history_pair_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the selection of a pair from the buttons."""
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    
    if query.data == CALLBACK_HISTORY_MANUAL_INPUT:
        text = "الرجاء إدخال زوج العملات لعرض سجله (مثال: BTCUSDT):"
        await _send_or_edit(update, context, text, build_cancel_keyboard(CALLBACK_CANCEL), edit=True)
        return H_ASK_PAIR
        
    pair = query.data.split(CALLBACK_HISTORY_BY_PAIR_START, 1)[1]
    
    if not is_valid_symbol(pair, context):
        await _send_or_edit(update, context, 
            f"⚠️ الرمز '{pair}' غير صالح أو غير متداول حالياً.",
            InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=CALLBACK_GOTO_HISTORY)]]),
            edit=True
        )
        return ConversationHandler.END

    try:
        # Show loading message
        await _send_or_edit(update, context, "⏳ جاري جلب كامل السجل التاريخي للعملة...", edit=True)
        
        # Get current price for additional context
        current_price = await get_current_price(pair, context)
        current_price_text = f"\n💰 السعر الحالي: ${current_price:f}" if current_price else ""
        
        # Get all historical trades
        trades = await fetch_all_trades(pair, context)
        
        # Format trades with statistics only
        trades_text = format_trade_history(trades, show_trades=False)
        
        # Add pair name, current price, and total trades count to the message
        trades_text = (
            f"<b>تحليل تداولات {pair}</b>{current_price_text}\n"
            f"إجمالي عدد الصفقات: {len(trades)}\n\n"
            + trades_text
        )
        
        keyboard = [[InlineKeyboardButton("🔙 رجوع لقائمة السجل", callback_data=CALLBACK_GOTO_HISTORY)]]
        await _send_or_edit(update, context, trades_text, InlineKeyboardMarkup(keyboard), edit=True)
        
    except Exception as e:
        logger.error(f"Error showing history for {pair}: {e}")
        await _send_or_edit(update, context, 
            f"⚠️ حدث خطأ أثناء جلب سجل {pair}.",
            InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=CALLBACK_GOTO_HISTORY)]]),
            edit=True
        )
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
    # <<<--- استخدام القائمة الافتراضية عند الحاجة --- >>>
    favorites: Set[str] = context.user_data.setdefault('favorite_pairs', DEFAULT_FAVORITE_PAIRS.copy())
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

    # <<<--- استخدام القائمة الافتراضية عند الحاجة --- >>>
    favorites: Set[str] = context.user_data.setdefault('favorite_pairs', DEFAULT_FAVORITE_PAIRS.copy())
    if len(favorites) >= MAX_FAVORITES:
         await update.message.reply_text(f"⚠️ لقد وصلت للحد الأقصى لعدد المفضلة ({MAX_FAVORITES}). قم بإزالة زوج أولاً.", reply_markup=build_cancel_keyboard(CALLBACK_CANCEL))
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
    # <<<--- استخدام القائمة الافتراضية عند الحاجة --- >>>
    favorites: Set[str] = context.user_data.setdefault('favorite_pairs', DEFAULT_FAVORITE_PAIRS.copy())
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
    # <<<--- استخدام القائمة الافتراضية عند الحاجة --- >>>
    favorites: Set[str] = context.user_data.setdefault('favorite_pairs', DEFAULT_FAVORITE_PAIRS.copy())

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
    if not query: return ConversationHandler.END
    await query.answer()
    callback_data = query.data

    if callback_data == CALLBACK_START_BUY:
        context.user_data['trade_side'] = SIDE_BUY
        logger.info("Starting BUY conversation")
        favorites: Set[str] = context.user_data.get('favorite_pairs', set())

        # Get balance information for display
        balance_text = ""
        try:
            balances = await get_account_balances(context)
            usdt_balance = next((b for b in balances if b['asset'] == 'USDT'), None)
            if usdt_balance:
                free_usdt = usdt_balance['free']
                balance_text = f"\n💰 رصيدك المتاح: ${free_usdt:.2f} USDT"
        except Exception as e:
            logger.error(f"Error getting USDT balance: {e}")

        if favorites:
            text = f"عملية الشراء. اختر زوجًا من المفضلة أو أدخل زوجًا آخر:{balance_text}"
            keyboard = build_buy_favorites_keyboard(favorites)
            await _send_or_edit(update, context, text, keyboard, edit=True)
            return None
        else:
            text = f"عملية الشراء.\n\nالرجاء إدخال زوج العملات (مثال: BTCUSDT){balance_text}"
            keyboard = build_cancel_keyboard(CALLBACK_CANCEL_TRADE)
            await _send_or_edit(update, context, text, keyboard, edit=True)
            return T_ASK_PAIR

    elif callback_data == CALLBACK_START_SELL:
        context.user_data['trade_side'] = SIDE_SELL
        logger.info("Starting SELL conversation")
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
        
        try:
            balances = await get_account_balances(context)
            # Filter out stablecoins and assets with zero free balance
            sellable_balances = []
            for balance in balances:
                if balance['asset'] not in ['USDT', 'BUSD', 'USDC', 'DAI', 'TUSD'] and balance['free'] > 0:
                    # Get current price for value calculation
                    pair = f"{balance['asset']}USDT"
                    current_price = await get_current_price(pair, context)
                    if current_price:
                        balance['current_price'] = current_price
                        balance['total_value'] = balance['free'] * current_price
                        sellable_balances.append(balance)
                    else:
                        # Try with BUSD pair if USDT pair not found
                        pair_busd = f"{balance['asset']}BUSD"
                        current_price_busd = await get_current_price(pair_busd, context)
                        if current_price_busd:
                            balance['current_price'] = current_price_busd
                            balance['total_value'] = balance['free'] * current_price_busd
                            sellable_balances.append(balance)

            if not sellable_balances:
                text = "لا يوجد لديك أرصدة عملات (غير مستقرة) متاحة للبيع حالياً."
                keyboard = [[InlineKeyboardButton("🔙 رجوع لقائمة التداول", callback_data=CALLBACK_GOTO_TRADING)]]
                await _send_or_edit(update, context, text, InlineKeyboardMarkup(keyboard), edit=True)
                return ConversationHandler.END

            # Sort by value
            sellable_balances.sort(key=lambda x: x.get('total_value', 0), reverse=True)
            
            text = "عملية البيع. اختر الأصل الذي تريد بيعه:\n\n"
            text += "💰 أرصدتك المتاحة:\n"
            for balance in sellable_balances[:10]:  # Show top 10 by value
                asset = balance['asset']
                free_qty = balance['free']
                current_price = balance.get('current_price', 0)
                total_value = balance.get('total_value', 0)
                text += f"• {asset}: {free_qty:f}\n  السعر: ${current_price:f}\n  القيمة: ${total_value:.2f}\n"

            keyboard = build_sell_asset_keyboard(sellable_balances)
            await _send_or_edit(update, context, text, keyboard, edit=True)
            return T_CHOOSE_SELL_ASSET

        except Exception as e:
            logger.error(f"Error preparing sell menu: {e}")
            text = "⚠️ حدث خطأ أثناء جلب الأرصدة. الرجاء المحاولة مرة أخرى."
            keyboard = [[InlineKeyboardButton("🔙 رجوع لقائمة التداول", callback_data=CALLBACK_GOTO_TRADING)]]
            await _send_or_edit(update, context, text, InlineKeyboardMarkup(keyboard), edit=True)
            return ConversationHandler.END
    else:
        logger.warning(f"Unexpected callback_data to start trade: {callback_data}")
        return ConversationHandler.END


async def handle_buy_favorite_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles selection of a favorite pair to buy."""
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    callback_data = query.data
    
    if not callback_data.startswith(CALLBACK_BUY_FAVORITE_PREFIX):
        logger.warning(f"Unexpected callback_data in buy favorite: {callback_data}")
        return ConversationHandler.END
        
    pair = callback_data.split(CALLBACK_BUY_FAVORITE_PREFIX, 1)[1]

    # Validate Symbol
    if not is_valid_symbol(pair, context):
        await _send_or_edit(update, context, f"⚠️ الرمز '{pair}' غير صالح أو غير متداول حالياً.", InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=CALLBACK_GOTO_TRADING)]]), edit=True)
        return ConversationHandler.END

    context.user_data['trade_pair'] = pair
    context.user_data['trade_side'] = SIDE_BUY
    logger.info(f"Buying favorite pair selected: {pair}")

    # Get balance information
    balance_text = ""
    try:
        balances = await get_account_balances(context)
        usdt_balance = next((b for b in balances if b['asset'] == 'USDT'), None)
        if usdt_balance:
            free_usdt = usdt_balance['free']
            balance_text = f"\n💰 رصيدك المتاح: ${free_usdt:.2f} USDT"
    except Exception as e:
        logger.error(f"Error getting USDT balance: {e}")

    # Get current price
    price_text = ""
    try:
        current_price = await get_current_price(pair, context)
        if current_price:
            price_text = f"\n💱 السعر الحالي: ${current_price:f}"
    except Exception as e:
        logger.error(f"Error getting current price: {e}")

    text = f"الشراء لـ {pair}{balance_text}{price_text}\n\nالرجاء إدخال القيمة بالدولار (USDT):"
    await _send_or_edit(update, context, text, build_cancel_keyboard(CALLBACK_CANCEL_TRADE), edit=True, parse_mode=ParseMode.HTML)
    return T_ASK_AMOUNT

async def handle_buy_other_pair(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles pressing 'Enter other pair' button."""
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    
    # Get balance information
    balance_text = ""
    try:
        balances = await get_account_balances(context)
        usdt_balance = next((b for b in balances if b['asset'] == 'USDT'), None)
        if usdt_balance:
            free_usdt = usdt_balance['free']
            balance_text = f"\n💰 رصيدك المتاح: ${free_usdt:.2f} USDT"
    except Exception as e:
        logger.error(f"Error getting USDT balance: {e}")

    context.user_data['trade_side'] = SIDE_BUY
    text = f"عملية الشراء.\n\nالرجاء إدخال زوج العملات (مثال: BTCUSDT){balance_text}"
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
    if not query: return ConversationHandler.END
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
        # Get current price for USDT value calculation
        pair = f"{selected_asset}USDT"
        current_price = await get_current_price(pair, context)
        
        if not current_price:
            await _send_or_edit(update, context, f"⚠️ لم أتمكن من جلب السعر الحالي لـ {pair}.", build_cancel_keyboard(CALLBACK_CANCEL_TRADE), edit=True)
            return ConversationHandler.END
            
        available_value = available_qty * current_price
        
        text = (
            f"الأصل: {selected_asset}\n"
            f"المتاح: {available_qty:f} {selected_asset}\n"
            f"القيمة التقريبية: ${available_value:.2f}\n"
            f"السعر الحالي: ${current_price:f}\n\n"
            f"أدخل القيمة المطلوب بيعها بالدولار (USDT):"
        )
        
        context.user_data['sell_current_price'] = current_price
        await _send_or_edit(update, context, text, build_cancel_keyboard(CALLBACK_CANCEL_TRADE), edit=True)
        return T_ASK_SELL_AMOUNT
    else:
        logger.warning(f"Unexpected callback_data for sell amount choice: {choice}")
        return await cancel_trade_conversation(update, context)

async def handle_sell_amount_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the USDT amount input for partial sell."""
    if not update.message or not update.message.text:
        return T_ASK_SELL_AMOUNT

    usdt_amount_str = update.message.text.strip()
    selected_asset = context.user_data.get('sell_asset')
    available_qty = context.user_data.get('sell_available_qty')
    current_price = context.user_data.get('sell_current_price')
    pair = f"{selected_asset}USDT"

    if not all([selected_asset, available_qty, current_price]):
        await update.message.reply_text("⚠️ خطأ داخلي: بيانات غير مكتملة.", reply_markup=build_cancel_keyboard(CALLBACK_CANCEL_TRADE))
        return T_ASK_SELL_AMOUNT

    try:
        usdt_amount = decimal_context.create_decimal(usdt_amount_str)
        if usdt_amount <= 0:
            raise ValueError("القيمة يجب أن تكون أكبر من صفر.")

        # Calculate token quantity from USDT amount
        token_quantity = usdt_amount / current_price
        available_value = available_qty * current_price

        if usdt_amount > available_value:
            raise ValueError(f"القيمة المطلوبة (${usdt_amount:.2f}) تتجاوز القيمة المتاحة (${available_value:.2f})")

        # Get symbol filters and adjust quantity
        symbol_filters = get_symbol_filters(pair, context)
        adjusted_quantity = adjust_quantity(token_quantity, symbol_filters)
        
        if adjusted_quantity <= 0:
            raise ValueError("الكمية المحسوبة صغيرة جداً بعد التعديل.")

        # Store trade details
        context.user_data['trade_amount'] = adjusted_quantity
        context.user_data['trade_pair'] = pair

        # Format confirmation message
        adjusted_value = adjusted_quantity * current_price
        text = (
            f"تم تحديد:\n"
            f"القيمة: ${usdt_amount:.2f}\n"
            f"الكمية المعدلة: {format_decimal(adjusted_quantity, symbol_filters, 'LOT_SIZE')} {selected_asset}\n"
            f"القيمة التقريبية بعد التعديل: ${adjusted_value:.2f}\n\n"
            f"هل ترغب في إضافة SL/TP؟"
        )

        await update.message.reply_text(text, reply_markup=build_sltp_choice_keyboard())
        return T_ASK_SLTP_CHOICE

    except (InvalidOperation, ValueError) as e:
        await update.message.reply_text(
            f"⚠️ قيمة غير صالحة: {str(e)}\n"
            f"الرجاء إدخال القيمة بالدولار:",
            reply_markup=build_cancel_keyboard(CALLBACK_CANCEL_TRADE)
        )
        return T_ASK_SELL_AMOUNT
    except Exception as e:
        logger.error(f"Error handling sell amount input: {e}", exc_info=True)
        await update.message.reply_text(
            "⚠️ حدث خطأ غير متوقع. الرجاء المحاولة مرة أخرى.",
            reply_markup=build_cancel_keyboard(CALLBACK_CANCEL_TRADE)
        )
        return T_ASK_SELL_AMOUNT

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
    """Handles USDT amount input for BUY or PARTIAL SELL with validation."""
    if not update.message or not update.message.text:
        logger.warning("Update without message text in T_ASK_AMOUNT/T_ASK_SELL_AMOUNT")
        return T_ASK_AMOUNT

    amount_str = update.message.text.strip()
    current_trade_side = context.user_data.get('trade_side')
    pair = context.user_data.get('trade_pair')
    next_state = T_ASK_SLTP_CHOICE
    error_return_state = T_ASK_AMOUNT if current_trade_side == SIDE_BUY else T_ASK_SELL_AMOUNT

    if not pair:
        logger.error("Pair not found in context for amount handling.")
        await update.message.reply_text("⚠️ خطأ داخلي: لم يتم تحديد زوج العملات.", reply_markup=build_main_menu_keyboard())
        return ConversationHandler.END

    symbol_filters = get_symbol_filters(pair, context)
    if not symbol_filters:
        logger.error(f"Could not get filters for {pair} in amount handler.")
        await update.message.reply_text(f"⚠️ لم أتمكن من جلب قيود التداول لـ {pair}. لا يمكن المتابعة.", reply_markup=build_cancel_keyboard(CALLBACK_CANCEL_TRADE))
        return error_return_state

    try:
        # Get current price
        current_price = await get_current_price(pair, context)
        if not current_price:
            await update.message.reply_text("⚠️ لم أتمكن من جلب السعر الحالي. الرجاء المحاولة مرة أخرى.", reply_markup=build_cancel_keyboard(CALLBACK_CANCEL_TRADE))
            return error_return_state

        # Convert USDT amount to token quantity
        usdt_amount = decimal_context.create_decimal(amount_str)
        if usdt_amount <= 0:
            raise ValueError("القيمة يجب أن تكون أكبر من صفر.")

        # Check max buy limit for BUY orders
        if current_trade_side == SIDE_BUY:
            max_buy_setting = context.user_data.get('max_buy_usdt', DEFAULT_MAX_BUY_USDT)
            if usdt_amount > max_buy_setting:
                await update.message.reply_text(
                    f"⚠️ القيمة المدخلة (${usdt_amount:.2f}) تتجاوز حد الشراء المحدد (${max_buy_setting:.2f}).",
                    reply_markup=build_cancel_keyboard(CALLBACK_CANCEL_TRADE)
                )
                return error_return_state

        # Calculate token quantity from USDT amount
        token_quantity = usdt_amount / current_price

        # Validate against LOT_SIZE filter
        lot_filter = symbol_filters.get('LOT_SIZE')
        min_qty = decimal_context.create_decimal(lot_filter.get('minQty', '0')) if lot_filter else Decimal(0)
        max_qty = decimal_context.create_decimal(lot_filter.get('maxQty', 'inf')) if lot_filter else Decimal('inf')

        if token_quantity < min_qty:
            raise ValueError(f"القيمة صغيرة جداً. الحد الأدنى للكمية هو {min_qty:f} (≈ ${(min_qty * current_price):.2f})")
        if token_quantity > max_qty:
            raise ValueError(f"القيمة كبيرة جداً. الحد الأقصى للكمية هو {max_qty:f} (≈ ${(max_qty * current_price):.2f})")

        # Adjust quantity according to LOT_SIZE
        adjusted_quantity = adjust_quantity(token_quantity, symbol_filters)
        if adjusted_quantity <= 0:
            raise ValueError(f"القيمة صغيرة جداً بعد التعديل حسب قيود المنصة.")

        # For SELL orders, check available balance
        if current_trade_side == SIDE_SELL:
            available_qty = context.user_data.get('sell_available_qty')
            if available_qty is not None and adjusted_quantity > available_qty:
                raise ValueError(f"القيمة المطلوبة (${usdt_amount:.2f}) تتجاوز الرصيد المتاح ({available_qty:f} ≈ ${(available_qty * current_price):.2f})")

        # Store both USDT amount and token quantity
        context.user_data['trade_amount'] = adjusted_quantity
        context.user_data['trade_usdt_amount'] = usdt_amount
        
        # Format display message
        adjusted_usdt = adjusted_quantity * current_price
        text = (
            f"تم تحديد القيمة: ${usdt_amount:.2f}\n"
            f"الكمية بعد التعديل: {format_decimal(adjusted_quantity, symbol_filters, 'LOT_SIZE')} "
            f"(≈ ${adjusted_usdt:.2f})\n"
            f"السعر الحالي: {format_decimal(current_price, symbol_filters, 'PRICE_FILTER')}\n\n"
            f"هل ترغب في إضافة أمر إيقاف خسارة (SL) أو جني أرباح (TP)؟"
        )
        
        await update.message.reply_html(text, reply_markup=build_sltp_choice_keyboard())
        return next_state

    except (InvalidOperation, ValueError) as e:
        logger.warning(f"Invalid amount input: {amount_str} - {e}")
        await update.message.reply_text(
            f"⚠️ قيمة غير صالحة: {e}\n"
            f"الرجاء إدخال قيمة بالدولار (USDT):",
            reply_markup=build_cancel_keyboard(CALLBACK_CANCEL_TRADE)
        )
        return error_return_state
    except Exception as e:
        logger.error(f"Unexpected error handling amount: {e}", exc_info=True)
        await update.message.reply_text(
            "⚠️ حدث خطأ غير متوقع. الرجاء المحاولة مرة أخرى.",
            reply_markup=build_cancel_keyboard(CALLBACK_CANCEL_TRADE)
        )
        return error_return_state


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

    except ValueError as e:
         logger.error(f"Value Error ({trade_action_text}): {e}")
         error_msg = f"❌ **خطأ في البيانات:**\n\n<code>{e}</code>"
         await _send_or_edit(update, context, error_msg, final_keyboard, edit=True, parse_mode=ParseMode.HTML)

    except Exception as e:
        logger.error(f"Unexpected Error ({trade_action_text}): {e}", exc_info=True)
        error_msg = "❌ حدث خطأ غير متوقع أثناء تنفيذ الأمر."
        await _send_or_edit(update, context, error_msg, final_keyboard, edit=True)

    finally:
        # Always end the conversation and clear data after attempt
        return await cancel_trade_conversation(update, context, clear_only=True)

# --- وظائف إعدادات التنبيهات ---
async def toggle_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggles the alerts enabled status."""
    query = update.callback_query
    if query: await query.answer()
    context.user_data['alert_config']['enabled'] = not context.user_data['alert_config']['enabled']
    status = "مفعلة ✅" if context.user_data['alert_config']['enabled'] else "معطلة ❌"
    text = f"تم تغيير حالة التنبيهات إلى: {status}"
    keyboard = build_alerts_menu_keyboard(context)
    await _send_or_edit(update, context, text, keyboard, edit=True, parse_mode=ParseMode.HTML)

async def start_manual_threshold_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the manual threshold input process."""
    query = update.callback_query
    if query: await query.answer()
    
    current_threshold = context.user_data.get('alert_config', {}).get('threshold_percent', DEFAULT_ALERT_THRESHOLD)
    text = (
        f"النسبة الحالية: {current_threshold}%\n\n"
        "الرجاء إدخال نسبة التغير الجديدة (رقم موجب):"
    )
    await _send_or_edit(update, context, text, build_cancel_keyboard(CALLBACK_GOTO_ALERTS), edit=True)
    return ALERT_ASK_THRESHOLD

async def handle_manual_threshold_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles manual input for alert threshold."""
    if not update.message or not update.message.text:
        return ALERT_ASK_THRESHOLD
        
    try:
        input_value = update.message.text.strip().replace('%', '')
        percentage = decimal_context.create_decimal(input_value)
        
        if percentage <= 0:
            raise ValueError("النسبة يجب أن تكون أكبر من صفر.")
        if percentage > 100:
            raise ValueError("النسبة يجب أن تكون أقل من أو تساوي 100%.")
            
        config = context.user_data.setdefault('alert_config', {})
        config['threshold_percent'] = percentage
        
        await show_alerts_menu(update, context)
        return ConversationHandler.END
        
    except (InvalidOperation, ValueError) as e:
        await update.message.reply_text(
            f"⚠️ قيمة غير صالحة: {str(e)}\n"
            "الرجاء إدخال رقم موجب (مثال: 2.5):",
            reply_markup=build_cancel_keyboard(CALLBACK_GOTO_ALERTS)
        )
        return ALERT_ASK_THRESHOLD

async def set_alert_threshold_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Starts the process of setting alert threshold."""
    query = update.callback_query
    if query: await query.answer()
    
    current_threshold = context.user_data.get('alert_config', {}).get('threshold_percent', DEFAULT_ALERT_THRESHOLD)
    text = f"النسبة الحالية: {current_threshold}%\n\nاختر نسبة التغير الجديدة للتنبيهات:"
    keyboard = build_alert_threshold_keyboard([1, 2, 3, 5, 7, 10])
    await _send_or_edit(update, context, text, keyboard, edit=True)

async def handle_alert_threshold_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the selection of alert threshold percentage."""
    query = update.callback_query
    if not query: return
    await query.answer()
    
    try:
        percentage = int(query.data.split(CALLBACK_ALERT_PERC_PREFIX, 1)[1])
        config = context.user_data.setdefault('alert_config', {})
        config['threshold_percent'] = Decimal(percentage)
        
        await show_alerts_menu(update, context)
        
    except (ValueError, IndexError) as e:
        logger.error(f"Error processing alert threshold selection: {e}")
        await _send_or_edit(update, context, "⚠️ حدث خطأ في تحديد نسبة التغير.", build_alerts_menu_keyboard(context), edit=True)

# --- وظائف الشراء السريع ---
async def quick_buy_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the quick buy conversation."""
    query = update.callback_query
    if query: await query.answer()
    favorites: Set[str] = context.user_data.get('favorite_pairs', set())
    
    if favorites:
        text = "عملية الشراء السريع.\nاختر زوجًا من المفضلة أو أدخل زوجًا آخر:"
        keyboard = build_buy_favorites_keyboard(favorites)
        await _send_or_edit(update, context, text, keyboard, edit=True)
        return QB_ASK_PAIR
    else:
        text = "عملية الشراء السريع.\n\nالرجاء إدخال زوج العملات (مثال: BTCUSDT):"
        await _send_or_edit(update, context, text, build_cancel_keyboard(CALLBACK_CANCEL_TRADE), edit=True)
        return QB_ASK_PAIR

async def quick_buy_pair_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles pair input/selection for quick buy."""
    pair = None
    query = update.callback_query
    
    if query:
        await query.answer()
        if query.data.startswith(CALLBACK_BUY_FAVORITE_PREFIX):
            pair = query.data.split(CALLBACK_BUY_FAVORITE_PREFIX, 1)[1]
        elif query.data == CALLBACK_BUY_OTHER_PAIR:
            text = "الرجاء إدخال زوج العملات (مثال: BTCUSDT):"
            await _send_or_edit(update, context, text, build_cancel_keyboard(CALLBACK_CANCEL_TRADE), edit=True)
            return QB_ASK_PAIR
    elif update.message and update.message.text:
        pair = update.message.text.strip().upper()
    
    if not pair:
        return QB_ASK_PAIR
    
    # Validate pair
    if not is_valid_symbol(pair, context):
        error_text = f"⚠️ الرمز '{pair}' غير صالح أو غير متداول حاليًا. الرجاء إدخال رمز صحيح:"
        if query:
            await _send_or_edit(update, context, error_text, build_cancel_keyboard(CALLBACK_CANCEL_TRADE), edit=True)
        else:
            await update.message.reply_text(error_text, reply_markup=build_cancel_keyboard(CALLBACK_CANCEL_TRADE))
        return QB_ASK_PAIR

    context.user_data['qb_pair'] = pair
    context.user_data['trade_side'] = SIDE_BUY # Set trade side for market order

    # Get current price for display
    current_price = await get_current_price(pair, context)
    if current_price:
        context.user_data['qb_current_price'] = current_price
        
    # Get available balance
    quote_balance = await get_quote_asset_balance(pair, context)
    balance_text = ""
    if quote_balance is not None:
        quote_asset = ""
        exchange_info = context.bot_data.get(EXCHANGE_INFO_CACHE_KEY)
        if exchange_info:
            for symbol_data in exchange_info.get('symbols', []):
                if symbol_data['symbol'] == pair:
                    quote_asset = symbol_data.get('quoteAsset')
                    break
        if quote_asset:
            balance_text = f"\n<i>(رصيد {quote_asset} المتاح: {quote_balance.normalize():f})</i>"

    price_text = f"\nالسعر الحالي: {current_price:f}" if current_price else ""
    text = f"الزوج: {pair}{price_text}{balance_text}\n\nالرجاء إدخال الكمية للشراء:"
    
    if query:
        await _send_or_edit(update, context, text, build_cancel_keyboard(CALLBACK_CANCEL_TRADE), edit=True, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_html(text, reply_markup=build_cancel_keyboard(CALLBACK_CANCEL_TRADE))
    
    return QB_ASK_AMOUNT

async def quick_buy_amount_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles amount input for quick buy."""
    if not update.message or not update.message.text:
        return QB_ASK_AMOUNT

    amount_str = update.message.text.strip()
    pair = context.user_data.get('qb_pair')
    
    if not pair:
        await update.message.reply_text("⚠️ خطأ داخلي: لم يتم تحديد الزوج.", reply_markup=build_main_menu_keyboard())
        return ConversationHandler.END

    symbol_filters = get_symbol_filters(pair, context)
    if not symbol_filters:
        await update.message.reply_text(f"⚠️ لم أتمكن من جلب قيود التداول لـ {pair}.", reply_markup=build_cancel_keyboard(CALLBACK_CANCEL_TRADE))
        return QB_ASK_AMOUNT

    try:
        amount_input = decimal_context.create_decimal(amount_str)
        if amount_input <= 0:
            raise ValueError("الكمية يجب أن تكون أكبر من صفر.")

        # Validate against LOT_SIZE
        lot_filter = symbol_filters.get('LOT_SIZE')
        min_qty = decimal_context.create_decimal(lot_filter.get('minQty', '0')) if lot_filter else Decimal(0)
        max_qty = decimal_context.create_decimal(lot_filter.get('maxQty', 'inf')) if lot_filter else Decimal('inf')

        if amount_input < min_qty:
            raise ValueError(f"الكمية ({amount_input:f}) أقل من الحد الأدنى ({min_qty:f}).")
        if amount_input > max_qty:
            raise ValueError(f"الكمية ({amount_input:f}) أكبر من الحد الأقصى ({max_qty:f}).")

        # Adjust quantity
        amount = adjust_quantity(amount_input, symbol_filters)
        if amount <= 0:
            raise ValueError(f"الكمية ({amount_input:f}) صغيرة جدًا بعد التعديل.")

        context.user_data['qb_amount'] = amount
        context.user_data['trade_amount'] = amount # Set for market order

        # Check max buy limit
        max_buy_setting = context.user_data.get('max_buy_usdt', DEFAULT_MAX_BUY_USDT)
        current_price = context.user_data.get('qb_current_price')
        if current_price:
            estimated_cost = amount * current_price
            if estimated_cost > max_buy_setting:
                await update.message.reply_text(f"⚠️ تحذير: القيمة التقديرية للصفقة (${estimated_cost:.2f}) تتجاوز حد الشراء المحدد (${max_buy_setting:.2f}).")

        # Show SL percentage options
        text = f"تم تحديد الكمية: {format_decimal(amount, symbol_filters, 'LOT_SIZE')}\n\nاختر نسبة إيقاف الخسارة (SL):"
        keyboard = build_percent_keyboard(CALLBACK_QB_SL_PERC_PREFIX, [1, 2, 3, 5])
        await update.message.reply_text(text, reply_markup=keyboard)
        return QB_ASK_SL_PERCENT

    except (InvalidOperation, ValueError) as e:
        await update.message.reply_text(f"⚠️ قيمة غير صالحة: {e}\nالرجاء إدخال رقم صحيح:", reply_markup=build_cancel_keyboard(CALLBACK_CANCEL_TRADE))
        return QB_ASK_AMOUNT
    except Exception as e:
        logger.error(f"Unexpected error handling quick buy amount: {e}", exc_info=True)
        await update.message.reply_text("⚠️ حدث خطأ غير متوقع.", reply_markup=build_cancel_keyboard(CALLBACK_CANCEL_TRADE))
        return QB_ASK_AMOUNT

async def quick_buy_sl_percent_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles SL percentage selection for quick buy."""
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    
    pair = context.user_data.get('qb_pair')
    current_price = context.user_data.get('qb_current_price')
    
    if not all([pair, current_price]):
        logger.error("Missing data for quick buy SL calculation")
        return await cancel_trade_conversation(update, context)
        
    try:
        percentage = int(query.data.split(CALLBACK_QB_SL_PERC_PREFIX, 1)[1])
        percentage_decimal = Decimal(percentage) / 100
        sl_price_raw = current_price * (1 - percentage_decimal) # For buy orders
        
        symbol_filters = get_symbol_filters(pair, context)
        sl_price = adjust_price(sl_price_raw, symbol_filters)
        
        if sl_price <= 0:
            raise ValueError("سعر SL المحسوب غير صالح.")
            
        context.user_data['qb_sl_price'] = sl_price
        context.user_data['sl_price'] = sl_price # Set for market order
        
        formatted_sl = format_decimal(sl_price, symbol_filters, 'PRICE_FILTER')
        text = f"تم تحديد SL بنسبة {percentage}% ({formatted_sl}).\n\nاختر نسبة جني الأرباح (TP) (أو تخطَّ):"
        keyboard = build_percent_keyboard(CALLBACK_QB_TP_PERC_PREFIX, [2, 3, 5, 10])
        keyboard.inline_keyboard.append([InlineKeyboardButton("➡️ تخطَّ TP", callback_data=CALLBACK_QB_SKIP_TP)])
        
        await _send_or_edit(update, context, text, keyboard, edit=True)
        return QB_ASK_TP_PERCENT
        
    except Exception as e:
        logger.error(f"Error in quick buy SL percent handler: {e}", exc_info=True)
        await _send_or_edit(update, context, "⚠️ حدث خطأ في تحديد SL.", build_cancel_keyboard(CALLBACK_CANCEL_TRADE), edit=True)
        return ConversationHandler.END

async def quick_buy_tp_percent_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles TP percentage selection for quick buy."""
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    
    if query.data == CALLBACK_QB_SKIP_TP:
        context.user_data['qb_tp_price'] = None
        context.user_data['tp_price'] = None
        return await build_and_show_confirmation(update, context)
        
    pair = context.user_data.get('qb_pair')
    current_price = context.user_data.get('qb_current_price')
    sl_price = context.user_data.get('qb_sl_price')
    
    if not all([pair, current_price]):
        logger.error("Missing data for quick buy TP calculation")
        return await cancel_trade_conversation(update, context)
        
    try:
        percentage = int(query.data.split(CALLBACK_QB_TP_PERC_PREFIX, 1)[1])
        percentage_decimal = Decimal(percentage) / 100
        tp_price_raw = current_price * (1 + percentage_decimal) # For buy orders
        
        symbol_filters = get_symbol_filters(pair, context)
        tp_price = adjust_price(tp_price_raw, symbol_filters)
        
        if tp_price <= 0:
            raise ValueError("سعر TP المحسوب غير صالح.")
            
        if sl_price and tp_price <= sl_price:
            raise ValueError(f"سعر TP ({tp_price:f}) أقل من أو يساوي سعر SL ({sl_price:f}).")
            
        context.user_data['qb_tp_price'] = tp_price
        context.user_data['tp_price'] = tp_price # Set for market order
        
        return await build_and_show_confirmation(update, context)
        
    except Exception as e:
        logger.error(f"Error in quick buy TP percent handler: {e}", exc_info=True)
        await _send_or_edit(update, context, f"⚠️ خطأ في تحديد TP: {e}", build_cancel_keyboard(CALLBACK_CANCEL_TRADE), edit=True)
        return ConversationHandler.END

# --- نهاية وظائف الشراء السريع ---

async def cancel_trade_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE, clear_only: bool = False) -> int:
    """Cancels the trade conversation and clears trade data."""
    if not clear_only:
        query = update.callback_query
        if query: await query.answer()
        text = "تم إلغاء العملية."
        keyboard = build_main_menu_keyboard()
        await _send_or_edit(update, context, text, keyboard, edit=bool(query))

    # Clear trade data
    trade_keys = [k for k in context.user_data if k.startswith(('trade_', 'sell_', 'qb_'))]
    for key in trade_keys:
        context.user_data.pop(key, None)
    return ConversationHandler.END

async def history_ask_pair_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles manual pair input for trade history."""
    if not update.message or not update.message.text:
        return H_ASK_PAIR
    
    pair = update.message.text.strip().upper()
    
    # Validate Symbol
    if not is_valid_symbol(pair, context):
        await update.message.reply_text(
            f"⚠️ الرمز '{pair}' غير صالح أو غير متداول حالياً. الرجاء إدخال رمز صحيح:",
            reply_markup=build_cancel_keyboard(CALLBACK_CANCEL)
        )
        return H_ASK_PAIR
    
    if not binance_client:
        await update.message.reply_text("⚠️ عذرًا، اتصال Binance غير متاح حالياً.")
        return ConversationHandler.END
    
    try:
        # Send typing action while fetching
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
        
        # Get current price for additional context
        current_price = await get_current_price(pair, context)
        current_price_text = f"\n💰 السعر الحالي: ${current_price:f}" if current_price else ""
        
        # Show loading message
        loading_msg = await update.message.reply_text("⏳ جاري جلب كامل السجل التاريخي للعملة...")
        
        # Get all historical trades
        trades = await fetch_all_trades(pair, context)
        
        # Format trades with statistics only
        trades_text = format_trade_history(trades, show_trades=False)
        
        # Add pair name, current price, and total trades count to the message
        trades_text = (
            f"<b>تحليل تداولات {pair}</b>{current_price_text}\n"
            f"إجمالي عدد الصفقات: {len(trades)}\n\n"
            + trades_text
        )
        
        # Delete loading message
        await loading_msg.delete()
        
        keyboard = [[InlineKeyboardButton("🔙 رجوع لقائمة السجل", callback_data=CALLBACK_GOTO_HISTORY)]]
        await update.message.reply_html(trades_text, reply_markup=InlineKeyboardMarkup(keyboard))
        
    except Exception as e:
        logger.error(f"Error showing history for {pair}: {e}")
        await update.message.reply_text(
            f"⚠️ حدث خطأ أثناء جلب سجل {pair}.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=CALLBACK_GOTO_HISTORY)]])
        )
    return ConversationHandler.END

async def handle_history_pair_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the selection of a pair from the buttons."""
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    
    if query.data == CALLBACK_HISTORY_MANUAL_INPUT:
        text = "الرجاء إدخال زوج العملات لعرض سجله (مثال: BTCUSDT):"
        await _send_or_edit(update, context, text, build_cancel_keyboard(CALLBACK_CANCEL), edit=True)
        return H_ASK_PAIR
        
    pair = query.data.split(CALLBACK_HISTORY_BY_PAIR_START, 1)[1]
    
    if not is_valid_symbol(pair, context):
        await _send_or_edit(update, context, 
            f"⚠️ الرمز '{pair}' غير صالح أو غير متداول حالياً.",
            InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=CALLBACK_GOTO_HISTORY)]]),
            edit=True
        )
        return ConversationHandler.END

    try:
        # Show loading message
        await _send_or_edit(update, context, "⏳ جاري جلب كامل السجل التاريخي للعملة...", edit=True)
        
        # Get current price for additional context
        current_price = await get_current_price(pair, context)
        current_price_text = f"\n💰 السعر الحالي: ${current_price:f}" if current_price else ""
        
        # Get all historical trades
        trades = await fetch_all_trades(pair, context)
        
        # Format trades with statistics only
        trades_text = format_trade_history(trades, show_trades=False)
        
        # Add pair name, current price, and total trades count to the message
        trades_text = (
            f"<b>تحليل تداولات {pair}</b>{current_price_text}\n"
            f"إجمالي عدد الصفقات: {len(trades)}\n\n"
            + trades_text
        )
        
        keyboard = [[InlineKeyboardButton("🔙 رجوع لقائمة السجل", callback_data=CALLBACK_GOTO_HISTORY)]]
        await _send_or_edit(update, context, trades_text, InlineKeyboardMarkup(keyboard), edit=True)
        
    except Exception as e:
        logger.error(f"Error showing history for {pair}: {e}")
        await _send_or_edit(update, context, 
            f"⚠️ حدث خطأ أثناء جلب سجل {pair}.",
            InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=CALLBACK_GOTO_HISTORY)]]),
            edit=True
        )
    return ConversationHandler.END

def build_conversation_handlers() -> List[ConversationHandler]:
    """Builds and returns all conversation handlers."""
    # Trading conversation
    trading_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(trade_start, pattern=f"^({CALLBACK_START_BUY}|{CALLBACK_START_SELL})$"),
            CallbackQueryHandler(handle_buy_favorite_selection, pattern=f"^{CALLBACK_BUY_FAVORITE_PREFIX}"),
            CallbackQueryHandler(handle_buy_other_pair, pattern=f"^{CALLBACK_BUY_OTHER_PAIR}$"),
            CallbackQueryHandler(handle_quick_sell_pair, pattern=f"^{CALLBACK_QUICK_SELL_PAIR}"),
        ],
        states={
            T_ASK_PAIR: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ask_pair_handler),
                CallbackQueryHandler(handle_buy_favorite_selection, pattern=f"^{CALLBACK_BUY_FAVORITE_PREFIX}"),
                CallbackQueryHandler(handle_buy_other_pair, pattern=f"^{CALLBACK_BUY_OTHER_PAIR}$"),
            ],
            T_ASK_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_amount_handler)],
            T_CHOOSE_SELL_ASSET: [
                CallbackQueryHandler(choose_sell_asset_handler, pattern=f"^{CALLBACK_SELL_ASSET_PREFIX}"),
                CallbackQueryHandler(lambda u, c: cancel_trade_conversation(u, c), pattern=f"^{CALLBACK_GOTO_TRADING}$"),
            ],
            T_ASK_SELL_AMOUNT: [
                CallbackQueryHandler(ask_sell_amount_handler, pattern=f"^({CALLBACK_SELL_AMOUNT_ALL}|{CALLBACK_SELL_AMOUNT_PARTIAL})$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_sell_amount_input),
            ],
            T_ASK_SLTP_CHOICE: [
                CallbackQueryHandler(ask_sltp_choice_handler, pattern=f"^({CALLBACK_ADD_SLTP_YES}|{CALLBACK_ADD_SLTP_NO}|{CALLBACK_ADD_SLTP_PERCENT})$"),
                CallbackQueryHandler(lambda u, c: cancel_trade_conversation(u, c), pattern=f"^{CALLBACK_CANCEL_TRADE}$"),
            ],
            T_ASK_SL_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_sl_price_handler)],
            T_ASK_TP_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_tp_price_handler)],
            T_ASK_SL_PERCENT: [
                CallbackQueryHandler(ask_sl_percent_handler, pattern=f"^{CALLBACK_SL_PERCENT_PREFIX}"),
                CallbackQueryHandler(lambda u, c: cancel_trade_conversation(u, c), pattern=f"^{CALLBACK_CANCEL_TRADE}$"),
            ],
            T_ASK_TP_PERCENT: [
                CallbackQueryHandler(ask_tp_percent_handler, pattern=f"^{CALLBACK_TP_PERCENT_PREFIX}"),
                CallbackQueryHandler(ask_tp_percent_handler, pattern=f"^{CALLBACK_SKIP_TP}$"),
                CallbackQueryHandler(lambda u, c: cancel_trade_conversation(u, c), pattern=f"^{CALLBACK_CANCEL_TRADE}$"),
            ],
            T_CONFIRM_TRADE_STATE: [
                CallbackQueryHandler(confirm_trade_final_handler, pattern=f"^({CALLBACK_CONFIRM_TRADE}|{CALLBACK_CANCEL_TRADE})$"),
            ],
        },
        fallbacks=[
            CommandHandler("start", start_command),
            CommandHandler("cancel", lambda u, c: cancel_trade_conversation(u, c)),
            CallbackQueryHandler(lambda u, c: cancel_trade_conversation(u, c), pattern=f"^{CALLBACK_CANCEL_TRADE}$"),
            CallbackQueryHandler(navigation_button_handler, pattern=f"^{CALLBACK_GOTO_TRADING}$"),
        ],
        name="trading_conversation",
        persistent=True,
        per_message=True,  # Changed to True
        per_chat=True,
        per_user=True,
        allow_reentry=True  # Added allow_reentry
    )

    # Quick Sell conversation
    quick_sell_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(handle_quick_sell_pair, pattern=f"^{CALLBACK_QUICK_SELL_PAIR}"),
        ],
        states={
            T_ASK_SL_PERCENT: [
                CallbackQueryHandler(handle_quick_sell_sl_percent, pattern=f"^{CALLBACK_QS_SL_PERC_PREFIX}"),
                CallbackQueryHandler(lambda u, c: cancel_trade_conversation(u, c), pattern=f"^{CALLBACK_CANCEL_TRADE}$"),
            ],
            T_ASK_TP_PERCENT: [
                CallbackQueryHandler(handle_quick_sell_tp_percent, pattern=f"^{CALLBACK_QS_TP_PERC_PREFIX}"),
                CallbackQueryHandler(lambda u, c: cancel_trade_conversation(u, c), pattern=f"^{CALLBACK_CANCEL_TRADE}$"),
            ],
        },
        fallbacks=[
            CommandHandler("start", start_command),
            CommandHandler("cancel", lambda u, c: cancel_trade_conversation(u, c)),
            CallbackQueryHandler(lambda u, c: cancel_trade_conversation(u, c), pattern=f"^{CALLBACK_CANCEL_TRADE}$"),
            CallbackQueryHandler(navigation_button_handler, pattern=f"^{CALLBACK_GOTO_TRADING}$"),
        ],
        name="quick_sell_conversation",
        persistent=True,
        per_message=False,
        per_chat=True,
        per_user=True
    )

    # Search conversation
    search_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(search_manual_start, pattern=f"^{CALLBACK_SEARCH_MANUAL_START}$")],
        states={
            S_ASK_PAIR: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_ask_pair_handler)],
        },
        fallbacks=[
            CommandHandler("start", start_command),
            CommandHandler("cancel", lambda u, c: cancel_trade_conversation(u, c)),
            CallbackQueryHandler(lambda u, c: cancel_trade_conversation(u, c), pattern=f"^{CALLBACK_CANCEL}$"),
        ],
        name="search_conversation",
        persistent=True,
        per_message=False,
        per_chat=True,
        per_user=True
    )

    # History conversation
    history_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(history_by_pair_start, pattern=f"^{CALLBACK_HISTORY_BY_PAIR_START}$"),
            CallbackQueryHandler(handle_history_pair_selection, pattern=f"^{CALLBACK_HISTORY_BY_PAIR_START}.*$"),
        ],
        states={
            H_ASK_PAIR: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, history_ask_pair_handler),
                CallbackQueryHandler(handle_history_pair_selection, pattern=f"^{CALLBACK_HISTORY_BY_PAIR_START}.*$"),
                CallbackQueryHandler(history_by_pair_start, pattern=f"^{CALLBACK_HISTORY_MANUAL_INPUT}$"),
            ],
        },
        fallbacks=[
            CommandHandler("start", start_command),
            CommandHandler("cancel", lambda u, c: cancel_trade_conversation(u, c)),
            CallbackQueryHandler(lambda u, c: cancel_trade_conversation(u, c), pattern=f"^{CALLBACK_CANCEL}$"),
            CallbackQueryHandler(navigation_button_handler, pattern=f"^{CALLBACK_GOTO_HISTORY}$"),
        ],
        name="history_conversation",
        persistent=True,
        per_message=False,
        per_chat=True,
        per_user=True
    )

    # Favorites conversation
    favorites_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_favorite_start, pattern=f"^{CALLBACK_ADD_FAVORITE_START}$")],
        states={
            FAV_ASK_ADD_PAIR: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_favorite_pair_handler)],
        },
        fallbacks=[
            CommandHandler("start", start_command),
            CommandHandler("cancel", lambda u, c: cancel_trade_conversation(u, c)),
            CallbackQueryHandler(lambda u, c: cancel_trade_conversation(u, c), pattern=f"^{CALLBACK_CANCEL}$"),
        ],
        name="favorites_conversation",
        persistent=True,
        per_message=False,
        per_chat=True,
        per_user=True
    )

    # Settings conversation
    settings_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(settings_set_max_buy_start, pattern=f"^{CALLBACK_SET_MAX_BUY_START}$")],
        states={
            SET_ASK_MAX_BUY_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, settings_ask_max_buy_amount_handler)],
        },
        fallbacks=[
            CommandHandler("start", start_command),
            CommandHandler("cancel", lambda u, c: cancel_trade_conversation(u, c)),
            CallbackQueryHandler(lambda u, c: cancel_trade_conversation(u, c)),
        ],
        name="settings_conversation",
        persistent=True,
        per_message=False,
        per_chat=True,
        per_user=True
    )

    # Quick Buy conversation
    quick_buy_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(quick_buy_start, pattern=f"^{CALLBACK_QUICK_BUY_START}$")],
        states={
            QB_ASK_PAIR: [
                CallbackQueryHandler(quick_buy_pair_handler, pattern=f"^{CALLBACK_BUY_FAVORITE_PREFIX}"),
                CallbackQueryHandler(quick_buy_pair_handler, pattern=f"^{CALLBACK_BUY_OTHER_PAIR}$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, quick_buy_pair_handler),
            ],
            QB_ASK_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, quick_buy_amount_handler)],
            QB_ASK_SL_PERCENT: [CallbackQueryHandler(quick_buy_sl_percent_handler, pattern=f"^{CALLBACK_QB_SL_PERC_PREFIX}")],
            QB_ASK_TP_PERCENT: [
                CallbackQueryHandler(quick_buy_tp_percent_handler, pattern=f"^{CALLBACK_QB_TP_PERC_PREFIX}"),
                CallbackQueryHandler(quick_buy_tp_percent_handler, pattern=f"^{CALLBACK_QB_SKIP_TP}$"),
            ],
            T_CONFIRM_TRADE_STATE: [CallbackQueryHandler(confirm_trade_final_handler, pattern=f"^({CALLBACK_CONFIRM_TRADE}|{CALLBACK_CANCEL_TRADE})$")],
        },
        fallbacks=[
            CommandHandler("start", start_command),
            CommandHandler("cancel", lambda u, c: cancel_trade_conversation(u, c)),
            CallbackQueryHandler(lambda u, c: cancel_trade_conversation(u, c)),
        ],
        name="quick_buy_conversation",
        persistent=True,
        per_message=False,
        per_chat=True,
        per_user=True
    )

    # Add alerts conversation
    alerts_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_manual_threshold_input, pattern="^alert_manual_input$"),
            CallbackQueryHandler(start_add_custom_alert, pattern=f"^{CALLBACK_CUSTOM_ALERT_ADD}$")
        ],
        states={
            ALERT_ASK_THRESHOLD: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_manual_threshold_input)],
            CUSTOM_ALERT_ASK_SYMBOL: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_alert_symbol)],
            CUSTOM_ALERT_ASK_THRESHOLD: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_alert_threshold)]
        },
        fallbacks=[
            CommandHandler("start", start_command),
            CommandHandler("cancel", lambda u, c: cancel_trade_conversation(u, c)),
            CallbackQueryHandler(lambda u, c: show_alerts_menu(u, c), pattern=f"^{CALLBACK_GOTO_ALERTS}$"),
            CallbackQueryHandler(remove_custom_alert, pattern=f"^{CALLBACK_CUSTOM_ALERT_REMOVE}_.*$")
        ],
        name="alerts_conversation",
        persistent=True,
        per_message=False,
        per_chat=True,
        per_user=True
    )

    # Return all conversation handlers
    return [
        trading_conv,
        search_conv,
        history_conv,
        favorites_conv,
        settings_conv,
        quick_buy_conv,
        alerts_conv,
        quick_sell_conv  # Add the new conversation handler
    ]

async def cancel_all_sell_orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cancels all open sell orders."""
    query = update.callback_query
    if not query: return
    await query.answer()
    
    if not binance_client:
        await _send_or_edit(update, context, "⚠️ عذرًا، اتصال Binance غير متاح حالياً.", edit=True)
        return

    try:
        # Get all open orders
        open_orders = binance_client.get_open_orders()
        sell_orders = [order for order in open_orders if order['side'] == 'SELL']
        
        if not sell_orders:
            await _send_or_edit(update, context, "لا توجد أوامر بيع مفتوحة للإلغاء.", edit=True)
            return

        # Cancel each sell order
        cancelled_count = 0
        failed_count = 0
        error_messages = []

        for order in sell_orders:
            try:
                binance_client.cancel_order(symbol=order['symbol'], orderId=order['orderId'])
                cancelled_count += 1
            except Exception as e:
                failed_count += 1
                error_messages.append(f"{order['symbol']}: {str(e)}")
                logger.error(f"Error cancelling order {order['orderId']} for {order['symbol']}: {e}")

        # Prepare response message
        response = f"✅ تم إلغاء {cancelled_count} أمر بيع بنجاح."
        if failed_count > 0:
            response += f"\n❌ فشل إلغاء {failed_count} أمر."
            if error_messages:
                response += "\nالأخطاء:"
                for msg in error_messages[:5]:  # Show first 5 errors only
                    response += f"\n- {msg}"
                if len(error_messages) > 5:
                    response += "\n..."

        await _send_or_edit(update, context, response, None, edit=True)
        # Show updated orders after a short delay
        await asyncio.sleep(1)
        await show_orders_info(update, context)

    except Exception as e:
        logger.error(f"Error in cancel_all_sell_orders: {e}", exc_info=True)
        error_text = "⚠️ حدث خطأ أثناء محاولة إلغاء الأوامر."
        keyboard = [[InlineKeyboardButton("🔙 رجوع لقائمة التداول", callback_data=CALLBACK_GOTO_TRADING)]]
        await _send_or_edit(update, context, error_text, InlineKeyboardMarkup(keyboard), edit=True)

async def main() -> None:
    """Main function to start the bot."""
    try:
        logger.info("Starting main function...")
        
        # Initialize persistence
        logger.info("Initializing persistence...")
        persistence = PicklePersistence(filepath="bot_data.pickle")
        
        # Create the Application and pass it your bot's token
        logger.info("Creating application with token...")
        if not TELEGRAM_BOT_TOKEN:
            logger.error("TELEGRAM_BOT_TOKEN is not set!")
            return
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).persistence(persistence).build()
        logger.info("Application created successfully")

        # Get all conversation handlers
        logger.info("Building conversation handlers...")
        conversation_handlers = build_conversation_handlers()
        logger.info(f"Built {len(conversation_handlers)} conversation handlers")
        
        # Add conversation handlers
        logger.info("Adding handlers to application...")
        for handler in conversation_handlers:
            application.add_handler(handler)
            logger.debug(f"Added handler: {handler.name}")
        
        # Add command handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("help", help_command_handler))
        application.add_handler(CommandHandler("balance", balance_command_handler))
        application.add_handler(CommandHandler("orders", orders_command_handler))
        application.add_handler(CommandHandler("settings", settings_command_handler))
        logger.info("Added command handlers")
        
        # Add navigation button handlers
        application.add_handler(CallbackQueryHandler(navigation_button_handler, pattern=f"^{CALLBACK_MAIN_MENU}$"))
        application.add_handler(CallbackQueryHandler(navigation_button_handler, pattern=f"^{CALLBACK_GOTO_TRADING}$"))
        application.add_handler(CallbackQueryHandler(navigation_button_handler, pattern=f"^{CALLBACK_GOTO_ACCOUNT}$"))
        application.add_handler(CallbackQueryHandler(navigation_button_handler, pattern=f"^{CALLBACK_GOTO_SEARCH}$"))
        application.add_handler(CallbackQueryHandler(navigation_button_handler, pattern=f"^{CALLBACK_GOTO_HISTORY}$"))
        application.add_handler(CallbackQueryHandler(navigation_button_handler, pattern=f"^{CALLBACK_GOTO_FAVORITES}$"))
        application.add_handler(CallbackQueryHandler(navigation_button_handler, pattern=f"^{CALLBACK_GOTO_SETTINGS}$"))
        application.add_handler(CallbackQueryHandler(navigation_button_handler, pattern=f"^{CALLBACK_GOTO_ALERTS}$"))
        application.add_handler(CallbackQueryHandler(navigation_button_handler, pattern=f"^{CALLBACK_SHOW_HELP}$"))
        application.add_handler(CallbackQueryHandler(navigation_button_handler, pattern=f"^{CALLBACK_SHOW_BALANCE}$"))
        application.add_handler(CallbackQueryHandler(navigation_button_handler, pattern=f"^{CALLBACK_SHOW_ORDERS}$"))
        application.add_handler(CallbackQueryHandler(show_total_pnl, pattern=f"^{CALLBACK_SHOW_PNL}$"))
        logger.info("Added navigation handlers")
        
        # Add market data handlers
        application.add_handler(CallbackQueryHandler(show_gainers, pattern=f"^{CALLBACK_SHOW_GAINERS}$"))
        application.add_handler(CallbackQueryHandler(show_losers, pattern=f"^{CALLBACK_SHOW_LOSERS}$"))
        logger.info("Added market data handlers")
        
        # Add favorites handlers
        application.add_handler(CallbackQueryHandler(remove_favorite_start, pattern=f"^{CALLBACK_REMOVE_FAVORITE_START}$"))
        application.add_handler(CallbackQueryHandler(remove_favorite_pair_handler, pattern=f"^{CALLBACK_REMOVE_FAVORITE_PREFIX}"))
        logger.info("Added favorites handlers")
        
        # Add history handlers
        application.add_handler(CallbackQueryHandler(show_today_trades, pattern=f"^{CALLBACK_HISTORY_TODAY}$"))
        logger.info("Added history handlers")
        
        # Add alerts handlers
        application.add_handler(CallbackQueryHandler(toggle_alerts, pattern=f"^{CALLBACK_TOGGLE_ALERTS}$"))
        application.add_handler(CallbackQueryHandler(set_alert_threshold_start, pattern=f"^{CALLBACK_SET_ALERT_THRESHOLD_START}$"))
        application.add_handler(CallbackQueryHandler(handle_alert_threshold_selection, pattern=f"^{CALLBACK_ALERT_PERC_PREFIX}"))
        logger.info("Added alerts handlers")

        # Add cancel all sell orders handler
        application.add_handler(CallbackQueryHandler(cancel_all_sell_orders, pattern=f"^{CALLBACK_CANCEL_ALL_SELL_ORDERS}$"))
        logger.info("Added cancel all sell orders handler")

        # Add trading handlers
        application.add_handler(CallbackQueryHandler(trade_start, pattern=f"^{CALLBACK_START_BUY}$"))
        application.add_handler(CallbackQueryHandler(trade_start, pattern=f"^{CALLBACK_START_SELL}$"))
        application.add_handler(CallbackQueryHandler(handle_quick_sell_pair, pattern=f"^{CALLBACK_QUICK_SELL_PAIR}"))
        application.add_handler(CallbackQueryHandler(handle_buy_favorite_selection, pattern=f"^{CALLBACK_BUY_FAVORITE_PREFIX}"))
        application.add_handler(CallbackQueryHandler(handle_buy_other_pair, pattern=f"^{CALLBACK_BUY_OTHER_PAIR}$"))
        logger.info("Added trading handlers")

        # Start the bot
        logger.info("Starting bot...")
        
        # Fetch initial exchange info
        await fetch_and_cache_exchange_info(application)
        logger.info("Exchange info cached")
        
        logger.info("Starting polling...")
        
        # Set up polling in a way that works with Python 3.12
        await application.initialize()
        await application.start()
        await application.updater.start_polling(drop_pending_updates=True)
        
        logger.info("Bot is running. Press Ctrl+C to stop.")
        
        # Keep the bot running
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Stopping bot...")
        await application.stop()
        await application.shutdown()
    except Exception as e:
        logger.error(f"Error in main function: {e}", exc_info=True)
        raise

if __name__ == '__main__':
    try:
        logger.info("Starting bot script...")
        asyncio.run(main())
        logger.info("Bot script completed normally")
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
