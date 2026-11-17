import requests
import datetime

# --- API Helper Functions ---
def safe_request(url, headers=None):
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            return res.json()
    except:
        pass
    return None

# ১. ফিয়ার অ্যান্ড গ্রিড
def get_fear_and_greed():
    data = safe_request("https://api.alternative.me/fng/")
    if data and 'data' in data:
        return int(data['data'][0]['value']), data['data'][0]['value_classification']
    return 50, "Neutral"

# ২. Yahoo Finance থেকে দাম
def get_yahoo_price(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    data = safe_request(url, headers=headers)
    if data:
        try:
            price = data['chart']['result'][0]['meta']['regularMarketPrice']
            if symbol == "%5ETNX": return round(price / 10, 2)
            return round(price, 2)
        except: pass
    return "N/A"

# ৩. ক্রিপ্টো গ্লোবাল ডেটা
def get_crypto_global_data():
    btc_res = safe_request("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_24hr_vol=true")
    global_res = safe_request("https://api.coingecko.com/api/v3/global")
    if btc_res and global_res:
        try:
            btc_price = btc_res['bitcoin']['usd']
            btc_vol = btc_res['bitcoin']['usd_24h_vol'] / 1e9 
            total_mcap = global_res['data']['total_market_cap']['usd'] / 1e12 
            btc_dominance = global_res['data']['market_cap_percentage']['btc']
            eth_dominance = global_res['data']['market_cap_percentage']['eth']
            global_vol = global_res['data']['total_volume']['usd'] / 1e9
            return btc_price, round(total_mcap, 2), round(btc_dominance, 1), round(eth_dominance, 1), round(btc_vol, 1), round(global_vol, 1)
        except: pass
    return 0, 0.0, 0.0, 0.0, 0.0, 0.0

# ৪. সাইকেল স্টেজ
def get_cycle_stage(fng, dxy):
    if fng < 30 and dxy != "N/A" and dxy < 105:
        return "ACCUMULATION (Buy Zone)", "text-green-500", "বাজার Accumulation জোনে। ধীরে ধীরে কেনার (DCA) জন্য ভালো সময়।"
    elif fng > 70:
        return "MARKUP / DISTRIBUTION (Caution)", "text-red-500", "বাজার Distribution জোনে। সতর্ক থাকুন, লাভ নেওয়ার কথা ভাবুন।"
    else:
        return "NEUTRAL / GRINDING", "text-yellow-500", "বাজার নিরপেক্ষ। রেগুলার প্ল্যান অনুযায়ী হোল্ড করুন।"

# ৫. ম্যাক্রো লজিক
def get_macro_insights(vix, spx, brent_oil, gold, yield_10y, dxy):
    insights = []
    dxy_status = "NEUTRAL"; dxy_color = "text-yellow-500"; dxy_action = "ডলার ইনডেক্স স্বাভাবিক।"
    if dxy != "N/A":
        if dxy > 105: dxy_status, dxy_color, dxy_action = "BEARISH", "text-red-500", "ডলার শক্তিশালী, ক্রিপ্টোর জন্য খারাপ।"
        elif dxy < 100: dxy_status, dxy_color, dxy_action = "BULLISH", "text-green-500", "ডলার দুর্বল, ক্রিপ্টোর জন্য ভালো।"
    insights.append({"name": "Dollar Index (DXY)", "value": dxy, "status": dxy_status, "color": dxy_color, "action": dxy_action, "link": "https://www.tradingview.com/chart/?symbol=TVC%3ADXY"})

    vix_status = "NEUTRAL"; vix_color = "text-yellow-500"; vix_action = "বাজার স্থিতিশীল।"
    if vix != "N/A":
        if vix > 25: vix_status, vix_color, vix_action = "HIGH RISK", "text-red-500", "ভোলাটিলিটি বেশি। নতুন কেনা থেকে বিরত থাকুন।"
        elif vix < 15: vix_status, vix_color, vix_action = "LOW RISK", "text-green-500", "বাজারে ভয় নেই, রিস্ক-অন পরিবেশ।"
    insights.append({"name": "VIX (Volatility)", "value": vix, "status": vix_status, "color": vix_color, "action": vix_action, "link": "https://www.tradingview.com/chart/?symbol=TVC%3AVIX"})

    insights.append({"name": "S&P 500", "value": spx, "status": "TRACKING", "color": "text-blue-400", "action": "স্টক মার্কেট বাড়লে ক্রিপ্টোও বাড়ে (Risk-on)।", "link": "https://www.tradingview.com/chart/?symbol=SP%3ASPX"})

    brent_status = "NEUTRAL"; brent_color = "text-yellow-500"; brent_action = "ব্রেন্ট অয়েলের দাম স্বাভাবিক।"
    if brent_oil != "N/A":
        if brent_oil > 85: brent_status, brent_color, brent_action = "INFLATION RISK", "text-red-500", "ব্রেন্ট অয়েলের দাম বেশি। CPI বাড়তে পারে (বেয়ারিশ)।"
        elif brent_oil < 70: brent_status, brent_color, brent_action = "DISINFLATION", "text-green-500", "ব্রেন্ট অয়েলের দাম কম। মুদ্রাস্ফীতি কমার ইঙ্গিত (বুলিশ)।"
    insights.append({"name": "Brent Crude Oil", "value": f"${brent_oil}", "status": brent_status, "color": brent_color, "action": brent_action, "link": "https://www.tradingview.com/chart/?symbol=TVC%3AUKOIL"})

    yield_status = "NEUTRAL"; yield_color = "text-yellow-500"; yield_action = "ইল্ড স্বাভাবিক।"
    if yield_10y != "N/A":
        if yield_10y > 5.0: yield_status, yield_color, yield_action = "HIGH YIELD", "text-red-500", "ইল্ড ৫% এর উপরে। বাজারে তারল্য সংকুচিত হচ্ছে, ক্রিপ্টোর জন্য নেতিবাচক।"
        elif yield_10y < 4.5: yield_status, yield_color, yield_action = "LOW YIELD", "text-green-500", "ইল্ড ৪.৫% এর নিচে। বাজারে টাকা সহজলভ্য, ক্রিপ্টোর জন্য ইতিবাচক।"
    insights.append({"name": "US 10Y Treasury Yield", "value": f"{yield_10y}%", "status": yield_status, "color": yield_color, "action": yield_action, "link": "https://www.tradingview.com/chart/?symbol=TVC%3AUS10Y"})

    insights.append({"name": "Gold", "value": f"${gold}", "status": "SAFE HAVEN", "color": "text-yellow-600", "action": "সোনার দাম বাড়লে বিনিয়োগকারীরা ঝুঁকি এড়াতে চাইছে।", "link": "https://www.tradingview.com/chart/?symbol=OANDA%3AXAUUSD"})
    return insights

# ৬. ইভেন্ট অ্যালার্ট
def get_event_alerts(fng, vix):
    alerts = []
    if vix != "N/A" and vix > 20: 
        alerts.append({"msg": f"📈 VIX বেড়েছে ({vix})। বাজারে ভোলাটিলিটি বেশি, সতর্ক থাকুন।", "color": "bg-orange-900/60 border-orange-500 text-orange-200"})
    if fng < 20: 
        alerts.append({"msg": f"🩸 বাজারে চরম ভয় ({fng})। DCA করার সুযোগ হতে পারে।", "color": "bg-green-900/60 border-green-500 text-green-200"})
    return alerts

# ৭. হালভিং কাউন্টডাউন
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

cycle_text, cycle_color, cycle_action = get_cycle_stage(fng_val, dxy_val)
macro_insights = get_macro_insights(vix_val, spx_val, brent_oil_val, gold_val, yield_10y, dxy_val)
alerts = get_event_alerts(fng_val, vix_val)
halving_text = get_halving_countdown()
current_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

if btc_dom_val < 50:
    alt_status = "ALT SEASON"; alt_color = "text-purple-400"
else:
    alt_status = "BTC SEASON"; alt_color = "text-orange-400"

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

        <!-- Weekly Outlook & Cycle Stage -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
            <div class="bg-gray-800 p-4 rounded-lg border border-gray-700 text-center">
                <h2 class="text-sm font-semibold text-gray-400 mb-1">Weekly Market Outlook</h2>
                <p class="text-lg font-bold {outlook_color}">{outlook}</p>
                <p class="text-xs text-gray-400 mt-2 bg-gray-900 p-2 rounded"><span class="text-blue-400 font-bold">করণীয়:</span> বাজারের পরিস্থিতি বুঝে আপনার DCA প্ল্যান চালিয়ে যান।</p>
            </div>
            <div class="bg-gray-800 p-4 rounded-lg border border-gray-700 text-center">
                <h2 class="text-sm font-semibold text-gray-400 mb-1">Current Cycle Stage</h2>
                <p class="text-lg font-bold {cycle_color}">{cycle_text}</p>
                <p class="text-xs text-gray-400 mt-2 bg-gray-900 p-2 rounded"><span class="text-blue-400 font-bold">করণীয়:</span> {cycle_action}</p>
            </div>
        </div>

        <!-- BTC Chart & Order Book Link -->
        <div class="grid grid-cols-1 gap-4 mb-6">
            <div class="bg-gray-800 rounded-lg border border-gray-700 p-2">
                <h2 class="text-sm font-semibold text-gray-400 px-2 mb-2">BTC/USDT Live Chart</h2>
                <div class="tradingview-widget-container" style="height:300px; width:100%;">
                    <div id="tradingview_btc"></div>
                    <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
                    <script type="text/javascript">
                    new TradingView.widget({{ "width": "100%", "height": 300, "symbol": "BINANCE:BTCUSDT", "interval": "60", "timezone": "Etc/UTC", "theme": "dark", "style": "1", "locale": "en", "enable_publishing": false, "hide_side_toolbar": true, "container_id": "tradingview_btc" }});
                    </script>
                </div>
            </div>

            <div class="bg-gray-800 rounded-lg border border-gray-700 p-4 text-center">
                <h2 class="text-lg font-bold text-gray-200 mb-2">Live Buying/Selling Pressure (Order Book)</h2>
                <p class="text-sm text-gray-400 mb-4">বাজারে ক্রেতা নাকি বিক্রেতা বেশি, তা লাইভ দেখতে নিচের লিংকে ক্লিক করুন।</p>
                <a href="https://www.coinglass.com/pro/futures/OrderBook" target="_blank" class="inline-block bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-6 rounded-lg transition duration-300">
                    Open Live Order Book Imbalance →
                </a>
            </div>
        </div>

        <!-- Macro Indicators & Links (Replacing live zeros) -->
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
                    <a href="{macro['link']}" target="_blank" class="text-xs text-blue-400 mt-2 block underline font-semibold">TradingView-এ লাইভ চার্ট দেখুন →</a>
                </div>
"""

html_content += f"""
            </div>
        </div>

        <!-- Advanced On-Chain Indicators (Replacing live zeros) -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
            <!-- 200W MA Link -->
            <div class="bg-gray-800 p-4 rounded-lg border border-gray-700 flex flex-col justify-between">
                <div>
                    <h2 class="text-sm font-semibold text-gray-400 mb-2">200W Moving Average</h2>
                    <p class="text-xs text-gray-400 mt-2 bg-gray-900 p-2 rounded"><span class="text-blue-400 font-bold">করণীয়:</span> 200W MA এর উপরে থাকলে বুলিশ, নিচে নামলে সতর্ক হোন।</p>
                </div>
                <a href="https://www.tradingview.com/chart/?symbol=BINANCE%3ABTCUSDT" target="_blank" class="text-sm text-blue-400 mt-3 block underline font-semibold">TradingView-এ 200W MA দেখুন →</a>
            </div>

            <!-- Funding Rate Link -->
            <div class="bg-gray-800 p-4 rounded-lg border border-gray-700 flex flex-col justify-between">
                <div>
                    <h2 class="text-sm font-semibold text-gray-400 mb-2">Funding Rate</h2>
                    <p class="text-xs text-gray-400 mt-2 bg-gray-900 p-2 rounded"><span class="text-blue-400 font-bold">করণীয়:</span> ফান্ডিং রেট পজিটিভ হলে বাজারে লোভ (সতর্ক), নেগেটিভ হলে ভয় (সুযোগ)।</p>
                </div>
                <a href="https://www.coinglass.com/FundingRate" target="_blank" class="text-sm text-blue-400 mt-3 block underline font-semibold">CoinGlass-এ লাইভ দেখুন →</a>
            </div>

            <!-- Open Interest Link -->
            <div class="bg-gray-800 p-4 rounded-lg border border-gray-700 flex flex-col justify-between">
                <div>
                    <h2 class="text-sm font-semibold text-gray-400 mb-2">Open Interest (OI)</h2>
                    <p class="text-xs text-gray-400 mt-2 bg-gray-900 p-2 rounded"><span class="text-blue-400 font-bold">করণীয়:</span> OI বেশি হলে বাজারে অস্থিরতা বাড়তে পারে।</p>
                </div>
                <a href="https://www.coinglass.com/OpenInterest" target="_blank" class="text-sm text-blue-400 mt-3 block underline font-semibold">CoinGlass-এ লাইভ দেখুন →</a>
            </div>

            <!-- Halving Countdown -->
            <div class="bg-gray-800 p-4 rounded-lg border border-gray-700 flex flex-col justify-between">
                <div>
                    <h2 class="text-sm font-semibold text-gray-400 mb-1">Halving Countdown</h2>
                    <p class="text-xl font-bold text-purple-400 mb-2">{halving_text}</p>
                    <p class="text-xs text-gray-400 mt-2 bg-gray-900 p-2 rounded"><span class="text-blue-400 font-bold">করণীয়:</span> হালভিং যত কাছে আসবে, বাজার তত বুলিশ হতে পারে। ধৈর্য ধরে হোল্ড করুন।</p>
                </div>
            </div>
        </div>

        <!-- Long-Term Deep Metrics Section -->
        <div class="bg-gray-800 rounded-lg border border-gray-700 p-4 mb-6">
            <h2 class="text-lg font-bold text-gray-200 mb-4 text-center border-b border-gray-700 pb-2">LONG-TERM DEEP METRICS</h2>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                <!-- MVRV -->
                <div class="bg-gray-900 p-3 rounded-lg border border-gray-700">
                    <div class="flex justify-between items-center mb-1">
                        <span class="text-sm font-semibold text-gray-300">MVRV Z-Score</span>
                        <span class="text-xs font-bold px-2 py-1 rounded bg-gray-700 text-gray-300">LIVE LINK</span>
                    </div>
                    <p class="text-xs text-gray-400 mt-2"><span class="text-blue-400 font-bold">করণীয়:</span> ৩.৫ এর উপরে গেলে সতর্ক হোন, ০ এর নিচে নামলে DCA করুন।</p>
                    <a href="https://www.coinglass.com/pro/onchain/bitcoin-mvrv-market-value-to-realized-value" target="_blank" class="text-xs text-blue-400 mt-2 block underline font-semibold">CoinGlass-এ লাইভ দেখুন →</a>
                </div>
                <!-- SOPR -->
                <div class="bg-gray-900 p-3 rounded-lg border border-gray-700">
                    <div class="flex justify-between items-center mb-1">
                        <span class="text-sm font-semibold text-gray-300">STH SOPR</span>
                        <span class="text-xs font-bold px-2 py-1 rounded bg-gray-700 text-gray-300">LIVE LINK</span>
                    </div>
                    <p class="text-xs text-gray-400 mt-2"><span class="text-blue-400 font-bold">করণীয়:</span> ১.০ এর নিচে থাকলে বাজার কম মূল্যায়িত (DCA সুযোগ)।</p>
                    <a href="https://www.coinglass.com/pro/onchain/bitcoin-sopr" target="_blank" class="text-xs text-blue-400 mt-2 block underline font-semibold">CoinGlass-এ লাইভ দেখুন →</a>
                </div>
                <!-- Netflow -->
                <div class="bg-gray-900 p-3 rounded-lg border border-gray-700">
                    <div class="flex justify-between items-center mb-1">
                        <span class="text-sm font-semibold text-gray-300">Exchange Netflow</span>
                        <span class="text-xs font-bold px-2 py-1 rounded bg-blue-900 text-blue-400">LIVE LINK</span>
                    </div>
                    <p class="text-xs text-gray-400 mt-2"><span class="text-blue-400 font-bold">করণীয়:</span> এক্সচেঞ্জে বিটকয়েন কমলে বুলিশ, বাড়লে সতর্ক হোন।</p>
                    <a href="https://www.coinglass.com/pro/onchain/bitcoin-exchange-netflow" target="_blank" class="text-xs text-blue-400 mt-2 block underline font-semibold">CoinGlass-এ লাইভ দেখুন →</a>
                </div>
            </div>
            
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                <!-- Stablecoin -->
                <div class="bg-gray-900 p-3 rounded-lg border border-gray-700">
                    <div class="flex justify-between items-center mb-1">
                        <span class="text-sm font-semibold text-gray-300">Stablecoin Supply</span>
                        <span class="text-xs font-bold px-2 py-1 rounded bg-gray-700 text-gray-300">LIVE LINK</span>
                    </div>
                    <p class="text-xs text-gray-400 mt-2"><span class="text-blue-400 font-bold">করণীয়:</span> স্টেবলকয়েন বাড়লে (ইনফ্লো) বুলিশ, কমলে সতর্ক হোন।</p>
                    <a href="https://defillama.com/stablecoins" target="_blank" class="text-xs text-blue-400 mt-2 block underline font-semibold">DefiLlama-তে লাইভ দেখুন →</a>
                </div>
                <!-- M2 -->
                <div class="bg-gray-900 p-3 rounded-lg border border-gray-700">
                    <div class="flex justify-between items-center mb-1">
                        <span class="text-sm font-semibold text-gray-300">Global M2 Supply</span>
                        <span class="text-xs font-bold px-2 py-1 rounded bg-gray-700 text-gray-300">LIVE LINK</span>
                    </div>
                    <p class="text-xs text-gray-400 mt-2"><span class="text-blue-400 font-bold">করণীয়:</span> M2 বাড়লে তারল্য বাড়ে, ক্রিপ্টোর জন্য ভালো।</p>
                    <a href="https://www.tradingview.com/chart/?symbol=ECONOMICS%3AGLOBALM2" target="_blank" class="text-xs text-blue-400 mt-2 block underline font-semibold">TradingView-এ দেখুন →</a>
                </div>
                <!-- Liquidation Heatmap -->
                <div class="bg-gray-900 p-3 rounded-lg border border-gray-700">
                    <div class="flex justify-between items-center mb-1">
                        <span class="text-sm font-semibold text-gray-300">Liquidation Heatmap</span>
                        <span class="text-xs font-bold px-2 py-1 rounded bg-purple-900 text-purple-400">LIVE LINK</span>
                    </div>
                    <p class="text-xs text-gray-400 mt-2"><span class="text-blue-400 font-bold">করণীয়:</span> বড় লিকুইডেশন ক্লাস্টার দেখে বোঝা যায় বাজার কোথায় আটকে আছে।</p>
                    <a href="https://www.coinglass.com/pro/futures/LiquidationHeatMap" target="_blank" class="text-xs text-blue-400 mt-2 block underline font-semibold">CoinGlass-এ লাইভ দেখুন →</a>
                </div>
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
                        <p class="text-xs text-gray-400 mt-1"><span class="text-blue-400 font-bold">করণীয়:</span> সতর্ক থাকুন, ডেটা প্রকাশের সময় বাজারে বড় ওঠানামা হতে পারে।</p>
                    </div>
                </li>
            </ul>
        </div>
        
        <div class="mt-6 text-center text-xs text-gray-500">
            Built for Long-Term Spot Trading. Live data only.
        </div>
    </div>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as file:
    file.write(html_content)

print("Dashboard updated successfully with links instead of static zeros.")
