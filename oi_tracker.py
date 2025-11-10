import logging
import os
import sys  # For sys.exit() for critical error handling
import time  # For time.sleep() in the live update loop
from dhanhq import dhanhq
from datetime import datetime, date, timedelta, timezone
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
#        export KITE_API_KEY="your_api_key"
#        export KITE_API_SECRET="your_api_secret"
#    For Windows (PowerShell):
#        $env:KITE_API_KEY="your_api_key"
#        $env:KITE_API_SECRET="your_api_secret"
#    Replace "your_api_key" and "your_api_secret" with your actual Kite API credentials.
# 2. Alternatively, you can hardcode them below by changing API_KEY_DEFAULT and
#    API_SECRET_DEFAULT, but using environment variables is recommended for security.
# --- API Credentials ---
CLIENT_ID_DEFAULT = "YOUR_CLIENT_ID"  # Default placeholder if env var not found
ACCESS_TOKEN_DEFAULT = "YOUR_ACCESS_TOKEN"  # Default placeholder if env var not found
# --- Trading Parameters ---
# -- NIFTY Parameters --
UNDERLYING_SYMBOL = "NIFTY 50"  # Underlying instrument (e.g., "NIFTY 50", "NIFTY BANK")
STRIKE_DIFFERENCE = 50  # Difference between consecutive strikes (50 for NIFTY, 100 for BANKNIFTY)
OPTIONS_COUNT = 5  # Number of ITM/OTM strikes to fetch on each side of ATM (e.g., 2 means 2 ITM, 1 ATM, 2 OTM = 5 levels total)
# --- Exchange Configuration ---
EXCHANGE_NFO_OPTIONS = "NFO"  # Exchange for NFO options contracts
EXCHANGE_LTP = "NSE"  # Exchange for fetching LTP of the underlying (e.g., NSE for NIFTY 50)
# --- Trading Parameters ---
# -- SENSEX Parameters --
#UNDERLYING_SYMBOL = "SENSEX"  # Underlying instrument (e.g., "NIFTY 50", "NIFTY BANK")
#STRIKE_DIFFERENCE = 100  # Difference between consecutive strikes (50 for NIFTY, 100 for BANKNIFTY)
#OPTIONS_COUNT = 5  # Number of ITM/OTM strikes to fetch on each side of ATM (e.g., 2 means 2 ITM, 1 ATM, 2 OTM = 5 levels total)
# --- Exchange Configuration ---
# Use KiteConnect attributes for exchange names
#EXCHANGE_NFO_OPTIONS = KiteConnect.EXCHANGE_BFO  # Exchange for NFO options contracts
#EXCHANGE_LTP = KiteConnect.EXCHANGE_BSE  # Exchange for fetching LTP of the underlying (e.g., NSE for NIFTY 50)
# --- Data Fetching Parameters ---
HISTORICAL_DATA_MINUTES = 40  # How many minutes of historical data to fetch for OI calculation
OI_CHANGE_INTERVALS_MIN = (5, 10, 15, 30)  # Past intervals (in minutes) to calculate OI change from latest OI
# --- Display and Logging ---
REFRESH_INTERVAL_SECONDS = 60  # How often to refresh the data and tables (in seconds)
LOG_FILE_NAME = "oi_tracker.log"  # Name of the log file
FILE_LOG_LEVEL = "DEBUG, INFO"  # Logging level for the log file (DEBUG, INFO, WARNING, ERROR, CRITICAL)
PCT_CHANGE_THRESHOLDS = {  # Thresholds for highlighting OI % change (interval_in_min: percentage)
    5: 8.0,
    10: 10.0,  # Highlight if 10-min % change > 10%
    15: 15.0,  # Highlight if 15-min % change > 15%
    30: 25.0  # Highlight if 30-min % change > 25%
}
# Note: Console output is managed by Rich; file logging captures more detailed/background info.
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
# Derive underlying prefix (e.g., NIFTY from "NIFTY 50") for instrument searching
now = datetime.now()
current_year_two_digits = now.strftime("%y")
UNDERLYING_PREFIX = UNDERLYING_SYMBOL.split(" ")[0].upper()
# Retrieve API keys from environment variables or use default placeholders
client_id_to_use = os.getenv("DHAN_CLIENT_ID", CLIENT_ID_DEFAULT)
access_token_to_use = os.getenv("DHAN_ACCESS_TOKEN", ACCESS_TOKEN_DEFAULT)
# Global DhanHQ and Rich Console instances
# Initialize DhanHQ with reduced library logging to prevent console clutter from the library itself
dhan = dhanhq(client_id=client_id_to_use, access_token=access_token_to_use)
console = Console()  # For Rich text and table display
# --- Core Functions ---
def get_security_id(dhan_obj: dhanhq, underlying_sym: str):
    """
    Fetches the security ID for the underlying symbol.
    Args:
        dhan_obj: Initialized dhanhq object.
        underlying_sym: The underlying symbol (e.g., "NIFTY 50").
    Returns:
        The security ID as a string, or None if not found.
    """
    instruments = dhan_obj.fetch_security_list()
    symbol = underlying_sym.split(" ")[0].upper()
    for index, row in instruments.iterrows():
        if row['SEM_INSTRUMENT_NAME'] == 'INDEX' and row['SEM_TRADING_SYMBOL'] == symbol:
            return str(row['SEM_SECURITY_ID'])
    return None

