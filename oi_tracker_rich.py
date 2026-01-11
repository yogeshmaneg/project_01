# Script to track option OI changes
# This script connects to the DhanHQ API, fetches NFO option chain data for a specified underlying,
# calculates Open Interest (OI) changes over various intervals, and displays this information
# in live-updating tables in the console.

import logging
import os
import sys  # For sys.exit() for critical error handling
import time # For time.sleep() in the live update loop
from dhanhq import dhanhq
import pandas as pd
import requests
import io
from datetime import datetime, date, timedelta, timezone
import pygame
import wave
import math

# Rich library imports for enhanced terminal output
from rich.console import Console, Group
from rich.table import Table
from rich.live import Live
from rich.text import Text
from rich.panel import Panel

# ==============================================================================
# --- SCRIPT CONFIGURATION ---
# ==============================================================================
# Instructions for API Keys:
# 1. Set Environment Variables:
#    For Linux/macOS:
#      export KITE_API_KEY="your_api_key"
#      export KITE_API_SECRET="your_api_secret"
#    For Windows (PowerShell):
#      $env:KITE_API_KEY="your_api_key"
#      $env:KITE_API_SECRET="your_api_secret"
#    Replace "your_api_key" and "your_api_secret" with your actual Kite API credentials.
# 2. Alternatively, you can hardcode them below by changing API_KEY_DEFAULT and
#    API_SECRET_DEFAULT, but using environment variables is recommended for security.

# --- API Credentials ---
CLIENT_ID = "YOUR_CLIENT_ID"            # Replace with your DhanHQ Client ID
ACCESS_TOKEN = "YOUR_ACCESS_TOKEN"      # Replace with your DhanHQ Access Token

# --- Trading Parameters ---
# -- NIFTY Parameters --
UNDERLYING_SYMBOL = "NIFTY 50"       # Underlying instrument (e.g., "NIFTY 50", "BANKNIFTY")
STRIKE_DIFFERENCE = 50               # Difference between consecutive strikes (50 for NIFTY, 100 for BANKNIFTY)
OPTIONS_COUNT = 2                    # Number of ITM/OTM strikes to fetch on each side of ATM (e.g., 2 means 2 ITM, 1 ATM, 2 OTM = 5 levels total)

# --- Trading Parameters ---
# --  BANKNIFTY Parameters --
# UNDERLYING_SYMBOL = "BANKNIFTY"
# STRIKE_DIFFERENCE = 100
# OPTIONS_COUNT = 5



# --- Data Fetching Parameters ---
HISTORICAL_DATA_MINUTES = 40         # How many minutes of historical data to fetch for OI calculation
OI_CHANGE_INTERVALS_MIN = (5, 10, 15, 30) # Past intervals (in minutes) to calculate OI change from latest OI

# --- Display and Logging ---
REFRESH_INTERVAL_SECONDS = 60        # How often to refresh the data and tables (in seconds)
LOG_FILE_NAME = "oi_tracker.log"     # Name of the log file
FILE_LOG_LEVEL = "DEBUG, INFO"              # Logging level for the log file (DEBUG, INFO, WARNING, ERROR, CRITICAL)
PCT_CHANGE_THRESHOLDS = {            # Thresholds for highlighting OI % change (interval_in_min: percentage)
     5: 8.0,
    10: 10.0,  # Highlight if 10-min % change > 10%
    15: 15.0,  # Highlight if 15-min % change > 15%
    30: 25.0   # Highlight if 30-min % change > 25%
}

# Note: Console output is managed by Rich; file logging captures more detailed/background info.

# ==============================================================================
# --- SOUND GENERATION ---
# ==============================================================================
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

# ==============================================================================
# --- END OF CONFIGURATION ---
# ==============================================================================

# --- Global Initializations ---
# Setup file logging according to configured level and file name
logging.basicConfig(
    level=getattr(logging, FILE_LOG_LEVEL.upper(), logging.INFO),
    format='%(asctime)s - %(levelname)s - %(module)s - %(message)s',
    filename=LOG_FILE_NAME,
    filemode='a'  # Append to the log file
)

try:
    pygame.mixer.init()
except pygame.error as e:
    logging.warning(f"Pygame mixer could not be initialized: {e}. Audio alerts will be disabled.")
    pygame = None

generate_alert_sound()

# Derive underlying prefix (e.g., NIFTY from "NIFTY 50") for instrument searching

