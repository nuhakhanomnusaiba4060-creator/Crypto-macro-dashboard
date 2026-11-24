
#!/usr/bin/env python3
"""
Crypto Dada Style Live Signals Engine
Version: 1.2.0

Providers:
- Binance Spot: BTC price and daily candles
- CoinGlass API V4: ETF flows and futures market data
- Glassnode API: MVRV Z-Score and NUPL
- Alternative.me: Fear & Greed sentiment proxy

Output:
data/live_signals.json

API keys must be stored in GitHub Actions Secrets:
COINGLASS_API_KEY
GLASSNODE_API_KEY
"""

import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from datetime import datetime, timezone
from pathlib import Path


VERSION = "1.2.0"
OUTPUT_FILE = Path("data/live_signals.json")

SPOT_BASE = "https://api.binance.com"
SPOT_BACKUP = "https://data-api.binance.vision"

COINGLASS_BASE = "https://open-api-v4.coinglass.com"
GLASSNODE_BASE = "https://api.glassnode.com"

REQUEST_TIMEOUT = 20


# ---------------------------------------------------------
# COMMON HELPERS
# ---------------------------------------------------------

def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def timestamp_from_ms(value):
    try:
        return datetime.fromtimestamp(
            float(value) / 1000,
            timezone.utc
        ).isoformat(timespec="seconds")
    except (TypeError, ValueError, OverflowError):
        return None


def timestamp_from_seconds(value):
    try:
        return datetime.fromtimestamp(
            float(value),
            timezone.utc
        ).isoformat(timespec="seconds")
    except (TypeError, ValueError, OverflowError):
        return None


def safe_float(value):
    try:
        number = float(value)

        if math.isfinite(number):
            return number

    except (TypeError, ValueError, OverflowError):
        pass

    return None


def http_get(url, headers=None):
    request_headers = {
        "User-Agent": "CryptoDada-LiveSignals/1.2.0",
        "Accept": "application/json"
    }

    if headers:
        request_headers.update(headers)

    request = urllib.request.Request(
        url,
        headers=request_headers
    )

    with urllib.request.urlopen(
        request,
        timeout=REQUEST_TIMEOUT
    ) as response:

        raw = response.read().decode("utf-8")

        return json.loads(raw)


def build_url(base, path, params=None):
    url = base.rstrip("/") + "/" + path.lstrip("/")

    if params:
        url += "?" + urllib.parse.urlencode(params)

    return url


def get_json(base, path, params=None, headers=None):
    return http_get(
        build_url(base, path, params),
        headers=headers
    )


def unavailable(source="Not connected", error=None):
    result = {
        "value": None,
        "unit": "",
        "status": "UNAVAILABLE",
        "source": source,
        "source_updated_at": None,
        "fetched_at": utc_now()
    }

    if error:
        result["error"] = str(error)[:350]

    return result


def make_metric(
    value,
    unit="",
    source="",
    source_updated_at=None,
    status="OK"
):
    if value is None:
        return unavailable(source or "Unknown source")

    return {
        "value": value,
        "unit": unit,
        "status": status,
        "source": source,
        "source_updated_at": source_updated_at,
        "fetched_at": utc_now()
    }


def safe_build(function, source_name):
    try:
        return function()

    except Exception as exc:
        print(source_name, "ERROR:", str(exc)[:250])

        return unavailable(
            source=source_name,
            error=exc
        )


# ---------------------------------------------------------
# BINANCE SPOT
# ---------------------------------------------------------

def get_spot_json(path, params=None):
    errors = []

    for base in (SPOT_BASE, SPOT_BACKUP):

        try:
            return get_json(
                base,
                path,
                params
            )

        except Exception as exc:
            errors.append(str(exc))

    raise RuntimeError(
        "Binance Spot API unavailable: " +
        " | ".join(errors)
    )


def calculate_sma(values, period):
    if len(values) < period:
        return None

    return sum(values[-period:]) / period


def calculate_rsi(values, period=14):
    if len(values) < period + 1:
        return None

    changes = [
        values[i] - values[i - 1]
        for i in range(
            len(values) - period,
            len(values)
        )
    ]

    gains = [max(change, 0) for change in changes]
    losses = [abs(min(change, 0)) for change in changes]

    average_gain = sum(gains) / period
    average_loss = sum(losses) / period

    if average_loss == 0:
        return 100.0 if average_gain > 0 else 50.0

    rs = average_gain / average_loss

    return 100 - (100 / (1 + rs))


def fetch_btc_price():
    data = get_spot_json(
        "/api/v3/ticker/price",
        {"symbol": "BTCUSDT"}
    )

    price = safe_float(data.get("price"))

    if price is None:
        raise RuntimeError("Invalid BTC Spot price")

    return price


