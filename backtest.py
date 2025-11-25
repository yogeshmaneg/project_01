import pandas as pd
import order_management
import config
from pricing import black_scholes, get_time_to_expiry

def place_order_mock(signal, current_price):
    """
    Simulates placing an order for backtesting purposes.
    """
    option_type = 'CALL' if signal == 'BUY_CALL' else 'PUT'
    strike_price = order_management.get_otm_strike(current_price, option_type)
    return {'type': option_type, 'strike': strike_price}

def run_backtest(df, strategy_func, order_func, stop_loss_func):
    """
    Runs a backtest of the trading strategy and returns a DataFrame of the trades.

    NOTE: This backtest is a simplified simulation and has several limitations:
    - It does not account for transaction costs (brokerage, taxes, etc.).
    - It does not account for slippage.
    - The options pricing model is a simplified Black-Scholes implementation with
      constant volatility, which may not accurately reflect real market prices.
    """
    trades = []
    current_position = None

    for i in range(1, len(df)):
        underlying_price = df.iloc[i]['close']
        trade_date = df.index[i]
        time_to_expiry = get_time_to_expiry(trade_date)

        if current_position is None:
            signal = strategy_func(df, i)
            if signal:
                option_type = 'call' if signal == 'BUY_CALL' else 'put'
                strike_price = order_func(signal, underlying_price)['strike']
                entry_price = black_scholes(underlying_price, strike_price, time_to_expiry, config.RISK_FREE_RATE, config.VOLATILITY, option_type)

                current_position = order_func(signal, underlying_price)
                current_position['entry_price'] = entry_price
                current_position['highest_price'] = entry_price

                trades.append({
                    'entry_date': trade_date,
                    'entry_price': entry_price,
                    'signal': signal,
                    'strike': current_position['strike'],
                    'exit_date': None,
                    'exit_price': None,
                    'pnl': None
                })
        else:
            option_type = 'call' if current_position['type'] == 'CALL' else 'put'
            option_price = black_scholes(underlying_price, current_position['strike'], time_to_expiry, config.RISK_FREE_RATE, config.VOLATILITY, option_type)
            stop_loss_triggered, current_position = stop_loss_func(current_position, option_price)
            if stop_loss_triggered:
                trades[-1]['exit_date'] = trade_date
                trades[-1]['exit_price'] = option_price
                trades[-1]['pnl'] = option_price - trades[-1]['entry_price']
                current_position = None

    return pd.DataFrame(trades)

def export_to_excel(df, filename='backtest_results.xlsx'):
    """
    Exports a DataFrame to an Excel file.
    """
    df.to_excel(filename)
    print(f"Backtest results exported to {filename}")