now = datetime.now()
current_year_two_digits = now.strftime("%y")
UNDERLYING_PREFIX = UNDERLYING_SYMBOL.split(" ")[0].upper()

# Global DhanHQ and Rich Console instances
dhan = dhanhq(CLIENT_ID, ACCESS_TOKEN)
console = Console() # For Rich text and table display


# --- Core Functions ---

def get_atm_strike(dhan_obj: dhanhq, underlying_sym: str, strike_diff: int, instruments_df: pd.DataFrame):
    """
    Fetches the Last Traded Price (LTP) for the underlying symbol and calculates the At-The-Money (ATM) strike.

    Args:
        dhan_obj: Initialized dhanhq object.
        underlying_sym: The underlying symbol (e.g., "NIFTY 50").
        strike_diff: The difference between consecutive option strikes.
        instruments_df: DataFrame containing the instrument master list.

    Returns:
        The calculated ATM strike as a float, or None if LTP cannot be fetched or an error occurs.
    """
    try:
        # Find the NIFTY 50 index instrument to get its security ID
        nifty_instrument = instruments_df[
            (instruments_df['SM_SYMBOL_NAME'] == 'NIFTY') &
            (instruments_df['SEM_INSTRUMENT_NAME'] == 'INDEX')
        ]
        if nifty_instrument.empty:
            logging.error("NIFTY 50 instrument not found in the master file.")
            return None

        nifty_security_id = int(nifty_instrument.iloc[0]['SEM_SMST_SECURITY_ID'])

        # Fetch LTP using DhanHQ's ticker_data
        securities = {"IDX_I": [nifty_security_id]}
        ltp_data = dhan_obj.ticker_data(securities)

        # Validate LTP data structure
        if ltp_data and ltp_data['status'] == 'success' and 'data' in ltp_data and 'IDX_I' in ltp_data['data'] and ltp_data['data']['IDX_I']:
            ltp = ltp_data['data']['IDX_I'][0]['last_price']
            # Calculate ATM strike by rounding LTP to the nearest strike difference
            atm_strike = round(ltp / strike_diff) * strike_diff
            logging.debug(f"LTP for {underlying_sym}: {ltp}, Calculated ATM strike: {atm_strike}")
            return atm_strike
        else:
            logging.error(f"LTP data not found or incomplete. Response: {ltp_data}")
            return None
    except Exception as e:
        logging.error(f"Error in get_atm_strike for {underlying_sym}: {e}", exc_info=True)
        return None

def get_nearest_expiries(instruments_df: pd.DataFrame, underlying_prefix_str: str):
    """
    Finds the nearest weekly and monthly expiries for the given underlying symbol.

    Args:
        instruments_df: DataFrame of instruments from DhanHQ.
        underlying_prefix_str: The prefix of the underlying symbol (e.g., "NIFTY").

    Returns:
        A dictionary with 'weekly' and 'monthly' expiry dates, or None if not found.
    """
    today = datetime.now().date()

    nifty_options = instruments_df[
        (instruments_df['SEM_INSTRUMENT_NAME'] == 'OPTIDX') &
        (instruments_df['SM_SYMBOL_NAME'] == underlying_prefix_str)
    ].copy()

    if nifty_options.empty:
        logging.error(f"No options found for {underlying_prefix_str}.")
        return None

    nifty_options['SEM_EXPIRY_DATE'] = pd.to_datetime(nifty_options['SEM_EXPIRY_DATE']).dt.date

    future_expiries = sorted(nifty_options[nifty_options['SEM_EXPIRY_DATE'] >= today]['SEM_EXPIRY_DATE'].unique())

    if not future_expiries:
        logging.error(f"No future expiries found for {underlying_prefix_str}.")
        return None

    nearest_weekly = None
    nearest_monthly = None

    # Find nearest weekly (first expiry is always the nearest weekly)
    if future_expiries:
        nearest_weekly = future_expiries[0]

    # Find nearest monthly
    for expiry in future_expiries:
        month = expiry.month
        year = expiry.year
        # Get the last day of the month
        last_day = date(year, month, 1) + timedelta(days=31)
        last_day = last_day.replace(day=1) - timedelta(days=1)

        # Find the last Thursday of the month
        last_thursday = last_day
        while last_thursday.weekday() != 3: # 3 is Thursday
            last_thursday -= timedelta(days=1)

        if expiry == last_thursday.date():
            nearest_monthly = expiry
            break

    # If nearest monthly is the same as nearest weekly, find the next monthly
    if nearest_monthly == nearest_weekly:
        for expiry in future_expiries:
            if expiry > nearest_monthly:
                month = expiry.month
                year = expiry.year
                last_day = date(year, month, 1) + timedelta(days=31)
                last_day = last_day.replace(day=1) - timedelta(days=1)
                last_thursday = last_day
                while last_thursday.weekday() != 3:
                    last_thursday -= timedelta(days=1)
                if expiry == last_thursday.date():
                    nearest_monthly = expiry
                    break

    expiries = {'weekly': nearest_weekly, 'monthly': nearest_monthly}
    logging.info(f"Nearest expiries found: Weekly -> {expiries['weekly']}, Monthly -> {expiries['monthly']}")
    return expiries

