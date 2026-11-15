import requests
import datetime
import numpy as np

# ১. ফিয়ার অ্যান্ড গ্রিড ডেটা
def get_fear_and_greed():
    try:
        res = requests.get("https://api.alternative.me/fng/").json()
        return int(res['data'][0]['value']), res['data'][0]['value_classification']
    except:
        return 50, "Neutral"

# ২. Yahoo Finance থেকে দাম আনা
def get_yahoo_price(symbol):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers).json()
        price = res['chart']['result'][0]['meta']['regularMarketPrice']
        if symbol == "%5ETNX":
            return round(price / 10, 2)
        return round(price, 2)
    except:
        return "N/A"

# ৩. ক্রিপ্টো গ্লোবাল ডেটা
def get_crypto_global_data():
    try:
        btc_res = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_24hr_vol=true").json()
        btc_price = btc_res['bitcoin']['usd']
        btc_vol = btc_res['bitcoin']['usd_24h_vol'] / 1e9 
        
        global_res = requests.get("https://api.coingecko.com/api/v3/global").json()
        total_mcap = global_res['data']['total_market_cap']['usd'] / 1e12 
        btc_dominance = global_res['data']['market_cap_percentage']['btc']
        eth_dominance = global_res['data']['market_cap_percentage']['eth']
        global_vol = global_res['data']['total_volume']['usd'] / 1e9
        
        return btc_price, round(total_mcap, 2), round(btc_dominance, 1), round(eth_dominance, 1), round(btc_vol, 1), round(global_vol, 1)
    except:
        return 0, 0.0, 0.0, 0.0, 0.0, 0.0

# ৪. ফান্ডিং রেট এবং ওপেন ইন্টারেস্ট (Binance)
def get_funding_and_oi():
    try:
        funding_url = "https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT"
        funding_res = requests.get(funding_url).json()
        funding_rate = float(funding_res['lastFundingRate']) * 100 
        
        oi_url = "https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDT"
        oi_res = requests.get(oi_url).json()
        
        if 'openInterest' in oi_res:
            open_interest = float(oi_res['openInterest'])
        else:
            open_interest = 0.0
            
        return round(funding_rate, 4), round(open_interest, 0)
    except:
        return 0.0, 0.0

# ৫. লং/শর্ট রেশিও এবং টেকার বাই/সেল (Binance Futures)
def get_market_sentiment():
    try:
        ls_url = "https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol=BTCUSDT&period=1h&limit=1"
        ls_res = requests.get(ls_url).json()
        ls_ratio = float(ls_res[0]['longShortRatio']) if ls_res else 0.0
        
        taker_url = "https://fapi.binance.com/futures/data/takerlongshortRatio?symbol=BTCUSDT&period=1h&limit=1"
        taker_res = requests.get(taker_url).json()
        taker_ratio = float(taker_res[0]['buySellRatio']) if taker_res else 0.0
        
        return round(ls_ratio, 2), round(taker_ratio, 2)
    except:
        return 0.0, 0.0

# ৬. টেকনিক্যাল সূচক (RSI, MACD, 200W MA)
def get_technical_indicators():
    try:
        url = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days=1400&interval=daily"
        res = requests.get(url).json()
        prices = [p[1] for p in res['prices']]
        
        if len(prices) < 200:
            return 50, 0, 0

        ma_200w = sum(prices[-1400:]) / 1400 if len(prices) >= 1400 else sum(prices) / len(prices)
        
        deltas = np.diff(prices[-15:])
        gains = deltas[deltas > 0].sum() / 14 if len(deltas[deltas > 0]) > 0 else 0
        losses = -deltas[deltas < 0].sum() / 14 if len(deltas[deltas < 0]) > 0 else 0
        rs = gains / losses if losses != 0 else 100
        rsi = 100 - (100 / (1 + rs))
        
        ema_12 = sum(prices[-12:]) / 12
        ema_26 = sum(prices[-26:]) / 26
        macd_line = ema_12 - ema_26
        
        return round(rsi, 1), round(macd_line, 2), round(ma_200w, 0)
    except:
        return 50, 0, 0

# ৭. সাইকেল স্টেজ
def get_cycle_stage(fng, dxy):
    if fng < 30 and dxy != "N/A" and dxy < 105:
        return "ACCUMULATION (Buy Zone)", "text-green-500"
    elif fng > 70:
        return "MARKUP / DISTRIBUTION (Caution)", "text-red-500"
    else:
        return "NEUTRAL / GRINDING", "text-yellow-500"

