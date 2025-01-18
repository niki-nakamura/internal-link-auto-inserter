
# Google Search Console Data to Spreadsheet  
このリポジトリ（またはドキュメント）は、**Google Search Console (以下 GSC)** に登録されたサイトの「検索クエリ・クリック数・表示回数・CTR・掲載順位」などのデータを、**Google スプレッドシート**へ自動的に抽出・記録する方法をまとめたものです。

## 1. 前提
- すでに**GSC**で対象サイト(ドメイン or URLプレフィックス)を登録し、該当サイトに「閲覧者以上の権限」が付与されている Google アカウントを用意している
- **Google Cloud Platform (GCP)** のアカウントがある
- スプレッドシート上で**Google Apps Script (GAS)** を編集する環境がある

## 2. 全体像
1. **GCP側の設定**  
   - GCPにプロジェクトを作成し、Search Console API を有効にする  
   - OAuth同意画面を作成して、スクリプト実行用のアカウントをテストユーザーに追加  
2. **スプレッドシート側の設定**  
   - Apps Script プロジェクトにて GCP プロジェクト番号を紐付け  
   - `appsscript.json` (マニフェストファイル) のOAuthスコープを設定  
3. **GAS スクリプトの実装**  
   - B列(C列)のキーワード・URLを読み取って Search Console API を呼び出し  
   - D列へ検索結果のパフォーマンス指標を自動で書き込む  
4. **実行 & 認証**  
   - 初回実行時に Google の OAuth 同意フローでアクセス権を承認  
   - D列にデータが反映されるのを確認  

---

## 3. GCP側の設定
### 3-1. プロジェクト作成

1. [Google Cloud Platform (GCP)コンソール](https://console.cloud.google.com/) にアクセス  
2. 画面上部の「プロジェクトを選択」→「新しいプロジェクトを作成」  
3. プロジェクト名はわかりやすいものにし、「作成」  

### 3-2. Search Console APIを有効化

1. 左メニュー「APIとサービス」→「ライブラリ」  
2. 「Search Console API」を検索、クリックして「有効にする」ボタンを押す  

### 3-3. OAuth同意画面の設定

1. 左メニュー「APIとサービス」→「OAuth同意画面」をクリック  
2. 「外部ユーザー」or「内部ユーザー」を選択（個人利用なら「外部」でもOK）  
3. 「アプリ名」「ユーザーサポートメール」を入力  
4. スコープ設定は基本的に追加不要 → 「保存して次へ」  
5. テストユーザーに自分（またはチーム）の Google アカウントを追加 →「保存」  

これでGCP側のOAuth設定が完了です。

---

## 4. スプレッドシート側の設定
### 4-1. Apps Scriptエディタを開く
1. GSCデータを出力したいスプレッドシートを開く  
2. 上部メニュー「拡張機能」→「Apps Script」をクリック  
3. 別タブでApps Scriptエディタが開く  

### 4-2. GCPのプロジェクト紐付け
1. Apps Scriptの左下メニューの「設定(歯車アイコン)」→「Google Cloud プロジェクト」欄  
2. 「プロジェクトを変更」ボタンをクリック  
3. 先ほど作成したGCPプロジェクトの「プロジェクト番号」を入力 →「プロジェクトを設定」  
4. 正しく紐付けされると、設定画面に現在のプロジェクト番号が表示される  

### 4-3. マニフェストファイルの編集
1. 同じ設定画面で「appsscript.json をエディタに表示する」をオン  
2. エディタ左のファイルツリーに「appsscript.json」が表示されるので開く  
3. `"oauthScopes"` を下記のように設定して保存  

```jsonc
{
  "timeZone": "Asia/Tokyo",
  "dependencies": {},
  "exceptionLogging": "STACKDRIVER",
  "oauthScopes": [
    "https://www.googleapis.com/auth/spreadsheets",       // スプレッドシート操作
    "https://www.googleapis.com/auth/webmasters",         // サーチコンソールAPI
    "https://www.googleapis.com/auth/script.external_request" // UrlFetchApp利用
  ],
  "runtimeVersion": "V8"
}
```

---

## 5. GASスクリプトの実装例

以下は、シート上の**B列**に「検索クエリ」、**C列**に「URL」を入力し、**D列**に24時間分のサーチコンソール指標（クリック数/表示数/CTR/平均順位）を出力する例です。  

> **注意**: Search Consoleは当日データが未反映の場合が多く、正確には2〜3日遅れで数値が確定します。ここでは「24時間分」をサンプルとして指定しますが、データが「データなし」になる場合があります。

```js
/**
 * スプレッドシートのB列(キーワード)、C列(URL)を読み取り、
 * 直近24時間を指定してSearch Console APIから検索パフォーマンス情報を取得し、D列に書き込む
 */
function fetchSCDataFor24h() {
  // (1) 対象シートの取得
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName("List_4"); // 実際のシート名に合わせて変更

  // (2) A～C列の最終行を取得し、2行目以降をループ
  const lastRow = sheet.getLastRow();
  for (let row = 2; row <= lastRow; row++) {
    const query = sheet.getRange(row, 2).getValue();   // B列:検索クエリ
    const pageUrl = sheet.getRange(row, 3).getValue(); // C列:URL

    // 空ならスキップ
    if (!query || !pageUrl) continue;

    // (3) 直近24時間の期間を設定 (実際に当日分が反映されていないこともあります)
    const startDate = getDateStrNDaysAgo(1);
    const endDate   = getDateStrNDaysAgo(0);

    // (4) APIリクエスト用のpayload
    const payload = {
      startDate: startDate,
      endDate: endDate,
      dimensions: ["query", "page"],
      dimensionFilterGroups: [{
        filters: [
          {dimension: "query", operator: "equals", expression: query},
          {dimension: "page", operator: "equals", expression: pageUrl}
        ]
      }],
      rowLimit: 100
    };

    // (5) サーチコンソールAPIエンドポイントを設定
    // ドメインプロパティの場合 "sc-domain:example.com" などになる
    // URLプレフィックスの場合は https%3A%2F%2Fexample.com%2F のようにURLエンコードして指定
    const propertyUrlEncoded = encodeURIComponent("https://example.com/");
    const apiUrl = `https://www.googleapis.com/webmasters/v3/sites/${propertyUrlEncoded}/searchAnalytics/query`;

    const options = {
      method: "post",
      contentType: "application/json",
      payload: JSON.stringify(payload),
      muteHttpExceptions: true,
      headers: {
        Authorization: "Bearer " + ScriptApp.getOAuthToken()
      }
    };

    let resultText = "データなし";
    try {
      // (6) API呼び出し
      const response = UrlFetchApp.fetch(apiUrl, options);
      const json = JSON.parse(response.getContentText());
      const rows = json.rows;

      // (7) 結果取得
      if (rows && rows.length > 0) {
        const data = rows[0]; // 配列内の最初のレコードを取得
        const clicks = data.clicks || 0;
        const impressions = data.impressions || 0;
        const ctr = (data.ctr * 100).toFixed(1) + "%";
        const position = data.position.toFixed(1);

        resultText = `クリック:${clicks}, 表示:${impressions}, CTR:${ctr}, 平均順位:${position}`;
      }
    } catch (e) {
      resultText = "APIエラー:" + e;
    }

    // (8) D列に書き込み
    sheet.getRange(row, 4).setValue(resultText);
  }
}

