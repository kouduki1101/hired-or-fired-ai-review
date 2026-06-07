import Link from "next/link";
import { SmartStartButton } from "@/components/SmartStartButton";

const reviewPatterns = [
  {
    level: "Basic",
    title: "None と空文字を同じものとして扱っていないか",
    category: "境界値・入力検証",
    pattern: "truthy / falsy の混同",
    challenge: "プロフィール表示のNone/空文字レビュー",
    challengeId: "python-truthiness-profile-review",
    suspiciousCode: `def display_name(nickname):
    if not nickname:
        return "Anonymous"
    return nickname`,
    wrongLocation: "`if not nickname:` が None だけでなく空文字も拾っている。",
    whyWrong: [
      "仕様が「nickname が None のときだけ Anonymous」と言っているなら、空文字はユーザーが明示的に入れた値かもしれない。",
      "`not value` は None、空文字、0、空リスト、空辞書をまとめて false 扱いする。",
      "AI生成コードは短く書くために `if not ...` を使いがちだが、業務仕様では区別が必要なことが多い。"
    ],
    correctCode: `def display_name(nickname):
    if nickname is None:
        return "Anonymous"
    return nickname`,
    reflexes: [
      "`if not value` を見たら、None / 空文字 / 0 を同じ扱いにしてよいか確認する。",
      "仕様に「未設定の場合だけ」とあれば、まず `is None` を候補にする。",
      "画面表示・プロフィール・任意入力では、空文字が有効値かを疑う。"
    ]
  },
  {
    level: "Basic",
    title: "境界値ちょうどを落としていないか",
    category: "境界値・入力検証",
    pattern: "以上 / 超過、未満 / 以下の取り違え",
    challenge: "ユーザー登録条件の境界値レビュー",
    challengeId: "user-registration-boundary-review",
    suspiciousCode: `def can_register(user):
    if user.get("age") <= 18:
        return False
    return True`,
    wrongLocation: "`<= 18` により、18歳ちょうども登録不可になっている。",
    whyWrong: [
      "仕様が「18歳以上は登録可能」なら、落としてよいのは 17 歳以下。",
      "`<=` と `<` の1文字差で、ちょうど境界のユーザーだけが誤判定される。",
      "境界値バグはテストが 17 / 19 だけだと見逃されやすい。"
    ],
    correctCode: `def can_register(user):
    if user.get("age") < 18:
        return False
    return True`,
    reflexes: [
      "「以上」「以下」「未満」「超過」が出たら、ちょうどその値を頭で実行する。",
      "年齢、在庫、点数、金額、日数は境界値レビューの最優先対象。",
      "自然言語の仕様と比較演算子を必ず1対1で照合する。"
    ]
  },
  {
    level: "Basic",
    title: "スキップしたいだけなのにループを止めていないか",
    category: "ロジック間違い",
    pattern: "break / continue / return の取り違え",
    challenge: "在庫集計ループのcontinue/breakレビュー",
    challengeId: "python-loop-inventory-review",
    suspiciousCode: `def count_available(items):
    count = 0
    for item in items:
        if item["stock"] == 0:
            break
        count += item["stock"]
    return count`,
    wrongLocation: "`break` により、在庫0の商品を見つけた瞬間に後続の商品をすべて捨てている。",
    whyWrong: [
      "在庫0の商品を集計対象から外したいだけなら、ループ全体を終了してはいけない。",
      "`break` は以降のデータを処理しない。`continue` はその1件だけを飛ばす。",
      "AI生成コードは「除外条件」を書くときに、止めるのか飛ばすのかを曖昧にしやすい。"
    ],
    correctCode: `def count_available(items):
    count = 0
    for item in items:
        if item["stock"] == 0:
            continue
        count += item["stock"]
    return count`,
    reflexes: [
      "`break` を見たら「本当に後続データを捨ててよいか」と問う。",
      "`return` がループ内にあれば、最初の1件だけで終わっていないか疑う。",
      "除外・無視・スキップという仕様なら、まず `continue` を候補にする。"
    ]
  },
  {
    level: "Basic",
    title: "件数・数量・率・固定額を混同していないか",
    category: "ロジック間違い",
    pattern: "集計単位と計算単位のズレ",
    challenge: "注文割引と権限チェックの複合レビュー",
    challengeId: "order-discount-permission-review",
    suspiciousCode: `def apply_discount(total):
    if total >= 10000:
        total = total - 20
    return total`,
    wrongLocation: "`total - 20` が、20%割引ではなく20円引きになっている。",
    whyWrong: [
      "仕様が20%割引なら、金額から固定値20を引くのではなく、0.8倍にする必要がある。",
      "同じ `total` でも、件数、数量、金額、比率のどれを表すかで正しい式が変わる。",
      "単位を読み違えると、コードは動くのに業務結果だけが静かに壊れる。"
    ],
    correctCode: `def apply_discount(total):
    if total >= 10000:
        total = total * 0.8
    return total`,
    reflexes: [
      "割引、税率、手数料、在庫集計では、単位を声に出して読む。",
      "`+= 1` は件数、`+= quantity` は数量。どちらが仕様か確認する。",
      "「%」が仕様にあるのに固定値を足し引きしていたら赤信号。"
    ]
  },
  {
    level: "Intermediate",
    title: "前回呼び出しの状態が残っていないか",
    category: "データフロー不整合",
    pattern: "mutable default argument",
    challenge: "mutable defaultとコピーの参照レビュー",
    challengeId: "python-mutable-default-copy-review",
    suspiciousCode: `def add_tag(name, tags=[]):
    tags.append(name)
    return tags`,
    wrongLocation: "`tags=[]` が関数定義時に一度だけ作られ、呼び出し間で共有される。",
    whyWrong: [
      "Pythonのデフォルト引数は呼び出しごとではなく、関数定義時に評価される。",
      "1回目の `add_tag` で追加した値が、2回目の呼び出しにも残る。",
      "リストや辞書をデフォルト引数にしたコードは、AI生成でも人間のコードでも頻出のレビュー対象。"
    ],
    correctCode: `def add_tag(name, tags=None):
    if tags is None:
        tags = []
    tags.append(name)
    return tags`,
    reflexes: [
      "引数に `=[]` や `={}` を見たら、ほぼ反射で疑う。",
      "呼び出しごとに独立すべき状態なら、デフォルトは `None` にする。",
      "共有したい状態なのか、偶然共有されているだけなのかを切り分ける。"
    ]
  },
  {
    level: "Intermediate",
    title: "コピーしたつもりで元データを壊していないか",
    category: "データフロー不整合",
    pattern: "参照とコピーの混同",
    challenge: "mutable defaultとコピーの参照レビュー",
    challengeId: "python-mutable-default-copy-review",
    suspiciousCode: `def mask_user(user):
    masked = user
    masked["email"] = "***"
    return masked`,
    wrongLocation: "`masked = user` はコピーではなく、同じ辞書への別名を作っている。",
    whyWrong: [
      "`masked` を変更すると、元の `user` も変更される。",
      "マスキング、整形、表示用変換では、元データを破壊してはいけないことが多い。",
      "代入はコピーではない、という基本を忘れると、後続処理で原因不明のデータ汚染が起きる。"
    ],
    correctCode: `def mask_user(user):
    masked = user.copy()
    masked["email"] = "***"
    return masked`,
    reflexes: [
      "`copy = original` を見たら、名前だけコピーしていないか疑う。",
      "入力を破壊してよい関数か、表示用の別オブジェクトを返す関数かを確認する。",
      "ネストがある場合は shallow copy で足りるかも追加で見る。"
    ]
  },
  {
    level: "Intermediate",
    title: "失敗を成功レスポンスに変換していないか",
    category: "要件の読み違い",
    pattern: "例外処理と戻り値契約の破壊",
    challenge: "例外処理と戻り値契約のレビュー",
    challengeId: "python-exception-contract-review",
    suspiciousCode: `def parse_amount(text):
    try:
        return {"ok": True, "value": int(text)}
    except Exception:
        return {"ok": True, "value": 0}`,
    wrongLocation: "`except Exception` の中で `ok: True` を返しており、失敗が成功に見える。",
    whyWrong: [
      "呼び出し側は `ok` を見て成功だと判断するため、入力エラーに気づけない。",
      "`except Exception` は範囲が広く、想定外のバグまで握りつぶす。",
      "エラーを値で返すなら、成功時と失敗時の契約を明確に分ける必要がある。"
    ],
    correctCode: `def parse_amount(text):
    try:
        return {"ok": True, "value": int(text)}
    except ValueError:
        return {"ok": False, "value": None}`,
    reflexes: [
      "`except Exception` を見たら、握りつぶしているバグがないか確認する。",
      "エラー時に `ok=True`、空配列、0などを返していないか疑う。",
      "戻り値契約は、成功と失敗が呼び出し側から区別できる形かを見る。"
    ]
  },
  {
    level: "Intermediate",
    title: "generator を二回使って空にしていないか",
    category: "データフロー不整合",
    pattern: "generator 消費と内包表記条件のズレ",
    challenge: "generator消費とcomprehension条件レビュー",
    challengeId: "python-generator-comprehension-review",
    suspiciousCode: `def summarize_scores(scores):
    passing = (score for score in scores if score >= 70)
    count = len(list(passing))
    passing_avg = sum(passing) / count
    failed = [score for score in scores if score >= 70]
    return passing_avg, failed`,
    wrongLocation: "`len(list(passing))` で generator を消費した後に、同じ `passing` を `sum` している。",
    whyWrong: [
      "generator は一度読み切ると空になるため、`sum(passing)` は期待値にならない。",
      "`failed` の条件も `>= 70` になっており、不合格ではなく合格点を集めている。",
      "内包表記は短く見えるぶん、条件が逆でも流し読みしやすい。"
    ],
    correctCode: `def summarize_scores(scores):
    passing = [score for score in scores if score >= 70]
    count = len(passing)
    passing_avg = None if count == 0 else sum(passing) / count
    failed = [score for score in scores if score < 70]
    return passing_avg, failed`,
    reflexes: [
      "`list(generator)` の後に同じ generator を使っていたら消費済みを疑う。",
      "passing / failed、include / exclude の条件は対になっているか見る。",
      "平均計算では0件時のゼロ除算も同時に確認する。"
    ]
  },
  {
    level: "Advanced",
    title: "非同期APIの結果を await せずに使っていないか",
    category: "データフロー不整合",
    pattern: "await 漏れ",
    challenge: "async/awaitと認可分岐のレビュー",
    challengeId: "python-async-await-review",
    suspiciousCode: `async def load_dashboard(user_id, client):
    profile = client.get_profile(user_id)
    orders = await client.get_orders(user_id)
    if profile["disabled"]:
        raise PermissionError("disabled")
    return {"profile": profile, "orders": orders}`,
    wrongLocation: "`profile = client.get_profile(user_id)` に `await` がなく、profile が実データではなく coroutine になっている。",
    whyWrong: [
      "coroutine object は辞書ではないため、`profile['disabled']` で壊れる。",
      "片方のAPIだけ await されているコードは、レビューで見落としやすい。",
      "認可判定は、非同期取得が完了した実データに対して行う必要がある。"
    ],
    correctCode: `async def load_dashboard(user_id, client):
    profile = await client.get_profile(user_id)
    orders = await client.get_orders(user_id)
    if profile["disabled"]:
        raise PermissionError("disabled")
    return {"profile": profile, "orders": orders}`,
    reflexes: [
      "async関数内で外部API呼び出しを見たら、返り値を使う前に await されているか確認する。",
      "同じ client の片方だけ await されている場合は、もう片方を疑う。",
      "await漏れは型が緩い環境ほどレビューで拾う必要がある。"
    ]
  },
  {
    level: "Advanced",
    title: "キャッシュが認可を迂回していないか",
    category: "権限・セキュリティ",
    pattern: "cache before authorization / 粗すぎる cache key",
    challenge: "キャッシュと認可順序のレビュー",
    challengeId: "python-cache-auth-review",
    suspiciousCode: `CACHE = {}

def get_report(user, report_id, db):
    key = report_id
    if key in CACHE:
        return CACHE[key]
    if not user["can_view_reports"]:
        raise PermissionError("forbidden")
    report = db.load_report(user["tenant_id"], report_id)
    CACHE[key] = report
    return report`,
    wrongLocation: "キャッシュ確認が認可より先にあり、さらに key が `report_id` だけで tenant を分離できていない。",
    whyWrong: [
      "権限のないユーザーでも、キャッシュ済みならレポートを取得できる。",
      "別テナントで同じ report_id がある場合、他社データを返す可能性がある。",
      "高速化のコードは、セキュリティ境界をすり抜ける典型的な場所。"
    ],
    correctCode: `CACHE = {}

def get_report(user, report_id, db):
    if not user["can_view_reports"]:
        raise PermissionError("forbidden")
    key = (user["tenant_id"], report_id)
    if key in CACHE:
        return CACHE[key]
    report = db.load_report(user["tenant_id"], report_id)
    CACHE[key] = report
    return report`,
    reflexes: [
      "キャッシュより前に認可があるかを必ず見る。",
      "マルチテナントでは cache key に tenant_id が含まれているか確認する。",
      "高速化・共通化・メモ化は、権限境界を壊していないか疑う。"
    ]
  }
];

