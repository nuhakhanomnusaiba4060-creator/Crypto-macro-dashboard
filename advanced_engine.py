
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FREE ADVANCED CRYPTO INTELLIGENCE ENGINE
Version: 3.0.0

Sources:
- Binance Spot Public API
- CoinBoss Public Derivatives API
- Mempool.space
- Coin Metrics Community API

Policy:
- No synthetic data.
- Unavailable data remains explicitly unavailable.
- Stale data is never labelled fresh.
- Futures data is sentiment context only.
- Order book depth represents top 100 levels only.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
import time

from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

OUTPUT_FILE = Path(
    os.getenv(
        "ADVANCED_DATA_FILE",
        str(DATA_DIR / "advanced_data.json")
    )
)

TIMEOUT = 20
RETRIES = 3

BINANCE = "https://data-api.binance.vision"
COINBOSS = "https://www.coinboss.com/api"
MEMPOOL = "https://mempool.space/api"
COINMETRICS = "https://community-api.coinmetrics.io/v4"

USER_AGENT = "CryptoMacroDashboard-FreeEngine/3.0.0"

HALVING_INTERVAL = 210000

ORDER_BOOK_LIMIT = 100

# Maximum permitted source age.
ORDERBOOK_MAX_AGE_SECONDS = 120
TAKER_MAX_AGE_SECONDS = 30 * 60
DERIVATIVES_MAX_AGE_SECONDS = 2 * 60 * 60
MVRV_MAX_AGE_SECONDS = 72 * 60 * 60
BREADTH_MAX_AGE_SECONDS = 30 * 60


# ============================================================
# TIME HELPERS
# ============================================================

def utc_now():

    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def parse_timestamp(value):

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


def unix_ms_to_iso(value):

    try:

        number = finite(value)

        if number is None or number <= 0:
            return None

        return (
            datetime.fromtimestamp(
                number / 1000,
                tz=timezone.utc
            )
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

    except (ValueError, OverflowError, OSError):

        return None


def age_seconds(timestamp):

    parsed = parse_timestamp(timestamp)

    if parsed is None:
        return None

    age = (
        datetime.now(timezone.utc) - parsed
    ).total_seconds()

    # Future timestamps are invalid.
    if age < -300:
        return None

    return max(0.0, age)


def freshness_status(timestamp, max_age_seconds):

    age = age_seconds(timestamp)

    if age is None:
        return "TIMESTAMP_UNKNOWN"

    if age > max_age_seconds:
        return "STALE"

    return "OK"


# ============================================================
# COMMON HELPERS
# ============================================================

def finite(value):

    try:

        number = float(value)

        if math.isfinite(number):
            return number

    except (TypeError, ValueError, OverflowError):

        pass

    return None


def unavailable(reason):

    return {
        "value": None,
        "status": "UNAVAILABLE",
        "reason": str(reason or "Data unavailable")[:250],
        "source_updated_at": None,
        "fetched_at": utc_now()
    }


def metric(
    value,
    unit,
    source,
    observed_at=None,
    max_age_seconds=None,
    fetched_at=None
):

    number = finite(value)

    fetched_at = fetched_at or utc_now()

    if number is None:

        return {
            "value": None,
            "unit": unit,
            "status": "UNAVAILABLE",
            "source": source,
            "source_updated_at": observed_at,
            "fetched_at": fetched_at,
            "reason": "Valid numeric observation unavailable"
        }

    status = "OK"

    if max_age_seconds is not None:

        status = freshness_status(
            observed_at,
            max_age_seconds
        )

    return {
        "value": number,
        "unit": unit,
        "status": status,
        "source": source,
        "source_updated_at": observed_at,
        "observed_at": observed_at,
        "fetched_at": fetched_at,
        "error": (
            "Source timestamp missing, invalid, future-dated, or stale"
            if status != "OK"
            else None
        )
    }


def safe_list(value):

    return value if isinstance(value, list) else []


def safe_dict(value):

    return value if isinstance(value, dict) else {}


# ============================================================
# HTTP REQUEST
# ============================================================

def fetch_url(url):

    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json"
        }
    )

    last_error = "Unknown network error"

    for attempt in range(RETRIES):

        try:

            with urlopen(
                request,
                timeout=TIMEOUT
            ) as response:

                return (
                    response.read().decode("utf-8"),
                    utc_now()
                )

        except HTTPError as error:

            last_error = f"HTTP_{error.code}"

            if error.code not in (
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
            OSError
        ) as error:

            last_error = str(error)

        if attempt < RETRIES - 1:
            time.sleep(attempt + 1)

    raise RuntimeError(last_error)


def fetch_json(url):

    raw, fetched_at = fetch_url(url)

    try:

        data = json.loads(raw)

    except json.JSONDecodeError as error:

        raise RuntimeError(
            f"Invalid JSON response: {error}"
        )

    return data, fetched_at


def fetch_text(url):

    raw, fetched_at = fetch_url(url)

    return raw.strip(), fetched_at


