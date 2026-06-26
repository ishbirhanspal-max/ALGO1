import ccxt
import time
import numpy as np

# 1. Initialize Exchange Connection (Binance Testnet)
exchange = ccxt.binance({
    'apiKey': 'AiZOnxG8QEUMtC9rqk6YFGUmVeHJHO5HDTMxfPk52F8IS3kKx8OKf4ojHRaOgXjC',     # Replace with your Testnet API Key
    'secret': 'xOLWId9We6FUt7ejb0zcg8LMHDSwqyTcgDrI4g0kwqoCJVaET13mmivc8o2ugh6n',  # Replace with your Testnet Secret Key
    'enableRateLimit': True,
})
exchange.set_sandbox_mode(True) # Activates free fake money mode

# 2. Strategy Parameters
SYMBOL_A = 'SOL/USDT'
SYMBOL_B = 'LTC/USDT'
WINDOW_SIZE = 20         # Size of the rolling window
TRADE_USD_SIZE = 20      # Risking ~$20 per leg of the trade

# Track current position state: 'NONE', 'LONG_SPREAD', or 'SHORT_SPREAD'
current_state = 'NONE'

# Quantities held (tracked to ensure exact closure during exits)
qty_a = 0
qty_b = 0

print("Initializing bot and pre-seeding historical rolling window...")
spread_history = []

# Fetch historical data to immediately build the rolling window
ohlcv_a = exchange.fetch_ohlcv(SYMBOL_A, timeframe='1m', limit=WINDOW_SIZE)
ohlcv_b = exchange.fetch_ohlcv(SYMBOL_B, timeframe='1m', limit=WINDOW_SIZE)

for i in range(len(ohlcv_a)):
    spread_history.append(ohlcv_a[i][4] - ohlcv_b[i][4]) # Close Price A - Close Price B

print(f"Successfully seeded window with {len(spread_history)} historical data points.")
print("Starting real-time Statistical Arbitrage execution loop...")

# 3. Real-Time Execution Loop
while True:
    try:
        # Fetch live ticker prices simultaneously
        ticker_a = exchange.fetch_ticker(SYMBOL_A)
        ticker_b = exchange.fetch_ticker(SYMBOL_B)
        
        price_a = ticker_a['last']
        price_b = ticker_b['last']
        
        # Calculate current live spread
        current_spread = price_a - price_b
        
        # Update rolling window: append latest spread, drop oldest
        spread_history.append(current_spread)
        if len(spread_history) > WINDOW_SIZE:
            spread_history.pop(0)
            
        # Calculate statistical metrics
        rolling_mean = np.mean(spread_history)
        rolling_std = np.std(spread_history)
        
        # Guard clause against zero division
        if rolling_std == 0:
            rolling_std = 0.0001
            
        # Mathematical core: Z-Score calculation
        z_score = (current_spread - rolling_mean) / rolling_std
        
        print(f"Live Prices -> A: {price_a} | B: {price_b} | Spread: {current_spread:.4f} | Z-Score: {z_score:.2f} | State: {current_state}")

        # --- EXECUTION LOGIC ---
        
        if current_state == 'NONE':
            # ENTRY TRIGGER: LONG SPREAD (Z < -2.0)
            if z_score < -2.0:
                qty_a = TRADE_USD_SIZE / price_a
                qty_b = TRADE_USD_SIZE / price_b
                print(f"🚨 ENTRY TRIGGER: Z-Score ({z_score:.2f}) < -2.0. BUYING SPREAD...")
                
                exchange.create_market_buy_order(SYMBOL_A, qty_a)
                exchange.create_market_sell_order(SYMBOL_B, qty_b)
                
                current_state = 'LONG_SPREAD'
                print(f"Position opened: LONG {qty_a:.3f} {SYMBOL_A} & SHORT {qty_b:.3f} {SYMBOL_B}")

            # ENTRY TRIGGER: SHORT SPREAD (Z > +2.0)
            elif z_score > 2.0:
                qty_a = TRADE_USD_SIZE / price_a
                qty_b = TRADE_USD_SIZE / price_b
                print(f"🚨 ENTRY TRIGGER: Z-Score ({z_score:.2f}) > +2.0. SHORTING SPREAD...")
                
                exchange.create_market_sell_order(SYMBOL_A, qty_a)
                exchange.create_market_buy_order(SYMBOL_B, qty_b)
                
                current_state = 'SHORT_SPREAD'
                print(f"Position opened: SHORT {qty_a:.3f} {SYMBOL_A} & LONG {qty_b:.3f} {SYMBOL_B}")

        elif current_state == 'LONG_SPREAD':
            # EXIT TRIGGER: LONG SPREAD REVERSION (Z >= -0.5)
            if z_score >= -0.5:
                print(f"✅ EXIT TRIGGER: Z-Score ({z_score:.2f}) reverted above -0.5. Closing positions...")
                
                exchange.create_market_sell_order(SYMBOL_A, qty_a)
                exchange.create_market_buy_order(SYMBOL_B, qty_b)
                
                current_state = 'NONE'
                print("Spread position fully closed. Back to flat.")

        elif current_state == 'SHORT_SPREAD':
            # EXIT TRIGGER: SHORT SPREAD REVERSION (Z <= +0.5)
            if z_score <= 0.5:
                print(f"✅ EXIT TRIGGER: Z-Score ({z_score:.2f}) reverted below +0.5. Closing positions...")
                
                exchange.create_market_buy_order(SYMBOL_A, qty_a)
                exchange.create_market_sell_order(SYMBOL_B, qty_b)
                
                current_state = 'NONE'
                print("Spread position fully closed. Back to flat.")

        # Pause loop for 5 seconds to manage exchange rate limits
        time.sleep(5)

    except Exception as e:
        print(f"Error encountered: {e}")
        time.sleep(10)
