import pandas as pd
from datetime import datetime, timedelta
import config
import market_data
import strategy

def _get_option_price(underlying_price, strike_price, option_type, expiry_date, current_date):
    """
    (Placeholder) Simulates the approximate price of an option contract.

    NOTE: This is a highly simplified model for backtesting purposes only.
    It does NOT use a standard pricing model like Black-Scholes and does not
    account for critical factors like implied volatility ("vega"), interest
    rates ("rho"), or the rate of time decay ("theta").

    This function should NOT be used for live trading.
    """
    intrinsic_value = 0
    if option_type == 'CALL':
        intrinsic_value = max(0, underlying_price - strike_price)
    elif option_type == 'PUT':
        intrinsic_value = max(0, strike_price - underlying_price)

    days_to_expiry = max(1, (expiry_date - current_date.date()).days)
    time_value = 10 * (days_to_expiry / 7) # Simplified time decay premium

    return intrinsic_value + time_value

def _generate_dummy_data():
    """Generates a dummy DataFrame for testing the backtester."""
    print("Generating dummy data for backtest...")
    base_price = 20000
    data = []
    dates = pd.date_range(start="2023-01-01", periods=500, freq='5min') # Corrected frequency

    for i in range(500):
        price_movement = i % 100
        if i // 100 % 2 == 0: # Upward trend
            price = base_price + price_movement
        else: # Downward trend
            price = base_price + 100 - price_movement

        data.append({
            'datetime': dates[i],
            'open': price - 2,
            'high': price + 2,
            'low': price - 3,
            'close': price,
            'volume': 10000 + (i * 10)
        })

    df = pd.DataFrame(data)
    df.set_index('datetime', inplace=True)
    return df

def run_backtest(instrument, timeframe, from_date, to_date, use_dummy_data=False):
    """
    Runs a backtest for a given instrument and timeframe.
    Returns both the list of trades and the DataFrame with signals.
    """
    print(f"\n--- Running Backtest for {instrument['security_id']} ({timeframe}min) ---")

    if use_dummy_data:
        df = _generate_dummy_data()
    else:
        df = market_data.get_historical_data(instrument, timeframe, from_date, to_date)

    if df.empty:
        print("No historical data to backtest.")
        return [], pd.DataFrame()

    df_with_signals = strategy.generate_signals(df)

    trades = []
    active_trade = None

    for i in range(1, len(df_with_signals)):
        current_candle = df_with_signals.iloc[i]

        if active_trade:
            exit_option_price = _get_option_price(
                current_candle['close'], active_trade['strike_price'], active_trade['option_type'],
                active_trade['expiry_date'], current_candle.name
            )
            pnl = (exit_option_price - active_trade['entry_price']) if active_trade['option_type'] == 'CALL' else (active_trade['entry_price'] - exit_option_price)
            pnl_percent = pnl / active_trade['entry_price']

            exit_reason = None
            if pnl_percent <= -config.STOP_LOSS_PERCENT: exit_reason = "SL"
            elif pnl_percent >= config.TAKE_PROFIT_PERCENT: exit_reason = "TP"
            elif active_trade['option_type'] == 'CALL' and current_candle['sell_signal']: exit_reason = "Signal"
            elif active_trade['option_type'] == 'PUT' and current_candle['buy_signal']: exit_reason = "Signal"

            if exit_reason:
                active_trade.update({
                    'exit_price': exit_option_price, 'exit_time': current_candle.name,
                    'pnl': pnl, 'exit_reason': exit_reason
                })
                trades.append(active_trade)
                active_trade = None

        if not active_trade:
            option_type = 'CALL' if current_candle['buy_signal'] else 'PUT' if current_candle['sell_signal'] else None
            if option_type:
                strike_price = round(current_candle['close'] / 100) * 100 + (100 if option_type == 'CALL' else -100)
                expiry_date = current_candle.name.date() + timedelta(days=(3 - current_candle.name.weekday() + 7) % 7)
                entry_price = _get_option_price(
                    current_candle['close'], strike_price, option_type, expiry_date, current_candle.name
                )
                active_trade = {
                    'entry_time': current_candle.name, 'instrument': instrument['security_id'],
                    'option_type': option_type, 'strike_price': strike_price,
                    'expiry_date': expiry_date, 'entry_price': entry_price,
                    'pnl': 0, 'exit_reason': None
                }

    print(f"Backtest complete. Found {len(trades)} trades.")
    return trades, df_with_signals

if __name__ == '__main__':
    nifty_50 = config.INDICES["NIFTY_50"]
    trades, _ = run_backtest(nifty_50, 5, None, None, use_dummy_data=True)

    if trades:
        print("\n--- Trades ---")
        for trade in trades:
            print(f"  Entry: {trade['entry_time']} @ {trade['entry_price']:.2f}, Type: {trade['option_type']}")
            print(f"  Exit:  {trade['exit_time']} @ {trade['exit_price']:.2f}, Reason: {trade['exit_reason']}")
            print(f"  PnL:   {trade['pnl']:.2f}\n")
