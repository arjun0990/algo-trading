import csv
import gzip
import shutil
import sys

import requests
from datetime import datetime
from core.utils import log


INSTRUMENT_FILE = "complete.csv"
INSTRUMENT_URL = "https://assets.upstox.com/market-quote/instruments/exchange/complete.csv.gz"


class InstrumentManager:

    def __init__(self):
        self.ensure_instrument_file()

    # ==========================
    # DOWNLOAD MASTER IF NEEDED
    # ==========================
    def ensure_instrument_file(self):
        try:
            open(INSTRUMENT_FILE)
        except:
            log("Downloading instrument master...")
            r = requests.get(INSTRUMENT_URL)
            if r.status_code != 200:
                log("CRITICAL: Instrument download failed")
                sys.exit()

            with open("complete.csv.gz", "wb") as f:
                f.write(r.content)

            with gzip.open("complete.csv.gz", "rb") as f_in:
                with open(INSTRUMENT_FILE, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)

    # ==========================
    # GET NEAREST EXPIRY
    # ==========================
    def get_nearest_expiry(self, symbol_name="NIFTY"):
        expiries = set()

        with open(INSTRUMENT_FILE, newline='', encoding="utf-8") as file:
            reader = csv.DictReader(file)
            for row in reader:
                if row["name"] == symbol_name and row["exchange"] == "NSE_FO":
                    expiries.add(row["expiry"])

        today = datetime.today().date()

        valid = sorted(
            datetime.strptime(e, "%Y-%m-%d").date()
            for e in expiries
            if datetime.strptime(e, "%Y-%m-%d").date() >= today
        )
        # print("VALID IS ", valid)
        return valid[0].strftime("%Y-%m-%d") if valid else None

    def get_atm_strike(self, symbol_name, market_data):
        """
        Returns ATM strike rounded to nearest 50.
        """

        ltp = market_data.get_ltp("NSE_INDEX|Nifty 50")

        if not ltp:
            return None

        return round(ltp / 50) * 50

    # ==========================
    # FIND OPTION CONTRACT
    # ==========================
    def find_option(self, expiry, strike, option_type, symbol_name="NIFTY"):

        with open(INSTRUMENT_FILE, newline='', encoding="utf-8") as file:
            reader = csv.DictReader(file)

            for row in reader:
                if (
                        row["exchange"] == "NSE_FO"
                        and row["name"] == symbol_name
                        and row["expiry"] == expiry
                        and float(row["strike"]) == strike
                        and row["option_type"] == option_type
                ):
                    token = row["instrument_key"].split("|")[1]
                    return token, int(row["lot_size"])

        return None, None