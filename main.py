import yfinance as yf
import pandas as pd
import requests
import json
import os
from datetime import datetime, timedelta
import pytz

# --- 設定（環境変数） ---
ACCESS_TOKEN = os.getenv('LINE_ACCESS_TOKEN')
USER_ID = os.getenv('LINE_USER_ID')

# --- 共通機能（自作インジケーター） ---
def get_atr(df, length=14):
    high_low = df['High'] - df['Low']
    high_close = (df['High'] - df['Close'].shift()).abs()
    low_close = (df['Low'] - df['Close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=length).mean()

def get_rsi(series, length=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=length).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=length).mean()
    rs = gain / loss.replace(0, 0.00001)
    return 100 - (100 / (1 + rs))

def send_line(text):
    if not text: return
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {ACCESS_TOKEN}"}
    data = {"to": USER_ID, "messages": [{"type": "text", "text": text}]}
    requests.post(url, headers=headers, data=json.dumps(data))

def is_market_safe():
    jst = datetime.now(pytz.timezone('Asia/Tokyo'))
    if jst.weekday() >= 5: return False, "土日休止"
    if jst.weekday() == 0 and 6 <= jst.hour < 9: return False, "月曜早朝リスク"
    if 6 <= jst.hour <= 7:
        if jst.hour == 6 or (jst.hour == 7 and jst.minute < 30): return False, "早朝メンテ"
    return True, "取引可能"

# --- 1. ゴールド監視ロジック ---
def analyze_gold():
    gold_1h = yf.download("GC=F", interval="60m", period="7d", progress=False)
    gold_15m = yf.download("GC=F", interval="15m", period="2d", progress=False)
    gold_d = yf.download("GC=F", period="2y", progress=False)
    tnx = yf.download("^TNX", interval="60m", period="5d", progress=False)
    dxy = yf.download("DX-Y.NYB", interval="60m", period="5d", progress=False)

    if gold_1h.empty or dxy.empty: return None

    score, messages = 0, []
    now_p = float(gold_1h['Close'].iloc[-1].item())
    sma200 = gold_d['Close'].rolling(window=200).mean().iloc[-1].item()
    
    # MACD 
    exp1 = gold_1h['Close'].ewm(span=12, adjust=False).mean()
    exp2 = gold_1h['Close'].ewm(span=26, adjust=False).mean()
    macd, signal = (exp1 - exp2), (exp1 - exp2).ewm(span=9, adjust=False).mean()
    
    atr_val = get_atr(gold_1h).iloc[-1]
    rsi_15 = get_rsi(gold_15m['Close']).iloc[-1]

    t_diff = tnx['Close'].iloc[-1].item() - tnx['Close'].iloc[-2].item()
    dxy_diff = dxy['Close'].iloc[-1].item() - dxy['Close'].iloc[-2].item()

    if now_p > sma200: score += 2; messages.append("🟢長期上昇トレンド")
    if macd.iloc[-1] > signal.iloc[-1]: score += 1
    if t_diff < 0 and dxy_diff < 0: score += 2; messages.append("🌍マクロ追い風")
    if now_p < sma200: score -= 2; messages.append("🔴長期下落トレンド")
    if macd.iloc[-1] < signal.iloc[-1]: score -= 1
    if t_diff > 0 and dxy_diff > 0: score -= 2; messages.append("⛔マクロ逆風")

    total_score = abs(score)
    if total_score >= 3:
        direction = "BUY" if score > 0 else "SELL"
        sl, tp = (now_p - atr_val*2.5, now_p + atr_val*4.0) if direction == "BUY" else (now_p + atr_val*2.5, now_p - atr_val*4.0)
        return f"👑【ゴールド・{direction}】\nスコア:{total_score}\n" + "\n".join([f"・{m}" for m in messages]) + \
               f"\n💰価格: ${now_p:.2f}\n🛡️損切: ${sl:.2f}\n🎯利確: ${tp:.2f}\n⏱️RSI: {rsi_15:.1f}"
    return None

# --- 2. 日経225監視ロジック ---
def analyze_nikkei():
    def get_sq_alert():
        today = datetime.now()
        f_friday = (today.replace(day=1) + timedelta(days=(4 - today.replace(day=1).weekday() + 7) % 7))
        s_friday = f_friday + timedelta(days=7)
        if today.date() == s_friday.date(): return "⚠️【SQ本日】警戒！"
        if today.date() == (s_friday - timedelta(days=2)).date(): return "⚠️【魔の水曜日】警戒！"
        return ""

    ext_data = yf.download(["^DJI", "^NDX"], period="2d", interval="1d", progress=False)
    df = yf.download("^N225", interval="5m", period="2d", progress=False)
    if df.empty: return None

    dow_chg = ((ext_data['Close']['^DJI'].iloc[-1] - ext_data['Close']['^DJI'].iloc[-2]) / ext_data['Close']['^DJI'].iloc[-2]) * 100
    ndx_chg = ((ext_data['Close']['^NDX'].iloc[-1] - ext_data['Close']['^NDX'].iloc[-2]) / ext_data['Close']['^NDX'].iloc[-2]) * 100
    
    # ボリンジャーバンド自作
    ma = df['Close'].rolling(window=20).mean()
    std = df['Close'].rolling(window=20).std()
    u_band, l_band = ma + (std * 2), ma - (std * 2)
    
    latest_c = df['Close'].iloc[-1].item()
    strategy = None
    if latest_c > u_band.iloc[-1] and (dow_chg > 0.1 or ndx_chg > 0.1): strategy = "🚀【日経・強気買い】"
    elif latest_c < l_band.iloc[-1] and (dow_chg < -0.1 or ndx_chg < -0.1): strategy = "📉【日経・強気売り】"

    if strategy:
        atr_n = get_atr(df).iloc[-1]
        return f"{strategy}\n{get_sq_alert()}\n🇺🇸NYダウ: {dow_chg:+.2f}%\n🇯🇵価格: {latest_c:.0f}円\n🎯利確幅: +{round(atr_n*1.5)}円"
    return None

def main():
    safe, reason = is_market_safe()
    if not safe: return
    send_line(analyze_gold())
    send_line(analyze_nikkei())

if __name__ == "__main__":
    main()
