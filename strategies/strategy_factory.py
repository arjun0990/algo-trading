
def get_strategy(strategy_name: str):

    name = strategy_name.upper()


    if name == "INSTANT_FIRE":
        from strategies.instant_fire import InstantFireStrategy
        return InstantFireStrategy()

    raise ValueError(f"Invalid ACTIVE_STRATEGY in config.py: {strategy_name}")
