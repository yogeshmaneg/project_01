"""
This script tracks the change in Open Interest (OI) for NIFTY 50 options
and displays it in a live-updating table.
"""
from dhanhq import dhanhq
from dhanhq.marketfeed import DhanFeed
import asyncio
import logging
import datetime
import pandas as pd
import time
import os
import pygame
import wave
import math
import requests
import io

# Setup logging
logging.basicConfig(level=logging.INFO)

# --- Replace with your actual credentials ---
client_id = "your_client_id"
access_token = "your_access_token"
# ---

# Check for placeholder credentials and exit if they are not changed.
if client_id == "your_client_id" or access_token == "your_access_token":
    print("="*80)
    print("!!! ACTION REQUIRED !!!")
    print("Please edit the 'oi_tracker.py' file and replace the placeholder")
    print("credentials with your actual DhanHQ Client ID and Access Token.")
    print("="*80)
    exit()

# --- Sound Generation ---
def generate_alert_sound(filename="alert.wav", duration=0.5, frequency=1000):
    """Generates a simple sine wave and saves it as a WAV file."""
    if os.path.exists(filename):
        return

    sample_rate = 44100
    n_samples = int(duration * sample_rate)
    amplitude = 16000

    with wave.open(filename, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)

        for i in range(n_samples):
            value = int(amplitude * math.sin(2 * math.pi * frequency * i / sample_rate))
            wf.writeframes(value.to_bytes(2, byteorder='little', signed=True))
# ---

# Initialize Pygame Mixer
try:
    pygame.mixer.init()
except pygame.error as e:
    logging.warning(f"Pygame mixer could not be initialized: {e}. Audio alerts will be disabled.")
    pygame = None

# Generate the alert sound file
generate_alert_sound()

# Initialize DhanHQ
dhan = dhanhq(client_id, access_token)


# Verify connection
try:
    positions = dhan.get_positions()
    logging.info(f"Successfully connected.")
except Exception as e:
    logging.error(f"Authentication failed: {e}")
    exit()

# Fetch instruments
try:
    # Note: If you encounter an SSL: CERTIFICATE_VERIFY_FAILED error,
    # it is likely due to an issue with your local Python environment's SSL certificates.
    # The secure solution is to update your system's certificate store.
    # For more details, see: https://stackoverflow.com/questions/27835619/urllib-and-ssl-certificate-verify-failed-error
    url = "https://images.dhan.co/api-data/api-scrip-master.csv"
    response = requests.get(url)
    response.raise_for_status()
    instruments_df = pd.read_csv(io.StringIO(response.text), low_memory=False)
    logging.info("Successfully fetched instruments.")
except requests.exceptions.SSLError as e:
    logging.error(f"SSL Certificate Error: {e}")
    logging.error("This is likely an issue with your local environment's SSL certificates.")
    logging.error("Please see the note in the script's source code for more information.")
    exit()
except requests.exceptions.RequestException as e:
    logging.error(f"Failed to download instruments file: {e}")
    exit()
except Exception as e:
    logging.error(f"Failed to process instruments file: {e}")
    exit()

# --- Configuration ---
underlying_instrument = "NIFTY 50"
underlying_exchange = "NSE"
strike_interval = 50
# ---

def get_atm_strike():
    """Fetches the LTP of the underlying instrument and determines the ATM strike."""
    try:
        nifty_instrument = instruments_df[
            (instruments_df['SM_SYMBOL_NAME'] == 'NIFTY') &
            (instruments_df['SEM_INSTRUMENT_NAME'] == 'INDEX')
        ]
        if nifty_instrument.empty:
            logging.error("NIFTY 50 instrument not found.")
            return None

        nifty_security_id = str(nifty_instrument.iloc[0]['SEM_SMST_SECURITY_ID'])

        # Using the REST API for fetching LTP
        securities = {"IDX_I": [nifty_security_id]}
        ltp_data = dhan.ticker_data(securities)

        if ltp_data and ltp_data['status'] == 'success':
            data = ltp_data['data']
            if 'IDX_I' in data and data['IDX_I']:
                ltp = data['IDX_I'][0]['last_price']
                atm_strike = round(ltp / strike_interval) * strike_interval
                logging.info(f"LTP for {underlying_instrument}: {ltp}, ATM Strike: {atm_strike}")
                return atm_strike

        logging.error(f"Failed to get LTP. Response: {ltp_data}")
        return None
    except Exception as e:
        logging.error(f"Failed to get LTP and determine ATM strike: {e}")
        return None

# Get the ATM strike
atm_strike = get_atm_strike()
if not atm_strike:
    exit()

def get_option_contracts(atm_strike, num_strikes=2):
    """
    Finds the security IDs for the ATM, ITM, and OTM options for the nearest expiry.
    """
    nifty_options = instruments_df[
        (instruments_df['SEM_INSTRUMENT_NAME'] == 'OPTIDX') &
        (instruments_df['SM_SYMBOL_NAME'] == 'NIFTY')
    ].copy()

    nifty_options['SEM_EXPIRY_DATE'] = pd.to_datetime(nifty_options['SEM_EXPIRY_DATE'])

    # Find the nearest expiry date
    expiries = sorted(nifty_options['SEM_EXPIRY_DATE'].unique())
    nearest_expiry = expiries[0]
    logging.info(f"Nearest expiry date: {nearest_expiry.date()}")

    # Select the strikes
    strikes = [atm_strike + i * strike_interval for i in range(-num_strikes, num_strikes + 1)]

    selected_contracts = {"calls": {}, "puts": {}}
    for strike in strikes:
        for opt_type in ["CE", "PE"]:
            contract = nifty_options[
                (nifty_options['SEM_STRIKE_PRICE'] == strike) &
                (nifty_options['SEM_OPTION_TYPE'] == opt_type) &
                (nifty_options['SEM_EXPIRY_DATE'] == nearest_expiry)
            ]
            if not contract.empty:
                security_id = str(contract.iloc[0]['SEM_SMST_SECURITY_ID'])
                if opt_type == "CE":
                    selected_contracts["calls"][strike] = security_id
                else:
                    selected_contracts["puts"][strike] = security_id

    return selected_contracts

# Get the option contracts
option_contracts = get_option_contracts(atm_strike)
if not option_contracts["calls"] or not option_contracts["puts"]:
    logging.error("Could not find all the required option contracts.")
    exit()

logging.info(f"Selected call contracts: {option_contracts['calls']}")
logging.info(f"Selected put contracts: {option_contracts['puts']}")

def get_historical_oi(security_id, interval='1', lookback_period=30):
    """Fetches historical OI data for a given security ID."""
    to_date = datetime.datetime.now()
    from_date = to_date - datetime.timedelta(minutes=lookback_period)

    try:
        data = dhan.intraday_daily_data(
            security_id=security_id,
            exchange_segment='NSE_FNO',
            instrument_type='OPTIDX',
            interval=interval,
            from_date=from_date.strftime('%Y-%m-%d'),
            to_date=to_date.strftime('%Y-%m-%d')
        )

        if data['status'] == 'success':
            df = pd.DataFrame({
                'date': pd.to_datetime(data['data']['timestamp'], unit='s'),
                'oi': data['data']['open_interest']
            })
            return df
        else:
            logging.error(f"Failed to fetch historical data for {security_id}: {data['errorMessage']}")
            return pd.DataFrame()

    except Exception as e:
        logging.error(f"Failed to fetch historical data for {security_id}: {e}")
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
    """Plays an alert sound if pygame is available."""
    if pygame:
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
