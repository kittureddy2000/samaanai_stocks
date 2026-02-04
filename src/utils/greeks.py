"""Black-Scholes option Greeks calculator.

Computes Delta, Gamma, Theta, and Vega for European-style options
using the Black-Scholes model. Used by the option chain API endpoint
to enrich yfinance option data with computed Greeks.
"""

import math
from scipy.stats import norm


def black_scholes_greeks(
    option_type: str,
    stock_price: float,
    strike_price: float,
    time_to_expiry: float,
    risk_free_rate: float,
    implied_volatility: float,
) -> dict:
    """Calculate Black-Scholes Greeks for a European option.

    Args:
        option_type: 'call' or 'put'
        stock_price: Current underlying stock price
        strike_price: Option strike price
        time_to_expiry: Time to expiration in years (e.g. 30 days = 30/365)
        risk_free_rate: Risk-free interest rate as decimal (e.g. 0.045 for 4.5%)
        implied_volatility: IV as decimal (e.g. 0.25 for 25%)

    Returns:
        Dict with keys: delta, gamma, theta (per day), vega (per 1% IV change).
        Returns None for all if inputs are invalid.
    """
    null_result = {'delta': None, 'gamma': None, 'theta': None, 'vega': None}

    # Guard against invalid inputs
    if (time_to_expiry <= 0 or stock_price <= 0 or strike_price <= 0
            or implied_volatility <= 0):
        return null_result

    try:
        sqrt_t = math.sqrt(time_to_expiry)
        vol_sqrt_t = implied_volatility * sqrt_t

        # d1 and d2
        d1 = (math.log(stock_price / strike_price)
              + (risk_free_rate + 0.5 * implied_volatility ** 2) * time_to_expiry
              ) / vol_sqrt_t
        d2 = d1 - vol_sqrt_t

        # Standard normal CDF and PDF
        n_d1 = norm.pdf(d1)
        discount = math.exp(-risk_free_rate * time_to_expiry)

        is_call = option_type.lower() == 'call'

        # Delta
        if is_call:
            delta = norm.cdf(d1)
        else:
            delta = norm.cdf(d1) - 1

        # Gamma (same for call and put)
        gamma = n_d1 / (stock_price * vol_sqrt_t)

        # Theta (per calendar day)
        common_theta = -(stock_price * n_d1 * implied_volatility) / (2 * sqrt_t)
        if is_call:
            theta = (common_theta
                     - risk_free_rate * strike_price * discount * norm.cdf(d2)) / 365
        else:
            theta = (common_theta
                     + risk_free_rate * strike_price * discount * norm.cdf(-d2)) / 365

        # Vega (per 1% change in IV)
        vega = stock_price * n_d1 * sqrt_t / 100

        return {
            'delta': round(delta, 4),
            'gamma': round(gamma, 6),
            'theta': round(theta, 4),
            'vega': round(vega, 4),
        }

    except (ValueError, ZeroDivisionError, OverflowError):
        return null_result
