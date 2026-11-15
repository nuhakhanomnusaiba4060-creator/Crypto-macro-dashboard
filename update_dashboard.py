import requests
import datetime

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
        
        stablecoin_mcap = 160.5 
        
        return btc_price, round(total_mcap, 2), round(btc_dominance, 1), round(eth_dominance, 1), round(btc_vol, 1), round(global_vol, 1), stablecoin_mcap
    except:
        return 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0

# ৪. ফান্ডিং রেট এবং ওপেন ইন্টারেস্ট
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

# ৫. MVRV Z-Score (আনুমানিক)
def get_mvrv_zscore(btc_price):
    realized_price = 45000 
    if btc_price <= 0:
        return "N/A"
    mvrv_ratio = btc_price / realized_price
    z_score = (mvrv_ratio - 1.5) / 0.8 
    return round(z_score, 2)

# ৬. সাইকেল স্টেজ
def get_cycle_stage(fng, dxy):
    if fng < 30 and dxy != "N/A" and dxy < 105:
        return "ACCUMULATION (Buy Zone)", "text-green-500"
    elif fng > 70:
        return "MARKUP / DISTRIBUTION (Caution)", "text-red-500"
    else:
        return "NEUTRAL / GRINDING", "text-yellow-500"

# ৭. ম্যাক্রো লজিক
def get_macro_insights(vix, spx, oil, gold, yield_10y, dxy):
    insights = []
    
    # DXY
    dxy_status = "NEUTRAL"; dxy_color = "text-yellow-500"; dxy_action = "ডলার ইনডেক্স স্বাভাবিক।"
    if dxy != "N/A":
        if dxy > 105: dxy_status, dxy_color, dxy_action = "BEARISH", "text-red-500", "ডলার শক্তিশালী, ক্রিপ্টোর জন্য খারাপ।"
        elif dxy < 100: dxy_status, dxy_color, dxy_action = "BULLISH", "text-green-500", "ডলার দুর্বল, ক্রিপ্টোর জন্য ভালো।"
    insights.append({"name": "Dollar Index (DXY)", "value": dxy, "status": dxy_status, "color": dxy_color, "action": dxy_action})

    # VIX
    vix_status = "NEUTRAL"; vix_color = "text-yellow-500"; vix_action = "বাজার স্থিতিশীল।"
    if vix != "N/A":
        if vix > 25: vix_status, vix_color, vix_action = "HIGH RISK", "text-red-500", "ভোলাটিলিটি বেশি। নতুন কেনা থেকে বিরত থাকুন।"
        elif vix < 15: vix_status, vix_color, vix_action = "LOW RISK", "text-green-500", "বাজারে ভয় নেই, রিস্ক-অন পরিবেশ।"
    insights.append({"name": "VIX (Volatility)", "value": vix, "status": vix_status, "color": vix_color, "action": vix_action})

    # S&P 500
    insights.append({"name": "S&P 500", "value": spx, "status": "TRACKING", "color": "text-blue-400", "action": "স্টক মার্কেট বাড়লে ক্রিপ্টোও বাড়ে (Risk-on)।"})

    # Oil
    oil_status = "NEUTRAL"; oil_color = "text-yellow-500"; oil_action = "তেলের দাম স্বাভাবিক।"
    if oil != "N/A":
        if oil > 85: oil_status, oil_color, oil_action = "INFLATION RISK", "text-red-500", "তেলের দাম বেশি। CPI বাড়তে পারে (বেয়ারিশ)।"
        elif oil < 70: oil_status, oil_color, oil_action = "DISINFLATION", "text-green-500", "তেলের দাম কম। মুদ্রাস্ফীতি কমার ইঙ্গিত (বুলিশ)।"
    insights.append({"name": "Oil (WTI)", "value": f"${oil}", "status": oil_status, "color": oil_color, "action": oil_action})

    # US 10Y Yield
    yield_status = "NEUTRAL"; yield_color = "text-yellow-500"; yield_action = "ইল্ড স্বাভাবিক।"
    if yield_10y != "N/A":
        if yield_10y > 5.0: yield_status, yield_color, yield_action = "HIGH YIELD", "text-red-500", "ইল্ড ৫% এর উপরে। বাজারে তারল্য সংকুচিত হচ্ছে, ক্রিপ্টোর জন্য নেতিবাচক।"
        elif yield_10y < 4.5: yield_status, yield_color, yield_action = "LOW YIELD", "text-green-500", "ইল্ড ৪.৫% এর নিচে। বাজারে টাকা সহজলভ্য, ক্রিপ্টোর জন্য ইতিবাচক।"
    insights.append({"name": "US 10Y Treasury Yield", "value": f"{yield_10y}%", "status": yield_status, "color": yield_color, "action": yield_action})

    # Gold
    insights.append({"name": "Gold", "value": f"${gold}", "status": "SAFE HAVEN", "color": "text-yellow-600", "action": "সোনার দাম বাড়লে বিনিয়োগকারীরা ঝুঁকি এড়াতে চাইছে।"})
    
    return insights

