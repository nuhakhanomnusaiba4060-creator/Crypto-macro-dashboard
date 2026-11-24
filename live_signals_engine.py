
#!/usr/bin/env python3
"""
Crypto Dada Style Live Signals Engine
Version: 1.1.0

Output:
data/live_signals.json

Public data sources:
- Binance Spot API
- Binance Futures API
- Alternative.me Fear & Greed API

ETF, MVRV Z-Score and NUPL remain UNAVAILABLE
until a verified provider is configured.
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


VERSION = "1.1.0"
OUTPUT_FILE = Path("data/live_signals.json")

SPOT_BASE = "https://api.binance.com"
SPOT_BACKUP = "https://data-api.binance.vision"
FUTURES_BASE = "https://fapi.binance.com"

REQUEST_TIMEOUT = 15


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


def safe_float(value):
    try:
        number = float(value)
        if math.isfinite(number):
            return number
    except (TypeError, ValueError, OverflowError):
        pass
    return None


def http_get(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "CryptoDada-LiveSignals/1.1",
            "Accept": "application/json"
        }
    )

    with urllib.request.urlopen(
        request,
        timeout=REQUEST_TIMEOUT
    ) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw)


def get_json(path, params=None, base=SPOT_BASE):
    query = urllib.parse.urlencode(params or {})
    url = base + path

    if query:
        url += "?" + query

    return http_get(url)


def get_spot_json(path, params=None):
    errors = []

    for base in (SPOT_BASE, SPOT_BACKUP):
        try:
            return get_json(path, params, base)
        except Exception as exc:
            errors.append(str(exc))

    raise RuntimeError(
        "Binance Spot API unavailable: " + " | ".join(errors)
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
        result["error"] = str(error)[:300]

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


def calculate_sma(values, period):
    if len(values) < period:
        return None

    recent = values[-period:]

    if not recent:
        return None

    return sum(recent) / period


def calculate_rsi(values, period=14):
    if len(values) < period + 1:
        return None

    changes = [
        values[i] - values[i - 1]
        for i in range(len(values) - period, len(values))
    ]

    gains = [max(change, 0) for change in changes]
    losses = [abs(min(change, 0)) for change in changes]

    average_gain = sum(gains) / period
    average_loss = sum(losses) / period

    if average_loss == 0:
        return 100.0 if average_gain > 0 else 50.0

    relative_strength = average_gain / average_loss

    return 100 - (100 / (1 + relative_strength))


def fetch_btc_price():
    data = get_spot_json(
        "/api/v3/ticker/price",
        {"symbol": "BTCUSDT"}
    )

    price = safe_float(data.get("price"))

    if price is None:
        raise RuntimeError("Invalid BTC ticker price")

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

    if not isinstance(data, list) or len(data) < 30:
        raise RuntimeError("Insufficient BTC daily candle data")

    now_ms = int(time.time() * 1000)

    # Binance Kline fields:
    # 0 = open time
    # 4 = close price
    # 6 = close time

    closed = [
        candle for candle in data
        if len(candle) > 6 and int(candle[6]) < now_ms
    ]

    if len(closed) < 30:
        raise RuntimeError("Insufficient closed daily candles")

    closes = [
        safe_float(candle[4])
        for candle in closed
    ]

    closes = [value for value in closes if value is not None]

    if len(closes) < 30:
        raise RuntimeError("Invalid daily close prices")

    latest_closed_time = timestamp_from_ms(closed[-1][6])

    return closes, latest_closed_time


def build_price_structure():
    current_price = fetch_btc_price()
    closes, candle_updated = fetch_btc_daily_candles()

    ma20 = calculate_sma(closes, 20)
    ma50 = calculate_sma(closes, 50)
    ma200 = calculate_sma(closes, 200)
    rsi14 = calculate_rsi(closes, 14)

    previous_candles = closes[-21:-1]

    support = min(previous_candles) if previous_candles else None
    resistance = max(previous_candles) if previous_candles else None

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


def build_funding_rate():
    data = get_json(
        "/fapi/v1/fundingRate",
        {
            "symbol": "BTCUSDT",
            "limit": 1
        },
        FUTURES_BASE
    )

    if not isinstance(data, list) or not data:
        raise RuntimeError("Funding Rate data unavailable")

    item = data[-1]

    rate = safe_float(item.get("fundingRate"))

    if rate is None:
        raise RuntimeError("Invalid Funding Rate")

    return make_metric(
        rate * 100,
        "%",
        "Binance USD-M Futures Funding Rate",
        timestamp_from_ms(item.get("fundingTime"))
    )


def build_open_interest():
    data = get_json(
        "/fapi/v1/openInterest",
        {"symbol": "BTCUSDT"},
        FUTURES_BASE
    )

    value = safe_float(data.get("openInterest"))

    if value is None:
        raise RuntimeError("Invalid Open Interest")

    return make_metric(
        value,
        "BTC",
        "Binance USD-M Futures Open Interest",
        utc_now()
    )


def build_futures_premium():
    data = get_json(
        "/fapi/v1/premiumIndex",
        {"symbol": "BTCUSDT"},
        FUTURES_BASE
    )

    mark_price = safe_float(data.get("markPrice"))
    index_price = safe_float(data.get("indexPrice"))

    if (
        mark_price is None
        or index_price is None
        or index_price == 0
    ):
        raise RuntimeError("Invalid Futures Premium data")

    premium = ((mark_price - index_price) / index_price) * 100

    return make_metric(
        premium,
        "%",
        "Binance USD-M Futures Mark Price vs Index Price",
        timestamp_from_ms(data.get("time"))
    )


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

    return {
        "value": value,
        "unit": "index / 100",
        "status": "PROXY_ONLY",
        "classification": item.get("value_classification", "Unknown"),
        "source": "Alternative.me Fear & Greed Index",
        "source_updated_at": timestamp_from_ms(
            safe_float(item.get("timestamp")) * 1000
        ) if safe_float(item.get("timestamp")) is not None else None,
        "fetched_at": utc_now(),
        "note": (
            "Sentiment proxy only. This is not direct retail trading "
            "activity or verified retail buying/selling data."
        )
    }


def build_etf_flows():
    return unavailable(
        source="ETF Flow Provider not configured",
        error=(
            "No verified ETF Flow provider connected. "
            "Accumulation/Distribution cannot be determined."
        )
    )


def build_mvrv():
    return unavailable(
        source="On-chain Provider not configured",
        error="Verified MVRV Z-Score data source is not connected."
    )


def build_nupl():
    return unavailable(
        source="On-chain Provider not configured",
        error="Verified NUPL data source is not connected."
    )


def safe_build(function, source_name):
    try:
        return function()
    except Exception as exc:
        return unavailable(
            source=source_name,
            error=exc
        )


def build_price_safely():
    try:
        return build_price_structure()
    except Exception as exc:
        return {
            "price": unavailable("Binance Spot API", exc),
            "support": unavailable("Binance Spot Daily Candles", exc),
            "resistance": unavailable("Binance Spot Daily Candles", exc),
            "ma20": unavailable("Binance Spot Daily Candles", exc),
            "ma50": unavailable("Binance Spot Daily Candles", exc),
            "ma200": unavailable("Binance Spot Daily Candles", exc),
            "rsi14": unavailable("Binance Spot Daily Candles", exc),
            "candle_updated_at": None,
            "status": "UNAVAILABLE",
            "error": str(exc)[:300]
        }


def build_payload():
    fetched_at = utc_now()

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
            "ETF Flow Provider"
        ),

        "funding_rate": safe_build(
            build_funding_rate,
            "Binance Futures Funding Rate"
        ),

        "open_interest": safe_build(
            build_open_interest,
            "Binance Futures Open Interest"
        ),

        "futures_premium": safe_build(
            build_futures_premium,
            "Binance Futures Premium"
        ),

        "on_chain": {
            "mvrv_z_score": safe_build(
                build_mvrv,
                "On-chain MVRV Provider"
            ),
            "nupl": safe_build(
                build_nupl,
                "On-chain NUPL Provider"
            )
        },

        "retail_mania": safe_build(
            build_retail_sentiment,
            "Alternative.me Fear & Greed API"
        )
    }

    return payload


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


def main():
    print("Starting Crypto Dada Style Live Signals Engine...")
    print("Version:", VERSION)

    payload = build_payload()
    save_payload(payload)

    print("Output saved:", OUTPUT_FILE)
    print("Fetched at:", payload["fetched_at"])

    for name in (
        "price_structure",
        "etf_flows",
        "funding_rate",
        "open_interest",
        "futures_premium",
        "retail_mania"
    ):
        item = payload.get(name, {})
        print(
            name,
            "=>",
            item.get("status", "UNKNOWN")
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