def get_relevant_option_details(instruments_df: pd.DataFrame, atm_strike_val: float, expiry_dt: date,
                                strike_diff_val: int, opt_count: int, underlying_prefix_str: str):
    """
    Identifies relevant ITM, ATM, and OTM Call/Put option contract details (security_id, tradingsymbol, strike)
    for a given ATM strike and expiry date from the DhanHQ instrument DataFrame.

    Args:
        instruments_df: DataFrame of all instruments.
        atm_strike_val: The current At-The-Money strike.
        expiry_dt: The expiry date for the options.
        strike_diff_val: The difference between option strikes.
        opt_count: Number of ITM/OTM strikes to fetch on each side of ATM.
        underlying_prefix_str: The prefix of the underlying (e.g., "NIFTY").

    Returns:
        A dictionary where keys are like "atm_ce", "itm1_pe", etc., and values are
        dictionaries containing 'security_id', 'tradingsymbol', and 'strike'.
        Returns an empty dictionary if critical inputs are missing.
    """
    relevant_options = {}
    if not expiry_dt or atm_strike_val is None:
        logging.error("Expiry date or ATM strike is None, cannot fetch option details.")
        return relevant_options

    logging.debug(f"Searching for options with expiry: {expiry_dt}, ATM strike: {atm_strike_val}")

    # Filter for NIFTY options with the correct expiry date
    nifty_options = instruments_df[
        (instruments_df['SEM_INSTRUMENT_NAME'] == 'OPTIDX') &
        (instruments_df['SM_SYMBOL_NAME'] == underlying_prefix_str) &
        (pd.to_datetime(instruments_df['SEM_EXPIRY_DATE']).dt.date == expiry_dt)
    ].copy()

    # Iterate from -opt_count to +opt_count to cover all required strikes
    for i in range(-opt_count, opt_count + 1):
        current_strike = atm_strike_val + (i * strike_diff_val)

        # Find CE and PE contracts for the current strike
        ce_contract = nifty_options[
            (nifty_options['SEM_STRIKE_PRICE'] == current_strike) &
            (nifty_options['SEM_OPTION_TYPE'] == 'CE')
        ]
        pe_contract = nifty_options[
            (nifty_options['SEM_STRIKE_PRICE'] == current_strike) &
            (nifty_options['SEM_OPTION_TYPE'] == 'PE')
        ]

        # Determine key suffix (atm, itm1, otm1, etc.)
        if i == 0: key_suffix = "atm"
        elif i < 0: key_suffix = f"itm{-i}"
        else: key_suffix = f"otm{i}"

        if not ce_contract.empty:
            relevant_options[f"{key_suffix}_ce"] = {
                'security_id': str(ce_contract.iloc[0]['SEM_SMST_SECURITY_ID']),
                'tradingsymbol': ce_contract.iloc[0]['SM_TRADING_SYMBOL'],
                'strike': current_strike
            }
        else:
            logging.warning(f"CE option not found for strike {current_strike}, expiry {expiry_dt}")

        if not pe_contract.empty:
            relevant_options[f"{key_suffix}_pe"] = {
                'security_id': str(pe_contract.iloc[0]['SEM_SMST_SECURITY_ID']),
                'tradingsymbol': pe_contract.iloc[0]['SM_TRADING_SYMBOL'],
                'strike': current_strike
            }
        else:
            logging.warning(f"PE option not found for strike {current_strike}, expiry {expiry_dt}")

    logging.debug(f"Relevant option details identified: {len(relevant_options)} contracts.")
    return relevant_options