def get_atm_strike(dhan_obj: dhanhq, security_id: str, exch_for_ltp: str, strike_diff: int):
    """
    Fetches the Last Traded Price (LTP) for the underlying symbol and calculates
    the At-The-Money (ATM) strike.
    Args:
        dhan_obj: Initialized dhanhq object.
        security_id: The security ID of the underlying instrument.
        exch_for_ltp: The exchange to fetch LTP from (e.g., "NSE").
        strike_diff: The difference between consecutive option strikes.
    Returns:
        The calculated ATM strike as a float, or None if LTP cannot be fetched or an error occurs.
    """
    try:
        ltp_data = dhan_obj.get_quotes(security_id)

        if not ltp_data or 'data' not in ltp_data or 'ltp' not in ltp_data['data']:
            logging.error(f"LTP data not found or incomplete for {underlying_sym}. Response: {ltp_data}")
            return None

        ltp = ltp_data['data']['ltp']
        # Calculate ATM strike by rounding LTP to the nearest strike difference
        atm_strike = round(ltp / strike_diff) * strike_diff
        logging.debug(f"LTP for {underlying_sym}: {ltp}, Calculated ATM strike: {atm_strike}")
        return atm_strike
    except Exception as e:
        logging.error(f"Error in get_atm_strike for {underlying_sym}: {e}", exc_info=True)
        return None
def get_nearest_weekly_expiry(dhan_obj: dhanhq, security_id: str):
    """
    Finds the nearest future weekly expiry date for the given underlying security ID.
    Args:
        dhan_obj: Initialized dhanhq object.
        security_id: The security ID of the underlying instrument.
    Returns:
        The nearest weekly expiry date as a datetime.date object, or None if no suitable expiry is found.
    """
    today = date.today()
    possible_expiries = set()
    logging.info(f"Searching for nearest weekly expiry for security ID: {security_id}.")

    expiry_data = dhan_obj.expiry_list(
        under_security_id=security_id,
        under_exchange_segment="IDX_I"
    )

    if not expiry_data or 'data' not in expiry_data or 'expiry_dates' not in expiry_data['data']:
        logging.error(f"No expiry data found for {underlying_prefix_str}.")
        return None

    for expiry in expiry_data['data']['expiry_dates']:
        expiry_date = datetime.strptime(expiry, '%Y-%m-%d').date()
        if expiry_date >= today:
            possible_expiries.add(expiry_date)

    if not possible_expiries:
        logging.error(f"No future expiries found for {underlying_prefix_str}.")
        return None

    # Sort expiries and return the closest one
    nearest_expiry = sorted(list(possible_expiries))[0]
    logging.info(f"Nearest weekly expiry for {underlying_prefix_str}: {nearest_expiry}")
    return {"expiry": nearest_expiry, "symbol_prefix": "NIFTY"} # symbol_prefix is not available from this API call.
