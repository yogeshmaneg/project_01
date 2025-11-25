from datetime import date, timedelta

def get_nearest_expiry():
    """
    Finds the nearest weekly expiry date (Thursday).
    """
    today = date.today()
    days_ahead = 3 - today.weekday() # 3 = Thursday
    if days_ahead < 0:
        days_ahead += 7
    return today + timedelta(days=days_ahead)
