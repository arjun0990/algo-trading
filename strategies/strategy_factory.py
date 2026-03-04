from config import AUTO_EXIT_GTT_CONFIG
from strategies.bounce_strategy import BounceStrategy
from strategies.pivot_session_strategy import PivotSessionStrategy
from strategies.auto_exit_gtt_strategy import AutoExitGTTStrategy

def get_strategy(strategy_name: str):

    name = strategy_name.upper()

    if name == "BOUNCE":
        return BounceStrategy()

    if name == "PIVOT":
        return PivotSessionStrategy()

    if name == "GTT":
        from strategies.catch_gtt_order_strategy import ManualGTTStrategy
        return ManualGTTStrategy()

    if name == "AUTO_EXIT_GTT":
        return AutoExitGTTStrategy()

    if name == "COMBINED_GTT":
        from strategies.combined_gtt_strategy import CombinedGTTStrategy
        return CombinedGTTStrategy()

    raise ValueError(f"Invalid ACTIVE_STRATEGY in config.py: {strategy_name}")