def get_relevant_option_details(dhan_obj: dhanhq, security_id: str, atm_strike_val: float, expiry_dt: date, strike_diff_val: int, opt_count: int):
    """
    Identifies relevant ITM, ATM, and OTM Call/Put option contract details
    (tradingsymbol, instrument_token, strike) for a given ATM strike and expiry date.
    Args:
        dhan_obj: Initialized dhanhq object.
        security_id: The security ID of the underlying instrument.
        atm_strike_val: The current At-The-Money strike.
        expiry_dt: The expiry date for the options.
        strike_diff_val: The difference between option strikes.
        opt_count: Number of ITM/OTM strikes to fetch on each side of ATM.
    Returns:
        A dictionary where keys are like "atm_ce", "itm1_pe", etc., and values are
        dictionaries containing 'tradingsymbol', 'instrument_token', and 'strike'.
        Returns an empty dictionary if critical inputs are missing.
    """
    relevant_options = {}
    if not expiry_dt or atm_strike_val is None:
        logging.error("Expiry date or ATM strike is None, cannot fetch option details.")
        return relevant_options

    option_chain_data = dhan_obj.get_option_chain(security_id, expiry_dt.strftime("%Y-%m-%d"))

    if not option_chain_data or 'data' not in option_chain_data or not option_chain_data['data']:
        logging.error(f"No option chain data found for security ID {security_id} on {expiry_dt}.")
        return relevant_options

    for i in range(-opt_count, opt_count + 1):
        current_strike = atm_strike_val + (i * strike_diff_val)

        key_suffix = _get_key_suffix(i, opt_count)

        for option in option_chain_data['data']:
            if option['strikePrice'] == current_strike:
                if option['optionType'] == 'CALL':
                    relevant_options[f"{key_suffix}_ce"] = {
                        'tradingsymbol': option['displayName'],
                        'instrument_token': option['securityId'],
                        'strike': current_strike
                    }
                elif option['optionType'] == 'PUT':
                    relevant_options[f"{key_suffix}_pe"] = {
                        'tradingsymbol': option['displayName'],
                        'instrument_token': option['securityId'],
                        'strike': current_strike
                    }

    logging.debug(f"Relevant option details identified: {len(relevant_options)} contracts.")
    return relevant_options