# ৮. ইভেন্ট অ্যালার্ট
def get_event_alerts(fng, vix):
    today = datetime.date.today()
    events = {
        "US CPI Data": datetime.date(2026, 11, 15), 
        "FOMC Meeting": datetime.date(2026, 12, 12),
        "NFP Jobs Report": datetime.date(2026, 12, 6)
    }
    alerts = []
    for name, date in events.items():
        days_left = (date - today).days
        if 0 <= days_left <= 7:
            if days_left <= 3: alerts.append({"msg": f"🚨 সতর্কতা: {name} মাত্র {days_left} দিন বাকি! বাজার অস্থির হতে পারে।", "color": "bg-red-900/60 border-red-500 text-red-200"})
            else: alerts.append({"msg": f"⚠️ মনে রাখবেন: {name} আগামী {days_left} দিনের মধ্যে।", "color": "bg-yellow-900/60 border-yellow-500 text-yellow-200"})
    if vix != "N/A" and vix > 20: alerts.append({"msg": f"📈 VIX বেড়েছে ({vix})। বাজারে ভোলাটিলিটি বেশি, সতর্ক থাকুন।", "color": "bg-orange-900/60 border-orange-500 text-orange-200"})
    if fng < 20: alerts.append({"msg": f"🩸 বাজারে চরম ভয় ({fng})। DCA করার সুযোগ হতে পারে।", "color": "bg-green-900/60 border-green-500 text-green-200"})
    return alerts

# ৯. হালভিং কাউন্টডাউন
def get_halving_countdown():
    next_halving = datetime.date(2028, 4, 15)
    today = datetime.date.today()
    days_left = (next_halving - today).days
    return f"{days_left} দিন বাকি" if days_left > 0 else "হালভিং সম্পন্ন"

# ডেটা প্রসেসিং
fng_val, fng_class = get_fear_and_greed()
dxy_val = get_yahoo_price("DX-Y.NYB")
oil_val = get_yahoo_price("CL=F")
vix_val = get_yahoo_price("%5EVIX")
spx_val = get_yahoo_price("%5EGSPC")
yield_10y = get_yahoo_price("%5ETNX")
gold_val = get_yahoo_price("GC=F")
btc_val, total_mcap_val, btc_dom_val, eth_dom_val, btc_vol_val, global_vol_val, stablecoin_mcap = get_crypto_global_data()
funding_rate, open_interest = get_funding_and_oi()
mvrv_z = get_mvrv_zscore(btc_val)

cycle_text, cycle_color = get_cycle_stage(fng_val, dxy_val)
macro_insights = get_macro_insights(vix_val, spx_val, oil_val, gold_val, yield_10y, dxy_val)
alerts = get_event_alerts(fng_val, vix_val)
halving_text = get_halving_countdown()
current_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

# Altseason লজিক
if btc_dom_val < 50:
    alt_status = "ALT SEASON"; alt_color = "text-purple-400"
else:
    alt_status = "BTC SEASON"; alt_color = "text-orange-400"

# 200W MA এবং Pi Cycle
ma_200w = 30000 
if btc_val > ma_200w:
    ma_status = "BULLISH"; ma_color = "text-green-500"; ma_action = "দাম 200W MA এর উপরে। লং-টার্ম সাপোর্ট টিকে আছে।"
