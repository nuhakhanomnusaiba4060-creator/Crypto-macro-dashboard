
#!/usr/bin/env python3
"""
Crypto Dada Style Live Signals Engine
Version: 1.3.1

FREE PROVIDERS:
- Binance Spot
- CoinBoss Public API
- Explore21 Public On-chain API
- Alternative.me Fear & Greed

No paid API keys required.

Output:
data/live_signals.json
"""

import json
import math
import time
import urllib.request
import urllib.parse

from datetime import datetime, timezone
from pathlib import Path


VERSION = "1.3.1"

OUTPUT_FILE = Path("data/live_signals.json")

BINANCE_URLS = [
    "https://api.binance.com",
    "https://data-api.binance.vision",
]

# Correct base URL.
# Endpoint paths already contain /api/.
COINBOSS = "https://www.coinboss.com"

EXPLORE21 = "https://data.explore21.com/v1"

TIMEOUT = 20


# ==================================================
# COMMON FUNCTIONS
# ==================================================

def now():
    return datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    )


def timestamp_ms(value):
    try:
        return datetime.fromtimestamp(
            float(value) / 1000,
            timezone.utc
        ).isoformat(timespec="seconds")
    except Exception:
        return None


def timestamp_seconds(value):
    try:
        return datetime.fromtimestamp(
            float(value),
            timezone.utc
        ).isoformat(timespec="seconds")
    except Exception:
        return None


def number(value):
    try:
        result = float(value)

        if math.isfinite(result):
            return result

    except (TypeError, ValueError, OverflowError):
        pass

    return None


def request_json(url):

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "CryptoDadaDashboard/1.3.1",
            "Accept": "application/json",
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=TIMEOUT
    ) as response:

        return json.loads(
            response.read().decode("utf-8")
        )


def make_url(base, path, params=None):

    url = (
        base.rstrip("/")
        + "/"
        + path.lstrip("/")
    )

    if params:
        url += "?" + urllib.parse.urlencode(params)

    return url


def metric(
    value,
    unit,
    source,
    updated=None,
    status="OK"
):

    return {
        "value": value,
        "unit": unit,
        "status": status if value is not None else "UNAVAILABLE",
        "source": source,
        "source_updated_at": updated,
        "fetched_at": now(),
    }


def unavailable(source, error=None):

    result = metric(
        None,
        "",
        source,
        None,
        "UNAVAILABLE",
    )

    if error:
        result["error"] = str(error)[:300]

    return result


def run_safely(function, source):

    try:
        return function()

    except Exception as exc:

        print(
            source,
            "ERROR:",
            str(exc)[:200]
        )

        return unavailable(source, exc)


def extract_timestamp(data):

    if isinstance(data, dict):

        for key in (
            "asof",
            "timestamp",
            "time",
            "ts",
            "updated_at",
            "updatedAt",
            "date",
        ):

            value = data.get(key)

            if value is None:
                continue

            if isinstance(value, (int, float)):

                if value > 100000000000:
                    return timestamp_ms(value)

                if value > 1000000000:
                    return timestamp_seconds(value)

            if isinstance(value, str) and len(value) >= 10:
                return value

        for value in data.values():

            result = extract_timestamp(value)

            if result:
                return result

    elif isinstance(data, list):

        for item in reversed(data):

            result = extract_timestamp(item)

            if result:
                return result

    return None


# ==================================================
# BINANCE SPOT API
# ==================================================

def binance_get(path, params=None):

    errors = []

    for base in BINANCE_URLS:

        try:
            return request_json(
                make_url(base, path, params)
            )

        except Exception as exc:
            errors.append(str(exc))

    raise RuntimeError(
        "Binance API failed: "
        + " | ".join(errors)
    )


def sma(values, period):

    if len(values) < period:
        return None

    return sum(values[-period:]) / period