def fetch_historical_oi_data(dhan_obj: dhanhq, option_details_dict: dict,
                             minutes_of_data: int = HISTORICAL_DATA_MINUTES):
    """
    Fetches historical OI data (minute interval) for the provided option contracts using DhanHQ API.

    Args:
        dhan_obj: Initialized dhanhq object.
        option_details_dict: Dictionary of option contracts (from get_relevant_option_details).
        minutes_of_data: The duration in minutes for which to fetch historical data.

    Returns:
        A dictionary where keys are option keys (e.g., "atm_ce") and values are lists
        of historical candle data (each candle is a dict). Returns empty list for a contract on error.
    """
    historical_oi_store = {}
    if not option_details_dict:
        logging.warning("No option details provided to fetch_historical_oi_data.")
        return historical_oi_store

    # Calculate date range for historical data API call
    to_date = datetime.now()
    from_date = to_date - timedelta(minutes=minutes_of_data)

    logging.debug(f"Fetching historical data from {from_date.strftime('%Y-%m-%d')} to {to_date.strftime('%Y-%m-%d')}")

    for option_key, details in option_details_dict.items():
        security_id = details.get('security_id')
        tradingsymbol = details.get('tradingsymbol')

        if not security_id:
            logging.warning(f"Missing security_id for {option_key} ({tradingsymbol}). Skipping historical data fetch.")
            historical_oi_store[option_key] = []
            continue

        try:
            logging.debug(f"Fetching historical OI for {tradingsymbol} (ID: {security_id})")
            data = dhan_obj.intraday_daily_data(
                security_id=security_id,
                exchange_segment='NSE_FNO',
                instrument_type='OPTIDX',
                from_date=from_date.strftime('%Y-%m-%d'),
                to_date=to_date.strftime('%Y-%m-%d')
            )

            if data['status'] == 'success':
                df = pd.DataFrame({
                    'date': pd.to_datetime(data['data']['timestamp'], unit='s'),
                    'oi': data['data']['open_interest']
                })
                # Convert DataFrame to list of dictionaries to maintain compatibility with the rest of the script
                historical_oi_store[option_key] = df.to_dict('records')
                logging.debug(f"Fetched {len(df)} records for {tradingsymbol}")
            else:
                logging.error(f"Failed to fetch historical data for {tradingsymbol}: {data.get('errorMessage', 'Unknown error')}")
                historical_oi_store[option_key] = []
        except Exception as e:
            logging.error(f"Error fetching historical OI for {tradingsymbol} (ID: {security_id}): {e}", exc_info=True)
            historical_oi_store[option_key] = []

    return historical_oi_store

def find_oi_at_timestamp(historical_candles: list, target_time: datetime,
                          latest_oi_and_time: tuple):
    """
    Finds Open Interest (OI) at or just before a specific target_time from a list of historical candles.
    The historical_candles are assumed to be sorted oldest to newest.

    Args:
        historical_candles: List of candle dictionaries (containing 'date' and 'oi').
        target_time: The target datetime object to find OI for.
        latest_oi_and_time: Optional tuple (latest_oi, latest_timestamp). If provided, ensures
                            that the selected candle is not later than this latest_timestamp.

    Returns:
        The Open Interest (int) at the target time, or None if no suitable candle is found.
    """
    if not historical_candles:
        return None

    # Iterate backwards through candles to find the most recent one at or before target_time
    for candle in reversed(historical_candles):
        candle_time = candle['date']

        if candle_time <= target_time:
            if latest_oi_and_time and candle_time > latest_oi_and_time[1]:
                continue
            return candle.get('oi')

    return None