def fetch_historical_oi_data(dhan_obj: dhanhq, option_details_dict: dict, minutes_of_data: int = HISTORICAL_DATA_MINUTES):
    """
    Fetches historical OI data (minute interval) for the provided option contracts.
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

    for option_key, details in option_details_dict.items():
        instrument_token = details.get('instrument_token')
        tradingsymbol = details.get('tradingsymbol')
        if not instrument_token:
            logging.warning(f"Missing instrument_token for {option_key} ({tradingsymbol}). Skipping historical data fetch.")
            historical_oi_store[option_key] = []  # Store empty list for consistency
            continue

        try:
            logging.debug(f"Fetching historical OI for {tradingsymbol} (Token: {instrument_token})")
            to_date = datetime.now()
            from_date = to_date - timedelta(minutes=minutes_of_data)
            data = dhan_obj.historical_minute_charts(
                security_id=instrument_token,
                exchange_segment='NFO',
                instrument_type='OPTIDX',
                from_date=from_date.strftime('%Y-%m-%d'),
                to_date=to_date.strftime('%Y-%m-%d')
            )

            if data and data.get('status') == 'success' and 'data' in data:
                # Convert the data to the expected format
                formatted_data = []
                for index, row in data['data'].iterrows():
                    formatted_data.append({
                        'date': row['start_Time'],
                        'oi': row['open_Interest']
                    })
                historical_oi_store[option_key] = formatted_data
                logging.debug(f"Fetched {len(formatted_data)} records for {tradingsymbol}")
            else:
                historical_oi_store[option_key] = []
        except Exception as e:
            logging.error(f"Error fetching historical OI for {tradingsymbol} (Token: {instrument_token}): {e}", exc_info=True)
            historical_oi_store[option_key] = []  # Store empty list on error to prevent crashes downstream
    return historical_oi_store
def find_oi_at_timestamp(historical_candles: list, target_time: datetime, latest_oi_and_time: tuple):
    """
    Finds Open Interest (OI) at or just before a specific target_time from a list of
    historical candles. The historical_candles are assumed to be sorted oldest to newest.
    Args:
        historical_candles: List of candle dictionaries (from Kite API, containing 'date' and 'oi').
        target_time: The target datetime object (timezone-aware) to find OI for.
        latest_oi_and_time: Optional tuple (latest_oi, latest_timestamp). If provided, ensures
                            that the selected candle is not later than this latest_timestamp.
                            This prevents looking "into the future" if target_time is very recent
                            and slightly ahead of the last available candle.
    Returns:
        The Open Interest (int) at the target time, or None if no suitable candle is found.
    """
    if not historical_candles:
        return None
    # Iterate backwards through candles to find the most recent one at or before target_time
    for candle in reversed(historical_candles):
        candle_time = candle['date']  # 'date' field from Kite API is already a timezone-aware datetime object
        if candle_time <= target_time:
            # If latest_oi_and_time is provided, ensure we don't pick a candle
            # whose timestamp is later than the latest_oi_timestamp from the most current data point.
            if latest_oi_and_time and candle_time > latest_oi_and_time[1]:
                continue  # This candle is too new compared to the reference latest OI point
            return candle.get('oi')

    # If loop completes, no candle was found at or before target_time (or before the first candle)
    return None
def calculate_oi_differences(raw_historical_data_store: dict, intervals_min: tuple):
    """
    Calculates OI differences between the latest OI and OI at specified past intervals.
    Args:
        raw_historical_data_store: Dictionary of historical candle data for various option contracts.
        intervals_min: A tuple of time intervals in minutes (e.g., (10, 15, 30)) for which to calculate OI change.
    Returns:
        A dictionary structured by option_key, containing 'latest_oi', 'latest_oi_timestamp',
        and 'diff_Xm' for each interval X.
    """
    oi_differences_report = {}
    # Use a consistent, timezone-aware current time for all calculations in this batch
    current_processing_time = datetime.now(timezone.utc)
    logging.debug(f"Calculating OI differences based on current time: {current_processing_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
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
            continue  # Move to the next option contract
        # Calculate OI at different past intervals
        for interval in intervals_min:
            target_past_time = current_processing_time - timedelta(minutes=interval)

            past_oi = find_oi_at_timestamp(
                candles_list,
                target_past_time,
                latest_oi_and_time=(latest_oi, latest_oi_timestamp)  # Pass current latest OI info
            )

            abs_oi_diff = None
            pct_oi_change = None
            if past_oi is not None:
                abs_oi_diff = latest_oi - past_oi
                if past_oi != 0:  # Avoid division by zero for percentage change
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
    Helper function to determine the option key suffix (atm, itmX, otmX) based on
    the strike's index relative to the At-The-Money (ATM) strike.
    This mirrors the key generation logic in get_relevant_option_details.
    Args:
        index_from_atm: Integer representing the strike's position from ATM.
                        0 for ATM, negative for lower strikes, positive for higher strikes.
        total_options_one_side: Not directly used in current logic but kept for context.
    Returns:
        A string suffix like "atm", "itm1", "otm2".
    """
    if index_from_atm == 0:
        return "atm"
    elif index_from_atm < 0:  # Strikes less than ATM
        return f"itm{-index_from_atm}"  # e.g., index -1 is itm1
    else:  # Strikes greater than ATM
        return f"otm{index_from_atm}"   # e.g., index 1 is otm1