def rsi(values, period=14):

    if len(values) < period + 1:
        return None

    changes = [
        values[i] - values[i - 1]
        for i in range(
            len(values) - period,
            len(values)
        )
    ]

    gains = [max(x, 0) for x in changes]
    losses = [abs(min(x, 0)) for x in changes]

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    if avg_loss == 0:

        if avg_gain > 0:
            return 100.0

        return 50.0

    rs = avg_gain / avg_loss

    return 100 - (100 / (1 + rs))


def build_price_structure():

    ticker = binance_get(
        "/api/v3/ticker/price",
        {"symbol": "BTCUSDT"},
    )

    price = number(ticker.get("price"))

    if price is None:
        raise RuntimeError("BTC price unavailable")

    candles = binance_get(
        "/api/v3/klines",
        {
            "symbol": "BTCUSDT",
            "interval": "1d",
            "limit": 210,
        },
    )

    current_ms = int(time.time() * 1000)

    closed = [
        candle for candle in candles
        if int(candle[6]) < current_ms
    ]

    closes = [
        number(candle[4])
        for candle in closed
    ]

    closes = [
        value for value in closes
        if value is not None
    ]

    if len(closes) < 200:
        raise RuntimeError("MA200 data unavailable")

    updated = timestamp_ms(closed[-1][6])

    previous = closes[-21:-1]

    return {

        "price": metric(
            price,
            "USDT",
            "Binance Spot BTCUSDT Ticker",
            now(),
        ),

        "support": metric(
            min(previous),
            "USDT",
            "Binance Spot Daily Candles",
            updated,
        ),

        "resistance": metric(
            max(previous),
            "USDT",
            "Binance Spot Daily Candles",
            updated,
        ),

        "ma20": metric(
            sma(closes, 20),
            "USDT",
            "Binance Spot Daily Candles",
            updated,
        ),

        "ma50": metric(
            sma(closes, 50),
            "USDT",
            "Binance Spot Daily Candles",
            updated,
        ),

        "ma200": metric(
            sma(closes, 200),
            "USDT",
            "Binance Spot Daily Candles",
            updated,
        ),

        "rsi14": metric(
            rsi(closes, 14),
            "RSI",
            "Binance Spot Daily Candles",
            updated,
        ),

        "candle_updated_at": updated,
        "status": "OK",
    }


def safe_price_structure():

    try:
        return build_price_structure()

    except Exception as exc:

        return {

            "price": unavailable("Binance Spot", exc),

            "support": unavailable("Binance Daily Candles", exc),

            "resistance": unavailable("Binance Daily Candles", exc),

            "ma20": unavailable("Binance Daily Candles", exc),

            "ma50": unavailable("Binance Daily Candles", exc),

            "ma200": unavailable("Binance Daily Candles", exc),

            "rsi14": unavailable("Binance Daily Candles", exc),

            "candle_updated_at": None,

            "status": "UNAVAILABLE",

            "error": str(exc)[:300],
        }


# ==================================================
# COINBOSS PUBLIC API
# ==================================================

def coinboss(path, params=None):

    data = request_json(
        make_url(
            COINBOSS,
            path,
            params
        )
    )

    if not isinstance(data, dict):
        raise RuntimeError("Invalid CoinBoss response")

    if data.get("success") is False:

        raise RuntimeError(
            data.get("error", "CoinBoss request failed")
        )

    if data.get("ok") is False:

        raise RuntimeError(
            data.get("error", "CoinBoss request failed")
        )

    return data


# ==================================================
# BITCOIN ETF FLOWS
# ==================================================

