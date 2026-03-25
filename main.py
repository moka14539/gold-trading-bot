import yfinance as yf
import mplfinance as mpf
import requests
import json
import os
import pandas as pd

# --- 設定 ---
ACCESS_TOKEN = os.getenv('LINE_ACCESS_TOKEN')
USER_ID = os.getenv('LINE_USER_ID')
IMGBB_API_KEY = os.getenv('IMGBB_API_KEY')

def main():
    # 1. データを取得（auto_adjust=Trueで古い形式に合わせる）
    df = yf.download("GC=F", interval="60m", period="5d", auto_adjust=True)
    
    # --- 【最強の型対策】 ---
    # ① 多重階層インデックス（MultiIndex）を解除
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    # ② 必要な列だけを抽出してコピー（余計なメタデータを排除）
    df = df[['Open', 'High', 'Low', 'Close']].copy()
    
    # ③ 強制的にfloat型に変換し、欠損値を削除
    df = df.astype(float).dropna()
    
    if df.empty:
        print("データが空または数値変換に失敗しました")
        return

    # 2. チャート画像を作成
    file_path = "test_chart.png"
    # DateTime型を確定させ、インデックス名を消す（mplfinanceの仕様対策）
    df.index = pd.to_datetime(df.index)
    df.index.name = 'Date'
    
    # ここでエラーが出る場合はデータの中身に問題があるためprintで確認
    print(df.head())
    print(df.dtypes)
    
    mpf.plot(df.tail(50), type='candle', style='charles', savefig=file_path)
    
    # 3. ImgBBにアップロード
    with open(file_path, "rb") as f:
        res = requests.post("https://api.imgbb.com/1/upload", 
                            data={"key": IMGBB_API_KEY, "image": f.read()})
    
    # 4. 結果判定
    res_json = res.json()
    if res.status_code == 200:
        image_url = res_json['data']['url']
        msg = "✅ 三度目の正直！画像テスト成功。設定は完璧です。"
    else:
        image_url = None
        msg = f"❌ アップロード失敗: {res_json.get('error', {}).get('message', '不明なエラー')}"

    # 5. LINEに送信
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {ACCESS_TOKEN}"}
    messages = [{"type": "text", "text": msg}]
    if image_url:
        messages.append({"type": "image", "originalContentUrl": image_url, "previewImageUrl": image_url})
    
    line_res = requests.post(url, headers=headers, data=json.dumps({"to": USER_ID, "messages": messages}))
    print(f"Status: {res.status_code}, LINE Status: {line_res.status_code}")

if __name__ == "__main__":
    main()
