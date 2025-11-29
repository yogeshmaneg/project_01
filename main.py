import argparse
from datetime import datetime, timedelta
import config
import backtest
import reporting
import plotting

def main(use_dummy_data=False):
    """
    Main function to run the backtesting and reporting process.
    """

    # Define the date range for the backtest
    to_date = datetime.now().strftime("%Y-%m-%d")
    from_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")

    for index_name, instrument in config.INDICES.items():
        print(f"\n{'='*50}")
        print(f"Processing Index: {index_name}")
        print(f"{'='*50}")

        for timeframe in config.TIMEFRAMES:
            # --- 1. Run the Backtest ---
            # The backtest function now returns both trades and the dataframe with signals
            trades, df_with_signals = backtest.run_backtest(
                instrument, timeframe, from_date, to_date, use_dummy_data
            )

            if trades:
                # --- 2. Generate Report ---
                report_filename = f"report_{index_name}_{timeframe}min.xlsx"
                reporting.generate_report(trades, report_filename)

                # --- 3. Generate Plot ---
                # Pass the dataframe directly to the plotting function
                if not df_with_signals.empty:
                    plot_filename = f"chart_{index_name}_{timeframe}min.png"
                    plotting.plot_backtest_results(df_with_signals, trades, plot_filename)
                else:
                    print("Could not generate plot because no data was returned from the backtest.")

            else:
                print(f"No trades were generated for {index_name} ({timeframe}min). Skipping report and plot.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Run the trading algorithm backtester.")
    parser.add_argument(
        '--dummy-data',
        action='store_true',
        help="Use generated dummy data instead of fetching from the API."
    )
    args = parser.parse_args()

    main(use_dummy_data=args.dummy_data)