def fetch_btc_daily_candles():
    data = get_spot_json(
        "/api/v3/klines",
        {
            "symbol": "BTCUSDT",
            "interval": "1d",
            "limit": 210
        }
    )

    if not isinstance(data, list):
        raise RuntimeError("Invalid Binance candle response")

    now_ms = int(time.time() * 1000)

    closed = [
        candle for candle in data
        if len(candle) > 6
        and int(candle[6]) < now_ms
    ]

    if len(closed) < 200:
        raise RuntimeError(
            "Not enough closed daily candles for MA200"
        )

    closes = []

    for candle in closed:
        value = safe_float(candle[4])

        if value is not None:
            closes.append(value)

    if len(closes) < 200:
        raise RuntimeError("Invalid daily close values")

    candle_updated = timestamp_from_ms(closed[-1][6])

    return closes, candle_updated


def build_price_structure():
    current_price = fetch_btc_price()

    closes, candle_updated = fetch_btc_daily_candles()

    ma20 = calculate_sma(closes, 20)
    ma50 = calculate_sma(closes, 50)
    ma200 = calculate_sma(closes, 200)
    rsi14 = calculate_rsi(closes, 14)

    # Previous 20 completed daily candles.
    previous_candles = closes[-21:-1]

    support = min(previous_candles)
    resistance = max(previous_candles)

    return {
        "price": make_metric(
            current_price,
            "USDT",
            "Binance Spot BTCUSDT Ticker",
            utc_now()
        ),

        "support": make_metric(
            support,
            "USDT",
            "Binance Spot Daily Candles",
            candle_updated
        ),

        "resistance": make_metric(
            resistance,
            "USDT",
            "Binance Spot Daily Candles",
            candle_updated
        ),

        "ma20": make_metric(
            ma20,
            "USDT",
            "Binance Spot Daily Candles",
            candle_updated
        ),

        "ma50": make_metric(
            ma50,
            "USDT",
            "Binance Spot Daily Candles",
            candle_updated
        ),

        "ma200": make_metric(
            ma200,
            "USDT",
            "Binance Spot Daily Candles",
            candle_updated
        ),

        "rsi14": make_metric(
            rsi14,
            "RSI",
            "Binance Spot Daily Candles",
            candle_updated
        ),

        "candle_updated_at": candle_updated,
        "status": "OK"
    }


def build_price_safely():
    try:
        return build_price_structure()

    except Exception as exc:
        return {
            "price": unavailable("Binance Spot API", exc),
            "support": unavailable("Binance Daily Candles", exc),
            "resistance": unavailable("Binance Daily Candles", exc),
            "ma20": unavailable("Binance Daily Candles", exc),
            "ma50": unavailable("Binance Daily Candles", exc),
            "ma200": unavailable("Binance Daily Candles", exc),
            "rsi14": unavailable("Binance Daily Candles", exc),
            "candle_updated_at": None,
            "status": "UNAVAILABLE",
            "error": str(exc)[:350]
        }


# ---------------------------------------------------------
# COINGLASS API V4
# ---------------------------------------------------------

def coinglass_get(path, params=None):
    api_key = os.getenv("COINGLASS_API_KEY", "").strip()

    if not api_key:
        raise RuntimeError(
            "COINGLASS_API_KEY GitHub Secret is missing"
        )

    response = get_json(
        COINGLASS_BASE,
        path,
        params,
        headers={
            "CG-API-KEY": api_key
        }
    )

    if not isinstance(response, dict):
        raise RuntimeError("Invalid CoinGlass response")

    if str(response.get("code")) != "0":
        raise RuntimeError(
            "CoinGlass API error: " +
            str(response.get("msg", response.get("code")))
        )

    return response.get("data")


def build_etf_flows():
    data = coinglass_get(
        "/api/etf/bitcoin/flow-history"
    )

    if not isinstance(data, list) or not data:
        raise RuntimeError("Bitcoin ETF flow data unavailable")

    # Latest available daily record.
    latest = data[-1]

    flow = safe_float(latest.get("flow_usd"))

    if flow is None:
        raise RuntimeError("Latest ETF net flow is missing")

    timestamp = timestamp_from_ms(
        latest.get("timestamp")
    )

    if not timestamp:
        raise RuntimeError("ETF source timestamp is missing")

    age_seconds = (
        datetime.now(timezone.utc)
        - datetime.fromisoformat(timestamp)
    ).total_seconds()

    status = "OK"

    if age_seconds > 72 * 60 * 60:
        status = "STALE"

    result = make_metric(
        flow,
        "USD",
        "CoinGlass Bitcoin Spot ETF Flow",
        timestamp,
        status
    )

    result["classification"] = (
        "Net Inflow" if flow > 0
        else "Net Outflow" if flow < 0
        else "Neutral"
    )

    result["record_date"] = timestamp[:10]
    result["update_frequency"] = "Daily"
    result["note"] = (
        "Positive value means net inflow; "
        "negative value means net outflow."
    )

    result["data_age_hours"] = round(
        max(age_seconds, 0) / 3600,
        2
    )

    return result


