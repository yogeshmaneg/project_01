import pandas as pd
import config
from pricing import black_scholes, get_time_to_expiry
from datetime import datetime
from utils import get_nearest_expiry

def get_option_security_id(dhan, underlying_security_id, strike_price, option_type):
    """
    Fetches the option chain and returns the security ID for the given strike and type.
    """
    if dhan is None:
        print("Dhan API client is not initialized.")
        return None

    try:
        # This will fail with a placeholder client_id, which is expected.
        expiry_date = get_nearest_expiry().strftime('%Y-%m-%d')
        response = dhan.get_option_chain(
            security_id=str(underlying_security_id),
            expiry_date=expiry_date
        )

        for option in response['data']:
            if option['strike_price'] == strike_price and option['option_type'] == option_type:
                return option['security_id']

        return None
    except Exception as e:
        print(f"Failed to get option security ID: {e}")
        return None

def get_otm_strike(current_price, option_type, index=config.INDEX_TO_TRADE):
    """
    Calculates the +1 OTM strike price.
    """
    strike_difference = config.STRIKE_DIFFERENCE[index]
    if option_type == 'CALL':
        return (current_price // strike_difference + 1) * strike_difference
    elif option_type == 'PUT':
        return (current_price // strike_difference) * strike_difference - strike_difference

def place_sell_order(dhan, security_id):
    """
    Places a market sell order on DhanHQ to exit a position.
    """
    if dhan is None:
        print("Dhan API client is not initialized.")
        return None

    try:
        # This will fail with a placeholder client_id, which is expected.
        response = dhan.place_order(
            security_id=str(security_id),
            exchange_segment=config.EXCHANGE_SEGMENT[config.INDEX_TO_TRADE],
            transaction_type='SELL',
            quantity=1,
            order_type='MARKET',
            product_type='INTRA',
            price=0
        )
        print(f"Sell order placement response: {response}")
        return response
    except Exception as e:
        print(f"Failed to place sell order: {e}")
        return None

def place_order(dhan, signal, security_id):
    """
    Places a market order on DhanHQ.
    """
    if dhan is None:
        print("Dhan API client is not initialized.")
        return None

    try:
        # This will fail with a placeholder client_id, which is expected.
        response = dhan.place_order(
            security_id=str(security_id),
            exchange_segment=config.EXCHANGE_SEGMENT[config.INDEX_TO_TRADE],
            transaction_type='BUY',
            quantity=1,
            order_type='MARKET',
            product_type='INTRA',
            price=0
        )
        print(f"Order placement response: {response}")
        return response
    except Exception as e:
        print(f"Failed to place order: {e}")
        return None

def get_option_price(dhan, security_id, underlying_price, strike_price, option_type):
    """
    Fetches the live market price of an option.
    """
    if config.LIVE_TRADING:
        if dhan is None:
            print("Dhan API client is not initialized.")
            return None

        try:
            # This will fail with a placeholder client_id, which is expected.
            response = dhan.quote_data(security_id=str(security_id))
            return response['data']['ltp']
        except Exception as e:
            print(f"Failed to get option price: {e}")
            return None
    else:
        time_to_expiry = get_time_to_expiry(datetime.now())
        option_type_map = {'CALL': 'call', 'PUT': 'put'}
        return black_scholes(underlying_price, strike_price, time_to_expiry, config.RISK_FREE_RATE, config.VOLATILITY, option_type_map[option_type])

def check_trailing_stop_loss(position, current_price, trailing_sl_percentage=config.TRAIL_SL_PERCENT):
    """
    Checks if the trailing stop-loss has been triggered.
    """
    if position is None:
        return False, position

    # Update the highest price
    if current_price > position['highest_price']:
        position['highest_price'] = current_price

    # Check if the stop-loss is triggered
    stop_loss_price = position['highest_price'] * (1 - trailing_sl_percentage)
    if current_price < stop_loss_price:
        print(f"Trailing stop-loss triggered at: {current_price}")
        return True, position

    return False, position
