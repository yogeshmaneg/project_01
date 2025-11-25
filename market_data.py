import pandas as pd
from dhanhq import dhanhq
import pandas_ta as ta
import config
from datetime import datetime

def get_latest_candle(dhan, security_id, exchange_segment='IDX', instrument='INDEX'):
    """
    Fetches the latest candle for a given security ID.

    NOTE: This function is inefficient for live trading as it fetches the
    entire day's data on every call. A more robust solution would use
    websockets or a more targeted API endpoint.
    """
    try:
        # This is a placeholder. In a real scenario, you would use a function
        # that returns only the latest candle. For now, we'll fetch a small
        # amount of data and return the last row.
        today = datetime.now().strftime('%Y-%m-%d')
        response = dhan.intraday_minute_data(
            security_id=str(security_id),
            exchange_segment=exchange_segment,
            instrument_type=instrument,
            from_date=today,
            to_date=today
        )
        if response['status'] == 'success':
            df = pd.DataFrame(response['data'])
            df.rename(columns={'start_Time': 'date'}, inplace=True)
            df['date'] = pd.to_datetime(df['date'], unit='s')
            df.set_index('date', inplace=True)
            return df.iloc[-1:]
        else:
            print(f"Error fetching latest candle: {response}")
            return None
    except Exception as e:
        print(f"An error occurred while fetching the latest candle: {e}")
        return None

def get_historical_data(dhan, security_id, exchange_segment='IDX', instrument='INDEX', interval='5', use_mock_data=True):
    """
    Fetches historical data for a given security ID and resamples it to the specified interval.
    If use_mock_data is True, it reads data from a CSV file.
    """
    if use_mock_data:
        try:
            df = pd.read_csv('nifty_50_mock_data.csv')
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            return df
        except FileNotFoundError:
            print("Error: nifty_50_mock_data.csv not found.")
            return None
    else:
        try:
            response = dhan.intraday_minute_data(
                security_id=str(security_id),
                exchange_segment=exchange_segment,
                instrument_type=instrument,
                from_date=config.BACKTEST_FROM_DATE,
                to_date=config.BACKTEST_TO_DATE
            )
            if response['status'] == 'success':
                df = pd.DataFrame(response['data'])
                df.rename(columns={'start_Time': 'date'}, inplace=True)
                df['date'] = pd.to_datetime(df['date'], unit='s')
                df.set_index('date', inplace=True)

                # Resample to 5-minute candles
                ohlc_dict = {
                    'open': 'first',
                    'high': 'max',
                    'low': 'min',
                    'close': 'last',
                    'volume': 'sum'
                }
                df = df.resample(f'{interval}T').apply(ohlc_dict).dropna()
                return df
            else:
                print(f"Error fetching historical data: {response}")
                return None
        except Exception as e:
            print(f"An error occurred while fetching historical data: {e}")
            return None

def calculate_indicators(df):
    """
    Calculates technical indicators (Bollinger Bands and RSI) for a given DataFrame.
    """
    if df is not None:
        df.ta.bbands(append=True, length=config.BB_LENGTH, std=config.BB_STD)
        df.ta.rsi(append=True, length=config.RSI_LENGTH)
    return df
