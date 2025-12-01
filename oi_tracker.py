import json
import time
from datetime import datetime, timedelta
from dhanhq import dhanhq
import pandas as pd
from rich.console import Console
from rich.table import Table
from playsound import playsound

# --- Configuration ---
CONFIG_FILE = 'config.json'
NIFTY_SECURITY_ID = 13  # Nifty 50 security ID
EXCHANGE_SEGMENT = 'IDX_I'
TIME_INTERVALS = [3, 5, 10, 15, 30]
STRIKE_RANGE = 2  # Number of strikes above and below ATM

def load_config():
    """Loads API credentials from the configuration file."""
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
        if config['client_id'] == 'YOUR_CLIENT_ID' or config['access_token'] == 'YOUR_ACCESS_TOKEN':
            print("Please update your client_id and access_token in config.json")
            exit()
        return config['client_id'], config['access_token']
    except FileNotFoundError:
        print(f"Error: {CONFIG_FILE} not found. Please create it with your API credentials.")
        exit()
    except KeyError:
        print(f"Error: Invalid {CONFIG_FILE}. Make sure it contains 'client_id' and 'access_token'.")
        exit()

def get_nearest_expiry(dhan):
    """Fetches the nearest expiry date for Nifty 50 options."""
    try:
        expiries = dhan.get_expiry(NIFTY_SECURITY_ID, EXCHANGE_SEGMENT)
        return expiries['expiry_dates'][0]
    except Exception as e:
        print(f"Error fetching expiry dates: {e}")
        return None

def get_atm_strike(dhan, expiry_date):
    """Determines the at-the-money (ATM) strike price."""
    try:
        option_chain = dhan.get_option_chain(NIFTY_SECURITY_ID, EXCHANGE_SEGMENT, expiry_date)
        ltp = option_chain['data']['last_price']
        # Find the strike price closest to the last traded price
        atm_strike = min(option_chain['data']['oc'], key=lambda x: abs(float(x) - ltp))
        return float(atm_strike)
    except Exception as e:
        print(f"Error fetching option chain: {e}")
        return None

def get_strikes(atm_strike):
    """Generates a list of strike prices around the ATM strike."""
    return [atm_strike + i * 50 for i in range(-STRIKE_RANGE, STRIKE_RANGE + 1)]

def display_tables(console, call_data, put_data):
    """Displays the OI data in two tables using rich."""
    console.clear()

    call_table = Table(title="Nifty 50 Call Options OI Change (%)")
    put_table = Table(title="Nifty 50 Put Options OI Change (%)")

    call_table.add_column("Strike", justify="right", style="cyan", no_wrap=True)
    put_table.add_column("Strike", justify="right", style="cyan", no_wrap=True)

    for interval in TIME_INTERVALS:
        call_table.add_column(f"{interval} min", justify="right")
        put_table.add_column(f"{interval} min", justify="right")

    red_cell_count = 0
    for strike in call_data.index:
        call_row = [f"{strike:.2f}"]
        put_row = [f"{strike:.2f}"]
        for i, interval in enumerate(TIME_INTERVALS):
            call_val = call_data.iloc[call_data.index.get_loc(strike), i]
            put_val = put_data.iloc[put_data.index.get_loc(strike), i]

            call_style = "white"
            if (interval == 10 and call_val > 10) or \
               (interval == 15 and call_val > 15) or \
               (interval == 30 and call_val > 25):
                call_style = "red"
                red_cell_count += 1

            put_style = "white"
            if (interval == 10 and put_val > 10) or \
               (interval == 15 and put_val > 15) or \
               (interval == 30 and put_val > 25):
                put_style = "red"
                red_cell_count +=1

            call_row.append(f"[{call_style}]{call_val:.2f}[/{call_style}]")
            put_row.append(f"[{put_style}]{put_val:.2f}[/{put_style}]")

        call_table.add_row(*call_row)
        put_table.add_row(*put_row)

    console.print(call_table)
    console.print(put_table)

    return red_cell_count