def calculate_oi_differences(raw_historical_data_store: dict, intervals_min: tuple):
    """
    Calculates OI differences between the latest OI and OI at specified past intervals.

    Args:
        raw_historical_data_store: Dictionary of historical candle data for various option contracts.
        intervals_min: A tuple of time intervals in minutes for which to calculate OI change.

    Returns:
        A dictionary structured by option_key, containing 'latest_oi', 'latest_oi_timestamp',
        and 'diff_Xm' for each interval X.
    """
    oi_differences_report = {}
    current_processing_time = datetime.now()
    logging.debug(f"Calculating OI differences based on current time: {current_processing_time.strftime('%Y-%m-%d %H:%M:%S')}")

    for option_key, candles_list in raw_historical_data_store.items():
        oi_differences_report[option_key] = {}

        latest_oi, latest_oi_timestamp = None, None
        if candles_list:
            # Candles are sorted oldest to newest by API; the last one is the latest.
            latest_candle = candles_list[-1]
            latest_oi = latest_candle.get('oi')
            latest_oi_timestamp = latest_candle.get('date') # This is a datetime object

        oi_differences_report[option_key]['latest_oi'] = latest_oi
        oi_differences_report[option_key]['latest_oi_timestamp'] = latest_oi_timestamp

        # If latest_oi is None (e.g., no data for the contract), cannot calculate differences
        if latest_oi is None:
            for interval in intervals_min:
                oi_differences_report[option_key][f'abs_diff_{interval}m'] = None
                oi_differences_report[option_key][f'pct_diff_{interval}m'] = None
            continue # Move to the next option contract

        # Calculate OI at different past intervals
        for interval in intervals_min:
            target_past_time = current_processing_time - timedelta(minutes=interval)

            past_oi = find_oi_at_timestamp(
                candles_list,
                target_past_time,
                latest_oi_and_time=(latest_oi, latest_oi_timestamp) # Pass current latest OI info
            )

            abs_oi_diff = None
            pct_oi_change = None
            if past_oi is not None:
                abs_oi_diff = latest_oi - past_oi
                if past_oi != 0: # Avoid division by zero for percentage change
                    pct_oi_change = (abs_oi_diff / past_oi) * 100
                # else: pct_oi_change remains None if past_oi is 0 but abs_oi_diff is not (Infinite change)
            else:
                logging.debug(f"Could not find past OI for {option_key} at {interval}m prior ({target_past_time.strftime('%H:%M:%S %Z')}). abs_oi_diff and pct_oi_change will be None.")

            oi_differences_report[option_key][f'abs_diff_{interval}m'] = abs_oi_diff
            oi_differences_report[option_key][f'pct_diff_{interval}m'] = pct_oi_change

    logging.debug("OI differences calculation complete.")
    return oi_differences_report

def _get_key_suffix(index_from_atm: int, total_options_one_side: int) -> str:
    """
    Helper function to determine the option key suffix (atm, itmX, otmX)
    based on the strike's index relative to the At-The-Money (ATM) strike.
    This mirrors the key generation logic in `get_relevant_option_details`.

    Args:
        index_from_atm: Integer representing the strike's position from ATM.
                        0 for ATM, negative for lower strikes, positive for higher strikes.
        total_options_one_side: Not directly used in current logic but kept for context.

    Returns:
        A string suffix like "atm", "itm1", "otm2".
    """
    if index_from_atm == 0:
        return "atm"
    elif index_from_atm < 0: # Strikes less than ATM
        return f"itm{-index_from_atm}" # e.g., index -1 is itm1
    else: # Strikes greater than ATM
        return f"otm{index_from_atm}"  # e.g., index 1 is otm1