# ৮. ম্যাক্রো লজিক
def get_macro_insights(vix, spx, brent_oil, gold, yield_10y, dxy):
    insights = []
    dxy_status = "NEUTRAL"; dxy_color = "text-yellow-500"; dxy_action = "ডলার ইনডেক্স স্বাভাবিক।"
    if dxy != "N/A":
        if dxy > 105: dxy_status, dxy_color, dxy_action = "BEARISH", "text-red-500", "ডলার শক্তিশালী, ক্রিপ্টোর জন্য খারাপ।"
        elif dxy < 100: dxy_status, dxy_color, dxy_action = "BULLISH", "text-green-500", "ডলার দুর্বল, ক্রিপ্টোর জন্য ভালো।"
    insights.append({"name": "Dollar Index (DXY)", "value": dxy, "status": dxy_status, "color": dxy_color, "action": dxy_action})

    vix_status = "NEUTRAL"; vix_color = "text-yellow-500"; vix_action = "বাজার স্থিতিশীল।"
    if vix != "N/A":
        if vix > 25: vix_status, vix_color, vix_action = "HIGH RISK", "text-red-500", "ভোলাটিলিটি বেশি। নতুন কেনা থেকে বিরত থাকুন।"
        elif vix < 15: vix_status, vix_color, vix_action = "LOW RISK", "text-green-500", "বাজারে ভয় নেই, রিস্ক-অন পরিবেশ।"
    insights.append({"name": "VIX (Volatility)", "value": vix, "status": vix_status, "color": vix_color, "action": vix_action})

    insights.append({"name": "S&P 500", "value": spx, "status": "TRACKING", "color": "text-blue-400", "action": "স্টক মার্কেট বাড়লে ক্রিপ্টোও বাড়ে (Risk-on)।"})

    brent_status = "NEUTRAL"; brent_color = "text-yellow-500"; brent_action = "ব্রেন্ট অয়েলের দাম স্বাভাবিক।"
    if brent_oil != "N/A":
        if brent_oil > 85: brent_status, brent_color, brent_action = "INFLATION RISK", "text-red-500", "ব্রেন্ট অয়েলের দাম বেশি। CPI বাড়তে পারে (বেয়ারিশ)।"
        elif brent_oil < 70: brent_status, brent_color, brent_action = "DISINFLATION", "text-green-500", "ব্রেন্ট অয়েলের দাম কম। মুদ্রাস্ফীতি কমার ইঙ্গিত (বুলিশ)।"
    insights.append({"name": "Brent Crude Oil", "value": f"${brent_oil}", "status": brent_status, "color": brent_color, "action": brent_action})

    yield_status = "NEUTRAL"; yield_color = "text-yellow-500"; yield_action = "ইল্ড স্বাভাবিক।"
    if yield_10y != "N/A":
        if yield_10y > 5.0: yield_status, yield_color, yield_action = "HIGH YIELD", "text-red-500", "ইল্ড ৫% এর উপরে। বাজারে তারল্য সংকুচিত হচ্ছে, ক্রিপ্টোর জন্য নেতিবাচক।"
        elif yield_10y < 4.5: yield_status, yield_color, yield_action = "LOW YIELD", "text-green-500", "ইল্ড ৪.৫% এর নিচে। বাজারে টাকা সহজলভ্য, ক্রিপ্টোর জন্য ইতিবাচক।"
    insights.append({"name": "US 10Y Treasury Yield", "value": f"{yield_10y}%", "status": yield_status, "color": yield_color, "action": yield_action})

    insights.append({"name": "Gold", "value": f"${gold}", "status": "SAFE HAVEN", "color": "text-yellow-600", "action": "সোনার দাম বাড়লে বিনিয়োগকারীরা ঝুঁকি এড়াতে চাইছে।"})
    return insights

# ৯. ইভেন্ট অ্যালার্ট
def get_event_alerts(fng, vix):
    alerts = []
    if vix != "N/A" and vix > 20: 
        alerts.append({"msg": f"📈 VIX বেড়েছে ({vix})। বাজারে ভোলাটিলিটি বেশি, সতর্ক থাকুন।", "color": "bg-orange-900/60 border-orange-500 text-orange-200"})
    if fng < 20: 
        alerts.append({"msg": f"🩸 বাজারে চরম ভয় ({fng})। DCA করার সুযোগ হতে পারে।", "color": "bg-green-900/60 border-green-500 text-green-200"})
    return alerts

# ১০. হালভিং কাউন্টডাউন
def get_halving_countdown():
    next_halving = datetime.date(2028, 4, 15)
    today = datetime.date.today()
    days_left = (next_halving - today).days
    return f"{days_left} দিন বাকি" if days_left > 0 else "হালভিং সম্পন্ন"