def fetch_coinglass_btc_pairs():
    data = coinglass_get(
        "/api/futures/pairs-markets",
        {"symbol": "BTC"}
    )

    if not isinstance(data, list) or not data:
        raise RuntimeError("CoinGlass BTC Futures market data unavailable")

    return data


def find_binance_btcusdt(pairs):
    for item in pairs:

        exchange = str(
            item.get("exchange_name", "")
        ).lower()

        instrument = str(
            item.get("instrument_id", "")
        ).upper()

        if exchange == "binance" and instrument == "BTCUSDT":
            return item

    raise RuntimeError(
        "CoinGlass did not return Binance BTCUSDT Futures pair"
    )


def build_futures_market():
    pairs = fetch_coinglass_btc_pairs()

    item = find_binance_btcusdt(pairs)

    funding = safe_float(item.get("funding_rate"))
    oi_btc = safe_float(item.get("open_interest_quantity"))
    oi_usd = safe_float(item.get("open_interest_usd"))

    current_price = safe_float(item.get("current_price"))
    index_price = safe_float(item.get("index_price"))

    fetched = utc_now()

    if funding is None:
        funding_metric = unavailable(
            "CoinGlass Binance Futures Funding Rate",
            "Funding rate field is missing"
        )
    else:
        funding_metric = make_metric(
            funding,
            "%",
            "CoinGlass Binance BTCUSDT Futures",
            fetched
        )

    if oi_btc is None:
        oi_metric = unavailable(
            "CoinGlass Binance Futures Open Interest",
            "Open interest quantity is missing"
        )
    else:
        oi_metric = make_metric(
            oi_btc,
            "BTC",
            "CoinGlass Binance BTCUSDT Futures",
            fetched
        )

        if oi_usd is not None:
            oi_metric["value_usd"] = oi_usd
            oi_metric["value_usd_unit"] = "USD"

    if (
        current_price is None
        or index_price is None
        or index_price == 0
    ):
        premium_metric = unavailable(
            "CoinGlass Binance Futures Premium",
            "Current price or index price is missing"
        )
    else:
        premium = (
            (current_price - index_price)
            / index_price
        ) * 100

        premium_metric = make_metric(
            premium,
            "%",
            "CoinGlass Binance Futures Current Price vs Index Price",
            fetched
        )

        premium_metric["current_price"] = current_price
        premium_metric["index_price"] = index_price

    return {
        "funding_rate": funding_metric,
        "open_interest": oi_metric,
        "futures_premium": premium_metric
    }


# ---------------------------------------------------------
# GLASSNODE ON-CHAIN API
# ---------------------------------------------------------

def glassnode_get(path):
    api_key = os.getenv("GLASSNODE_API_KEY", "").strip()

    if not api_key:
        raise RuntimeError(
            "GLASSNODE_API_KEY GitHub Secret is missing"
        )

    params = {
        "a": "BTC",
        "i": "24h",
        "f": "json",
        "api_key": api_key
    }

    data = get_json(
        GLASSNODE_BASE,
        path,
        params
    )

    if not isinstance(data, list) or not data:
        raise RuntimeError(
            "Glassnode returned no metric data"
        )

    valid = []

    for item in data:
        if not isinstance(item, dict):
            continue

        value = safe_float(item.get("v"))
        timestamp = safe_float(item.get("t"))

        if value is not None and timestamp is not None:
            valid.append((timestamp, value))

    if not valid:
        raise RuntimeError(
            "Glassnode metric has no valid values"
        )

    valid.sort(key=lambda row: row[0])

    return valid[-1]


def build_glassnode_metric(
    path,
    metric_name,
    unit=""
):
    timestamp, value = glassnode_get(path)

    source_time = timestamp_from_seconds(timestamp)

    if not source_time:
        raise RuntimeError(
            metric_name + " source timestamp is invalid"
        )

    age_seconds = (
        datetime.now(timezone.utc)
        - datetime.fromisoformat(source_time)
    ).total_seconds()

    status = "OK"

    # Daily on-chain data older than 72h is not presented as fresh.
    if age_seconds > 72 * 60 * 60:
        status = "STALE"

    result = make_metric(
        value,
        unit,
        "Glassnode BTC " + metric_name,
        source_time,
        status
    )

    result["update_frequency"] = "Daily"

    result["data_age_hours"] = round(
        max(age_seconds, 0) / 3600,
        2
    )

    return result