def generate_options_tables(oi_report: dict, contract_details: dict, current_atm_strike: float,
                            strike_step: int, num_strikes_each_side: int,
                            change_intervals_list: tuple, expiry_type: str):
    """
    Generates two Rich Tables (one for Calls, one for Puts) displaying the OI analysis for a specific expiry type.

    Args:
        oi_report: Dictionary containing calculated OI data.
        contract_details: Dictionary containing details of identified option contracts.
        current_atm_strike: The current At-The-Money strike.
        strike_step: The difference between option strikes.
        num_strikes_each_side: Number of ITM/OTM strikes to display.
        change_intervals_list: Tuple of intervals for OI change columns.
        expiry_type: A string label for the expiry (e.g., "Weekly").

    Returns:
        A Rich Group object containing the Call and Put tables, or a Rich Panel with an error message.
    """
    if current_atm_strike is None:
        logging.error("Cannot generate tables: current_atm_strike is None.")
        return Panel(f"[bold red]ATM Strike could not be determined for {expiry_type} expiry. Tables cannot be generated.[/bold red]", title="Error", border_style="red")

    time_now_str = datetime.now().strftime('%H:%M:%S')

    # Create Call options table
    call_table_title = f"{expiry_type.upper()} CALL Options OI ({UNDERLYING_SYMBOL} - ATM: {int(current_atm_strike)}) @ {time_now_str}"
    call_table = Table(title=call_table_title, show_lines=True, expand=True)

    # Create Put options table
    put_table_title = f"{expiry_type.upper()} PUT Options OI ({UNDERLYING_SYMBOL} - ATM: {int(current_atm_strike)}) @ {time_now_str}"
    put_table = Table(title=put_table_title, show_lines=True, expand=True)

    # Define common columns for both tables
    cols = ["Strike", "Symbol", "Latest OI", "OI Time"]
    for interval in change_intervals_list: # Dynamically add OI change columns
        cols.append(f"OI %Chg ({interval}m)") # Updated column header

    for col_name in cols:
        call_table.add_column(col_name, justify="right")
        put_table.add_column(col_name, justify="right")

    # Iterate through strike levels relative to ATM (-num to +num)
    total_call_threshold_breached = 0
    total_call_cells = 0

    total_put_threshold_breached = 0
    total_put_cells = 0
    for i in range(-num_strikes_each_side, num_strikes_each_side + 1):
        strike_val = current_atm_strike + (i * strike_step)
        key_suffix = _get_key_suffix(i, num_strikes_each_side) # Get "atm", "itmX", "otmX"

        # --- Populate Call Option Row ---
        option_key_ce = f"{key_suffix}_ce" # e.g., "atm_ce", "itm1_ce"
        ce_data = oi_report.get(option_key_ce, {}) # Get data for this call option
        ce_contract = contract_details.get(option_key_ce, {}) # Get contract details

        ce_strike_display = str(int(ce_contract.get('strike', strike_val))) # Use actual strike from contract if available

        # Style strike price: ATM (cyan), ITM for Calls (lower strikes - green), OTM for Calls (higher strikes - red)
        ce_strike_style = "cyan" if i == 0 else ("green" if i < 0 else "red")

        ce_latest_oi = ce_data.get('latest_oi')
        ce_latest_oi_time = ce_data.get('latest_oi_timestamp')

        # Prepare row data for call table
        ce_row_data = [
            Text(ce_strike_display, style=ce_strike_style),
            ce_contract.get('tradingsymbol', 'N/A'),
            f"{ce_latest_oi:,}" if ce_latest_oi is not None else "N/A", # Format OI with comma
            ce_latest_oi_time.strftime("%H:%M:%S %Z") if ce_latest_oi_time else "N/A" # Format time
        ]

        for interval in change_intervals_list: # Add OI change values
            total_call_cells = total_call_cells+1
            pct_oi_change = ce_data.get(f'pct_diff_{interval}m')
            formatted_pct_str = f"{pct_oi_change:+.2f}%" if pct_oi_change is not None else "N/A"

            cell_text = Text(formatted_pct_str)
            if pct_oi_change is not None and interval in PCT_CHANGE_THRESHOLDS:
                if abs(pct_oi_change) > PCT_CHANGE_THRESHOLDS[interval]: # Check absolute change against threshold
                    cell_text.stylize("bold red") # Apply style if threshold exceeded
                    total_call_threshold_breached = total_call_threshold_breached+1
            ce_row_data.append(cell_text)
        call_table.add_row(*ce_row_data)

        # --- Populate Put Option Row ---
        option_key_pe = f"{key_suffix}_pe" # e.g., "atm_pe", "itm1_pe"
        pe_data = oi_report.get(option_key_pe, {}) # Get data for this put option
        pe_contract = contract_details.get(option_key_pe, {}) # Get contract details

        pe_strike_display = str(int(pe_contract.get('strike', strike_val)))

        # Style strike price: ATM (cyan), ITM for Puts (higher strikes - green), OTM for Puts (lower strikes - red)
        pe_strike_style = "cyan" if i == 0 else ("green" if i > 0 else "red")

        pe_latest_oi = pe_data.get('latest_oi')
        pe_latest_oi_time = pe_data.get('latest_oi_timestamp')

        # Prepare row data for put table
        pe_row_data = [
            Text(pe_strike_display, style=pe_strike_style),
            pe_contract.get('tradingsymbol', 'N/A'),
            f"{pe_latest_oi:,}" if pe_latest_oi is not None else "N/A",
            pe_latest_oi_time.strftime("%H:%M:%S %Z") if pe_latest_oi_time else "N/A"
        ]
        for interval in change_intervals_list: # Add OI percentage change values
            total_put_cells = total_put_cells+1
            pct_oi_change = pe_data.get(f'pct_diff_{interval}m')
            formatted_pct_str = f"{pct_oi_change:+.2f}%" if pct_oi_change is not None else "N/A"

            cell_text = Text(formatted_pct_str)
            if pct_oi_change is not None and interval in PCT_CHANGE_THRESHOLDS:
                if abs(pct_oi_change) > PCT_CHANGE_THRESHOLDS[interval]: # Check absolute change against threshold
                    cell_text.stylize("bold red") # Apply style if threshold exceeded
                    total_put_threshold_breached = total_put_threshold_breached+1
            pe_row_data.append(cell_text)
        put_table.add_row(*pe_row_data)
    if (float(total_put_threshold_breached)/float(total_put_cells) > 0.5) or (float(total_call_threshold_breached)/float(total_call_cells) > 0.5):
        play_alert_sound()


    return Group(call_table, put_table) # Group tables for simultaneous display in Live