def main():
    """Main function to run the OI tracker."""
    client_id, access_token = load_config()

    try:
        dhan = dhanhq(client_id, access_token)
        print("Successfully connected to DhanHQ API.")
    except Exception as e:
        print(f"Error connecting to DhanHQ API: {e}")
        exit()

    expiry_date = get_nearest_expiry(dhan)
    if not expiry_date:
        exit()

    atm_strike = get_atm_strike(dhan, expiry_date)
    if not atm_strike:
        exit()

    strikes = get_strikes(atm_strike)

    print(f"Nearest Expiry: {expiry_date}")
    print(f"ATM Strike: {atm_strike}")
    print(f"Tracking Strikes: {strikes}")

    # --- Initialize Data Storage ---
    columns = [f'{t} min' for t in TIME_INTERVALS]
    call_oi_data = pd.DataFrame(index=strikes, columns=columns, dtype=float)
    put_oi_data = pd.DataFrame(index=strikes, columns=columns, dtype=float)

    # --- Main Loop ---
    console = Console()
    oi_history = []
    last_atm_check = datetime.now()
    while True:
        # --- Recalculate ATM strike every 15 minutes ---
        if datetime.now() - last_atm_check > timedelta(minutes=15):
            new_atm_strike = get_atm_strike(dhan, expiry_date)
            if new_atm_strike and new_atm_strike != atm_strike:
                print(f"ATM strike changed from {atm_strike} to {new_atm_strike}. Resetting...")
                atm_strike = new_atm_strike
                strikes = get_strikes(atm_strike)
                call_oi_data = pd.DataFrame(index=strikes, columns=columns, dtype=float)
                put_oi_data = pd.DataFrame(index=strikes, columns=columns, dtype=float)
                oi_history = []
            last_atm_check = datetime.now()

        # Fetch current option chain data
        option_chain = dhan.get_option_chain(NIFTY_SECURITY_ID, EXCHANGE_SEGMENT, expiry_date)
        current_oi = {}
        for strike in strikes:
            strike_str = f"{strike:.2f}"
            if strike_str in option_chain['data']['oc']:
                oc_data = option_chain['data']['oc'][strike_str]
                current_oi[strike] = {
                    'ce': oc_data.get('ce', {}).get('oi', 0),
                    'pe': oc_data.get('pe', {}).get('oi', 0)
                }

        oi_history.append({'timestamp': datetime.now(), 'data': current_oi})

        # Prune history
        oi_history = [entry for entry in oi_history if entry['timestamp'] > datetime.now() - timedelta(minutes=max(TIME_INTERVALS))]

        # Calculate OI change
        for interval in TIME_INTERVALS:
            past_time = datetime.now() - timedelta(minutes=interval)
            past_entry = min(oi_history, key=lambda x: abs(x['timestamp'] - past_time))

            for strike in strikes:
                if strike in past_entry['data'] and strike in current_oi:
                    initial_call_oi = past_entry['data'][strike]['ce']
                    current_call_oi = current_oi[strike]['ce']
                    if initial_call_oi > 0:
                        call_oi_data.loc[strike, f'{interval} min'] = ((current_call_oi - initial_call_oi) / initial_call_oi) * 100

                    initial_put_oi = past_entry['data'][strike]['pe']
                    current_put_oi = current_oi[strike]['pe']
                    if initial_put_oi > 0:
                        put_oi_data.loc[strike, f'{interval} min'] = ((current_put_oi - initial_put_oi) / initial_put_oi) * 100

        # Display the tables
        red_cell_count = display_tables(console, call_oi_data.fillna(0), put_oi_data.fillna(0))

        # Check for alert condition
        total_cells = len(strikes) * len(TIME_INTERVALS) * 2 # 2 for call and put tables
        if red_cell_count > 0.5 * total_cells:
            try:
                playsound('alert.wav')
            except Exception as e:
                print(f"Error playing sound: {e}")

        time.sleep(60)

if __name__ == "__main__":
    main()