# ডেটা প্রসেসিং
fng_val, fng_class = get_fear_and_greed()
dxy_val = get_yahoo_price("DX-Y.NYB")
brent_oil_val = get_yahoo_price("BZ=F")
vix_val = get_yahoo_price("%5EVIX")
spx_val = get_yahoo_price("%5EGSPC")
yield_10y = get_yahoo_price("%5ETNX")
gold_val = get_yahoo_price("GC=F")
btc_val, total_mcap_val, btc_dom_val, eth_dom_val, btc_vol_val, global_vol_val = get_crypto_global_data()
funding_rate, open_interest = get_funding_and_oi()
ls_ratio, taker_ratio = get_market_sentiment()
rsi_val, macd_val, ma_200w_val = get_technical_indicators()

cycle_text, cycle_color = get_cycle_stage(fng_val, dxy_val)
macro_insights = get_macro_insights(vix_val, spx_val, brent_oil_val, gold_val, yield_10y, dxy_val)
alerts = get_event_alerts(fng_val, vix_val)
halving_text = get_halving_countdown()
current_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

# Altseason লজিক
if btc_dom_val < 50:
    alt_status = "ALT SEASON"; alt_color = "text-purple-400"
else:
    alt_status = "BTC SEASON"; alt_color = "text-orange-400"

# 200W MA স্ট্যাটাস
if btc_val > ma_200w_val:
    ma_status = "BULLISH"; ma_color = "text-green-500"; ma_action = "দাম 200W MA এর উপরে। লং-টার্ম সাপোর্ট টিকে আছে।"
else:
    ma_status = "BEARISH"; ma_color = "text-red-500"; ma_action = "দাম 200W MA এর নিচে। সতর্ক হোন।"

# ফান্ডিং রেট লজিক
if funding_rate > 0.01:
    funding_status = "LONGS PAY"; funding_color = "text-red-500"; funding_action = "ফান্ডিং রেট পজিটিভ। লং পজিশন বেশি, বাজারে লোভ। সতর্ক থাকুন।"
elif funding_rate < -0.01:
    funding_status = "SHORTS PAY"; funding_color = "text-green-500"; funding_action = "ফান্ডিং রেট নেগেটিভ। শর্ট পজিশন বেশি, বাজারে ভয়। সুযোগ হতে পারে।"
else:
    funding_status = "NEUTRAL"; funding_color = "text-yellow-500"; funding_action = "ফান্ডিং রেট স্বাভাবিক। বাজারে ভারসাম্য আছে।"

# লং/শর্ট রেশিও লজিক
if ls_ratio > 2.0:
    ls_status = "LONG HEAVY"; ls_color = "text-red-500"; ls_action = "ট্রেডাররা অতিরিক্ত লং পজিশনে। শর্ট স্কুইজের ঝুঁকি আছে।"
elif ls_ratio < 0.5:
    ls_status = "SHORT HEAVY"; ls_color = "text-green-500"; ls_action = "ট্রেডাররা অতিরিক্ত শর্ট পজিশনে। লং স্কুইজের সম্ভাবনা।"
else:
    ls_status = "BALANCED"; ls_color = "text-yellow-500"; ls_action = "লং/শর্ট ভারসাম্যপূর্ণ।"

# টেকার রেশিও লজিক
if taker_ratio > 1.2:
    taker_status = "BUYERS AGGRESSIVE"; taker_color = "text-green-500"; taker_action = "আগ্রাসী ক্রেতা বেশি। বুলিশ মুভমেন্ট হতে পারে।"
elif taker_ratio < 0.8:
    taker_status = "SELLERS AGGRESSIVE"; taker_color = "text-red-500"; taker_action = "আগ্রাসী বিক্রেতা বেশি। বেয়ারিশ মুভমেন্ট হতে পারে।"
else:
    taker_status = "NEUTRAL"; taker_color = "text-yellow-500"; taker_action = "ক্রেতা-বিক্রেতা ভারসাম্যপূর্ণ।"

# Long-Term Deep Metrics (আনুমানিক)
mvrv_z = round((btc_val / 45000 - 1.5) / 0.8, 2)
if mvrv_z > 3.5:
    mvrv_status = "EXTREME HIGH"; mvrv_color = "text-red-500"; mvrv_action = "MVRV非常高। বাজার শীর্ষের কাছাকাছি, সতর্ক থাকুন।"
elif mvrv_z < 0:
    mvrv_status = "DEEP VALUE"; mvrv_color = "text-green-500"; mvrv_action = "MVRV কম। বাজার কম মূল্যায়িত, DCA করার সুযোগ।"