def safe_fetch(url):

    try:

        data, fetched_at = fetch_json(url)

        if (
            isinstance(data, dict)
            and data.get("success") is False
        ):

            return (
                None,
                fetched_at,
                data.get("error")
                or data.get("code")
                or "API returned success=false"
            )

        return data, fetched_at, None

    except Exception as error:

        return None, utc_now(), str(error)[:250]


# ============================================================
# BINANCE SPOT ORDER BOOK
# ============================================================

def get_order_book(symbol):

    url = (
        f"{BINANCE}/api/v3/depth"
        f"?symbol={symbol}&limit={ORDER_BOOK_LIMIT}"
    )

    data, fetched_at, error = safe_fetch(url)

    if not isinstance(data, dict):

        reason = error or "Invalid order book response"

        return {
            "symbol": symbol,
            "depth_scope": "TOP_100_LEVELS_ONLY",
            "imbalance_percent": unavailable(reason),
            "bid_value_usdt": unavailable(reason),
            "ask_value_usdt": unavailable(reason),
            "last_update_id": None,
            "snapshot_retrieved_at": fetched_at,
            "status": "UNAVAILABLE"
        }

    try:

        bids = safe_list(data.get("bids"))
        asks = safe_list(data.get("asks"))

        if not bids or not asks:
            raise ValueError("Empty order book side")

        bid_value = 0.0
        ask_value = 0.0

        for row in bids:

            if not isinstance(row, list) or len(row) < 2:
                raise ValueError("Malformed bid level")

            price = finite(row[0])
            quantity = finite(row[1])

            if (
                price is None
                or quantity is None
                or price <= 0
                or quantity <= 0
            ):
                raise ValueError("Invalid bid price or quantity")

            bid_value += price * quantity

        for row in asks:

            if not isinstance(row, list) or len(row) < 2:
                raise ValueError("Malformed ask level")

            price = finite(row[0])
            quantity = finite(row[1])

            if (
                price is None
                or quantity is None
                or price <= 0
                or quantity <= 0
            ):
                raise ValueError("Invalid ask price or quantity")

            ask_value += price * quantity

        total = bid_value + ask_value

        if total <= 0:
            raise ValueError("Order book total depth is zero")

        imbalance = (
            (bid_value - ask_value) / total
        ) * 100

        snapshot_status = freshness_status(
            fetched_at,
            ORDERBOOK_MAX_AGE_SECONDS
        )

        return {

            "symbol": symbol,

            "depth_scope": "TOP_100_LEVELS_ONLY",

            "levels_requested": ORDER_BOOK_LIMIT,

            "bid_levels_received": len(bids),

            "ask_levels_received": len(asks),

            "imbalance_percent": metric(
                imbalance,
                "%",
                "Binance Spot Order Book Top 100 Levels",
                fetched_at,
                ORDERBOOK_MAX_AGE_SECONDS,
                fetched_at
            ),

            "bid_value_usdt": metric(
                bid_value,
                "USDT",
                "Binance Spot Order Book Top 100 Levels",
                fetched_at,
                ORDERBOOK_MAX_AGE_SECONDS,
                fetched_at
            ),

            "ask_value_usdt": metric(
                ask_value,
                "USDT",
                "Binance Spot Order Book Top 100 Levels",
                fetched_at,
                ORDERBOOK_MAX_AGE_SECONDS,
                fetched_at
            ),

            "last_update_id": data.get("lastUpdateId"),

            "snapshot_retrieved_at": fetched_at,

            "status": snapshot_status,

            "limitation": (
                "Top 100 bid/ask levels only. "
                "This is not the full exchange order book."
            )
        }

    except Exception as error:

        reason = str(error)

        return {
            "symbol": symbol,
            "depth_scope": "TOP_100_LEVELS_ONLY",
            "imbalance_percent": unavailable(reason),
            "bid_value_usdt": unavailable(reason),
            "ask_value_usdt": unavailable(reason),
            "last_update_id": data.get("lastUpdateId"),
            "snapshot_retrieved_at": fetched_at,
            "status": "INVALID_DATA"
        }


# ============================================================
# BINANCE SPOT TAKER BUY / SELL
# ============================================================

