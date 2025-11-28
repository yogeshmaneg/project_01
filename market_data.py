from dhanhq import dhanhq
import pandas as pd
from datetime import datetime, timedelta
import config

def get_historical_data(instrument, timeframe, from_date_str, to_date_str):
    """
    Fetches historical intraday data for a given instrument and timeframe.

    Args:
        instrument (dict): A dictionary containing security_id and exchange.
        timeframe (int): The timeframe in minutes (1, 5, etc.).
        from_date_str (str): The start date in YYYY-MM-DD format.
        to_date_str (str): The end date in YYYY-MM-DD format.

    Returns:
        pandas.DataFrame: A DataFrame containing the historical data, or an empty DataFrame if an error occurs.
    """
    try:
        dhan = dhanhq(config.CLIENT_ID, config.ACCESS_TOKEN)

        from_date = datetime.strptime(from_date_str, "%Y-%m-%d")
        to_date = datetime.strptime(to_date_str, "%Y-%m-%d")

        all_data_chunks = []

        current_from_date = from_date
        while current_from_date < to_date:
            current_to_date = min(current_from_date + timedelta(days=89), to_date)

            print(f"Fetching data from {current_from_date.strftime('%Y-%m-%d')} to {current_to_date.strftime('%Y-%m-%d')} for {timeframe}min timeframe")

            instrument_type = "INDEX"
            exchange_segment = 'IDX_I'

            data = dhan.intraday_minute_data(
                security_id=instrument["security_id"],
                exchange_segment=exchange_segment,
                instrument_type=instrument_type,
                from_date=current_from_date.strftime("%Y-%m-%d"),
                to_date=current_to_date.strftime("%Y-%m-%d"),
                interval=timeframe
            )

            if data and data.get('status') == 'success' and 'data' in data and data['data']:
                 # The API returns a dictionary of lists. Convert it to a DataFrame directly.
                 chunk_df = pd.DataFrame(data['data'])
                 all_data_chunks.append(chunk_df)
            elif data:
                if not (data.get('status') == 'success' and 'data' in data and not data['data']):
                    print(f"API Error for {instrument['security_id']}: {data.get('remarks', 'No remarks')}")
            else:
                 print(f"API Error for {instrument['security_id']}: Empty or invalid response")

            current_from_date += timedelta(days=90)

        if not all_data_chunks:
            print("No data fetched.")
            return pd.DataFrame()

        # Concatenate all the chunk DataFrames
        df = pd.concat(all_data_chunks, ignore_index=True)

        # Correction: The correct key for the timestamp is 'timestamp'.
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='s').dt.tz_localize('UTC').dt.tz_convert('Asia/Kolkata')
        df.set_index('datetime', inplace=True)
        df = df[['open', 'high', 'low', 'close', 'volume']]

        return df

    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return pd.DataFrame()

if __name__ == '__main__':
    nifty_50 = config.INDICES["NIFTY_50"]
    to_date_str = datetime.now().strftime("%Y-%m-%d")
    from_date_str = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")

    print("--- Fetching 5-minute data for Nifty 50 ---")
    df_5min = get_historical_data(nifty_50, 5, from_date_str, to_date_str)
    if not df_5min.empty:
        print("Successfully fetched 5-minute data:")
        print(df_5min.head())
        print(df_5min.tail())
    else:
        print("Failed to fetch 5-minute data.")
