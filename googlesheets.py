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