def get_taker_ratio(symbol):

    url = (
        f"{BINANCE}/api/v3/klines"
        f"?symbol={symbol}&interval=15m&limit=3"
    )

    data, fetched_at, error = safe_fetch(url)

    if not isinstance(data, list) or len(data) < 2:

        reason = error or "Insufficient Binance candle data"

        return {
            "symbol": symbol,
            "interval": "15m",
            "taker_buy_sell_ratio": unavailable(reason),
            "taker_buy_quote_volume": unavailable(reason),
            "taker_sell_quote_volume": unavailable(reason),
            "candle_close_time": None,
            "status": "UNAVAILABLE"
        }

    try:

        # Binance returns the latest candle, which may still be forming.
        # Use the previous, fully closed candle.
        candle = data[-2]

        if not isinstance(candle, list) or len(candle) < 11:
            raise ValueError("Malformed Binance kline")

        close_time_ms = int(candle[6])

        candle_close_at = unix_ms_to_iso(
            close_time_ms
        )

        if candle_close_at is None:
            raise ValueError("Invalid candle close timestamp")

        if age_seconds(candle_close_at) is None:
            raise ValueError("Future or invalid candle timestamp")

        total_quote = finite(candle[7])

        taker_buy_quote = finite(candle[10])

        if (
            total_quote is None
            or taker_buy_quote is None
            or total_quote <= 0
            or taker_buy_quote < 0
            or taker_buy_quote > total_quote
        ):
            raise ValueError("Invalid taker quote volume")

        taker_sell_quote = (
            total_quote - taker_buy_quote
        )

        ratio = (
            taker_buy_quote / taker_sell_quote
            if taker_sell_quote > 0
            else None
        )

        return {

            "symbol": symbol,

            "interval": "15m",

            "candle_policy": "LAST_CLOSED_CANDLE_ONLY",

            "candle_close_time": candle_close_at,

            "taker_buy_sell_ratio": metric(
                ratio,
                "ratio",
                "Binance Spot 15m Closed Kline",
                candle_close_at,
                TAKER_MAX_AGE_SECONDS,
                fetched_at
            ),

            "taker_buy_quote_volume": metric(
                taker_buy_quote,
                "USDT",
                "Binance Spot 15m Closed Kline",
                candle_close_at,
                TAKER_MAX_AGE_SECONDS,
                fetched_at
            ),

            "taker_sell_quote_volume": metric(
                taker_sell_quote,
                "USDT",
                "Binance Spot 15m Closed Kline",
                candle_close_at,
                TAKER_MAX_AGE_SECONDS,
                fetched_at
            ),

            "status": freshness_status(
                candle_close_at,
                TAKER_MAX_AGE_SECONDS
            )
        }

    except Exception as error:

        reason = str(error)

        return {
            "symbol": symbol,
            "interval": "15m",
            "taker_buy_sell_ratio": unavailable(reason),
            "taker_buy_quote_volume": unavailable(reason),
            "taker_sell_quote_volume": unavailable(reason),
            "candle_close_time": None,
            "status": "INVALID_DATA"
        }


# ============================================================
# COINBOSS DERIVATIVES HELPERS
# ============================================================

def coinboss_fetch(path, coin):

    url = f"{COINBOSS}{path}?coin={coin}"

    data, fetched_at, error = safe_fetch(url)

    if not isinstance(data, dict):

        return None, fetched_at, error or "Invalid CoinBoss response"

    if data.get("success") is not True:

        return (
            None,
            fetched_at,
            data.get("error") or "CoinBoss request unsuccessful"
        )

    return data, fetched_at, None


def coinboss_timestamp(data, *keys):

    for key in keys:

        timestamp = unix_ms_to_iso(
            data.get(key)
        )

        if timestamp:
            return timestamp

    return None


# ============================================================
# COINBOSS OPEN INTEREST
# ============================================================

def get_coinboss_open_interest(coin):

    data, fetched_at, error = coinboss_fetch(
        "/sd/oi",
        coin
    )

    if data is None:

        return {

            "total_usd": unavailable(error),

            "total_change_24h_pct": unavailable(error),

            "exchange_count": unavailable(error),

            "instrument_count": unavailable(error),

            "coverage": None,

            "asof": None,

            "status": "UNAVAILABLE"
        }

    observed_at = coinboss_timestamp(
        data,
        "asof",
        "now"
    )

    status = freshness_status(
        observed_at,
        DERIVATIVES_MAX_AGE_SECONDS
    )

    change = safe_dict(data.get("change"))

    return {

        "total_usd": metric(
            data.get("total_usd"),
            "USD",
            "CoinBoss Cross-exchange Open Interest",
            observed_at,
            DERIVATIVES_MAX_AGE_SECONDS,
            fetched_at
        ),

        "total_change_24h_pct": metric(
            change.get("pct_24h"),
            "%",
            "CoinBoss Cross-exchange Open Interest",
            observed_at,
            DERIVATIVES_MAX_AGE_SECONDS,
            fetched_at
        ),

        "exchange_count": metric(
            data.get("n_exchanges"),
            "exchanges",
            "CoinBoss",
            observed_at,
            DERIVATIVES_MAX_AGE_SECONDS,
            fetched_at
        ),

        # This is listed instrument count, not contract quantity.
        "instrument_count": metric(
            data.get("n_contracts"),
            "instruments",
            "CoinBoss",
            observed_at,
            DERIVATIVES_MAX_AGE_SECONDS,
            fetched_at
        ),

        "coverage": data.get("coverage"),

        "method": data.get("method"),

        "asof": observed_at,

        "fetched_at": fetched_at,

        "status": status,

        "provider": "CoinBoss"
    }


# ============================================================
# COINBOSS FUNDING RATE / APR
# ============================================================

