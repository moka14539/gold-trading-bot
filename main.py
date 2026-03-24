import yfinance as yf
import pandas as pd
import mplfinance as mpf
import requests
import json
import os
from datetime import datetime
import pytz

# --- 設定 ---
ACCESS_TOKEN = os.getenv('LINE_ACCESS_TOKEN')
USER_ID = os.getenv('LINE_USER_ID')
IMGBB_API_KEY = os.getenv('IMGBB_API_KEY')

def send_line_with_chart(text, image_url=None):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {ACCESS_TOKEN}"}
    messages = [{"type": "text", "text": text}]
    if image_url:
        messages.append({"type": "image", "originalContentUrl": image_url, "previewImageUrl": image_url})
    data = {"to": USER_ID, "messages": messages}
    requests.post(url, headers=headers, data=json.dumps(data))

def create_chart(df_1h, last_upper, last_lower):
    file_path = "chart.png"
    sma200 = df_1h['Close'].rolling(window=200).mean()
    ap = [
        mpf.make_addplot(sma200, color='orange', width=1.5),
        mpf.make_addplot([last_upper]*len(df_1h.tail(50)), color='cyan', linestyle='--', width=0.8),
        mpf.make_addplot([last_lower]*len(df_1h.tail(50)), color='cyan', linestyle='--', width=0.8),
    ]
    mpf.plot(df_1h.tail(50), type='candle', style='charles', savefig=file_path, addplot=ap, volume=False, title="GOLD 1H BB-Standard", tight_layout=True)
    return file_path

def upload_to_imgbb(file_path):
    url = "https://api.imgbb.com/1/upload"
    with open(file_path, "rb") as f:
        payload = {"key": IMGBB_API_KEY, "image": f.read()}
        res = requests.post(url, data=payload)
    return res.json()['data']['url']

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/period, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/period, adjust=False).mean()
    return 100 - (100 / (1 + gain/loss))

def main():
    # 1. データ取得
    gold_1h = yf.download("GC=F", interval="60m", period="10d")
    gold_15m = yf.download("GC=F", interval="15m", period="3d")
    gold_d = yf.download("GC=F", period="2y")
    tnx = yf.download("^TNX", interval="60m", period="5d")
    usdjpy = yf.download("JPY=X", interval="60m", period="5d")

    if gold_1h.empty or gold_15m.empty: return

    # 2. テクニカル指標計算
    now_p = gold_1h['Close'].iloc[-1].item()
    sma200 = gold_d['Close'].rolling(window=200).mean().iloc[-1].item()
    
    # BB (1時間足)
    ma20_1h = gold_1h['Close'].rolling(window=20).mean()
    std_1h = gold_1h['Close'].rolling(window=20).std()
    last_upper = (ma20_1h + (std_1h * 2)).iloc[-1].item()
    last_lower = (ma20_1h - (std_1h * 2)).iloc[-1].item()

    # RSI (1時間足 & 15分足)
    rsi_1h = calculate_rsi(gold_1h['Close']).iloc[-1].item()
    rsi_15m = calculate_rsi(gold_15m['Close']).iloc[-1].item()

    # マクロ要因
    t_diff = tnx['Close'].iloc[-1].item() - tnx['Close'].iloc[-2].item()
    u_diff = usdjpy['Close'].iloc[-1].item() - usdjpy['Close'].iloc[-2].item()

    # 3. 判定ロジック
    messages = []
    score = 0

    # トレンド & マクロ (+1〜+3)
    if now_p > sma200: 
        score += 1
        if t_diff < 0 and u_diff < 0: messages.append("🌍マクロ最強追い風"); score += 2
    elif now_p < sma200:
        score -= 1
        if t_diff > 0 and u_diff > 0: messages.append("⛔マクロ最強逆風"); score -= 2

    # 1時間足の深さ判定 (+2)
    if rsi_1h < 35: messages.append("💎1H足レベルでの大底圏"); score += 2
    elif rsi_1h > 65: messages.append("💎1H足レベルでの天井圏"); score -= 2

    # BBタッチ & 15分足RSIシンクロ判定 (+2〜+4)
    if now_p <= last_lower: # BB下限タッチ
        if rsi_15m < 30:
            messages.append("🔥【鉄板】BB下限 + 15M売られすぎ"); score += 4
        else:
            messages.append("📉 BB下限タッチ（反発待ち）"); score += 2
    elif now_p >= last_upper: # BB上限タッチ
        if rsi_15m > 70:
            messages.append("🔥【鉄板】BB上限 + 15M買われすぎ"); score -= 4
        else:
            messages.append("📈 BB上限タッチ（垂れ待ち）"); score -= 2

    # 4. 通知判定（スコア5以上）
    total_score = abs(score)
    if total_score >= 5:
        try:
            img_path = create_chart(gold_1h, last_upper, last_lower)
            img_url = upload_to_imgbb(img_path)
        except: img_url = None

        direction = "BUY" if score > 0 else "SELL"
        atr = (gold_1h['High'] - gold_1h['Low']).rolling(14).mean().iloc[-1].item()
        sl = now_p - (atr * 2.5) if direction == "BUY" else now_p + (atr * 2.5)
        tp = now_p + (atr * 4.0) if direction == "BUY" else now_p - (atr * 4.0)

        title = "👑 【超・極推奨】" if total_score >= 7 else "🔥 【極推奨】"
        text = f"{title}\nスコア:{total_score}\n\n" + "\n".join([f"・{m}" for m in messages])
        text += f"\n\n💰価格: ${now_p:.2f}\n🛡️損切: ${sl:.2f}\n🎯利確: ${tp:.2f}\n⏱️RSI1H: {rsi_1h:.1f} / 15M: {rsi_15m:.1f}"
        
        send_line_with_chart(text, img_url)

if __name__ == "__main__":
    main()