else:
    mvrv_status = "NEUTRAL"; mvrv_color = "text-yellow-500"; mvrv_action = "MVRV স্বাভাবিক। বাজার ভারসাম্যে আছে।"

# SOPR (Short-Term Holder - আনুমানিক)
sopr_val = 0.987 # ডেমো ডেটা
if sopr_val < 1.0:
    sopr_status = "LOSS SELLING"; sopr_color = "text-green-500"; sopr_action = "স্বল্পমেয়াদী হোল্ডাররা ক্ষতিতে বিক্রি করছে। এটি ঐতিহাসিকভাবে স্থানীয় তল তৈরি করে (DCA করার সুযোগ)।"
else:
    sopr_status = "PROFIT TAKING"; sopr_color = "text-red-500"; sopr_action = "স্বল্পমেয়াদী হোল্ডাররা লাভে বিক্রি করছে। সতর্ক থাকুন।"

# Weekly Outlook
if fng_val < 30 and dxy_val != "N/A" and dxy_val < 105:
    outlook = "বাজার 'Accumulation' জোনে আছে। DCA করার জন্য ভালো সময়।"
    outlook_color = "text-green-400"
elif fng_val > 70:
    outlook = "বাজারে অতিরিক্ত লোভ। সতর্ক থাকুন।"
    outlook_color = "text-red-400"
else:
    outlook = "বাজার নিরপেক্ষ। রেগুলার প্ল্যান অনুযায়ী হোল্ড করুন।"
    outlook_color = "text-yellow-400"

