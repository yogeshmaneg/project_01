from scipy.stats import norm
import numpy as np
import config
from datetime import datetime, date, timedelta

def get_time_to_expiry(trade_date):
    """
    Calculates the time to expiry for a weekly option.
    """
    today = trade_date.date()
    expiry_day_of_week = config.EXPIRY_DAY[config.INDEX_TO_TRADE]
    days_ahead = expiry_day_of_week - today.weekday()
    if days_ahead < 0:
        days_ahead += 7

    expiry_day = today + timedelta(days=days_ahead)
    expiry_date = datetime.combine(expiry_day, datetime.min.time()).replace(hour=15, minute=30)

    time_diff = expiry_date - trade_date
    return max(time_diff.days / 365.25, 1/365.25) # Ensure T is not zero

def black_scholes(S, K, T, r, sigma, option_type='call'):
    """
    Calculates the Black-Scholes option price.
    """
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)

    if option_type == 'call':
        price = (S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2))
    elif option_type == 'put':
        price = (K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1))
    else:
        raise ValueError("Invalid option type. Must be 'call' or 'put'.")

    return price