def get_coinboss_funding(coin):

    data, fetched_at, error = coinboss_fetch(
        "/sd/funding",
        coin
    )

    if data is None:

        return {

            "avg_8h": unavailable(error),

            "oi_weighted_8h": unavailable(error),

            "apr_pct": unavailable(error),

            "provider_apr_pct": unavailable(error),

            "apr_difference_percentage_points": unavailable(error),

            "apr_consistency": "UNAVAILABLE",

            "exchange_count": unavailable(error),

            "coverage": None,

            "asof": None,

            "status": "UNAVAILABLE"
        }

    observed_at = coinboss_timestamp(
        data,
        "now",
        "asof"
    )

    status = freshness_status(
        observed_at,
        DERIVATIVES_MAX_AGE_SECONDS
    )

    avg_rate = finite(
        data.get("avg_8h")
    )

    provider_apr = finite(
        data.get("apr_pct")
    )

    # Simple annualization:
    # 3 funding periods/day × 365 days × average 8h rate.
    calculated_apr = (
        avg_rate * 3 * 365 * 100
        if avg_rate is not None
        else None
    )

    apr_difference = (
        abs(provider_apr - calculated_apr)
        if (
            provider_apr is not None
            and calculated_apr is not None
        )
        else None
    )

    if apr_difference is None:

        consistency = "NOT_VERIFIABLE"

    elif apr_difference <= 0.5:

        consistency = "CLOSE"

    else:

        consistency = "MISMATCH"

    return {

        "avg_8h": metric(
            avg_rate,
            "fraction per 8h",
            "CoinBoss Cross-exchange Funding",
            observed_at,
            DERIVATIVES_MAX_AGE_SECONDS,
            fetched_at
        ),

        "oi_weighted_8h": metric(
            data.get("oi_weighted_8h"),
            "fraction per 8h",
            "CoinBoss Cross-exchange Funding",
            observed_at,
            DERIVATIVES_MAX_AGE_SECONDS,
            fetched_at
        ),

        "apr_pct": metric(
            calculated_apr,
            "% per year",
            "Calculated from average 8h funding",
            observed_at,
            DERIVATIVES_MAX_AGE_SECONDS,
            fetched_at
        ),

        "provider_apr_pct": metric(
            provider_apr,
            "% per year",
            "CoinBoss provider-reported APR",
            observed_at,
            DERIVATIVES_MAX_AGE_SECONDS,
            fetched_at
        ),

        "apr_difference_percentage_points": metric(
            apr_difference,
            "percentage points",
            "Calculated APR versus provider APR",
            observed_at,
            DERIVATIVES_MAX_AGE_SECONDS,
            fetched_at
        ),

        "apr_consistency": consistency,

        "apr_formula": (
            "average_8h_rate × 3 × 365 × 100"
        ),

        "exchange_count": metric(
            data.get("n_exchanges"),
            "exchanges",
            "CoinBoss",
            observed_at,
            DERIVATIVES_MAX_AGE_SECONDS,
            fetched_at
        ),

        "coverage": data.get("coverage"),

        "method": data.get("method"),

        "asof": observed_at,

        "fetched_at": fetched_at,

        "status": status,

        "provider": "CoinBoss",

        "unit_note": (
            "Funding rate is a fraction. "
            "0.0001 = 0.01%. "
            "APR is simple annualization, not guaranteed return."
        )
    }


# ============================================================
# COINBOSS LONG / SHORT
# ============================================================