def build_etf():

    data = coinboss(
        "/api/etf/flows",
        {
            "asset": "BTC",
            "days": 30,
        },
    )

    latest = data.get("latest")

    if not isinstance(latest, dict):
        raise RuntimeError("ETF latest data unavailable")

    value = number(latest.get("flow"))

    if value is None:
        raise RuntimeError("ETF flow value missing")

    updated = latest.get("date")

    result = metric(
        value,
        "million USD",
        "CoinBoss Bitcoin Spot ETF Flow",
        updated,
    )

    result["classification"] = (
        "Net Inflow" if value > 0
        else "Net Outflow" if value < 0
        else "Neutral"
    )

    result["sum_7d"] = number(
        latest.get("sum_7d")
    )

    result["aum"] = number(
        latest.get("aum")
    )

    result["update_frequency"] = "Daily"

    result["note"] = (
        "Daily net ETF flow. Positive means inflow; "
        "negative means outflow. Unit: million USD."
    )

    result["provider_response_received_at"] = now()

    return result


# ==================================================
# FUNDING RATE
# ==================================================

def build_funding():

    data = coinboss(
        "/api/sd/funding",
        {"coin": "BTC"},
    )

    value = number(
        data.get("oi_weighted_8h")
    )

    aggregation = "OI-weighted 8-hour rate"

    if value is None:

        value = number(
            data.get("avg_8h")
        )

        aggregation = "Average 8-hour rate"

    if value is None:
        raise RuntimeError("Funding rate fields unavailable")

    # API value is fraction.
    # Convert fraction into percentage.
    value_pct = value * 100

    updated = timestamp_ms(
        data.get("now")
    )

    result = metric(
        value_pct,
        "% per 8h",
        "CoinBoss BTC Aggregated Funding Rate",
        updated,
    )

    result["aggregation"] = aggregation

    result["note"] = (
        "Positive funding means longs generally pay shorts. "
        "Negative funding means shorts generally pay longs."
    )

    result["provider_response_received_at"] = now()

    return result


# ==================================================
# OPEN INTEREST
# ==================================================

def build_open_interest():

    data = coinboss(
        "/api/sd/oi",
        {"coin": "BTC"},
    )

    value = number(
        data.get("total_usd_single_adjusted")
    )

    if value is None:

        value = number(
            data.get("total_usd")
        )

    if value is None:
        raise RuntimeError("Open Interest value unavailable")

    updated = timestamp_ms(
        data.get("asof")
    )

    result = metric(
        value,
        "USD",
        "CoinBoss BTC Aggregated Open Interest",
        updated,
    )

    result["note"] = (
        "Aggregated BTC futures open interest in USD. "
        "Single-side adjusted value preferred when available."
    )

    result["provider_response_received_at"] = now()

    return result


# ==================================================
# FUTURES PREMIUM / BASIS
# ==================================================

def build_futures_premium():

    data = coinboss(
        "/api/sd/basis",
        {"coin": "BTC"},
    )

    perp = data.get("perp", {})

    if not isinstance(perp, dict):
        perp = {}

    aggregate = perp.get("aggregate", {})

    if not isinstance(aggregate, dict):
        aggregate = {}

    value = number(
        aggregate.get("oi_weighted_pct")
    )

    if value is None:

        value = number(
            aggregate.get("median_pct")
        )

    if value is None:
        raise RuntimeError("Futures basis value unavailable")

    updated = (
        extract_timestamp(data.get("meta", {}))
        or timestamp_ms(data.get("now"))
    )

    result = metric(
        value,
        "%",
        "CoinBoss BTC Perpetual Futures Basis",
        updated,
    )

    result["note"] = (
        "Open-interest-weighted perpetual mark/index basis. "
        "This is futures market context, not a spot trading signal."
    )

    result["provider_response_received_at"] = now()

    return result


# ==================================================
# EXPLORE21 ON-CHAIN API
# ==================================================

def explore_get(path):

    return request_json(
        make_url(
            EXPLORE21,
            path
        )
    )


def build_mvrv():

    data = explore_get(
        "/metrics/bitcoin-mvrv-z-score/latest"
    )

    rows = data.get("data", [])

    if isinstance(rows, dict):
        rows = [rows]

    if not rows:
        raise RuntimeError("MVRV data unavailable")

    latest = rows[-1]

    value = number(
        latest.get("mvrv_z_score")
    )

    if value is None:
        raise RuntimeError("MVRV value missing")

    result = metric(
        value,
        "",
        "Explore21 Bitcoin MVRV Z-Score",
        latest.get("date"),
    )

    result["update_frequency"] = "Daily"

    result["attribution"] = "Explore21"

    return result