def build_mvrv():
    return build_glassnode_metric(
        "/v1/metrics/market/mvrv_z_score",
        "MVRV Z-Score"
    )


def build_nupl():
    return build_glassnode_metric(
        "/v1/metrics/indicators/net_unrealized_profit_loss",
        "NUPL"
    )


# ---------------------------------------------------------
# ALTERNATIVE.ME FEAR & GREED
# ---------------------------------------------------------

def build_retail_sentiment():
    data = http_get(
        "https://api.alternative.me/fng/?limit=1&format=json"
    )

    entries = data.get("data", [])

    if not entries:
        raise RuntimeError("Fear & Greed data unavailable")

    item = entries[0]

    value = safe_float(item.get("value"))

    if value is None:
        raise RuntimeError("Invalid Fear & Greed value")

    timestamp_value = safe_float(
        item.get("timestamp")
    )

    source_time = (
        timestamp_from_seconds(timestamp_value)
        if timestamp_value is not None
        else None
    )

    return {
        "value": value,
        "unit": "index / 100",
        "status": "PROXY_ONLY",
        "classification": item.get(
            "value_classification",
            "Unknown"
        ),
        "source": "Alternative.me Fear & Greed Index",
        "source_updated_at": source_time,
        "fetched_at": utc_now(),
        "update_frequency": "Daily",
        "note": (
            "Sentiment proxy only. This is not direct retail "
            "trading activity or verified retail buying/selling data."
        )
    }


# ---------------------------------------------------------
# MAIN PAYLOAD
# ---------------------------------------------------------

def build_payload():
    fetched_at = utc_now()

    futures = safe_build(
        build_futures_market,
        "CoinGlass Futures Market"
    )

    if not isinstance(futures, dict) or (
        "funding_rate" not in futures
    ):
        futures = {
            "funding_rate": unavailable(
                "CoinGlass Funding Rate"
            ),
            "open_interest": unavailable(
                "CoinGlass Open Interest"
            ),
            "futures_premium": unavailable(
                "CoinGlass Futures Premium"
            )
        }

    payload = {
        "schema_version": 1,
        "engine": "Crypto Dada Style Live Signals Engine",
        "engine_version": VERSION,
        "symbol": "BTCUSDT",
        "market": "Binance Spot",
        "fetched_at": fetched_at,

        "price_structure": build_price_safely(),

        "etf_flows": safe_build(
            build_etf_flows,
            "CoinGlass Bitcoin ETF Flow"
        ),

        "funding_rate": futures["funding_rate"],

        "open_interest": futures["open_interest"],

        "futures_premium": futures["futures_premium"],

        "on_chain": {
            "mvrv_z_score": safe_build(
                build_mvrv,
                "Glassnode MVRV Z-Score"
            ),

            "nupl": safe_build(
                build_nupl,
                "Glassnode NUPL"
            )
        },

        "retail_mania": safe_build(
            build_retail_sentiment,
            "Alternative.me Fear & Greed"
        )
    }

    return payload


# ---------------------------------------------------------
# SAVE JSON SAFELY
# ---------------------------------------------------------

def save_payload(payload):
    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    temporary_file = OUTPUT_FILE.with_suffix(".tmp")

    temporary_file.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
            allow_nan=False
        ),
        encoding="utf-8"
    )

    temporary_file.replace(OUTPUT_FILE)


# ---------------------------------------------------------
# RUN
# ---------------------------------------------------------

def main():
    print("Starting Crypto Dada Style Live Signals Engine...")
    print("Version:", VERSION)

    payload = build_payload()

    save_payload(payload)

    print("Output saved:", OUTPUT_FILE)
    print("Fetched at:", payload["fetched_at"])

    sections = [
        "price_structure",
        "etf_flows",
        "funding_rate",
        "open_interest",
        "futures_premium",
        "retail_mania"
    ]

    for name in sections:
        item = payload.get(name, {})

        print(
            name,
            "=>",
            item.get("status", "UNKNOWN"),
            "|",
            item.get("value", "N/A")
        )

    print(
        "mvrv_z_score =>",
        payload["on_chain"]["mvrv_z_score"]["status"]
    )

    print(
        "nupl =>",
        payload["on_chain"]["nupl"]["status"]
    )

    print("Engine completed.")


if __name__ == "__main__":
    main()
