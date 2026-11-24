
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CRYPTO DADA LIVE SIGNALS ENGINE
Version: 1.3.2

Free public data providers:
- Binance Spot
- CoinBoss Public API
- Explore21
- Alternative.me

No paid API key required.

Important:
- Missing data is represented as null, never as fake zero.
- Source observation time is kept separate from fetch time.
- Support/resistance use completed daily candle lows/highs.
- Old observations are marked STALE.
- One provider failure does not stop the remaining providers.
- JSON schema_version remains 1 for dashboard compatibility.
"""

import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request

from datetime import datetime, timezone
from pathlib import Path


# ============================================================
# CONFIGURATION
# ============================================================

VERSION = "1.3.2"
SCHEMA_VERSION = 1

SYMBOL = "BTCUSDT"
BINANCE_BASE = "https://api.binance.com"
COINBOSS_BASE = "https://www.coinboss.com"
EXPLORE21_BASE = "https://data.explore21.com"
ALTERNATIVE_BASE = "https://api.alternative.me"

OUTPUT_FILE = Path("data/live_signals.json")

HTTP_TIMEOUT = 20
USER_AGENT = "CryptoDadaLiveSignals/1.3.2"

PRICE_CANDLE_LIMIT = 210
SUPPORT_RESISTANCE_LOOKBACK = 20

# Data freshness thresholds
DEFAULT_MAX_AGE_HOURS = 48
DAILY_MAX_AGE_HOURS = 48
MVRV_MAX_AGE_HOURS = 48
FEAR_GREED_MAX_AGE_HOURS = 48


# ============================================================
# TIME AND BASIC HELPERS
# ============================================================

def utc_now():
    return datetime.now(timezone.utc)


def iso_now():
    return utc_now().isoformat(timespec="seconds")


def iso_from_ms(value):
    try:
        number = float(value)

        if not math.isfinite(number) or number <= 0:
            return None

        return datetime.fromtimestamp(
            number / 1000.0,
            tz=timezone.utc
        ).isoformat(timespec="seconds")

    except (TypeError, ValueError, OverflowError, OSError):
        return None


def parse_timestamp(value):
    """
    Convert supported timestamp formats to aware UTC datetime.

    Supported:
    - ISO timestamp strings
    - Unix seconds
    - Unix milliseconds
    - YYYY-MM-DD
    """

    if value is None:
        return None

    try:
        if isinstance(value, (int, float)):
            number = float(value)

            if not math.isfinite(number) or number <= 0:
                return None

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
                parsed = parsed.replace(tzinfo=timezone.utc)

            return parsed.astimezone(timezone.utc)

    except (TypeError, ValueError, OverflowError, OSError):
        return None

    return None


def finite_number(value):
    try:
        number = float(value)

        if not math.isfinite(number):
            return None

        return number

    except (TypeError, ValueError, OverflowError):
        return None


def safe_round(value, digits=4):
    number = finite_number(value)

    if number is None:
        return None

    return round(number, digits)


def age_hours(timestamp):
    parsed = parse_timestamp(timestamp)

    if parsed is None:
        return None

    difference = utc_now() - parsed
    return max(0.0, difference.total_seconds() / 3600.0)


def timestamp_from_date_or_value(value):
    """
    Extract a real observation timestamp from provider data.
    Returns None when the provider does not expose one.
    """

    return parse_timestamp(value).isoformat(timespec="seconds") \
        if parse_timestamp(value) else None


# ============================================================
# HTTP
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

        status_code = getattr(response, "status", 200)

        if status_code < 200 or status_code >= 300:
            raise RuntimeError(
                f"HTTP request failed: {status_code}"
            )

        raw = response.read().decode("utf-8")

        return json.loads(raw)


# ============================================================
# METRIC STRUCTURE
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


def unavailable_metric(source, note, unit=None):
    return make_metric(
        value=None,
        unit=unit,
        status="UNAVAILABLE",
        source=source,
        source_updated_at=None,
        note=note
    )


def apply_freshness(metric, max_age_hours):
    """
    Mark an observation STALE when its actual source timestamp
    is older than the configured limit.

    Missing source timestamp is not treated as fresh.
    """

    if not isinstance(metric, dict):
        return metric

    source_time = metric.get("source_updated_at")

    if not source_time:
        if metric.get("status") not in (
            "UNAVAILABLE",
            "ERROR",
            "PROXY_ONLY"
        ):
            metric["status"] = "TIME_UNKNOWN"

            old_note = metric.get("note")
            timestamp_note = (
                "Provider did not expose a verified observation "
                "timestamp. Fetch time is shown separately."
            )

            metric["note"] = (
                f"{old_note} {timestamp_note}"
                if old_note else timestamp_note
            )

        return metric

    age = age_hours(source_time)

    if age is None:
        metric["status"] = "TIME_UNKNOWN"
        metric["data_age_hours"] = None
        return metric

    metric["data_age_hours"] = round(age, 2)

    if age > max_age_hours:
        metric["status"] = "STALE"

        old_note = metric.get("note")
        stale_note = (
            f"Source observation is {age:.1f} hours old; "
            f"freshness limit is {max_age_hours} hours."
        )

        metric["note"] = (
            f"{old_note} {stale_note}"
            if old_note else stale_note
        )

    return metric


def run_safely(name, function, *args, **kwargs):
    """
    Run one provider independently.
    A provider error must not stop other metrics.
    """

    try:
        result = function(*args, **kwargs)

        if not isinstance(result, dict):
            raise RuntimeError(
                "Provider returned an invalid metric structure."
            )

        return result

    except Exception as exc:
        message = f"{type(exc).__name__}: {str(exc)}"

        print(f"{name} => ERROR | {message}")

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
    url = f"{BINANCE_BASE}/api/v3/ticker/price"

    data = http_get_json(
        url,
        {"symbol": SYMBOL}
    )

    price = finite_number(data.get("price"))

    if price is None or price <= 0:
        raise RuntimeError("Invalid Binance spot price.")

    return make_metric(
        value=price,
        unit="USDT",
        status="OK",
        source="Binance Spot BTCUSDT Ticker",
        source_updated_at=None,
        note=(
            "Live ticker response. Binance ticker price endpoint "
            "does not provide an observation timestamp; fetch time "
            "is recorded separately."
        )
    )


# ============================================================
# BINANCE DAILY CANDLES
# ============================================================

def fetch_daily_candles():
    url = f"{BINANCE_BASE}/api/v3/klines"

    data = http_get_json(
        url,
        {
            "symbol": SYMBOL,
            "interval": "1d",
            "limit": PRICE_CANDLE_LIMIT
        }
    )

    if not isinstance(data, list) or len(data) < 200:
        raise RuntimeError(
            "Insufficient Binance daily candle history."
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

            if (
                candle["open"] is None
                or candle["high"] is None
                or candle["low"] is None
                or candle["close"] is None
            ):
                continue

            candles.append(candle)

        except (TypeError, ValueError, IndexError):
            continue

    if len(candles) < 200:
        raise RuntimeError(
            "Not enough valid daily candles after parsing."
        )

    # Exclude the current, potentially incomplete daily candle.
    now_ms = int(time.time() * 1000)

    completed = [
        candle
        for candle in candles
        if candle["close_time"] < now_ms
    ]

    if len(completed) < 200:
        raise RuntimeError(
            "Not enough completed daily candles."
        )

    return completed


def calculate_sma(values, period):
    if len(values) < period:
        return None

    sample = values[-period:]

    if any(value is None for value in sample):
        return None

    return sum(sample) / period


def calculate_rsi(values, period=14):
    if len(values) < period + 1:
        return None

    changes = [
        values[index] - values[index - 1]
        for index in range(len(values) - period, len(values))
    ]

    gains = [
        change if change > 0 else 0.0
        for change in changes
    ]

    losses = [
        abs(change) if change < 0 else 0.0
        for change in changes
    ]

    average_gain = sum(gains) / period
    average_loss = sum(losses) / period

    if average_loss == 0:
        return 100.0 if average_gain > 0 else 50.0

    relative_strength = average_gain / average_loss

    return 100.0 - (
        100.0 / (1.0 + relative_strength)
    )


def fetch_price_structure():
    candles = fetch_daily_candles()

    closes = [candle["close"] for candle in candles]
    latest_candle = candles[-1]

    ma20 = calculate_sma(closes, 20)
    ma50 = calculate_sma(closes, 50)
    ma200 = calculate_sma(closes, 200)
    rsi14 = calculate_rsi(closes, 14)

    # Use the previous 20 completed candles for S/R.
    # The latest completed candle is excluded from the
    # support/resistance lookback to avoid using the same
    # candle as both current reference and historical range.
    sr_candles = candles[-(SUPPORT_RESISTANCE_LOOKBACK + 1):-1]

    if len(sr_candles) < SUPPORT_RESISTANCE_LOOKBACK:
        raise RuntimeError(
            "Insufficient candles for support/resistance."
        )

    support = min(
        candle["low"] for candle in sr_candles
    )

    resistance = max(
        candle["high"] for candle in sr_candles
    )

    candle_timestamp = iso_from_ms(
        latest_candle["close_time"]
    )

    price = fetch_binance_price()

    return {
        "price": price,

        "support": make_metric(
            value=support,
            unit="USDT",
            status="OK",
            source="Binance Spot Daily Candles",
            source_updated_at=candle_timestamp,
            note=(
                f"Lowest Low of the previous "
                f"{SUPPORT_RESISTANCE_LOOKBACK} completed daily candles."
            ),
            extra={
                "lookback": (
                    f"{SUPPORT_RESISTANCE_LOOKBACK} completed daily candles"
                ),
                "method": "lowest low"
            }
        ),

        "resistance": make_metric(
            value=resistance,
            unit="USDT",
            status="OK",
            source="Binance Spot Daily Candles",
            source_updated_at=candle_timestamp,
            note=(
                f"Highest High of the previous "
                f"{SUPPORT_RESISTANCE_LOOKBACK} completed daily candles."
            ),
            extra={
                "lookback": (
                    f"{SUPPORT_RESISTANCE_LOOKBACK} completed daily candles"
                ),
                "method": "highest high"
            }
        ),

        "ma20": make_metric(
            value=ma20,
            unit="USDT",
            status="OK" if ma20 is not None else "UNAVAILABLE",
            source="Binance Spot Daily Candles",
            source_updated_at=candle_timestamp,
            note="20-day simple moving average."
        ),

        "ma50": make_metric(
            value=ma50,
            unit="USDT",
            status="OK" if ma50 is not None else "UNAVAILABLE",
            source="Binance Spot Daily Candles",
            source_updated_at=candle_timestamp,
            note="50-day simple moving average."
        ),

        "ma200": make_metric(
            value=ma200,
            unit="USDT",
            status="OK" if ma200 is not None else "UNAVAILABLE",
            source="Binance Spot Daily Candles",
            source_updated_at=candle_timestamp,
            note="200-day simple moving average."
        ),

        "rsi14": make_metric(
            value=rsi14,
            unit="RSI",
            status="OK" if rsi14 is not None else "UNAVAILABLE",
            source="Binance Spot Daily Candles",
            source_updated_at=candle_timestamp,
            note="14-period RSI calculated from completed daily closes."
        ),

        "candle_updated_at": candle_timestamp
    }


# ============================================================
# COINBOSS ETF FLOWS
# ============================================================

def fetch_etf_flows():
    url = f"{COINBOSS_BASE}/api/etf/flows"

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

    observation_time = (
        timestamp_from_date_or_value(latest.get("date"))
    )

    if daily_flow is None and weekly_flow is None:
        raise RuntimeError(
            "ETF response did not contain a valid daily or 7-day flow."
        )

    if daily_flow is None:
        daily_status = "UNAVAILABLE"
        daily_note = "Provider did not return a valid latest daily flow."
    else:
        daily_status = "OK"
        daily_note = (
            "Latest reported daily net ETF flow. "
            "A zero value is preserved as a genuine provider value."
        )

    if weekly_flow is None:
        weekly_status = "UNAVAILABLE"
        weekly_note = "Provider did not return a valid 7-day net flow."
    else:
        weekly_status = "OK"
        weekly_note = "Provider-reported cumulative 7-day net ETF flow."

    return {
        "value": daily_flow,
        "unit": "million USD",
        "status": daily_status,
        "source": "CoinBoss Public ETF API",
        "source_updated_at": observation_time,
        "fetched_at": iso_now(),
        "data_age_hours": age_hours(observation_time),
        "note": daily_note,

        "daily_net_flow": daily_flow,
        "daily_unit": "million USD",

        "seven_day_net_flow": weekly_flow,
        "seven_day_unit": "million USD",
        "seven_day_status": weekly_status,
        "seven_day_note": weekly_note,

        # Keep the old field name for compatibility.
        "sum_7d": weekly_flow,

        "aum": aum,
        "aum_unit": "million USD",

        "classification": (
            "Unavailable"
            if daily_flow is None
            else (
                "Positive"
                if daily_flow > 0
                else "Negative"
                if daily_flow < 0
                else "Neutral"
            )
        ),

        "update_frequency": "Daily"
    }


# ============================================================
# COINBOSS FUNDING RATE
# ============================================================

def fetch_funding_rate():
    url = f"{COINBOSS_BASE}/api/sd/funding"

    data = http_get_json(
        url,
        {"coin": "BTC"}
    )

    value = finite_number(
        data.get("oi_weighted_8h")
    )

    if value is None:
        value = finite_number(
            data.get("avg_8h")
        )

    if value is None:
        raise RuntimeError(
            "Funding API did not return a valid funding rate."
        )

    # Provider returns a fraction; convert to percentage.
    percentage = value * 100.0

    source_timestamp = timestamp_from_date_or_value(
        data.get("now")
    )

    return make_metric(
        value=percentage,
        unit="% per 8h",
        status="OK",
        source="CoinBoss Public Funding API",
        source_updated_at=source_timestamp,
        note=(
            "Open-interest-weighted 8-hour funding rate. "
            "Provider fraction converted to percentage."
        ),
        extra={
            "method": "oi_weighted_8h",
            "raw_fraction": value
        }
    )


# ============================================================
# COINBOSS OPEN INTEREST
# ============================================================

def fetch_open_interest():
    url = f"{COINBOSS_BASE}/api/sd/oi"

    data = http_get_json(
        url,
        {"coin": "BTC"}
    )

    value = finite_number(
        data.get("total_usd_single_adjusted")
    )

    if value is None:
        value = finite_number(
            data.get("total_usd")
        )

    if value is None:
        raise RuntimeError(
            "Open interest API did not return a valid USD value."
        )

    source_timestamp = timestamp_from_date_or_value(
        data.get("asof")
    )

    return make_metric(
        value=value,
        unit="USD",
        status="OK",
        source="CoinBoss Public Open Interest API",
        source_updated_at=source_timestamp,
        note=(
            "Total BTC open interest in USD. "
            "Preferred adjusted value, with total_usd fallback."
        )
    )


# ============================================================
# COINBOSS FUTURES BASIS / PREMIUM
# ============================================================

def fetch_futures_premium():
    url = f"{COINBOSS_BASE}/api/sd/basis"

    data = http_get_json(
        url,
        {"coin": "BTC"}
    )

    perp = data.get("perp") or {}

    value = finite_number(
        perp.get("oi_weighted_pct")
    )

    if value is None:
        value = finite_number(
            perp.get("median_pct")
        )

    if value is None:
        raise RuntimeError(
            "Basis API did not return a valid perp basis."
        )

    # Do not use data['now'] as the observation timestamp.
    # It may only be the response/server time.
    meta = data.get("meta") or {}

    source_timestamp = None

    for key in (
        "source_updated_at",
        "updated_at",
        "timestamp",
        "asof",
        "time"
    ):
        candidate = timestamp_from_date_or_value(
            meta.get(key)
        )

        if candidate:
            source_timestamp = candidate
            break

    note = (
        "Perpetual futures basis percentage. "
        "This is not a pure spot premium measurement."
    )

    if source_timestamp is None:
        note += (
            " Provider did not expose a verified underlying "
            "observation timestamp; fetch time is shown separately."
        )

    return make_metric(
        value=value,
        unit="%",
        status="OK" if source_timestamp else "TIME_UNKNOWN",
        source="CoinBoss Public Futures Basis API",
        source_updated_at=source_timestamp,
        note=note,
        extra={
            "method": (
                "oi_weighted_pct"
                if perp.get("oi_weighted_pct") is not None
                else "median_pct"
            )
        }
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

    # Support common response layouts without assuming one
    # undocumented field structure.
    candidates = []

    if isinstance(data, dict):
        candidates.append(data)

        for key in ("data", "result", "metric"):
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

    timestamp_keys = (
        "date",
        "timestamp",
        "updated_at",
        "as_of",
        "time"
    )

    for candidate in candidates:
        if value is None:
            for key in value_keys:
                possible = finite_number(candidate.get(key))

                if possible is not None:
                    value = possible
                    break

        if source_timestamp is None:
            for key in timestamp_keys:
                possible_time = timestamp_from_date_or_value(
                    candidate.get(key)
                )

                if possible_time:
                    source_timestamp = possible_time
                    break

    if value is None:
        raise RuntimeError(
            "Explore21 response did not contain a valid MVRV Z-Score."
        )

    metric = make_metric(
        value=value,
        unit="Z-Score",
        status="OK",
        source="Explore21 Bitcoin MVRV Z-Score",
        source_updated_at=source_timestamp,
        note=(
            "On-chain MVRV Z-Score. "
            "Value is retained when stale, but marked accordingly."
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
    # NUPL is not currently listed in the verified free
    # Explore21 metric catalog used by this engine.
    # Do not substitute an unverified provider or fabricate data.

    return unavailable_metric(
        source="Explore21",
        note=(
            "NUPL is not currently listed in the verified "
            "free Explore21 metric catalog. No unverified "
            "alternative provider is being used."
        ),
        unit="Ratio"
    )


# ============================================================
# ALTERNATIVE.ME FEAR AND GREED
# ============================================================

def fetch_fear_greed():
    url = f"{ALTERNATIVE_BASE}/fng/"

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
            "Fear & Greed API returned an invalid value."
        )

    classification = latest.get(
        "value_classification"
    )

    source_timestamp = timestamp_from_date_or_value(
        latest.get("timestamp")
    )

    metric = make_metric(
        value=value,
        unit="Index (0-100)",
        status="PROXY_ONLY",
        source="Alternative.me Fear & Greed Index",
        source_updated_at=source_timestamp,
        note=(
            "Sentiment proxy only. This is not a direct measurement "
            "of retail trading activity or retail positioning."
        ),
        extra={
            "classification": classification,
            "proxy_only": True
        }
    )

    return apply_freshness(
        metric,
        FEAR_GREED_MAX_AGE_HOURS
    )


# ============================================================
# DATA COLLECTION
# ============================================================

def collect_all_data():
    print("=" * 60)
    print("CRYPTO DADA LIVE SIGNALS ENGINE")
    print(f"Version: {VERSION}")
    print("Free Providers - No Paid API Keys")
    print("=" * 60)

    run_started_at = iso_now()

    print("\nCollecting market data...\n")

    # Price structure is collected independently.
    try:
        price_structure = fetch_price_structure()

    except Exception as exc:
        print(
            "Price Structure => ERROR | "
            f"{type(exc).__name__}: {str(exc)}"
        )

        price_structure = {
            "price": make_metric(
                source="Binance Spot BTCUSDT",
                status="ERROR",
                note=str(exc)
            ),
            "support": unavailable_metric(
                "Binance Spot Daily Candles",
                "Price structure collection failed."
            ),
            "resistance": unavailable_metric(
                "Binance Spot Daily Candles",
                "Price structure collection failed."
            ),
            "ma20": unavailable_metric(
                "Binance Spot Daily Candles",
                "Price structure collection failed."
            ),
            "ma50": unavailable_metric(
                "Binance Spot Daily Candles",
                "Price structure collection failed."
            ),
            "ma200": unavailable_metric(
                "Binance Spot Daily Candles",
                "Price structure collection failed."
            ),
            "rsi14": unavailable_metric(
                "Binance Spot Daily Candles",
                "Price structure collection failed."
            ),
            "candle_updated_at": None
        }

    # Independent providers: one failure must not block another.
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

    # Root fetched_at is set after all provider requests finish.
    completed_at = iso_now()

    payload = {
        "schema_version": SCHEMA_VERSION,
        "engine": "Crypto Dada Style Live Signals Engine",
        "engine_version": VERSION,
        "symbol": SYMBOL,
        "market": "Binance Spot",

        # Keep fetched_at for existing dashboard compatibility.
        # It now represents the end of the collection run.
        "fetched_at": completed_at,
        "run_started_at": run_started_at,
        "run_completed_at": completed_at,

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
# JSON VALIDATION AND SAVE
# ============================================================

def validate_no_non_finite(value, path="root"):
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(
                f"Non-finite number found at {path}"
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


def save_json_atomically(payload):
    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    validate_no_non_finite(payload)

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

    temporary_file.replace(OUTPUT_FILE)


# ============================================================
# STATUS REPORT
# ============================================================

def get_metric_value(metric):
    if not isinstance(metric, dict):
        return None

    return metric.get("value")


def get_metric_status(metric):
    if not isinstance(metric, dict):
        return "UNAVAILABLE"

    return metric.get("status", "UNAVAILABLE")


def print_status(name, metric):
    value = get_metric_value(metric)
    status = get_metric_status(metric)

    print(
        f"{name} => {status} | {value}"
    )

    if isinstance(metric, dict):
        note = metric.get("note")

        if note and status in (
            "ERROR",
            "UNAVAILABLE",
            "STALE",
            "TIME_UNKNOWN"
        ):
            print(f"  NOTE: {note}")


def print_report(payload):
    print("\nDATA STATUS")

    price = payload["price_structure"]

    print_status(
        "BTC Price",
        price.get("price")
    )

    print_status(
        "BTC Support",
        price.get("support")
    )

    print_status(
        "BTC Resistance",
        price.get("resistance")
    )

    print_status(
        "MA20",
        price.get("ma20")
    )

    print_status(
        "MA50",
        price.get("ma50")
    )

    print_status(
        "MA200",
        price.get("ma200")
    )

    print_status(
        "RSI14",
        price.get("rsi14")
    )

    print_status(
        "ETF Daily Flow",
        payload.get("etf_flows")
    )

    etf = payload.get("etf_flows") or {}

    print(
        "ETF 7-Day Flow => "
        f"{etf.get('seven_day_status', 'UNAVAILABLE')} | "
        f"{etf.get('seven_day_net_flow')}"
    )

    print_status(
        "Funding Rate",
        payload.get("funding_rate")
    )

    print_status(
        "Open Interest",
        payload.get("open_interest")
    )

    print_status(
        "Futures Premium",
        payload.get("futures_premium")
    )

    on_chain = payload.get("on_chain") or {}

    print_status(
        "MVRV Z-Score",
        on_chain.get("mvrv_z_score")
    )

    print_status(
        "NUPL",
        on_chain.get("nupl")
    )

    print_status(
        "Fear & Greed",
        payload.get("retail_mania")
    )


# ============================================================
# MAIN
# ============================================================

def main():
    try:
        payload = collect_all_data()

        save_json_atomically(payload)

        print_report(payload)

        print("\n" + "=" * 60)
        print(f"Engine Version: {VERSION}")
        print(f"JSON saved: {OUTPUT_FILE}")
        print(f"Fetched: {payload.get('fetched_at')}")
        print("=" * 60)

    except Exception as exc:
        print("\nFATAL ENGINE ERROR")
        print(f"{type(exc).__name__}: {str(exc)}")
        raise


if __name__ == "__main__":
    main()
