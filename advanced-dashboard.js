
/* =========================================================
   ADVANCED CRYPTO INTELLIGENCE DASHBOARD
   Bangla UI | Spot Portfolio | Market Radar
   ========================================================= */

(() => {
  "use strict";

  if (document.getElementById("advancedCryptoDashboard")) {
    return;
  }

  const style = document.createElement("style");

  style.textContent = `
    #advancedCryptoDashboard {
      margin-top: 30px;
      color: #e8eef7;
    }

    #advancedCryptoDashboard .adv-title {
      margin: 25px 0 13px;
      padding-left: 11px;
      border-left: 3px solid #f4c65e;
      font-size: 17px;
      font-weight: 800;
    }

    #advancedCryptoDashboard .adv-grid {
      display: grid;
      grid-template-columns: repeat(
        auto-fit,
        minmax(190px, 1fr)
      );
      gap: 12px;
    }

    #advancedCryptoDashboard .adv-card {
      background: #101927;
      border: 1px solid #233248;
      border-radius: 11px;
      padding: 15px;
      min-width: 0;
    }

    #advancedCryptoDashboard .adv-label {
      color: #8d9bb0;
      font-size: 12px;
      margin-bottom: 10px;
    }

    #advancedCryptoDashboard .adv-value {
      font-size: 19px;
      font-weight: 800;
      overflow-wrap: anywhere;
    }

    #advancedCryptoDashboard .adv-note {
      color: #8d9bb0;
      font-size: 11px;
      line-height: 1.6;
      margin-top: 8px;
    }

    #advancedCryptoDashboard .adv-table-wrap {
      overflow-x: auto;
      background: #101927;
      border: 1px solid #233248;
      border-radius: 10px;
    }

    #advancedCryptoDashboard table {
      width: 100%;
      min-width: 510px;
      border-collapse: collapse;
      font-size: 12px;
    }

    #advancedCryptoDashboard th,
    #advancedCryptoDashboard td {
      padding: 10px;
      border-bottom: 1px solid #233248;
      text-align: left;
    }

    #advancedCryptoDashboard th {
      color: #8d9bb0;
    }

    #advancedCryptoDashboard .adv-form {
      display: grid;
      grid-template-columns: repeat(
        auto-fit,
        minmax(130px, 1fr)
      );
      gap: 9px;
    }

    #advancedCryptoDashboard input {
      width: 100%;
      padding: 10px;
      background: #080d16;
      border: 1px solid #34445b;
      border-radius: 7px;
      color: #e8eef7;
    }

    #advancedCryptoDashboard button {
      margin-top: 10px;
      padding: 10px 14px;
      background: #263b55;
      color: white;
      border: 1px solid #415875;
      border-radius: 7px;
      cursor: pointer;
    }

    #advancedCryptoDashboard .adv-pill {
      display: inline-block;
      padding: 4px 7px;
      background: #1b2c43;
      border-radius: 5px;
      color: #f4c65e;
      font-size: 10px;
    }
  `;

  document.head.appendChild(style);

  const root = document.createElement("section");
  root.id = "advancedCryptoDashboard";

  root.innerHTML = `
    <div class="adv-title">
      উন্নত Derivatives ও Institutional Radar
    </div>

    <div class="adv-grid">
      <div class="adv-card">
        <div class="adv-label">BTC Funding Rate</div>
        <div class="adv-value" id="advBtcFunding">লোড হচ্ছে...</div>
        <div class="adv-note">প্রতি ৮ ঘণ্টার হার</div>
      </div>

      <div class="adv-card">
        <div class="adv-label">BTC Open Interest</div>
        <div class="adv-value" id="advBtcOI">লোড হচ্ছে...</div>
        <div class="adv-note">কন্ট্রাক্ট সংখ্যা</div>
      </div>

      <div class="adv-card">
        <div class="adv-label">BTC Futures Basis</div>
        <div class="adv-value" id="advBtcBasis">লোড হচ্ছে...</div>
        <div class="adv-note">Mark Price বনাম Index Price</div>
      </div>

      <div class="adv-card">
        <div class="adv-label">ETH Funding Rate</div>
        <div class="adv-value" id="advEthFunding">লোড হচ্ছে...</div>
      </div>

      <div class="adv-card">
        <div class="adv-label">ETH Open Interest</div>
        <div class="adv-value" id="advEthOI">লোড হচ্ছে...</div>
      </div>

      <div class="adv-card">
        <div class="adv-label">ETH Futures Basis</div>
        <div class="adv-value" id="advEthBasis">লোড হচ্ছে...</div>
      </div>

      <div class="adv-card">
        <div class="adv-label">BTC/ETH ETF Flow</div>
        <div class="adv-value" id="advETF">তথ্য পাওয়া যায়নি</div>
        <div class="adv-note">যাচাইকৃত ETF ডেটা-সোর্স প্রয়োজন</div>
      </div>

      <div class="adv-card">
        <div class="adv-label">Liquidation Heatmap</div>
        <div class="adv-value" id="advLiquidation">তথ্য পাওয়া যায়নি</div>
        <div class="adv-note">আলাদা ডেটা-সোর্স প্রয়োজন</div>
      </div>
    </div>

    <div class="adv-title">On-chain Intelligence</div>

    <div class="adv-grid">
      <div class="adv-card">
        <div class="adv-label">MVRV Z-Score</div>
        <div class="adv-value" id="advMVRV">তথ্য পাওয়া যায়নি</div>
        <div class="adv-note">On-chain provider প্রয়োজন</div>
      </div>

      <div class="adv-card">
        <div class="adv-label">NUPL</div>
        <div class="adv-value" id="advNUPL">তথ্য পাওয়া যায়নি</div>
        <div class="adv-note">On-chain provider প্রয়োজন</div>
      </div>

      <div class="adv-card">
        <div class="adv-label">Exchange Netflow</div>
        <div class="adv-value" id="advExchangeFlow">তথ্য পাওয়া যায়নি</div>
      </div>

      <div class="adv-card">
        <div class="adv-label">Whale Activity</div>
        <div class="adv-value" id="advWhales">তথ্য পাওয়া যায়নি</div>
      </div>
    </div>

    <div class="adv-title">Market Breadth ও Volume Radar</div>

    <div class="adv-grid">
      <div class="adv-card">
        <div class="adv-label">বৃদ্ধি পাওয়া Pair</div>
        <div class="adv-value" id="advAdvancing">--</div>
      </div>

      <div class="adv-card">
        <div class="adv-label">পতন হওয়া Pair</div>
        <div class="adv-value" id="advDeclining">--</div>
      </div>

      <div class="adv-card">
        <div class="adv-label">Advance / Decline Ratio</div>
        <div class="adv-value" id="advRatio">--</div>
      </div>

      <div class="adv-card">
        <div class="adv-label">Volume Leaders</div>
        <div class="adv-value" id="advVolumeCount">--</div>
        <div class="adv-note">গত ২৪ ঘণ্টার ভলিউম</div>
      </div>
    </div>

    <div class="adv-table-wrap" style="margin-top:12px">
      <table>
        <thead>
          <tr>
            <th>Pair</th>
            <th>২৪ ঘণ্টার Volume (USDT)</th>
            <th>পরিবর্তন</th>
            <th>লেনদেন</th>
          </tr>
        </thead>
        <tbody id="advVolumeRows">
          <tr><td colspan="4">ডেটার জন্য অপেক্ষা...</td></tr>
        </tbody>
      </table>
    </div>

    <div class="adv-title">Spot Portfolio Assistant</div>

    <div class="adv-card">
      <div class="adv-note">
        শুধু Spot holdings লিখুন। হিসাব এই ব্রাউজারেই হবে।
        কোনো Wallet Password বা API Key লাগবে না।
      </div>

      <div class="adv-form" style="margin-top:12px">
        <input id="advCoin" placeholder="Coin (যেমন BTC)">
        <input id="advQuantity" type="number" min="0" step="any"
          placeholder="পরিমাণ">
        <input id="advAverage" type="number" min="0" step="any"
          placeholder="গড় ক্রয়মূল্য (USD)">
        <input id="advCurrent" type="number" min="0" step="any"
          placeholder="বর্তমান মূল্য (USD)">
      </div>

      <button id="advCalculate">লাভ/ক্ষতি হিসাব করুন</button>

      <div id="advPortfolioResult"
        class="adv-note" aria-live="polite"></div>
    </div>

    <div class="adv-title">Market Signal Table</div>

    <div class="adv-table-wrap">
      <table>
        <thead>
          <tr>
            <th>সংকেত</th>
            <th>বর্তমান অবস্থা</th>
            <th>ব্যাখ্যা</th>
            <th>নীতি</th>
          </tr>
        </thead>
        <tbody id="advSignalRows">
          <tr><td colspan="4">ডেটার জন্য অপেক্ষা...</td></tr>
        </tbody>
      </table>
    </div>

    <div class="adv-note">
      এই টেবিল বাজারের তথ্য দেখায়; এটি স্বয়ংক্রিয় BUY/SELL অর্ডার নয়।
    </div>

    <div class="adv-note" id="advUpdated"></div>
  `;

  const main = document.querySelector("main");

  if (main) {
    main.appendChild(root);
  } else {
    document.body.appendChild(root);
  }

  const $ = id => document.getElementById(id);

  const unavailable = "তথ্য পাওয়া যায়নি";

  function set(id, value) {
    const element = $(id);
    if (element) element.textContent = value;
  }

  function number(value, digits = 2) {
    if (
      value === null ||
      value === undefined ||
      !Number.isFinite(Number(value))
    ) {
      return unavailable;
    }

    return Number(value).toLocaleString("en-US", {
      maximumFractionDigits: digits
    });
  }

  function showMetric(item, suffix = "") {
    if (!item || item.status !== "OK") {
      return unavailable;
    }

    return number(item.value, 6) + suffix;
  }

  function safeText(value) {
    return String(value ?? "").replace(
      /[&<>"']/g,
      char => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
      })[char]
    );
  }

  function addSignal(name, current, explanation, status) {
    return `
      <tr>
        <td>${safeText(name)}</td>
        <td>${safeText(current)}</td>
        <td>${safeText(explanation)}</td>
        <td><span class="adv-pill">${safeText(status)}</span></td>
      </tr>
    `;
  }

  async function loadAdvancedData() {
    try {
      const response = await fetch(
        "data/advanced_data.json?t=" + Date.now(),
        { cache: "no-store" }
      );

      if (!response.ok) {
        throw new Error("HTTP " + response.status);
      }

      const data = await response.json();

      const btc = data.derivatives?.BTCUSDT || {};
      const eth = data.derivatives?.ETHUSDT || {};

      set(
        "advBtcFunding",
        showMetric(btc.last_funding_rate, "%")
      );

      set(
        "advBtcOI",
        showMetric(btc.open_interest_contracts)
      );

      set(
        "advBtcBasis",
        showMetric(btc.basis_percent, "%")
      );

      set(
        "advEthFunding",
        showMetric(eth.last_funding_rate, "%")
      );

      set(
        "advEthOI",
        showMetric(eth.open_interest_contracts)
      );

      set(
        "advEthBasis",
        showMetric(eth.basis_percent, "%")
      );

      set("advETF", showMetric(data.etf_flows));

      set(
        "advLiquidation",
        showMetric(data.liquidation_heatmap)
      );

      set(
        "advMVRV",
        showMetric(data.on_chain?.mvrv_z_score)
      );

      set(
        "advNUPL",
        showMetric(data.on_chain?.nupl)
      );

      set(
        "advExchangeFlow",
        showMetric(data.on_chain?.exchange_netflow)
      );

      set(
        "advWhales",
        showMetric(data.on_chain?.whale_activity)
      );

      const breadth =
        data.spot_market_activity?.breadth || {};

      set(
        "advAdvancing",
        number(breadth.advancing_pairs, 0)
      );

      set(
        "advDeclining",
        number(breadth.declining_pairs, 0)
      );

      set(
        "advRatio",
        number(breadth.advance_decline_ratio, 3)
      );

      const leaders =
        data.spot_market_activity?.volume_leaders_24h || [];

      set(
        "advVolumeCount",
        leaders.length
          ? leaders.length + "টি Pair"
          : unavailable
      );

      const volumeRows = $("advVolumeRows");

      if (volumeRows) {
        volumeRows.innerHTML = leaders.length
          ? leaders.map(item => `
              <tr>
                <td>${safeText(item.symbol)}</td>
                <td>${number(item.quote_volume_24h, 0)}</td>
                <td>${number(item.change_24h_pct, 2)}%</td>
                <td>${number(item.trades, 0)}</td>
              </tr>
            `).join("")
          : `<tr><td colspan="4">${unavailable}</td></tr>`;
      }

      await loadSignalTable(data);

      set(
        "advUpdated",
        "সর্বশেষ Advanced ডেটা: " +
        (data.generated_at || unavailable)
      );

    } catch (error) {
      const ids = [
        "advBtcFunding",
        "advBtcOI",
        "advBtcBasis",
        "advEthFunding",
        "advEthOI",
        "advEthBasis",
        "advETF",
        "advLiquidation",
        "advMVRV",
        "advNUPL",
        "advExchangeFlow",
        "advWhales",
        "advAdvancing",
        "advDeclining",
        "advRatio",
        "advVolumeCount"
      ];

      ids.forEach(id => set(id, unavailable));

      set(
        "advUpdated",
        "Advanced ডেটা লোড হয়নি: " + error.message
      );
    }
  }

  async function loadSignalTable(data) {
    const rows = [];

    let decision = null;

    try {
      const response = await fetch(
        "data/decision_data.json?t=" + Date.now(),
        { cache: "no-store" }
      );

      if (response.ok) {
        decision = await response.json();
      }
    } catch (_) {
      decision = null;
    }

    const btc = decision?.crypto_market?.btc || {};
    const eth = decision?.crypto_market?.eth || {};

    const btcTrend = btc.trend || unavailable;
    const ethTrend = eth.trend || unavailable;

    rows.push(
      addSignal(
        "BTC দৈনিক প্রবণতা",
        btcTrend,
        "বিদ্যমান Decision Engine-এর বিশ্লেষণ",
        btcTrend === "BULLISH"
          ? "BULLISH"
          : btcTrend === "BEARISH"
            ? "BEARISH"
            : "UNKNOWN"
      )
    );

    rows.push(
      addSignal(
        "ETH দৈনিক প্রবণতা",
        ethTrend,
        "বিদ্যমান Decision Engine-এর বিশ্লেষণ",
        ethTrend === "BULLISH"
          ? "BULLISH"
          : ethTrend === "BEARISH"
            ? "BEARISH"
            : "UNKNOWN"
      )
    );

    const funding =
      data.derivatives?.BTCUSDT?.last_funding_rate;

    const fundingValue =
      funding?.status === "OK"
        ? Number(funding.value)
        : null;

    let fundingStatus = "UNKNOWN";

    if (fundingValue !== null) {
      if (fundingValue > 0.05) {
        fundingStatus = "HIGH POSITIVE";
      } else if (fundingValue < -0.03) {
        fundingStatus = "NEGATIVE";
      } else {
        fundingStatus = "NORMAL";
      }
    }

    rows.push(
      addSignal(
        "BTC Funding",
        showMetric(funding, "%"),
        "Positive funding-এ Long পক্ষ funding দেয়; একা এটি reversal signal নয়।",
        fundingStatus
      )
    );

    rows.push(
      addSignal(
        "BTC Open Interest",
        showMetric(
          data.derivatives?.BTCUSDT?.open_interest_contracts
        ),
        "একটি snapshot; সময়ভিত্তিক পরিবর্তন ছাড়া দিক নিশ্চিত নয়।",
        "CONTEXT ONLY"
      )
    );

    const breadth =
      data.spot_market_activity?.breadth || {};

    rows.push(
      addSignal(
        "Spot Market Breadth",
        number(breadth.advancing_pairs, 0) +
          " বৃদ্ধি / " +
          number(breadth.declining_pairs, 0) +
          " পতন",
        "Binance Spot USDT Pair-এর ২৪ ঘণ্টার পরিবর্তন।",
        "CONTEXT ONLY"
      )
    );

    const table = $("advSignalRows");

    if (table) {
      table.innerHTML = rows.join("");
    }
  }

  $("advCalculate").addEventListener("click", () => {
    const coin = $("advCoin").value.trim().toUpperCase();
    const quantity = Number($("advQuantity").value);
    const average = Number($("advAverage").value);
    const current = Number($("advCurrent").value);

    const output = $("advPortfolioResult");

    if (
      !coin ||
      !Number.isFinite(quantity) ||
      quantity <= 0 ||
      !Number.isFinite(average) ||
      average <= 0 ||
      !Number.isFinite(current) ||
      current <= 0
    ) {
      output.textContent =
        "Coin, পরিমাণ, গড় ক্রয়মূল্য ও বর্তমান মূল্য সঠিকভাবে দিন।";
      return;
    }

    const investment = quantity * average;
    const value = quantity * current;
    const pnl = value - investment;
    const percentage = (pnl / investment) * 100;

    output.textContent =
      coin +
      " | বিনিয়োগ: $" + number(investment) +
      " | বর্তমান মূল্য: $" + number(value) +
      " | লাভ/ক্ষতি: " +
      (pnl >= 0 ? "+" : "-") +
      "$" + number(Math.abs(pnl)) +
      " (" +
      (percentage >= 0 ? "+" : "") +
      number(percentage) +
      "%)";
  });

  loadAdvancedData();

  // প্রতি ৫ মিনিটে নতুন JSON পরীক্ষা করবে।
  // মূল Engine প্রতি ঘণ্টায় ডেটা আপডেট করে।
  setInterval(loadAdvancedData, 5 * 60 * 1000);

})();