def get_coinboss_long_short(coin):

    data, fetched_at, error = coinboss_fetch(
        "/sd/ls",
        coin
    )

    if data is None:

        reason = error or "Long/Short data unavailable"

        return {

            "account": unavailable(reason),

            "top_account": unavailable(reason),

            "position": unavailable(reason),

            "all_position": unavailable(reason),

            "taker": unavailable(reason),

            "coverage": None,

            "provider": "CoinBoss",

            "asof": None,

            "status": "UNAVAILABLE"
        }

    observed_at = coinboss_timestamp(
        data,
        "now",
        "asof"
    )

    overall_status = freshness_status(
        observed_at,
        DERIVATIVES_MAX_AGE_SECONDS
    )

    def parse_flavour(name, label):

        block = data.get(name)

        if not isinstance(block, dict):

            return {

                "ratio": unavailable(
                    f"{label} ratio unavailable"
                ),

                "long_pct": unavailable(
                    f"{label} long percentage unavailable"
                ),

                "short_pct": unavailable(
                    f"{label} short percentage unavailable"
                ),

                "exchange_count": unavailable(
                    f"{label} exchange count unavailable"
                ),

                "by_exchange": []
            }

        long_pct = finite(
            block.get("long_pct")
        )

        short_pct = finite(
            block.get("short_pct")
        )

        ratio = finite(
            block.get("ratio")
        )

        exchange_count = finite(
            block.get("n_exchanges")
        )

        if long_pct is not None and not 0 <= long_pct <= 100:
            long_pct = None

        if short_pct is not None and not 0 <= short_pct <= 100:
            short_pct = None

        if ratio is not None and ratio <= 0:
            ratio = None

        if (
            long_pct is not None
            and short_pct is not None
            and abs((long_pct + short_pct) - 100) > 2
        ):
            long_pct = None
            short_pct = None

        if (
            ratio is None
            and long_pct is not None
            and short_pct is not None
            and short_pct > 0
        ):

            ratio = long_pct / short_pct

        source = f"CoinBoss Cross-exchange {label}"

        exchanges = []

        raw_exchanges = block.get("by_exchange")

        if isinstance(raw_exchanges, list):

            for row in raw_exchanges:

                if not isinstance(row, dict):
                    continue

                row_long = finite(
                    row.get("long_pct")
                )

                row_short = finite(
                    row.get("short_pct")
                )

                row_ratio = finite(
                    row.get("ratio")
                )

                if (
                    row_ratio is None
                    and row_long is not None
                    and row_short is not None
                    and row_short > 0
                ):

                    row_ratio = row_long / row_short

                exchanges.append({

                    "exchange": row.get("exchange"),

                    "long_pct": row_long,

                    "short_pct": row_short,

                    "ratio": row_ratio,

                    "timestamp": unix_ms_to_iso(
                        row.get("timestamp")
                    )
                })

        return {

            "ratio": metric(
                ratio,
                "long/short ratio",
                source,
                observed_at,
                DERIVATIVES_MAX_AGE_SECONDS,
                fetched_at
            ),

            "long_pct": metric(
                long_pct,
                "%",
                source,
                observed_at,
                DERIVATIVES_MAX_AGE_SECONDS,
                fetched_at
            ),

            "short_pct": metric(
                short_pct,
                "%",
                source,
                observed_at,
                DERIVATIVES_MAX_AGE_SECONDS,
                fetched_at
            ),

            "exchange_count": metric(
                exchange_count,
                "exchanges",
                source,
                observed_at,
                DERIVATIVES_MAX_AGE_SECONDS,
                fetched_at
            ),

            "by_exchange": exchanges
        }

    return {

        "account": parse_flavour(
            "account",
            "Account"
        ),

        "top_account": parse_flavour(
            "top_account",
            "Top Trader Account"
        ),

        "position": parse_flavour(
            "top_position",
            "Top Trader Position"
        ),

        "all_position": parse_flavour(
            "position_all",
            "All Trader Position"
        ),

        "taker": parse_flavour(
            "taker",
            "Taker Buy/Sell"
        ),

        "definitions": safe_dict(
            data.get("definitions")
        ),

        "method": safe_dict(
            data.get("method")
        ),

        "coverage": data.get("coverage"),

        "provider": "CoinBoss",

        "asof": observed_at,

        "fetched_at": fetched_at,

        "status": overall_status,

        "schema": data.get("schema")
    }


# ============================================================
# DERIVATIVES OUTPUT
# ============================================================

def get_derivatives(symbol):

    if not isinstance(symbol, str) or not symbol.endswith("USDT"):

        raise ValueError(
            "Only exact USDT quote symbols are accepted"
        )

    coin = symbol[:-4]

    if not coin:
        raise ValueError("Invalid base asset")

    oi = get_coinboss_open_interest(coin)

    funding = get_coinboss_funding(coin)

    long_short = get_coinboss_long_short(coin)

    return {

        "symbol": symbol,

        "provider": "CoinBoss",

        "data_type": (
            "Cross-exchange Futures sentiment only; "
            "not Spot market data"
        ),

        "open_interest_usd": oi["total_usd"],

        "open_interest_change_24h_pct": (
            oi["total_change_24h_pct"]
        ),

        "open_interest_instrument_count": (
            oi["instrument_count"]
        ),

        "open_interest_exchange_count": (
            oi["exchange_count"]
        ),

        "last_funding_rate": funding["oi_weighted_8h"],

        "funding_avg_8h": funding["avg_8h"],

        "funding_apr_pct": funding["apr_pct"],

        "funding_provider_apr_pct": (
            funding["provider_apr_pct"]
        ),

        "funding_apr_consistency": (
            funding["apr_consistency"]
        ),

        "funding_apr_difference_percentage_points": (
            funding["apr_difference_percentage_points"]
        ),

        "funding_exchange_count": funding["exchange_count"],

        "global_long_short_ratio": (
            long_short["account"]["ratio"]
        ),

        "global_long_percent": (
            long_short["account"]["long_pct"]
        ),

        "global_short_percent": (
            long_short["account"]["short_pct"]
        ),

        "top_account_long_short_ratio": (
            long_short["top_account"]["ratio"]
        ),

        "top_position_long_short_ratio": (
            long_short["position"]["ratio"]
        ),

        "position_long_short_ratio": (
            long_short["position"]["ratio"]
        ),

        "all_position_long_short_ratio": (
            long_short["all_position"]["ratio"]
        ),

        "taker_long_short_ratio": (
            long_short["taker"]["ratio"]
        ),

        "long_short_detail": {

            "account": long_short["account"],

            "top_account": long_short["top_account"],

            "top_position": long_short["position"],

            "all_position": long_short["all_position"],

            "taker": long_short["taker"],

            "definitions": long_short.get(
                "definitions",
                {}
            ),

            "method": long_short.get(
                "method",
                {}
            )
        },

        "mark_price": unavailable(
            "Not included in selected CoinBoss aggregate endpoint"
        ),

        "index_price": unavailable(
            "Not included in selected CoinBoss aggregate endpoint"
        ),

        "liquidation_clusters": unavailable(
            "Verified liquidation heatmap integration not configured"
        ),

        "coverage": {

            "open_interest": oi.get("coverage"),

            "funding": funding.get("coverage"),

            "long_short": long_short.get("coverage")
        },

        "asof": {

            "open_interest": oi.get("asof"),

            "funding": funding.get("asof"),

            "long_short": long_short.get("asof")
        },

        "data_status": {

            "open_interest": oi.get("status"),

            "funding": funding.get("status"),

            "long_short": long_short.get("status")
        },

        "provider_note": (
            "CoinBoss aggregates data from multiple derivatives venues. "
            "Long/short populations are kept separate. "
            "Futures metrics are sentiment context only, not Spot signals."
        )
    }


