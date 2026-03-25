import yfinance as yf
import mplfinance as mpf
import requests
import json
import os

# --- 設定 ---
ACCESS_TOKEN = os.getenv('LINE_ACCESS_TOKEN')
USER_ID = os.getenv('LINE_USER_ID')
IMGBB_API_KEY = os.getenv('IMGBB_API_KEY')

def main():
    # 1. 適当なデータを取得
    df = yf.download("GC=F", interval="60m", period="5d")
    
    # 2. 強制的にチャート画像を作成
    file_path = "test_chart.png"
    mpf.plot(df.tail(50), type='candle', style='charles', savefig=file_path)
    
    # 3. ImgBBにアップロード
    with open(file_path, "rb") as f:
        res = requests.post("https://api.imgbb.com/1/upload", 
                            data={"key": IMGBB_API_KEY, "image": f.read()})
    
    # 4. 結果を判定
    res_json = res.json()
    if res.status_code == 200:
        image_url = res_json['data']['url']
        msg = "✅ 画像テスト成功！このURLが届いていれば設定は完璧です。"
    else:
        image_url = None
        msg = f"❌ 画像アップロード失敗: {res_json.get('error', {}).get('message', '不明なエラー')}"

    # 5. LINEに送信
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {ACCESS_TOKEN}"}
    messages = [{"type": "text", "text": msg}]
    if image_url:
        messages.append({"type": "image", "originalContentUrl": image_url, "previewImageUrl": image_url})
    
    requests.post(url, headers=headers, data=json.dumps({"to": USER_ID, "messages": messages}))
    print(f"Status: {res.status_code}, Msg: {msg}")

if __name__ == "__main__":
    main()
