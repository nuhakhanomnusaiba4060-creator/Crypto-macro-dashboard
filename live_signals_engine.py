
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CRYPTO DADA LIVE SIGNALS ENGINE
Version: 1.3.3

FREE PUBLIC DATA PROVIDERS
1. Binance Market Data Only
2. CoinBoss Public API
3. Explore21
4. Alternative.me

No paid API keys required.

Version 1.3.3 changes:
- Binance uses data-api.binance.vision.
- Futures basis reads perp.aggregate correctly.
- Source timestamps are separated from fetch timestamps.
- Provider response failures are detected.
- Daily support/resistance use candle lows/highs.
- MVRV freshness is checked.
- ETF daily and 7-day flows remain separate.
- JSON schema v1 is retained.
- Missing data is never replaced with zero.
"""

import json
import math
import time
import urllib.parse
import urllib.request

from datetime import datetime, timezone
from pathlib import Path


# ============================================================
# CONFIGURATION
# ============================================================

VERSION = "1.3.3"
SCHEMA_VERSION = 1

SYMBOL = "BTCUSDT"

# Official Binance public market-data-only endpoint.
BINANCE_BASE = "https://data-api.binance.vision"

# CoinBoss documentation base URL:
# https://www.coinboss.com/api
COINBOSS_BASE = "https://www.coinboss.com"

EXPLORE21_BASE = "https://data.explore21.com"
ALTERNATIVE_BASE = "https://api.alternative.me"

OUTPUT_FILE = Path("data/live_signals.json")

HTTP_TIMEOUT = 25
USER_AGENT = "CryptoDadaLiveSignals/1.3.3"

PRICE_CANDLE_LIMIT = 210
SUPPORT_RESISTANCE_LOOKBACK = 20

DEFAULT_MAX_AGE_HOURS = 48
MVRV_MAX_AGE_HOURS = 48
ETF_MAX_AGE_HOURS = 48
FEAR_GREED_MAX_AGE_HOURS = 48


# ============================================================
# TIME HELPERS
# ============================================================

def utc_now():
    return datetime.now(timezone.utc)


def iso_now():
    return utc_now().isoformat(timespec="seconds")


def parse_timestamp(value):
    if value is None:
        return None

    try:
        if isinstance(value, (int, float)):
            number = float(value)

            if not math.isfinite(number) or number <= 0:
                return None

            # Unix milliseconds
            if number > 100000000000:
                number /= 1000.0

            return datetime.fromtimestamp(
                number,
                tz=timezone.utc
            )

        if isinstance(value, str):
            text = value.strip()

            if not text:
                return None

            if text.isdigit():
                return parse_timestamp(int(text))

            if len(text) == 10 and text[4] == "-":
                text += "T00:00:00+00:00"

            if text.endswith("Z"):
                text = text[:-1] + "+00:00"

            parsed = datetime.fromisoformat(text)

            if parsed.tzinfo is None:
                parsed = parsed.replace(
                    tzinfo=timezone.utc
                )

            return parsed.astimezone(timezone.utc)

    except (
        TypeError,
        ValueError,
        OverflowError,
        OSError
    ):
        return None

    return None


def timestamp_string(value):
    parsed = parse_timestamp(value)

    if parsed is None:
        return None

    return parsed.isoformat(timespec="seconds")


def timestamp_from_ms(value):
    return timestamp_string(value)


def age_hours(timestamp):
    parsed = parse_timestamp(timestamp)

    if parsed is None:
        return None

    seconds = (
        utc_now() - parsed
    ).total_seconds()

    return max(0.0, seconds / 3600.0)


# ============================================================
# NUMBER HELPERS
# ============================================================

def finite_number(value):
    try:
        number = float(value)

        if not math.isfinite(number):
            return None

        return number

    except (
        TypeError,
        ValueError,
        OverflowError
    ):
        return None


def safe_round(value, digits=4):
    number = finite_number(value)

    if number is None:
        return None

    return round(number, digits)


# ============================================================
# HTTP CLIENT
# ============================================================

def http_get_json(url, params=None):
    if params:
        query = urllib.parse.urlencode(params)
        separator = "&" if "?" in url else "?"
        url = url + separator + query

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json"
        },
        method="GET"
    )

    with urllib.request.urlopen(
        request,
        timeout=HTTP_TIMEOUT
    ) as response:

        status_code = getattr(
            response,
            "status",
            200
        )

        if not 200 <= status_code < 300:
            raise RuntimeError(
                f"HTTP request failed: {status_code}"
            )

        raw = response.read().decode("utf-8")

        data = json.loads(raw)

    if isinstance(data, dict):
        if data.get("success") is False:
            raise RuntimeError(
                "Provider API returned success=false: "
                + str(data.get("code", "UNKNOWN"))
                + " "
                + str(data.get("error", "Unknown API error"))
            )

    return data


# ============================================================
# METRIC BUILDERS
# ============================================================

def make_metric(
    value=None,
    unit=None,
    status="UNAVAILABLE",
    source=None,
    source_updated_at=None,
    note=None,
    extra=None
):
    metric = {
        "value": finite_number(value),
        "unit": unit,
        "status": status,
        "source": source,
        "source_updated_at": source_updated_at,
        "fetched_at": iso_now(),
        "data_age_hours": None,
        "note": note
    }

    age = age_hours(source_updated_at)

    if age is not None:
        metric["data_age_hours"] = round(age, 2)

    if extra and isinstance(extra, dict):
        metric.update(extra)

    return metric


def unavailable_metric(
    source,
    note,
    unit=None
):
    return make_metric(
        value=None,
        unit=unit,
        status="UNAVAILABLE",
        source=source,
        source_updated_at=None,
        note=note
    )


def apply_freshness(
    metric,
    max_age_hours,
    provider_quality=None
):
    """
    Never treat an unknown source timestamp as fresh.
    Keep the numeric value for reference when stale.
    """

    if not isinstance(metric, dict):
        return metric

    source_time = metric.get(
        "source_updated_at"
    )

    if not source_time:
        if metric.get("status") not in (
            "UNAVAILABLE",
            "ERROR"
        ):
            metric["status"] = "TIME_UNKNOWN"

            old_note = metric.get("note") or ""

            extra_note = (
                "Provider did not expose a verified "
                "observation timestamp. Fetch time is "
                "recorded separately."
            )

            metric["note"] = (
                old_note + " " + extra_note
            ).strip()

        return metric

    age = age_hours(source_time)

    if age is None:
        metric["status"] = "TIME_UNKNOWN"
        metric["data_age_hours"] = None
        return metric

    metric["data_age_hours"] = round(
        age,
        2
    )

    is_provider_stale = (
        str(provider_quality or "").upper()
        in ("STALE", "BROKEN", "UNAVAILABLE")
    )

    if age > max_age_hours or is_provider_stale:
        metric["status"] = "STALE"

        old_note = metric.get("note") or ""

        stale_note = (
            f"Source data is {age:.1f} hours old; "
            f"freshness limit is {max_age_hours} hours."
            if age > max_age_hours
            else (
                "Provider quality reports this data "
                "as stale or unusable."
            )
        )

        metric["note"] = (
            old_note + " " + stale_note
        ).strip()

    return metric


def run_safely(name, function, *args, **kwargs):
    try:
        result = function(*args, **kwargs)

        if not isinstance(result, dict):
            raise RuntimeError(
                "Provider returned invalid metric structure."
            )

        return result

    except Exception as exc:
        message = (
            f"{type(exc).__name__}: {str(exc)}"
        )

        print(
            f"{name} => ERROR | {message}"
        )

        return make_metric(
            value=None,
            unit=None,
            status="ERROR",
            source=name,
            source_updated_at=None,
            note=message
        )


# ============================================================
# BINANCE SPOT PRICE
# ============================================================

def fetch_binance_price():
    url = (
        f"{BINANCE_BASE}"
        "/api/v3/ticker/price"
    )

    data = http_get_json(
        url,
        {"symbol": SYMBOL}
    )

    price = finite_number(
        data.get("price")
    )

    if price is None or price <= 0:
        raise RuntimeError(
            "Binance returned an invalid BTC spot price."
        )

    return make_metric(
        value=price,
        unit="USDT",
        status="TIME_UNKNOWN",
        source="Binance Spot BTCUSDT Ticker",
        source_updated_at=None,
        note=(
            "Binance public spot ticker. "
            "This endpoint does not provide an observation "
            "timestamp. Fetch time is recorded separately."
        )
    )


# ============================================================
# BINANCE DAILY CANDLES
# ============================================================

def fetch_daily_candles():
    url = (
        f"{BINANCE_BASE}"
        "/api/v3/klines"
    )

    data = http_get_json(
        url,
        {
            "symbol": SYMBOL,
            "interval": "1d",
            "limit": PRICE_CANDLE_LIMIT
        }
    )

    if not isinstance(data, list):
        raise RuntimeError(
            "Binance Klines response is not a list."
        )

    candles = []

    for row in data:
        if not isinstance(row, list) or len(row) < 7:
            continue

        try:
            candle = {
                "open_time": int(row[0]),
                "open": finite_number(row[1]),
                "high": finite_number(row[2]),
                "low": finite_number(row[3]),
                "close": finite_number(row[4]),
                "volume": finite_number(row[5]),
                "close_time": int(row[6])
            }

            required = (
                candle["open"],
                candle["high"],
                candle["low"],
                candle["close"]
            )

            if any(
                item is None for item in required
            ):
                continue

            if candle["high"] < candle["low"]:
                continue

            candles.append(candle)

        except (
            TypeError,
            ValueError,
            IndexError
        ):
            continue

    now_ms = int(time.time() * 1000)

    completed = [
        candle
        for candle in candles
        if candle["close_time"] < now_ms
    ]

    if len(completed) < 200:
        raise RuntimeError(
            "Insufficient completed daily candles."
        )

    return completed


def calculate_sma(values, period):
    if len(values) < period:
        return None

    sample = values[-period:]

    if any(
        value is None for value in sample
    ):
        return None

    return sum(sample) / period


def calculate_rsi(values, period=14):
    if len(values) < period + 1:
        return None

    changes = []

    for index in range(
        len(values) - period,
        len(values)
    ):
        changes.append(
            values[index] - values[index - 1]
        )

    gains = [
        max(change, 0.0)
        for change in changes
    ]

    losses = [
        abs(min(change, 0.0))
        for change in changes
    ]

    average_gain = sum(gains) / period
    average_loss = sum(losses) / period

    if average_loss == 0:
        if average_gain == 0:
            return 50.0

        return 100.0

    rs = average_gain / average_loss

    return 100.0 - (
        100.0 / (1.0 + rs)
    )


def fetch_price_structure():
    candles = fetch_daily_candles()

    closes = [
        candle["close"]
        for candle in candles
    ]

    latest_candle = candles[-1]

    candle_timestamp = timestamp_from_ms(
        latest_candle["close_time"]
    )

    ma20 = calculate_sma(closes, 20)
    ma50 = calculate_sma(closes, 50)
    ma200 = calculate_sma(closes, 200)

    rsi14 = calculate_rsi(
        closes,
        14
    )

    lookback = candles[
        -(SUPPORT_RESISTANCE_LOOKBACK + 1):-1
    ]

    if len(lookback) < SUPPORT_RESISTANCE_LOOKBACK:
        raise RuntimeError(
            "Insufficient candles for support/resistance."
        )

    support = min(
        candle["low"]
        for candle in lookback
    )

    resistance = max(
        candle["high"]
        for candle in lookback
    )

    price = fetch_binance_price()

    candle_source = (
        "Binance Spot Daily Candles"
    )

    return {
        "price": price,

        "support": make_metric(
            value=support,
            unit="USDT",
            status="OK",
            source=candle_source,
            source_updated_at=candle_timestamp,
            note=(
                f"Lowest Low of the previous "
                f"{SUPPORT_RESISTANCE_LOOKBACK} "
                "completed daily candles."
            ),
            extra={
                "lookback": (
                    f"{SUPPORT_RESISTANCE_LOOKBACK} "
                    "completed daily candles"
                ),
                "method": "lowest low"
            }
        ),

        "resistance": make_metric(
            value=resistance,
            unit="USDT",
            status="OK",
            source=candle_source,
            source_updated_at=candle_timestamp,
            note=(
                f"Highest High of the previous "
                f"{SUPPORT_RESISTANCE_LOOKBACK} "
                "completed daily candles."
            ),
            extra={
                "lookback": (
                    f"{SUPPORT_RESISTANCE_LOOKBACK} "
                    "completed daily candles"
                ),
                "method": "highest high"
            }
        ),

        "ma20": make_metric(
            value=ma20,
            unit="USDT",
            status="OK" if ma20 is not None else "UNAVAILABLE",
            source=candle_source,
            source_updated_at=candle_timestamp,
            note="20-day simple moving average."
        ),

        "ma50": make_metric(
            value=ma50,
            unit="USDT",
            status="OK" if ma50 is not None else "UNAVAILABLE",
            source=candle_source,
            source_updated_at=candle_timestamp,
            note="50-day simple moving average."
        ),

        "ma200": make_metric(
            value=ma200,
            unit="USDT",
            status="OK" if ma200 is not None else "UNAVAILABLE",
            source=candle_source,
            source_updated_at=candle_timestamp,
            note="200-day simple moving average."
        ),

        "rsi14": make_metric(
            value=rsi14,
            unit="RSI",
            status="OK" if rsi14 is not None else "UNAVAILABLE",
            source=candle_source,
            source_updated_at=candle_timestamp,
            note=(
                "14-period RSI calculated from "
                "completed daily candle closes."
            )
        ),

        "candle_updated_at": candle_timestamp
    }


# ============================================================
# COINBOSS ETF FLOWS
# ============================================================

def fetch_etf_flows():
    url = (
        f"{COINBOSS_BASE}"
        "/api/etf/flows"
    )

    data = http_get_json(
        url,
        {
            "asset": "BTC",
            "days": 30
        }
    )

    latest = data.get("latest") or {}

    daily_flow = finite_number(
        latest.get("flow")
    )

    weekly_flow = finite_number(
        latest.get("sum_7d")
    )

    aum = finite_number(
        latest.get("aum")
    )

    source_timestamp = timestamp_string(
        latest.get("date")
    )

    if daily_flow is None and weekly_flow is None:
        raise RuntimeError(
            "ETF API returned no valid daily or weekly flow."
        )

    daily_status = (
        "OK" if daily_flow is not None
        else "UNAVAILABLE"
    )

    weekly_status = (
        "OK" if weekly_flow is not None
        else "UNAVAILABLE"
    )

    classification = (
        "Unavailable"
        if daily_flow is None
        else (
            "Positive" if daily_flow > 0
            else "Negative" if daily_flow < 0
            else "Neutral"
        )
    )

    metric = {
        "value": daily_flow,
        "unit": "million USD",
        "status": daily_status,
        "source": "CoinBoss Public ETF API",
        "source_updated_at": source_timestamp,
        "fetched_at": iso_now(),
        "data_age_hours": age_hours(source_timestamp),
        "note": (
            "Latest reported daily net ETF flow. "
            "Zero is preserved only when the provider "
            "actually reports zero."
        ),

        "daily_net_flow": daily_flow,
        "daily_unit": "million USD",
        "daily_status": daily_status,

        "seven_day_net_flow": weekly_flow,
        "seven_day_unit": "million USD",
        "seven_day_status": weekly_status,
        "seven_day_note": (
            "Provider-reported cumulative 7-day net ETF flow."
        ),

        # Compatibility with previous dashboard.
        "sum_7d": weekly_flow,

        "aum": aum,
        "aum_unit": "million USD",

        "classification": classification,
        "update_frequency": "Daily"
    }

    return apply_freshness(
        metric,
        ETF_MAX_AGE_HOURS
    )


# ============================================================
# COINBOSS FUNDING RATE
# ============================================================

def fetch_funding_rate():
    url = (
        f"{COINBOSS_BASE}"
        "/api/sd/funding"
    )

    data = http_get_json(
        url,
        {"coin": "BTC"}
    )

    value = finite_number(
        data.get("oi_weighted_8h")
    )

    method = "oi_weighted_8h"

    if value is None:
        value = finite_number(
            data.get("avg_8h")
        )
        method = "avg_8h"

    if value is None:
        raise RuntimeError(
            "Funding API returned no valid rate."
        )

    # CoinBoss returns a fraction.
    percentage = value * 100.0

    meta = data.get("meta") or {}

    source_timestamp = timestamp_string(
        meta.get("observed_at")
    )

    # Do not use data['now'] as source observation time.
    # It is the API response/server time.
    metric = make_metric(
        value=percentage,
        unit="% per 8h",
        status="OK" if source_timestamp else "TIME_UNKNOWN",
        source="CoinBoss Public Funding API",
        source_updated_at=source_timestamp,
        note=(
            "Open-interest-weighted 8-hour funding rate. "
            "Provider fraction converted to percentage."
        ),
        extra={
            "method": method,
            "raw_fraction": value
        }
    )

    return apply_freshness(
        metric,
        1.0,
        meta.get("quality")
    )


# ============================================================
# COINBOSS OPEN INTEREST
# ============================================================

def fetch_open_interest():
    url = (
        f"{COINBOSS_BASE}"
        "/api/sd/oi"
    )

    data = http_get_json(
        url,
        {"coin": "BTC"}
    )

    value = finite_number(
        data.get("total_usd_single_adjusted")
    )

    method = "total_usd_single_adjusted"

    if value is None:
        value = finite_number(
            data.get("total_usd")
        )
        method = "total_usd"

    if value is None:
        raise RuntimeError(
            "Open Interest API returned no valid USD value."
        )

    source_timestamp = timestamp_from_ms(
        data.get("asof")
    )

    meta = data.get("meta") or {}

    metric = make_metric(
        value=value,
        unit="USD",
        status="OK",
        source="CoinBoss Public Open Interest API",
        source_updated_at=source_timestamp,
        note=(
            "Total BTC open interest in USD. "
            "Adjusted single-sided value is preferred."
        ),
        extra={
            "method": method
        }
    )

    return apply_freshness(
        metric,
        1.0,
        meta.get("quality")
    )


# ============================================================
# COINBOSS FUTURES BASIS / PREMIUM
# ============================================================

def fetch_futures_premium():
    url = (
        f"{COINBOSS_BASE}"
        "/api/sd/basis"
    )

    data = http_get_json(
        url,
        {"coin": "BTC"}
    )

    perp = data.get("perp") or {}
    aggregate = perp.get("aggregate") or {}

    # Correct documented path:
    # perp.aggregate.oi_weighted_pct
    value = finite_number(
        aggregate.get("oi_weighted_pct")
    )

    method = "perp.aggregate.oi_weighted_pct"

    if value is None:
        value = finite_number(
            aggregate.get("median_pct")
        )
        method = "perp.aggregate.median_pct"

    if value is None:
        raise RuntimeError(
            "Basis API returned no valid perp aggregate basis. "
            "Both oi_weighted_pct and median_pct are null/missing."
        )

    meta = data.get("meta") or {}

    # First choice: actual source observation timestamp.
    source_timestamp = timestamp_from_ms(
        meta.get("observed_at")
    )

    # Fallback: newest actual exchange observation in contracts.
    # received_at and fetched_at are deliberately NOT used as
    # source observation timestamps.
    if source_timestamp is None:
        contracts = perp.get("contracts") or []

        observed_times = []

        for contract in contracts:
            if not isinstance(contract, dict):
                continue

            observed = timestamp_from_ms(
                contract.get("observed_at")
            )

            if observed:
                parsed = parse_timestamp(observed)

                if parsed:
                    observed_times.append(parsed)

        if observed_times:
            source_timestamp = max(
                observed_times
            ).isoformat(timespec="seconds")

    quality = meta.get("quality")

    metric = make_metric(
        value=value,
        unit="%",
        status=(
            "OK" if source_timestamp
            else "TIME_UNKNOWN"
        ),
        source="CoinBoss Public Futures Basis API",
        source_updated_at=source_timestamp,
        note=(
            "Perpetual futures mark/index basis percentage. "
            "This is not a pure spot-versus-perpetual premium."
        ),
        extra={
            "method": method,
            "provider_quality": quality,
            "provider_is_stale": meta.get("is_stale"),
            "exchange_count": aggregate.get("n_exchanges"),
            "contract_count": aggregate.get("n_contracts")
        }
    )

    return apply_freshness(
        metric,
        1.0,
        quality
    )


# ============================================================
# EXPLORE21 MVRV Z-SCORE
# ============================================================

def fetch_mvrv_z_score():
    url = (
        f"{EXPLORE21_BASE}"
        "/v1/metrics/bitcoin-mvrv-z-score/latest"
    )

    data = http_get_json(url)

    candidates = []

    if isinstance(data, dict):
        candidates.append(data)

        for key in (
            "data",
            "result",
            "metric"
        ):
            nested = data.get(key)

            if isinstance(nested, dict):
                candidates.append(nested)

            elif isinstance(nested, list) and nested:
                if isinstance(nested[0], dict):
                    candidates.append(nested[0])

    value = None
    source_timestamp = None

    value_keys = (
        "value",
        "mvrv_z_score",
        "mvrv_zscore",
        "latest"
    )

    time_keys = (
        "date",
        "timestamp",
        "updated_at",
        "as_of",
        "time"
    )

    for candidate in candidates:
        if value is None:
            for key in value_keys:
                possible = finite_number(
                    candidate.get(key)
                )

                if possible is not None:
                    value = possible
                    break

        if source_timestamp is None:
            for key in time_keys:
                possible_time = timestamp_string(
                    candidate.get(key)
                )

                if possible_time:
                    source_timestamp = possible_time
                    break

    if value is None:
        raise RuntimeError(
            "Explore21 did not return a valid MVRV Z-Score."
        )

    metric = make_metric(
        value=value,
        unit="Z-Score",
        status="OK",
        source="Explore21 Bitcoin MVRV Z-Score",
        source_updated_at=source_timestamp,
        note=(
            "On-chain MVRV Z-Score. "
            "Stale values are retained for reference."
        )
    )

    return apply_freshness(
        metric,
        MVRV_MAX_AGE_HOURS
    )


# ============================================================
# NUPL
# ============================================================

def fetch_nupl():
    return unavailable_metric(
        source="Explore21",
        note=(
            "NUPL is not currently available from the "
            "verified free provider used by this engine. "
            "No unverified value is substituted."
        ),
        unit="Ratio"
    )


# ============================================================
# ALTERNATIVE.ME FEAR AND GREED
# ============================================================

def fetch_fear_greed():
    url = (
        f"{ALTERNATIVE_BASE}"
        "/fng/"
    )

    data = http_get_json(
        url,
        {"limit": 1}
    )

    rows = data.get("data") or []

    if not rows:
        raise RuntimeError(
            "Fear & Greed API returned no data."
        )

    latest = rows[0]

    value = finite_number(
        latest.get("value")
    )

    if value is None:
        raise RuntimeError(
            "Fear & Greed value is invalid."
        )

    source_timestamp = timestamp_from_ms(
        latest.get("timestamp")
    )

    metric = make_metric(
        value=value,
        unit="Index (0-100)",
        status="PROXY_ONLY",
        source="Alternative.me Fear & Greed Index",
        source_updated_at=source_timestamp,
        note=(
            "Sentiment proxy only. It does not directly "
            "measure retail trading activity or positioning."
        ),
        extra={
            "classification": latest.get(
                "value_classification"
            ),
            "proxy_only": True
        }
    )

    return apply_freshness(
        metric,
        FEAR_GREED_MAX_AGE_HOURS
    )


# ============================================================
# PRICE STRUCTURE FAILURE HANDLING
# ============================================================

def failed_price_structure(exc):
    message = (
        f"{type(exc).__name__}: {str(exc)}"
    )

    print(
        f"Price Structure => ERROR | {message}"
    )

    return {
        "price": make_metric(
            value=None,
            unit="USDT",
            status="ERROR",
            source="Binance Spot BTCUSDT",
            source_updated_at=None,
            note=message
        ),

        "support": unavailable_metric(
            "Binance Spot Daily Candles",
            "Price structure collection failed: " + message,
            "USDT"
        ),

        "resistance": unavailable_metric(
            "Binance Spot Daily Candles",
            "Price structure collection failed: " + message,
            "USDT"
        ),

        "ma20": unavailable_metric(
            "Binance Spot Daily Candles",
            "Price structure collection failed: " + message,
            "USDT"
        ),

        "ma50": unavailable_metric(
            "Binance Spot Daily Candles",
            "Price structure collection failed: " + message,
            "USDT"
        ),

        "ma200": unavailable_metric(
            "Binance Spot Daily Candles",
            "Price structure collection failed: " + message,
            "USDT"
        ),

        "rsi14": unavailable_metric(
            "Binance Spot Daily Candles",
            "Price structure collection failed: " + message,
            "RSI"
        ),

        "candle_updated_at": None
    }


# ============================================================
# COLLECT ALL DATA
# ============================================================

def collect_all_data():
    print("=" * 60)
    print("CRYPTO DADA LIVE SIGNALS ENGINE")
    print(f"Version: {VERSION}")
    print("Free Providers - No Paid API Keys")
    print("=" * 60)

    run_started_at = iso_now()

    print("\nCollecting data...\n")

    # Binance price structure
    try:
        price_structure = fetch_price_structure()

    except Exception as exc:
        price_structure = failed_price_structure(
            exc
        )

    # Independent provider calls
    etf_flows = run_safely(
        "ETF Flows",
        fetch_etf_flows
    )

    funding_rate = run_safely(
        "Funding Rate",
        fetch_funding_rate
    )

    open_interest = run_safely(
        "Open Interest",
        fetch_open_interest
    )

    futures_premium = run_safely(
        "Futures Premium",
        fetch_futures_premium
    )

    mvrv_z_score = run_safely(
        "MVRV Z-Score",
        fetch_mvrv_z_score
    )

    nupl = run_safely(
        "NUPL",
        fetch_nupl
    )

    fear_greed = run_safely(
        "Fear & Greed",
        fetch_fear_greed
    )

    run_completed_at = iso_now()

    payload = {
        "schema_version": SCHEMA_VERSION,
        "engine": "Crypto Dada Style Live Signals Engine",
        "engine_version": VERSION,
        "symbol": SYMBOL,
        "market": "Binance Spot",

        "fetched_at": run_completed_at,
        "run_started_at": run_started_at,
        "run_completed_at": run_completed_at,

        "price_structure": price_structure,

        "etf_flows": etf_flows,

        "funding_rate": funding_rate,

        "open_interest": open_interest,

        "futures_premium": futures_premium,

        "on_chain": {
            "mvrv_z_score": mvrv_z_score,
            "nupl": nupl
        },

        "retail_mania": fear_greed
    }

    return payload


# ============================================================
# JSON VALIDATION
# ============================================================

def validate_no_non_finite(
    value,
    path="root"
):
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(
                f"Non-finite number at {path}"
            )

    elif isinstance(value, dict):
        for key, item in value.items():
            validate_no_non_finite(
                item,
                f"{path}.{key}"
            )

    elif isinstance(value, list):
        for index, item in enumerate(value):
            validate_no_non_finite(
                item,
                f"{path}[{index}]"
            )


def validate_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError(
            "Payload must be a JSON object."
        )

    required = (
        "schema_version",
        "engine",
        "engine_version",
        "symbol",
        "market",
        "fetched_at",
        "price_structure",
        "etf_flows",
        "funding_rate",
        "open_interest",
        "futures_premium",
        "on_chain",
        "retail_mania"
    )

    for key in required:
        if key not in payload:
            raise ValueError(
                f"Missing required root key: {key}"
            )

    if payload["schema_version"] != SCHEMA_VERSION:
        raise ValueError(
            "Unexpected schema version."
        )

    if payload["engine_version"] != VERSION:
        raise ValueError(
            "Unexpected engine version."
        )

    validate_no_non_finite(payload)


# ============================================================
# ATOMIC JSON SAVE
# ============================================================

def save_json_atomically(payload):
    validate_payload(payload)

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    temporary_file = OUTPUT_FILE.with_suffix(
        OUTPUT_FILE.suffix + ".tmp"
    )

    with temporary_file.open(
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            payload,
            file,
            indent=2,
            ensure_ascii=False,
            allow_nan=False
        )

        file.write("\n")

    temporary_file.replace(
        OUTPUT_FILE
    )


# ============================================================
# REPORT
# ============================================================

def print_metric(name, metric):
    if not isinstance(metric, dict):
        print(
            f"{name} => UNAVAILABLE | None"
        )
        return

    print(
        f"{name} => "
        f"{metric.get('status', 'UNAVAILABLE')} | "
        f"{metric.get('value')}"
    )

    status = metric.get("status")

    if status in (
        "ERROR",
        "UNAVAILABLE",
        "STALE",
        "TIME_UNKNOWN"
    ):
        note = metric.get("note")

        if note:
            print(
                f"  NOTE: {note}"
            )


def print_report(payload):
    print("\nDATA STATUS")

    price = payload.get(
        "price_structure"
    ) or {}

    print_metric(
        "BTC Price",
        price.get("price")
    )

    print_metric(
        "BTC Support",
        price.get("support")
    )

    print_metric(
        "BTC Resistance",
        price.get("resistance")
    )

    print_metric(
        "MA20",
        price.get("ma20")
    )

    print_metric(
        "MA50",
        price.get("ma50")
    )

    print_metric(
        "MA200",
        price.get("ma200")
    )

    print_metric(
        "RSI14",
        price.get("rsi14")
    )

    etf = payload.get("etf_flows") or {}

    print_metric(
        "ETF Daily Flow",
        etf
    )

    print(
        "ETF 7-Day Flow => "
        f"{etf.get('seven_day_status', 'UNAVAILABLE')} | "
        f"{etf.get('seven_day_net_flow')}"
    )

    print_metric(
        "Funding Rate",
        payload.get("funding_rate")
    )

    print_metric(
        "Open Interest",
        payload.get("open_interest")
    )

    print_metric(
        "Futures Premium",
        payload.get("futures_premium")
    )

    on_chain = payload.get("on_chain") or {}

    print_metric(
        "MVRV Z-Score",
        on_chain.get("mvrv_z_score")
    )

    print_metric(
        "NUPL",
        on_chain.get("nupl")
    )

    print_metric(
        "Fear & Greed",
        payload.get("retail_mania")
    )


# ============================================================
# MAIN
# ============================================================

def main():
    try:
        payload = collect_all_data()

        save_json_atomically(
            payload
        )

        print_report(
            payload
        )

        print("\n" + "=" * 60)
        print(f"Engine Version: {VERSION}")
        print(f"JSON saved: {OUTPUT_FILE}")
        print(f"Fetched: {payload['fetched_at']}")
        print("=" * 60)

    except Exception as exc:
        print("\nFATAL ENGINE ERROR")

        print(
            f"{type(exc).__name__}: {str(exc)}"
        )

        raise


if __name__ == "__main__":
    main()
