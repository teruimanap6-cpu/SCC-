# 出欠ボット

定例の出欠を #出欠管理 のリアクションで集めるボットです。

## できること

- 定例（火・日 18:00〜20:00）の前日 20:00 に出欠確認を投稿（🏫 対面／💻 オンライン／❌ 欠席）
- 1人1つのリアクションに自動で整理（別のものを押すと前のリアクションが外れる）
- 開始30分前（17:30）を締切とし、集計を返信で投稿
- 未回答者へのリマインドは `config.py` の `REMIND_TIME` に時刻を入れると有効になります（初期設定はオフ）
- `/attendance`：最新の出欠状況を自分だけに表示
- `/attendance_create`：臨時の出欠確認を作成（メッセージ管理の権限を持つ人のみ）

時刻や選択肢は `config.py` で変更できます。

## セットアップ

### 1. ボットを作る

1. Discord Developer Portal で「New Application」を作成する
2. 「Bot」タブでトークンを発行し、控えておく
3. 同じタブの「Privileged Gateway Intents」で **Server Members Intent** をオンにする

### 2. サーバーに招待する

「OAuth2 → URL Generator」で次を選び、生成されたURLから招待します。

- Scopes：`bot`、`applications.commands`
- Bot Permissions：View Channels、Send Messages、Send Messages in Threads、Read Message History、Add Reactions、Manage Messages

### 3. #出欠管理 の権限

- `@everyone`：メッセージ送信をオフ、リアクションの追加はオン、スレッドでのメッセージ送信はオン
- ボット：メッセージ送信・メッセージの管理をオン

### 4. IDを控える

Discordの「詳細設定 → 開発者モード」をオンにすると、右クリックでIDをコピーできます。

- サーバーID
- #出欠管理 のチャンネルID

### 5. Railway で動かす

1. このフォルダをGitHubのリポジトリにする
2. Railway で「Deploy from GitHub repo」を選ぶ
3. Variables に次の3つを登録する

| 名前 | 値 |
|---|---|
| `DISCORD_TOKEN` | ボットのトークン |
| `GUILD_ID` | サーバーID |
| `ATTENDANCE_CHANNEL_ID` | #出欠管理 のチャンネルID |

起動コマンドは `Procfile` の `python bot.py` が使われます。

## 動作確認

1. `/attendance_create` で、数分後の日時を指定して臨時の出欠確認を作る
2. リアクションを付け替えて、1つだけ残ることを確かめる
3. `/attendance` で集計が表示されることを確かめる

## 注意

- トークンはGitHubに上げず、Railway の Variables にだけ置いてください。
- 休みの日は `config.py` の `SKIP_DATES` に追加して再デプロイします。
- 臨時の出欠確認では、自動集計は行いません。`/attendance` で確認してください。