const reviewChecklist = [
  "まずカテゴリを決める。構文ではなく、どの種類の事故かを見る。",
  "怪しい行を1行で言語化する。どこがズレているかを曖昧にしない。",
  "仕様の言葉とコードの演算子・条件・戻り値を照合する。",
  "正解コードを頭に浮かべる。書けなくても、修正の方向は言える状態にする。",
  "最後に、同じ型のバグが他の行にもないか横展開する。"
];

const trainingLoop = [
  {
    title: "1. カテゴリを先に見る",
    body: "境界値、ロジック、データフロー、権限、要件読み違い。まず事故の種類を決める。"
  },
  {
    title: "2. 怪しい箇所を短く指摘する",
    body: "`if not value`、`<= 18`、`break`、`except Exception` のように、レビューで刺す場所を決める。"
  },
  {
    title: "3. 正解を先に見て型にする",
    body: "このページでは正解コードを隠さない。レビュー面接では、瞬間的に修正方針が浮かぶことが目的。"
  }
];

export default function PythonReviewGuidePage() {
  return (
    <main>
      <section className="learn-hero">
        <div>
          <p className="eyebrow">Python Review Pattern Book</p>
          <h1>AIコードを見抜くためのPythonレビュー型帳</h1>
          <p>
            これはPythonを書くための教科書ではありません。AIが生成したコードを見た瞬間に、
            「これはどのカテゴリの不具合か」「どこが間違っているか」「正しい修正は何か」が
            頭に浮かぶようにするための、正解付きレビュー筋トレ表です。
          </p>
          <div className="hero-actions">
            <SmartStartButton>採用面接を受ける</SmartStartButton>
            <Link className="soft-button" href="/problems">
              求人票を見る
            </Link>
            <Link className="soft-button" href="/">
              Homeへ戻る
            </Link>
          </div>
        </div>
        <aside className="learn-checklist">
          <h2>Instant Review Checklist</h2>
          <ul>
            {reviewChecklist.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </aside>
      </section>

      <section className="learn-section">
        <div className="learning-flow">
          {trainingLoop.map((item) => (
            <article className="flow-card" key={item.title}>
              <h2>{item.title}</h2>
              <p>{item.body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="learn-section">
        <div className="section-header">
          <div>
            <h2>レビューで見抜く10の型</h2>
            <p className="muted">
              各カードはゲーム内の選択順に合わせています。カテゴリを決め、失敗パターンを言語化し、
              最後に正解コードを選ぶ。その対応関係をここで先に焼き付けます。
            </p>
          </div>
        </div>
        <div className="pattern-board">
          {reviewPatterns.map((pattern) => (
            <article className="review-pattern-card" key={pattern.title}>
              <div className="job-meta">
                <span className="pill">{pattern.level}</span>
                <span className="pill">{pattern.category}</span>
                <span className="pill">対応問題: {pattern.challenge}</span>
              </div>
              <h3>{pattern.title}</h3>
              <p className="pattern-label">失敗パターン: {pattern.pattern}</p>

              <div className="pattern-grid">
                <div>
                  <strong>怪しいコード</strong>
                  <pre className="pattern-code">{pattern.suspiciousCode}</pre>
                </div>
                <div>
                  <strong>正解として浮かべる修正</strong>
                  <pre className="pattern-code correct">{pattern.correctCode}</pre>
                </div>
              </div>

              <div className="pattern-explain">
                <div className="pattern-answer">
                  <strong>どこが間違っているか</strong>
                  <p>{pattern.wrongLocation}</p>
                </div>
                <div>
                  <strong>なぜ危ないか</strong>
                  <ul>
                    {pattern.whyWrong.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
                <div>
                  <strong>瞬間レビュー反射</strong>
                  <ul>
                    {pattern.reflexes.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              </div>

              <div className="pattern-actions">
                <div>
                  <strong>この型をすぐ試す</strong>
                  <p>{pattern.challenge} で、カテゴリ選択から正解コード選択まで練習できます。</p>
                </div>
                <Link className="primary-button" href={`/play/${pattern.challengeId}`}>
                  この問題を解く
                </Link>
              </div>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
