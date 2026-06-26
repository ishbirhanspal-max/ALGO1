import ccxt
import time
import numpy as np
import csv
from datetime import datetime

# 1. Initialize Exchange Connection (Binance Testnet)
exchange = ccxt.binance({
    'apiKey': 'YOUR_TESTNET_API_KEY',     
    'secret': 'YOUR_TESTNET_SECRET_KEY',  
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

# 3. Setup CSV File (Creates file and adds Headers if it doesn't exist)
csv_filename = 'trade_history.csv'
with open(csv_filename, 'w', newline='') as file:
    writer = csv.writer(file)
    writer.writerow(['Timestamp', 'Action', 'State', 'Asset A Price', 'Asset B Price', 'Realized P/L', 'Total P/L'])

def log_trade(action, state, price_a, price_b, realized_pl, total_pl):
    """Helper function to write a row to the CSV file"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(csv_filename, 'a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([timestamp, action, state, price_a, price_b, round(realized_pl, 4), round(total_pl, 4)])

print("Initializing bot and pre-seeding historical rolling window...")
spread_history = []
ohlcv_a = exchange.fetch_ohlcv(SYMBOL_A, timeframe='1m', limit=WINDOW_SIZE)
ohlcv_b = exchange.fetch_ohlcv(SYMBOL_B, timeframe='1m', limit=WINDOW_SIZE)

for i in range(len(ohlcv_a)):
    spread_history.append(ohlcv_a[i][4] - ohlcv_b[i][4])

print("Starting real-time Statistical Arbitrage execution loop...")
print(f"Trades will be saved to: {csv_filename}")
print("-" * 60)

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

        time.sleep(5)

    except Exception as e:
        print(f"Error encountered: {e}")
        time.sleep(10)