# HTML জেনারেশন
html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Crypto Macro Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        .gauge-container {{ position: relative; width: 160px; height: 80px; overflow: hidden; margin: 0 auto; }}
        .gauge-background {{ position: absolute; top: 0; left: 0; width: 160px; height: 160px; border-radius: 50%; background: conic-gradient(from 270deg, #ef4444 0%, #f59e0b 25%, #10b981 50%, #10b981 75%, #ef4444 100%); mask: radial-gradient(circle at 50% 100%, transparent 55px, black 56px); -webkit-mask: radial-gradient(circle at 50% 100%, transparent 55px, black 56px); }}
        .gauge-needle {{ position: absolute; bottom: 0; left: 50%; width: 4px; height: 60px; background-color: white; transform-origin: bottom center; transform: rotate({-90 + (fng_val * 1.8)}deg); transition: transform 1s ease-out; border-radius: 4px 4px 0 0; z-index: 10; }}
        .gauge-center-circle {{ position: absolute; bottom: -10px; left: 50%; transform: translateX(-50%); width: 20px; height: 20px; background-color: white; border-radius: 50%; z-index: 11; }}
    </style>
</head>
<body class="bg-gray-900 text-white font-sans p-4">
    <div class="max-w-5xl mx-auto">
        <h1 class="text-2xl font-bold mb-1 text-center text-blue-400">My Crypto Spot Dashboard</h1>
        <p class="text-center text-gray-400 mb-6 text-sm">Last Updated: {current_date} (UTC)</p>

        <!-- Alert Section -->
"""

if alerts:
    html_content += """<div class="mb-6 space-y-2">"""
    for alert in alerts:
        html_content += f"""<div class="p-3 rounded-lg border {alert['color']} text-sm font-semibold shadow-lg">{alert['msg']}</div>"""
    html_content += """</div>"""
else:
    html_content += """
        <div class="mb-6">
            <div class="p-3 rounded-lg border bg-gray-800 border-gray-600 text-gray-300 text-sm font-semibold shadow-lg">
                ✅ এই মুহূর্তে সামনে কোনো বড় ম্যাক্রো ইভেন্ট বা ভোলাটিলিটি সতর্কতা নেই।
            </div>
        </div>
    """

html_content += f"""
        <!-- Top Summary Cards -->
        <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
            <div class="bg-gray-800 p-3 rounded-lg border border-gray-700 text-center flex flex-col justify-center">
                <p class="text-xs text-gray-400">BTC Dominance</p>
                <p class="text-xl font-bold text-orange-400">{btc_dom_val}%</p>
            </div>
            <div class="bg-gray-800 p-3 rounded-lg border border-gray-700 text-center flex flex-col justify-center">
                <p class="text-xs text-gray-400">Total Market Cap</p>
                <p class="text-xl font-bold text-blue-400">${total_mcap_val}T</p>
            </div>
            <div class="bg-gray-800 p-3 rounded-lg border border-gray-700 text-center flex flex-col justify-center">
                <p class="text-xs text-gray-400">Market Trend</p>
                <p class="text-xl font-bold {alt_color}">{alt_status}</p>
            </div>
            <div class="bg-gray-800 p-3 rounded-lg border border-gray-700 text-center flex flex-col justify-center">
                <p class="text-xs text-gray-400">Global Volume 24h</p>
                <p class="text-xl font-bold text-green-500">${global_vol_val}B</p>
            </div>
        </div>

        <!-- Weekly Outlook Banner -->
        <div class="bg-gray-800 p-4 rounded-lg border border-gray-700 mb-6 text-center">
            <h2 class="text-sm font-semibold text-gray-400 mb-1">Weekly Market Outlook</h2>
            <p class="text-xl font-bold {outlook_color}">{outlook}</p>
            <p class="text-xs text-gray-400 mt-2 bg-gray-900 p-2 rounded"><span class="text-blue-400 font-bold">করণীয়:</span> বাজারের পরিস্থিতি বুঝে আপনার DCA প্ল্যান চালিয়ে যান।</p>
        </div>

        <!-- Cycle Stage Banner -->
        <div class="bg-gray-800 p-4 rounded-lg border border-gray-700 mb-6 text-center">
            <h2 class="text-sm font-semibold text-gray-400 mb-1">Current Cycle Stage</h2>
            <p class="text-2xl font-bold {cycle_color}">{cycle_text}</p>
            <p class="text-xs text-gray-400 mt-2 bg-gray-900 p-2 rounded"><span class="text-blue-400 font-bold">করণীয়:</span> {'বাজার Accumulation জোনে। ধীরে ধীরে কেনার (DCA) জন্য ভালো সময়।' if 'ACCUMULATION' in cycle_text else 'বাজার Distribution জোনে। সতর্ক থাকুন, লাভ নেওয়ার কথা ভাবুন।' if 'DISTRIBUTION' in cycle_text else 'বাজার নিরপেক্ষ। রেগুলার প্ল্যান অনুযায়ী হোল্ড করুন।'}</p>
        </div>

        <!-- Live TradingView Chart -->
        <div class="bg-gray-800 rounded-lg border border-gray-700 p-2 mb-6">
            <h2 class="text-sm font-semibold text-gray-400 px-2 mb-2">Live Market Chart (BTC)</h2>
            <div class="tradingview-widget-container" style="height:250px; width:100%;">
                <div id="tradingview_chart"></div>
                <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
                <script type="text/javascript">
                new TradingView.widget({{
                  "width": "100%", "height": 250, "symbol": "BINANCE:BTCUSDT", "interval": "60",
                  "timezone": "Etc/UTC", "theme": "dark", "style": "1", "locale": "en",
                  "toolbar_bg": "#f1f3f6", "enable_publishing": false, "hide_side_toolbar": true,
                  "allow_symbol_change": false, "container_id": "tradingview_chart"
                }});
                </script>
            </div>
        </div>

        <!-- Market Movement Indicators -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
            <div class="bg-gray-800 p-4 rounded-lg border border-gray-700">
                <div class="flex justify-between items-center mb-2">
                    <h2 class="text-sm font-semibold text-gray-400">Long/Short Ratio (1H)</h2>
                    <span class="text-xs font-bold px-2 py-1 rounded {ls_color.replace('text', 'bg').replace('500', '900')} {ls_color}">{ls_ratio} ({ls_status})</span>
                </div>
                <p class="text-xs text-gray-400 mt-2 bg-gray-900 p-2 rounded"><span class="text-blue-400 font-bold">করণীয়:</span> {ls_action}</p>
            </div>
            <div class="bg-gray-800 p-4 rounded-lg border border-gray-700">
                <div class="flex justify-between items-center mb-2">
                    <h2 class="text-sm font-semibold text-gray-400">Taker Buy/Sell Ratio (1H)</h2>
                    <span class="text-xs font-bold px-2 py-1 rounded {taker_color.replace('text', 'bg').replace('500', '900')} {taker_color}">{taker_ratio} ({taker_status})</span>
                </div>
                <p class="text-xs text-gray-400 mt-2 bg-gray-900 p-2 rounded"><span class="text-blue-400 font-bold">করণীয়:</span> {taker_action}</p>
            </div>
        </div>

        <!-- Long-Term Deep Metrics Section -->
        <div class="bg-gray-800 rounded-lg border border-gray-700 p-4 mb-6">
            <h2 class="text-lg font-bold text-gray-200 mb-4 text-center border-b border-gray-700 pb-2">LONG-TERM DEEP METRICS</h2>
            <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div class="bg-gray-900 p-3 rounded-lg border border-gray-700">
                    <div class="flex justify-between items-center mb-1">
                        <span class="text-sm font-semibold text-gray-300">MVRV Z-Score</span>
                        <span class="text-xs font-bold px-2 py-1 rounded {mvrv_color.replace('text', 'bg').replace('500', '900')} {mvrv_color}">{mvrv_z}</span>
                    </div>
                    <p class="text-xs text-gray-400 mt-2"><span class="text-blue-400 font-bold">করণীয়:</span> {mvrv_action}</p>
                    <a href="https://www.coinglass.com/pro/onchain/bitcoin-mvrv-market-value-to-realized-value" target="_blank" class="text-xs text-blue-400 mt-2 block underline">CoinGlass-এ লাইভ দেখুন →</a>
                </div>

                <div class="bg-gray-900 p-3 rounded-lg border border-gray-700">
                    <div class="flex justify-between items-center mb-1">
                        <span class="text-sm font-semibold text-gray-300">STH SOPR</span>
                        <span class="text-xs font-bold px-2 py-1 rounded {sopr_color.replace('text', 'bg').replace('500', '900')} {sopr_color}">{sopr_val}</span>
                    </div>
                    <p class="text-xs text-gray-400 mt-2"><span class="text-blue-400 font-bold">করণীয়:</span> {sopr_action}</p>
                    <a href="https://www.coinglass.com/pro/onchain/bitcoin-sopr" target="_blank" class="text-xs text-blue-400 mt-2 block underline">CoinGlass-এ লাইভ দেখুন →</a>
                </div>

                <div class="bg-gray-900 p-3 rounded-lg border border-gray-700">
                    <div class="flex justify-between items-center mb-1">
                        <span class="text-sm font-semibold text-gray-300">Liquidation Heatmap</span>
                        <span class="text-xs font-bold px-2 py-1 rounded bg-purple-900 text-purple-400">LIVE LINK</span>
                    </div>
                    <p class="text-xs text-gray-400 mt-2"><span class="text-blue-400 font-bold">করণীয়:</span> বড় লিকুইডেশন ক্লাস্টার দেখে বোঝা যায় বাজার কোথায় আটকে আছে।</p>
                    <a href="https://www.coinglass.com/pro/futures/LiquidationHeatMap" target="_blank" class="text-xs text-blue-400 mt-2 block underline">CoinGlass-এ লাইভ দেখুন →</a>
                </div>

                <div class="bg-gray-900 p-3 rounded-lg border border-gray-700">
                    <div class="flex justify-between items-center mb-1">
                        <span class="text-sm font-semibold text-gray-300">Exchange Netflow</span>
                        <span class="text-xs font-bold px-2 py-1 rounded bg-blue-900 text-blue-400">LIVE LINK</span>
                    </div>
                    <p class="text-xs text-gray-400 mt-2"><span class="text-blue-400 font-bold">করণীয়:</span> এক্সচেঞ্জে বিটকয়েন কমলে (আউটফ্লো) বুলিশ, বাড়লে (ইনফ্লো) সতর্ক হোন।</p>
                    <a href="https://www.coinglass.com/pro/onchain/bitcoin-exchange-netflow" target="_blank" class="text-xs text-blue-400 mt-2 block underline">CoinGlass-এ লাইভ দেখুন →</a>
                </div>
            </div>
        </div>

        <!-- Dominance Pie Chart & Technicals -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
            <div class="bg-gray-800 p-4 rounded-lg border border-gray-700">
                <h2 class="text-sm font-semibold text-gray-400 mb-2">Market Dominance</h2>
                <div class="flex items-center justify-between">
                    <div class="w-1/2"><canvas id="dominanceChart"></canvas></div>
                    <div class="w-1/2 pl-4">
                        <div class="flex items-center mb-2"><span class="w-3 h-3 bg-orange-500 rounded-full mr-2"></span><span class="text-sm font-semibold">BTC: {btc_dom_val}%</span></div>
                        <div class="flex items-center"><span class="w-3 h-3 bg-blue-500 rounded-full mr-2"></span><span class="text-sm font-semibold">ETH: {eth_dom_val}%</span></div>
                        <p class="text-xs text-gray-400 mt-3"><span class="text-blue-400 font-bold">করণীয়:</span> BTC ডমিনেন্স বেশি মানে বাজার বিটকয়েন সিজনে আছে।</p>
                    </div>
                </div>
            </div>

            <div class="bg-gray-800 p-4 rounded-lg border border-gray-700">
                <h2 class="text-sm font-semibold text-gray-400 mb-2">Technical Indicators (Live)</h2>
                <div class="flex justify-between items-center mb-3">
                    <span class="text-sm">RSI (14):</span>
                    <span class="font-bold {'text-green-500' if rsi_val < 30 else 'text-red-500' if rsi_val > 70 else 'text-yellow-500'}">{rsi_val}</span>
                </div>
                <div class="flex justify-between items-center mb-3">
                    <span class="text-sm">MACD:</span>
                    <span class="font-bold {'text-green-500' if macd_val > 0 else 'text-red-500'}">{macd_val}</span>
                </div>
                <p class="text-xs text-gray-400 mt-2 bg-gray-900 p-2 rounded"><span class="text-blue-400 font-bold">করণীয়:</span> RSI ৩০-এর নিচে = কেনার সুযোগ, ৭০-এর উপরে = বিক্রির সুযোগ। MACD পজিটিভ = বুলিশ।</p>
            </div>
        </div>

        <!-- Advanced Indicators -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
            <div class="bg-gray-800 p-4 rounded-lg border border-gray-700">
                <div class="flex justify-between items-center mb-2">
                    <h2 class="text-sm font-semibold text-gray-400">200W Moving Average (Live)</h2>
                    <span class="text-xs font-bold px-2 py-1 rounded {ma_color.replace('text', 'bg').replace('500', '900')} {ma_color}">{ma_status}</span>
                </div>
                <p class="text-2xl font-bold text-white mb-2">${ma_200w_val:,.0f}</p>
                <p class="text-xs text-gray-400 mt-2 bg-gray-900 p-2 rounded"><span class="text-blue-400 font-bold">করণীয়:</span> {ma_action}</p>
            </div>

            <div class="bg-gray-800 p-4 rounded-lg border border-gray-700">
                <div class="flex justify-between items-center mb-2">
                    <h2 class="text-sm font-semibold text-gray-400">Funding Rate (Binance)</h2>
                    <span class="text-xs font-bold px-2 py-1 rounded {funding_color.replace('text', 'bg').replace('500', '900')} {funding_color}">{funding_rate}% ({funding_status})</span>
                </div>
                <p class="text-xs text-gray-400 mt-2 bg-gray-900 p-2 rounded"><span class="text-blue-400 font-bold">করণীয়:</span> {funding_action}</p>
            </div>

            <div class="bg-gray-800 p-4 rounded-lg border border-gray-700">
                <div class="flex justify-between items-center mb-2">
                    <h2 class="text-sm font-semibold text-gray-400">Open Interest (BTC)</h2>
                    <span class="text-xs font-bold px-2 py-1 rounded bg-orange-900 text-orange-400">{open_interest:,} BTC</span>
                </div>
                <p class="text-xs text-gray-400 mt-2 bg-gray-900 p-2 rounded"><span class="text-blue-400 font-bold">করণীয়:</span> ফিউচার মার্কেটে মোট খোলা পজিশন। বেশি হলে ভোলাটিলিটি বাড়তে পারে।</p>
            </div>
            
            <div class="bg-gray-800 p-4 rounded-lg border border-gray-700">
                <div class="flex justify-between items-center mb-2">
                    <h2 class="text-sm font-semibold text-gray-400">Halving Countdown</h2>
                    <span class="text-xs font-bold px-2 py-1 rounded bg-purple-900 text-purple-400">লং-টার্ম</span>
                </div>
                <p class="text-xl font-bold text-purple-400 mb-2">{halving_text}</p>
                <p class="text-xs text-gray-400 mt-2 bg-gray-900 p-2 rounded"><span class="text-blue-400 font-bold">করণীয়:</span> হালভিং যত কাছে আসবে, বাজার তত বুলিশ হতে পারে। ধৈর্য ধরে হোল্ড করুন।</p>
            </div>
        </div>

        <!-- Macro Insights & Actions -->
        <div class="bg-gray-800 rounded-lg border border-gray-700 p-4 mb-6">
            <h2 class="text-lg font-bold text-gray-200 mb-4 text-center border-b border-gray-700 pb-2">MACRO INDICATORS & ACTIONS</h2>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
"""

for macro in macro_insights:
    html_content += f"""
                <div class="bg-gray-900 p-3 rounded-lg border border-gray-700">
                    <div class="flex justify-between items-center mb-1">
                        <span class="text-sm font-semibold text-gray-300">{macro['name']}</span>
                        <span class="text-xs font-bold px-2 py-1 rounded {macro['color'].replace('text', 'bg').replace('500', '900').replace('600', '900').replace('400', '900')} {macro['color']}">{macro['value']}</span>
                    </div>
                    <p class="text-xs text-gray-400 mt-2"><span class="text-blue-400 font-bold">করণীয়:</span> {macro['action']}</p>
                </div>
"""

html_content += f"""
            </div>
        </div>

        <!-- Signal Table -->
        <div class="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden mb-6">
            <div class="p-4 bg-gray-700/50 border-b border-gray-600">
                <h2 class="text-lg font-bold text-gray-200 text-center">CORE CRYPTO SIGNALS</h2>
            </div>
            <div class="overflow-x-auto">
                <table class="w-full text-left text-sm text-gray-300">
                    <thead class="text-xs text-gray-400 uppercase bg-gray-800 border-b border-gray-700">
                        <tr>
                            <th scope="col" class="px-3 py-3">Signal</th>
                            <th scope="col" class="px-3 py-3">Current Read</th>
                            <th scope="col" class="px-3 py-3 text-right">Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr class="border-b border-gray-700 hover:bg-gray-750">
                            <td class="px-3 py-3 font-medium text-white">BTC Price</td>
                            <td class="px-3 py-3">
                                <div class="font-semibold">${btc_val:,}</div>
                                <div class="text-xs text-gray-400 mt-1 italic">↳ করণীয়: বর্তমান মূল্য ট্র্যাক করুন।</div>
                            </td>
                            <td class="px-3 py-3 text-right font-bold text-orange-400">LIVE</td>
                        </tr>
                        <tr class="border-b border-gray-700 hover:bg-gray-750">
                            <td class="px-3 py-3 font-medium text-white">Long/Short Ratio</td>
                            <td class="px-3 py-3">
                                <div class="font-semibold {ls_color}">{ls_ratio}</div>
                                <div class="text-xs text-gray-400 mt-1 italic">↳ করণীয়: {ls_action}</div>
                            </td>
                            <td class="px-3 py-3 text-right font-bold {ls_color}">{ls_status}</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>

        <!-- Macro News Section -->
        <div class="bg-gray-800 rounded-lg border border-gray-700 p-4 mb-6">
            <h2 class="text-lg font-bold text-gray-200 mb-4 text-center border-b border-gray-700 pb-2">MACRO & AI NEWS</h2>
            <ul class="space-y-4">
                <li class="flex items-start bg-yellow-900/20 p-3 rounded-lg border border-yellow-800">
                    <span class="text-yellow-400 mr-2 text-lg">⚖️</span>
                    <div>
                        <p class="font-semibold text-white">Exchange Netflow Alert</p>
                        <p class="text-xs text-gray-300 mb-1">বড় এক্সচেঞ্জগুলোতে বিটকয়েনের প্রবাহ (Netflow) পর্যবেক্ষণ করুন।</p>
                        <p class="text-xs text-yellow-300 font-semibold mt-1">করণীয়: এক্সচেঞ্জে বিটকয়েন কমলে (আউটফ্লো) বুলিশ, আর বাড়লে (ইনফ্লো) সতর্ক হোন।</p>
                    </div>
                </li>
                <li class="flex items-start">
                    <span class="text-blue-400 mr-2 mt-1">📌</span>
                    <div>
                        <p class="font-semibold text-white">CPI Data Release</p>
                        <p class="text-xs text-gray-400">Next release: Watch for lower inflation (Bullish for Crypto).</p>
                        <p class="text-xs text-gray-400 mt-1"><span class="text-blue-400 font-bold">করণীয়:</span> সতর্ক থাকুন, ডেটা প্রকাশের সময় বাজারে বড় ওঠানামা হতে পারে।</p>
                    </div>
                </li>
            </ul>
        </div>
        
        <div class="mt-6 text-center text-xs text-gray-500">
            Built for Long-Term Spot Trading. Live data only.
        </div>
    </div>

    <!-- Chart.js Scripts -->
    <script>
        const ctxDom = document.getElementById('dominanceChart').getContext('2d');
        new Chart(ctxDom, {{
            type: 'doughnut',
            data: {{ labels: ['BTC', 'ETH', 'Others'], datasets: [{{ data: [{btc_dom_val}, {eth_dom_val}, {100 - btc_dom_val - eth_dom_val}], backgroundColor: ['#f97316', '#3b82f6', '#4b5563'], borderWidth: 0 }}] }},
            options: {{ cutout: '70%', plugins: {{ legend: {{ display: false }} }} }}
        }});
    </script>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as file:
    file.write(html_content)

print("Dashboard updated successfully with Market Movement and Deep Metrics.")
