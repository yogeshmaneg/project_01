import time
import json
import os
import pandas as pd
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from playsound import playsound
from dhanhq import dhanhq

# --- Constants and Configuration ---

# Dictionary for strike price steps of indices
INDEX_STEP_DICT = {
    'NIFTY': 50, 'NIFTY 50': 50, 'BANKNIFTY': 100, 'NIFTY BANK': 100,
    'FINNIFTY': 50, 'NIFTY FIN SERVICE': 50, 'MIDCPNIFTY': 25,
    'SENSEX': 100, 'BANKEX': 100
}

# --- Helper Functions for DhanHQ API Interaction ---

def get_instrument_file():
    """
    Downloads and caches the Dhan scrip master file.
    Deletes old files to ensure the data is recent.
    """
    if not os.path.exists('Dependencies'):
        os.makedirs('Dependencies')

    today_str = time.strftime("%Y-%m-%d")
    expected_file = f'Dependencies/all_instrument {today_str}.csv'

    # Clean up old instrument files
    for item in os.listdir("Dependencies"):
        if item.startswith('all_instrument') and today_str not in item:
            os.remove(os.path.join("Dependencies", item))

    if os.path.exists(expected_file):
        print(f"Reading existing instrument file: {expected_file}")
        return pd.read_csv(expected_file, low_memory=False)
    else:
        print("Downloading new instrument file from Dhan...")
        df = pd.read_csv("https://images.dhan.co/api-data/api-scrip-master.csv", low_memory=False)
        df.to_csv(expected_file, index=False)
        return df

def get_ltp(dhan, instrument_df, symbol_name):
    """
    Fetches the Last Traded Price (LTP) for a given symbol.
    """
    try:
        # For indices, the segment is 'IDX_I'
        if "NIFTY" in symbol_name or "SENSEX" in symbol_name or "BANKEX" in symbol_name:
            segment = 'IDX_I'
            security_id_row = instrument_df[instrument_df['SEM_CUSTOM_SYMBOL'] == symbol_name]
        else: # Assuming equity or other
            segment = 'NSE_EQ'
            security_id_row = instrument_df[instrument_df['SEM_TRADING_SYMBOL'] == symbol_name]

        if security_id_row.empty:
            print(f"Could not find security ID for {symbol_name}")
            return 0

        security_id = security_id_row.iloc[0]['SEM_SMST_SECURITY_ID']

        response = dhan.quote(str(security_id), segment)
        if response.get('status') == 'success':
            return response.get('data', {}).get('last_price', 0)
        else:
            print(f"Error fetching LTP for {symbol_name}: {response}")
            return 0
    except Exception as e:
        print(f"Exception fetching LTP for {symbol_name}: {e}")
        return 0

def get_oi(dhan, instrument_df, symbol_name):
    """
    Fetches the Open Interest for a given F&O symbol.
    """
    try:
        segment = 'NSE_FNO'
        security_id_row = instrument_df[instrument_df['SEM_CUSTOM_SYMBOL'] == symbol_name]
        if security_id_row.empty:
            # print(f"Could not find security ID for {symbol_name}")
            return 0

        security_id = security_id_row.iloc[0]['SEM_SMST_SECURITY_ID']
        response = dhan.quote(str(security_id), segment)

        if response.get('status') == 'success':
            return response.get('data', {}).get('oi', 0)
        else:
            # print(f"Error fetching OI for {symbol_name}: {response}")
            return 0
    except Exception as e:
        # print(f"Exception fetching OI for {symbol_name}: {e}")
        return 0

def find_option_symbol(instrument_df, underlying, expiry, strike, option_type):
    """
    Finds the trading symbol for a specific option contract.
    """
    expiry_date_str = pd.to_datetime(expiry, format='%d-%m-%Y').strftime('%Y-%m-%d')

    # Filter for the specific contract
    filtered_df = instrument_df[
        (instrument_df['SEM_INSTRUMENT_NAME'] == 'OPTIDX') &
        (instrument_df['SEM_TRADING_SYMBOL'].str.contains(underlying, na=False)) &
        (instrument_df['SEM_EXPIRY_DATE'] == expiry_date_str) &
        (instrument_df['SEM_STRIKE_PRICE'] == strike) &
        (instrument_df['SEM_OPTION_TYPE'] == option_type)
    ]

    if not filtered_df.empty:
        return filtered_df.iloc[0]['SEM_CUSTOM_SYMBOL']
    else:
        return None

