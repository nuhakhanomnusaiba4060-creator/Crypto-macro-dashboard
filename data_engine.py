
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CRYPTO MACRO DASHBOARD
Public Market Data Engine

Sources:
1. CoinGecko - Global market statistics and BTC/ETH reference prices
2. Alternative.me - Fear & Greed Index
3. Binance Spot API - Closed daily BTC/ETH candles

No API key required.
No fabricated values.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
import time

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


# =========================================================
# CONFIGURATION
# =========================================================

SCHEMA_VERSION = 2

OUTPUT_FILE = Path(
    os.getenv(
        "DASHBOARD_DATA_FILE",
        "data/market_data.json"
    )
)

TIMEOUT_SECONDS = 15

USER_AGENT = "CryptoMacroDashboard/2.0"

BINANCE_BASE = "https://data-api.binance.vision"

COINGECKO_BASE = "https://api.coingecko.com/api/v3"

ALTERNATIVE_BASE = "https://api.alternative.me"


# =========================================================
# TIME UTILITIES
# =========================================================

def utc_now() -> str:

    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def parse_timestamp(value: str):

    if not isinstance(value, str) or not value.strip():
        return None

    try:

        parsed = datetime.fromisoformat(
            value.strip().replace("Z", "+00:00")
        )

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return parsed.astimezone(timezone.utc)

    except (ValueError, TypeError):

        return None


def age_status(
    timestamp: str | None,
    stale_after_seconds: int
) -> str:

    parsed = parse_timestamp(timestamp)

    if parsed is None:
        return "TIMESTAMP_UNKNOWN"

    age = (
        datetime.now(timezone.utc) - parsed
    ).total_seconds()

    if age < -300:
        return "TIMESTAMP_INVALID"

    if age > stale_after_seconds:
        return "STALE"

    return "OK"


def timestamp_from_seconds(value: Any):

    try:

        return (
            datetime.fromtimestamp(
                int(value),
                timezone.utc
            )
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )

    except (
        TypeError,
        ValueError,
        OverflowError,
        OSError
    ):

        return None


def timestamp_from_milliseconds(value: Any):

    try:

        return (
            datetime.fromtimestamp(
                int(value) / 1000,
                timezone.utc
            )
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )

    except (
        TypeError,
        ValueError,
        OverflowError,
        OSError
    ):

        return None


# =========================================================
# NUMBER VALIDATION
# =========================================================

def finite_number(value: Any) -> float | None:

    try:

        number = float(value)

    except (
        TypeError,
        ValueError,
        OverflowError
    ):

        return None

    if not math.isfinite(number):
        return None

    return number


# =========================================================
# HTTP REQUEST
# =========================================================

def http_json(
    url: str,
    params: dict[str, Any] | None = None
):

    if params:

        url = f"{url}?{urlencode(params)}"

    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json"
        }
    )

    last_error = "Unknown network error"

    for attempt in range(3):

        try:

            with urlopen(
                request,
                timeout=TIMEOUT_SECONDS
            ) as response:

                payload = response.read()

            data = json.loads(
                payload.decode("utf-8")
            )

            return data, utc_now()

        except HTTPError as exc:

            last_error = f"HTTP_{exc.code}"

            if exc.code not in (
                429,
                500,
                502,
                503,
                504
            ):
                break

        except (
            URLError,
            TimeoutError,
            OSError,
            json.JSONDecodeError
        ) as exc:

            last_error = (
                f"{type(exc).__name__}: {exc}"
            )

        if attempt < 2:
            time.sleep(1.5 * (attempt + 1))

    raise RuntimeError(last_error)


# =========================================================
# STANDARD METRIC FORMAT
# =========================================================

def metric(
    value: Any = None,
    unit: str | None = None,
    source: str | None = None,
    source_updated_at: str | None = None,
    status: str = "OK",
    error: str | None = None,
    fetched_at: str | None = None
):

    number = (
        finite_number(value)
        if value is not None
        else None
    )

    if value is not None and number is None:

        status = "INVALID_DATA"

        error = "Invalid numeric value"

    if number is None and status == "OK":

        status = "UNAVAILABLE"

    if status == "OK":

        timestamp_status = age_status(
            source_updated_at,
            7 * 24 * 3600
        )

        if timestamp_status != "OK":
            status = timestamp_status

    return {
        "value": number,
        "unit": unit,
        "source": source,
        "source_updated_at": source_updated_at,
        "fetched_at": fetched_at or utc_now(),
        "status": status,
        "error": error
    }


def unavailable(
    source: str,
    error: str
):

    return metric(
        source=source,
        status="UNAVAILABLE",
        error=str(error)[:240]
    )


