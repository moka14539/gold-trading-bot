import yfinance as yf
import pandas as pd
import requests
import json
import os
from datetime import datetime
import pytz

ACCESS_TOKEN = os.getenv('LINE_ACCESS_TOKEN')
USER_ID = os.getenv('LINE_USER_ID')

def send_line(text):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {ACCESS_TOKEN}"}
    data = {"to": USER_ID, "messages": [{"type": "text", "text": text}]}
    requests.post(url, headers=headers, data=json.dumps(data))

def analyze_gold_complete():
    # 1. データ取得
    gold_1h = yf.download("GLD", interval="60m", period="7d")
    gold_d = yf.download("GLD", period="2y")
    tnx = yf.download("^TNX", interval="60m", period="5d")
    usdjpy = yf.download("JPY=X", interval="60m", period="5d")

    messages = []
    score = 0
    now_g = gold_1h['Close'].iloc[-1].item()
    
    # --- 指標計算 ---
    # 200日線 (長期)
    sma200 = gold_d['Close'].rolling(window=200).mean().iloc[-1].item()
    # ボリバン
    ma20 = gold_1h['Close'].rolling(window=20).mean()
    std = gold_1h['Close'].rolling(window=20).std()
    upper, lower = ma20 + (std * 2), ma20 - (std * 2)
    # MACD
    exp1 = gold_1h['Close'].ewm(span=12, adjust=False).mean()
    exp2 = gold_1h['Close'].ewm(span=26, adjust=False).mean()
    macd = exp1 - exp2
    signal = macd.ewm(span=9, adjust=False).mean()
    # RSI
    delta = gold_1h['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rsi = (100 - (100 / (1 + gain/loss))).iloc[-1].item()

    # 外部要因
    t_now, t_prev = tnx['Close'].iloc[-1].item(), tnx['Close'].iloc[-2].item()
    u_now, u_prev = usdjpy['Close'].iloc[-1].item(), usdjpy['Close'].iloc[-2].item()

    # --- 時間帯判定 (日本時間) ---
    jst = datetime.now(pytz.timezone('Asia/Tokyo'))
    is_active_time = 16 <= jst.hour <= 24 or 0 <= jst.hour <= 2 # ロンドン・NY時間
    time_bonus = 1 if is_active_time else 0

    # --- 🟢 BUY戦略 (4つ) ---
    if now_g > sma200: # 長期上昇中
        if rsi < 40: messages.append("🟢【長期押し目】200日線上でのRSI低迷。絶好の買い場。"); score += 2
    if now_g > upper.iloc[-2].item(): messages.append("📈【BBブレイク】上昇の勢い加速。"); score += 1
    if macd.iloc[-2].item() <= signal.iloc[-2].item() and macd.iloc[-1].item() > signal.iloc[-1].item():
        messages.append("🔵【MACDクロス】ゴールデンクロス。"); score += 1
    if t_now < t_prev and u_now < u_prev: messages.append("🌍【マクロ追い風】金利低下＆ドル安。"); score += 2

    # --- 🔴 SELL戦略 (4つ) ---
    if now_g < sma200: # 長期下落中
        if rsi > 65: messages.append("🔴【長期戻り売り】200日線下でのRSI過熱。"); score -= 2
    if now_g < lower.iloc[-2].item(): messages.append("📉【BB下放れ】下落の勢い加速。"); score -= 1
    if macd.iloc[-2].item() >= signal.iloc[-2].item() and macd.iloc[-1].item() < signal.iloc[-1].item():
        messages.append("🟠【MACDクロス】デッドクロス。"); score -= 1
    if t_now > t_prev and u_now > u_prev: messages.append("⛔【マクロ逆風】金利上昇＆ドル高。"); score -= 2

    # --- 判定と損切り計算 ---
    if messages:
        score += (time_bonus if score > 0 else -time_bonus) # 活発な時間はスコア加算
        total_score = abs(score)
        direction = "BUY" if score > 0 else "SELL"
        
        # 損切り目安 (直近のボラティリティから算出)
        sl_range = std.iloc[-1].item() * 1.5
        sl_price = now_g - sl_range if direction == "BUY" else now_g + sl_range

        title = f"🔥【全力{direction}推奨】" if total_score >= 4 else f"📢 ゴールド{direction}報告"
        output = f"{title}\n時別: {'欧米市場(活発) ✅' if is_active_time else '東京市場(静穏)'}\n\n"
        output += "\n---\n".join(messages)
        output += f"\n\n💰現在価格: ${now_g:.2f}"
        output += f"\n🛡️損切り目安: ${sl_price:.2f}"
        output += f"\n📊判定強度: {total_score}段階"
        send_line(output)

if __name__ == "__main__":
    analyze_gold_complete()
