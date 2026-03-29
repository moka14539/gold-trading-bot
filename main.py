import yfinance as yf
import pandas as pd
import requests
import json
import os
from datetime import datetime
import pytz

# 環境変数
ACCESS_TOKEN = os.getenv('LINE_ACCESS_TOKEN')
USER_ID = os.getenv('LINE_USER_ID')

def send_line(text):
    if not text: return
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {ACCESS_TOKEN}"}
    data = {"to": USER_ID, "messages": [{"type": "text", "text": text}]}
    try:
        requests.post(url, headers=headers, data=json.dumps(data), timeout=10)
    except Exception as e:
        print(f"LINE送信エラー: {e}")

def is_market_safe():
    jst = datetime.now(pytz.timezone('Asia/Tokyo'))
    if jst.weekday() >= 5: return False, "土日休止"
    if jst.weekday() == 0 and 6 <= jst.hour < 9: return False, "月曜早朝リスク"
    if 6 <= jst.hour <= 7:
        if jst.hour == 6 or (jst.hour == 7 and jst.minute < 30): return False, "早朝メンテ"
    return True, "取引可能"

def analyze_and_send():
    is_safe, reason = is_market_safe()
    if not is_safe: return

    # 1. データ取得
    gold_1h = yf.download("GC=F", interval="60m", period="7d", progress=False)
    gold_15m = yf.download("GC=F", interval="15m", period="2d", progress=False)
    gold_d = yf.download("GC=F", period="2y", progress=False)
    tnx = yf.download("^TNX", interval="60m", period="5d", progress=False)
    dxy = yf.download("DX-Y.NYB", interval="60m", period="5d", progress=False)

    if gold_1h.empty or gold_15m.empty or dxy.empty: return

    messages = []
    score = 0
    now_p = float(gold_1h['Close'].iloc[-1].item())
    
    # --- 指標計算 ---
    sma200 = gold_d['Close'].rolling(window=200).mean().iloc[-1].item()
    
    # 15分足RSI
    delta_15 = gold_15m['Close'].diff()
    gain = (delta_15.where(delta_15 > 0, 0)).rolling(window=14).mean()
    loss = (-delta_15.where(delta_15 < 0, 0)).rolling(window=14).mean()
    loss = loss.replace(0, 0.00001)
    rsi_15 = (100 - (100 / (1 + (gain / loss)))).iloc[-1].item()
    
    # MACD (1h)
    exp1 = gold_1h['Close'].ewm(span=12, adjust=False).mean()
    exp2 = gold_1h['Close'].ewm(span=26, adjust=False).mean()
    macd_1h = exp1 - exp2
    sig_1h = macd_1h.ewm(span=9, adjust=False).mean()
    
    # ATR
    high_low = gold_1h['High'] - gold_1h['Low']
    high_close = (gold_1h['High'] - gold_1h['Close'].shift()).abs()
    low_close = (gold_1h['Low'] - gold_1h['Close'].shift()).abs()
    atr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1).rolling(14).mean().iloc[-1].item()

    # 外部要因
    t_diff = tnx['Close'].iloc[-1].item() - tnx['Close'].iloc[-2].item()
    dxy_diff = dxy['Close'].iloc[-1].item() - dxy['Close'].iloc[-2].item()

    # --- 判定ロジック ---
    if now_p > sma200:
        messages.append("🟢長期上昇トレンド継続")
        score += 2
    if macd_1h.iloc[-1].item() > sig_1h.iloc[-1].item():
        score += 1
    if t_diff < 0 and dxy_diff < 0:
        messages.append("🌍マクロ追い風（金利安・ドル独歩安）")
        score += 2

    if now_p < sma200:
        messages.append("🔴長期下落トレンド継続")
        score -= 2
    if macd_1h.iloc[-1].item() < sig_1h.iloc[-1].item():
        score -= 1
    if t_diff > 0 and dxy_diff > 0:
        messages.append("⛔マクロ逆風（金利高・ドル高）")
        score -= 2

    # --- 通知実行 ---
    total_score = abs(score)
    if total_score >= 3:
        direction = "BUY" if score > 0 else "SELL"
        sl = now_p - (atr * 2.5) if direction == "BUY" else now_p + (atr * 2.5)
        tp = now_p + (atr * 4.0) if direction == "BUY" else now_p - (atr * 4.0)
        
        title = f"👑【極・{direction}推奨】" if total_score >= 5 else f"📢 【{direction}チャンス】"
        output_text = f"{title}\n信頼スコア:{total_score}\n\n"
        output_text += "\n".join([f"・{m}" for m in messages])
        output_text += f"\n\n💰価格: ${now_p:.2f}\n🛡️損切: ${sl:.2f}\n🎯利確: ${tp:.2f}"
        output_text += f"\n\n⏱️15m RSI: {rsi_15:.1f}"
        output_text += f"\n📊DXY変位: {dxy_diff:+.3f}"
        
        send_line(output_text)

if __name__ == "__main__":
    analyze_and_send()
