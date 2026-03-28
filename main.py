import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import json
import os
from datetime import datetime, timedelta
import pytz

# --- 設定（環境変数） ---
ACCESS_TOKEN = os.getenv('LINE_ACCESS_TOKEN')
USER_ID = os.getenv('LINE_USER_ID')

# --- 共通機能 ---
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

    score = 0
    messages = []
    now_p = float(gold_1h['Close'].iloc[-1])
    sma200 = gold_d['Close'].rolling(window=200).mean().iloc[-1].item()
    
    # 指標計算 (1h MACD / ATR / RSI)
    exp1 = gold_1h['Close'].ewm(span=12, adjust=False).mean()
    exp2 = gold_1h['Close'].ewm(span=26, adjust=False).mean()
    macd_1h, sig_1h = (exp1 - exp2), (exp1 - exp2).ewm(span=9, adjust=False).mean()
    atr = ta.atr(gold_1h['High'], gold_1h['Low'], gold_1h['Close'], length=14).iloc[-1]
    rsi_15 = ta.rsi(gold_15m['Close'], length=14).iloc[-1]

    # 判定
    t_diff = tnx['Close'].iloc[-1].item() - tnx['Close'].iloc[-2].item()
    dxy_diff = dxy['Close'].iloc[-1].item() - dxy['Close'].iloc[-2].item()

    if now_p > sma200: score += 2; messages.append("🟢長期上昇トレンド")
    if macd_1h.iloc[-1] > sig_1h.iloc[-1]: score += 1
    if t_diff < 0 and dxy_diff < 0: score += 2; messages.append("🌍マクロ追い風")

    if now_p < sma200: score -= 2; messages.append("🔴長期下落トレンド")
    if macd_1h.iloc[-1] < sig_1h.iloc[-1]: score -= 1
    if t_diff > 0 and dxy_diff > 0: score -= 2; messages.append("⛔マクロ逆風")

    total_score = abs(score)
    if total_score >= 3:
        direction = "BUY" if score > 0 else "SELL"
        sl, tp = (now_p - atr*2.5, now_p + atr*4.0) if direction == "BUY" else (now_p + atr*2.5, now_p - atr*4.0)
        title = f"👑【ゴールド・極{direction}】" if total_score >= 5 else f"📢【ゴールド・{direction}】"
        return f"{title}\nスコア:{total_score}\n" + "\n".join([f"・{m}" for m in messages]) + \
               f"\n\n💰価格: ${now_p:.2f}\n🛡️損切: ${sl:.2f}\n🎯利確: ${tp:.2f}\n⏱️RSI: {rsi_15:.1f}"
    return None

# --- 2. 日経225監視ロジック ---
def analyze_nikkei():
    # SQ判定
    def get_sq_alert():
        today = datetime.now()
        first_day = today.replace(day=1)
        first_friday = first_day + timedelta(days=(4 - first_day.weekday() + 7) % 7)
        second_friday = first_friday + timedelta(days=7)
        magic_wed = second_friday - timedelta(days=2)
        if today.date() == second_friday.date(): return "⚠️【SQ本日】乱高下警戒！"
        if today.date() == magic_wed.date(): return "⚠️【魔の水曜日】仕掛け警戒！"
        return ""

    # データ取得
    ext_data = yf.download(["^DJI", "^NDX", "JPY=X"], period="2d", interval="1d", progress=False)
    df = yf.download("^N225", interval="5m", period="2d", progress=False)
    if df.empty: return None

    dow_chg = ((ext_data['Close']['^DJI'].iloc[-1] - ext_data['Close']['^DJI'].iloc[-2]) / ext_data['Close']['^DJI'].iloc[-2]) * 100
    ndx_chg = ((ext_data['Close']['^NDX'].iloc[-1] - ext_data['Close']['^NDX'].iloc[-2]) / ext_data['Close']['^NDX'].iloc[-2]) * 100
    
    # テクニカル
    df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
    bb = ta.bbands(df['Close'], length=20, std=2)
    latest = df.iloc[-1]
    
    strategy = None
    if latest['Close'] > bb['BBU_20_2.0'].iloc[-1] and (dow_chg > 0.1 or ndx_chg > 0.1):
        strategy = "🚀【日経・強気買い】"
    elif latest['Close'] < bb['BBL_20_2.0'].iloc[-1] and (dow_chg < -0.1 or ndx_chg < -0.1):
        strategy = "📉【日経・強気売り】"

    if strategy:
        tp, sl = round(latest['ATR'] * 1.5, 0), round(latest['ATR'] * 0.8, 0)
        sq = get_sq_alert()
        return f"{strategy}\n{sq}\n🇺🇸NYダウ: {dow_chg:+.2f}%\n🇯🇵価格: {latest['Close']:.0f}円\n🎯利確幅: +{tp}円 / 🛡️損切幅: -{sl}円"
    return None

# --- メイン実行 ---
def main():
    is_safe, reason = is_market_safe()
    if not is_safe:
        print(f"市場休止中: {reason}")
        return

    # それぞれ個別に解析
    gold_msg = analyze_gold()
    nikkei_msg = analyze_nikkei()

    # 通知がある場合のみ送信（別々に送ることで通知を分ける）
    if gold_msg: send_line(gold_msg)
    if nikkei_msg: send_line(nikkei_msg)

if __name__ == "__main__":
    main()