def play_alert_sound():
    """Plays an alert sound if pygame is available."""
    if pygame:
        try:
            pygame.mixer.music.load("alert.wav")
            pygame.mixer.music.play()
        except Exception as e:
            logging.warning(f"Could not play alert sound: {e}. Make sure 'alert.wav' is a valid sound file.")

def run_analysis_iteration(dhan_obj: dhanhq, nfo_instr: pd.DataFrame, expiry_date: date, expiry_type: str):
    """
    Performs one complete iteration of fetching data, calculating differences, and generating tables for a specific expiry.

    Args:
        dhan_obj: Initialized dhanhq object.
        nfo_instr: DataFrame of all NFO instruments.
        expiry_date: The expiry date to analyze.
        expiry_type: A string label for the expiry (e.g., "Weekly").

    Returns:
        A Rich Group object containing the Call and Put tables for display,
        or a Rich Panel with an error/warning message if issues occur.
    """
    try:
        logging.debug(f"Starting new analysis iteration for {expiry_type} expiry: {expiry_date}")

        # 1. Get current ATM strike
        current_atm_strike = get_atm_strike(dhan_obj, UNDERLYING_SYMBOL, STRIKE_DIFFERENCE, nfo_instr)

        if not current_atm_strike:
            logging.error("Could not determine ATM strike for this iteration.")
            return Panel(f"[bold red]Error: Could not determine ATM strike for {expiry_type} expiry. Check logs.[/bold red]", title="Update Error", border_style="red")

        # 2. Identify relevant option contracts
        option_contract_details = get_relevant_option_details(
            nfo_instr, current_atm_strike, expiry_date,
            STRIKE_DIFFERENCE, OPTIONS_COUNT, UNDERLYING_PREFIX
        )

        # If no contracts are found (e.g., due to market close or issues with instrument list for that ATM)
        if not option_contract_details:
            logging.warning(f"Could not retrieve relevant option contracts for ATM {int(current_atm_strike)}.")
            return Panel(f"[bold yellow]Warning: Could not retrieve relevant option contracts for ATM {int(current_atm_strike)}. Waiting for next refresh.[/bold yellow]", title="Update Warning", border_style="yellow")



        # 3. Fetch historical OI data for these contracts
        raw_historical_oi_data = fetch_historical_oi_data(dhan, option_contract_details)

        # 4. Calculate OI differences
        oi_change_data = calculate_oi_differences(raw_historical_oi_data, OI_CHANGE_INTERVALS_MIN)

        # 5. Generate Rich tables for display
        table_group = generate_options_tables(
            oi_change_data, option_contract_details, current_atm_strike,
            STRIKE_DIFFERENCE, OPTIONS_COUNT, OI_CHANGE_INTERVALS_MIN, expiry_type
        )
        logging.debug(f"Analysis iteration for {expiry_type} completed successfully.")
        return table_group

    except Exception as e: # Catch any other unexpected errors during the iteration
        logging.error(f"Exception during analysis iteration: {e}", exc_info=True)
        return Panel(f"[bold red]An error occurred during data refresh: {e}. Check logs.[/bold red]", title="Update Error", border_style="red")


