
# =========================================================
# 🔐 BROKER AUTHENTICATION
# =========================================================
import json

def load_access_token():
    try:
        with open("token.json", "r") as f:
            data = json.load(f)
            return data["access_token"]
    except Exception:
        raise Exception("Token file not found. Run generate_token.py first.")

ACCESS_TOKEN = load_access_token()

# =========================================================
# 🔁 STRATEGY SELECTION
# =========================================================

ACTIVE_STRATEGY = "COMBINED_GTT"
# Options:
# "BOUNCE"
# "PIVOT"
# COMBINED_GTT
# "GTT"
# AUTO_EXIT_GTT


# =========================================================
# 🛡 GLOBAL ENGINE SETTINGS (Shared Across All Strategies)
# =========================================================

GLOBAL_CONFIG = {

    # -----------------------------------------------------
    # Core Exchange Settings
    # -----------------------------------------------------
    "lot_size": 65,

    # -----------------------------------------------------
    # Risk Protection
    # -----------------------------------------------------
    "enable_global_pnl_guard": True,
    "max_daily_loss": -5000,
    "max_daily_profit": 100,

    # -----------------------------------------------------
    # Entry Protection
    # -----------------------------------------------------
    "entry_timeout_seconds": 20,
    "max_entry_chase": 2,

    # -----------------------------------------------------
    # Trade Duration
    # -----------------------------------------------------
    "max_trade_duration_minutes": 30,

    # -----------------------------------------------------
    # SL Buffer (for low-based SL)
    # -----------------------------------------------------
    "sl_buffer": 0.5,

    # -----------------------------------------------------
    # Order Behaviour
    # -----------------------------------------------------
    "product_type": "D",     # D = Intraday
    "validity": "DAY",

    # -----------------------------------------------------
    # Manual Exit Support
    # -----------------------------------------------------
    "manual_exit_enabled": True,
}


# =========================================================
# 🔵 BOUNCE STRATEGY CONFIG
# =========================================================

BOUNCE_CONFIG = {

    # -----------------------------------------------------
    # Position Sizing
    # -----------------------------------------------------
    "lots": 1,

    # -----------------------------------------------------
    # Strike Selection
    # -----------------------------------------------------
    "strike_offset": 0,
    "enable_ce": True,
    "enable_pe": True,

    # -----------------------------------------------------
    # Entry Logic
    # -----------------------------------------------------
    "bounce_points": 10,
    "entry_buffer": 0,
    "min_premium": 50,

    # -----------------------------------------------------
    # Spread Filter
    # -----------------------------------------------------
    "use_spread_filter": False,
    "max_spread": 2,

    # -----------------------------------------------------
    # SL Mode
    # -----------------------------------------------------
    # True  → fixed SL
    # False → low-based SL
    "use_fixed_sl": True,
    "fixed_sl_points": 2,

    # -----------------------------------------------------
    # Exit Behaviour
    # -----------------------------------------------------
    "partial_exit_enabled": False,
    "complete_exit_only": True,

    # -----------------------------------------------------
    # Time Filter
    # -----------------------------------------------------
    "no_new_trades_after_hour": 22,
    "no_new_trades_after_minute": 15,
}


# =========================================================
# 🔴 PIVOT STRATEGY CONFIG
# =========================================================

PIVOT_CONFIG = {

    # -----------------------------------------------------
    # Position Sizing
    # -----------------------------------------------------
    "lots": 1,

    # -----------------------------------------------------
    # Strike Selection
    # -----------------------------------------------------
    "strike_offset": 50,
    "enable_ce": True,
    "enable_pe": False,

    # -----------------------------------------------------
    # Pivot Engine Behaviour
    # -----------------------------------------------------
    "enable_above_pivot_trade": True,
    "enable_below_pivot_trade": True,

    # -----------------------------------------------------
    # SL Behaviour
    # -----------------------------------------------------
    "use_fixed_sl": True,
    "fixed_sl_points": 20,

    # -----------------------------------------------------
    # Exit Behaviour
    # -----------------------------------------------------
    "partial_exit_enabled": True,
    "complete_exit_only": False,

    # -----------------------------------------------------
    # Session Behaviour
    # -----------------------------------------------------
    "one_trade_per_session": True,
}

# =========================================================
# 🔴 GTT STRATEGY CONFIG
# =========================================================
GTT_CONFIG = {

    # ---------------------------------
    # Position Sizing
    # ---------------------------------
    "lots": 1,

    # ---------------------------------qe
    # Strike Configuration
    # ---------------------------------
    # 0  → ATM
    # 50 → CE = ATM + 50, PE = ATM - 50
    # 100 → CE = ATM + 100, PE = ATM - 100
    "strike_offset": 50,

    # ---------------------------------
    # Entry Configuration
    # ---------------------------------
    "entry_type": "IMMEDIATE",   # IMMEDIATE / ABOVE / BELOW

    "above_points": 5,           # Used if entry_type == ABOVE
    "below_points": 5,           # Used if entry_type == BELOW

    # ---------------------------------
    # Exit Configuration (Premium Points)
    # ---------------------------------
    "target_points": 1,
    "sl_points": 16,

    # ---------------------------------
    # Trailing Stop
    # ---------------------------------
    "enable_trailing": False,
    "trailing_points": 2,

    # ---------------------------------
    # Strike Refresh
    # ---------------------------------
    "enable_dynamic_strike": False,
    "strike_refresh_interval": 5   # seconds (dynamic strike throttle)
}

# =========================================================
# 🔴 AUTO GTT EXIT STRATEGY CONFIG
# =========================================================
AUTO_EXIT_GTT_CONFIG = {

    # Exit Logic (points from average fill price)
    "target_points": 2,
    "sl_points": 20,

    # Optional Trailing Stop
    "enable_trailing": False,
    "trailing_points": 10,

    # Polling Control
    "position_check_interval": 2  # seconds
}