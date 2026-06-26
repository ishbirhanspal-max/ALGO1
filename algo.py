import ccxt
import time
import numpy as np
import gspread
from datetime import datetime
from google.oauth2.service_account import Credentials

# 1. Initialize Exchange Connection (Binance Testnet)
# REPLACE THESE WITH NEW KEYS AFTER DELETING THE COMPROMISED ONES
exchange = ccxt.binance({
    'apiKey': 'AiZOnxG8QEUMtC9rqk6YFGUmVeHJHO5HDTMxfPk52F8IS3kKx8OKf4ojHRaOgXjC',     
    'secret': 'xOLWId9We6FUt7ejb0zcg8LMHDSwqyTcgDrI4g0kwqoCJVaET13mmivc8o2ugh6n',  
    'enableRateLimit': True,
})
exchange.set_sandbox_mode(True)

# 2. Strategy Parameters
SYMBOL_A = 'BTC/USDT'
SYMBOL_B = 'ETH/USDT'
WINDOW_SIZE = 20         
TRADE_USD_SIZE = 1000    # Set to $1000 as requested

# State Management
current_state = 'NONE'
spread_history = []
qty_a = 0.0
qty_b = 0.0
entry_price_a = 0.0
entry_price_b = 0.0
total_realized_pl = 0.0

# --- GOOGLE SHEETS SETUP ---
# Ensure your JSON file is in the same folder and the name matches exactly!
JSON_FILE = 'stock-automation-487422-87d85d0a01ee.json' 
scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']

print(f"Connecting to Google Sheets using {JSON_FILE}...")
credentials = Credentials.from_service_account_file(JSON_FILE, scopes=scopes)
client = gspread.authorize(credentials)
sheet = client.open('Crypto_Bot_Logs').sheet1

if not sheet.row_values(1):
    sheet.append_row(['Timestamp', 'Action', 'State', 'Asset A', 'Asset B', 'Price A', 'Price B', 'Unrealized P/L', 'Realized P/L'])

def log_trade(action, state, price_a, price_b, unrealized, realized):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # Row data including Asset Names
    row_data = [timestamp, action, state, SYMBOL_A, SYMBOL_B, round(price_a, 2), round(price_b, 2), round(unrealized, 2), round(realized, 2)]
    try:
        sheet.append_row(row_data)
        print(f"📝 Logged {action} to Google Sheets.")
    except Exception as e:
        print(f"⚠️ Failed to log to Sheets: {e}")

# Pre-seed window
ohlcv_a = exchange.fetch_ohlcv(SYMBOL_A, timeframe='1m', limit=WINDOW_SIZE)
ohlcv_b = exchange.fetch_ohlcv(SYMBOL_B, timeframe='1m', limit=WINDOW_SIZE)
for i in range(len(ohlcv_a)):
    spread_history.append(ohlcv_a[i][4] - ohlcv_b[i][4])

print(f"✅ Monitoring {SYMBOL_A} vs {SYMBOL_B} with ${TRADE_USD_SIZE} size.")

while True:
    try:
        ticker_a = exchange.fetch_ticker(SYMBOL_A)
        ticker_b = exchange.fetch_ticker(SYMBOL_B)
        price_a, price_b = ticker_a['last'], ticker_b['last']
        
        current_spread = price_a - price_b
        spread_history.append(current_spread)
        if len(spread_history) > WINDOW_SIZE: spread_history.pop(0)
            
        z_score = (current_spread - np.mean(spread_history)) / (np.std(spread_history) or 0.0001)
        
        # Calculate P/L
        unrealized_pl = 0.0
        if current_state == 'LONG_SPREAD':
            unrealized_pl = ((price_a - entry_price_a) * qty_a) + ((entry_price_b - price_b) * qty_b)
        elif current_state == 'SHORT_SPREAD':
            unrealized_pl = ((entry_price_a - price_a) * qty_a) + ((price_b - entry_price_b) * qty_b)

        # Print Status with Asset Names
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {SYMBOL_A}/{SYMBOL_B} | Z: {z_score:+.2f} | Un-Realized: ${unrealized_pl:+.2f} | Realized: ${total_realized_pl:+.2f}")

        # --- EXECUTION LOGIC ---
        if current_state == 'NONE':
            if z_score < -2.0:
                qty_a, qty_b = TRADE_USD_SIZE / price_a, TRADE_USD_SIZE / price_b
                entry_price_a, entry_price_b = price_a, price_b
                exchange.create_market_buy_order(SYMBOL_A, qty_a)
                exchange.create_market_sell_order(SYMBOL_B, qty_b)
                current_state = 'LONG_SPREAD'
                log_trade('OPEN_LONG_SPREAD', current_state, price_a, price_b, 0.0, total_realized_pl)

            elif z_score > 2.0:
                qty_a, qty_b = TRADE_USD_SIZE / price_a, TRADE_USD_SIZE / price_b
                entry_price_a, entry_price_b = price_a, price_b
                exchange.create_market_sell_order(SYMBOL_A, qty_a)
                exchange.create_market_buy_order(SYMBOL_B, qty_b)
                current_state = 'SHORT_SPREAD'
                log_trade('OPEN_SHORT_SPREAD', current_state, price_a, price_b, 0.0, total_realized_pl)

        elif current_state == 'LONG_SPREAD' and z_score >= -0.5:
            exchange.create_market_sell_order(SYMBOL_A, qty_a)
            exchange.create_market_buy_order(SYMBOL_B, qty_b)
            total_realized_pl += unrealized_pl
            log_trade('CLOSE_LONG', current_state, price_a, price_b, 0.0, total_realized_pl)
            current_state = 'NONE'

        elif current_state == 'SHORT_SPREAD' and z_score <= 0.5:
            exchange.create_market_buy_order(SYMBOL_A, qty_a)
            exchange.create_market_sell_order(SYMBOL_B, qty_b)
            total_realized_pl += unrealized_pl
            log_trade('CLOSE_SHORT', current_state, price_a, price_b, 0.0, total_realized_pl)
            current_state = 'NONE'

        time.sleep(1)

    except Exception as e:
        print(f"Error: {e}")
        time.sleep(10)
