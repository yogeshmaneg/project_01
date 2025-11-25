import pandas as pd
import pandas_ta as ta
import config

def check_strategy_conditions(df, i):
    """
    Checks if the trading strategy conditions are met.

    :param df: DataFrame with historical data and indicators.
    :param i: The current index in the DataFrame.
    :return: 'BUY_CALL', 'BUY_PUT', or None
    """
    if df is None or len(df) < 2:
        return None

    latest_candle = df.iloc[i]

    # Column names
    bbu_col = f'BBU_{config.BB_LENGTH}_{float(config.BB_STD)}'
    bbl_col = f'BBL_{config.BB_LENGTH}_{float(config.BB_STD)}'
    rsi_col = f'RSI_{config.RSI_LENGTH}'

    # Check if the columns exist to prevent KeyErrors
    if bbu_col not in df.columns or bbl_col not in df.columns or rsi_col not in df.columns:
        return None

    # Buy Call condition
    if latest_candle['close'] > latest_candle[bbu_col] and latest_candle[rsi_col] > config.RSI_OVERBOUGHT:
        return 'BUY_CALL'

    # Buy Put condition
    if latest_candle['close'] < latest_candle[bbl_col] and latest_candle[rsi_col] < config.RSI_OVERSOLD:
        return 'BUY_PUT'

    return None
