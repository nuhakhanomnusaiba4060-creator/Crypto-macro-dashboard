
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FREE ADVANCED CRYPTO INTELLIGENCE ENGINE
Version: 2.2.0

Free public data sources:
- Binance Spot API
- Binance USD-M Futures Public API
- Mempool.space
- Coin Metrics Community API

No API key required.
No synthetic data.
Unavailable data remains explicitly unavailable.
"""

import json
import math
import time

from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_FILE = DATA_DIR / "advanced_data.json"

TIMEOUT = 20
RETRIES = 3

BINANCE = "https://data-api.binance.vision"
FUTURES_API = "https://fapi.binance.com"
MEMPOOL = "https://mempool.space/api"
COINMETRICS = "https://community-api.coinmetrics.io/v4"

USER_AGENT = "CryptoMacroDashboard-FreeEngine/2.2.0"
HALVING_INTERVAL = 210000


def utc_now():
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def fetch_url(url):
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json"
        }
    )

    last_error = None

    for attempt in range(RETRIES):
        try:
            with urlopen(request, timeout=TIMEOUT) as response:
                return response.read().decode("utf-8")

        except (
            HTTPError,
            URLError,
            TimeoutError,
            OSError
        ) as error:
            last_error = str(error)

            if attempt < RETRIES - 1:
                time.sleep(attempt + 1)

    raise RuntimeError(last_error or "Request failed")


def fetch_json(url):
    raw = fetch_url(url)

    try:
        return json.loads(raw)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"Invalid JSON response: {error}"
        )


def fetch_text(url):
    return fetch_url(url).strip()


def finite(value):
    try:
        number = float(value)

        if math.isfinite(number):
            return number

    except (TypeError, ValueError, OverflowError):
        pass

    return None


def metric(value, unit, source):
    number = finite(value)

    if number is None:
        return unavailable("Valid data unavailable")

    return {
        "value": number,
        "unit": unit,
        "status": "OK",
        "source": source,
        "fetched_at": utc_now()
    }


def unavailable(reason):
    return {
        "value": None,
        "status": "UNAVAILABLE",
        "reason": str(reason or "Data unavailable")[:250],
        "fetched_at": utc_now()
    }


def safe_fetch(url):
    try:
        return fetch_json(url), None
    except Exception as error:
        return None, str(error)[:250]


# ============================================================
# BINANCE SPOT ORDER BOOK
# ============================================================

def get_order_book(symbol):
    url = (
        f"{BINANCE}/api/v3/depth"
        f"?symbol={symbol}&limit=100"
    )

    data, error = safe_fetch(url)

    if not isinstance(data, dict):
        return {
            "symbol": symbol,
            "imbalance_percent": unavailable(error),
            "bid_value_usdt": unavailable(error),
            "ask_value_usdt": unavailable(error)
        }

    try:
        bids = data.get("bids", [])
        asks = data.get("asks", [])

        bid_value = 0.0
        ask_value = 0.0

        for price, quantity in bids:
            p = finite(price)
            q = finite(quantity)

            if p is None or q is None or p < 0 or q < 0:
                raise ValueError("Invalid bid order book data")

            bid_value += p * q

        for price, quantity in asks:
            p = finite(price)
            q = finite(quantity)

            if p is None or q is None or p < 0 or q < 0:
                raise ValueError("Invalid ask order book data")

            ask_value += p * q

        total = bid_value + ask_value

        if total <= 0:
            raise ValueError("Empty order book")

        imbalance = (
            (bid_value - ask_value) / total
        ) * 100

        return {
            "symbol": symbol,
            "imbalance_percent": metric(
                imbalance,
                "%",
                "Binance Spot Order Book"
            ),
            "bid_value_usdt": metric(
                bid_value,
                "USDT",
                "Binance Spot Order Book"
            ),
            "ask_value_usdt": metric(
                ask_value,
                "USDT",
                "Binance Spot Order Book"
            ),
            "last_update_id": data.get("lastUpdateId")
        }

    except Exception as error:
        reason = str(error)

        return {
            "symbol": symbol,
            "imbalance_percent": unavailable(reason),
            "bid_value_usdt": unavailable(reason),
            "ask_value_usdt": unavailable(reason)
        }


# ============================================================
# BINANCE SPOT TAKER BUY / SELL
# ============================================================

def get_taker_ratio(symbol):
    url = (
        f"{BINANCE}/api/v3/klines"
        f"?symbol={symbol}&interval=15m&limit=3"
    )

    data, error = safe_fetch(url)

    if not isinstance(data, list) or len(data) < 2:
        return {
            "symbol": symbol,
            "interval": "15m",
            "taker_buy_sell_ratio": unavailable(error),
            "taker_buy_quote_volume": unavailable(error),
            "taker_sell_quote_volume": unavailable(error)
        }

    try:
        # সর্বশেষ সম্পূর্ণ বন্ধ হওয়া Candle
        candle = data[-2]

        total_quote = finite(candle[7])
        taker_buy_quote = finite(candle[10])

        if total_quote is None or taker_buy_quote is None:
            raise ValueError("Invalid candle volume")

        taker_sell_quote = total_quote - taker_buy_quote

        if (
            total_quote <= 0
            or taker_buy_quote < 0
            or taker_sell_quote < 0
        ):
            raise ValueError("Invalid taker volume")

        if taker_sell_quote == 0:
            ratio_metric = unavailable(
                "Sell volume is zero; ratio cannot be calculated"
            )
        else:
            ratio_metric = metric(
                taker_buy_quote / taker_sell_quote,
                "ratio",
                "Binance Spot 15m Kline"
            )

        return {
            "symbol": symbol,
            "interval": "15m",
            "candle_close_time": candle[6],
            "taker_buy_sell_ratio": ratio_metric,
            "taker_buy_quote_volume": metric(
                taker_buy_quote,
                "USDT",
                "Binance Spot 15m Kline"
            ),
            "taker_sell_quote_volume": metric(
                taker_sell_quote,
                "USDT",
                "Binance Spot 15m Kline"
            )
        }

    except Exception as error:
        reason = str(error)

        return {
            "symbol": symbol,
            "interval": "15m",
            "taker_buy_sell_ratio": unavailable(reason),
            "taker_buy_quote_volume": unavailable(reason),
            "taker_sell_quote_volume": unavailable(reason)
        }


# ============================================================
# BINANCE USD-M FUTURES SENTIMENT
# ============================================================

def get_derivatives(symbol):
    base = f"{FUTURES_API}/fapi/v1"

    result = {
        "symbol": symbol,
        "data_type": "Futures sentiment only; not Spot market data",
        "mark_price": unavailable("Not fetched"),
        "index_price": unavailable("Not fetched"),
        "last_funding_rate": unavailable("Not fetched"),
        "open_interest_contracts": unavailable("Not fetched"),
        "global_long_short_ratio": unavailable("Not fetched"),
        "liquidation_clusters": unavailable(
            "No verified free liquidation heatmap source"
        )
    }

    # Funding Rate
    data, error = safe_fetch(
        f"{base}/fundingRate?symbol={symbol}&limit=1"
    )

    if isinstance(data, list) and data:
        latest = data[-1]

        result["last_funding_rate"] = metric(
            latest.get("fundingRate"),
            "rate",
            "Binance USD-M Futures"
        )

        result["last_funding_rate"]["funding_time"] = (
            latest.get("fundingTime")
        )
    else:
        result["last_funding_rate"] = unavailable(error)

    # Open Interest
    data, error = safe_fetch(
        f"{base}/openInterest?symbol={symbol}"
    )

    if isinstance(data, dict):
        result["open_interest_contracts"] = metric(
            data.get("openInterest"),
            "contracts",
            "Binance USD-M Futures"
        )

        result["open_interest_contracts"]["time"] = data.get("time")
    else:
        result["open_interest_contracts"] = unavailable(error)

    # Global Long / Short Account Ratio
    data, error = safe_fetch(
        f"{base}/globalLongShortAccountRatio"
        f"?symbol={symbol}&period=15m&limit=1"
    )

    if isinstance(data, list) and data:
        latest = data[-1]

        ratio = metric(
            latest.get("longShortRatio"),
            "ratio",
            "Binance USD-M Futures"
        )

        long_fraction = finite(latest.get("longAccount"))
        short_fraction = finite(latest.get("shortAccount"))

        # Binance returns fractions, not percentage values.
        long_percent = (
            long_fraction * 100
            if long_fraction is not None
            and 0 <= long_fraction <= 1
            else None
        )

        short_percent = (
            short_fraction * 100
            if short_fraction is not None
            and 0 <= short_fraction <= 1
            else None
        )

        ratio["long_account_percent"] = long_percent
        ratio["short_account_percent"] = short_percent
        ratio["period"] = "15m"
        ratio["observation_time"] = latest.get("timestamp")

        result["global_long_short_ratio"] = ratio

    else:
        result["global_long_short_ratio"] = unavailable(error)

    # Mark Price and Index Price
    data, error = safe_fetch(
        f"{base}/premiumIndex?symbol={symbol}"
    )

    if isinstance(data, dict):
        result["mark_price"] = metric(
            data.get("markPrice"),
            "USDT",
            "Binance USD-M Futures"
        )

        result["index_price"] = metric(
            data.get("indexPrice"),
            "USDT",
            "Binance USD-M Futures"
        )

        result["mark_price"]["time"] = data.get("time")
        result["index_price"]["time"] = data.get("time")

        result["last_funding_rate"]["next_funding_time"] = (
            data.get("nextFundingTime")
        )

    else:
        result["mark_price"] = unavailable(error)
        result["index_price"] = unavailable(error)

    return result


# ============================================================
# MEMPOOL BITCOIN MINING DATA
# ============================================================

def get_mining_data():
    url = f"{MEMPOOL}/v1/mining/hashrate/3d"
    data, error = safe_fetch(url)

    if not isinstance(data, dict):
        return {
            "hashrate": unavailable(error),
            "difficulty": unavailable(error),
            "estimated_hashrate": unavailable(error)
        }

    return {
        "hashrate": metric(
            data.get("currentHashrate"),
            "H/s",
            "Mempool.space"
        ),
        "difficulty": metric(
            data.get("currentDifficulty"),
            "difficulty",
            "Mempool.space"
        ),
        "estimated_hashrate": metric(
            data.get("estimatedHashrate"),
            "H/s",
            "Mempool.space"
        )
    }


# ============================================================
# BITCOIN HALVING COUNTDOWN
# ============================================================

def get_halving():
    try:
        height = int(
            fetch_text(f"{MEMPOOL}/blocks/tip/height")
        )

        if height < 0:
            raise ValueError("Invalid Bitcoin block height")

        next_halving = (
            (height // HALVING_INTERVAL) + 1
        ) * HALVING_INTERVAL

        remaining = max(0, next_halving - height)
        estimated_days = remaining * 10 / 1440

        return {
            "current_block_height": height,
            "next_halving_block": next_halving,
            "blocks_remaining": remaining,
            "estimated_days_remaining": round(
                estimated_days, 2
            ),
            "estimated_years_remaining": round(
                estimated_days / 365.25, 2
            ),
            "status": "OK",
            "source": "Mempool.space",
            "note": (
                "আনুমানিক সময়; প্রকৃত Halving নির্ধারিত "
                "হবে Block Height অনুযায়ী।"
            ),
            "fetched_at": utc_now()
        }

    except Exception as error:
        return {
            "current_block_height": None,
            "next_halving_block": None,
            "blocks_remaining": None,
            "estimated_days_remaining": None,
            "estimated_years_remaining": None,
            "status": "UNAVAILABLE",
            "reason": str(error)[:250],
            "fetched_at": utc_now()
        }


# ============================================================
# COIN METRICS COMMUNITY API - MVRV
# ============================================================

def get_mvrv():
    url = (
        f"{COINMETRICS}/timeseries/asset-metrics"
        "?assets=btc"
        "&metrics=CapMVRVCur"
        "&frequency=1d"
        "&page_size=2"
    )

    data, error = safe_fetch(url)

    if not isinstance(data, dict):
        return {
            "mvrv_ratio": unavailable(error),
            "mvrv_z_score": unavailable(
                "Community endpoint unavailable"
            )
        }

    rows = data.get("data", [])

    if not rows:
        return {
            "mvrv_ratio": unavailable(
                "No MVRV observation returned"
            ),
            "mvrv_z_score": unavailable(
                "MVRV Z-Score is not supplied by this metric"
            )
        }

    latest = rows[-1]

    ratio = metric(
        latest.get("CapMVRVCur"),
        "ratio",
        "Coin Metrics Community API"
    )

    ratio["observation_date"] = latest.get("time")

    return {
        "mvrv_ratio": ratio,
        "mvrv_z_score": unavailable(
            "CapMVRVCur is MVRV Ratio, not MVRV Z-Score"
        )
    }


# ============================================================
# BINANCE SPOT MARKET BREADTH
# ============================================================

def get_spot_activity():
    rows, error = safe_fetch(
        f"{BINANCE}/api/v3/ticker/24hr"
    )

    if not isinstance(rows, list):
        return {
            "status": "UNAVAILABLE",
            "reason": str(error),
            "volume_leaders_24h": [],
            "breadth": unavailable(error)
        }

    valid = []
    advancing = 0
    declining = 0
    unchanged = 0

    excluded = (
        "UPUSDT",
        "DOWNUSDT",
        "BULLUSDT",
        "BEARUSDT"
    )

    for item in rows:
        symbol = item.get("symbol", "")

        if not symbol.endswith("USDT"):
            continue

        if any(tag in symbol for tag in excluded):
            continue

        quote_volume = finite(item.get("quoteVolume"))
        change = finite(item.get("priceChangePercent"))
        trades = finite(item.get("count"))

        if (
            quote_volume is None
            or change is None
            or trades is None
            or quote_volume <= 0
        ):
            continue

        valid.append({
            "symbol": symbol,
            "quote_volume_24h": quote_volume,
            "change_24h_pct": change,
            "trades": int(trades)
        })

        if change > 0:
            advancing += 1
        elif change < 0:
            declining += 1
        else:
            unchanged += 1

    valid.sort(
        key=lambda item: item["quote_volume_24h"],
        reverse=True
    )

    measured = advancing + declining + unchanged

    if measured == 0:
        return {
            "status": "UNAVAILABLE",
            "reason": "No valid USDT Spot pairs returned",
            "volume_leaders_24h": [],
            "breadth": unavailable(
                "No valid Spot breadth observations"
            )
        }

    breadth = {
        "advancing_pairs": advancing,
        "declining_pairs": declining,
        "unchanged_pairs": unchanged,
        "measured_pairs": measured,
        "advance_decline_ratio": (
            round(advancing / declining, 3)
            if declining > 0
            else None
        ),
        "status": "OK",
        "source": "Binance Spot 24h ticker",
        "fetched_at": utc_now()
    }

    return {
        "status": "OK",
        "volume_leaders_24h": valid[:12],
        "breadth": breadth,
        "note": (
            "২৪ ঘণ্টার Spot Market Breadth; "
            "এটি স্বল্পমেয়াদি volume spike নয়। "
            "USDT trading pairs-এর উপর ভিত্তি করে গণনা করা।"
        )
    }


# ============================================================
# MAIN ENGINE
# ============================================================

def main():
    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    print("Starting Free Advanced Crypto Engine v2.2.0")

    print("Fetching Spot Order Books...")
    order_books = {
        "BTCUSDT": get_order_book("BTCUSDT"),
        "ETHUSDT": get_order_book("ETHUSDT")
    }

    print("Fetching Spot Taker Ratios...")
    taker_ratios = {
        "BTCUSDT": get_taker_ratio("BTCUSDT"),
        "ETHUSDT": get_taker_ratio("ETHUSDT")
    }

    print("Fetching Bitcoin Mining Data...")
    mining = get_mining_data()

    print("Fetching Bitcoin Halving...")
    halving = get_halving()

    print("Fetching MVRV...")
    mvrv = get_mvrv()

    print("Fetching Spot Market Breadth...")
    spot_activity = get_spot_activity()

    print("Fetching Futures Sentiment...")
    derivatives = {
        "BTCUSDT": get_derivatives("BTCUSDT"),
        "ETHUSDT": get_derivatives("ETHUSDT")
    }

    result = {
        "schema_version": 2,
        "engine": "Free Advanced Crypto Intelligence",
        "engine_version": "2.2.0",
        "generated_at": utc_now(),

        "data_policy": (
            "Free public APIs only. "
            "Unavailable data remains null. "
            "No synthetic values."
        ),

        "data_sources": [
            "Binance Spot Public API",
            "Binance USD-M Futures Public API",
            "Mempool.space",
            "Coin Metrics Community API"
        ],

        "etf_flows": unavailable(
            "No reliable free ETF flow API configured"
        ),

        "on_chain": {
            "mvrv_ratio": mvrv["mvrv_ratio"],
            "mvrv_z_score": mvrv["mvrv_z_score"],

            "sth_sopr": unavailable(
                "No verified free STH SOPR source configured"
            ),

            "nupl": unavailable(
                "No verified free NUPL source configured"
            ),

            "exchange_netflow": unavailable(
                "No verified free exchange flow source configured"
            ),

            "stablecoin_supply": unavailable(
                "No verified free stablecoin supply source configured"
            ),

            "whale_activity": unavailable(
                "Entity-labelled whale data unavailable"
            ),

            "hashrate": mining["hashrate"],
            "mining_difficulty": mining["difficulty"],
            "estimated_hashrate": mining["estimated_hashrate"]
        },

        "halving": halving,
        "spot_market_activity": spot_activity,
        "spot_order_book": order_books,
        "spot_taker_activity": taker_ratios,
        "derivatives": derivatives,

        "liquidation_heatmap": unavailable(
            "No free verified liquidation heatmap source configured"
        ),

        "portfolio": {
            "status": "LOCAL_ONLY",
            "note": (
                "Portfolio data is not uploaded to external providers."
            )
        }
    }

    temporary_file = OUTPUT_FILE.with_suffix(".tmp")

    temporary_file.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
            allow_nan=False
        ) + "\n",
        encoding="utf-8"
    )

    temporary_file.replace(OUTPUT_FILE)

    print("----------------------------------")
    print("FREE ADVANCED ENGINE SUCCESS")
    print("Output:", OUTPUT_FILE)
    print("Version: 2.2.0")
    print("----------------------------------")


if __name__ == "__main__":
    main()