def get_strike_symbols(instrument_df, underlying, expiry, ltp):
    """
    Calculates ATM, ITM, and OTM strikes and finds their symbols.
    """
    step = INDEX_STEP_DICT.get(underlying, 50)
    atm_strike = round(ltp / step) * step

    strikes = {
        "ATM-2": atm_strike - (2 * step),
        "ATM-1": atm_strike - (1 * step),
        "ATM":   atm_strike,
        "ATM+1": atm_strike + (1 * step),
        "ATM+2": atm_strike + (2 * step),
    }

    symbols = {"call": {}, "put": {}}

    # Get Call symbols (ITM, ATM, OTM)
    symbols["call"]["ATM-2"] = find_option_symbol(instrument_df, underlying, expiry, strikes["ATM-2"], 'CE')
    symbols["call"]["ATM-1"] = find_option_symbol(instrument_df, underlying, expiry, strikes["ATM-1"], 'CE')
    symbols["call"]["ATM"] = find_option_symbol(instrument_df, underlying, expiry, strikes["ATM"], 'CE')
    symbols["call"]["ATM+1"] = find_option_symbol(instrument_df, underlying, expiry, strikes["ATM+1"], 'CE')
    symbols["call"]["ATM+2"] = find_option_symbol(instrument_df, underlying, expiry, strikes["ATM+2"], 'CE')

    # Get Put symbols (OTM, ATM, ITM)
    symbols["put"]["ATM-2"] = find_option_symbol(instrument_df, underlying, expiry, strikes["ATM-2"], 'PE')
    symbols["put"]["ATM-1"] = find_option_symbol(instrument_df, underlying, expiry, strikes["ATM-1"], 'PE')
    symbols["put"]["ATM"] = find_option_symbol(instrument_df, underlying, expiry, strikes["ATM"], 'PE')
    symbols["put"]["ATM+1"] = find_option_symbol(instrument_df, underlying, expiry, strikes["ATM+1"], 'PE')
    symbols["put"]["ATM+2"] = find_option_symbol(instrument_df, underlying, expiry, strikes["ATM+2"], 'PE')

    return symbols

# --- Core Application Logic ---

def get_oi_data(dhan, instrument_df, strike_symbols):
    """
    Gets the Open Interest data for the given strike symbols.
    """
    oi_data = {"call": {}, "put": {}}
    for option_type, strike_map in strike_symbols.items():
        for strike_name, symbol in strike_map.items():
            if symbol:
                oi = get_oi(dhan, instrument_df, symbol)
                oi_data[option_type][strike_name] = oi if oi is not None else 0
            else:
                oi_data[option_type][strike_name] = 0
    return oi_data

def create_oi_tables():
    """
    Creates the initial empty OI tables.
    """
    columns = ["3 mins", "5 mins", "10 mins", "15 mins", "30 mins"]
    indices = ["ATM-2", "ATM-1", "ATM", "ATM+1", "ATM+2"]
    call_df = pd.DataFrame(index=indices, columns=columns)
    put_df = pd.DataFrame(index=indices, columns=columns)
    return call_df, put_df

def update_oi_table(table, column_name, initial_oi, current_oi):
    """
    Calculates the percentage change in OI and updates the table.
    """
    for strike_name, initial_val in initial_oi.items():
        current_val = current_oi.get(strike_name, 0)
        if initial_val > 0:
            percentage_change = ((current_val - initial_val) / initial_val) * 100
            table.loc[strike_name, column_name] = percentage_change
        else:
            table.loc[strike_name, column_name] = "N/A"

def generate_rich_table(df, title):
    """
    Generates a rich Table from a pandas DataFrame with color coding.
    """
    rich_table = Table(title=title)
    rich_table.add_column("Strike")
    for col in df.columns:
        rich_table.add_column(col)

    color_coded_cells = 0
    total_cells = 0

    for index, row in df.iterrows():
        row_values = [index]
        for col_name, val in row.items():
            total_cells += 1
            if pd.notna(val) and isinstance(val, (int, float)):
                color = ""
                if col_name == "10 mins" and val > 10:
                    color = "red"
                elif col_name == "15 mins" and val > 15:
                    color = "red"
                elif col_name == "30 mins" and val > 25:
                    color = "red"

                if color:
                    color_coded_cells += 1
                    row_values.append(f"[{color}]{val:.2f}%[/{color}]")
                else:
                    row_values.append(f"{val:.2f}%")
            else:
                row_values.append(str(val) if pd.notna(val) else "")
        rich_table.add_row(*row_values)

    return rich_table, color_coded_cells, total_cells

