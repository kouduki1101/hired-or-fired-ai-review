import type {
  InterviewChallenge,
  ReviewCategory,
  ReviewChoice,
  ReviewStep,
  ReviewStepKind
} from "@/lib/types";

const categoryLabels: Record<ReviewCategory, string> = {
  spec: "要件の読み違い",
  logic: "ロジック間違い",
  boundary: "境界値・入力検証",
  data_flow: "データフロー不整合",
  security: "権限・セキュリティ"
};

const categoryChoiceTemplates: Array<{
  id: ReviewCategory;
  description: string;
}> = [
  {
    id: "spec",
    description: "仕様の条件や期待値をコードが取り違えている"
  },
  {
    id: "logic",
    description: "分岐、演算、真偽値の扱いが意図と逆になっている"
  },
  {
    id: "boundary",
    description: "0、空、None、ちょうど境界値などの扱いが崩れている"
  },
  {
    id: "data_flow",
    description: "入力から出力までの値の受け渡しや変換がずれている"
  },
  {
    id: "security",
    description: "権限確認や禁止操作の制御が抜けている、または逆になっている"
  }
];

type DomainSeed = {
  key: string;
  label: string;
  role: string;
};

type PatternContext = DomainSeed & {
  functionName: string;
};

type PatternResult = {
  key: string;
  title: string;
  category: ReviewCategory;
  difficulty: 1 | 2 | 3 | 4 | 5;
  pattern: {
    id: string;
    label: string;
    description: string;
  };
  requirements: string[];
  examples: string[];
  constraints: string[];
  code: string;
  startLine: number;
  endLine: number;
  issueTitle: string;
  summary: string;
  explanation: string;
  correctCode: string;
  hints: string[];
  fix: {
    id: string;
    label: string;
    description: string;
    code: string;
  };
};

type PatternDefinition = {
  key: string;
  title: string;
  functionBase: string;
  build: (context: PatternContext) => PatternResult;
};

function categoryStep(correctCategory: ReviewCategory): ReviewStep {
  return {
    kind: "category",
    prompt: "この指摘はどのカテゴリ？",
    choices: categoryChoiceTemplates.map((choice) => ({
      id: choice.id,
      label: categoryLabels[choice.id],
      description: choice.description,
      correct: choice.id === correctCategory
    }))
  };
}

function step(
  kind: Exclude<ReviewStepKind, "category">,
  prompt: string,
  choices: Array<Omit<ReviewChoice, "correct"> & { correct?: boolean }>
): ReviewStep {
  return {
    kind,
    prompt,
    choices: choices.map((choice) => ({ ...choice, correct: choice.correct === true }))
  };
}

function reviewSteps(
  category: ReviewCategory,
  pattern: PatternResult["pattern"],
  fix: PatternResult["fix"]
): ReviewStep[] {
  return [
    categoryStep(category),
    step("pattern", "どんな失敗パターン？", [
      { ...pattern, correct: true },
      {
        id: "distractor_operator",
        label: "演算子だけの取り違え",
        description: "単純な + / - / 比較演算子の取り違え"
      },
      {
        id: "distractor_validation",
        label: "入力検証漏れ",
        description: "入力値の存在確認や範囲確認が足りない"
      },
      {
        id: "distractor_permission",
        label: "権限条件の反転",
        description: "許可・拒否の条件が逆になっている"
      }
    ]),
    step("fix", "正しい修正はどれ？", [
      { ...fix, correct: true },
      {
        id: "fix-noop",
        label: "現状のままにする",
        description: "指摘した不具合が残る"
      },
      {
        id: "fix-broaden",
        label: "条件を広げるだけにする",
        description: "仕様の区別がさらに曖昧になる"
      },
      {
        id: "fix-return-none",
        label: "失敗時はNoneを返す",
        description: "戻り値契約や要件と一致しない"
      }
    ])
  ];
}

function difficultyLabel(difficulty: PatternResult["difficulty"]) {
  if (difficulty === 1) return "Warm-up";
  if (difficulty === 2) return "Basic";
  if (difficulty === 3) return "Practical";
  if (difficulty === 4) return "Advanced";
  return "Boss";
}

function challengeTitle(domain: DomainSeed, pattern: PatternDefinition) {
  const prefix = domain.label;
  const titles: Record<string, string> = {
    "truthy-empty": `${prefix}ラベルの未設定判定レビュー`,
    "inclusive-threshold": `${prefix}スコアの境界値レビュー`,
    "upper-boundary": `${prefix}期限の上限判定レビュー`,
    "wrong-addition": `${prefix}補正値の加算レビュー`,
    "percentage-fixed": `${prefix}金額の割合計算レビュー`,
    "count-vs-quantity": `${prefix}数量の集計レビュー`,
    "break-continue": `${prefix}データの除外条件レビュー`,
    "return-inside-loop": `${prefix}データの全件確認レビュー`,
    "min-max": `${prefix}候補の最高スコア選定レビュー`,
    "sort-direction": `${prefix}候補の優先順位レビュー`,
    "filter-reversed": `${prefix}レコードの有効データ抽出レビュー`,
    "missing-none-validation": `${prefix}連絡先のNone検証レビュー`,
    "negative-validation": `${prefix}金額の負数検証レビュー`,
    "mutable-default": `${prefix}メモの共有状態レビュー`,
    "alias-copy": `${prefix}レコードのマスキングレビュー`,
    "shallow-copy-nested": `${prefix}設定のネストコピー確認`,
    "exception-success": `${prefix}数値変換の失敗扱いレビュー`,
    "broad-exception": `${prefix}必須項目の例外処理レビュー`,
    "generator-reuse": `${prefix}実績の平均計算レビュー`,
    "missing-await": `${prefix}API取得のawaitレビュー`,
    "permission-inverted": `${prefix}操作権限レビュー`,
    "auth-after-cache": `${prefix}キャッシュの認可順序レビュー`,
    "tenant-cache-key": `${prefix}テナント分離レビュー`,
    "date-boundary": `${prefix}締切日の境界値レビュー`,
    "range-off-by-one": `${prefix}日数リストの終端レビュー`,
    "one-based-index": `${prefix}候補番号のindexレビュー`,
    "dedupe-order": `${prefix}IDの重複排除レビュー`,
    "matrix-alias": `${prefix}表データの二次元配列レビュー`,
    "integer-division": `${prefix}完了率の比率計算レビュー`,
    rounding: `${prefix}金額の丸め処理レビュー`,
    "case-sensitive-role": `${prefix}ロール判定の表記ゆれレビュー`,
    "membership-substring": `${prefix}権限名の部分一致レビュー`
  };

  return titles[pattern.key] ?? `${prefix}コードレビュー`;
}

function makeChallenge(domain: DomainSeed, pattern: PatternDefinition): InterviewChallenge {
  const result = pattern.build({
    ...domain,
    functionName: `${domain.key}_${pattern.functionBase}`
  });

  return {
    id: `${domain.key}-${pattern.key}-review`,
    role: domain.role,
    title: challengeTitle(domain, pattern),
    difficultyLabel: difficultyLabel(result.difficulty),
    estimatedMinutes: 5,
    timeLimitSeconds: 300,
    codeLanguage: "python",
    requirements: result.requirements,
    examples: result.examples,
    constraints: result.constraints,
    code: result.code,
    challengeHints: [
      "仕様の言葉とコードの条件を1つずつ対応させてください。",
      "怪しい行を決めたら、カテゴリ、失敗パターン、修正の順に確定してください。",
      "この問題は実装力ではなく、見抜く力を測るレビュー面接です。"
    ],
    issues: [
      {
        id: `${domain.key}-${result.key}-issue`,
        title: result.issueTitle,
        category: result.category,
        pattern: result.pattern.id,
        startLine: result.startLine,
        endLine: result.endLine,
        difficulty: result.difficulty,
        summary: result.summary,
        explanation: result.explanation,
        correctCode: result.correctCode,
        hints: result.hints,
        steps: reviewSteps(result.category, result.pattern, result.fix)
      }
    ]
  };
}