def generate_options_tables(oi_report: dict, contract_details: dict, current_atm_strike: float, strike_step: int, num_strikes_each_side: int, change_intervals_list: tuple):
    """
    Generates two Rich Tables (one for Calls, one for Puts) displaying the OI analysis.
    If current_atm_strike is None, it returns an error Panel.
    Args:
        oi_report: Dictionary containing calculated OI data (from calculate_oi_differences).
        contract_details: Dictionary containing details of identified option contracts.
        current_atm_strike: The current At-The-Money strike. If None, an error panel is returned.
        strike_step: The difference between option strikes.
        num_strikes_each_side: Number of ITM/OTM strikes to display.
        change_intervals_list: Tuple of intervals (e.g., (10, 15, 30)) for OI change columns.
    Returns:
        A Rich Group object containing the Call and Put tables, or a Rich Panel with an error message.
    """
    if current_atm_strike is None:
        logging.error("Cannot generate tables: current_atm_strike is None.")
        return Panel("[bold red]ATM Strike could not be determined. Tables cannot be generated.[/bold red]", title="Error", border_style="red")
    time_now_str = datetime.now().strftime('%H:%M:%S')  # Timestamp for table titles
    # Create Call options table
    call_table_title = f"CALL Options OI ({UNDERLYING_SYMBOL} - ATM: {int(current_atm_strike)}) @ {time_now_str}"
    call_table = Table(title=call_table_title, show_lines=True, expand=True)
    # Create Put options table
    put_table_title = f"PUT Options OI ({UNDERLYING_SYMBOL} - ATM: {int(current_atm_strike)}) @ {time_now_str}"
    put_table = Table(title=put_table_title, show_lines=True, expand=True)
    # Define common columns for both tables
    cols = ["Strike", "Symbol", "Latest OI", "OI Time"]
    for interval in change_intervals_list:  # Dynamically add OI change columns
        cols.append(f"OI %Chg ({interval}m)")  # Updated column header
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
        key_suffix = _get_key_suffix(i, num_strikes_each_side)  # Get "atm", "itmX", "otmX"
        # --- Populate Call Option Row ---
        option_key_ce = f"{key_suffix}_ce"  # e.g., "atm_ce", "itm1_ce"
        ce_data = oi_report.get(option_key_ce, {})  # Get data for this call option
        ce_contract = contract_details.get(option_key_ce, {})  # Get contract details

        ce_strike_display = str(int(ce_contract.get('strike', strike_val)))  # Use actual strike from contract if available

        # Style strike price: ATM (cyan), ITM for Calls (lower strikes - green), OTM for Calls (higher strikes - red)
        ce_strike_style = "cyan" if i == 0 else ("green" if i < 0 else "red")

        ce_latest_oi = ce_data.get('latest_oi')
        ce_latest_oi_time = ce_data.get('latest_oi_timestamp')
        # Prepare row data for call table
        ce_row_data = [
            Text(ce_strike_display, style=ce_strike_style),
            ce_contract.get('tradingsymbol', 'N/A'),
            f"{ce_latest_oi:,}" if ce_latest_oi is not None else "N/A",  # Format OI with comma
            ce_latest_oi_time.strftime("%H:%M:%S %Z") if ce_latest_oi_time else "N/A"  # Format time
        ]
        for interval in change_intervals_list:  # Add OI change values
            total_call_cells = total_call_cells+1
            pct_oi_change = ce_data.get(f'pct_diff_{interval}m')
            formatted_pct_str = f"{pct_oi_change:+.2f}%" if pct_oi_change is not None else "N/A"

            cell_text = Text(formatted_pct_str)
            if pct_oi_change is not None and interval in PCT_CHANGE_THRESHOLDS:
                if abs(pct_oi_change) > PCT_CHANGE_THRESHOLDS[interval]:  # Check absolute change against threshold
                    cell_text.stylize("bold red")  # Apply style if threshold exceeded
                    total_call_threshold_breached = total_call_threshold_breached+1
            ce_row_data.append(cell_text)
        call_table.add_row(*ce_row_data)
        # --- Populate Put Option Row ---
        option_key_pe = f"{key_suffix}_pe"  # e.g., "atm_pe", "itm1_pe"
        pe_data = oi_report.get(option_key_pe, {})  # Get data for this put option
        pe_contract = contract_details.get(option_key_pe, {})  # Get contract details
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
        for interval in change_intervals_list:  # Add OI percentage change values
            total_put_cells = total_put_cells+1
            pct_oi_change = pe_data.get(f'pct_diff_{interval}m')
            formatted_pct_str = f"{pct_oi_change:+.2f}%" if pct_oi_change is not None else "N/A"
            cell_text = Text(formatted_pct_str)
            if pct_oi_change is not None and interval in PCT_CHANGE_THRESHOLDS:
                if abs(pct_oi_change) > PCT_CHANGE_THRESHOLDS[interval]:  # Check absolute change against threshold
                    cell_text.stylize("bold red")  # Apply style if threshold exceeded
                    total_put_threshold_breached = total_put_threshold_breached+1
            pe_row_data.append(cell_text)
        put_table.add_row(*pe_row_data)
    if (float(total_put_threshold_breached)/float(total_put_cells) > 0.5) or (float(total_call_threshold_breached)/float(total_call_cells) > 0.5):
        os.system('afplay /Users/vibhu/zd/siren-alert-96052.mp3')
    return Group(call_table, put_table)  # Group tables for simultaneous display in Live
