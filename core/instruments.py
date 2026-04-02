import csv
import gzip
import shutil
import sys
import json
import os
import requests
from datetime import datetime
from core.utils import log
from config import ACTIVE_INDEX, INDEX_CONFIG

INSTRUMENT_FILE = "complete.json"
INSTRUMENT_URL = "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"
FILTER_PREFIX = "nifsen_"
class InstrumentManager:

    def __init__(self):
        self.ensure_instrument_file()
        # create or load filtered file
        self.ensure_filtered_file()
        # Option lookup cache
        self.option_lookup = {}

        # Build lookup once
        self.build_option_cache()
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

            with open("complete.json.gz", "wb") as f:
                f.write(r.content)

            with gzip.open("complete.json.gz", "rb") as f_in:
                with open(INSTRUMENT_FILE, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)

    def ensure_filtered_file(self):

        today = datetime.today().strftime("%Y%m%d")
        self.filtered_file = f"{FILTER_PREFIX}{today}.json"

        # -------------------------------------------------
        # If today's file already exists → reuse it
        # -------------------------------------------------
        if os.path.exists(self.filtered_file):
            log(f"[INSTRUMENT] Using cached option file {self.filtered_file}")
            return

        # -------------------------------------------------
        # Remove old filtered files (previous days)
        # -------------------------------------------------
        for f in os.listdir("."):

            if f.startswith(FILTER_PREFIX) and f.endswith(".json"):

                # Extra safety: never delete today's file
                if f == self.filtered_file:
                    continue

                try:
                    os.remove(f)
                    log(f"[INSTRUMENT] Removed old filtered file {f}")
                except Exception as e:
                    log(f"[INSTRUMENT] Could not remove {f}: {e}")

        log("[INSTRUMENT] Creating filtered NIFTY/SENSEX option file...")

        filtered = []

        with open(INSTRUMENT_FILE, encoding="utf-8") as f:

            data = json.load(f)

            for row in data:

                try:

                    # Keep only options
                    if row.get("instrument_type") not in ("CE", "PE"):
                        continue

                    # Keep only NIFTY or SENSEX
                    if row.get("name") not in ("NIFTY", "SENSEX"):
                        continue

                    filtered.append(row)

                except:
                    continue

        with open(self.filtered_file, "w", encoding="utf-8") as f:
            json.dump(filtered, f)

        log(f"[INSTRUMENT] Filtered instruments saved → {self.filtered_file}")

    # def ensure_filtered_file(self):
    #
    #     today = datetime.today().strftime("%Y%m%d")
    #     self.filtered_file = f"{FILTER_PREFIX}{today}.json"
    #
    #     # file already exists → reuse
    #     if os.path.exists(self.filtered_file):
    #         log(f"[INSTRUMENT] Using cached option file {self.filtered_file}")
    #         return
    #
    #     log("[INSTRUMENT] Creating filtered NIFTY/SENSEX option file...")
    #
    #     filtered = []
    #
    #     with open(INSTRUMENT_FILE, encoding="utf-8") as f:
    #
    #         data = json.load(f)
    #
    #         for row in data:
    #
    #             try:
    #
    #                 # keep only options
    #                 if row.get("instrument_type") not in ("CE", "PE"):
    #                     continue
    #
    #                 # keep only NIFTY or SENSEX
    #                 if row.get("name") not in ("NIFTY", "SENSEX"):
    #                     continue
    #
    #                 filtered.append(row)
    #
    #             except:
    #                 continue
    #
    #     with open(self.filtered_file, "w", encoding="utf-8") as f:
    #         json.dump(filtered, f)
    #
    #     log(f"[INSTRUMENT] Filtered instruments saved → {self.filtered_file}")

    # ==========================
    # BUILD OPTION CACHE
    # ==========================
    def build_option_cache(self):

        log("[INSTRUMENT] Building option lookup cache...")

        with open(self.filtered_file, encoding="utf-8") as f:

            data = json.load(f)

            for row in data:

                try:

                    expiry_date = datetime.fromtimestamp(
                        row["expiry"] / 1000
                    ).strftime("%Y-%m-%d")

                    key = (
                        row["segment"],
                        row["name"],
                        expiry_date,
                        float(row["strike_price"]),
                        row["instrument_type"]
                    )

                    token = row["instrument_key"].split("|")[1]
                    lot = int(row["lot_size"])

                    self.option_lookup[key] = (token, lot)

                except:
                    continue
        log(f"[INSTRUMENT] Cache loaded → {len(self.option_lookup)} instruments")

    # ==========================
    # GET NEAREST EXPIRY
    # ==========================
    def get_nearest_expiry(self, symbol_name=ACTIVE_INDEX):

        expiries = set()

        with open(self.filtered_file, encoding="utf-8") as f:

            data = json.load(f)

            for row in data:

                try:

                    if row.get("name") != symbol_name:
                        continue

                    expiry_epoch = row.get("expiry")

                    if not expiry_epoch:
                        continue

                    expiry_date = datetime.fromtimestamp(
                        expiry_epoch / 1000
                    ).date()

                    expiries.add(expiry_date)

                except:
                    continue

        if not expiries:
            log("[INSTRUMENT] No option expiries found in instrument file")
            return None

        today = datetime.today().date()

        valid = sorted(e for e in expiries if e >= today)

        if not valid:
            log("[INSTRUMENT] No valid future expiries found")
            return None

        return valid[0].strftime("%Y-%m-%d")

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
    def find_option(self, expiry, strike, option_type, symbol_name=ACTIVE_INDEX):

        exchange = INDEX_CONFIG[ACTIVE_INDEX]["segment"]

        key = (
            exchange,
            symbol_name,
            expiry,
            float(strike),
            option_type
        )

        result = self.option_lookup.get(key)

        if result:
            return result

        return None, None