const domains: DomainSeed[] = [
  {
    key: "supply",
    label: "調達",
    role: "Supply Chain Review Candidate"
  },
  {
    key: "billing",
    label: "請求",
    role: "Billing Review Candidate"
  },
  {
    key: "hr",
    label: "人事",
    role: "HR Systems Review Candidate"
  },
  {
    key: "learning",
    label: "学習",
    role: "Learning Platform Review Candidate"
  }
];

const patterns: PatternDefinition[] = [
  {
    key: "truthy-empty",
    title: "None/空文字レビュー",
    functionBase: "normalize_label",
    build: (context) => ({
      key: "truthy-empty",
      title: "のNone/空文字レビュー",
      category: "boundary",
      difficulty: 2,
      pattern: {
        id: "truthy_falsy_confusion",
        label: "truthy/falsyの混同",
        description: "Noneだけを扱うべき条件が空文字や0まで拾っている"
      },
      requirements: [
        "label が None の場合だけ「未設定」を返す",
        "空文字はユーザーが明示した値としてそのまま扱う",
        "None 以外は文字列として返す"
      ],
      examples: [
        `${context.functionName}(None) -> "未設定"`,
        `${context.functionName}("") -> ""`
      ],
      constraints: [
        "None と空文字を同じ扱いにしない",
        "表示用のフォールバック条件を厳密に読む"
      ],
      code: `def ${context.functionName}(label):
    if not label:
        return "未設定"
    return label`,
      startLine: 2,
      endLine: 3,
      issueTitle: "Noneだけでなく空文字まで未設定扱いにしている",
      summary: "`if not label` が None と空文字をまとめて扱っている。",
      explanation:
        "仕様では None の場合だけフォールバックします。空文字まで「未設定」にすると、ユーザー入力を勝手に置き換えます。",
      correctCode: `if label is None:
        return "未設定"`,
      hints: [
        "`not label` は None だけを見ていません。",
        "空文字は仕様上そのまま返す値です。",
        "Noneだけを見るなら `is None` です。"
      ],
      fix: {
        id: "fix-is-none",
        label: "Noneだけを判定する",
        description: "空文字とNoneを分けて扱う",
        code: `if label is None:
        return "未設定"`
      }
    })
  },
  {
    key: "inclusive-threshold",
    title: "境界値以上レビュー",
    functionBase: "is_priority",
    build: (context) => ({
      key: "inclusive-threshold",
      title: "の境界値以上レビュー",
      category: "boundary",
      difficulty: 2,
      pattern: {
        id: "inclusive_threshold_dropped",
        label: "境界値ちょうどの除外",
        description: "以上の条件なのに、ちょうど境界値を落としている"
      },
      requirements: [
        "score が 80 以上なら優先対象にする",
        "score が 79 以下なら通常対象にする",
        "80ちょうどは優先対象である"
      ],
      examples: [
        `${context.functionName}(80) -> True`,
        `${context.functionName}(79) -> False`
      ],
      constraints: [
        "以上と超過を取り違えない",
        "境界値そのものを頭で実行する"
      ],
      code: `def ${context.functionName}(score):
    if score <= 80:
        return False
    return True`,
      startLine: 2,
      endLine: 3,
      issueTitle: "80ちょうどを優先対象から落としている",
      summary: "`<= 80` のため、80点ちょうどが False になる。",
      explanation:
        "仕様は80以上です。落としてよいのは80未満なので、比較演算子が1文字ずれています。",
      correctCode: `if score < 80:
        return False`,
      hints: [
        "80ちょうどを入力したときの戻り値を考えてください。",
        "仕様は80以上です。",
        "`<=` ではなく `<` が必要です。"
      ],
      fix: {
        id: "fix-less-than",
        label: "80未満だけを落とす",
        description: "80ちょうどを優先対象に残す",
        code: `if score < 80:
        return False`
      }
    })
  },
  {
    key: "upper-boundary",
    title: "上限値以内レビュー",
    functionBase: "within_limit",
    build: (context) => ({
      key: "upper-boundary",
      title: "の上限値以内レビュー",
      category: "boundary",
      difficulty: 2,
      pattern: {
        id: "upper_boundary_excluded",
        label: "上限値ちょうどの除外",
        description: "以内の条件なのに、ちょうど上限値を落としている"
      },
      requirements: [
        "days が 30 以下なら許可する",
        "days が 31 以上なら拒否する",
        "30日ちょうどは許可する"
      ],
      examples: [
        `${context.functionName}(30) -> True`,
        `${context.functionName}(31) -> False`
      ],
      constraints: [
        "以内は上限値を含む",
        "境界の1つ上だけを拒否する"
      ],
      code: `def ${context.functionName}(days):
    if days >= 30:
        return False
    return True`,
      startLine: 2,
      endLine: 3,
      issueTitle: "30日ちょうどを拒否している",
      summary: "`>= 30` のため、許可すべき30日ちょうどが拒否される。",
      explanation:
        "30日以内は30日を含みます。拒否条件は30以上ではなく30を超える場合です。",
      correctCode: `if days > 30:
        return False`,
      hints: [
        "以内は境界値を含みます。",
        "30を入れたときにFalseになっています。",
        "拒否条件は `> 30` です。"
      ],
      fix: {
        id: "fix-greater-than",
        label: "30を超えた場合だけ拒否する",
        description: "30日ちょうどを許可する",
        code: `if days > 30:
        return False`
      }
    })
  },
  {
    key: "wrong-addition",
    title: "加算式レビュー",
    functionBase: "apply_adjustment",
    build: (context) => ({
      key: "wrong-addition",
      title: "の加算式レビュー",
      category: "logic",
      difficulty: 1,
      pattern: {
        id: "wrong_arithmetic_operator",
        label: "算術演算子の取り違え",
        description: "加算すべき値を減算している"
      },
      requirements: [
        "base に adjustment を加算して返す",
        "adjustment は正の補正値として扱う",
        "入力値は変更しない"
      ],
      examples: [`${context.functionName}(100, 20) -> 120`],
      constraints: [
        "演算子と仕様の動詞を照合する",
        "補正値の符号を勝手に反転しない"
      ],
      code: `def ${context.functionName}(base, adjustment):
    total = base - adjustment
    return total`,
      startLine: 2,
      endLine: 2,
      issueTitle: "加算すべき補正値を減算している",
      summary: "仕様は加算だが、コードは `base - adjustment` になっている。",
      explanation:
        "補正値を足す仕様なので、減算すると結果が逆方向にずれます。",
      correctCode: "total = base + adjustment",
      hints: [
        "仕様の動詞は加算です。",
        "2行目の演算子を見てください。",
        "`-` ではなく `+` が正しいです。"
      ],
      fix: {
        id: "fix-add",
        label: "加算に直す",
        description: "baseにadjustmentを足す",
        code: "total = base + adjustment"
      }
    })
  },
  {
    key: "percentage-fixed",
    title: "割合計算レビュー",
    functionBase: "apply_discount",
    build: (context) => ({
      key: "percentage-fixed",
      title: "の割合計算レビュー",
      category: "logic",
      difficulty: 2,
      pattern: {
        id: "percentage_as_fixed_amount",
        label: "割合と固定額の混同",
        description: "20%の処理を固定値20として扱っている"
      },
      requirements: [
        "amount が 10000 以上なら20%割引する",
        "20円引きではなく20%割引である",
        "10000未満はそのまま返す"
      ],
      examples: [
        `${context.functionName}(10000) -> 8000`,
        `${context.functionName}(9000) -> 9000`
      ],
      constraints: [
        "割合と固定額を混同しない",
        "金額の単位を確認する"
      ],
      code: `def ${context.functionName}(amount):
    if amount >= 10000:
        amount = amount - 20
    return amount`,
      startLine: 3,
      endLine: 3,
      issueTitle: "20%割引を20円引きとして処理している",
      summary: "`amount - 20` は20%ではなく固定額20の減算。",
      explanation:
        "仕様は20%割引です。金額に0.8を掛ける必要があります。",
      correctCode: "amount = amount * 0.8",
      hints: [
        "仕様には%があります。",
        "20を引くと固定額の割引です。",
        "20%割引は0.8倍です。"
      ],
      fix: {
        id: "fix-percent",
        label: "0.8倍にする",
        description: "20%割引として計算する",
        code: "amount = amount * 0.8"
      }
    })
  },
  {
    key: "count-vs-quantity",
    title: "数量集計レビュー",
    functionBase: "sum_quantity",
    build: (context) => ({
      key: "count-vs-quantity",
      title: "の数量集計レビュー",
      category: "logic",
      difficulty: 2,
      pattern: {
        id: "count_instead_of_quantity",
        label: "件数と数量の混同",
        description: "数量を合計すべきところで件数を数えている"
      },
      requirements: [
        "records の quantity を合計する",
        "レコード件数ではなく数量合計を返す",
        "quantity が0のレコードも数量として扱う"
      ],
      examples: [`${context.functionName}([{"quantity": 2}, {"quantity": 5}]) -> 7`],
      constraints: [
        "何の合計かを変数名だけで判断しない",
        "件数と数量を分けて読む"
      ],
      code: `def ${context.functionName}(records):
    total = 0
    for record in records:
        total += 1
    return total`,
      startLine: 4,
      endLine: 4,
      issueTitle: "quantityではなく件数を足している",
      summary: "`total += 1` は数量合計ではなくレコード件数になる。",
      explanation:
        "仕様は各レコードの quantity 合計です。1ずつ足すと件数カウントになります。",
      correctCode: `total += record["quantity"]`,
      hints: [
        "足している値が1固定です。",
        "仕様はquantityの合計です。",
        "4行目でrecordの値を使う必要があります。"
      ],
      fix: {
        id: "fix-quantity",
        label: "quantityを合計する",
        description: "件数ではなく数量を足す",
        code: `total += record["quantity"]`
      }
    })
  },
  {
    key: "break-continue",
    title: "ループスキップレビュー",
    functionBase: "sum_available",
    build: (context) => ({
      key: "break-continue",
      title: "のループスキップレビュー",
      category: "logic",
      difficulty: 2,
      pattern: {
        id: "break_instead_of_continue",
        label: "break/continueの取り違え",
        description: "1件だけスキップすべき条件でループ全体を終了している"
      },
      requirements: [
        "blocked が True のレコードは集計しない",
        "blocked 以外の後続レコードは引き続き処理する",
        "value の合計を返す"
      ],
      examples: [`${context.functionName}([blocked, available]) -> 後続availableも集計`],
      constraints: [
        "除外と終了を混同しない",
        "後続データが捨てられないか確認する"
      ],
      code: `def ${context.functionName}(records):
    total = 0
    for record in records:
        if record["blocked"]:
            break
        total += record["value"]
    return total`,
      startLine: 5,
      endLine: 5,
      issueTitle: "除外条件でループ全体を止めている",
      summary: "blocked レコードを見つけた時点で後続処理まで止まる。",
      explanation:
        "blocked の1件だけを集計から外す仕様なので、`break` ではなく `continue` が必要です。",
      correctCode: "continue",
      hints: [
        "blockedは1件だけ除外する条件です。",
        "breakは後続レコードも捨てます。",
        "5行目はcontinueが正しいです。"
      ],
      fix: {
        id: "fix-continue",
        label: "continueにする",
        description: "対象レコードだけをスキップする",
        code: "continue"
      }
    })
  },
  {
    key: "return-inside-loop",
    title: "早すぎるreturnレビュー",
    functionBase: "all_ready",
    build: (context) => ({
      key: "return-inside-loop",
      title: "の早すぎるreturnレビュー",
      category: "logic",
      difficulty: 3,
      pattern: {
        id: "early_return_in_loop",
        label: "ループ内の早すぎるreturn",
        description: "全件確認すべき処理が最初の成功で終了している"
      },
      requirements: [
        "すべての records が ready なら True を返す",
        "1件でも ready でなければ False を返す",
        "空配列は True とする"
      ],
      examples: [`${context.functionName}([{"ready": True}, {"ready": False}]) -> False`],
      constraints: [
        "any と all の違いを見る",
        "ループ内returnが妥当か確認する"
      ],
      code: `def ${context.functionName}(records):
    for record in records:
        if record["ready"]:
            return True
    return False`,
      startLine: 3,
      endLine: 4,
      issueTitle: "1件readyなら全体をTrueにしている",
      summary: "全件確認ではなく、最初のreadyでTrueを返している。",
      explanation:
        "仕様は全件readyです。readyでないレコードを見つけた時だけFalseにし、最後まで通ればTrueにします。",
      correctCode: `if not record["ready"]:
            return False`,
      hints: [
        "仕様は all です。",
        "今のコードは any に近い挙動です。",
        "readyでない場合にFalseを返すべきです。"
      ],
      fix: {
        id: "fix-all",
        label: "not readyでFalseにする",
        description: "全件readyかを確認する",
        code: `if not record["ready"]:
            return False`
      }
    })
  },
  {
    key: "min-max",
    title: "最大値選択レビュー",
    functionBase: "pick_best",
    build: (context) => ({
      key: "min-max",
      title: "の最大値選択レビュー",
      category: "logic",
      difficulty: 1,
      pattern: {
        id: "min_max_reversed",
        label: "最大/最小の取り違え",
        description: "最高値を選ぶ仕様で最小値を選んでいる"
      },
      requirements: [
        "scores の中で最大値を返す",
        "空配列は None を返す",
        "最小値ではなく最高値を選ぶ"
      ],
      examples: [`${context.functionName}([10, 30, 20]) -> 30`],
      constraints: [
        "best/highestという語と関数を照合する",
        "空配列の扱いも確認する"
      ],
      code: `def ${context.functionName}(scores):
    if not scores:
        return None
    return min(scores)`,
      startLine: 4,
      endLine: 4,
      issueTitle: "最大値ではなく最小値を返している",
      summary: "`min(scores)` は最高値ではなく最低値。",
      explanation:
        "仕様は最大値の選択です。`best` と `min` の意味が一致していません。",
      correctCode: "return max(scores)",
      hints: [
        "bestは最小でしょうか、最大でしょうか。",
        "4行目の関数名を見てください。",
        "`max` が正しいです。"
      ],
      fix: {
        id: "fix-max",
        label: "maxを使う",
        description: "最大値を返す",
        code: "return max(scores)"
      }
    })
  },
  {
    key: "sort-direction",
    title: "並び順レビュー",
    functionBase: "rank_items",
    build: (context) => ({
      key: "sort-direction",
      title: "の並び順レビュー",
      category: "logic",
      difficulty: 2,
      pattern: {
        id: "sort_direction_reversed",
        label: "昇順/降順の取り違え",
        description: "高い順に並べる仕様で低い順に並んでいる"
      },
      requirements: [
        "items を score の高い順に並べる",
        "score が同じ場合の順序は問わない",
        "元の配列は変更しない"
      ],
      examples: [`${context.functionName}([{"score": 1}, {"score": 3}]) -> 3が先`],
      constraints: [
        "ランキングは降順が多い",
        "sortのreverse指定を見る"
      ],
      code: `def ${context.functionName}(items):
    return sorted(items, key=lambda item: item["score"])`,
      startLine: 2,
      endLine: 2,
      issueTitle: "高い順ではなく低い順に並べている",
      summary: "`sorted` のデフォルトは昇順なので、低いscoreが先に来る。",
      explanation:
        "仕様は高い順です。`reverse=True` を付けないとランキングが逆になります。",
      correctCode: `return sorted(items, key=lambda item: item["score"], reverse=True)`,
      hints: [
        "sortedのデフォルトは昇順です。",
        "仕様は高い順です。",
        "reverse=Trueが必要です。"
      ],
      fix: {
        id: "fix-reverse-sort",
        label: "reverse=Trueを付ける",
        description: "scoreの高い順に並べる",
        code: `return sorted(items, key=lambda item: item["score"], reverse=True)`
      }
    })
  },
  {
    key: "filter-reversed",
    title: "抽出条件レビュー",
    functionBase: "active_only",
    build: (context) => ({
      key: "filter-reversed",
      title: "の抽出条件レビュー",
      category: "logic",
      difficulty: 2,
      pattern: {
        id: "filter_condition_reversed",
        label: "フィルタ条件の反転",
        description: "残すべき対象と除外すべき対象が逆になっている"
      },
      requirements: [
        "status が active のレコードだけを返す",
        "inactive は返さない",
        "入力順は維持する"
      ],
      examples: [`${context.functionName}([active, inactive]) -> [active]`],
      constraints: [
        "抽出したい集合を確認する",
        "!= と == を流し読みしない"
      ],
      code: `def ${context.functionName}(records):
    return [record for record in records if record["status"] != "active"]`,
      startLine: 2,
      endLine: 2,
      issueTitle: "active以外を返している",
      summary: "activeだけを返す仕様だが、条件が `!= active` になっている。",
      explanation:
        "抽出条件が逆です。activeを残すなら `== 'active'` で絞り込みます。",
      correctCode: `return [record for record in records if record["status"] == "active"]`,
      hints: [
        "仕様はactiveだけを残すことです。",
        "今の条件はactive以外を選んでいます。",
        "`!=` ではなく `==` です。"
      ],
      fix: {
        id: "fix-active-filter",
        label: "activeだけにする",
        description: "残す対象に条件を合わせる",
        code: `return [record for record in records if record["status"] == "active"]`
      }
    })
  },
  {
    key: "missing-none-validation",
    title: "None入力レビュー",
    functionBase: "has_email",
    build: (context) => ({
      key: "missing-none-validation",
      title: "のNone入力レビュー",
      category: "boundary",
      difficulty: 2,
      pattern: {
        id: "none_case_missed",
        label: "Noneケースの見落とし",
        description: "空文字だけを見てNoneを検証していない"
      },
      requirements: [
        "email が None の場合は False",
        "email が空文字の場合は False",
        "email に @ が含まれる場合だけ True"
      ],
      examples: [
        `${context.functionName}(None) -> False`,
        `${context.functionName}("") -> False`
      ],
      constraints: [
        "空文字とNoneの両方を見る",
        "文字列メソッドを呼ぶ前にNoneを処理する"
      ],
      code: `def ${context.functionName}(email):
    if email == "":
        return False
    return "@" in email`,
      startLine: 2,
      endLine: 4,
      issueTitle: "Noneのemailで壊れる",
      summary: "空文字だけを検証し、Noneのまま `in` 判定に進む。",
      explanation:
        "仕様ではNoneもFalseです。Noneに対して文字列判定を行うと例外になります。",
      correctCode: `if not email:
        return False`,
      hints: [
        "空文字だけでなくNoneも入力されます。",
        "Noneに `in` を使えません。",
        "`if not email` で両方を落とせます。"
      ],
      fix: {
        id: "fix-not-email",
        label: "Noneと空文字を先に落とす",
        description: "文字列判定前に入力を検証する",
        code: `if not email:
        return False`
      }
    })
  },
  {
    key: "negative-validation",
    title: "負数検証レビュー",
    functionBase: "is_valid_amount",
    build: (context) => ({
      key: "negative-validation",
      title: "の負数検証レビュー",
      category: "boundary",
      difficulty: 1,
      pattern: {
        id: "negative_value_allowed",
        label: "負数を許可している",
        description: "負数を無効にする仕様でTrueを返している"
      },
      requirements: [
        "amount が0以上なら True",
        "amount が負数なら False",
        "0は有効値として扱う"
      ],
      examples: [
        `${context.functionName}(0) -> True`,
        `${context.functionName}(-1) -> False`
      ],
      constraints: [
        "0と負数を分ける",
        "検証関数のTrue/Falseを反転しない"
      ],
      code: `def ${context.functionName}(amount):
    if amount < 0:
        return True
    return True`,
      startLine: 2,
      endLine: 3,
      issueTitle: "負数でもTrueを返している",
      summary: "amount < 0 の場合も True になっている。",
      explanation:
        "負数は無効なので False を返す必要があります。",
      correctCode: `if amount < 0:
        return False`,
      hints: [
        "負数の例を頭で実行してください。",
        "検証関数でTrueは有効を意味します。",
        "負数ではFalseです。"
      ],
      fix: {
        id: "fix-negative-false",
        label: "負数ではFalseを返す",
        description: "無効なamountを拒否する",
        code: `if amount < 0:
        return False`
      }
    })
  },
  {
    key: "mutable-default",
    title: "mutable defaultレビュー",
    functionBase: "append_note",
    build: (context) => ({
      key: "mutable-default",
      title: "のmutable defaultレビュー",
      category: "data_flow",
      difficulty: 3,
      pattern: {
        id: "mutable_default_argument",
        label: "mutable default argument",
        description: "デフォルト引数のリストが呼び出し間で共有される"
      },
      requirements: [
        "notes を指定しない場合は空リストから始める",
        "呼び出しごとに独立したリストを返す",
        "前回呼び出しの値を引き継がない"
      ],
      examples: [`${context.functionName}("a") -> ["a"], 次回 ${context.functionName}("b") -> ["b"]`],
      constraints: [
        "リストのデフォルト引数を疑う",
        "呼び出し間で状態を共有しない"
      ],
      code: `def ${context.functionName}(note, notes=[]):
    notes.append(note)
    return notes`,
      startLine: 1,
      endLine: 2,
      issueTitle: "デフォルト引数のリストを共有している",
      summary: "`notes=[]` が呼び出し間で共有される。",
      explanation:
        "Pythonのデフォルト引数は定義時に一度だけ評価されます。リストを変更すると次回呼び出しに残ります。",
      correctCode: `def ${context.functionName}(note, notes=None):
    if notes is None:
        notes = []`,
      hints: [
        "関数定義の引数にリストがあります。",
        "appendすると次回呼び出しにも残ります。",
        "デフォルトはNoneにします。"
      ],
      fix: {
        id: "fix-none-default",
        label: "Noneデフォルトにする",
        description: "呼び出しごとに新しいリストを作る",
        code: `def ${context.functionName}(note, notes=None):
    if notes is None:
        notes = []`
      }
    })
  },
  {
    key: "alias-copy",
    title: "参照コピー破壊レビュー",
    functionBase: "mask_record",
    build: (context) => ({
      key: "alias-copy",
      title: "の参照コピー破壊レビュー",
      category: "data_flow",
      difficulty: 3,
      pattern: {
        id: "alias_instead_of_copy",
        label: "コピーと参照の混同",
        description: "コピーしたつもりで同じオブジェクトを変更している"
      },
      requirements: [
        "入力recordは変更しない",
        "返却用のrecordだけmasked=Trueにする",
        "元データは後続処理でそのまま使う"
      ],
      examples: [`元record["masked"]は変更されない`],
      constraints: [
        "代入はコピーではない",
        "入力破壊が許されるか確認する"
      ],
      code: `def ${context.functionName}(record):
    masked = record
    masked["masked"] = True
    return masked`,
      startLine: 2,
      endLine: 3,
      issueTitle: "元recordまで変更している",
      summary: "`masked = record` はコピーではなく同じ辞書への参照。",
      explanation:
        "返却用だけを変更する仕様なので、浅いコピーを作ってから変更する必要があります。",
      correctCode: "masked = record.copy()",
      hints: [
        "代入はコピーではありません。",
        "3行目の変更は元recordにも効きます。",
        "`record.copy()` が必要です。"
      ],
      fix: {
        id: "fix-copy",
        label: "dictをコピーする",
        description: "返却用の別オブジェクトを変更する",
        code: "masked = record.copy()"
      }
    })
  },
  {
    key: "shallow-copy-nested",
    title: "ネスト参照レビュー",
    functionBase: "copy_settings",
    build: (context) => ({
      key: "shallow-copy-nested",
      title: "のネスト参照レビュー",
      category: "data_flow",
      difficulty: 4,
      pattern: {
        id: "nested_object_shared",
        label: "ネストオブジェクトの共有",
        description: "浅いコピーだけで内部の辞書やリストが共有されている"
      },
      requirements: [
        "settings全体を独立コピーする",
        "返却後に nested flags を変更しても元settingsへ影響しない",
        "トップレベルだけでなく内部辞書も分離する"
      ],
      examples: [`copy["flags"]["enabled"]変更後も元settingsは変わらない`],
      constraints: [
        "浅いコピーと深いコピーを区別する",
        "ネスト構造の共有を疑う"
      ],
      code: `def ${context.functionName}(settings):
    copied = settings.copy()
    copied["flags"]["enabled"] = True
    return copied`,
      startLine: 2,
      endLine: 3,
      issueTitle: "内部辞書が元settingsと共有されている",
      summary: "浅いコピーでは `flags` の中身が共有されたまま。",
      explanation:
        "ネストした辞書を変更するなら、内部辞書もコピーする必要があります。",
      correctCode: `copied = settings.copy()
    copied["flags"] = settings["flags"].copy()`,
      hints: [
        "copy()は浅いコピーです。",
        "flagsは内部辞書です。",
        "内部辞書もコピーしてください。"
      ],
      fix: {
        id: "fix-nested-copy",
        label: "内部辞書もコピーする",
        description: "ネストしたflagsを分離する",
        code: `copied = settings.copy()
    copied["flags"] = settings["flags"].copy()`
      }
    })
  },
  {
    key: "exception-success",
    title: "例外成功扱いレビュー",
    functionBase: "parse_count",
    build: (context) => ({
      key: "exception-success",
      title: "の例外成功扱いレビュー",
      category: "spec",
      difficulty: 3,
      pattern: {
        id: "failure_returned_as_success",
        label: "失敗を成功レスポンスにしている",
        description: "例外時にもok=Trueを返している"
      },
      requirements: [
        "数値に変換できれば ok=True と value を返す",
        "変換できなければ ok=False と value=None を返す",
        "失敗を成功として扱わない"
      ],
      examples: [
        `${context.functionName}("3") -> {"ok": True, "value": 3}`,
        `${context.functionName}("x") -> {"ok": False, "value": None}`
      ],
      constraints: [
        "戻り値契約を見る",
        "例外処理が失敗を隠していないか確認する"
      ],
      code: `def ${context.functionName}(text):
    try:
        return {"ok": True, "value": int(text)}
    except Exception:
        return {"ok": True, "value": 0}`,
      startLine: 4,
      endLine: 5,
      issueTitle: "変換失敗時にもok=Trueを返している",
      summary: "失敗ケースが成功レスポンスとして返る。",
      explanation:
        "呼び出し側はok=Trueを成功と解釈します。変換失敗時はok=Falseにする必要があります。",
      correctCode: `except ValueError:
        return {"ok": False, "value": None}`,
      hints: [
        "例外時のokを見てください。",
        "失敗を成功として返しています。",
        "ValueErrorを捕捉してok=Falseです。"
      ],
      fix: {
        id: "fix-ok-false",
        label: "ok=Falseを返す",
        description: "失敗を呼び出し側が判別できるようにする",
        code: `except ValueError:
        return {"ok": False, "value": None}`
      }
    })
  },
  {
    key: "broad-exception",
    title: "広すぎる例外レビュー",
    functionBase: "load_required",
    build: (context) => ({
      key: "broad-exception",
      title: "の広すぎる例外レビュー",
      category: "spec",
      difficulty: 4,
      pattern: {
        id: "broad_exception_swallow",
        label: "広すぎる例外捕捉",
        description: "想定外のバグまで握りつぶしている"
      },
      requirements: [
        "KeyError の場合だけ既定値を返す",
        "その他の例外は握りつぶさない",
        "バグを正常系に変換しない"
      ],
      examples: [`missing key -> "N/A", TypeError -> 例外のまま`],
      constraints: [
        "捕捉する例外型を見る",
        "想定外のエラーを隠さない"
      ],
      code: `def ${context.functionName}(record):
    try:
        return record["required"]
    except Exception:
        return "N/A"`,
      startLine: 4,
      endLine: 5,
      issueTitle: "KeyError以外も握りつぶしている",
      summary: "`except Exception` が想定外の例外まで既定値に変換する。",
      explanation:
        "仕様はKeyErrorだけのフォールバックです。広すぎる捕捉はバグを隠します。",
      correctCode: `except KeyError:
        return "N/A"`,
      hints: [
        "仕様で許される例外はKeyErrorだけです。",
        "Exceptionは広すぎます。",
        "捕捉する型を狭めてください。"
      ],
      fix: {
        id: "fix-key-error",
        label: "KeyErrorだけ捕捉する",
        description: "想定外の例外は握りつぶさない",
        code: `except KeyError:
        return "N/A"`
      }
    })
  },
  {
    key: "generator-reuse",
    title: "generator再利用レビュー",
    functionBase: "average_positive",
    build: (context) => ({
      key: "generator-reuse",
      title: "のgenerator再利用レビュー",
      category: "data_flow",
      difficulty: 4,
      pattern: {
        id: "generator_consumed_twice",
        label: "generatorの二重消費",
        description: "一度消費したgeneratorを再利用している"
      },
      requirements: [
        "0より大きい値だけの平均を返す",
        "対象が0件なら None を返す",
        "generatorを消費した後に再利用しない"
      ],
      examples: [`${context.functionName}([1, 3, -1]) -> 2`],
      constraints: [
        "generatorは一度読むと空になる",
        "平均計算の0件ケースを見る"
      ],
      code: `def ${context.functionName}(values):
    positives = (value for value in values if value > 0)
    count = len(list(positives))
    if count == 0:
        return None
    return sum(positives) / count`,
      startLine: 2,
      endLine: 6,
      issueTitle: "positivesをlist化した後に再利用している",
      summary: "generatorは `len(list(...))` で消費済みになる。",
      explanation:
        "count取得後の `sum(positives)` には要素が残っていません。リスト化した値を再利用します。",
      correctCode: `positives = [value for value in values if value > 0]`,
      hints: [
        "positivesはgeneratorです。",
        "list化した時点で消費されています。",
        "最初からリストにしてcountとsumに使います。"
      ],
      fix: {
        id: "fix-list",
        label: "positivesをリストにする",
        description: "同じ要素をcountとsumで使えるようにする",
        code: `positives = [value for value in values if value > 0]`
      }
    })
  },
  {
    key: "missing-await",
    title: "await漏れレビュー",
    functionBase: "load_profile",
    build: (context) => ({
      key: "missing-await",
      title: "のawait漏れレビュー",
      category: "data_flow",
      difficulty: 4,
      pattern: {
        id: "missing_await",
        label: "await漏れ",
        description: "非同期処理の結果ではなくcoroutineを使っている"
      },
      requirements: [
        "client.get_profile は非同期APIである",
        "profileを辞書として使う前にawaitする",
        "disabledならPermissionErrorを送出する"
      ],
      examples: [`disabled profile -> PermissionError`],
      constraints: [
        "async関数内の外部API呼び出しを見る",
        "片方だけawaitされていないケースを疑う"
      ],
      code: `async def ${context.functionName}(user_id, client):
    profile = client.get_profile(user_id)
    orders = await client.get_orders(user_id)
    if profile["disabled"]:
        raise PermissionError("disabled")
    return {"profile": profile, "orders": orders}`,
      startLine: 2,
      endLine: 4,
      issueTitle: "get_profileをawaitしていない",
      summary: "profileが実データではなくcoroutineのまま使われる。",
      explanation:
        "非同期APIはawaitしないと結果が得られません。辞書アクセス前にawaitが必要です。",
      correctCode: "profile = await client.get_profile(user_id)",
      hints: [
        "ordersはawaitされています。",
        "profileはawaitされていません。",
        "2行目にawaitが必要です。"
      ],
      fix: {
        id: "fix-await",
        label: "get_profileをawaitする",
        description: "profileを実データとして取得する",
        code: "profile = await client.get_profile(user_id)"
      }
    })
  },
  {
    key: "permission-inverted",
    title: "権限反転レビュー",
    functionBase: "can_export",
    build: (context) => ({
      key: "permission-inverted",
      title: "の権限反転レビュー",
      category: "security",
      difficulty: 3,
      pattern: {
        id: "permission_condition_inverted",
        label: "権限条件の反転",
        description: "許可されていないユーザーを通している"
      },
      requirements: [
        "user['can_export'] が True の場合だけ True",
        "False の場合は False",
        "管理者以外に特例はない"
      ],
      examples: [
        `${context.functionName}({"can_export": True}) -> True`,
        `${context.functionName}({"can_export": False}) -> False`
      ],
      constraints: [
        "許可条件と戻り値を照合する",
        "否定条件でTrueを返していないか見る"
      ],
      code: `def ${context.functionName}(user):
    if not user["can_export"]:
        return True
    return False`,
      startLine: 2,
      endLine: 4,
      issueTitle: "権限がないユーザーを許可している",
      summary: "`not can_export` のときに True を返している。",
      explanation:
        "権限がないユーザーは拒否すべきです。戻り値が仕様と逆になっています。",
      correctCode: `return user["can_export"] is True`,
      hints: [
        "can_exportがFalseの例を実行してください。",
        "今は権限なしでTrueになります。",
        "権限値をそのまま判定に使います。"
      ],
      fix: {
        id: "fix-permission",
        label: "権限ありだけTrueにする",
        description: "can_exportの値に合わせる",
        code: `return user["can_export"] is True`
      }
    })
  },
  {
    key: "auth-after-cache",
    title: "キャッシュ認可順序レビュー",
    functionBase: "get_cached_record",
    build: (context) => ({
      key: "auth-after-cache",
      title: "のキャッシュ認可順序レビュー",
      category: "security",
      difficulty: 5,
      pattern: {
        id: "cache_before_authorization",
        label: "キャッシュが認可を迂回",
        description: "認可チェック前にキャッシュ済みデータを返している"
      },
      requirements: [
        "データ取得前に必ず user['can_view'] を確認する",
        "権限がないユーザーにはキャッシュ済みデータも返さない",
        "権限確認後にキャッシュを参照する"
      ],
      examples: [`can_view=False -> PermissionError`],
      constraints: [
        "高速化が認可を迂回していないか見る",
        "キャッシュヒット時の経路を確認する"
      ],
      code: `CACHE = {}

def ${context.functionName}(user, record_id, db):
    key = record_id
    if key in CACHE:
        return CACHE[key]
    if not user["can_view"]:
        raise PermissionError("forbidden")
    record = db.load(record_id)
    CACHE[key] = record
    return record`,
      startLine: 5,
      endLine: 7,
      issueTitle: "認可前にキャッシュ済みデータを返している",
      summary: "キャッシュヒットすると権限確認に到達しない。",
      explanation:
        "キャッシュはDBアクセスを省略してよいですが、認可を省略してはいけません。",
      correctCode: `if not user["can_view"]:
        raise PermissionError("forbidden")
    if key in CACHE:
        return CACHE[key]`,
      hints: [
        "キャッシュヒット時に権限チェックへ進みますか。",
        "認可はキャッシュより前です。",
        "if key in CACHE の前に権限確認を置きます。"
      ],
      fix: {
        id: "fix-auth-first",
        label: "認可を先に行う",
        description: "権限確認後にキャッシュを返す",
        code: `if not user["can_view"]:
        raise PermissionError("forbidden")
    if key in CACHE:
        return CACHE[key]`
      }
    })
  },
  {
    key: "tenant-cache-key",
    title: "テナント分離レビュー",
    functionBase: "get_tenant_record",
    build: (context) => ({
      key: "tenant-cache-key",
      title: "のテナント分離レビュー",
      category: "security",
      difficulty: 5,
      pattern: {
        id: "cache_key_too_coarse",
        label: "粗すぎるキャッシュキー",
        description: "テナント境界を含まないキーでデータが混ざる"
      },
      requirements: [
        "キャッシュキーには tenant_id と record_id を含める",
        "別テナントの同じrecord_idを混同しない",
        "db.loadにはtenant_idとrecord_idを渡す"
      ],
      examples: [`tenant A/B の record_id=1 は別キャッシュ`],
      constraints: [
        "マルチテナント境界を見る",
        "キャッシュキーの粒度を確認する"
      ],
      code: `CACHE = {}

def ${context.functionName}(tenant_id, record_id, db):
    key = record_id
    if key in CACHE:
        return CACHE[key]
    record = db.load(tenant_id, record_id)
    CACHE[key] = record
    return record`,
      startLine: 4,
      endLine: 4,
      issueTitle: "キャッシュキーにtenant_idがない",
      summary: "record_idだけでは別テナントのデータを分離できない。",
      explanation:
        "マルチテナントでは同じrecord_idが別テナントに存在します。キーにtenant_idが必要です。",
      correctCode: "key = (tenant_id, record_id)",
      hints: [
        "db.loadにはtenant_idを渡しています。",
        "キャッシュキーにはrecord_idしかありません。",
        "tenant_idをキーに含めてください。"
      ],
      fix: {
        id: "fix-tenant-key",
        label: "tenant_idをキーに含める",
        description: "テナント別にキャッシュを分離する",
        code: "key = (tenant_id, record_id)"
      }
    })
  },
  {
    key: "date-boundary",
    title: "日付境界レビュー",
    functionBase: "is_before_deadline",
    build: (context) => ({
      key: "date-boundary",
      title: "の日付境界レビュー",
      category: "boundary",
      difficulty: 3,
      pattern: {
        id: "date_deadline_excluded",
        label: "締切当日の除外",
        description: "締切日当日を許可すべき仕様で拒否している"
      },
      requirements: [
        "target_date が deadline 以前なら True",
        "deadline 当日は True",
        "deadline より後なら False"
      ],
      examples: [`target_date == deadline -> True`],
      constraints: [
        "以前/以後は境界を含む",
        "日付の等号を確認する"
      ],
      code: `def ${context.functionName}(target_date, deadline):
    if target_date >= deadline:
        return False
    return True`,
      startLine: 2,
      endLine: 3,
      issueTitle: "deadline当日を拒否している",
      summary: "`>= deadline` のため、締切当日もFalseになる。",
      explanation:
        "deadline以前は当日を含みます。拒否するのはdeadlineより後だけです。",
      correctCode: `if target_date > deadline:
        return False`,
      hints: [
        "deadline当日は許可です。",
        ">=は当日も含めて拒否します。",
        "拒否条件は > deadline です。"
      ],
      fix: {
        id: "fix-date-after",
        label: "deadlineより後だけ拒否する",
        description: "締切当日を許可する",
        code: `if target_date > deadline:
        return False`
      }
    })
  },
  {
    key: "range-off-by-one",
    title: "range終端レビュー",
    functionBase: "build_days",
    build: (context) => ({
      key: "range-off-by-one",
      title: "のrange終端レビュー",
      category: "boundary",
      difficulty: 3,
      pattern: {
        id: "range_end_exclusive_missed",
        label: "range終端の除外",
        description: "rangeの終端が含まれないことを見落としている"
      },
      requirements: [
        "1日目からdays日目までの整数リストを返す",
        "days日目を含める",
        "days=3なら[1, 2, 3]"
      ],
      examples: [`${context.functionName}(3) -> [1, 2, 3]`],
      constraints: [
        "rangeの終端は含まれない",
        "件数と最後の値を確認する"
      ],
      code: `def ${context.functionName}(days):
    result = []
    for day in range(1, days):
        result.append(day)
    return result`,
      startLine: 3,
      endLine: 3,
      issueTitle: "最終日がリストに含まれない",
      summary: "`range(1, days)` は days を含まない。",
      explanation:
        "days日目まで含めるなら、終端は `days + 1` にする必要があります。",
      correctCode: "for day in range(1, days + 1):",
      hints: [
        "rangeの終端は含まれません。",
        "days=3で頭の中で実行してください。",
        "days + 1 が必要です。"
      ],
      fix: {
        id: "fix-range-end",
        label: "days + 1まで回す",
        description: "最終日を含める",
        code: "for day in range(1, days + 1):"
      }
    })
  },
  {
    key: "one-based-index",
    title: "1始まり番号レビュー",
    functionBase: "pick_position",
    build: (context) => ({
      key: "one-based-index",
      title: "の1始まり番号レビュー",
      category: "boundary",
      difficulty: 2,
      pattern: {
        id: "one_based_index_used_as_zero_based",
        label: "1始まり/0始まりの混同",
        description: "ユーザー向け番号をPythonのindexとしてそのまま使っている"
      },
      requirements: [
        "position は1始まりで指定される",
        "position=1なら先頭要素を返す",
        "範囲外は None を返す"
      ],
      examples: [`${context.functionName}(["a", "b"], 1) -> "a"`],
      constraints: [
        "ユーザー入力の番号とPython indexを分ける",
        "境界チェックを見る"
      ],
      code: `def ${context.functionName}(items, position):
    if position < 1 or position > len(items):
        return None
    return items[position]`,
      startLine: 4,
      endLine: 4,
      issueTitle: "1始まりのpositionをそのままindexに使っている",
      summary: "position=1で2番目の要素を返す。",
      explanation:
        "Pythonのリストは0始まりです。ユーザー向けの1始まり番号は1引いてindexにします。",
      correctCode: "return items[position - 1]",
      hints: [
        "position=1の例を考えてください。",
        "Pythonのindexは0始まりです。",
        "1を引いて参照します。"
      ],
      fix: {
        id: "fix-position-minus-one",
        label: "position - 1で参照する",
        description: "1始まり番号を0始まりindexに変換する",
        code: "return items[position - 1]"
      }
    })
  },
  {
    key: "dedupe-order",
    title: "重複排除順序レビュー",
    functionBase: "unique_ids",
    build: (context) => ({
      key: "dedupe-order",
      title: "の重複排除順序レビュー",
      category: "data_flow",
      difficulty: 3,
      pattern: {
        id: "set_loses_order",
        label: "setで順序を失う",
        description: "入力順を維持すべき重複排除でsetを使っている"
      },
      requirements: [
        "重複を除いたidリストを返す",
        "最初に出現した順序を維持する",
        "順序を変えてはいけない"
      ],
      examples: [`${context.functionName}(["b", "a", "b"]) -> ["b", "a"]`],
      constraints: [
        "setは順序保証目的で使わない",
        "重複排除と順序維持を両立する"
      ],
      code: `def ${context.functionName}(ids):
    return list(set(ids))`,
      startLine: 2,
      endLine: 2,
      issueTitle: "set化で入力順を失っている",
      summary: "`list(set(ids))` は最初の出現順を維持しない。",
      explanation:
        "仕様は順序維持です。seenを使って、初出のidだけを順に追加します。",
      correctCode: `seen = set()
    result = []
    for item_id in ids:
        if item_id not in seen:
            seen.add(item_id)
            result.append(item_id)
    return result`,
      hints: [
        "setは重複排除できますが順序が目的ではありません。",
        "最初に出現した順序を守る仕様です。",
        "seenとresultを使います。"
      ],
      fix: {
        id: "fix-preserve-order",
        label: "seenで順序維持する",
        description: "初出順に重複排除する",
        code: `seen = set()
    result = []
    for item_id in ids:
        if item_id not in seen:
            seen.add(item_id)
            result.append(item_id)
    return result`
      }
    })
  },
  {
    key: "matrix-alias",
    title: "二次元配列共有レビュー",
    functionBase: "build_matrix",
    build: (context) => ({
      key: "matrix-alias",
      title: "の二次元配列共有レビュー",
      category: "data_flow",
      difficulty: 4,
      pattern: {
        id: "list_multiplication_alias",
        label: "リスト乗算による行共有",
        description: "二次元配列の各行が同じリストを参照している"
      },
      requirements: [
        "rows x cols の独立した二次元配列を作る",
        "1つのセル変更が他行へ波及しない",
        "初期値はすべて0"
      ],
      examples: [`matrix[0][0]変更後もmatrix[1][0]は0`],
      constraints: [
        "リスト乗算の参照共有を見る",
        "二次元配列は内包表記で作る"
      ],
      code: `def ${context.functionName}(rows, cols):
    matrix = [[0] * cols] * rows
    return matrix`,
      startLine: 2,
      endLine: 2,
      issueTitle: "各行が同じリストを共有している",
      summary: "`[[0] * cols] * rows` は内側のリスト参照を複製する。",
      explanation:
        "行ごとに独立したリストを作る必要があります。外側も内包表記で生成します。",
      correctCode: "matrix = [[0] * cols for _ in range(rows)]",
      hints: [
        "リスト乗算は参照を複製します。",
        "1セル変更が他行に波及します。",
        "行ごとに新しいリストを作ります。"
      ],
      fix: {
        id: "fix-matrix-comprehension",
        label: "内包表記で行を作る",
        description: "各行を独立させる",
        code: "matrix = [[0] * cols for _ in range(rows)]"
      }
    })
  },
  {
    key: "integer-division",
    title: "比率計算レビュー",
    functionBase: "completion_rate",
    build: (context) => ({
      key: "integer-division",
      title: "の比率計算レビュー",
      category: "logic",
      difficulty: 2,
      pattern: {
        id: "integer_division_for_ratio",
        label: "比率で整数除算を使っている",
        description: "小数の比率が必要なのに切り捨てている"
      },
      requirements: [
        "completed / total の小数比率を返す",
        "total が0なら0を返す",
        "50%は0.5として返す"
      ],
      examples: [
        `${context.functionName}(1, 2) -> 0.5`,
        `${context.functionName}(0, 0) -> 0`
      ],
      constraints: [
        "比率と整数商を混同しない",
        "0除算も確認する"
      ],
      code: `def ${context.functionName}(completed, total):
    if total == 0:
        return 0
    return completed // total`,
      startLine: 4,
      endLine: 4,
      issueTitle: "比率を整数除算で切り捨てている",
      summary: "`//` により 1/2 が 0 になる。",
      explanation:
        "小数比率が必要なので、通常の除算 `/` を使います。",
      correctCode: "return completed / total",
      hints: [
        "50%は0.5です。",
        "`//` は切り捨て除算です。",
        "比率には `/` を使います。"
      ],
      fix: {
        id: "fix-float-division",
        label: "通常の除算にする",
        description: "小数比率を返す",
        code: "return completed / total"
      }
    })
  },
  {
    key: "rounding",
    title: "丸め処理レビュー",
    functionBase: "calc_tax",
    build: (context) => ({
      key: "rounding",
      title: "の丸め処理レビュー",
      category: "logic",
      difficulty: 3,
      pattern: {
        id: "floor_instead_of_round",
        label: "四捨五入と切り捨ての混同",
        description: "round指定なのにintで切り捨てている"
      },
      requirements: [
        "price * rate を四捨五入して返す",
        "切り捨てではない",
        "小数結果は整数に丸める"
      ],
      examples: [`${context.functionName}(15, 0.1) -> 2`],
      constraints: [
        "intは切り捨て",
        "丸め仕様を確認する"
      ],
      code: `def ${context.functionName}(price, rate):
    return int(price * rate)`,
      startLine: 2,
      endLine: 2,
      issueTitle: "四捨五入ではなく切り捨てている",
      summary: "`int` は小数を切り捨てる。",
      explanation:
        "仕様は四捨五入です。`round` を使う必要があります。",
      correctCode: "return round(price * rate)",
      hints: [
        "intは丸めではなく切り捨てです。",
        "15 * 0.1 は1.5です。",
        "roundを使います。"
      ],
      fix: {
        id: "fix-round",
        label: "roundを使う",
        description: "四捨五入する",
        code: "return round(price * rate)"
      }
    })
  },
  {
    key: "case-sensitive-role",
    title: "大文字小文字レビュー",
    functionBase: "is_admin",
    build: (context) => ({
      key: "case-sensitive-role",
      title: "の大文字小文字レビュー",
      category: "boundary",
      difficulty: 2,
      pattern: {
        id: "case_sensitive_comparison",
        label: "大文字小文字の未正規化",
        description: "大小文字を区別しない仕様でそのまま比較している"
      },
      requirements: [
        "role が admin なら True",
        "ADMIN や Admin も True",
        "その他のroleはFalse"
      ],
      examples: [
        `${context.functionName}("ADMIN") -> True`,
        `${context.functionName}("user") -> False`
      ],
      constraints: [
        "入力表記の揺れを見る",
        "比較前に正規化する"
      ],
      code: `def ${context.functionName}(role):
    return role == "admin"`,
      startLine: 2,
      endLine: 2,
      issueTitle: "ADMINをadminとして扱えない",
      summary: "文字列比較が大小文字を区別している。",
      explanation:
        "仕様では大文字小文字を区別しません。比較前に小文字化します。",
      correctCode: `return role.lower() == "admin"`,
      hints: [
        "ADMINの例を考えてください。",
        "今の比較は完全一致です。",
        "lower()してから比較します。"
      ],
      fix: {
        id: "fix-lower",
        label: "lowerして比較する",
        description: "大小文字を吸収する",
        code: `return role.lower() == "admin"`
      }
    })
  },
  {
    key: "membership-substring",
    title: "権限文字列レビュー",
    functionBase: "has_permission",
    build: (context) => ({
      key: "membership-substring",
      title: "の権限文字列レビュー",
      category: "security",
      difficulty: 4,
      pattern: {
        id: "substring_permission_match",
        label: "部分一致の権限判定",
        description: "権限名を文字列の部分一致で判定している"
      },
      requirements: [
        "permission は user['permissions'] の要素として完全一致する必要がある",
        "role文字列への部分一致で許可しない",
        "permissions がない場合は False"
      ],
      examples: [`permission="admin" が role="superadmin" に含まれても許可しない`],
      constraints: [
        "権限は部分文字列で判定しない",
        "リスト内の完全一致を見る"
      ],
      code: `def ${context.functionName}(user, permission):
    return permission in user["role"]`,
      startLine: 2,
      endLine: 2,
      issueTitle: "role文字列への部分一致で権限を許可している",
      summary: "`permission in user['role']` は部分文字列一致になる。",
      explanation:
        "権限はpermissionsリストの要素として完全一致する必要があります。",
      correctCode: `return permission in user.get("permissions", [])`,
      hints: [
        "roleは権限リストではありません。",
        "文字列inは部分一致です。",
        "permissionsリストを見るべきです。"
      ],
      fix: {
        id: "fix-permission-list",
        label: "permissionsリストで判定する",
        description: "権限名を完全一致で確認する",
        code: `return permission in user.get("permissions", [])`
      }
    })
  }
];

export const generatedChallenges: InterviewChallenge[] = patterns.flatMap((pattern) =>
  domains.map((domain) => makeChallenge(domain, pattern))
);