def run_analysis_iteration(dhan_conn: dhanhq, underlying_security_id: str, nearest_exp_date: date):
    """
    Performs one complete iteration of fetching data, calculating differences, and generating tables.
    This function is called repeatedly by the live update loop.
    Args:
        dhan_conn: Initialized dhanhq object.
        nearest_exp_date: The nearest weekly expiry date (determined once at startup).
    Returns:
        A Rich Group object containing the Call and Put tables for display,
        or a Rich Panel with an error/warning message if issues occur.
    """
    try:
        logging.debug("Starting new analysis iteration.")
        # 1. Get current ATM strike
        current_atm_strike = get_atm_strike(dhan_conn, UNDERLYING_SYMBOL, EXCHANGE_LTP, STRIKE_DIFFERENCE)
        if not current_atm_strike:  # Critical if ATM cannot be determined for this iteration
            logging.error("Could not determine ATM strike for this iteration.")
            return Panel("[bold red]Error: Could not determine ATM strike. Check logs. Waiting for next refresh.[/bold red]", title="Update Error", border_style="red")

        # This check should ideally be redundant if main() ensures nearest_exp_date is valid before starting loop
        if not nearest_exp_date:
             logging.error("Nearest expiry date is not available (should not happen if pre-checked).")
             return Panel("[bold red]Error: Nearest expiry date not available. Critical error.[/bold red]", title="Update Error", border_style="red")
        # 2. Identify relevant option contracts around the new ATM strike
        option_contract_details = get_relevant_option_details(
            dhan_conn, current_atm_strike, nearest_exp_date,
            STRIKE_DIFFERENCE, OPTIONS_COUNT
        )

        # If no contracts are found (e.g., due to market close or issues with instrument list for that ATM)
        if not option_contract_details:
            logging.warning(f"Could not retrieve relevant option contracts for ATM {int(current_atm_strike)}.")
            return Panel(f"[bold yellow]Warning: Could not retrieve relevant option contracts for ATM {int(current_atm_strike)}. Waiting for next refresh.[/bold yellow]", title="Update Warning", border_style="yellow")
        # 3. Fetch historical OI data for these contracts
        raw_historical_oi_data = fetch_historical_oi_data(dhan_conn, option_contract_details)
        #print(raw_historical_oi_data)

        # 4. Calculate OI differences
        oi_change_data = calculate_oi_differences(raw_historical_oi_data, OI_CHANGE_INTERVALS_MIN)

        # 5. Generate Rich tables for display
        table_group = generate_options_tables(
            oi_change_data, option_contract_details, current_atm_strike,
            STRIKE_DIFFERENCE, OPTIONS_COUNT, OI_CHANGE_INTERVALS_MIN
        )
        logging.debug("Analysis iteration completed successfully.")
        return table_group
    except Exception as e:  # Catch any other unexpected errors during the iteration
        logging.error(f"Exception during analysis iteration: {e}", exc_info=True)
        return Panel(f"[bold red]An error occurred during data refresh: {e}. Check logs.[/bold red]", title="Update Error", border_style="red")
