import ccxt
import time
import numpy as np
import csv
from datetime import datetime

# 1. Initialize Exchange Connection (Binance Testnet)
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
qty_a = 0.0
qty_b = 0.0
entry_price_a = 0.0
entry_price_b = 0.0
total_realized_pl = 0.0

import ccxt
import time
import numpy as np
from datetime import datetime
import gspread
from google.oauth2.service_account import stock-automation-487422-87d85d0a01ee.json

# --- GOOGLE SHEETS SETUP ---
# Define the API scopes required
scopes = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

# Authenticate using the JSON file you downloaded
print("Connecting to Google Sheets...")
credentials = Credentials.from_service_account_file('credentials.json', scopes=scopes)
client = gspread.authorize(credentials)

# Open the specific sheet by name
sheet = client.open('Crypto_Bot_Logs').sheet1

# Optional: Write headers if the sheet is completely empty
if not sheet.row_values(1):
    sheet.append_row(['Timestamp', 'Action', 'State', 'Asset A Price', 'Asset B Price', 'Realized P/L', 'Total P/L'])

print("✅ Connected to Google Sheets!")

def log_trade(action, state, price_a, price_b, realized_pl, total_pl):
    """Helper function to write a row directly to Google Sheets in real-time"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    row_data = [timestamp, action, state, price_a, price_b, round(realized_pl, 4), round(total_pl, 4)]
    
    try:
        # Appends the new trade as a new row at the bottom of the sheet
        sheet.append_row(row_data)
        print("📝 Logged trade to Google Sheets successfully.")
    except Exception as e:
        print(f"⚠️ Failed to log to Sheets: {e}")

# 4. Real-Time Execution Loop
while True:
    try:
        # Fetch live data
        ticker_a = exchange.fetch_ticker(SYMBOL_A)
        ticker_b = exchange.fetch_ticker(SYMBOL_B)
        price_a = ticker_a['last']
        price_b = ticker_b['last']
        
        current_spread = price_a - price_b
        
        # Update rolling window
        spread_history.append(current_spread)
        if len(spread_history) > WINDOW_SIZE:
            spread_history.pop(0)
            
        # Calculate stats
        rolling_mean = np.mean(spread_history)
        rolling_std = np.std(spread_history)
        if rolling_std == 0: rolling_std = 0.0001
        z_score = (current_spread - rolling_mean) / rolling_std
        
        # Calculate Unrealized P/L if holding a position
        unrealized_pl = 0.0
        if current_state == 'LONG_SPREAD':
            # Long A, Short B
            unrealized_pl = ((price_a - entry_price_a) * qty_a) + ((entry_price_b - price_b) * qty_b)
        elif current_state == 'SHORT_SPREAD':
            # Short A, Long B
            unrealized_pl = ((entry_price_a - price_a) * qty_a) + ((price_b - entry_price_b) * qty_b)

        # Print Live Status
        timestamp = datetime.now().strftime('%H:%M:%S')
        status = f"[{timestamp}] Z-Score: {z_score:+.2f} | State: {current_state}"
        if current_state != 'NONE':
            status += f" | Unrealized P/L: ${unrealized_pl:+.3f}"
        print(status)


        # --- EXECUTION LOGIC ---
        
        if current_state == 'NONE':
            if z_score < -2.0:
                print(f"\n🚨 ENTRY TRIGGER: Z-Score < -2.0. BUYING SPREAD...")
                qty_a = TRADE_USD_SIZE / price_a
                qty_b = TRADE_USD_SIZE / price_b
                entry_price_a = price_a
                entry_price_b = price_b
                
                exchange.create_market_buy_order(SYMBOL_A, qty_a)
                exchange.create_market_sell_order(SYMBOL_B, qty_b)
                
                current_state = 'LONG_SPREAD'
                log_trade('OPEN_ENTRY', current_state, price_a, price_b, 0.0, total_realized_pl)
                print(f"Filled: LONG {SYMBOL_A} @ {price_a} | SHORT {SYMBOL_B} @ {price_b}\n")

            elif z_score > 2.0:
                print(f"\n🚨 ENTRY TRIGGER: Z-Score > +2.0. SHORTING SPREAD...")
                qty_a = TRADE_USD_SIZE / price_a
                qty_b = TRADE_USD_SIZE / price_b
                entry_price_a = price_a
                entry_price_b = price_b
                
                exchange.create_market_sell_order(SYMBOL_A, qty_a)
                exchange.create_market_buy_order(SYMBOL_B, qty_b)
                
                current_state = 'SHORT_SPREAD'
                log_trade('OPEN_ENTRY', current_state, price_a, price_b, 0.0, total_realized_pl)
                print(f"Filled: SHORT {SYMBOL_A} @ {price_a} | LONG {SYMBOL_B} @ {price_b}\n")

        elif current_state == 'LONG_SPREAD' and z_score >= -0.5:
            print(f"\n✅ EXIT TRIGGER: Z-Score reverted above -0.5. CLOSING SPREAD...")
            
            exchange.create_market_sell_order(SYMBOL_A, qty_a)
            exchange.create_market_buy_order(SYMBOL_B, qty_b)
            
            # The Unrealized P/L now becomes Realized
            trade_profit = unrealized_pl
            total_realized_pl += trade_profit
            
            log_trade('CLOSE_EXIT', current_state, price_a, price_b, trade_profit, total_realized_pl)
            current_state = 'NONE'
            print(f"Closed Position. Trade P/L: ${trade_profit:+.3f} | Total P/L: ${total_realized_pl:+.3f}\n")

        elif current_state == 'SHORT_SPREAD' and z_score <= 0.5:
            print(f"\n✅ EXIT TRIGGER: Z-Score reverted below +0.5. CLOSING SPREAD...")
            
            exchange.create_market_buy_order(SYMBOL_A, qty_a)
            exchange.create_market_sell_order(SYMBOL_B, qty_b)
            
            # The Unrealized P/L now becomes Realized
            trade_profit = unrealized_pl
            total_realized_pl += trade_profit
            
            log_trade('CLOSE_EXIT', current_state, price_a, price_b, trade_profit, total_realized_pl)
            current_state = 'NONE'
            print(f"Closed Position. Trade P/L: ${trade_profit:+.3f} | Total P/L: ${total_realized_pl:+.3f}\n")

        time.sleep(1)

    except Exception as e:
        print(f"Error encountered: {e}")
        time.sleep(10)