# ============================================================
# MEMPOOL BITCOIN MINING DATA
# ============================================================

def get_mining_data():

    data, fetched_at, error = safe_fetch(
        f"{MEMPOOL}/v1/mining/hashrate/3d"
    )

    if not isinstance(data, dict):

        return {

            "hashrate": unavailable(error),

            "difficulty": unavailable(error),

            "estimated_hashrate": unavailable(error),

            "fetched_at": fetched_at
        }

    return {

        "hashrate": metric(
            data.get("currentHashrate"),
            "H/s",
            "Mempool.space",
            fetched_at,
            10 * 60,
            fetched_at
        ),

        "difficulty": metric(
            data.get("currentDifficulty"),
            "difficulty",
            "Mempool.space",
            fetched_at,
            10 * 60,
            fetched_at
        ),

        "estimated_hashrate": metric(
            data.get("estimatedHashrate"),
            "H/s",
            "Mempool.space",
            fetched_at,
            10 * 60,
            fetched_at
        ),

        "fetched_at": fetched_at,

        "observation_note": (
            "Provider API retrieval timestamp; "
            "not an independently verified block observation time."
        )
    }


# ============================================================
# BITCOIN HALVING COUNTDOWN
# ============================================================

def get_halving():

    try:

        raw, fetched_at = fetch_text(
            f"{MEMPOOL}/blocks/tip/height"
        )

        height = int(raw)

        if height < 0:
            raise ValueError("Invalid Bitcoin block height")

        next_halving = (
            (height // HALVING_INTERVAL) + 1
        ) * HALVING_INTERVAL

        remaining = max(
            0,
            next_halving - height
        )

        estimated_days = (
            remaining * 10 / 1440
        )

        return {

            "current_block_height": height,

            "next_halving_block": next_halving,

            "blocks_remaining": remaining,

            "estimated_days_remaining": round(
                estimated_days,
                2
            ),

            "estimated_years_remaining": round(
                estimated_days / 365.25,
                2
            ),

            "status": "OK",

            "source": "Mempool.space",

            "source_updated_at": fetched_at,

            "fetched_at": fetched_at,

            "note": (
                "Estimated time only. Actual halving is determined "
                "by Bitcoin block height, not calendar date."
            )
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

            "source_updated_at": None,

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
        "&page_size=5"
    )

    data, fetched_at, error = safe_fetch(url)

    if not isinstance(data, dict):

        return {

            "mvrv_ratio": unavailable(error),

            "mvrv_z_score": unavailable(
                "MVRV Z-Score unavailable"
            ),

            "status": "UNAVAILABLE"
        }

    rows = safe_list(data.get("data"))

    valid_rows = []

    for row in rows:

        if not isinstance(row, dict):
            continue

        observation_date = row.get("time")

        observed_at = parse_timestamp(
            observation_date
        )

        ratio = finite(
            row.get("CapMVRVCur")
        )

        if (
            observed_at is None
            or ratio is None
            or ratio <= 0
        ):
            continue

        valid_rows.append(
            (observed_at, ratio, observation_date)
        )

    if not valid_rows:

        return {

            "mvrv_ratio": unavailable(
                "No valid MVRV observation returned"
            ),

            "mvrv_z_score": unavailable(
                "MVRV Z-Score not supplied by CapMVRVCur"
            ),

            "status": "UNAVAILABLE"
        }

    valid_rows.sort(
        key=lambda item: item[0]
    )

    observed_at, ratio, observation_date = valid_rows[-1]

    status = freshness_status(
        observation_date,
        MVRV_MAX_AGE_SECONDS
    )

    mvrv_metric = metric(
        ratio,
        "ratio",
        "Coin Metrics Community API",
        observation_date,
        MVRV_MAX_AGE_SECONDS,
        fetched_at
    )

    mvrv_metric["observation_date"] = observation_date

    return {

        "mvrv_ratio": mvrv_metric,

        "mvrv_z_score": unavailable(
            "CapMVRVCur is MVRV Ratio, not MVRV Z-Score"
        ),

        "status": status,

        "observation_date": observation_date,

        "fetched_at": fetched_at
    }


# ============================================================
# BINANCE SPOT MARKET BREADTH
# ============================================================

def get_spot_activity():

    rows, fetched_at, error = safe_fetch(
        f"{BINANCE}/api/v3/ticker/24hr"
    )

    if not isinstance(rows, list):

        return {

            "status": "UNAVAILABLE",

            "reason": str(error),

            "volume_leaders_24h": [],

            "breadth": unavailable(error),

            "fetched_at": fetched_at
        }

    info, info_fetched_at, info_error = safe_fetch(
        f"{BINANCE}/api/v3/exchangeInfo"
    )

    if (
        not isinstance(info, dict)
        or not isinstance(info.get("symbols"), list)
    ):

        return {

            "status": "PARTIAL",

            "reason": (
                "Ticker data fetched, but exchangeInfo metadata "
                "was unavailable. Breadth classification withheld. "
                + str(info_error or "")
            )[:250],

            "volume_leaders_24h": [],

            "breadth": unavailable(
                "Cannot classify Spot pairs without exchange metadata"
            ),

            "fetched_at": fetched_at
        }

    stablecoins = {

        "USDT", "USDC", "FDUSD", "TUSD", "USDP",
        "DAI", "BUSD", "USDE", "USDS", "USDD",
        "USTC", "EUR", "EURI", "AEUR", "USD1",
        "RLUSD", "PYUSD", "UST"
    }

    tokenized_equities = {

        "NVDAB", "SOXLB", "TSLAB", "AAPLX",
        "MSFTX", "AMZNX", "GOOGLX", "METAX",
        "MSTRX", "COINX", "SPYX", "QQQX",
        "CRCLX", "HOODX", "PLTRX"
    }

    leveraged_suffixes = (
        "UP",
        "DOWN",
        "BULL",
        "BEAR"
    )

    symbol_meta = {}

    for item in info["symbols"]:

        if not isinstance(item, dict):
            continue

        symbol = item.get("symbol")

        if not isinstance(symbol, str):
            continue

        if item.get("quoteAsset") != "USDT":
            continue

        if item.get("status") != "TRADING":
            continue

        permissions = item.get("permissions")

        if (
            isinstance(permissions, list)
            and permissions
            and "SPOT" not in permissions
        ):
            continue

        symbol_meta[symbol] = item.get("baseAsset")

    valid = []

    advancing = 0
    declining = 0
    unchanged = 0

    excluded_stablecoins = 0
    excluded_equities = 0
    excluded_leveraged = 0
    unmatched_symbols = 0

    for item in rows:

        if not isinstance(item, dict):
            continue

        symbol = item.get("symbol")

        if (
            not isinstance(symbol, str)
            or not symbol.endswith("USDT")
        ):
            continue

        base_asset = symbol_meta.get(symbol)

        if not isinstance(base_asset, str) or not base_asset:
            unmatched_symbols += 1
            continue

        if base_asset in stablecoins:
            excluded_stablecoins += 1
            continue

        if base_asset in tokenized_equities:
            excluded_equities += 1
            continue

        if base_asset.endswith(leveraged_suffixes):
            excluded_leveraged += 1
            continue

        quote_volume = finite(
            item.get("quoteVolume")
        )

        change = finite(
            item.get("priceChangePercent")
        )

        trades = finite(
            item.get("count")
        )

        if (
            quote_volume is None
            or change is None
            or trades is None
            or quote_volume <= 0
            or trades < 0
        ):
            continue

        valid.append({

            "symbol": symbol,

            "base_asset": base_asset,

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

    measured = (
        advancing
        + declining
        + unchanged
    )

    eligible_metadata_pairs = len(symbol_meta)

    coverage_pct = (
        measured / eligible_metadata_pairs * 100
        if eligible_metadata_pairs > 0
        else None
    )

    if measured == 0:

        return {

            "status": "UNAVAILABLE",

            "reason": "No eligible crypto Spot USDT observations",

            "volume_leaders_24h": [],

            "breadth": unavailable(
                "No eligible crypto Spot breadth observations"
            ),

            "fetched_at": fetched_at
        }

    breadth_status = freshness_status(
        fetched_at,
        BREADTH_MAX_AGE_SECONDS
    )

    breadth = {

        "advancing_pairs": advancing,

        "declining_pairs": declining,

        "unchanged_pairs": unchanged,

        "measured_pairs": measured,

        "eligible_metadata_pairs": eligible_metadata_pairs,

        "coverage_pct": (
            round(coverage_pct, 2)
            if coverage_pct is not None
            else None
        ),

        "advance_decline_ratio": (
            round(advancing / declining, 3)
            if declining > 0
            else None
        ),

        "excluded_stablecoin_pairs": excluded_stablecoins,

        "excluded_tokenized_equity_pairs": excluded_equities,

        "excluded_leveraged_token_pairs": excluded_leveraged,

        "unmatched_symbol_count": unmatched_symbols,

        "classification": (
            "Binance Spot USDT trading pairs only. "
            "Stablecoins, known tokenized equity/ETF assets, "
            "leveraged tokens and unmatched metadata excluded."
        ),

        "status": breadth_status,

        "source": "Binance Spot 24h ticker + exchangeInfo",

        "source_updated_at": fetched_at,

        "fetched_at": fetched_at
    }

    return {

        "status": breadth_status,

        "volume_leaders_24h": valid[:12],

        "breadth": breadth,

        "coverage_note": (
            "Coverage is measured against eligible exchangeInfo "
            "USDT Spot pairs; excluded asset categories are not "
            "counted as advancing or declining."
        ),

        "note": (
            "২৪ ঘণ্টার Binance Crypto Spot Breadth. "
            "এটি Binance-এর USDT Spot market coverage, "
            "সমগ্র global crypto market নয়।"
        ),

        "fetched_at": fetched_at
    }


# ============================================================
# ATOMIC JSON WRITE
# ============================================================

def write_json_atomic(path, payload):

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


# ============================================================
# BUILD OUTPUT
# ============================================================

def build_payload():

    generated_at = utc_now()

    print("Fetching Spot Order Books...")

    order_books = {

        "BTCUSDT": get_order_book("BTCUSDT"),

        "ETHUSDT": get_order_book("ETHUSDT")
    }

    print("Fetching Spot Taker Activity...")

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

    print("Fetching Binance Spot Breadth...")

    spot_activity = get_spot_activity()

    print("Fetching CoinBoss Derivatives Context...")

    derivatives = {

        "BTCUSDT": get_derivatives("BTCUSDT"),

        "ETHUSDT": get_derivatives("ETHUSDT")
    }

    return {

        "schema_version": 3,

        "engine": "Free Advanced Crypto Intelligence",

        "engine_version": "3.0.0",

        "generated_at": generated_at,

        "update_mode": "scheduled_snapshot_not_realtime",

        "data_policy": (
            "Free public APIs only. "
            "Unavailable data remains null. "
            "Stale observations are explicitly marked. "
            "No synthetic values. "
            "Futures data is context only, never a Spot signal."
        ),

        "data_sources": [

            "Binance Spot Public API",

            "CoinBoss Public Derivatives API",

            "Mempool.space",

            "Coin Metrics Community API"
        ],

        "etf_flows": unavailable(
            "ETF flow integration not configured"
        ),

        "on_chain": {

            "mvrv_ratio": mvrv["mvrv_ratio"],

            "mvrv_z_score": mvrv["mvrv_z_score"],

            "mvrv_status": mvrv["status"],

            "mvrv_observation_date": mvrv.get(
                "observation_date"
            ),

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

            "estimated_hashrate": mining["estimated_hashrate"],

            "mining_fetched_at": mining.get(
                "fetched_at"
            )
        },

        "halving": halving,

        "spot_market_activity": spot_activity,

        "spot_order_book": order_books,

        "spot_taker_activity": taker_ratios,

        "derivatives": derivatives,

        "liquidation_heatmap": unavailable(
            "Verified liquidation heatmap integration not configured"
        ),

        "portfolio": {

            "status": "LOCAL_ONLY",

            "note": (
                "Portfolio data is not uploaded to external providers."
            )
        },

        "limitations": [

            "Order book contains top 100 levels only, not full market depth.",

            "Order book snapshot retrieval time is not an exchange event timestamp.",

            "CoinBoss derivatives are aggregated cross-exchange Futures context.",

            "Futures metrics must not independently trigger Spot BUY or SELL.",

            "MVRV Ratio is not MVRV Z-Score.",

            "Spot breadth represents Binance eligible USDT Spot pairs only.",

            "ETF flows, verified liquidation heatmap, SOPR, NUPL, exchange netflow and whale entity data are not integrated.",

            "Dashboard refresh interval does not guarantee provider update frequency."
        ]
    }


# ============================================================
# MAIN
# ============================================================

def main():

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    print(
        "Starting Free Advanced Crypto Intelligence Engine v3.0.0"
    )

    result = build_payload()

    write_json_atomic(
        OUTPUT_FILE,
        result
    )

    print("----------------------------------")

    print("ADVANCED ENGINE SUCCESS")

    print("Output:", OUTPUT_FILE)

    print("Version: 3.0.0")

    print("Generated:", result["generated_at"])

    print(
        "Spot Breadth:",
        result["spot_market_activity"].get("status")
    )

    print(
        "MVRV:",
        result["on_chain"]["mvrv_ratio"].get("status")
    )

    for symbol, item in result["spot_order_book"].items():

        print(
            f"{symbol} Order Book:",
            item.get("status")
        )

    for symbol, item in result["spot_taker_activity"].items():

        print(
            f"{symbol} Taker Activity:",
            item.get("status")
        )

    for symbol, item in result["derivatives"].items():

        print(
            f"{symbol} Derivatives:",
            item["data_status"]
        )

    print("----------------------------------")

    return 0


if __name__ == "__main__":

    raise SystemExit(main())
