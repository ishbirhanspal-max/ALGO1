import ccxt
import time
import numpy as np
import gspread
from datetime import datetime
from google.oauth2.service_account import Credentials

# 1. Initialize Exchange Connection (Binance Testnet)
# REPLACE THESE WITH NEW KEYS AFTER YOU DELETE THE COMPROMISED ONES
exchange = ccxt.binance({
    'apiKey': 'AiZOnxG8QEUMtC9rqk6YFGUmVeHJHO5HDTMxfPk52F8IS3kKx8OKf4ojHRaOgXjC',     
    'secret': 'xOLWId9We6FUt7ejb0zcg8LMHDSwqyTcgDrI4g0kwqoCJVaET13mmivc8o2ugh6n',  
    'enableRateLimit': True,
})
exchange.set_sandbox_mode(True)

# 2. Strategy Parameters
SYMBOL_A = 'SOL/USDT'
SYMBOL_B = 'LTC/USDT'
WINDOW_SIZE = 20         
TRADE_USD_SIZE = 20      

# State Management & Financial Tracking
current_state = 'NONE'
spread_history = []
qty_a = 0.0
qty_b = 0.0
entry_price_a = 0.0
entry_price_b = 0.0
total_realized_pl = 0.0

# --- GOOGLE SHEETS SETUP ---
scopes = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

print("Connecting to Google Sheets...")
# Ensure your file is named exactly 'credentials.json' and is in this folder
credentials = Credentials.from_service_account_file('credentials.json', scopes=scopes)
client = gspread.authorize(credentials)

sheet = client.open('Crypto_Bot_Logs').sheet1

if not sheet.row_values(1):
    sheet.append_row(['Timestamp', 'Action', 'State', 'Asset A Price', 'Asset B Price', 'Realized P/L', 'Total P/L'])

print("✅ Connected to Google Sheets!")

def log_trade(action, state, price_a, price_b, realized_pl, total_pl):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    row_data = [timestamp, action, state, price_a, price_b, round(realized_pl, 4), round(total_pl, 4)]
    try:
        sheet.append_row(row_data)
        print("📝 Logged trade to Google Sheets.")
    except Exception as e:
        print(f"⚠️ Failed to log to Sheets: {e}")

# Pre-seed window
ohlcv_a = exchange.fetch_ohlcv(SYMBOL_A, timeframe='1m', limit=WINDOW_SIZE)
ohlcv_b = exchange.fetch_ohlcv(SYMBOL_B, timeframe='1m', limit=WINDOW_SIZE)
for i in range(len(ohlcv_a)):
    spread_history.append(ohlcv_a[i][4] - ohlcv_b[i][4])

print("Starting real-time execution loop...")

# 4. Real-Time Execution Loop
while True:
    try:
        ticker_a = exchange.fetch_ticker(SYMBOL_A)
        ticker_b = exchange.fetch_ticker(SYMBOL_B)
        price_a = ticker_a['last']
        price_b = ticker_b['last']
        
        current_spread = price_a - price_b
        spread_history.append(current_spread)
        if len(spread_history) > WINDOW_SIZE:
            spread_history.pop(0)
            
        rolling_mean = np.mean(spread_history)
        rolling_std = np.std(spread_history)
        if rolling_std == 0: rolling_std = 0.0001
        
        # Z-Score Calculation [cite: 26, 46]
        z_score = (current_spread - rolling_mean) / rolling_std
        
        unrealized_pl = 0.0
        if current_state == 'LONG_SPREAD':
            unrealized_pl = ((price_a - entry_price_a) * qty_a) + ((entry_price_b - price_b) * qty_b)
        elif current_state == 'SHORT_SPREAD':
            unrealized_pl = ((entry_price_a - price_a) * qty_a) + ((price_b - entry_price_b) * qty_b)

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Z-Score: {z_score:+.2f} | State: {current_state}")

        # --- EXECUTION LOGIC (Statistical Arbitrage) ---
        if current_state == 'NONE':
            if z_score < -2.0: # Long Spread Entry [cite: 48]
                qty_a = TRADE_USD_SIZE / price_a
                qty_b = TRADE_USD_SIZE / price_b
                entry_price_a, entry_price_b = price_a, price_b
                exchange.create_market_buy_order(SYMBOL_A, qty_a)
                exchange.create_market_sell_order(SYMBOL_B, qty_b)
                current_state = 'LONG_SPREAD'
                log_trade('OPEN_ENTRY', current_state, price_a, price_b, 0.0, total_realized_pl)

            elif z_score > 2.0: # Short Spread Entry [cite: 51]
                qty_a = TRADE_USD_SIZE / price_a
                qty_b = TRADE_USD_SIZE / price_b
                entry_price_a, entry_price_b = price_a, price_b
                exchange.create_market_sell_order(SYMBOL_A, qty_a)
                exchange.create_market_buy_order(SYMBOL_B, qty_b)
                current_state = 'SHORT_SPREAD'
                log_trade('OPEN_ENTRY', current_state, price_a, price_b, 0.0, total_realized_pl)

        elif current_state == 'LONG_SPREAD' and z_score >= -0.5: # Exit Trigger [cite: 56]
            exchange.create_market_sell_order(SYMBOL_A, qty_a)
            exchange.create_market_buy_order(SYMBOL_B, qty_b)
            total_realized_pl += unrealized_pl
            log_trade('CLOSE_EXIT', current_state, price_a, price_b, unrealized_pl, total_realized_pl)
            current_state = 'NONE'

        elif current_state == 'SHORT_SPREAD' and z_score <= 0.5: # Exit Trigger [cite: 58]
            exchange.create_market_buy_order(SYMBOL_A, qty_a)
            exchange.create_market_sell_order(SYMBOL_B, qty_b)
            total_realized_pl += unrealized_pl
            log_trade('CLOSE_EXIT', current_state, price_a, price_b, unrealized_pl, total_realized_pl)
            current_state = 'NONE'

        time.sleep(1) # Refresh rate set to 1 second

    except Exception as e:
        print(f"Error encountered: {e}")
        time.sleep(10)
