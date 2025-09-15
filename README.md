ローカルでマイクから15秒程度で文字に起こせる

## なぜこれが必要か？
whisperでは音声ファイルを入力とし、マイクからの入力はサポートしていない。
これはwebsocketからの音声を10秒ごとにwhisperに入力し、結果を得る

## 他の選択肢
[whisperLiveKit](https://github.com/QuentinFuxa/WhisperLiveKit): 数秒でマイクから文字に起こせる

### 機能
- websocketで音声を受け取るapiを提供する

## 使い方
### python
インストール
pythonとffmpegがインストールされていることを前提にする。
``` bash
git clone (this repo)
cd (repo)
python -m venv .venv
source .venv/bin/activate
pip install -r requirements_lock.txt
```
実行
``` bash
source .venv/bin/activate
python python server.py --model turbo --port 9000
```
### dockerで使用する
インストール
``` bash
git clone (this repo)
cd (repo)
docker run -t whisper_batchstream .
```
実行
``` bash
# nvidia gpuがあれば
docker run -d --name whisper_batchstream --gpus all -p 9000 whisper_batchstream
# cpuで処理するなら
docker run -d --name whisper_batchstream -p 9000 whisper_batchstream
```
停止
``` bash
docker stop whisper_batchstream
```

## マイクの音声をwebsocketに流したい
post_sound_rsを使う。詳細はpost_sound_rsを参照
## プログラムの音声をwebsocketに流したい

## Requirements
- nvidia gpuがあれば高速化する。
- dockerかpython
- linuxで動作させていますが、linux固有の機能は使っていません。windowsでも動作するはずです。

## コントリビュート
改善する予定はありません

## ライセンス
MIT LICENSE
このプロジェクトには他からコピーしたソースコードが含まれています。
コピーしたソースコードのライセンスはNOTICEファイルに記述しています。