else:
    ma_status = "BEARISH"; ma_color = "text-red-500"; ma_action = "দাম 200W MA এর নিচে। সতর্ক হোন।"

pi_cycle_status = "SAFE" if btc_val < 90000 else "DANGER"
pi_cycle_color = "text-green-500" if btc_val < 90000 else "text-red-500"
pi_cycle_action = "বাজার এখনো শীর্ষে পৌঁছায়নি। হোল্ড করুন।" if btc_val < 90000 else "বাজার শীর্ষের কাছাকাছি! ধীরে ধীরে লাভ নিন।"

# Weekly Market Outflows (ডেমো)
weekly_outflow = -120.5 
if weekly_outflow < 0:
    outflow_status = "OUTFLOW"; outflow_color = "text-red-500"; outflow_action = "প্রাতিষ্ঠানিক পুঁজি বের হচ্ছে। সতর্ক থাকুন।"
else:
    outflow_status = "INFLOW"; outflow_color = "text-green-500"; outflow_action = "প্রাতিষ্ঠানিক পুঁজি ঢুকছে। বাজার বুলিশ হতে পারে।"

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

# ফান্ডিং রেট লজিক
if funding_rate > 0.01:
    funding_status = "LONGS PAY"; funding_color = "text-red-500"; funding_action = "ফান্ডিং রেট পজিটিভ। লং পজিশন বেশি, বাজারে লোভ। সতর্ক থাকুন।"
elif funding_rate < -0.01:
    funding_status = "SHORTS PAY"; funding_color = "text-green-500"; funding_action = "ফান্ডিং রেট নেগেটিভ। শর্ট পজিশন বেশি, বাজারে ভয়। সুযোগ হতে পারে।"
else:
    funding_status = "NEUTRAL"; funding_color = "text-yellow-500"; funding_action = "ফান্ডিং রেট স্বাভাবিক। বাজারে ভারসাম্য আছে।"

# MVRV লজিক
if mvrv_z != "N/A":
    if mvrv_z > 3.5:
        mvrv_status = "EXTREME HIGH"; mvrv_color = "text-red-500"; mvrv_action = "MVRV非常高। বাজার শীর্ষের কাছাকাছি, সতর্ক থাকুন।"
    elif mvrv_z < 0:
        mvrv_status = "DEEP VALUE"; mvrv_color = "text-green-500"; mvrv_action = "MVRV কম। বাজার কম মূল্যায়িত, DCA করার সুযোগ।"
    else:
        mvrv_status = "NEUTRAL"; mvrv_color = "text-yellow-500"; mvrv_action = "MVRV স্বাভাবিক। বাজার ভারসাম্যে আছে।"
else:
    mvrv_status = "N/A"; mvrv_color = "text-gray-500"; mvrv_action = "ডেটা লোড হয়নি।"

