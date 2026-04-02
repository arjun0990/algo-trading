from strategies.instant_entry_engine import ManualEntryStrategy
from strategies.instant_exit_engine import PositionExitEngine

class CombinedInstantEngine:


 def __init__(self):


    # Exit engine (handles ALL exits)
    self.exit_engine = PositionExitEngine()

    # Entry engine (keyboard/manual/API entries)
    self.entry_engine = ManualEntryStrategy(self.exit_engine)



# -------------------------------------------------
# MAIN ENGINE LOOP
# -------------------------------------------------

 def run(self, broker, market_data, risk_engine, instruments):

    # ENTRY ENGINE
    self.entry_engine.run(
        broker,
        market_data,
        risk_engine,
        instruments
    )

    # EXIT ENGINE
    self.exit_engine.run(
        broker,
        market_data,
        risk_engine,
        instruments
    )