# =========================================================
# GLOBAL MARKET DATA
# =========================================================

def fetch_global_market():

    source = "CoinGecko API"

    keys = (
        "total_market_cap_usd",
        "total_volume_24h_usd",
        "btc_dominance_pct",
        "eth_dominance_pct",
        "active_cryptocurrencies",
        "markets_count"
    )

    try:

        data, fetched_at = http_json(
            f"{COINGECKO_BASE}/global"
        )

        market_data = data.get("data")

        if not isinstance(market_data, dict):
            raise ValueError("Invalid global market response")

        updated_at = timestamp_from_seconds(
            market_data.get("updated_at")
        )

        status = age_status(
            updated_at,
            7200
        )

        def nested_number(parent, key):

            obj = market_data.get(parent)

            if not isinstance(obj, dict):
                return None

            return obj.get(key)

        fields = {

            "total_market_cap_usd": (
                nested_number("total_market_cap", "usd"),
                "USD"
            ),

            "total_volume_24h_usd": (
                nested_number("total_volume", "usd"),
                "USD"
            ),

            "btc_dominance_pct": (
                nested_number("market_cap_percentage", "btc"),
                "%"
            ),

            "eth_dominance_pct": (
                nested_number("market_cap_percentage", "eth"),
                "%"
            ),

            "active_cryptocurrencies": (
                market_data.get("active_cryptocurrencies"),
                "count"
            ),

            "markets_count": (
                market_data.get("markets"),
                "count"
            )
        }

        result = {}

        for key, (value, unit) in fields.items():

            result[key] = metric(
                value,
                unit,
                source,
                updated_at,
                status,
                fetched_at=fetched_at
            )

        return result

    except Exception as exc:

        return {
            key: unavailable(source, str(exc))
            for key in keys
        }


# =========================================================
# FEAR AND GREED
# =========================================================

def fetch_fear_greed():

    source = "Alternative.me Fear & Greed API"

    try:

        data, fetched_at = http_json(
            f"{ALTERNATIVE_BASE}/fng/",
            {
                "limit": 1,
                "format": "json"
            }
        )

        rows = data.get("data")

        if not isinstance(rows, list) or not rows:
            raise ValueError("Fear & Greed data unavailable")

        row = rows[0]

        if not isinstance(row, dict):
            raise ValueError("Invalid Fear & Greed response")

        value = finite_number(row.get("value"))

        if value is None or not 0 <= value <= 100:
            raise ValueError("Fear & Greed value outside 0-100")

        updated_at = timestamp_from_seconds(
            row.get("timestamp")
        )

        status = age_status(
            updated_at,
            48 * 3600
        )

        return {
            "value": value,
            "classification": str(
                row.get("value_classification", "Unknown")
            ),
            "unit": "/100",
            "source": source,
            "source_updated_at": updated_at,
            "fetched_at": fetched_at,
            "status": status,
            "error": None
        }

    except Exception as exc:

        return {
            "value": None,
            "classification": None,
            "unit": "/100",
            "source": source,
            "source_updated_at": None,
            "fetched_at": utc_now(),
            "status": "UNAVAILABLE",
            "error": str(exc)[:240]
        }


# =========================================================
# MOVING AVERAGES
# =========================================================

def sma(
    values: list[float],
    period: int
):

    if len(values) < period:
        return None

    return sum(values[-period:]) / period


def ema_series(
    values: list[float],
    period: int
):

    result = [None] * len(values)

    if len(values) < period:
        return result

    previous = sum(values[:period]) / period

    result[period - 1] = previous

    multiplier = 2 / (period + 1)

    for i in range(period, len(values)):

        previous = (
            values[i] - previous
        ) * multiplier + previous

        result[i] = previous

    return result


# =========================================================
# RSI
# =========================================================

def calculate_rsi(
    values: list[float],
    period: int = 14
):

    if len(values) < period + 1:
        return None

    changes = [
        values[i] - values[i - 1]
        for i in range(1, len(values))
    ]

    gains = [
        max(change, 0)
        for change in changes
    ]

    losses = [
        max(-change, 0)
        for change in changes
    ]

    average_gain = sum(gains[:period]) / period

    average_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):

        average_gain = (
            average_gain * (period - 1)
            + gains[i]
        ) / period

        average_loss = (
            average_loss * (period - 1)
            + losses[i]
        ) / period

    if average_loss == 0:

        return 100.0 if average_gain > 0 else 50.0

    rs = average_gain / average_loss

    return 100 - (100 / (1 + rs))