def fetch_instrument_master():
    """
    Downloads the DhanHQ scrip master CSV and loads it into a pandas DataFrame.
    """
    try:
        url = "https://images.dhan.co/api-data/api-scrip-master.csv"
        response = requests.get(url)
        response.raise_for_status()
        instruments_df = pd.read_csv(io.StringIO(response.text), low_memory=False)
        instruments_df.to_excel("api-scrip-master.xlsx", index=False)
        return instruments_df
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to download instruments file: {e}")
        return None
    except Exception as e:
        logging.error(f"Failed to process instruments file: {e}")
        return None

def main():
    """
    Main function to run the OI Tracker script.
    Handles initial setup (API connection, instrument fetching) and then enters the live update loop.
    """
    console.print(f"[bold blue]Starting OI Tracker Script (Log file: {LOG_FILE_NAME})[/bold blue]")

    # Check for placeholder credentials and exit if they are not changed.
    if CLIENT_ID == "YOUR_CLIENT_ID" or ACCESS_TOKEN == "YOUR_ACCESS_TOKEN":
        console.print(Panel("[bold red]Please edit the 'oi_tracker_rich.py' file and replace the placeholder credentials with your actual DhanHQ Client ID and Access Token.[/bold red]", title="[bold yellow]ACTION REQUIRED[/bold yellow]", border_style="yellow"))
        sys.exit(1)

    try:
        # --- Initial Setup ---
        # 1. Verify Connection
        console.print("Verifying DhanHQ API connection...")
        dhan.get_positions()
        console.print("[bold green]DhanHQ API connection successful![/bold green]")

        # 2. Fetch instruments list (done once at startup)
        console.print("Fetching instruments list from DhanHQ (once)...")
        nfo_instruments = fetch_instrument_master()
        if nfo_instruments is None or nfo_instruments.empty:
            console.print(f"[bold red]Failed to fetch or process the instrument master file. Exiting.[/bold red]")
            sys.exit(1) # Critical error
        logging.info(f"Fetched {len(nfo_instruments)} instruments.")

        # 3. Determine nearest expiries (done once at startup)
        expiries = get_nearest_expiries(nfo_instruments, UNDERLYING_PREFIX)
        if not expiries or not expiries.get('weekly') or not expiries.get('monthly'):
            console.print(f"[bold red]Could not determine nearest expiries for {UNDERLYING_PREFIX}. Exiting.[/bold red]")
            sys.exit(1)

        console.print(f"Tracking weekly expiry: [bold magenta]{expiries['weekly'].strftime('%d-%b-%Y')}[/bold magenta]")
        console.print(f"Tracking monthly expiry: [bold magenta]{expiries['monthly'].strftime('%d-%b-%Y')}[/bold magenta]")

        console.print(f"Starting live updates. Refresh interval: {REFRESH_INTERVAL_SECONDS} seconds. Press Ctrl+C to exit.")
        console.print(f"Underlying: [bold cyan]{UNDERLYING_SYMBOL}[/bold cyan], Strike Difference: [bold cyan]{STRIKE_DIFFERENCE}[/bold cyan], Options Count per side: [bold cyan]{OPTIONS_COUNT}[/bold cyan]")

        # --- Live Update Loop ---
        with Live(console=console, refresh_per_second=10, auto_refresh=False) as live:
            while True:
                logging.info("Starting new live update cycle.")

                weekly_tables = run_analysis_iteration(dhan, nfo_instruments, expiries['weekly'], "Weekly")
                monthly_tables = run_analysis_iteration(dhan, nfo_instruments, expiries['monthly'], "Monthly")

                display_group = Group(weekly_tables, monthly_tables)

                live.update(display_group, refresh=True)
                logging.info(f"Live display updated. Waiting for {REFRESH_INTERVAL_SECONDS} seconds.")
                # Wait for the configured refresh interval
                time.sleep(REFRESH_INTERVAL_SECONDS)

    # Handle user interruption (Ctrl+C)
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Script terminated by user (Ctrl+C).[/bold yellow]")
        logging.info("Script terminated by user.")
    # Catch any other unexpected critical errors during the main setup
    except Exception as e:
        console.print(f"[bold red]An unexpected critical error occurred in the main setup: {e}[/bold red]")
        logging.critical(f"Unexpected critical error in main: {e}", exc_info=True)
        sys.exit(1)
    finally:
        # This block executes whether an exception occurred or not (unless sys.exit was called)
        logging.info("oi_tracker.py script execution process ended.")
        console.print("[bold blue]OI Tracker script finished.[/bold blue]")

if __name__ == "__main__":
    # Entry point of the script
    main()
