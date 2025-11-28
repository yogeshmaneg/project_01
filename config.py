# DhanHQ API Credentials
CLIENT_ID = "YOUR_CLIENT_ID"
ACCESS_TOKEN = "YOUR_ACCESS_TOKEN"

# Trading Parameters
INDICES = {
    "NIFTY_50": {
        "security_id": "13",
        "exchange": "NSE_FNO"
    },
    "BANK_NIFTY": {
        "security_id": "25",
        "exchange": "NSE_FNO"
    },
    "SENSEX": {
        "security_id": "51",
        "exchange": "BSE_FNO"
    }
}
TIMEFRAMES = [1, 5]  # Timeframes in minutes to analyze

# Strategy Parameters
SUPERTREND_PERIOD = 10
SUPERTREND_MULTIPLIER = 3
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
RSI_BUY_THRESHOLD = 50
RSI_SELL_THRESHOLD = 50

# Risk Management
STOP_LOSS_PERCENT = 0.10  # 10%
TAKE_PROFIT_PERCENT = 0.20  # 20%

# Options Selection
OPTION_STRIKE_DISTANCE = 1  # +1 OTM
OPTION_EXPIRY_TYPE = "WEEKLY"  # "WEEKLY" or "MONTHLY"