def check_and_play_alert(color_coded_cells, total_cells):
    """
    Checks if more than 50% of the cells are color-coded and plays an alert sound.
    """
    if total_cells > 0 and (color_coded_cells / total_cells) > 0.5:
        playsound('alert.wav')

def main():
    """
    Main function to run the OI tracker.
    """
    console = Console()

    try:
        with open("config.json") as f:
            config = json.load(f)

        client_code = config["client_code"]
        token_id = config["token_id"]
        underlying = config["underlying"]
        expiry = config["expiry"]

        dhan = dhanhq(client_code, token_id)
        instrument_df = get_instrument_file()
        # Pre-process instrument file for faster lookups
        instrument_df['SEM_EXPIRY_DATE'] = pd.to_datetime(instrument_df['SEM_EXPIRY_DATE'], errors='coerce').dt.strftime('%Y-%m-%d')

        call_oi_table, put_oi_table = create_oi_tables()

        initial_oi = None
        start_time = time.time()

        updated_intervals = {
            "3 mins": False, "5 mins": False, "10 mins": False,
            "15 mins": False, "30 mins": False
        }

        with Live(console=console, screen=True, auto_refresh=False) as live:
            while True:
                try:
                    current_time = time.time()
                    elapsed_seconds = current_time - start_time

                    ltp = get_ltp(dhan, instrument_df, underlying)
                    if ltp == 0:
                        console.print(f"[yellow]Could not fetch LTP for {underlying}. Retrying in 60s.[/yellow]")
                        time.sleep(60)
                        continue

                    strike_symbols = get_strike_symbols(instrument_df, underlying, expiry, ltp)
                    current_oi = get_oi_data(dhan, instrument_df, strike_symbols)

                    if initial_oi is None:
                        initial_oi = current_oi

                    time_intervals = {
                        180: "3 mins", 300: "5 mins", 600: "10 mins",
                        900: "15 mins", 1800: "30 mins"
                    }

                    for seconds, interval_name in time_intervals.items():
                        if elapsed_seconds >= seconds and not updated_intervals[interval_name]:
                            update_oi_table(call_oi_table, interval_name, initial_oi["call"], current_oi["call"])
                            update_oi_table(put_oi_table, interval_name, initial_oi["put"], current_oi["put"])
                            updated_intervals[interval_name] = True

                    call_rich_table, call_color_coded, call_total_cells = generate_rich_table(call_oi_table, f"Call OI Change (%) - {underlying} LTP: {ltp}")
                    put_rich_table, put_color_coded, put_total_cells = generate_rich_table(put_oi_table, f"Put OI Change (%) - {underlying} LTP: {ltp}")

                    layout = Layout()
                    layout.split_row(
                        Panel(call_rich_table, title="[bold green]Call Options[/bold green]"),
                        Panel(put_rich_table, title="[bold red]Put Options[/bold red]")
                    )
                    live.update(layout)

                    check_and_play_alert(call_color_coded + put_color_coded, call_total_cells + put_total_cells)

                    time.sleep(60)
                except Exception as e:
                    console.print(f"[bold red]An error occurred in the main loop: {e}[/bold red]")
                    time.sleep(60)

    except FileNotFoundError:
        console.print("[bold red]Error: config.json not found. Please create it from config.example.json.[/bold red]")
    except json.JSONDecodeError as e:
        console.print(f"[bold red]Error: Could not parse config.json. Please check for syntax errors.[/bold red]")
        console.print(f"[bold red]Details: {e}[/bold red]")
        console.print(f"[yellow]Common mistakes include trailing commas or using single quotes instead of double quotes.[/yellow]")
    except KeyError as e:
        console.print(f"[bold red]Error: Missing key in config.json: {e}[/bold red]")
    except KeyboardInterrupt:
        console.print("[bold yellow]Exiting...[/bold yellow]")


if __name__ == "__main__":
    main()
