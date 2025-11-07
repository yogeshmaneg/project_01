"""
This script tracks the change in Open Interest (OI) for NIFTY 50 options
and displays it in a live-updating table.
"""
from kiteconnect import KiteConnect
import logging
import datetime
import pandas as pd
import time
import os
import pygame

# Setup logging
logging.basicConfig(level=logging.INFO)

# --- Replace with your actual credentials ---
api_key = "your_api_key"
api_secret = "your_api_secret"
request_token = "your_request_token"
# ---

# Initialize Pygame Mixer
pygame.mixer.init()

# Initialize KiteConnect
kite = KiteConnect(api_key=api_key)

# Generate session
try:
    data = kite.generate_session(request_token, api_secret=api_secret)
    kite.set_access_token(data["access_token"])
    logging.info("Successfully generated session.")
except Exception as e:
    logging.error(f"Session generation failed: {e}")
    # In a real application, you would handle this by redirecting the user to the login URL
    # print(f"Login URL: {kite.login_url()}")
    # For this script, we'll exit if session generation fails
    exit()

# Fetch instruments
try:
    instruments = kite.instruments("NFO")
    logging.info("Successfully fetched instruments.")
except Exception as e:
    logging.error(f"Failed to fetch instruments: {e}")
    exit()

# --- Configuration ---
underlying_instrument = "NIFTY 50"
underlying_exchange = "NSE"
strike_interval = 50
# ---

def get_atm_strike():
    """Fetches the LTP of the underlying instrument and determines the ATM strike."""
    try:
        ltp_data = kite.ltp(f"{underlying_exchange}:{underlying_instrument}")
        ltp = ltp_data[f"{underlying_exchange}:{underlying_instrument}"]["last_price"]
        atm_strike = round(ltp / strike_interval) * strike_interval
        logging.info(f"LTP for {underlying_instrument}: {ltp}, ATM Strike: {atm_strike}")
        return atm_strike
    except Exception as e:
        logging.error(f"Failed to get LTP and determine ATM strike: {e}")
        return None

# Get the ATM strike
atm_strike = get_atm_strike()
if not atm_strike:
    exit()

def get_option_contracts(atm_strike, num_strikes=2):
    """
    Finds the instrument tokens for the ATM, ITM, and OTM options for the nearest expiry.
    """
    nifty_options = [
        ins for ins in instruments
        if ins["name"] == "NIFTY" and ins["segment"] == "NFO-OPT"
    ]

    # Find the nearest expiry date
    expiries = sorted(list(set(ins["expiry"] for ins in nifty_options)))
    nearest_expiry = expiries[0]
    logging.info(f"Nearest expiry date: {nearest_expiry}")

    # Select the strikes
    strikes = [atm_strike + i * strike_interval for i in range(-num_strikes, num_strikes + 1)]

    selected_contracts = {"calls": {}, "puts": {}}
    for strike in strikes:
        for opt_type in ["CE", "PE"]:
            contract_name = f"NIFTY{nearest_expiry.strftime('%y%b').upper()}{strike}{opt_type}"
            contract = next((ins for ins in nifty_options if ins["tradingsymbol"].startswith(f"NIFTY") and ins["strike"] == strike and ins["instrument_type"] == opt_type and ins["expiry"] == nearest_expiry), None)
            if contract:
                if opt_type == "CE":
                    selected_contracts["calls"][strike] = contract["instrument_token"]
                else:
                    selected_contracts["puts"][strike] = contract["instrument_token"]

    return selected_contracts

# Get the option contracts
option_contracts = get_option_contracts(atm_strike)
if not option_contracts["calls"] or not option_contracts["puts"]:
    logging.error("Could not find all the required option contracts.")
    exit()

logging.info(f"Selected call contracts: {option_contracts['calls']}")
logging.info(f"Selected put contracts: {option_contracts['puts']}")

def get_historical_oi(instrument_token, interval='minute', lookback_period=30):
    """Fetches historical OI data for a given instrument token."""
    to_date = datetime.datetime.now()
    from_date = to_date - datetime.timedelta(minutes=lookback_period)

    try:
        data = kite.historical_data(instrument_token, from_date, to_date, interval, oi=True)
        return pd.DataFrame(data)
    except Exception as e:
        logging.error(f"Failed to fetch historical data for {instrument_token}: {e}")
        return pd.DataFrame()

def create_oi_tables():
    """Creates two pandas DataFrames to store the OI data for calls and puts."""
    strikes = sorted(option_contracts["calls"].keys())
    columns = ["10 mins", "15 mins", "30 mins"]

    call_oi_table = pd.DataFrame(index=strikes, columns=columns)
    put_oi_table = pd.DataFrame(index=strikes, columns=columns)

    return call_oi_table, put_oi_table