# =========================================================
# MACD
# =========================================================

def calculate_macd(values: list[float]):

    fast = ema_series(values, 12)

    slow = ema_series(values, 26)

    macd_values = []

    for f, s in zip(fast, slow):

        if f is not None and s is not None:

            macd_values.append(f - s)

    if len(macd_values) < 9:

        return None, None, None

    signal_values = ema_series(
        macd_values,
        9
    )

    macd_value = macd_values[-1]

    signal_value = signal_values[-1]

    if signal_value is None:

        return macd_value, None, None

    return (
        macd_value,
        signal_value,
        macd_value - signal_value
    )


# =========================================================
# ADX
# =========================================================

def calculate_adx(
    highs,
    lows,
    closes,
    period=14
):

    if len(closes) < period * 2 + 1:
        return None

    true_ranges = []

    positive_dm = []

    negative_dm = []

    for i in range(1, len(closes)):

        up_move = highs[i] - highs[i - 1]

        down_move = lows[i - 1] - lows[i]

        positive_dm.append(
            up_move
            if up_move > down_move and up_move > 0
            else 0.0
        )

        negative_dm.append(
            down_move
            if down_move > up_move and down_move > 0
            else 0.0
        )

        true_ranges.append(
            max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1])
            )
        )

    smoothed_tr = sum(true_ranges[:period])

    smoothed_plus = sum(positive_dm[:period])

    smoothed_minus = sum(negative_dm[:period])

    dx_values = []

    for i in range(period - 1, len(true_ranges)):

        if i > period - 1:

            smoothed_tr = (
                smoothed_tr
                - smoothed_tr / period
                + true_ranges[i]
            )

            smoothed_plus = (
                smoothed_plus
                - smoothed_plus / period
                + positive_dm[i]
            )

            smoothed_minus = (
                smoothed_minus
                - smoothed_minus / period
                + negative_dm[i]
            )

        if smoothed_tr <= 0:
            continue

        plus_di = (
            100 * smoothed_plus / smoothed_tr
        )

        minus_di = (
            100 * smoothed_minus / smoothed_tr
        )

        denominator = plus_di + minus_di

        dx = (
            100 * abs(plus_di - minus_di) / denominator
            if denominator > 0
            else 0.0
        )

        dx_values.append(dx)

    if len(dx_values) < period:
        return None

    adx = sum(dx_values[:period]) / period

    for dx in dx_values[period:]:

        adx = (
            adx * (period - 1) + dx
        ) / period

    return adx


# =========================================================
# TECHNICAL INDICATORS
# =========================================================

def calculate_indicators(candles):

    closes = [c["close"] for c in candles]

    highs = [c["high"] for c in candles]

    lows = [c["low"] for c in candles]

    volumes = [c["volume"] for c in candles]

    source = "Binance Spot closed 1D candles"

    updated_at = timestamp_from_milliseconds(
        candles[-1]["close_time"]
    )

    fetched_at = utc_now()

    candle_status = age_status(
        updated_at,
        36 * 3600
    )

    def m(value, unit):

        return metric(
            value,
            unit,
            source,
            updated_at,
            candle_status,
            fetched_at=fetched_at
        )

    # Bollinger Bands
    bb_mid = sma(closes, 20)

    bb_std = None

    if bb_mid is not None:

        last_twenty = closes[-20:]

        bb_std = math.sqrt(
            sum(
                (x - bb_mid) ** 2
                for x in last_twenty
            ) / 20
        )

    # MACD
    macd_value, macd_signal, macd_histogram = (
        calculate_macd(closes)
    )

    # Volume
    average_volume = sma(volumes, 20)

    # Support/Resistance:
    # Latest closed candle is intentionally excluded.
    # These levels use the previous 20 completed candles.
    prior_lows = lows[-21:-1] if len(lows) >= 21 else []

    prior_highs = highs[-21:-1] if len(highs) >= 21 else []

    return {

        "ma20": m(
            sma(closes, 20),
            "USDT"
        ),

        "ma50": m(
            sma(closes, 50),
            "USDT"
        ),

        "ma200": m(
            sma(closes, 200),
            "USDT"
        ),

        "ema20": m(
            ema_series(closes, 20)[-1],
            "USDT"
        ),

        "ema50": m(
            ema_series(closes, 50)[-1],
            "USDT"
        ),

        "rsi14": m(
            calculate_rsi(closes),
            "index"
        ),

        "macd": m(
            macd_value,
            "USDT"
        ),

        "macd_signal": m(
            macd_signal,
            "USDT"
        ),

        "macd_histogram": m(
            macd_histogram,
            "USDT"
        ),

        "adx14": m(
            calculate_adx(
                highs,
                lows,
                closes
            ),
            "index"
        ),

        "bollinger_upper": m(
            bb_mid + 2 * bb_std
            if bb_mid is not None and bb_std is not None
            else None,
            "USDT"
        ),

        "bollinger_middle": m(
            bb_mid,
            "USDT"
        ),

        "bollinger_lower": m(
            bb_mid - 2 * bb_std
            if bb_mid is not None and bb_std is not None
            else None,
            "USDT"
        ),

        "volume_last_closed_day": m(
            volumes[-1],
            "base asset"
        ),

        "volume_sma20": m(
            average_volume,
            "base asset"
        ),

        "volume_ratio_20d": m(
            volumes[-1] / average_volume
            if average_volume is not None and average_volume > 0
            else None,
            "x"
        ),

        "support_20d": m(
            min(prior_lows)
            if len(prior_lows) == 20
            else None,
            "USDT"
        ),

        "resistance_20d": m(
            max(prior_highs)
            if len(prior_highs) == 20
            else None,
            "USDT"
        )
    }


