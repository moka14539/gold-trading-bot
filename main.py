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

def is_market_safe():
    """取引しても安全な時間帯か判定する"""
    jst = datetime.now(pytz.timezone('Asia/Tokyo'))
    
    # 土日は市場休止
    if jst.weekday() >= 5:
        return False, "市場休止中（土日）"

    # 月曜早朝の不安定な時間
    if jst.weekday() == 0 and 6 <= jst.hour < 9:
        return False, "月曜早朝（リスク回避中）"

    # 毎朝のスプレッド拡大時間
    if 6 <= jst.hour <= 7:
        if jst.hour == 6 or (jst.hour == 7 and jst.minute < 30):
            return False, "早朝メンテナンス（コスト高回避）"

    return True, "取引可能"

def analyze_gold_opportunity():
    is_safe, reason = is_market_safe()
    if not is_safe:
        return

    # データ取得
    gold = yf.download("GC=F", interval="60m", period="7d")
    gold_d = yf.download("GC=F", period="2y")
    tnx = yf.download("^TNX", interval="60m", period="5d")
    usdjpy = yf.download("JPY=X", interval="60m", period="5d")

    if gold.empty: return

    messages = []
    score = 0
    now_g = gold['Close'].iloc[-1].item()
    
    # 指標計算
    sma200 = gold_d['Close'].rolling(window=200).mean().iloc[-1].item()
    ma20 = gold['Close'].rolling(window=20).mean()
    std = gold['Close'].rolling(window=20).std()
    upper, lower = ma20 + (std * 2), ma20 - (std * 2)
    
    exp1 = gold['Close'].ewm(span=12, adjust=False).mean()
    exp2 = gold['Close'].ewm(span=26, adjust=False).mean()
    macd = exp1 - exp2
    signal = macd.ewm(span=9, adjust=False).mean()
    
    delta = gold['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    gold['RSI'] = 100 - (100 / (1 + gain/loss))
    rsi_now = gold['RSI'].iloc[-1].item()
    
    high_low = gold['High'] - gold['Low']
    high_close = (gold['High'] - gold['Close'].shift()).abs()
    low_close = (gold['Low'] - gold['Close'].shift()).abs()
    atr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1).rolling(14).mean().iloc[-1].item()

    t_now, t_prev = tnx['Close'].iloc[-1].item(), tnx['Close'].iloc[-2].item()
    u_now, u_prev = usdjpy['Close'].iloc[-1].item(), usdjpy['Close'].iloc[-2].item()

    jst = datetime.now(pytz.timezone('Asia/Tokyo'))
    is_active_time = 16 <= jst.hour <= 24 or 0 <= jst.hour <= 4

    # 戦略判定
    if now_g > sma200 and rsi_now < 40: messages.append("🟢長期押し目買い候補"); score += 2
    if now_g > upper.iloc[-2].item(): messages.append("📈ボリバン上限突破"); score += 1
    if macd.iloc[-2].item() <= signal.iloc[-2].item() and macd.iloc[-1].item() > signal.iloc[-1].item():
        messages.append("🔵MACDゴールデンクロス"); score += 1
    if t_now < t_prev and u_now < u_prev: messages.append("🌍マクロ追い風（金利安・ドル安）"); score += 2

    if now_g < sma200 and rsi_now > 60: messages.append("🔴長期戻り売り候補"); score -= 2
    if now_g < lower.iloc[-2].item(): messages.append("📉ボリバン下限突破"); score -= 1
    if macd.iloc[-2].item() >= signal.iloc[-2].item() and macd.iloc[-1].item() < signal.iloc[-1].item():
        messages.append("🟠MACDデッドクロス"); score -= 1
    if t_now > t_prev and u_now > u_prev: messages.append("⛔マクロ逆風（金利高・ドル高）"); score -= 2

    # スコア3以上で通知
    total_score = abs(score) + (1 if is_active_time else 0)
    if messages and total_score >= 3:
        direction = "BUY" if score > 0 else "SELL"
        sl = now_g - (atr * 2.5) if direction == "BUY" else now_g + (atr * 2.5)
        tp = now_g + (atr * 4.0) if direction == "BUY" else now_g - (atr * 4.0)
        
        # タイトルの装飾を調整
        if total_score >= 5: title = f"👑【極・{direction}推奨】"
        elif total_score >= 4: title = f"🔥【強・{direction}推奨】"
        else: title = f"📢 【{direction}チャンス】"
        
        output = f"{title}\n信頼スコア:{total_score}\n\n"
        output += "\n".join([f"・{m}" for m in messages])
        output += f"\n\n💰価格: ${now_g:.2f}\n🛡️損切: ${sl:.2f}\n🎯利確: ${tp:.2f}"
        send_line(output)

if __name__ == "__main__":
    analyze_gold_opportunity()
