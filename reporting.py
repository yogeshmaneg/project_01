import pandas as pd
import numpy as np

def generate_report(trades, output_filename="backtest_report.xlsx"):
    """
    Generates a detailed Excel report from a list of trades.

    Args:
        trades (list): A list of trade dictionaries from the backtester.
        output_filename (str): The name of the Excel file to generate.
    """
    if not trades:
        print("No trades to generate a report for.")
        return

    df_trades = pd.DataFrame(trades)
    df_trades['pnl_percent'] = (df_trades['pnl'] / df_trades['entry_price']) * 100

    # --- Performance Metrics ---
    total_trades = len(df_trades)
    winning_trades = df_trades[df_trades['pnl'] > 0]
    losing_trades = df_trades[df_trades['pnl'] <= 0]

    win_rate = (len(winning_trades) / total_trades) * 100 if total_trades > 0 else 0

    gross_profit = winning_trades['pnl'].sum()
    gross_loss = abs(losing_trades['pnl'].sum())

    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

    # Simplified Sharpe Ratio (assuming risk-free rate is 0)
    avg_return = df_trades['pnl_percent'].mean()
    std_dev_return = df_trades['pnl_percent'].std()
    sharpe_ratio = (avg_return / std_dev_return) * np.sqrt(252) if std_dev_return > 0 else 0 # Annualized

    summary = {
        'Total Trades': total_trades,
        'Winning Trades': len(winning_trades),
        'Losing Trades': len(losing_trades),
        'Win Rate (%)': f"{win_rate:.2f}",
        'Gross Profit': f"{gross_profit:.2f}",
        'Gross Loss': f"{gross_loss:.2f}",
        'Net Profit': f"{(gross_profit - gross_loss):.2f}",
        'Profit Factor': f"{profit_factor:.2f}",
        'Sharpe Ratio (Annualized)': f"{sharpe_ratio:.2f}"
    }
    df_summary = pd.DataFrame([summary])

    # --- Daily P&L ---
    df_trades['exit_date'] = df_trades['exit_time'].dt.date
    daily_pnl = df_trades.groupby('exit_date')['pnl'].sum().reset_index()

    # --- Export to Excel ---
    with pd.ExcelWriter(output_filename, engine='openpyxl') as writer:
        df_summary.to_excel(writer, sheet_name='Performance Summary', index=False)
        df_trades.to_excel(writer, sheet_name='All Trades', index=False)
        daily_pnl.to_excel(writer, sheet_name='Daily PnL', index=False)

    print(f"Report generated: {output_filename}")
    print("\n--- Performance Summary ---")
    print(df_summary.to_string(index=False))


if __name__ == '__main__':
    # Use the backtester with dummy data to get a sample list of trades
    from backtest import run_backtest
    import config

    nifty_50 = config.INDICES["NIFTY_50"]
    sample_trades = run_backtest(nifty_50, 5, None, None, use_dummy_data=True)

    if sample_trades:
        generate_report(sample_trades)
