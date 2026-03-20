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

def analyze_gold_ultimate_cfd():
    # 1. データ取得
    gold = yf.download("GC=F", interval="60m", period="7d")
    gold_d = yf.download("GC=F", period="2y")
    tnx = yf.download("^TNX", interval="60m", period="5d")
    usdjpy = yf.download("JPY=X", interval="60m", period="5d")

    messages = []
    score = 0
    now_g = gold['Close'].iloc[-1].item()
    
    # --- A. テクニカル指標計算 ---
    # 200日線 (長期トレンド)
    sma200 = gold_d['Close'].rolling(window=200).mean().iloc[-1].item()
    # ボリンジャーバンド (20, 2sigma)
    ma20 = gold['Close'].rolling(window=20).mean()
    std = gold['Close'].rolling(window=20).std()
    upper, lower = ma20 + (std * 2), ma20 - (std * 2)
    # MACD
    exp1 = gold['Close'].ewm(span=12, adjust=False).mean()
    exp2 = gold['Close'].ewm(span=26, adjust=False).mean()
    macd = exp1 - exp2
    signal = macd.ewm(span=9, adjust=False).mean()
    # RSI
    delta = gold['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    gold['RSI'] = 100 - (100 / (1 + gain/loss))
    rsi_now = gold['RSI'].iloc[-1].item()
    
    # ATR (ボラティリティによる変動幅)
    high_low = gold['High'] - gold['Low']
    high_close = (gold['High'] - gold['Close'].shift()).abs()
    low_close = (gold['Low'] - gold['Close'].shift()).abs()
    atr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1).rolling(14).mean().iloc[-1].item()

    # --- B. 外部要因 (金利・為替) ---
    t_now, t_prev = tnx['Close'].iloc[-1].item(), tnx['Close'].iloc[-2].item()
    u_now, u_prev = usdjpy['Close'].iloc[-1].item(), usdjpy['Close'].iloc[-2].item()

    # --- C. 特殊ロジック (ダイバージェンス & 時間帯) ---
    # ダイバージェンス: 価格は上がってるのにRSIが下がってる(逆も然り)
    div_msg = ""
    if now_g > gold['Close'].iloc[-5].item() and rsi_now < gold['RSI'].iloc[-5].item():
        div_msg = "⚠️上昇の勢い減衰(ダイバージェンス)"
    elif now_g < gold['Close'].iloc[-5].item() and rsi_now > gold['RSI'].iloc[-5].item():
        div_msg = "⚠️下落の勢い減衰(ダイバージェンス)"

    # 時間帯: 欧米市場
    jst = datetime.now(pytz.timezone('Asia/Tokyo'))
    is_active = 16 <= jst.hour <= 24 or 0 <= jst.hour <= 4
    
    # --- D. 8つの独立戦略判定 (OR条件) ---
    # 🟢 BUY
    if now_g > sma200 and rsi_now < 42: messages.append("🟢長期押し目買い"); score += 2
    if now_g > upper.iloc[-2].item(): messages.append("📈BB上限突破(加速)"); score += 1
    if macd.iloc[-2].item() <= signal.iloc[-2].item() and macd.iloc[-1].item() > signal.iloc[-1].item():
        messages.append("🔵MACDゴールデンクロス"); score += 1
    if t_now < t_prev and u_now < u_prev: messages.append("🌍マクロ追い風(金利安・ドル安)"); score += 2

    # 🔴 SELL
    if now_g < sma200 and rsi_now > 58: messages.append("🔴長期戻り売り"); score -= 2
    if now_g < lower.iloc[-2].item(): messages.append("📉BB下限突破(急落)"); score -= 1
    if macd.iloc[-2].item() >= signal.iloc[-2].item() and macd.iloc[-1].item() < signal.iloc[-1].item():
        messages.append("🟠MACDデッドクロス"); score -= 1
    if t_now > t_prev and u_now > u_prev: messages.append("⛔マクロ逆風(金利高・ドル高)"); score -= 2

    # --- E. 最終出力 ---
    if messages:
        direction = "BUY" if score > 0 else "SELL"
        score_abs = abs(score) + (1 if is_active else 0)
        
        # 損切り・利確 (ATRベースで可変)
        sl = now_g - (atr * 2.2) if direction == "BUY" else now_g + (atr * 2.2)
        tp = now_g + (atr * 3.5) if direction == "BUY" else now_g - (atr * 3.5)

        title = f"👑【極・{direction}推奨】" if score_abs >= 4 else f"📢 CFD監視:{direction}"
        msg_text = f"{title}\nスコア:{score_abs} {div_msg}\n\n"
        msg_text += "\n".join([f"・{m}" for m in messages])
        msg_text += f"\n\n現在: ${now_g:.2f}\n🛡️SL: ${sl:.2f}\n🎯TP: ${tp:.2f}\n📊ボラ(ATR): {atr:.2f}"
        
        send_line(msg_text)

if __name__ == "__main__":
    analyze_gold_ultimate_cfd()
