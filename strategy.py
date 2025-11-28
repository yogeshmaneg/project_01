import pandas as pd
import pandas_ta as ta
import config

def generate_signals(df):
    """
    Generates trading signals based on SuperTrend and RSI indicators.

    Args:
        df (pandas.DataFrame): A DataFrame containing OHLCV data.

    Returns:
        pandas.DataFrame: The input DataFrame with added columns for indicators and signals.
    """
    if df.empty:
        return df

    # Calculate RSI
    df['rsi'] = ta.rsi(df['close'], length=config.RSI_PERIOD)

    # Calculate SuperTrend
    supertrend = ta.supertrend(df['high'], df['low'], df['close'],
                               length=config.SUPERTREND_PERIOD,
                               multiplier=config.SUPERTREND_MULTIPLIER)

    # --- Robustly find the SuperTrend column ---
    # Find the column name that starts with 'SUPERT_'
    supertrend_col_name = None
    if supertrend is not None and not supertrend.empty:
        for col in supertrend.columns:
            if col.startswith('SUPERT_'):
                supertrend_col_name = col
                break

    if supertrend_col_name:
        df['supertrend'] = supertrend[supertrend_col_name]
    else:
        # Handle the case where the SuperTrend could not be calculated
        print("Warning: SuperTrend indicator could not be calculated. Skipping signal generation.")
        df['supertrend'] = pd.NA
        df['buy_signal'] = False
        df['sell_signal'] = False
        return df


    # --- Signal Logic ---

    # Conditions
    # Use .shift() to compare the current close with the previous supertrend value
    price_crosses_above = (df['close'].shift(1) <= df['supertrend'].shift(1)) & (df['close'] > df['supertrend'])
    price_crosses_below = (df['close'].shift(1) >= df['supertrend'].shift(1)) & (df['close'] < df['supertrend'])
    rsi_above_threshold = df['rsi'] > config.RSI_BUY_THRESHOLD
    rsi_below_threshold = df['rsi'] < config.RSI_SELL_THRESHOLD

    # Generate Signals
    df['buy_signal'] = price_crosses_above & rsi_above_threshold
    df['sell_signal'] = price_crosses_below & rsi_below_threshold

    return df

if __name__ == '__main__':
    # Create a dummy DataFrame for testing
    data = {
        'open': [100, 102, 101, 103, 105, 104, 106, 108, 107, 109, 110, 108, 105, 103, 101],
        'high': [103, 104, 103, 105, 106, 106, 108, 110, 109, 111, 112, 110, 107, 105, 102],
        'low': [99, 101, 100, 102, 104, 103, 105, 107, 106, 108, 109, 107, 104, 102, 100],
        'close': [102, 103, 102, 104, 105, 105, 107, 109, 108, 110, 111, 109, 106, 104, 101],
        'volume': [1000] * 15
    }
    # We need enough data points for the indicators to be calculated
    more_data = pd.DataFrame({
        'open': range(100, 150),
        'high': range(102, 152),
        'low': range(98, 148),
        'close': range(101, 151),
        'volume': [1000] * 50
    })
    df = pd.concat([pd.DataFrame(data), more_data], ignore_index=True)


    print("--- Initial DataFrame (first 5 rows) ---")
    print(df.head())

    # Generate signals
    df_with_signals = generate_signals(df.copy())

    print("\n--- DataFrame with Signals (sample) ---")
    print(df_with_signals.tail(20))

    # Print rows where a signal is generated
    print("\n--- Buy Signals ---")
    print(df_with_signals[df_with_signals['buy_signal']])

    print("\n--- Sell Signals ---")
    print(df_with_signals[df_with_signals['sell_signal']])