def main():
    """
    Main function to run the OI Tracker script.
    Handles initial setup (API connection, instrument fetching) and then enters the live update loop.
    """
    console.print(f"[bold blue]Starting OI Tracker Script (Log file: {LOG_FILE_NAME})[/bold blue]")
    # Check if API keys are default placeholders and warn user
    if client_id_to_use == CLIENT_ID_DEFAULT or access_token_to_use == ACCESS_TOKEN_DEFAULT:
        console.print(f"[bold yellow]Warning: Using default placeholder API Key/Secret.[/bold yellow]")
        console.print(f"[yellow]Please set 'DHAN_CLIENT_ID' and 'DHAN_ACCESS_TOKEN' environment variables for live data.[/yellow]")
        logging.warning("Using default placeholder API Key/Secret. User prompted to set environment variables.")
        # The script might continue but will likely fail at API calls if keys are not valid.
    try:
        # --- Initial Setup ---
        # 1. Verify Connection
        dhan.get_positions()
        console.print("[bold green]DhanHQ API connection verified successfully![/bold green]")

        # 2. Get Security ID for the underlying symbol
        underlying_security_id = get_security_id(dhan, UNDERLYING_SYMBOL)
        if not underlying_security_id:
            console.print(f"[bold red]Could not find security ID for {UNDERLYING_SYMBOL}. Exiting.[/bold red]")
            logging.critical(f"Could not find security ID for {UNDERLYING_SYMBOL}.")
            sys.exit(1)
        console.print(f"Found security ID for {UNDERLYING_SYMBOL}: [bold magenta]{underlying_security_id}[/bold magenta]")

        # 3. Determine nearest weekly expiry (done once at startup)
        # Note: If the script is run over multiple days, this expiry might become outdated.
        # For simplicity, it's fetched once. A more advanced version might re-check periodically.
        return_arr = get_nearest_weekly_expiry(dhan, underlying_security_id)
        if not return_arr:
            console.print(f"[bold red]Could not determine nearest weekly expiry for {UNDERLYING_SYMBOL}. Exiting.[/bold red]")
            logging.critical(f"Could not determine nearest weekly expiry for {UNDERLYING_SYMBOL}.")
            sys.exit(1)  # Critical error
        nearest_expiry_date = return_arr['expiry']
        console.print(f"Tracking options for expiry: [bold magenta]{nearest_expiry_date.strftime('%d-%b-%Y')}[/bold magenta]")

        console.print(f"Starting live updates. Refresh interval: {REFRESH_INTERVAL_SECONDS} seconds. Press Ctrl+C to exit.")
        console.print(f"Underlying: [bold cyan]{UNDERLYING_SYMBOL}[/bold cyan], Strike Difference: [bold cyan]{STRIKE_DIFFERENCE}[/bold cyan], Options Count per side: [bold cyan]{OPTIONS_COUNT}[/bold cyan]")
        # --- Live Update Loop ---
        # refresh_per_second for Live is for UI animation smoothness if any;
        # auto_refresh=False means we control update timing with time.sleep()
        with Live(console=console, refresh_per_second=10, auto_refresh=False) as live:
            while True:
                logging.info("Starting new live update cycle.")
                # Perform one iteration of analysis
                display_content = run_analysis_iteration(dhan, underlying_security_id, nearest_expiry_date)
                # Update the live display with the new tables or error panel
                live.update(display_content, refresh=True)
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
    main()