# নতুন ভিজ্যুয়াল ডেটা (সিমুলেটেড)
avg_rsi = 35.48
macd_val = -0.46
long_liq = 1.73
short_liq = 0.25
liq_ratio = (long_liq / (long_liq + short_liq)) * 100
altcoin_index = 42

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

        <!-- Dominance Pie Chart & ETF Bar Chart -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
            <!-- BTC & ETH Dominance -->
            <div class="bg-gray-800 p-4 rounded-lg border border-gray-700">
                <h2 class="text-sm font-semibold text-gray-400 mb-2">Market Dominance</h2>
                <div class="flex items-center justify-between">
                    <div class="w-1/2"><canvas id="dominanceChart"></canvas></div>
                    <div class="w-1/2 pl-4">
                        <div class="flex items-center mb-2"><span class="w-3 h-3 bg-orange-500 rounded-full mr-2"></span><span class="text-sm font-semibold">BTC: {btc_dom_val}%</span></div>
                        <div class="flex items-center"><span class="w-3 h-3 bg-blue-500 rounded-full mr-2"></span><span class="text-sm font-semibold">ETH: {eth_dom_val}%</span></div>
                        <p class="text-xs text-gray-400 mt-3"><span class="text-blue-400 font-bold">করণীয়:</span> BTC ডমিনেন্স বেশি মানে বাজার বিটকয়েন সিজনে আছে।</p>
                    </div>
                </div>
            </div>
            <!-- ETF Tracker Bar Chart (Demo Data) -->
            <div class="bg-gray-800 p-4 rounded-lg border border-gray-700">
                <h2 class="text-sm font-semibold text-gray-400 mb-2">ETF Flows (Last 7 Days)</h2>
                <canvas id="etfChart" height="100"></canvas>
                <p class="text-xs text-gray-400 mt-2"><span class="text-blue-400 font-bold">করণীয়:</span> লাল বার মানে আউটফ্লো। সতর্ক থাকুন।</p>
            </div>
        </div>

        <!-- Advanced Technical Indicators (RSI, MACD, 200W MA, Pi Cycle) -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
            
            <!-- RSI Chart & Action -->
            <div class="bg-gray-800 p-4 rounded-lg border border-gray-700">
                <div class="flex justify-between items-center mb-2">
                    <h2 class="text-sm font-semibold text-gray-400">Average RSI (14)</h2>
                    <span class="text-xs font-bold px-2 py-1 rounded {'bg-green-900 text-green-400' if avg_rsi < 40 else 'bg-red-900 text-red-400'}">{avg_rsi} ({'Weak' if avg_rsi < 40 else 'Strong'})</span>
                </div>
                <div class="h-32"><canvas id="rsiChart"></canvas></div>
                <p class="text-xs text-gray-400 mt-2 bg-gray-900 p-2 rounded"><span class="text-blue-400 font-bold">করণীয়:</span> RSI ৩০ এর নিচে থাকলে বাজার কম মূল্যায়িত (কেনার সুযোগ), ৭০ এর উপরে থাকলে অতিরিক্ত মূল্যায়িত (বিক্রির সুযোগ)।</p>
            </div>

            <!-- MACD Chart & Action -->
            <div class="bg-gray-800 p-4 rounded-lg border border-gray-700">
                <div class="flex justify-between items-center mb-2">
                    <h2 class="text-sm font-semibold text-gray-400">MACD</h2>
                    <span class="text-xs font-bold px-2 py-1 rounded bg-red-900 text-red-400">{macd_val} (Negative)</span>
                </div>
                <div class="h-32"><canvas id="macdChart"></canvas></div>
                <p class="text-xs text-gray-400 mt-2 bg-gray-900 p-2 rounded"><span class="text-blue-400 font-bold">করণীয়:</span> MACD লাইন সিগন্যাল লাইনের উপরে থাকলে বুলিশ (কেনা), নিচে থাকলে বেয়ারিশ (বেচা)।</p>
            </div>

            <!-- 200W MA Chart & Action -->
            <div class="bg-gray-800 p-4 rounded-lg border border-gray-700">
                <div class="flex justify-between items-center mb-2">
                    <h2 class="text-sm font-semibold text-gray-400">200W Moving Average</h2>
                    <span class="text-xs font-bold px-2 py-1 rounded {ma_color.replace('text', 'bg').replace('500', '900')} {ma_color}">{ma_status}</span>
                </div>
                <div class="h-32"><canvas id="ma200Chart"></canvas></div>
                <p class="text-xs text-gray-400 mt-2 bg-gray-900 p-2 rounded"><span class="text-blue-400 font-bold">করণীয়:</span> {ma_action}</p>
            </div>

            <!-- Pi Cycle Top Chart & Action -->
            <div class="bg-gray-800 p-4 rounded-lg border border-gray-700">
                <div class="flex justify-between items-center mb-2">
                    <h2 class="text-sm font-semibold text-gray-400">Pi Cycle Top</h2>
                    <span class="text-xs font-bold px-2 py-1 rounded {pi_cycle_color.replace('text', 'bg').replace('500', '900')} {pi_cycle_color}">{pi_cycle_status}</span>
                </div>
                <div class="h-32"><canvas id="piCycleChart"></canvas></div>
                <p class="text-xs text-gray-400 mt-2 bg-gray-900 p-2 rounded"><span class="text-blue-400 font-bold">করণীয়:</span> {pi_cycle_action}</p>
            </div>

        </div>

        <!-- Macro Insights & Actions (CMC Style Cards with DXY) -->
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
                    <p class="text-xs text-gray-400 mt-2"><span class="text-blue-400 font-bold">করণীয়:</span> {macro['action']}</p>
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
                            <td class="px-3 py-3 text-right font-bold text-orange-400">TRACKING</td>
                        </tr>
                        <tr class="border-b border-gray-700 hover:bg-gray-750">
                            <td class="px-3 py-3 font-medium text-white">ETF Flows</td>
                            <td class="px-3 py-3">
                                <div class="font-semibold text-green-500">$50.5M</div>
                                <div class="text-xs text-gray-400 mt-1 italic">↳ করণীয়: প্রাতিষ্ঠানিক পুঁজি ঢুকছে (Inflow)।</div>
                            </td>
                            <td class="px-3 py-3 text-right font-bold text-green-500">BULLISH</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>

        <!-- Macro News Section (With Stablecoin News) -->
        <div class="bg-gray-800 rounded-lg border border-gray-700 p-4 mb-6">
            <h2 class="text-lg font-bold text-gray-200 mb-4 text-center border-b border-gray-700 pb-2">MACRO & AI NEWS</h2>
            <ul class="space-y-4">
                
                <!-- Stablecoin News (New) -->
                <li class="flex items-start bg-red-900/20 p-3 rounded-lg border border-red-800">
                    <span class="text-red-400 mr-2 text-lg">🩸</span>
                    <div>
                        <p class="font-semibold text-white">Stablecoin Supply Shrinks Fast</p>
                        <p class="text-xs text-gray-300 mb-1">Stablecoin supply has dropped by $17.1B in the last 30 days, the fastest decline since June 2022.</p>
                        <p class="text-xs text-red-300 font-semibold mt-1">করণীয়: বাজারে নগদ টাকা (তারল্য) কমছে। বড় কেনা থেকে বিরত থাকুন এবং ধৈর্য ধরে DCA করুন।</p>
                    </div>
                </li>

                <!-- MSCI News -->
                <li class="flex items-start bg-red-900/20 p-3 rounded-lg border border-red-800">
                    <span class="text-red-400 mr-2 text-lg">🚨</span>
                    <div>
                        <p class="font-semibold text-white">MSCI Index Update</p>
                        <p class="text-xs text-gray-300 mb-1">MSCI is planning to remove Strategy (MicroStrategy) from its US index.</p>
                        <p class="text-xs text-red-300 font-semibold mt-1">করণীয়: প্রাতিষ্ঠানিক ফান্ডগুলো Strategy-এর শেয়ার বিক্রি করতে পারে, যা বিটকয়েনে নেতিবাচক প্রভাব ফেলতে পারে। সতর্ক থাকুন, বড় পজিশন নেওয়ার আগে ভাবুন।</p>
                    </div>
                </li>

                <!-- CPI News -->
                <li class="flex items-start">
                    <span class="text-blue-400 mr-2 mt-1">📌</span>
                    <div>
                        <p class="font-semibold text-white">CPI Data Release</p>
                        <p class="text-xs text-gray-400">Next release: Nov 15. Watch for lower inflation (Bullish for Crypto).</p>
                        <p class="text-xs text-gray-400 mt-1"><span class="text-blue-400 font-bold">করণীয়:</span> সতর্ক থাকুন, ডেটা প্রকাশের সময় বাজারে বড় ওঠানামা হতে পারে।</p>
                    </div>
                </li>

                <!-- FOMC News -->
                <li class="flex items-start">
                    <span class="text-yellow-400 mr-2 mt-1">🏛️</span>
                    <div>
                        <p class="font-semibold text-white">FOMC Meeting</p>
                        <p class="text-xs text-gray-400">Next meeting: Dec 12. Fed's stance on rate cuts is crucial.</p>
                        <p class="text-xs text-gray-400 mt-1"><span class="text-blue-400 font-bold">করণীয়:</span> ফেডের সিদ্ধান্তের আগে নতুন বড় পজিশন নেওয়া থেকে বিরত থাকুন।</p>
                    </div>
                </li>
            </ul>
        </div>
        
        <div class="mt-6 text-center text-xs text-gray-500">
            Built for Long-Term Spot Trading. Keep patience.
        </div>
    </div>

    <!-- Chart.js Scripts -->
    <script>
        // Dominance Pie Chart
        const ctxDom = document.getElementById('dominanceChart').getContext('2d');
        new Chart(ctxDom, {{
            type: 'doughnut',
            data: {{ labels: ['BTC', 'ETH', 'Others'], datasets: [{{ data: [{btc_dom_val}, {eth_dom_val}, {100 - btc_dom_val - eth_dom_val}], backgroundColor: ['#f97316', '#3b82f6', '#4b5563'], borderWidth: 0 }}] }},
            options: {{ cutout: '70%', plugins: {{ legend: {{ display: false }} }} }}
        }});

        // ETF Bar Chart
        const ctxEtf = document.getElementById('etfChart').getContext('2d');
        new Chart(ctxEtf, {{
            type: 'bar',
            data: {{ labels: ['D1', 'D2', 'D3', 'D4', 'D5', 'D6', 'Today'], datasets: [{{ data: [120, -50, 200, -180, 80, 150, -120], backgroundColor: ['#10b981', '#ef4444', '#10b981', '#ef4444', '#10b981', '#10b981', '#ef4444'], borderRadius: 4 }}] }},
            options: {{ plugins: {{ legend: {{ display: false }} }}, scales: {{ x: {{ display: false }}, y: {{ display: false }} }} }}
        }});

        // RSI Chart
        const ctxRsi = document.getElementById('rsiChart').getContext('2d');
        new Chart(ctxRsi, {{
            type: 'line',
            data: {{ labels: ['1','2','3','4','5','6','7'], datasets: [{{ data: [45, 42, 38, 35, 30, 32, {avg_rsi}], borderColor: '#10b981', borderWidth: 2, tension: 0.4, pointRadius: 0 }}] }},
            options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }}, scales: {{ x: {{ display: false }}, y: {{ display: false, min: 0, max: 100 }} }} }}
        }});

        // MACD Chart
        const ctxMacd = document.getElementById('macdChart').getContext('2d');
        new Chart(ctxMacd, {{
            type: 'bar',
            data: {{ labels: ['1','2','3','4','5','6','7'], datasets: [{{ data: [10, 5, -5, -15, -25, -10, {macd_val}], backgroundColor: ['#10b981', '#10b981', '#ef4444', '#ef4444', '#ef4444', '#ef4444', '#ef4444'] }}] }},
            options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }}, scales: {{ x: {{ display: false }}, y: {{ display: false }} }} }}
        }});

        // 200W MA Chart
        const ctxMa = document.getElementById('ma200Chart').getContext('2d');
        new Chart(ctxMa, {{
            type: 'line',
            data: {{ labels: ['1','2','3','4','5','6','7'], datasets: [{{ label: 'Price', data: [25000, 28000, 29000, 31000, 33000, 35000, {btc_val}], borderColor: '#f97316', borderWidth: 2, tension: 0.4, pointRadius: 0 }}, {{ label: '200W MA', data: [{ma_200w}, {ma_200w}, {ma_200w}, {ma_200w}, {ma_200w}, {ma_200w}, {ma_200w}], borderColor: '#3b82f6', borderWidth: 2, borderDash: [5, 5], pointRadius: 0 }}] }},
            options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }}, scales: {{ x: {{ display: false }}, y: {{ display: false }} }} }}
        }});

        // Pi Cycle Chart
        const ctxPi = document.getElementById('piCycleChart').getContext('2d');
        new Chart(ctxPi, {{
            type: 'line',
            data: {{ labels: ['1','2','3','4','5','6','7'], datasets: [{{ data: [40000, 45000, 50000, 55000, 60000, 70000, {btc_val}], borderColor: '#8b5cf6', borderWidth: 2, tension: 0.4, pointRadius: 0 }}] }},
            options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }}, scales: {{ x: {{ display: false }}, y: {{ display: false }} }} }}
        }});
    </script>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as file:
    file.write(html_content)

print("Dashboard updated successfully! index.html created.")
