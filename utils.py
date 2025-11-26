from datetime import date, timedelta
import config

def get_nearest_expiry():
    """
    Finds the nearest weekly expiry date for the selected index.
    """
    today = date.today()
    expiry_day = config.EXPIRY_DAY[config.INDEX_TO_TRADE]
    days_ahead = expiry_day - today.weekday()
    if days_ahead < 0:
        days_ahead += 7
    return today + timedelta(days=days_ahead)
