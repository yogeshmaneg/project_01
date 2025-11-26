from dhanhq import dhanhq
import config
import market_data
import strategy
import order_management
import backtest
import time
import pandas as pd
from collections import deque

def connect_to_dhan():
    """
    Connects to the DhanHQ API and returns the API client.
    """
    try:
        dhan = dhanhq(config.CLIENT_ID, config.ACCESS_TOKEN)
        print("Successfully connected to DhanHQ API.")
        return dhan
    except Exception as e:
        print(f"Failed to connect to DhanHQ API: {e}")
        return None

def get_security_id(instrument_name):
    """
    Returns the security ID for the given instrument name.
    """
    instrument_map = {
        "NIFTY_50": 13,
        "BANKNIFTY": 26009,
        "SENSEX": 1
    }
    return instrument_map.get(instrument_name)

def run_backtest_and_export():
    """
    Runs the backtest and exports the results to an Excel file.
    """
    dhan = None
    if not config.USE_MOCK_DATA_FOR_BACKTEST:
        dhan = connect_to_dhan()
        if dhan is None:
            return
    df = market_data.get_historical_data(dhan, get_security_id(config.INDEX_TO_TRADE), use_mock_data=config.USE_MOCK_DATA_FOR_BACKTEST)
    if df is not None:
        df = market_data.calculate_indicators(df)
        trades_df = backtest.run_backtest(df, strategy.check_strategy_conditions, backtest.place_order_mock, order_management.check_trailing_stop_loss)
        backtest.export_to_excel(trades_df)

def main():
    """
    Main function to initialize and run the trading bot.
    """
    if config.LIVE_TRADING:
        dhan = connect_to_dhan()
        if dhan:
            security_id = get_security_id(config.INDEX_TO_TRADE)
            current_position = None

            # Use a deque to store a fixed number of 5-minute candles for indicator calculation
            max_candles = config.BB_LENGTH + 5 # Keep a few extra candles
            historical_data = deque(maxlen=max_candles)
            one_minute_candles = []

            while True:
                latest_candle = market_data.get_latest_candle(dhan, security_id)
                if latest_candle is not None:
                    one_minute_candles.append(latest_candle.iloc[0])

                    if len(one_minute_candles) == 5:
                        # Resample to 5-minute candles
                        df_5min = pd.DataFrame(one_minute_candles)
                        ohlc_dict = {
                            'open': 'first',
                            'high': 'max',
                            'low': 'min',
                            'close': 'last',
                            'volume': 'sum'
                        }
                        df_5min = df_5min.resample('5T').apply(ohlc_dict).dropna()

                        if not df_5min.empty:
                            historical_data.append(df_5min.iloc[0])
                            df = pd.DataFrame(list(historical_data))
                            df = market_data.calculate_indicators(df)

                            if len(df) > config.BB_LENGTH:
                                if current_position is None:
                                    signal = strategy.check_strategy_conditions(df, len(df)-1)
                                    if signal:
                                        print(f"Signal found: {signal}")
                                        option_type = 'CALL' if signal == 'BUY_CALL' else 'PUT'
                                        strike_price = order_management.get_otm_strike(df.iloc[-1]['close'], option_type)
                                        option_security_id = order_management.get_option_security_id(dhan, security_id, strike_price, option_type)
                                        if option_security_id:
                                            current_position = order_management.place_order(dhan, signal, option_security_id)
                                else:
                                    option_price = order_management.get_option_price(dhan, current_position['security_id'], df.iloc[-1]['close'], current_position['strike'], current_position['type'])
                                    if option_price is not None:
                                        stop_loss_triggered, current_position = order_management.check_trailing_stop_loss(current_position, option_price)
                                        if stop_loss_triggered:
                                            print("Exiting position")
                                            order_management.place_sell_order(dhan, current_position['security_id'])
                                            current_position = None

                        one_minute_candles = []

                time.sleep(60) # Wait for 1 minute
    else:
        run_backtest_and_export()

if __name__ == "__main__":
    main()