def build_nupl():

    return unavailable(
        "Explore21 NUPL",
        "NUPL is not currently listed in the verified free Explore21 metric catalog."
    )


# ==================================================
# FEAR & GREED
# ==================================================

def build_sentiment():

    data = request_json(
        "https://api.alternative.me/fng/?limit=1&format=json"
    )

    rows = data.get("data", [])

    if not rows:
        raise RuntimeError("Fear & Greed unavailable")

    latest = rows[0]

    value = number(
        latest.get("value")
    )

    if value is None:
        raise RuntimeError("Invalid Fear & Greed value")

    updated = timestamp_seconds(
        latest.get("timestamp")
    )

    result = metric(
        value,
        "index / 100",
        "Alternative.me Fear & Greed Index",
        updated,
        "PROXY_ONLY",
    )

    result["classification"] = latest.get(
        "value_classification",
        "Unknown",
    )

    result["note"] = (
        "Sentiment proxy only. Not direct retail trading activity."
    )

    return result


# ==================================================
# BUILD FINAL JSON
# ==================================================

def build_payload():

    return {

        "schema_version": 1,

        "engine": "Crypto Dada Style Live Signals Engine",

        "engine_version": VERSION,

        "symbol": "BTCUSDT",

        "market": "Binance Spot",

        "fetched_at": now(),

        "price_structure": safe_price_structure(),

        "etf_flows": run_safely(
            build_etf,
            "CoinBoss Bitcoin ETF Flow",
        ),

        "funding_rate": run_safely(
            build_funding,
            "CoinBoss Funding Rate",
        ),

        "open_interest": run_safely(
            build_open_interest,
            "CoinBoss Open Interest",
        ),

        "futures_premium": run_safely(
            build_futures_premium,
            "CoinBoss Futures Basis",
        ),

        "on_chain": {

            "mvrv_z_score": run_safely(
                build_mvrv,
                "Explore21 MVRV Z-Score",
            ),

            "nupl": build_nupl(),
        },

        "retail_mania": run_safely(
            build_sentiment,
            "Alternative.me Fear & Greed",
        ),
    }


# ==================================================
# SAVE JSON SAFELY
# ==================================================

def save_json(data):

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp = OUTPUT_FILE.with_suffix(".tmp")

    temp.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        ),
        encoding="utf-8",
    )

    temp.replace(OUTPUT_FILE)


# ==================================================
# MAIN
# ==================================================

def main():

    print("=" * 55)

    print("CRYPTO DADA LIVE SIGNALS ENGINE")

    print("Version:", VERSION)

    print("Free Providers - No Paid API Keys")

    print("=" * 55)

    data = build_payload()

    save_json(data)

    print("\nJSON saved:", OUTPUT_FILE)

    print("Fetched:", data["fetched_at"])

    checks = [

        ("BTC Price", data["price_structure"]["price"]),

        ("ETF Flows", data["etf_flows"]),

        ("Funding Rate", data["funding_rate"]),

        ("Open Interest", data["open_interest"]),

        ("Futures Premium", data["futures_premium"]),

        ("MVRV Z-Score", data["on_chain"]["mvrv_z_score"]),

        ("NUPL", data["on_chain"]["nupl"]),

        ("Fear & Greed", data["retail_mania"]),
    ]

    print("\nDATA STATUS")

    for name, item in checks:

        print(
            name,
            "=>",
            item.get("status"),
            "|",
            item.get("value"),
        )

        if item.get("error"):

            print(
                "   ERROR:",
                item["error"],
            )

    print("\nEngine completed.")


if __name__ == "__main__":
    main()
