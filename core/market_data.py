from datetime import datetime, timedelta
from urllib.parse import quote
from types import SimpleNamespace
import urllib.parse
from config import GTT_CONFIG, ACTIVE_INDEX, INDEX_CONFIG
class MarketData:

    def __init__(self, broker):
        self.broker = broker
        self.MARKET_OPEN_HOUR = 9
        self.MARKET_OPEN_MINUTE = 15
        self.MARKET_CLOSE_HOUR = 15
        self.MARKET_CLOSE_MINUTE = 30


        # ==========================
    # GET LTP FOR ANY INSTRUMENT
    # ==========================
    def get_ltp(self, instrument_key):

        # If already fully qualified (contains exchange)
        if "|" in instrument_key:
            key = instrument_key
        else:
            key = f"{INDEX_CONFIG[ACTIVE_INDEX]['segment']}|{instrument_key}"

        data = self.broker.safe_request(
            "GET",
            f"{self.broker.BASE_URL}/market-quote/ltp",
            params={"instrument_key": key}
        )

        if data.get("status") == "success":
            return list(data["data"].values())[0]["last_price"]

        return None

    def is_market_live(self):
        now = datetime.now()

        market_open = now.replace(
            hour=self.MARKET_OPEN_HOUR,
            minute=self.MARKET_OPEN_MINUTE,
            second=0,
            microsecond=0
        )

        market_close = now.replace(
            hour=self.MARKET_CLOSE_HOUR,
            minute=self.MARKET_CLOSE_MINUTE,
            second=0,
            microsecond=0
        )

        return market_open <= now <= market_close

    # ==========================
    # GET FULL QUOTE
    # ==========================

    def get_full_quote(self, instrument_key):
        print("Requesting full quote for:", instrument_key)

        url = f"https://api.upstox.com/v2/market-quote/quotes?instrument_key={instrument_key}"
        print(url)
        # Must send as comma-separated string (even single instrument)
        if "|" in instrument_key:
            symbol = instrument_key
        else:
            symbol = f"{INDEX_CONFIG[ACTIVE_INDEX]['segment']}|{instrument_key}"

        params = {"symbol": symbol}


        # print("DEBUG URL:", url)
        # print("DEBUG PARAMS:", params)

        data = self.broker.safe_request("GET", url, params=params)

        if data.get("status") == "success":
            q = list(data["data"].values())[0]

            return (
                q.get("last_price"),
                q.get("ohlc", {}).get("high"),
                q.get("depth", {}).get("buy", [{}])[0].get("price"),
                q.get("depth", {}).get("sell", [{}])[0].get("price"),
            )

        return None, None, None, None

    def is_market_live(self):
        now = datetime.now()

        market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
        market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)

        return market_open <= now <= market_close

    def get_last_completed_trading_day(self):
        today = datetime.now().date()

        if self.is_market_live():
            return today

        # If not live, go to previous trading day
        prev_day = today - timedelta(days=1)

        while prev_day.weekday() >= 5:  # Skip weekend
            prev_day -= timedelta(days=1)

        return prev_day

    def get_last_n_minutes(self, instrument_key, minutes_back=20):

        from datetime import datetime, timedelta
        if "|" in instrument_key:
            key = instrument_key
        else:
            key = f"{INDEX_CONFIG[ACTIVE_INDEX]['segment']}|{instrument_key}"
        if self.is_market_live():
            # 🔵 LIVE MARKET
            url = f"{self.broker.BASE_URL}/historical-candle/intraday/{key}/minutes/1"
            data = self.broker.safe_request("GET", url)

            if data.get("status") != "success":
                return []

            candles = data["data"].get("candles", [])
            candles.reverse()

            return candles[-minutes_back:]

        else:
            # 🟡 MARKET CLOSED → USE LAST COMPLETED SESSION
            last_day = self.get_last_completed_trading_day()
            date_str = last_day.strftime("%Y-%m-%d")

            url = (
                f"{self.broker.BASE_URL}/historical-candle/intraday/"
                f"{key}/minutes/1/{date_str}/{date_str}"
            )
            print(f"{self.broker.BASE_URL}/historical-candle/intraday/"
                f"{key}/minutes/1/{date_str}/{date_str}")
            data = self.broker.safe_request("GET", url)

            if data.get("status") != "success":
                return []

            candles = data["data"].get("candles", [])

            # Filter up to market close (15:30)
            filtered = []

            for c in candles:
                ts = datetime.fromisoformat(c[0].replace("Z", ""))

                if (
                        ts.hour < 15 or
                        (ts.hour == 15 and ts.minute <= 30)
                ):
                    filtered.append(c)

            return filtered[-minutes_back:]

    # ==========================
    # GET HISTORICAL CANDLES
    # ==========================
    def get_historical_candles(self, instrument_key, interval="minutes/1", minutes_back=15):
        to_time = datetime.now()
        if to_time.hour > 15 or (to_time.hour == 15 and to_time.minute > 30):
            to_time = to_time.replace(hour=15, minute=29, second=0, microsecond=0)
        from_time = to_time - timedelta(minutes=minutes_back)
        if "|" in instrument_key:
            key = instrument_key
        else:
            key = f"{INDEX_CONFIG[ACTIVE_INDEX]['segment']}|{instrument_key}"
            print(f"{self.broker.BASE_URL}/historical-candle/intraday/{key}/{interval}/{to_time}/{from_time}")
        data = self.broker.safe_request(
            "GET",
            f"{self.broker.BASE_URL}/historical-candle/intraday/{key}/{interval}",
            params={
                "from": from_time.strftime("%Y-%m-%dT%H:%M:%S"),
                "to": to_time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
        )
        print("HISTORICAL RAW RESPONSE:", data)
        if data.get("status") != "success":
            return []

        return data["data"].get("candles", [])

    def get_fib_auto_15_pivots(self, instrument_key):

        # Ensure full key format
        if "|" not in instrument_key:
            instrument_key = f"{INDEX_CONFIG[ACTIVE_INDEX]['segment']}|{instrument_key}"

        # Fetch last 2 completed 15min candles
        candles = self.get_historical_candles(
            instrument_key,
            interval="15minute",
            minutes_back=60
        )

        if not candles or len(candles) < 2:
            return None

        # Use previous completed candle (not current forming)
        prev = candles[-2]

        high = float(prev[2])
        low = float(prev[3])
        close = float(prev[4])

        P = (high + low + close) / 3
        diff = high - low

        pivots = {
            "P": round(P, 2),
            "R1": round(P + 0.382 * diff, 2),
            "R2": round(P + 0.618 * diff, 2),
            "R3": round(P + 1.000 * diff, 2),
            "S1": round(P - 0.382 * diff, 2),
            "S2": round(P - 0.618 * diff, 2),
            "S3": round(P - 1.000 * diff, 2),
        }

        return pivots

        # -------------------------------------------------------
        # PREVIOUS DAY FIBONACCI PIVOTS
        # -------------------------------------------------------

    # def get_previous_day_fib_pivots(self):
    #     print("STEP 1: ENTERED get_previous_day_fib_pivots")
    #     instrument_key = "NSE_INDEX|Nifty 50"
    #
    #     # URL encode properly
    #     encoded_key = quote(instrument_key, safe="")
    #
    #     today = datetime.now().date()
    #     print("STEP 2: Today =", today)
    #     # Move backwards until weekday (avoid weekends)
    #     prev_day = today - timedelta(days=1)
    #     print("STEP 3: Initial prev_day =", prev_day)
    #     while prev_day.weekday() >= 5:
    #         print("STEP 4: Weekend detected:", prev_day)
    #         prev_day -= timedelta(days=1)
    #     print("STEP 5: Final prev_day =", prev_day)
    #     to_date = prev_day.strftime("%Y-%m-%d")
    #     from_date = prev_day.strftime("%Y-%m-%d")
    #
    #     url = (
    #         f"{self.broker.BASE_URL}/historical-candle/"
    #         f"{encoded_key}/day/{to_date}/{from_date}"
    #     )
    #     print("STEP 6: Calling safe_request")
    #     response = self.broker.safe_request("GET", url)
    #     print("STEP 7: Returned from safe_request")
    #     if response.get("status") != "success":
    #         raise Exception("Could not fetch previous day candle")
    #
    #     candles = response["data"]["candles"]
    #     print("STEP 8: Candles received:", candles)
    #     if not candles:
    #         raise Exception("Empty previous day candle response")
    #     print("STEP 9: Exiting function normally")
    #     # Daily candle format:
    #     # [timestamp, open, high, low, close, volume, oi]
    #
    #     _, o, h, l, c, *_ = candles[0]
    #
    #     # Standard Fibonacci pivot calculation
    #     pivot = (h + l + c) / 3
    #
    #     r1 = pivot + 0.382 * (h - l)
    #     r2 = pivot + 0.618 * (h - l)
    #     r3 = pivot + 1.000 * (h - l)
    #
    #     s1 = pivot - 0.382 * (h - l)
    #     s2 = pivot - 0.618 * (h - l)
    #     s3 = pivot - 1.000 * (h - l)
    #
    #     return {
    #         "P": round(pivot, 2),
    #         "R1": round(r1, 2),
    #         "R2": round(r2, 2),
    #         "R3": round(r3, 2),
    #         "S1": round(s1, 2),
    #         "S2": round(s2, 2),
    #         "S3": round(s3, 2),
    #     }

    def get_previous_day_fib_pivots(self, instrument_token):
        """
        Fetch previous trading day OHLC for given option instrument
        and calculate Fibonacci pivots.
        """

        # Construct full instrument key
        instrument_key = f"{INDEX_CONFIG[ACTIVE_INDEX]['segment']}|{instrument_token}"
        encoded_key = quote(instrument_key, safe="")

        today = datetime.now().date()

        # --------------------------------------------------
        # Find previous trading day (skip weekends)
        # --------------------------------------------------
        prev_day = today - timedelta(days=1)
        while prev_day.weekday() >= 5:
            prev_day -= timedelta(days=1)

        date_str = prev_day.strftime("%Y-%m-%d")

        url = (
            f"{self.broker.BASE_URL}/historical-candle/"
            f"{encoded_key}/day/{date_str}/{date_str}"
        )

        response = self.broker.safe_request("GET", url)

        if response.get("status") != "success":
            raise Exception("Could not fetch previous day candle")

        candles = response["data"].get("candles", [])

        if not candles:
            raise Exception("Empty previous day candle response")

        # Format: [timestamp, open, high, low, close, volume, oi]
        _, o, h, l, c, *_ = candles[0]

        # --------------------------------------------------
        # Fibonacci Pivot Calculation
        # --------------------------------------------------
        pivot = (h + l + c) / 3

        diff = h - l

        r1 = pivot + 0.382 * diff
        r2 = pivot + 0.618 * diff
        r3 = pivot + 1.000 * diff

        s1 = pivot - 0.382 * diff
        s2 = pivot - 0.618 * diff
        s3 = pivot - 1.000 * diff

        return {
            "P": round(pivot, 2),
            "R1": round(r1, 2),
            "R2": round(r2, 2),
            "R3": round(r3, 2),
            "S1": round(s1, 2),
            "S2": round(s2, 2),
            "S3": round(s3, 2),
        }
    def get_intraday_1min_candles(self, instrument_key):
        # print("get_intraday_1min_candles instrument key:", instrument_key)
        key = f"{INDEX_CONFIG[ACTIVE_INDEX]['segment']}|{instrument_key}"
        # encoded_key = urllib.parse.quote(key, safe='')
        print(f"{self.broker.BASE_URL}/historical-candle/intraday/{key}/minutes/1")
        url = f"{self.broker.BASE_URL}/historical-candle/intraday/{key}/minutes/1"

        response = self.broker.safe_request("GET", url)

        if response.get("status") != "success":
            return None

        candles = response["data"].get("candles", [])
        print(candles)
        # API returns newest first → reverse to oldest first
        candles.reverse()

        return candles

    def get_latest_candle(self, instrument_key):
        # print("get_latest_candle instrument key:", instrument_key)
        key = f"{INDEX_CONFIG[ACTIVE_INDEX]['segment']}|{instrument_key}"
        candles = self.get_intraday_1min_candles(key)

        if not candles or len(candles) < 1:
            return None

        c = candles[-1]

        return SimpleNamespace(
            index=len(candles) - 1,
            timestamp=c[0],
            open=c[1],
            high=c[2],
            low=c[3],
            close=c[4]
        )

    def get_previous_candle(self, instrument_key):
        # print("get_previous_candle instrument key:", instrument_key)
        key = f"{INDEX_CONFIG[ACTIVE_INDEX]['segment']}|{instrument_key}"
        candles = self.get_intraday_1min_candles(key)

        if not candles or len(candles) < 2:
            return None

        c = candles[-2]

        return SimpleNamespace(
            index=len(candles) - 2,
            timestamp=c[0],
            open=c[1],
            high=c[2],
            low=c[3],
            close=c[4]
        )