/**
 * 今日からn日前の日付(YYYY-MM-DD)を返す関数
 */
function getDateStrNDaysAgo(n) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  const yyyy = d.getFullYear();
  const mm = ("0" + (d.getMonth() + 1)).slice(-2);
  const dd = ("0" + d.getDate()).slice(-2);
  return `${yyyy}-${mm}-${dd}`;
}
```

---

## 6. 実行と認証フロー
1. スクリプトエディタで `fetchSCDataFor24h` を選択し、実行ボタンをクリック  
2. 初回はOAuthの同意画面が表示される  
   - 「詳細」→「（安全でないページに移動）」などを選択し、同意フローを完了  
3. スクリプトが完了したら、スプレッドシートに戻ってD列を確認  
4. 該当のクエリ・URLに応じて「クリック:〇, 表示:〇, CTR:〇%, 平均順位:〇」という形で出力される  

---

## 7. 注意事項・運用のヒント
- **Search Console のデータ反映遅延**  
  当日分はすぐに反映されず、2～3日遅れて確定する傾向が強いです。「直近24時間」と指定しても「データなし」となるケースがあります。  
- **GASの実行時間制限 (6分)**  
  行数が多いと6分を超える恐れがあります。大量取得の場合は行を分割するなど工夫をしましょう。  
- **定期実行 (トリガー設定)**  
  1日1回や特定の時刻に自動実行したい場合は、スクリプトエディタ左の「トリガー」から時間ベースのトリガーを登録できます。  
- **Search Console への権限**  
  スクリプトを動かすGoogleアカウント (またはサービスアカウント) が、必ず対象サイトで「閲覧者」以上の権限を持っている必要があります。  

---

## 9. まとめ・その他のコツ
- **手順は「GCP設定 → スプレッドシート設定 → コード記述 → 実行」**の順に揃える  
- 画面キャプチャや図を README に添付すると、さらに分かりやすくなる  
- コードの各ステップにコメントを入れる  
- 実行ログ(コンソール)の見方や、APIエラーの典型的な原因なども補足しておくと親切  

---

# License
- This project is licensed under the MIT License. (例)

開発・利用にあたっては、**Google Cloud Platform**や**Google Apps Script**の利用規約・クォータ制限等に注意してください。
