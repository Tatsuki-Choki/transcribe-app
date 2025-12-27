# 文字起こしWebアプリ

動画・音声ファイルから高速に日本語文字起こしを行うWebアプリケーションです。

## 機能

- **URL入力**: YouTube, Vimeo, その他多数の動画サイトに対応
- **ファイルアップロード**: 動画ファイル（mp4, mov等）、音声ファイル（mp3, wav等）を直接アップロード
- **API選択**: Groq Whisper（高速）または OpenAI Whisper
- **タイムスタンプ**: オプションでタイムスタンプ付き出力
- **リアルタイム進捗表示**: ダウンロード・文字起こしの進捗をリアルタイムで表示
- **結果操作**: クリップボードコピー、テキストファイルダウンロード

## 必要環境

- Python 3.8+
- ffmpeg
- yt-dlp

### インストール

```bash
# ffmpeg (macOS)
brew install ffmpeg

# yt-dlp
pip install yt-dlp

# Flask
pip install flask requests
```

## 使い方

### 1. アプリ起動

```bash
cd transcribe-app
python3 app.py
```

### 2. ブラウザでアクセス

http://localhost:5000 を開く

### 3. 文字起こし

1. URLを入力 または ファイルをアップロード
2. APIプロバイダーを選択（Groq推奨）
3. APIキーを入力
4. 「文字起こし開始」をクリック

## APIキーの取得

- **Groq**: https://console.groq.com/keys
- **OpenAI**: https://platform.openai.com/api-keys

## 対応サイト

yt-dlpがサポートする1000以上のサイトに対応:
- YouTube
- Vimeo（プライベート動画含む）
- Twitter/X
- その他多数

## ファイル構成

```
transcribe-app/
├── app.py              # Flaskアプリ本体
├── templates/
│   └── index.html      # フロントエンドUI
├── scripts/
│   ├── transcribe.py   # 文字起こしスクリプト
│   ├── download_audio.py   # yt-dlpラッパー
│   └── download_vimeo.py   # Vimeo HLSダウンローダー
└── uploads/            # アップロードファイル一時保存
```

## 制限事項

- Whisper APIの25MBファイルサイズ制限は自動分割で対応
- 長時間動画（2時間以上）も処理可能

## ライセンス

MIT
