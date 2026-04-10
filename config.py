

import json

# =========================================================
# 🧭 INDEX CONFIGURATION
# =========================================================

# Select which index the engine will trade
ACTIVE_INDEX = "NIFTY"
# Options:
# "NIFTY"
# "SENSEX"

# =========================================================
# 🔁 STRATEGY SELECTION
# =========================================================

ACTIVE_STRATEGY = "INSTANT_FIRE"
# Options:
# INSTANT_FIRE
# "BOUNCE"
# COMBINED_GTT
# "GTT"
# INSTANT_EXPIRY_BLAST
# COMBINED_INSTANT_ENGINE
# AUTO_EXIT_GTT
# "PIVOT"

INDEX_CONFIG = {

    "NIFTY": {

        "segment": "NSE_FO",

        # Index price source
        "index_symbol": "NSE_INDEX|Nifty 50",

        # Option contract details
        "strike_step": 50,
        "lot_size": 65,

        # GTT limit
        "max_gtt_quantity": 17550,
        "atm_shift_threshold": 500
    },

    "SENSEX": {

        "segment": "BSE_FO",

        # Index price source
        "index_symbol": "BSE_INDEX|SENSEX",

        # Option contract details
        "strike_step": 100,
        "lot_size": 20,

        # GTT limit
        "max_gtt_quantity": 10020,
        "atm_shift_threshold": 1500
    }
}

# =========================================================
# 🔐 BROKER AUTHENTICATION
# =========================================================

def load_access_token():
    try:
        with open("token.json", "r") as f:
            data = json.load(f)
            return data["access_token"]
    except Exception:
        raise Exception("Token file not found. Run generate_token.py first.")

ACCESS_TOKEN = load_access_token()

# =========================================================
# 🛡 GLOBAL ENGINE SETTINGS (Shared Across All Strategies)
# =========================================================

GLOBAL_CONFIG = {

    # -----------------------------------------------------
    # Core Exchange Settings
    # -----------------------------------------------------
    "lot_size": 65,
    # Risk Protection
    # "enable_global_pnl_guard": True,
    # "max_daily_loss": -5000,
    # "max_daily_profit": 10000,


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
    "entry_buffe": 0,
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
    "strike_offset": 150,

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
    "target_points": 1,
    "sl_points": 30,

    # Optional Trailing Stop
    "enable_trailing": False,
    "trailing_points": 10,

    # Polling Control
    "position_check_interval": 2  # seconds
}

# =========================================================
# ⚡ INSTANT EXPIRY BLAST STRATEGY CONFIG
# =========================================================

INSTANT_EXPIRY_BLAST_CONFIG = {

    # Liquidity detection
    "liquidity_lookback_minutes": 15,

    # Compression detection
    "compression_factor": 0.6,
    "volume_factor": 1.5,

    # Premium acceleration
    "premium_acceleration_pct": 0.2,
    "acceleration_window_sec": 5,

    # Volume surge confirmation
    "volume_surge_factor": 2,

    # Strike scanning
    "strike_scan_range": 500,
    "use_fixed_offsets": False,
    "strike_offsets": [300],

    # Filters
    "min_option_premium": 3,
    "enable_spread_filter": False,

    # Exit logic
    "fixed_spike_points": 10,
    "percent_spike_target": 0.08
}

# =========================================================
# 🔵 STREAMING CONFIG (WebSocket Clone Only)
# =========================================================

ENABLE_STREAMING = True   # Set True to enable WebSocket engine
STREAM_CONFIG = {
    "heartbeat_timeout_seconds": 30
}

OPTION_INTEL_CONFIG = {

    # -------------------------
    # RANGE
    # -------------------------
    "strike_range": 300,   # ✅ reduced (focus on real action)

    # -------------------------
    # LIQUIDITY FILTERS
    # -------------------------
    "min_oi": 200,        # ✅ was too low
    "min_volume": 50,     # ✅ remove noise

    # -------------------------
    # SPIKE DETECTION
    # -------------------------
    "volume_spike_threshold": 1.6,   # ✅ tuned from data

    # -------------------------
    # WEIGHTS (REBALANCED)
    # -------------------------
    "gamma_weight": 0.30,   # 🔥 gamma dominant market
    "delta_weight": 0.20,
    "oi_weight": 0.25,      # 🔥 OI very important
    "volume_weight": 0.15,
    "structure_weight": 0.10,

    # -------------------------
    # GAMMA LOGIC
    # -------------------------
    "gamma_flip_threshold": 0,

    # -------------------------
    # SIGNAL THRESHOLDS
    # -------------------------
    "breakout_score": 70,    # 🔥 earlier detection
    "strength_threshold": 55, # 🔥 faster entries

    # -------------------------
    # AUTO TRADE
    # -------------------------
    "auto_trade": False,
}

# =========================================================
# ⚡ INSTANT ENGINE STRATEGY CONFIG
# =========================================================

INSTANT_ENGINE_CONFIG = {

    # Position sizing (for keypress trades)
    "lots": 1,

    # Strike selection
    "strike_offset": 0,

    # Entry price buffer (below best ask)x
    "entry_buffer": 0.9,
    # Exit configuration
    "target_points": 1.8,
    "sl_points": 15,

    # Entry timeout
    "entry_timeout_ms": 900,

    # Console position stabilization
    "stabilization_ms": 150,

    # Risk Protection===
    "enable_global_pnl_guard": False,
    "enable_trade_loss_guard": False,
    "max_daily_loss": -5000,
    "max_daily_profit": 10000,
    "max_trade_loss": -1500,   # per trade loss
}
