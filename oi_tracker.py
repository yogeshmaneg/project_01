import time
import json
import pandas as pd
from rich.console import Console
from rich.live import Live
from rich.table import Table
from playsound import playsound
from Dhan_Tradehull_V2 import Tradehull

def get_strike_symbols(tradehull, underlying, expiry):
    """
    Gets the ATM, ITM, and OTM strike symbols.
    """
    ce_atm_symbol, pe_atm_symbol, _ = tradehull.ATM_Strike_Selection(underlying, expiry)

    ce_itm1_symbol, pe_itm1_symbol, _, _ = tradehull.ITM_Strike_Selection(underlying, expiry, ITM_count=1)
    ce_itm2_symbol, pe_itm2_symbol, _, _ = tradehull.ITM_Strike_Selection(underlying, expiry, ITM_count=2)

    ce_otm1_symbol, pe_otm1_symbol, _, _ = tradehull.OTM_Strike_Selection(underlying, expiry, OTM_count=1)
    ce_otm2_symbol, pe_otm2_symbol, _, _ = tradehull.OTM_Strike_Selection(underlying, expiry, OTM_count=2)

    return {
        "call": {
            "ATM-2": ce_itm2_symbol,
            "ATM-1": ce_itm1_symbol,
            "ATM": ce_atm_symbol,
            "ATM+1": ce_otm1_symbol,
            "ATM+2": ce_otm2_symbol,
        },
        "put": {
            "ATM-2": pe_otm2_symbol,
            "ATM-1": pe_otm1_symbol,
            "ATM": pe_atm_symbol,
            "ATM+1": pe_itm1_symbol,
            "ATM+2": pe_itm2_symbol,
        },
    }

def get_oi_data(tradehull, strike_symbols):
    """
    Gets the Open Interest data for the given strike symbols.
    """
    oi_data = {"call": {}, "put": {}}
    for option_type, strike_map in strike_symbols.items():
        for strike_name, symbol in strike_map.items():
            if symbol:
                oi = tradehull.get_oi(symbol)
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

        tradehull = Tradehull(client_code, token_id)

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

                    strikes = get_strike_symbols(tradehull, underlying, expiry)
                    current_oi = get_oi_data(tradehull, strikes)

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

                    call_rich_table, call_color_coded, call_total_cells = generate_rich_table(call_oi_table, "Call OI Change (%)")
                    put_rich_table, put_color_coded, put_total_cells = generate_rich_table(put_oi_table, "Put OI Change (%)")

                    live.update(call_rich_table)
                    live.console.print(put_rich_table)
                    live.refresh()

                    check_and_play_alert(call_color_coded + put_color_coded, call_total_cells + put_total_cells)

                    time.sleep(60)
                except Exception as e:
                    console.print(f"[bold red]An error occurred: {e}[/bold red]")
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