# =========================================================
# BINANCE BTC / ETH DATA
# =========================================================

def fetch_asset(
    symbol: str,
    coin_id: str
):

    source = "Binance Spot Public API"

    result = {
        "symbol": symbol,
        "coin_id": coin_id
    }

    indicator_names = (
        "ma20",
        "ma50",
        "ma200",
        "ema20",
        "ema50",
        "rsi14",
        "macd",
        "macd_signal",
        "macd_histogram",
        "adx14",
        "bollinger_upper",
        "bollinger_middle",
        "bollinger_lower",
        "volume_last_closed_day",
        "volume_sma20",
        "volume_ratio_20d",
        "support_20d",
        "resistance_20d"
    )

    try:

        raw, fetched_at = http_json(
            f"{BINANCE_BASE}/api/v3/klines",
            {
                "symbol": f"{symbol}USDT",
                "interval": "1d",
                "limit": 250
            }
        )

        if not isinstance(raw, list):

            raise ValueError(
                "Invalid Binance candle payload"
            )

        now_ms = int(time.time() * 1000)

        candles = []

        seen_open_times = set()

        for row in raw:

            if not isinstance(row, list) or len(row) < 7:
                continue

            try:

                open_time = int(row[0])

                close_time = int(row[6])

            except (
                TypeError,
                ValueError,
                OverflowError
            ):

                continue

            # Exclude the currently forming candle.
            if close_time >= now_ms:
                continue

            # Reject duplicate candles.
            if open_time in seen_open_times:
                continue

            seen_open_times.add(open_time)

            parsed = [
                finite_number(row[i])
                for i in (1, 2, 3, 4, 5)
            ]

            if any(x is None for x in parsed):
                continue

            open_price, high, low, close, volume = parsed

            if min(
                open_price,
                high,
                low,
                close
            ) <= 0:
                continue

            if volume < 0:
                continue

            if high < max(
                open_price,
                close,
                low
            ):
                continue

            if low > min(
                open_price,
                close,
                high
            ):
                continue

            candles.append({

                "open_time": open_time,

                "close_time": close_time,

                "open": open_price,

                "high": high,

                "low": low,

                "close": close,

                "volume": volume
            })

        candles.sort(
            key=lambda x: x["open_time"]
        )

        if len(candles) < 200:

            raise ValueError(
                f"Only {len(candles)} valid closed daily candles; "
                "200 required"
            )

        # Ensure candle timestamps are strictly increasing.
        for i in range(1, len(candles)):

            if (
                candles[i]["open_time"]
                <= candles[i - 1]["open_time"]
            ):

                raise ValueError(
                    "Candle timestamps are not strictly increasing"
                )

        latest = candles[-1]

        updated_at = timestamp_from_milliseconds(
            latest["close_time"]
        )

        status = age_status(
            updated_at,
            36 * 3600
        )

        indicators = calculate_indicators(candles)

        for item in indicators.values():
            item["fetched_at"] = fetched_at

        result.update({

            "price_usdt": metric(
                latest["close"],
                "USDT",
                source,
                updated_at,
                status,
                fetched_at=fetched_at
            ),

            "candle_interval": "1d",

            "candle_policy": (
                "Only fully closed candles; "
                "current forming candle excluded"
            ),

            "candle_count": len(candles),

            "last_closed_candle_at": updated_at,

            "indicators": indicators
        })

    except Exception as exc:

        error = str(exc)[:240]

        result.update({

            "price_usdt": unavailable(
                source,
                error
            ),

            "candle_interval": "1d",

            "candle_policy": (
                "Only fully closed candles; "
                "current forming candle excluded"
            ),

            "candle_count": 0,

            "last_closed_candle_at": None,

            "indicators": {

                name: unavailable(
                    source,
                    error
                )

                for name in indicator_names
            }
        })

    return result