# Create the OI tables
call_oi_table, put_oi_table = create_oi_tables()

def calculate_oi_change(historical_data, interval):
    """Calculates the percentage OI change for a given interval."""
    if historical_data.empty:
        return None

    now = datetime.datetime.now().replace(second=0, microsecond=0)
    interval_time = now - datetime.timedelta(minutes=interval)

    # Find the closest data point to the interval time
    historical_data['date'] = pd.to_datetime(historical_data['date']).dt.round('min')

    initial_data = historical_data.iloc[(historical_data['date'] - interval_time).abs().argsort()[:1]]

    if initial_data.empty:
        return None

    initial_oi = initial_data["oi"].iloc[0]
    current_oi = historical_data["oi"].iloc[-1]

    if initial_oi == 0:
        return float('inf')  # Handle division by zero

    return ((current_oi - initial_oi) / initial_oi) * 100

def update_oi_tables():
    """Fetches the latest OI data and updates the tables."""
    for strike, token in option_contracts["calls"].items():
        hist_data = get_historical_oi(token)
        if not hist_data.empty:
            call_oi_table.loc[strike, "10 mins"] = calculate_oi_change(hist_data, 10)
            call_oi_table.loc[strike, "15 mins"] = calculate_oi_change(hist_data, 15)
            call_oi_table.loc[strike, "30 mins"] = calculate_oi_change(hist_data, 30)

    for strike, token in option_contracts["puts"].items():
        hist_data = get_historical_oi(token)
        if not hist_data.empty:
            put_oi_table.loc[strike, "10 mins"] = calculate_oi_change(hist_data, 10)
            put_oi_table.loc[strike, "15 mins"] = calculate_oi_change(hist_data, 15)
            put_oi_table.loc[strike, "30 mins"] = calculate_oi_change(hist_data, 30)

def play_alert_sound():
    """Plays an alert sound. A valid 'alert.wav' file is required."""
    try:
        pygame.mixer.music.load("alert.wav")
        pygame.mixer.music.play()
    except Exception as e:
        logging.warning(f"Could not play alert sound: {e}. Make sure 'alert.wav' is a valid sound file.")

def check_and_play_alert(call_table, put_table):
    """Checks if more than 50% of the cells are color-coded and plays an alert."""
    total_cells = call_table.size + put_table.size
    if total_cells == 0:
        return

    colored_cells = 0

    thresholds = {"10 mins": 10, "15 mins": 15, "30 mins": 25}

    for table in [call_table, put_table]:
        for _, row in table.iterrows():
            for col_name, cell_value in row.items():
                if isinstance(cell_value, (int, float)):
                    if cell_value > thresholds.get(col_name, 0):
                        colored_cells += 1

    logging.info(f"Colored cells: {colored_cells}/{total_cells}")
    if (colored_cells / total_cells) > 0.5:
        logging.info("Alert condition met. Playing sound.")
        play_alert_sound()

def print_colored_table(table, title):
    """Prints the OI table with color coding to the console."""
    print(f"--- {title} ---")

    RED = '\033[91m'
    RESET = '\033[0m'

    header = f"{'Strike':<10}" + "".join([f"{col:<15}" for col in table.columns])
    print(header)
    print("-" * len(header))

    thresholds = {"10 mins": 10, "15 mins": 15, "30 mins": 25}

    for index, row in table.iterrows():
        row_str = f"{index:<10}"
        for col_name, cell_value in row.items():
            val_str = f"{cell_value:.2f}%" if isinstance(cell_value, (int, float)) else "N/A"

            if isinstance(cell_value, (int, float)) and cell_value > thresholds.get(col_name, 0):
                colored_val_str = f"{RED}{val_str}{RESET}"
                row_str += f"{colored_val_str:<24}" # Adjust for invisible ANSI chars
            else:
                row_str += f"{val_str:<15}"
        print(row_str)
    print("\n")


if __name__ == "__main__":
    while True:
        try:
            update_oi_tables()

            os.system('cls' if os.name == 'nt' else 'clear')

            print("--- OI Tracker ---")
            print(f"Last updated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print_colored_table(call_oi_table, "CALL OI Change (%)")
            print_colored_table(put_oi_table, "PUT OI Change (%)")

            check_and_play_alert(call_oi_table, put_oi_table)

            time.sleep(60)
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            logging.error(f"An unexpected error occurred: {e}")
            time.sleep(60)
