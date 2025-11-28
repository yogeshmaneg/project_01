import matplotlib.pyplot as plt
import pandas as pd

def plot_backtest_results(df_signals, trades, output_filename="backtest_chart.png"):
    """
    Generates a plot of the backtest results.

    Args:
        df_signals (pd.DataFrame): The DataFrame containing the price data and signals.
        trades (list): A list of trade dictionaries.
        output_filename (str): The name of the image file to save.
    """
    if df_signals.empty:
        print("No data to plot.")
        return

    plt.style.use('seaborn-v0_8-darkgrid')
    fig, ax = plt.subplots(figsize=(15, 8))

    # Plot price and SuperTrend
    ax.plot(df_signals.index, df_signals['close'], label='Close Price', color='blue', alpha=0.7)
    ax.plot(df_signals.index, df_signals['supertrend'], label='SuperTrend', color='orange', linestyle='--', alpha=0.8)

    # Plot Buy/Sell signals from the trades log
    buy_signals = [trade['entry_time'] for trade in trades if trade['option_type'] == 'CALL']
    sell_signals = [trade['entry_time'] for trade in trades if trade['option_type'] == 'PUT']

    if buy_signals:
        buy_prices = df_signals.loc[buy_signals]['close']
        ax.scatter(buy_signals, buy_prices, label='Buy Signal', marker='^', color='green', s=150, zorder=5)

    if sell_signals:
        sell_prices = df_signals.loc[sell_signals]['close']
        ax.scatter(sell_signals, sell_prices, label='Sell Signal', marker='v', color='red', s=150, zorder=5)

    ax.set_title('Backtest Results: Price, SuperTrend, and Trades')
    ax.set_xlabel('Date')
    ax.set_ylabel('Price')
    ax.legend()
    plt.xticks(rotation=45)
    plt.tight_layout()

    plt.savefig(output_filename)
    print(f"Chart saved as {output_filename}")
    plt.close() # Close the plot to free up memory

if __name__ == '__main__':
    # This part is for standalone testing of the plotting function
    from backtest import _generate_dummy_data, run_backtest
    from strategy import generate_signals
    import config

    # Generate dummy data and signals
    dummy_df = _generate_dummy_data()
    dummy_df_with_signals = generate_signals(dummy_df.copy())

    # Run a backtest to get a list of trades
    nifty_50 = config.INDICES["NIFTY_50"]
    sample_trades = run_backtest(nifty_50, 5, None, None, use_dummy_data=True)

    # Plot the results
    if not dummy_df_with_signals.empty and sample_trades:
        plot_backtest_results(dummy_df_with_signals, sample_trades)