# =========================================================
# COINGECKO BTC / ETH REFERENCE PRICE
# =========================================================

def fetch_coingecko_prices():

    source = "CoinGecko API"

    try:

        data, fetched_at = http_json(
            f"{COINGECKO_BASE}/simple/price",
            {
                "ids": "bitcoin,ethereum",
                "vs_currencies": "usd",
                "include_24hr_change": "true",
                "include_last_updated_at": "true"
            }
        )

        result = {}

        for coin_id in (
            "bitcoin",
            "ethereum"
        ):

            item = data.get(coin_id)

            if not isinstance(item, dict):
                raise ValueError(
                    f"Missing {coin_id} price data"
                )

            updated_at = timestamp_from_seconds(
                item.get("last_updated_at")
            )

            status = age_status(
                updated_at,
                1800
            )

            result[coin_id] = {

                "price_usd": metric(
                    item.get("usd"),
                    "USD",
                    source,
                    updated_at,
                    status,
                    fetched_at=fetched_at
                ),

                "change_24h_pct": metric(
                    item.get("usd_24h_change"),
                    "%",
                    source,
                    updated_at,
                    status,
                    fetched_at=fetched_at
                ),

                "source_updated_at": updated_at,

                "fetched_at": fetched_at
            }

        return result

    except Exception as exc:

        error = str(exc)

        return {

            coin: {

                "price_usd": unavailable(
                    source,
                    error
                ),

                "change_24h_pct": unavailable(
                    source,
                    error
                ),

                "source_updated_at": None,

                "fetched_at": utc_now()
            }

            for coin in (
                "bitcoin",
                "ethereum"
            )
        }


# =========================================================
# ATOMIC JSON WRITE
# =========================================================

def write_json_atomic(
    path: Path,
    payload: dict[str, Any]
):

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent)
    )

    try:

        with os.fdopen(
            fd,
            "w",
            encoding="utf-8"
        ) as handle:

            json.dump(
                payload,
                handle,
                ensure_ascii=False,
                indent=2,
                allow_nan=False
            )

            handle.write("\n")

        os.replace(
            temp_name,
            path
        )

    except Exception:

        try:
            os.unlink(temp_name)
        except OSError:
            pass

        raise


# =========================================================
# BUILD MARKET DATA
# =========================================================

def build_payload():

    return {

        "schema_version": SCHEMA_VERSION,

        "generated_at": utc_now(),

        "update_mode": "scheduled_snapshot_not_realtime",

        "data_policy": (
            "Unavailable, stale, or timestamp-unknown values "
            "must not be treated as zero, neutral, or confirmed."
        ),

        "global_market": fetch_global_market(),

        "fear_greed": fetch_fear_greed(),

        "major_assets": fetch_coingecko_prices(),

        "technical": {

            "BTC": fetch_asset(
                "BTC",
                "bitcoin"
            ),

            "ETH": fetch_asset(
                "ETH",
                "ethereum"
            )
        },

        "not_integrated_yet": [

            "Fed policy and FOMC",

            "CPI/PCE/NFP",

            "DXY and Treasury yields",

            "VIX and equities",

            "ETF flows",

            "On-chain metrics",

            "Whale flows",

            "Token unlocks",

            "Project fundamentals"
        ]
    }


# =========================================================
# MAIN
# =========================================================

def main():

    payload = build_payload()

    write_json_atomic(
        OUTPUT_FILE,
        payload
    )

    print(
        f"Market data written: {OUTPUT_FILE}"
    )

    print(
        f"Generated at: {payload['generated_at']}"
    )

    print(
        f"Update mode: {payload['update_mode']}"
    )

    for name, item in payload["global_market"].items():

        print(
            f"Global {name}: {item['status']}"
        )

    print(
        "Fear & Greed:",
        payload["fear_greed"]["status"]
    )

    for symbol, asset in payload["technical"].items():

        print(
            f"{symbol} price:",
            asset["price_usdt"]["status"]
        )

        print(
            f"{symbol} closed candles:",
            asset["candle_count"]
        )

        for name, item in asset["indicators"].items():

            print(
                f"{symbol} {name}: {item['status']}"
            )

    return 0


if __name__ == "__main__":

    raise SystemExit(main())
