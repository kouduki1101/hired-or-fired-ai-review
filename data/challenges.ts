import type {
  InterviewChallenge,
  ReviewCategory,
  ReviewChoice,
  ReviewStep,
  ReviewStepKind
} from "@/lib/types";

export const categoryLabels: Record<ReviewCategory, string> = {
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
  pattern: {
    id: string;
    label: string;
    description: string;
  },
  fix: {
    id: string;
    label: string;
    description: string;
    code: string;
  },
  distractors: Array<{
    id: string;
    label: string;
    description: string;
    code?: string;
  }>
): ReviewStep[] {
  return [
    categoryStep(category),
    step("pattern", "どんな失敗パターン？", [
      { ...pattern, correct: true },
      {
        id: "wrong_operator",
        label: "演算子の取り違え",
        description: "算術演算や比較条件が仕様と違う"
      },
      {
        id: "partial_validation",
        label: "仕様の一部だけ検証",
        description: "必要な条件の一部しか見ていない"
      },
      {
        id: "permission_inversion",
        label: "権限条件の反転",
        description: "許可・拒否の条件が逆になっている"
      }
    ]),
    step("fix", "正しい修正はどれ？", [
      { ...fix, correct: true },
      ...distractors
    ])
  ];
}

const baseChallenges: InterviewChallenge[] = [
  {
    id: "calc-api-operator-review",
    role: "Junior Backend Reviewer",
    title: "計算APIの演算子レビュー",
    difficultyLabel: "Warm-up",
    estimatedMinutes: 5,
    timeLimitSeconds: 300,
    codeLanguage: "python",
    requirements: [
      "operator が add のときは a + b を返す",
      "operator が subtract のときは a - b を返す",
      "operator が multiply のときは a * b を返す",
      "operator が divide のときは a / b を返す。ただし b が 0 の場合は ValueError",
      "未対応の operator は None ではなく ValueError を送出する"
    ],
    examples: [
      "calculate_total(2, 3, 'add') -> 5",
      "calculate_total(8, 3, 'subtract') -> 5",
      "calculate_total(2, 3, 'power') -> ValueError"
    ],
    constraints: [
      "Pythonコードは実行せず、要件とコードの差分をレビューする",
      "演算結果と例外仕様の両方を見る"
    ],
    code: `def calculate_total(a, b, operator):
    if operator == "add":
        return a * b
    if operator == "subtract":
        return a + b
    if operator == "multiply":
        return a * b
    if operator == "divide":
        if b == 0:
            raise ValueError("division by zero")
        return a / b
    return None`,
    challengeHints: [
      "まず add / subtract の期待値を例と照合しよう。",
      "未対応 operator の仕様は戻り値ではなく例外です。",
      "怪しい行は 3、5、12 行目です。"
    ],
    issues: [
      {
        id: "calc-add-multiplies",
        title: "add が加算ではなく乗算している",
        category: "logic",
        pattern: "wrong_operator",
        startLine: 3,
        endLine: 3,
        difficulty: 1,
        summary: "add は a + b のはずだが、a * b を返している。",
        explanation:
          "要件では add は加算です。AI生成コードでは multiply と同じ処理になっているため、例 calculate_total(2, 3, 'add') が 6 になります。",
        correctCode: "return a + b",
        hints: [
          "add の例を実際に頭の中で計算してみよう。",
          "演算子が multiply と同じになっている行があります。",
          "3行目は `return a + b` が正しいです。"
        ],
        steps: [
          categoryStep("logic"),
          step("pattern", "どんな失敗パターン？", [
            {
              id: "wrong_operator",
              label: "演算子の取り違え",
              description: "期待される算術演算と実装された演算が違う",
              correct: true
            },
            {
              id: "missing_validation",
              label: "入力検証漏れ",
              description: "入力値の空や型を確認していない"
            },
            {
              id: "wrong_exception",
              label: "例外型の取り違え",
              description: "送出すべき例外と違う例外を使っている"
            },
            {
              id: "permission_inversion",
              label: "権限条件の反転",
              description: "許可・拒否の判定が逆になっている"
            }
          ]),
          step("fix", "正しい修正はどれ？", [
            {
              id: "fix-add",
              label: "加算に直す",
              description: "add の仕様どおり a + b を返す",
              code: "return a + b",
              correct: true
            },
            {
              id: "fix-subtract",
              label: "減算に直す",
              description: "subtract と同じ処理になる"
            },
            {
              id: "fix-int",
              label: "int に変換する",
              description: "演算子の取り違えは解消されない"
            },
            {
              id: "fix-none",
              label: "None を返す",
              description: "正常系の add が壊れる"
            }
          ])
        ]
      },
      {
        id: "calc-subtract-adds",
        title: "subtract が減算ではなく加算している",
        category: "logic",
        pattern: "wrong_operator",
        startLine: 5,
        endLine: 5,
        difficulty: 1,
        summary: "subtract は a - b のはずだが、a + b を返している。",
        explanation:
          "subtract の期待値は a - b です。加算してしまうと calculate_total(8, 3, 'subtract') が 11 になり、要件例と逆方向にずれます。",
        correctCode: "return a - b",
        hints: [
          "subtract の例 8 と 3 を確認しよう。",
          "減算の分岐で使われている演算子が違います。",
          "5行目は `return a - b` が正しいです。"
        ],
        steps: [
          categoryStep("logic"),
          step("pattern", "どんな失敗パターン？", [
            {
              id: "wrong_operator",
              label: "演算子の取り違え",
              description: "期待される算術演算と実装された演算が違う",
              correct: true
            },
            {
              id: "off_by_one",
              label: "境界値の1ズレ",
              description: "以上・より大きいなどの境界がずれている"
            },
            {
              id: "null_path",
              label: "None 経路の見落とし",
              description: "None 入力で例外や不正値になる"
            },
            {
              id: "missing_default",
              label: "デフォルト分岐漏れ",
              description: "未対応ケースの扱いがない"
            }
          ]),
          step("fix", "正しい修正はどれ？", [
            {
              id: "fix-sub",
              label: "減算に直す",
              description: "subtract の仕様どおり a - b を返す",
              code: "return a - b",
              correct: true
            },
            {
              id: "fix-mul",
              label: "乗算に直す",
              description: "multiply と同じ処理になる"
            },
            {
              id: "fix-div",
              label: "除算に直す",
              description: "divide と同じ処理になる"
            },
            {
              id: "fix-abs",
              label: "abs を使う",
              description: "仕様にない符号変換を加えてしまう"
            }
          ])
        ]
      },
      {
        id: "calc-unknown-operator",
        title: "未対応 operator で ValueError ではなく None を返す",
        category: "spec",
        pattern: "wrong_error_contract",
        startLine: 12,
        endLine: 12,
        difficulty: 2,
        summary: "未対応 operator は ValueError を送出する仕様だが、None を返している。",
        explanation:
          "呼び出し側は未対応 operator を例外として扱う前提です。None を返すと正常値のように流れてしまい、後続処理で原因が追いにくくなります。",
        correctCode: "raise ValueError(f\"unsupported operator: {operator}\")",
        hints: [
          "最後の分岐は戻り値の仕様を確認しよう。",
          "未対応 operator は None ではありません。",
          "12行目は ValueError を送出します。"
        ],
        steps: [
          categoryStep("spec"),
          step("pattern", "どんな失敗パターン？", [
            {
              id: "wrong_error_contract",
              label: "エラー契約の違反",
              description: "仕様が要求する例外ではなく通常値を返している",
              correct: true
            },
            {
              id: "wrong_operator",
              label: "演算子の取り違え",
              description: "算術演算そのものが違う"
            },
            {
              id: "leaky_state",
              label: "状態の漏れ",
              description: "前回の値が次回の処理に残っている"
            },
            {
              id: "wrong_priority",
              label: "優先順位の違反",
              description: "重要顧客などの優先順が逆になっている"
            }
          ]),
          step("fix", "正しい修正はどれ？", [
            {
              id: "fix-value-error",
              label: "ValueError を送出する",
              description: "未対応 operator を例外として扱う",
              code: "raise ValueError(f\"unsupported operator: {operator}\")",
              correct: true
            },
            {
              id: "fix-zero",
              label: "0 を返す",
              description: "未対応ケースが正常値に見えてしまう"
            },
            {
              id: "fix-none",
              label: "None のままにする",
              description: "現在の不具合を維持してしまう"
            },
            {
              id: "fix-add-default",
              label: "add として処理する",
              description: "仕様にない暗黙の変換になる"
            }
          ])
        ]
      }
    ]
  },
  {
    id: "user-registration-boundary-review",
    role: "Product Backend Reviewer",
    title: "ユーザー登録条件の境界値レビュー",
    difficultyLabel: "Practical",
    estimatedMinutes: 5,
    timeLimitSeconds: 300,
    codeLanguage: "python",
    requirements: [
      "user が None または空辞書なら False を返す",
      "age は 18 歳以上なら登録可能。18 歳ちょうどは OK",
      "email は空でなく、@ を含む必要がある",
      "banned が True のユーザーは登録不可",
      "すべての条件を満たす場合のみ True"
    ],
    examples: [
      "can_register_user({'age': 18, 'email': 'a@example.com', 'banned': False}) -> True",
      "can_register_user({'age': 17, 'email': 'a@example.com', 'banned': False}) -> False",
      "can_register_user(None) -> False"
    ],
    constraints: [
      "例外で落とすのではなく True / False を返す",
      "境界値と入力欠損を分けて見る"
    ],
    code: `def can_register_user(user):
    if not user:
        return True
    if user.get("age") <= 18:
        return False
    if user.get("email") == "":
        return False
    if user.get("banned") == True:
        return True
    return True`,
    challengeHints: [
      "None や空辞書が来たとき、登録してよいかを確認しよう。",
      "18歳ちょうど、空でないが @ のないメール、banned=True をそれぞれ追いかけよう。",
      "怪しい行は 3、4、6、9 行目です。"
    ],
    issues: [
      {
        id: "user-empty-allowed",
        title: "空の user が登録可能になっている",
        category: "boundary",
        pattern: "invalid_empty_input_allowed",
        startLine: 3,
        endLine: 3,
        difficulty: 2,
        summary: "user が None / 空辞書の場合は False のはずだが True を返している。",
        explanation:
          "要件では入力欠損は登録不可です。`if not user` の分岐で True を返すと、None や空辞書が登録可能として扱われます。",
        correctCode: "return False",
        hints: [
          "最初の if は入力欠損の扱いです。",
          "`not user` は None と空辞書の両方に一致します。",
          "3行目は `return False` が正しいです。"
        ],
        steps: [
          categoryStep("boundary"),
          step("pattern", "どんな失敗パターン？", [
            {
              id: "invalid_empty_input_allowed",
              label: "空入力を正常扱い",
              description: "None や空辞書を許可してしまう",
              correct: true
            },
            {
              id: "wrong_operator",
              label: "演算子の取り違え",
              description: "加算・減算などの演算子が違う"
            },
            {
              id: "wrong_discount_unit",
              label: "割引単位の取り違え",
              description: "率と固定額を混同している"
            },
            {
              id: "missing_auth",
              label: "認可処理の欠落",
              description: "権限確認なしに処理している"
            }
          ]),
          step("fix", "正しい修正はどれ？", [
            {
              id: "fix-false",
              label: "False を返す",
              description: "入力欠損は登録不可にする",
              code: "return False",
              correct: true
            },
            {
              id: "fix-true",
              label: "True のまま",
              description: "入力欠損が登録可能になる"
            },
            {
              id: "fix-raise",
              label: "例外を送出する",
              description: "要件は True / False 返却"
            },
            {
              id: "fix-pass",
              label: "何もしない",
              description: "後続で None アクセスのリスクが残る"
            }
          ])
        ]
      },
      {
        id: "user-age-18-rejected",
        title: "18歳ちょうどが登録不可になっている",
        category: "boundary",
        pattern: "inclusive_boundary_rejected",
        startLine: 4,
        endLine: 5,
        difficulty: 2,
        summary: "18歳以上が登録可能なのに、18歳ちょうどを False にしている。",
        explanation:
          "要件は 18 歳以上です。`<= 18` では 18 歳を拒否してしまうため、18 未満だけを拒否する条件に直します。",
        correctCode: "if user.get(\"age\") is None or user.get(\"age\") < 18:\n        return False",
        hints: [
          "18歳ちょうどの例を条件式に当てはめよう。",
          "`<= 18` は 18 を拒否します。",
          "4行目は `< 18` を使い、None も別途拒否します。"
        ],
        steps: [
          categoryStep("boundary"),
          step("pattern", "どんな失敗パターン？", [
            {
              id: "inclusive_boundary_rejected",
              label: "含む境界の拒否",
              description: "以上・以下の境界値を誤って拒否している",
              correct: true
            },
            {
              id: "invalid_empty_input_allowed",
              label: "空入力を正常扱い",
              description: "None や空辞書を許可してしまう"
            },
            {
              id: "wrong_error_contract",
              label: "エラー契約の違反",
              description: "例外仕様や戻り値仕様が違う"
            },
            {
              id: "wrong_default",
              label: "デフォルト値の誤り",
              description: "省略時の初期値が仕様と違う"
            }
          ]),
          step("fix", "正しい修正はどれ？", [
            {
              id: "fix-age",
              label: "18未満だけ拒否する",
              description: "18歳ちょうどは登録可能にする",
              code: "if user.get(\"age\") is None or user.get(\"age\") < 18:\n        return False",
              correct: true
            },
            {
              id: "fix-age-gt",
              label: "18より大きい場合に拒否",
              description: "成人側を拒否してしまう"
            },
            {
              id: "fix-age-eq",
              label: "18歳だけ許可",
              description: "19歳以上が拒否される"
            },
            {
              id: "fix-age-remove",
              label: "年齢条件を削除",
              description: "17歳以下も登録可能になる"
            }
          ])
        ]
      },
      {
        id: "user-email-format-missing",
        title: "email の @ チェックがない",
        category: "spec",
        pattern: "partial_validation",
        startLine: 6,
        endLine: 7,
        difficulty: 2,
        summary: "空文字だけを拒否し、@ を含まないメールが通ってしまう。",
        explanation:
          "要件は空でないことに加えて @ を含むことです。`abc.example.com` のような値は空ではないため、現在のコードでは通過します。",
        correctCode: "email = user.get(\"email\")\n    if not email or \"@\" not in email:\n        return False",
        hints: [
          "email の要件は空チェックだけではありません。",
          "`abc.example.com` を入れたときに通るか考えよう。",
          "6行目付近で `@` の有無も確認します。"
        ],
        steps: [
          categoryStep("spec"),
          step("pattern", "どんな失敗パターン？", [
            {
              id: "partial_validation",
              label: "仕様の一部だけ検証",
              description: "複数条件のうち一部しかチェックしていない",
              correct: true
            },
            {
              id: "inclusive_boundary_rejected",
              label: "含む境界の拒否",
              description: "境界値の含有条件が逆"
            },
            {
              id: "permission_inversion",
              label: "権限条件の反転",
              description: "禁止すべきものを許可している"
            },
            {
              id: "state_leak",
              label: "状態の持ち越し",
              description: "前回の状態が次の判定に残る"
            }
          ]),
          step("fix", "正しい修正はどれ？", [
            {
              id: "fix-email",
              label: "空と @ を確認する",
              description: "email 欠損と形式条件を同時に満たす",
              code: "email = user.get(\"email\")\n    if not email or \"@\" not in email:\n        return False",
              correct: true
            },
            {
              id: "fix-email-empty",
              label: "空文字だけ確認する",
              description: "現在と同じで @ なしが通る"
            },
            {
              id: "fix-email-domain",
              label: "example.com だけ許可",
              description: "仕様にないドメイン制限を追加してしまう"
            },
            {
              id: "fix-email-none",
              label: "email チェックを削除",
              description: "不正メールがすべて通る"
            }
          ])
        ]
      },
      {
        id: "user-banned-allowed",
        title: "banned ユーザーが登録可能になっている",
        category: "security",
        pattern: "deny_rule_inverted",
        startLine: 8,
        endLine: 9,
        difficulty: 3,
        summary: "banned が True のユーザーは登録不可だが True を返している。",
        explanation:
          "禁止済みユーザーを登録可能にするのは安全側に倒れていない実装です。banned=True の場合は必ず False を返す必要があります。",
        correctCode: "if user.get(\"banned\") is True:\n        return False",
        hints: [
          "banned=True は許可ではなく拒否です。",
          "8-9行目の True / False が逆です。",
          "9行目は `return False` が正しいです。"
        ],
        steps: [
          categoryStep("security"),
          step("pattern", "どんな失敗パターン？", [
            {
              id: "deny_rule_inverted",
              label: "拒否ルールの反転",
              description: "禁止対象を許可している",
              correct: true
            },
            {
              id: "partial_validation",
              label: "仕様の一部だけ検証",
              description: "複数条件のうち一部しか見ていない"
            },
            {
              id: "wrong_operator",
              label: "演算子の取り違え",
              description: "算術演算が違う"
            },
            {
              id: "wrong_sort_key",
              label: "並び替えキーの誤り",
              description: "ランキングの基準が違う"
            }
          ]),
          step("fix", "正しい修正はどれ？", [
            {
              id: "fix-banned",
              label: "banned は False を返す",
              description: "禁止ユーザーを登録不可にする",
              code: "if user.get(\"banned\") is True:\n        return False",
              correct: true
            },
            {
              id: "fix-banned-true",
              label: "True のままにする",
              description: "禁止ユーザーを許可してしまう"
            },
            {
              id: "fix-banned-skip",
              label: "banned 条件を削除",
              description: "禁止状態を見なくなる"
            },
            {
              id: "fix-banned-raise",
              label: "例外を送出する",
              description: "要件は True / False 返却"
            }
          ])
        ]
      }
    ]
  },
  {
    id: "order-discount-permission-review",
    role: "Senior Review Interview",
    title: "注文割引と権限チェックの複合レビュー",
    difficultyLabel: "Boss",
    estimatedMinutes: 5,
    timeLimitSeconds: 300,
    codeLanguage: "python",
    requirements: [
      "items の price * qty を合計する",
      "coupon が VIP20 の場合は合計金額から 20% 割引する",
      "approved 済み注文を変更できるのは admin のみ",
      "gold 顧客の shipping_days は 2 日、それ以外は 5 日",
      "戻り値には total, can_change, shipping_days を含める"
    ],
    examples: [
      "1000円の VIP20 注文 -> total は 800",
      "approved 注文 + user.role='member' -> can_change は False",
      "gold 顧客 -> shipping_days は 2"
    ],
    constraints: [
      "割引は固定額ではなく率で扱う",
      "権限チェックは安全側に倒す",
      "1つの関数内で複数の要件を同時に照合する"
    ],
    code: `def decide_order(order, user):
    total = 0
    for item in order["items"]:
        total += item["price"] * item["qty"]
    if order.get("coupon") == "VIP20":
        total = total - 20
    if user["role"] != "admin" and order["status"] == "approved":
        can_change = True
    else:
        can_change = False
    if order.get("customer_tier") == "gold":
        shipping_days = 5
    else:
        shipping_days = 2
    return {"total": total, "can_change": can_change, "shipping_days": shipping_days}`,
    challengeHints: [
      "割引、権限、配送日数を別々に読んでから戻り値に流そう。",
      "VIP20 は 20円引きではなく 20% 引きです。approved 注文の変更権限にも注意。",
      "怪しい行は 6、8、12、14 行目です。"
    ],
    issues: [
      {
        id: "order-discount-fixed-amount",
        title: "VIP20 が20%割引ではなく20円引きになっている",
        category: "logic",
        pattern: "wrong_discount_unit",
        startLine: 6,
        endLine: 6,
        difficulty: 3,
        summary: "VIP20 は20%割引のはずだが、固定額20を引いている。",
        explanation:
          "1000円の注文なら 800円になるべきですが、現在は 980円になります。割引率と固定額の混同はレビューでよく出るAIコードのズレです。",
        correctCode: "total = total * 0.8",
        hints: [
          "VIP20 の 20 は円ではなくパーセントです。",
          "total から固定値を引くと金額規模に応じた割引になりません。",
          "6行目は `total = total * 0.8` が正しいです。"
        ],
        steps: [
          categoryStep("logic"),
          step("pattern", "どんな失敗パターン？", [
            {
              id: "wrong_discount_unit",
              label: "率と固定額の混同",
              description: "20% と 20円のように単位を取り違えている",
              correct: true
            },
            {
              id: "permission_inversion",
              label: "権限条件の反転",
              description: "許可すべき人と拒否すべき人が逆"
            },
            {
              id: "wrong_shipping_branch",
              label: "配送条件の反転",
              description: "顧客区分ごとの日数が逆"
            },
            {
              id: "missing_loop",
              label: "ループ処理の欠落",
              description: "明細を合計していない"
            }
          ]),
          step("fix", "正しい修正はどれ？", [
            {
              id: "fix-discount-rate",
              label: "20%割引にする",
              description: "合計額に 0.8 を掛ける",
              code: "total = total * 0.8",
              correct: true
            },
            {
              id: "fix-discount-20",
              label: "20を引くまま",
              description: "現在の不具合が残る"
            },
            {
              id: "fix-discount-add",
              label: "20を足す",
              description: "割引ではなく値上げになる"
            },
            {
              id: "fix-discount-zero",
              label: "0円にする",
              description: "仕様にない全額割引になる"
            }
          ])
        ]
      },
      {
        id: "order-permission-inverted",
        title: "approved注文をmemberが変更できてしまう",
        category: "security",
        pattern: "permission_inversion",
        startLine: 7,
        endLine: 10,
        difficulty: 4,
        summary: "approved済み注文はadminのみ変更可能だが、member側で can_change=True になる。",
        explanation:
          "条件式が `user['role'] != 'admin'` のときに True を返しているため、権限がないユーザーに変更を許可します。これはAIレビュー面接で見逃すとかなり痛いタイプです。",
        correctCode:
          "if order.get(\"status\") == \"approved\":\n        can_change = user.get(\"role\") == \"admin\"\n    else:\n        can_change = True",
        hints: [
          "approved 注文を変更できるのは admin だけです。",
          "`!= admin` のとき True になる分岐を追いかけよう。",
          "7-10行目は approved と role を安全側に組み直します。"
        ],
        steps: [
          categoryStep("security"),
          step("pattern", "どんな失敗パターン？", [
            {
              id: "permission_inversion",
              label: "権限条件の反転",
              description: "権限のないユーザーを許可している",
              correct: true
            },
            {
              id: "wrong_discount_unit",
              label: "率と固定額の混同",
              description: "割引単位が違う"
            },
            {
              id: "partial_validation",
              label: "仕様の一部だけ検証",
              description: "複数条件の一部しか見ていない"
            },
            {
              id: "wrong_error_contract",
              label: "エラー契約の違反",
              description: "例外仕様や戻り値仕様が違う"
            }
          ]),
          step("fix", "正しい修正はどれ？", [
            {
              id: "fix-permission",
              label: "approved は admin のみ許可",
              description: "承認済み注文の変更を安全側に倒す",
              code:
                "if order.get(\"status\") == \"approved\":\n        can_change = user.get(\"role\") == \"admin\"\n    else:\n        can_change = True",
              correct: true
            },
            {
              id: "fix-permission-current",
              label: "現在の分岐を維持",
              description: "member が変更可能なまま"
            },
            {
              id: "fix-permission-always",
              label: "常に True",
              description: "権限チェックを消してしまう"
            },
            {
              id: "fix-permission-always-false",
              label: "常に False",
              description: "未承認注文まで変更不可になる"
            }
          ])
        ]
      },
      {
        id: "order-gold-shipping-reversed",
        title: "gold顧客の配送日数が逆になっている",
        category: "spec",
        pattern: "wrong_shipping_branch",
        startLine: 11,
        endLine: 14,
        difficulty: 2,
        summary: "gold 顧客は2日配送だが5日になり、それ以外が2日になっている。",
        explanation:
          "顧客区分ごとの分岐が逆です。gold は優先配送なので 2 日、それ以外は 5 日という仕様に合わせます。",
        correctCode:
          "if order.get(\"customer_tier\") == \"gold\":\n        shipping_days = 2\n    else:\n        shipping_days = 5",
        hints: [
          "gold 顧客は優先配送です。",
          "gold とそれ以外の shipping_days が入れ替わっています。",
          "12行目は2、14行目は5です。"
        ],
        steps: [
          categoryStep("spec"),
          step("pattern", "どんな失敗パターン？", [
            {
              id: "wrong_shipping_branch",
              label: "条件分岐の値が逆",
              description: "条件ごとの代入値が入れ替わっている",
              correct: true
            },
            {
              id: "wrong_discount_unit",
              label: "率と固定額の混同",
              description: "割引単位が違う"
            },
            {
              id: "permission_inversion",
              label: "権限条件の反転",
              description: "許可・拒否が逆"
            },
            {
              id: "invalid_empty_input_allowed",
              label: "空入力を正常扱い",
              description: "None や空辞書を許可してしまう"
            }
          ]),
          step("fix", "正しい修正はどれ？", [
            {
              id: "fix-shipping",
              label: "goldを2日、それ以外を5日にする",
              description: "優先顧客の配送要件に合わせる",
              code:
                "if order.get(\"customer_tier\") == \"gold\":\n        shipping_days = 2\n    else:\n        shipping_days = 5",
              correct: true
            },
            {
              id: "fix-shipping-current",
              label: "現在のまま",
              description: "gold が遅くなる"
            },
            {
              id: "fix-shipping-all-two",
              label: "全員2日にする",
              description: "一般顧客の要件と違う"
            },
            {
              id: "fix-shipping-all-five",
              label: "全員5日にする",
              description: "gold の優先配送がなくなる"
            }
          ])
        ]
      }
    ]
  },
  {
    id: "python-truthiness-profile-review",
    role: "Python Basics Reviewer",
    title: "プロフィール表示のNone/空文字レビュー",
    difficultyLabel: "Basic",
    estimatedMinutes: 5,
    timeLimitSeconds: 300,
    codeLanguage: "python",
    requirements: [
      "nickname が None の場合だけ 'Anonymous' を返す",
      "nickname が空文字の場合は、ユーザーが意図して空にした表示名として空文字を返す",
      "age が None の場合は 'unknown' を返す",
      "age が数値の場合は文字列化して返す",
      "戻り値は name と age_label を持つ辞書"
    ],
    examples: [
      "build_profile({'nickname': None, 'age': 20}) -> {'name': 'Anonymous', 'age_label': '20'}",
      "build_profile({'nickname': '', 'age': None}) -> {'name': '', 'age_label': 'unknown'}"
    ],
    constraints: [
      "truthy/falsy ではなく None と空文字を分けて読む",
      "Python の `not value` は 0、空文字、空リスト、None をすべて False 扱いする"
    ],
    code: `def build_profile(user):
    nickname = user.get("nickname")
    if not nickname:
        nickname = "Anonymous"
    age = user.get("age")
    age_label = str(age)
    return {"name": nickname, "age_label": age_label}`,
    challengeHints: [
      "None と空文字の扱いを分けて読もう。",
      "`if not nickname` は None だけではなく空文字にも反応します。",
      "age が None のとき `str(None)` は 'None' になります。"
    ],
    issues: [
      {
        id: "profile-empty-name-overwritten",
        title: "空文字nicknameまでAnonymousに置き換えている",
        category: "boundary",
        pattern: "truthiness_conflates_empty_and_none",
        startLine: 3,
        endLine: 4,
        difficulty: 2,
        summary: "None の場合だけ置換する仕様だが、空文字も falsy として置換している。",
        explanation:
          "Python の `not nickname` は None だけでなく空文字にも一致します。要件では空文字は有効値なので、`is None` で判定する必要があります。",
        correctCode: "if nickname is None:\n        nickname = \"Anonymous\"",
        hints: [
          "空文字は falsy ですが、今回の仕様では有効値です。",
          "`not nickname` と `nickname is None` の違いを見よう。",
          "3行目は `if nickname is None:` が正しいです。"
        ],
        steps: reviewSteps(
          "boundary",
          {
            id: "truthiness_conflates_empty_and_none",
            label: "truthy/falsyの混同",
            description: "None と空文字など、異なる値を同じ falsy として扱っている"
          },
          {
            id: "fix-none-only",
            label: "Noneだけ判定する",
            description: "空文字は残し、Noneだけ既定値へ置換する",
            code: "if nickname is None:\n        nickname = \"Anonymous\""
          },
          [
            {
              id: "fix-not",
              label: "not判定のままにする",
              description: "空文字までAnonymousになる"
            },
            {
              id: "fix-strip",
              label: "stripしてから判定する",
              description: "空文字を有効値とする仕様に反する"
            },
            {
              id: "fix-always",
              label: "常にAnonymousにする",
              description: "nicknameがある場合も消えてしまう"
            }
          ]
        )
      },
      {
        id: "profile-age-none-string",
        title: "age None が 'unknown' ではなく 'None' になる",
        category: "spec",
        pattern: "none_rendered_as_string",
        startLine: 6,
        endLine: 6,
        difficulty: 1,
        summary: "age が None の場合は unknown のはずだが、str(None) で 'None' になる。",
        explanation:
          "None を文字列化すると 'None' です。表示仕様として unknown を返すなら、文字列化の前に None 分岐が必要です。",
        correctCode: "age_label = \"unknown\" if age is None else str(age)",
        hints: [
          "`str(None)` の結果を思い出そう。",
          "None の表示仕様は 'unknown' です。",
          "6行目で条件式を使うと直せます。"
        ],
        steps: reviewSteps(
          "spec",
          {
            id: "none_rendered_as_string",
            label: "None表示仕様の違反",
            description: "None をそのまま文字列化して、仕様と違う表示値にしている"
          },
          {
            id: "fix-age-label",
            label: "Noneならunknownにする",
            description: "None分岐後、数値だけ文字列化する",
            code: "age_label = \"unknown\" if age is None else str(age)"
          },
          [
            {
              id: "fix-str",
              label: "str(age)のまま",
              description: "'None' 表示が残る"
            },
            {
              id: "fix-zero",
              label: "Noneなら0にする",
              description: "仕様にない年齢を作ってしまう"
            },
            {
              id: "fix-empty",
              label: "Noneなら空文字にする",
              description: "仕様は unknown"
            }
          ]
        )
      }
    ]
  },
  {
    id: "python-loop-inventory-review",
    role: "Python Basics Reviewer",
    title: "在庫集計ループのcontinue/breakレビュー",
    difficultyLabel: "Basic",
    estimatedMinutes: 5,
    timeLimitSeconds: 300,
    codeLanguage: "python",
    requirements: [
      "stock が 0 の商品は集計対象外。ただし後続の商品は集計する",
      "reserved が True の商品は集計対象外",
      "集計値は対象商品の stock 合計",
      "件数ではなく数量を返す"
    ],
    examples: [
      "[{'stock': 0}, {'stock': 5, 'reserved': False}] -> 5",
      "[{'stock': 3, 'reserved': True}] -> 0"
    ],
    constraints: [
      "`break` はループ全体を止める",
      "`continue` はその要素だけスキップする"
    ],
    code: `def count_available(items):
    total = 0
    for item in items:
        if item["stock"] == 0:
            break
        if item.get("reserved"):
            total += item["stock"]
        total += 1
    return total`,
    challengeHints: [
      "0在庫の商品が先頭にある場合、後続の商品まで見られるか確認しよう。",
      "reserved=True は足すのではなく除外です。",
      "最後に足しているのは stock ではなく 1 です。"
    ],
    issues: [
      {
        id: "inventory-break-stops-loop",
        title: "0在庫で後続商品まで集計を止めている",
        category: "logic",
        pattern: "break_used_instead_of_continue",
        startLine: 4,
        endLine: 5,
        difficulty: 2,
        summary: "0在庫はその商品だけスキップすべきだが、breakでループ全体を止めている。",
        explanation:
          "`break` はループを終了します。要件では後続商品を集計する必要があるため、ここは `continue` です。",
        correctCode: "if item[\"stock\"] == 0:\n            continue",
        hints: [
          "0在庫は処理終了ではなくスキップです。",
          "`break` と `continue` の違いを確認しよう。",
          "5行目は `continue` が正しいです。"
        ],
        steps: reviewSteps(
          "logic",
          {
            id: "break_used_instead_of_continue",
            label: "break/continueの取り違え",
            description: "1要素だけスキップすべき場面でループ全体を終了している"
          },
          {
            id: "fix-continue",
            label: "continueにする",
            description: "0在庫の商品だけスキップする",
            code: "if item[\"stock\"] == 0:\n            continue"
          },
          [
            {
              id: "fix-pass",
              label: "passにする",
              description: "後続の加算処理へ進んでしまう"
            },
            {
              id: "fix-return",
              label: "return totalにする",
              description: "そこで関数が終わってしまう"
            },
            {
              id: "fix-remove",
              label: "条件を削除する",
              description: "0在庫も集計対象になる"
            }
          ]
        )
      },
      {
        id: "inventory-reserved-added",
        title: "予約済み商品を除外せず加算している",
        category: "spec",
        pattern: "exclude_rule_inverted",
        startLine: 6,
        endLine: 7,
        difficulty: 2,
        summary: "reserved=True は除外対象だが、stock を加算している。",
        explanation:
          "除外条件で加算しているため、予約済み在庫までavailableとして数えます。`continue` でスキップするのが自然です。",
        correctCode: "if item.get(\"reserved\"):\n            continue",
        hints: [
          "reserved=True は集計対象外です。",
          "今のコードは除外条件で加算しています。",
          "7行目は `continue` が正しいです。"
        ],
        steps: reviewSteps(
          "spec",
          {
            id: "exclude_rule_inverted",
            label: "除外条件の反転",
            description: "除外すべきデータを逆に集計している"
          },
          {
            id: "fix-reserved-continue",
            label: "予約済みはcontinue",
            description: "reserved=Trueの要素を集計から外す",
            code: "if item.get(\"reserved\"):\n            continue"
          },
          [
            {
              id: "fix-add-zero",
              label: "0を足す",
              description: "意味は近いが後続処理で1が足される"
            },
            {
              id: "fix-false-only",
              label: "Falseならcontinue",
              description: "未予約商品を除外してしまう"
            },
            {
              id: "fix-delete",
              label: "reserved条件を消す",
              description: "予約済みも集計される"
            }
          ]
        )
      },
      {
        id: "inventory-counts-items-not-stock",
        title: "stock合計ではなく件数を足している",
        category: "logic",
        pattern: "wrong_accumulator_value",
        startLine: 8,
        endLine: 8,
        difficulty: 1,
        summary: "available数量を返す仕様だが、1件ごとに1を足している。",
        explanation:
          "要件は対象商品のstock合計です。件数カウントでは数量が大きい商品を正しく扱えません。",
        correctCode: "total += item[\"stock\"]",
        hints: [
          "返すのは件数ではなく数量です。",
          "stockが5の商品は5を足す必要があります。",
          "8行目は `total += item[\"stock\"]` です。"
        ],
        steps: reviewSteps(
          "logic",
          {
            id: "wrong_accumulator_value",
            label: "加算値の取り違え",
            description: "件数と数量など、集計すべき値を取り違えている"
          },
          {
            id: "fix-stock",
            label: "stockを足す",
            description: "対象商品の在庫数量を加算する",
            code: "total += item[\"stock\"]"
          },
          [
            {
              id: "fix-one",
              label: "1を足すまま",
              description: "件数カウントになる"
            },
            {
              id: "fix-price",
              label: "priceを足す",
              description: "金額合計になってしまう"
            },
            {
              id: "fix-total",
              label: "totalを2倍する",
              description: "仕様にない増幅になる"
            }
          ]
        )
      }
    ]
  },
  {
    id: "python-mutable-default-copy-review",
    role: "Intermediate Python Reviewer",
    title: "mutable defaultとコピーの参照レビュー",
    difficultyLabel: "Intermediate",
    estimatedMinutes: 5,
    timeLimitSeconds: 300,
    codeLanguage: "python",
    requirements: [
      "add_tag は呼び出しごとに独立した tags リストを扱う",
      "tags 引数が省略された場合、新しい空リストから始める",
      "clone_user は元の user を変更せず、新しい辞書を返す",
      "clone_user の戻り値だけ active=True にする"
    ],
    examples: [
      "add_tag({}, 'a') と add_tag({}, 'b') はタグを共有しない",
      "clone_user(original) 後も original['active'] は変わらない"
    ],
    constraints: [
      "デフォルト引数のリストは関数定義時に1回だけ作られる",
      "辞書代入 `copied = user` はコピーではなく同じ参照"
    ],
    code: `def add_tag(user, tag, tags=[]):
    tags.append(tag)
    user["tags"] = tags
    return user

def clone_user(user):
    copied = user
    copied["active"] = True
    return copied`,
    challengeHints: [
      "デフォルト引数に [] があると、呼び出し間で共有されます。",
      "`copied = user` は新しい辞書を作っていません。",
      "参照共有によって、別ユーザーや元データに副作用が出ます。"
    ],
    issues: [
      {
        id: "mutable-default-tags-shared",
        title: "tags=[] が呼び出し間で共有される",
        category: "data_flow",
        pattern: "mutable_default_argument",
        startLine: 1,
        endLine: 2,
        difficulty: 3,
        summary: "デフォルト引数の空リストが共有され、別呼び出しのタグが混ざる。",
        explanation:
          "Python のデフォルト引数は関数定義時に評価されます。`tags=[]` は呼び出しごとに新規作成されず、前回のappend結果が残ります。",
        correctCode:
          "def add_tag(user, tag, tags=None):\n    if tags is None:\n        tags = []\n    tags.append(tag)",
        hints: [
          "デフォルト引数の [] は毎回作られるわけではありません。",
          "appendした結果が次の呼び出しにも残る可能性があります。",
          "Noneをデフォルトにして関数内で [] を作ります。"
        ],
        steps: reviewSteps(
          "data_flow",
          {
            id: "mutable_default_argument",
            label: "mutable default argument",
            description: "リストや辞書をデフォルト引数にして状態を共有している"
          },
          {
            id: "fix-default-none",
            label: "Noneデフォルトにする",
            description: "呼び出しごとに必要なら新しいリストを作る",
            code:
              "def add_tag(user, tag, tags=None):\n    if tags is None:\n        tags = []\n    tags.append(tag)"
          },
          [
            {
              id: "fix-clear",
              label: "tags.clear()する",
              description: "渡されたtagsまで破壊する"
            },
            {
              id: "fix-tuple",
              label: "tags=()にするだけ",
              description: "appendできず処理が壊れる"
            },
            {
              id: "fix-global",
              label: "global tagsにする",
              description: "共有状態がさらに強くなる"
            }
          ]
        )
      },
      {
        id: "clone-user-aliases-original",
        title: "clone_user が元の辞書を直接変更している",
        category: "data_flow",
        pattern: "alias_instead_of_copy",
        startLine: 7,
        endLine: 8,
        difficulty: 3,
        summary: "`copied = user` はコピーではなく同じ辞書への参照。",
        explanation:
          "辞書を代入しても新しい辞書は作られません。`copied['active'] = True` は元のuserも変更します。",
        correctCode: "copied = user.copy()\ncopied[\"active\"] = True",
        hints: [
          "代入はコピーではありません。",
          "copiedを変更するとuserも変わります。",
          "浅い辞書なら `user.copy()` が必要です。"
        ],
        steps: reviewSteps(
          "data_flow",
          {
            id: "alias_instead_of_copy",
            label: "コピーではなく参照共有",
            description: "新しいオブジェクトを作ったつもりで同じ参照を使っている"
          },
          {
            id: "fix-user-copy",
            label: "user.copy()を使う",
            description: "元の辞書を変えずに新しい辞書を更新する",
            code: "copied = user.copy()\ncopied[\"active\"] = True"
          },
          [
            {
              id: "fix-same",
              label: "copied = userのまま",
              description: "元データが変わる"
            },
            {
              id: "fix-delete",
              label: "active更新を消す",
              description: "戻り値をactiveにする要件を満たさない"
            },
            {
              id: "fix-list",
              label: "list(user)にする",
              description: "辞書ではなくキー一覧になる"
            }
          ]
        )
      }
    ]
  },
  {
    id: "python-exception-contract-review",
    role: "Intermediate Python Reviewer",
    title: "例外処理と戻り値契約のレビュー",
    difficultyLabel: "Intermediate",
    estimatedMinutes: 5,
    timeLimitSeconds: 300,
    codeLanguage: "python",
    requirements: [
      "raw を int に変換できる場合は {'ok': True, 'value': value} を返す",
      "raw が数値でない場合は {'ok': False, 'error': 'invalid'} を返す",
      "value が負数の場合は {'ok': False, 'error': 'negative'} を返す",
      "想定外の例外は握りつぶさない"
    ],
    examples: [
      "parse_quantity('3') -> {'ok': True, 'value': 3}",
      "parse_quantity('-1') -> {'ok': False, 'error': 'negative'}",
      "parse_quantity('x') -> {'ok': False, 'error': 'invalid'}"
    ],
    constraints: [
      "except Exception は広すぎることが多い",
      "エラー時に ok=True を返すと呼び出し側が失敗に気づけない"
    ],
    code: `def parse_quantity(raw):
    try:
        value = int(raw)
        if value < 0:
            raise ValueError("negative")
        return {"ok": True, "value": value}
    except Exception:
        return {"ok": True, "value": 0}`,
    challengeHints: [
      "invalid と negative を同じ扱いにしていないか確認しよう。",
      "except Exception は想定外のバグまで隠します。",
      "エラー時の ok 値が要件と逆です。"
    ],
    issues: [
      {
        id: "exception-too-broad",
        title: "except Exception で想定外の例外まで握りつぶす",
        category: "spec",
        pattern: "overbroad_exception",
        startLine: 7,
        endLine: 7,
        difficulty: 3,
        summary: "数値変換の失敗だけ扱えばよいのに、すべての例外を捕捉している。",
        explanation:
          "`except Exception` はプログラミングミスや外部障害まで通常値に変換します。レビューでは、捕捉する例外の範囲が業務契約に合っているかを見る必要があります。",
        correctCode: "except ValueError as error:",
        hints: [
          "捕捉したいのは数値変換や負数判定のValueErrorです。",
          "Exceptionは広すぎます。",
          "7行目はValueErrorに絞ります。"
        ],
        steps: reviewSteps(
          "spec",
          {
            id: "overbroad_exception",
            label: "広すぎる例外捕捉",
            description: "想定外の失敗まで正常系のように処理している"
          },
          {
            id: "fix-value-error",
            label: "ValueErrorに絞る",
            description: "想定した入力エラーだけを処理する",
            code: "except ValueError as error:"
          },
          [
            {
              id: "fix-bare",
              label: "exceptだけにする",
              description: "さらに広くなって危険"
            },
            {
              id: "fix-pass",
              label: "passする",
              description: "戻り値契約を満たさない"
            },
            {
              id: "fix-finally",
              label: "finallyで返す",
              description: "正常/異常の区別が崩れやすい"
            }
          ]
        )
      },
      {
        id: "exception-error-returns-ok",
        title: "エラー時に ok=True を返している",
        category: "logic",
        pattern: "error_reported_as_success",
        startLine: 8,
        endLine: 8,
        difficulty: 2,
        summary: "変換失敗や負数を成功として返すため、呼び出し側が誤判定する。",
        explanation:
          "戻り値契約ではエラー時は ok=False です。`ok=True, value=0` は、実際の0入力と不正入力を区別できません。",
        correctCode:
          "message = \"negative\" if str(error) == \"negative\" else \"invalid\"\n        return {\"ok\": False, \"error\": message}",
        hints: [
          "エラー時の ok は False です。",
          "value=0 は正常な0と区別できません。",
          "invalid/negative の error を返す必要があります。"
        ],
        steps: reviewSteps(
          "logic",
          {
            id: "error_reported_as_success",
            label: "失敗を成功として返す",
            description: "エラー状態なのに成功フラグや正常値を返している"
          },
          {
            id: "fix-error-return",
            label: "ok=Falseとerrorを返す",
            description: "呼び出し側が失敗理由を判断できる",
            code:
              "message = \"negative\" if str(error) == \"negative\" else \"invalid\"\n        return {\"ok\": False, \"error\": message}"
          },
          [
            {
              id: "fix-ok-true",
              label: "ok=Trueのまま",
              description: "失敗を成功扱いしてしまう"
            },
            {
              id: "fix-none",
              label: "Noneを返す",
              description: "戻り値契約が崩れる"
            },
            {
              id: "fix-zero",
              label: "value=0だけ返す",
              description: "失敗理由が失われる"
            }
          ]
        )
      }
    ]
  },
  {
    id: "python-async-await-review",
    role: "Advanced Python Reviewer",
    title: "async/awaitと認可分岐のレビュー",
    difficultyLabel: "Advanced",
    estimatedMinutes: 5,
    timeLimitSeconds: 300,
    codeLanguage: "python",
    requirements: [
      "profile と orders はどちらも非同期APIから取得する",
      "非同期APIの戻り値は必ず await してから使う",
      "disabled ユーザーには dashboard を返さず PermissionError を送出する",
      "正常時は profile と orders を含む辞書を返す"
    ],
    examples: [
      "disabled=True -> PermissionError",
      "disabled=False -> {'profile': ..., 'orders': ...}"
    ],
    constraints: [
      "coroutine object を辞書のように扱わない",
      "認可失敗を status ok として返さない"
    ],
    code: `async def load_dashboard(user_id, client):
    profile = client.get_profile(user_id)
    orders = await client.get_orders(user_id)
    if profile["disabled"]:
        return {"status": "ok", "orders": []}
    return {"profile": profile, "orders": orders}`,
    challengeHints: [
      "profile は await 済みの辞書でしょうか。",
      "disabled ユーザーに ok を返してよいか確認しよう。",
      "非同期APIと認可分岐の両方を見る問題です。"
    ],
    issues: [
      {
        id: "async-profile-not-awaited",
        title: "get_profile を await せず coroutine を使っている",
        category: "data_flow",
        pattern: "missing_await",
        startLine: 2,
        endLine: 4,
        difficulty: 4,
        summary: "profile が実データではなく coroutine object のまま使われる。",
        explanation:
          "非同期APIをawaitしないと、戻り値は実データではなくcoroutineです。次の `profile['disabled']` で壊れます。",
        correctCode: "profile = await client.get_profile(user_id)",
        hints: [
          "ordersはawaitされていますがprofileはどうでしょう。",
          "coroutine object は辞書ではありません。",
          "2行目に await が必要です。"
        ],
        steps: reviewSteps(
          "data_flow",
          {
            id: "missing_await",
            label: "await漏れ",
            description: "非同期処理の完了結果ではなくcoroutineを後続に渡している"
          },
          {
            id: "fix-await-profile",
            label: "get_profileをawaitする",
            description: "profileを実データとして取得してから使う",
            code: "profile = await client.get_profile(user_id)"
          },
          [
            {
              id: "fix-await-orders",
              label: "ordersのawaitを消す",
              description: "非同期処理がさらに壊れる"
            },
            {
              id: "fix-dict",
              label: "dict(profile)にする",
              description: "coroutineは辞書化できない"
            },
            {
              id: "fix-sync",
              label: "asyncを消す",
              description: "awaitを使う関数として成立しない"
            }
          ]
        )
      },
      {
        id: "async-disabled-returns-ok",
        title: "disabledユーザーにokレスポンスを返している",
        category: "security",
        pattern: "authorization_failure_as_success",
        startLine: 4,
        endLine: 5,
        difficulty: 4,
        summary: "アクセス不可のユーザーにdashboard相当の正常レスポンスを返している。",
        explanation:
          "disabled ユーザーはアクセス不可なので PermissionError で止めるべきです。空ordersでも status ok は許可成功に見えます。",
        correctCode:
          "if profile[\"disabled\"]:\n        raise PermissionError(\"disabled user\")",
        hints: [
          "disabledは正常ケースではありません。",
          "空のordersを返してもstatus okなら許可成功に見えます。",
          "5行目はPermissionErrorを送出します。"
        ],
        steps: reviewSteps(
          "security",
          {
            id: "authorization_failure_as_success",
            label: "認可失敗を成功扱い",
            description: "アクセス不可の状態を正常レスポンスとして返している"
          },
          {
            id: "fix-permission-error",
            label: "PermissionErrorを送出",
            description: "disabledユーザーのアクセスを止める",
            code: "if profile[\"disabled\"]:\n        raise PermissionError(\"disabled user\")"
          },
          [
            {
              id: "fix-empty",
              label: "空ordersを返す",
              description: "アクセス許可に見える"
            },
            {
              id: "fix-false",
              label: "Falseを返す",
              description: "戻り値契約と違う"
            },
            {
              id: "fix-ignore",
              label: "disabled判定を削除",
              description: "認可がなくなる"
            }
          ]
        )
      }
    ]
  },
  {
    id: "python-cache-auth-review",
    role: "Advanced Python Reviewer",
    title: "キャッシュと認可順序のレビュー",
    difficultyLabel: "Advanced",
    estimatedMinutes: 5,
    timeLimitSeconds: 300,
    codeLanguage: "python",
    requirements: [
      "レポート取得前に必ず can_view_reports を確認する",
      "権限のないユーザーにはキャッシュ済みデータも返さない",
      "キャッシュキーには tenant_id と report_id を含める",
      "別テナントの同じ report_id が混ざらないようにする"
    ],
    examples: [
      "can_view_reports=False -> PermissionError",
      "tenant A と tenant B の report_id=1 は別キャッシュ"
    ],
    constraints: [
      "キャッシュは認可チェックを迂回しやすい",
      "キーが粗いとテナント間データ漏洩につながる"
    ],
    code: `CACHE = {}

def get_report(user, report_id, db):
    key = report_id
    if key in CACHE:
        return CACHE[key]
    if not user["can_view_reports"]:
        raise PermissionError("forbidden")
    report = db.load_report(user["tenant_id"], report_id)
    CACHE[key] = report
    return report`,
    challengeHints: [
      "キャッシュヒット時に認可チェックが実行されるか確認しよう。",
      "report_idだけでテナントを区別できるでしょうか。",
      "キャッシュは高速化だけでなくセキュリティ境界にも関係します。"
    ],
    issues: [
      {
        id: "cache-before-auth",
        title: "キャッシュヒット時に認可チェックを迂回する",
        category: "security",
        pattern: "cache_before_authorization",
        startLine: 5,
        endLine: 8,
        difficulty: 5,
        summary: "権限確認より前にキャッシュを返すため、権限のないユーザーにもデータが返る。",
        explanation:
          "キャッシュはDBアクセスを省略しますが、認可を省略してはいけません。必ず権限確認後にキャッシュ参照します。",
        correctCode:
          "if not user[\"can_view_reports\"]:\n        raise PermissionError(\"forbidden\")\n    if key in CACHE:\n        return CACHE[key]",
        hints: [
          "キャッシュヒット時に7行目の権限チェックへ到達しますか。",
          "認可はキャッシュより前です。",
          "権限確認後にCACHEを返す順序へ直します。"
        ],
        steps: reviewSteps(
          "security",
          {
            id: "cache_before_authorization",
            label: "キャッシュが認可を迂回",
            description: "高速化のためのキャッシュがセキュリティチェックより先にある"
          },
          {
            id: "fix-auth-first",
            label: "認可チェックを先にする",
            description: "権限のないユーザーにはキャッシュも返さない",
            code:
              "if not user[\"can_view_reports\"]:\n        raise PermissionError(\"forbidden\")\n    if key in CACHE:\n        return CACHE[key]"
          },
          [
            {
              id: "fix-cache-only",
              label: "キャッシュだけ見る",
              description: "認可が完全に抜ける"
            },
            {
              id: "fix-db-first",
              label: "DB取得を先にする",
              description: "権限前にデータ取得してしまう"
            },
            {
              id: "fix-return-none",
              label: "権限なしはNone",
              description: "要件はPermissionError"
            }
          ]
        )
      },
      {
        id: "cache-key-misses-tenant",
        title: "キャッシュキーにtenant_idが含まれていない",
        category: "data_flow",
        pattern: "cache_key_too_coarse",
        startLine: 4,
        endLine: 4,
        difficulty: 4,
        summary: "report_id だけのキーでは、別テナントの同じIDが混ざる。",
        explanation:
          "マルチテナントでは同じ report_id が別テナントに存在しえます。キャッシュキーにはtenant_idも含める必要があります。",
        correctCode: "key = (user[\"tenant_id\"], report_id)",
        hints: [
          "report_idだけでテナントを区別できますか。",
          "db.load_reportにはtenant_idも渡しています。",
          "4行目はタプルキーにします。"
        ],
        steps: reviewSteps(
          "data_flow",
          {
            id: "cache_key_too_coarse",
            label: "粗すぎるキャッシュキー",
            description: "区別すべき条件がキーに含まれず、別データが混ざる"
          },
          {
            id: "fix-tenant-key",
            label: "tenant_idをキーに含める",
            description: "テナント別にキャッシュを分離する",
            code: "key = (user[\"tenant_id\"], report_id)"
          },
          [
            {
              id: "fix-report-only",
              label: "report_idだけのまま",
              description: "別テナントのデータが混ざる"
            },
            {
              id: "fix-user-object",
              label: "user全体をキーにする",
              description: "dictは通常ハッシュできない"
            },
            {
              id: "fix-constant",
              label: "固定キーにする",
              description: "全レポートが混ざる"
            }
          ]
        )
      }
    ]
  },
  {
    id: "python-generator-comprehension-review",
    role: "Advanced Python Reviewer",
    title: "generator消費とcomprehension条件レビュー",
    difficultyLabel: "Advanced",
    estimatedMinutes: 5,
    timeLimitSeconds: 300,
    codeLanguage: "python",
    requirements: [
      "passing は70点以上のスコア",
      "failed は70点未満のスコア",
      "passing_avg は passing の平均",
      "passing が空の場合、passing_avg は None",
      "generatorを一度消費した後に再利用しない"
    ],
    examples: [
      "summarize_scores([80, 90, 50]) -> passing_avg 85, failed [50]",
      "summarize_scores([40, 50]) -> passing_avg None, failed [40, 50]"
    ],
    constraints: [
      "generator は一度イテレートすると消費される",
      "リスト内包表記の条件が逆になっていないか確認する"
    ],
    code: `def summarize_scores(scores):
    passing = (score for score in scores if score >= 70)
    count = len(list(passing))
    passing_avg = sum(passing) / count
    failed = [score for score in scores if score >= 70]
    return {"passing_avg": passing_avg, "failed": failed}`,
    challengeHints: [
      "passingはgeneratorです。list(passing)の後にもう一度使えるでしょうか。",
      "passingが0件のとき平均計算はどうなりますか。",
      "failedの条件は70点以上でしょうか、未満でしょうか。"
    ],
    issues: [
      {
        id: "generator-reused-after-list",
        title: "generatorをlist化した後にsumで再利用している",
        category: "data_flow",
        pattern: "generator_consumed_twice",
        startLine: 2,
        endLine: 4,
        difficulty: 4,
        summary: "passing generator は len(list(passing)) で消費済みになり、sum(passing) は0になる。",
        explanation:
          "generatorは一度消費すると再利用できません。平均計算に使うなら、最初にlistへ固定してからcountとsumに使います。",
        correctCode:
          "passing = [score for score in scores if score >= 70]\n    count = len(passing)\n    passing_avg = None if count == 0 else sum(passing) / count",
        hints: [
          "list(passing) は generator を最後まで読みます。",
          "その後の sum(passing) には要素が残っていません。",
          "passingをリストにしてからcountとsumに使います。"
        ],
        steps: reviewSteps(
          "data_flow",
          {
            id: "generator_consumed_twice",
            label: "generatorの再利用",
            description: "一度消費したgeneratorを再度使おうとしている"
          },
          {
            id: "fix-list-passing",
            label: "passingをリスト化して使う",
            description: "countとsumの両方で同じ要素を使える",
            code:
              "passing = [score for score in scores if score >= 70]\n    count = len(passing)\n    passing_avg = None if count == 0 else sum(passing) / count"
          },
          [
            {
              id: "fix-keep-generator",
              label: "generatorのまま",
              description: "再利用問題が残る"
            },
            {
              id: "fix-count-zero",
              label: "countを常に0にする",
              description: "平均が計算できない"
            },
            {
              id: "fix-scores-sum",
              label: "scores全体をsumする",
              description: "不合格点まで平均に入る"
            }
          ]
        )
      },
      {
        id: "failed-filter-reversed",
        title: "failedに70点以上を入れている",
        category: "logic",
        pattern: "comprehension_filter_reversed",
        startLine: 5,
        endLine: 5,
        difficulty: 2,
        summary: "failed は70点未満のはずだが、条件が >= 70 になっている。",
        explanation:
          "リスト内包表記の条件が passing と同じです。failed は `score < 70` が正しい条件です。",
        correctCode: "failed = [score for score in scores if score < 70]",
        hints: [
          "failedは合格点ではありません。",
          "passingと同じ条件になっています。",
          "5行目は `< 70` が正しいです。"
        ],
        steps: reviewSteps(
          "logic",
          {
            id: "comprehension_filter_reversed",
            label: "内包表記フィルタの反転",
            description: "抽出条件が対象集合と逆、または別集合と同じになっている"
          },
          {
            id: "fix-failed-filter",
            label: "70点未満にする",
            description: "failedに不合格点だけを入れる",
            code: "failed = [score for score in scores if score < 70]"
          },
          [
            {
              id: "fix-passing-condition",
              label: ">=70のまま",
              description: "合格点がfailedに入る"
            },
            {
              id: "fix-all",
              label: "全スコアを入れる",
              description: "合格/不合格の区別がない"
            },
            {
              id: "fix-empty",
              label: "常に空リスト",
              description: "不合格者が消える"
            }
          ]
        )
      }
    ]
  }
];

const additionalHandmadeChallenges: InterviewChallenge[] = [
  {
    id: "password-reset-token-leak-review",
    role: "Security Review Candidate",
    title: "パスワード再設定APIのトークン漏えいレビュー",
    difficultyLabel: "Practical",
    estimatedMinutes: 5,
    timeLimitSeconds: 300,
    codeLanguage: "python",
    requirements: [
      "再設定トークンはトークンストアで生成する",
      "トークンはユーザーのメールにだけ送る",
      "APIレスポンスには成功状態だけを返す",
      "レスポンス、ログ、例外メッセージにトークンを含めない"
    ],
    examples: [
      "issue_reset_token(user, token_store) -> {'ok': True}",
      "レスポンスに token キーが含まれていたら不合格"
    ],
    constraints: [
      "秘密値は画面やAPIレスポンスに出さない",
      "メール送信とAPI応答の責務を分けて見る"
    ],
    code: `def issue_reset_token(user, token_store):
    token = token_store.create(user["id"])
    send_email(user["email"], f"reset: {token}")
    return {"ok": True, "token": token}`,
    challengeHints: [
      "生成した秘密値がどこへ流れているか追ってください。",
      "メールに送ることと、APIレスポンスに返すことは別です。",
      "怪しいのは最後の戻り値です。"
    ],
    issues: [
      {
        id: "reset-token-returned",
        title: "再設定トークンをAPIレスポンスに含めている",
        category: "security",
        pattern: "sensitive_token_exposed",
        startLine: 4,
        endLine: 4,
        difficulty: 3,
        summary: "メールで送るべき再設定トークンを、呼び出し元にも返している。",
        explanation:
          "再設定トークンはアカウント乗っ取りに直結する秘密値です。メール送信に使った後、APIレスポンスでは成功状態だけを返すべきです。",
        correctCode: `return {"ok": True}`,
        hints: [
          "token は秘密値です。",
          "レスポンスのキーに token が含まれています。",
          "4行目は ok だけ返せば十分です。"
        ],
        steps: reviewSteps(
          "security",
          {
            id: "sensitive_token_exposed",
            label: "秘密値のレスポンス漏えい",
            description: "トークンや認証情報をAPIレスポンスに含めている"
          },
          {
            id: "fix-ok-only",
            label: "成功状態だけ返す",
            description: "再設定トークンは返さず、処理成功だけを通知する",
            code: `return {"ok": True}`
          },
          [
            {
              id: "fix-mask-token",
              label: "トークンを一部マスクする",
              description: "一部でも返すと秘密値の露出が残る"
            },
            {
              id: "fix-email-remove",
              label: "メール送信を消す",
              description: "ユーザーが再設定できなくなる"
            },
            {
              id: "fix-return-user",
              label: "ユーザー情報を返す",
              description: "不要な個人情報の露出が増える"
            }
          ]
        )
      }
    ]
  },
  {
    id: "shipping-threshold-surcharge-review",
    role: "Commerce Logic Reviewer",
    title: "送料しきい値と海外加算のレビュー",
    difficultyLabel: "Warm-up",
    estimatedMinutes: 5,
    timeLimitSeconds: 300,
    codeLanguage: "python",
    requirements: [
      "購入金額が10000円以上なら基本送料は無料",
      "購入金額が10000円未満なら基本送料は800円",
      "配送先がJP以外なら海外加算1200円を追加する",
      "配送先がJPなら海外加算は不要"
    ],
    examples: [
      "shipping_fee(10000, 'JP') -> 0",
      "shipping_fee(9000, 'US') -> 2000"
    ],
    constraints: [
      "以上と超過の違いを見る",
      "国コード条件の向きを確認する"
    ],
    code: `def shipping_fee(subtotal, country):
    fee = 800
    if subtotal > 10000:
        fee = 0
    if country == "JP":
        fee += 1200
    return fee`,
    challengeHints: [
      "10000円ちょうどのケースを頭で実行してください。",
      "海外加算がJPに付いていないか確認してください。",
      "怪しいのは比較演算子と国コード条件です。"
    ],
    issues: [
      {
        id: "free-shipping-excludes-equal",
        title: "10000円ちょうどが送料無料にならない",
        category: "boundary",
        pattern: "inclusive_threshold_excluded",
        startLine: 3,
        endLine: 3,
        difficulty: 1,
        summary: "仕様は10000円以上だが、コードは10000円超過だけを無料にしている。",
        explanation:
          "「以上」は境界値を含みます。10000円ちょうどの購入で送料800円になるため、条件は >= 10000 にする必要があります。",
        correctCode: `if subtotal >= 10000:`,
        hints: [
          "仕様の『以上』に注目してください。",
          "10000円ちょうどはどちらに入るべきでしょうか。",
          "3行目は >= が正しいです。"
        ],
        steps: reviewSteps(
          "boundary",
          {
            id: "inclusive_threshold_excluded",
            label: "境界値を含めていない",
            description: "以上・以下の条件なのに、超過・未満として実装している"
          },
          {
            id: "fix-gte-threshold",
            label: "以上条件にする",
            description: "10000円ちょうども送料無料に含める",
            code: `if subtotal >= 10000:`
          },
          [
            {
              id: "fix-lte",
              label: "10000円以下にする",
              description: "無料対象が逆になる"
            },
            {
              id: "fix-raise",
              label: "10000円なら例外にする",
              description: "仕様にないエラーを増やしている"
            },
            {
              id: "fix-fee-zero",
              label: "初期送料を0円にする",
              description: "10000円未満まで無料になってしまう"
            }
          ]
        )
      },
      {
        id: "domestic-surcharge-added",
        title: "国内配送に海外加算を付けている",
        category: "logic",
        pattern: "condition_direction_reversed",
        startLine: 5,
        endLine: 6,
        difficulty: 1,
        summary: "JP以外に加算すべき1200円を、JPのときに加算している。",
        explanation:
          "海外加算は配送先がJP以外のときだけ必要です。条件の向きが逆なので、国内配送が高くなり海外配送が安くなります。",
        correctCode: `if country != "JP":
        fee += 1200`,
        hints: [
          "海外加算はどの国に付くべきか確認してください。",
          "現在の条件は country == 'JP' です。",
          "5行目は != が正しいです。"
        ],
        steps: reviewSteps(
          "logic",
          {
            id: "condition_direction_reversed",
            label: "条件の向きが逆",
            description: "対象にすべきケースと除外すべきケースが反対になっている"
          },
          {
            id: "fix-not-jp",
            label: "JP以外に加算する",
            description: "海外配送だけ1200円を追加する",
            code: `if country != "JP":
        fee += 1200`
          },
          [
            {
              id: "fix-remove-fee",
              label: "加算処理を削除する",
              description: "海外送料が表現できなくなる"
            },
            {
              id: "fix-us-only",
              label: "USだけに加算する",
              description: "他の海外配送が漏れる"
            },
            {
              id: "fix-negative",
              label: "JPなら減額する",
              description: "仕様にない割引を追加している"
            }
          ]
        )
      }
    ]
  },
  {
    id: "reservation-adjacent-overlap-review",
    role: "Booking Systems Reviewer",
    title: "予約時間の隣接判定レビュー",
    difficultyLabel: "Practical",
    estimatedMinutes: 5,
    timeLimitSeconds: 300,
    codeLanguage: "python",
    requirements: [
      "同じ部屋で時間帯が重なる予約は拒否する",
      "別の部屋の予約は判定対象外",
      "既存予約の終了時刻と新規予約の開始時刻が同じなら予約可能",
      "新規予約の終了時刻と既存予約の開始時刻が同じなら予約可能"
    ],
    examples: [
      "existing 10:00-11:00, request 11:00-12:00 -> True",
      "existing 10:00-11:00, request 10:30-11:30 -> False"
    ],
    constraints: [
      "隣接と重複を分ける",
      "同じ部屋だけを見る"
    ],
    code: `def can_book(existing, request):
    for booking in existing:
        if booking["room_id"] != request["room_id"]:
            continue
        if request["start"] <= booking["end"] and request["end"] >= booking["start"]:
            return False
    return True`,
    challengeHints: [
      "11:00終了と11:00開始は重複でしょうか。",
      "重複条件は境界を含めるべきか考えてください。",
      "怪しいのは5行目の比較演算子です。"
    ],
    issues: [
      {
        id: "adjacent-booking-blocked",
        title: "隣接する予約を重複扱いしている",
        category: "boundary",
        pattern: "adjacent_interval_treated_as_overlap",
        startLine: 5,
        endLine: 5,
        difficulty: 2,
        summary: "終了時刻と開始時刻が同じだけの予約も拒否している。",
        explanation:
          "時間帯の重複判定では、隣接は重複ではありません。開始が既存終了より前、かつ終了が既存開始より後の場合だけ重複です。",
        correctCode: `if request["start"] < booking["end"] and request["end"] > booking["start"]:`,
        hints: [
          "等号があると境界ぴったりも重複になります。",
          "隣り合う予約は許可する仕様です。",
          "5行目は < と > の組み合わせにします。"
        ],
        steps: reviewSteps(
          "boundary",
          {
            id: "adjacent_interval_treated_as_overlap",
            label: "隣接区間を重複扱い",
            description: "境界が同じだけの時間帯を、実際に重なっているものとして扱っている"
          },
          {
            id: "fix-open-interval-overlap",
            label: "等号を外した重複条件にする",
            description: "隣接は許可し、実際に重なる区間だけ拒否する",
            code: `if request["start"] < booking["end"] and request["end"] > booking["start"]:`
          },
          [
            {
              id: "fix-or",
              label: "andをorにする",
              description: "ほとんどの予約が重複扱いになる"
            },
            {
              id: "fix-room-remove",
              label: "部屋判定を消す",
              description: "別部屋の予約まで拒否する"
            },
            {
              id: "fix-always-true",
              label: "常に予約可能にする",
              description: "本当の重複を防げない"
            }
          ]
        )
      }
    ]
  },
  {
    id: "feature-rollout-percentage-review",
    role: "Platform Feature Flag Reviewer",
    title: "Feature Flagの0%配信レビュー",
    difficultyLabel: "Practical",
    estimatedMinutes: 5,
    timeLimitSeconds: 300,
    codeLanguage: "python",
    requirements: [
      "flag.enabled が False なら誰にも配信しない",
      "excluded_tenants に含まれるテナントには配信しない",
      "percentage は 0 から 100 の配信率として扱う",
      "percentage が 0 の場合は誰にも配信しない"
    ],
    examples: [
      "percentage=0 -> False for every user",
      "user.tenant_id in excluded_tenants -> False"
    ],
    constraints: [
      "0%と100%の境界を見る",
      "除外テナントは配信率より優先する"
    ],
    code: `def is_enabled(user, flag):
    if not flag["enabled"]:
        return False
    bucket = hash(user["id"]) % 100
    if bucket <= flag["percentage"]:
        return True
    return False`,
    challengeHints: [
      "0%配信でbucket 0のユーザーはどうなるか見てください。",
      "excluded_tenants の仕様がコードにありますか。",
      "配信率の境界と除外条件の2つを見ます。"
    ],
    issues: [
      {
        id: "zero-percent-enables-bucket-zero",
        title: "0%配信でも一部ユーザーに有効化される",
        category: "boundary",
        pattern: "percentage_boundary_inclusive",
        startLine: 5,
        endLine: 6,
        difficulty: 2,
        summary: "bucket <= percentage のため、percentage=0 でも bucket=0 が有効になる。",
        explanation:
          "bucket は0から99です。0%なら誰にも配信しないため、比較は bucket < percentage にする必要があります。",
        correctCode: `if bucket < flag["percentage"]:
        return True`,
        hints: [
          "bucket は0になることがあります。",
          "0%のときに <= 0 は成立します。",
          "5行目は < が正しいです。"
        ],
        steps: reviewSteps(
          "boundary",
          {
            id: "percentage_boundary_inclusive",
            label: "0%境界を含めている",
            description: "配信率0%なのに、境界値のユーザーを含めている"
          },
          {
            id: "fix-strict-percentage",
            label: "配信率未満にする",
            description: "0%なら0人、100%なら全bucketが対象になる",
            code: `if bucket < flag["percentage"]:
        return True`
          },
          [
            {
              id: "fix-greater",
              label: "bucket > percentageにする",
              description: "配信率の意味が逆になる"
            },
            {
              id: "fix-random",
              label: "randomで判定する",
              description: "同じユーザーで結果が揺れる"
            },
            {
              id: "fix-plus-one",
              label: "bucketに1を足す",
              description: "100%や境界の扱いが分かりにくくなる"
            }
          ]
        )
      },
      {
        id: "excluded-tenants-ignored",
        title: "除外テナントの指定を見ていない",
        category: "spec",
        pattern: "required_guard_missing",
        startLine: 2,
        endLine: 3,
        difficulty: 3,
        summary: "excluded_tenants に入っているテナントでも、配信率判定に進んでしまう。",
        explanation:
          "除外テナントは明示的な拒否条件です。enabled 判定の後、bucket計算より前に tenant_id を確認する必要があります。",
        correctCode: `if user["tenant_id"] in flag.get("excluded_tenants", []):
        return False`,
        hints: [
          "仕様にある excluded_tenants がコードに出てきません。",
          "配信率より先に拒否すべき条件です。",
          "bucket計算の前にガードを入れます。"
        ],
        steps: reviewSteps(
          "spec",
          {
            id: "required_guard_missing",
            label: "必須ガード条件の欠落",
            description: "仕様にある除外条件がコードに実装されていない"
          },
          {
            id: "fix-excluded-tenant-guard",
            label: "除外テナントを先に拒否する",
            description: "対象外テナントには配信率に関係なくFalseを返す",
            code: `if user["tenant_id"] in flag.get("excluded_tenants", []):
        return False`
          },
          [
            {
              id: "fix-after-return",
              label: "return Trueの後に追加する",
              description: "到達しないコードになる"
            },
            {
              id: "fix-enabled-remove",
              label: "enabled判定を削除する",
              description: "flag全体の停止が効かなくなる"
            },
            {
              id: "fix-percentage-zero",
              label: "percentageを0に固定する",
              description: "通常配信ができなくなる"
            }
          ]
        )
      }
    ]
  },
  {
    id: "csv-import-email-validation-review",
    role: "Data Import Reviewer",
    title: "CSVインポートのメール検証レビュー",
    difficultyLabel: "Practical",
    estimatedMinutes: 5,
    timeLimitSeconds: 300,
    codeLanguage: "python",
    requirements: [
      "email は前後の空白を取り除いて検証する",
      "email に @ がなければエラーとして止める",
      "不正行を黙ってスキップしない",
      "age は整数に変換して保存する"
    ],
    examples: [
      "' a@example.com ' -> 'a@example.com'",
      "'invalid-email' -> ValueError"
    ],
    constraints: [
      "入力の正規化と検証順序を見る",
      "エラーを黙殺していないか確認する"
    ],
    code: `def import_users(rows):
    users = []
    for row in rows:
        email = row["email"]
        if "@" not in email:
            continue
        users.append({"email": email, "age": int(row["age"])})
    return users`,
    challengeHints: [
      "空白付きメールを想像してください。",
      "不正なメールをcontinueしてよい仕様でしょうか。",
      "検証前の正規化とエラー契約を見ます。"
    ],
    issues: [
      {
        id: "email-not-stripped",
        title: "メールアドレスの前後空白を除去していない",
        category: "data_flow",
        pattern: "input_normalization_missing",
        startLine: 4,
        endLine: 4,
        difficulty: 2,
        summary: "emailをそのまま使っているため、空白付きの値が保存される。",
        explanation:
          "CSVには前後空白が混ざりがちです。仕様ではstripしてから検証・保存する必要があります。",
        correctCode: `email = row["email"].strip()`,
        hints: [
          "CSV入力は余計な空白を含みます。",
          "検証前に正規化する必要があります。",
          "4行目で strip() します。"
        ],
        steps: reviewSteps(
          "data_flow",
          {
            id: "input_normalization_missing",
            label: "入力正規化漏れ",
            description: "検証や保存の前に入力値を正規化していない"
          },
          {
            id: "fix-strip-email",
            label: "stripしてから使う",
            description: "前後空白を落としてから検証・保存する",
            code: `email = row["email"].strip()`
          },
          [
            {
              id: "fix-lower-only",
              label: "lowerだけかける",
              description: "前後空白は残る"
            },
            {
              id: "fix-int-email",
              label: "intに変換する",
              description: "メールアドレスに対して不正な変換"
            },
            {
              id: "fix-no-change",
              label: "そのまま使う",
              description: "空白付き値が保存される"
            }
          ]
        )
      },
      {
        id: "invalid-email-silently-skipped",
        title: "不正なメール行を黙ってスキップしている",
        category: "spec",
        pattern: "invalid_input_silently_ignored",
        startLine: 5,
        endLine: 6,
        difficulty: 3,
        summary: "仕様ではエラーにすべき不正メールを continue で消している。",
        explanation:
          "インポートで黙って行を捨てると、利用者は欠落に気づけません。仕様どおり ValueError などで止めるべきです。",
        correctCode: `if "@" not in email:
            raise ValueError(f"invalid email: {email}")`,
        hints: [
          "仕様はスキップではなくエラーです。",
          "continue は行を消してしまいます。",
          "6行目は例外送出に変えます。"
        ],
        steps: reviewSteps(
          "spec",
          {
            id: "invalid_input_silently_ignored",
            label: "不正入力の黙殺",
            description: "不正な入力をエラーにせず、何もなかったように捨てている"
          },
          {
            id: "fix-raise-invalid-email",
            label: "不正メールで例外にする",
            description: "欠落を隠さず、呼び出し元に失敗を伝える",
            code: `if "@" not in email:
            raise ValueError(f"invalid email: {email}")`
          },
          [
            {
              id: "fix-return-users",
              label: "その場でusersを返す",
              description: "残り行の処理が止まり、理由も伝わらない"
            },
            {
              id: "fix-empty-email",
              label: "空文字に置き換える",
              description: "不正データが保存される"
            },
            {
              id: "fix-log-only",
              label: "ログだけ出して続ける",
              description: "仕様のエラー契約を満たさない"
            }
          ]
        )
      }
    ]
  },
  {
    id: "pagination-one-based-review",
    role: "API Pagination Reviewer",
    title: "1始まりページングの開始位置レビュー",
    difficultyLabel: "Warm-up",
    estimatedMinutes: 5,
    timeLimitSeconds: 300,
    codeLanguage: "python",
    requirements: [
      "page は1始まりで指定する",
      "page=1 のとき最初の要素から返す",
      "page が1未満なら ValueError を送出する",
      "per_page 件だけ返す"
    ],
    examples: [
      "paginate([1,2,3], page=1, per_page=2) -> [1,2]",
      "paginate([1,2,3], page=2, per_page=2) -> [3]"
    ],
    constraints: [
      "1始まりと0始まりの変換を見る",
      "不正ページ番号を見逃さない"
    ],
    code: `def paginate(items, page, per_page):
    start = page * per_page
    end = start + per_page
    return items[start:end]`,
    challengeHints: [
      "page=1, per_page=10ならstartは何になるべきでしょうか。",
      "page=0は仕様上有効でしょうか。",
      "2行目に2つの観点があります。"
    ],
    issues: [
      {
        id: "page-one-skips-first-window",
        title: "page=1で先頭ページを飛ばしている",
        category: "boundary",
        pattern: "one_based_index_not_converted",
        startLine: 2,
        endLine: 2,
        difficulty: 1,
        summary: "1始まりのpageを0始まりのslice開始位置へ変換していない。",
        explanation:
          "page=1ならstartは0です。現在は page * per_page なので、1ページ目でper_page件ぶん飛ばしてしまいます。",
        correctCode: `start = (page - 1) * per_page`,
        hints: [
          "sliceの開始位置は0始まりです。",
          "page=1ならstart=0です。",
          "2行目は (page - 1) を使います。"
        ],
        steps: reviewSteps(
          "boundary",
          {
            id: "one_based_index_not_converted",
            label: "1始まりを0始まりに変換していない",
            description: "ユーザー指定のpage番号と配列indexの基準がずれている"
          },
          {
            id: "fix-page-minus-one",
            label: "page-1で開始位置を作る",
            description: "1ページ目をslice開始0に変換する",
            code: `start = (page - 1) * per_page`
          },
          [
            {
              id: "fix-plus-one",
              label: "page+1にする",
              description: "さらに後ろへずれる"
            },
            {
              id: "fix-end-only",
              label: "endだけ直す",
              description: "開始位置のずれが残る"
            },
            {
              id: "fix-zero-start",
              label: "常にstart=0にする",
              description: "2ページ目以降が取れなくなる"
            }
          ]
        )
      },
      {
        id: "page-zero-not-rejected",
        title: "pageが1未満の入力を拒否していない",
        category: "spec",
        pattern: "missing_invalid_page_guard",
        startLine: 2,
        endLine: 2,
        difficulty: 2,
        summary: "page=0 や負数でもslice計算に進んでしまう。",
        explanation:
          "仕様ではpageが1未満ならValueErrorです。sliceは負数も動くため、ガードなしだと静かに誤ったページを返します。",
        correctCode: `if page < 1:
        raise ValueError("page must be >= 1")`,
        hints: [
          "Pythonのsliceは負数でも動きます。",
          "仕様は例外を要求しています。",
          "start計算の前にpageを検証します。"
        ],
        steps: reviewSteps(
          "spec",
          {
            id: "missing_invalid_page_guard",
            label: "不正ページ番号の検証漏れ",
            description: "仕様上拒否すべきpageを計算に流している"
          },
          {
            id: "fix-page-guard",
            label: "page<1でValueError",
            description: "slice計算の前に不正入力を止める",
            code: `if page < 1:
        raise ValueError("page must be >= 1")`
          },
          [
            {
              id: "fix-abs",
              label: "abs(page)にする",
              description: "不正入力を別の意味に変えてしまう"
            },
            {
              id: "fix-empty",
              label: "空配列を返す",
              description: "仕様の例外契約と違う"
            },
            {
              id: "fix-page-one",
              label: "page=1に丸める",
              description: "入力ミスを隠してしまう"
            }
          ]
        )
      }
    ]
  },
  {
    id: "rate-limit-global-bucket-review",
    role: "API Reliability Reviewer",
    title: "Rate Limitのグローバル共有バケットレビュー",
    difficultyLabel: "Intermediate",
    estimatedMinutes: 5,
    timeLimitSeconds: 300,
    codeLanguage: "python",
    requirements: [
      "制限は user_id と ip の組み合わせごとに適用する",
      "直近60秒のリクエストだけ数える",
      "60秒あたり100回以上なら拒否する",
      "別ユーザーのアクセスで他ユーザーをブロックしない"
    ],
    examples: [
      "user Aの100回到達でuser Bは影響を受けない",
      "同じuser_idとipの101回目 -> False"
    ],
    constraints: [
      "バケットキーの粒度を見る",
      "共有状態が広すぎないか確認する"
    ],
    code: `BUCKETS = {}

def allow_request(user_id, ip, now):
    key = "global"
    hits = BUCKETS.get(key, [])
    hits = [t for t in hits if now - t < 60]
    if len(hits) >= 100:
        return False
    hits.append(now)
    BUCKETS[key] = hits
    return True`,
    challengeHints: [
      "key が誰を表しているか見てください。",
      "user_id と ip が引数にあるのに使われているでしょうか。",
      "全員同じバケットなら何が起きるでしょうか。"
    ],
    issues: [
      {
        id: "rate-limit-global-key",
        title: "全ユーザーで同じRate Limitバケットを共有している",
        category: "data_flow",
        pattern: "state_key_too_coarse",
        startLine: 4,
        endLine: 4,
        difficulty: 3,
        summary: "keyが固定文字列のため、全ユーザー・全IPのアクセスが同じ制限に入る。",
        explanation:
          "仕様では user_id と ip の組み合わせごとに制限します。固定キーでは、あるユーザーの大量アクセスが他ユーザーまでブロックします。",
        correctCode: `key = (user_id, ip)`,
        hints: [
          "key = 'global' は粒度が粗すぎます。",
          "引数の user_id と ip が未使用です。",
          "4行目はタプルキーにします。"
        ],
        steps: reviewSteps(
          "data_flow",
          {
            id: "state_key_too_coarse",
            label: "状態キーが粗すぎる",
            description: "分けるべき利用者や条件を同じ状態として扱っている"
          },
          {
            id: "fix-user-ip-key",
            label: "user_idとipをキーにする",
            description: "制限バケットを利用者とIPごとに分離する",
            code: `key = (user_id, ip)`
          },
          [
            {
              id: "fix-ip-only",
              label: "ipだけをキーにする",
              description: "共有IPのユーザー同士が巻き込まれる"
            },
            {
              id: "fix-user-only",
              label: "user_idだけをキーにする",
              description: "仕様のip粒度を落としている"
            },
            {
              id: "fix-no-bucket",
              label: "BUCKETSを使わない",
              description: "過去リクエストを数えられない"
            }
          ]
        )
      }
    ]
  },
  {
    id: "payment-idempotency-order-review",
    role: "Payment Reliability Reviewer",
    title: "決済APIの冪等性チェック順序レビュー",
    difficultyLabel: "Advanced",
    estimatedMinutes: 5,
    timeLimitSeconds: 300,
    codeLanguage: "python",
    requirements: [
      "同じ idempotency_key のリクエストは同じ結果を返す",
      "既存結果がある場合、決済ゲートウェイを再実行しない",
      "初回だけ gateway.charge を呼び出す",
      "決済後は idempotency_key と結果を保存する"
    ],
    examples: [
      "同じidempotency_keyの2回目 -> gateway.chargeを呼ばない",
      "初回 -> chargeして保存する"
    ],
    constraints: [
      "副作用の前に冪等性を確認する",
      "キャッシュは処理結果の再利用であり、二重実行の後始末ではない"
    ],
    code: `def charge_order(order, request, gateway, store):
    charge = gateway.charge(order["amount"], request["card"])
    if store.exists(request["idempotency_key"]):
        return store.get(request["idempotency_key"])
    store.save(request["idempotency_key"], charge)
    return charge`,
    challengeHints: [
      "gateway.charge は副作用です。",
      "同じキーの2回目でも先にchargeしていませんか。",
      "冪等性チェックの順序を見ます。"
    ],
    issues: [
      {
        id: "charge-before-idempotency-check",
        title: "冪等性チェックより先に決済を実行している",
        category: "data_flow",
        pattern: "side_effect_before_idempotency_check",
        startLine: 2,
        endLine: 4,
        difficulty: 5,
        summary: "既存結果の確認前に gateway.charge を呼ぶため、リトライで二重課金が起きる。",
        explanation:
          "冪等性キーは副作用を起こす前に見る必要があります。既存結果があればchargeを呼ばずに保存済み結果を返します。",
        correctCode: `if store.exists(request["idempotency_key"]):
        return store.get(request["idempotency_key"])
    charge = gateway.charge(order["amount"], request["card"])`,
        hints: [
          "chargeは取り消しにくい副作用です。",
          "store.existsの前にchargeされています。",
          "冪等性チェックを2行目より前に移動します。"
        ],
        steps: reviewSteps(
          "data_flow",
          {
            id: "side_effect_before_idempotency_check",
            label: "冪等性チェック前の副作用",
            description: "再実行を防ぐ確認より先に、外部副作用を発生させている"
          },
          {
            id: "fix-idempotency-first",
            label: "保存済み結果を先に確認する",
            description: "既存キーなら決済せずに既存結果を返す",
            code: `if store.exists(request["idempotency_key"]):
        return store.get(request["idempotency_key"])
    charge = gateway.charge(order["amount"], request["card"])`
          },
          [
            {
              id: "fix-delete-key",
              label: "既存キーを削除する",
              description: "冪等性の意味がなくなる"
            },
            {
              id: "fix-charge-twice",
              label: "chargeを再試行する",
              description: "二重課金リスクが増える"
            },
            {
              id: "fix-return-none",
              label: "既存キーならNoneを返す",
              description: "同じ結果を返す仕様を満たさない"
            }
          ]
        )
      }
    ]
  },
  {
    id: "deadline-timezone-aware-review",
    role: "Time Handling Reviewer",
    title: "UTC期限判定のタイムゾーンレビュー",
    difficultyLabel: "Intermediate",
    estimatedMinutes: 5,
    timeLimitSeconds: 300,
    codeLanguage: "python",
    requirements: [
      "deadline_iso はUTCのISO文字列として扱う",
      "現在時刻もUTCで比較する",
      "aware datetime と naive datetime を混ぜない",
      "期限を過ぎていれば True を返す"
    ],
    examples: [
      "deadline='2026-06-07T00:00:00+00:00' はUTC基準で比較する",
      "ローカルタイムゾーンに依存しない"
    ],
    constraints: [
      "日時のnaive/awareを確認する",
      "サーバーのローカル時刻に依存していないか見る"
    ],
    code: `from datetime import datetime

def is_expired(deadline_iso):
    deadline = datetime.fromisoformat(deadline_iso)
    return datetime.now() > deadline`,
    challengeHints: [
      "datetime.now() はタイムゾーン付きでしょうか。",
      "deadline_iso はUTCとして扱う仕様です。",
      "比較する2つのdatetimeの基準を揃えます。"
    ],
    issues: [
      {
        id: "timezone-naive-now",
        title: "ローカルのnaiveな現在時刻でUTC期限を比較している",
        category: "boundary",
        pattern: "naive_datetime_compared_with_utc",
        startLine: 5,
        endLine: 5,
        difficulty: 4,
        summary: "UTC期限に対して datetime.now() のローカルnaive時刻を使っている。",
        explanation:
          "期限判定はタイムゾーンのずれがそのままバグになります。UTC基準のaware datetimeで比較すべきです。",
        correctCode: `return datetime.now(timezone.utc) > deadline`,
        hints: [
          "datetime.now() はサーバーローカルです。",
          "UTCとして扱うなら timezone.utc を使います。",
          "importにも timezone が必要です。"
        ],
        steps: reviewSteps(
          "boundary",
          {
            id: "naive_datetime_compared_with_utc",
            label: "naive時刻とUTC時刻の混在",
            description: "タイムゾーンなしの現在時刻でUTC期限を判定している"
          },
          {
            id: "fix-now-utc",
            label: "UTCの現在時刻で比較する",
            description: "現在時刻と期限の基準をUTCに揃える",
            code: `return datetime.now(timezone.utc) > deadline`
          },
          [
            {
              id: "fix-date-only",
              label: "日付だけ比較する",
              description: "時刻単位の期限が失われる"
            },
            {
              id: "fix-string-compare",
              label: "文字列として比較する",
              description: "形式差やタイムゾーンで壊れやすい"
            },
            {
              id: "fix-localize-deadline",
              label: "期限をローカル扱いにする",
              description: "UTCとして扱う仕様と逆になる"
            }
          ]
        )
      }
    ]
  },
  {
    id: "retry-policy-broad-except-review",
    role: "Resilience Reviewer",
    title: "リトライ処理の例外握りつぶしレビュー",
    difficultyLabel: "Intermediate",
    estimatedMinutes: 5,
    timeLimitSeconds: 300,
    codeLanguage: "python",
    requirements: [
      "リトライ対象は TimeoutError のみ",
      "ValueError などの非一時的な例外は再送出する",
      "3回失敗したら最後の TimeoutError を送出する",
      "失敗を None として成功扱いしない"
    ],
    examples: [
      "TimeoutErrorが3回 -> TimeoutError",
      "ValueError -> 即時にValueError"
    ],
    constraints: [
      "広すぎるexceptを疑う",
      "失敗時の戻り値契約を見る"
    ],
    code: `def fetch_with_retry(client, url):
    for _ in range(3):
        try:
            return client.get(url)
        except Exception:
            pass
    return None`,
    challengeHints: [
      "Exception は何でも捕まえます。",
      "Noneを返すと呼び出し元は失敗に気づけるでしょうか。",
      "一時的な失敗だけリトライする仕様です。"
    ],
    issues: [
      {
        id: "retry-catches-all-exceptions",
        title: "リトライ対象外の例外まで握りつぶしている",
        category: "spec",
        pattern: "overbroad_exception_retry",
        startLine: 5,
        endLine: 6,
        difficulty: 3,
        summary: "TimeoutErrorだけでなく、ValueErrorなども捕まえてリトライしている。",
        explanation:
          "入力不正やプログラムミスはリトライしても直りません。リトライ対象はTimeoutErrorに限定し、他の例外はそのまま出すべきです。",
        correctCode: `except TimeoutError as exc:
            last_error = exc`,
        hints: [
          "except Exception は広すぎます。",
          "仕様上のリトライ対象はTimeoutErrorだけです。",
          "5行目の例外型を絞ります。"
        ],
        steps: reviewSteps(
          "spec",
          {
            id: "overbroad_exception_retry",
            label: "広すぎる例外リトライ",
            description: "一時的でない失敗までリトライ対象にしている"
          },
          {
            id: "fix-timeout-only",
            label: "TimeoutErrorだけ捕まえる",
            description: "非一時的な例外は呼び出し元へ返す",
            code: `except TimeoutError as exc:
            last_error = exc`
          },
          [
            {
              id: "fix-base-exception",
              label: "BaseExceptionに広げる",
              description: "KeyboardInterruptなどまで握りつぶす"
            },
            {
              id: "fix-return-empty",
              label: "空文字を返す",
              description: "失敗を成功値に見せてしまう"
            },
            {
              id: "fix-no-retry",
              label: "tryを消す",
              description: "TimeoutErrorのリトライ要件を満たせない"
            }
          ]
        )
      },
      {
        id: "retry-returns-none-after-failure",
        title: "リトライ失敗をNoneで隠している",
        category: "data_flow",
        pattern: "failure_converted_to_none",
        startLine: 7,
        endLine: 7,
        difficulty: 3,
        summary: "3回失敗した後に例外ではなくNoneを返している。",
        explanation:
          "Noneは通常値として扱われやすく、失敗が後段に伝わりません。最後のTimeoutErrorを送出する契約にすべきです。",
        correctCode: `raise last_error`,
        hints: [
          "仕様は最後のTimeoutErrorを送出です。",
          "Noneでは失敗理由が消えます。",
          "7行目は例外送出に変えます。"
        ],
        steps: reviewSteps(
          "data_flow",
          {
            id: "failure_converted_to_none",
            label: "失敗をNoneに変換",
            description: "例外として扱うべき失敗を通常値に変えて隠している"
          },
          {
            id: "fix-raise-last-error",
            label: "最後の例外を送出する",
            description: "呼び出し元が失敗理由を扱えるようにする",
            code: `raise last_error`
          },
          [
            {
              id: "fix-return-false",
              label: "Falseを返す",
              description: "戻り値契約が曖昧になる"
            },
            {
              id: "fix-return-url",
              label: "URLを返す",
              description: "取得結果ではない値が返る"
            },
            {
              id: "fix-pass",
              label: "passを残す",
              description: "失敗が隠れたままになる"
            }
          ]
        )
      }
    ]
  },
  {
    id: "webhook-signature-body-review",
    role: "Webhook Security Reviewer",
    title: "Webhook署名検証の順序レビュー",
    difficultyLabel: "Advanced",
    estimatedMinutes: 5,
    timeLimitSeconds: 300,
    codeLanguage: "python",
    requirements: [
      "X-Signatureヘッダーを使って検証する",
      "署名検証はraw bodyに対して行う",
      "JSONを信頼して処理する前に署名を検証する",
      "署名値をpayload内の値として信用しない"
    ],
    examples: [
      "署名不一致 -> PermissionError",
      "署名一致 -> JSONをparseしてprocessへ渡す"
    ],
    constraints: [
      "信頼境界の前後を確認する",
      "署名の入力元を見る"
    ],
    code: `def handle_webhook(request, secret):
    payload = request.json()
    if payload.get("signature") != secret:
        raise PermissionError("invalid signature")
    return process(payload)`,
    challengeHints: [
      "payloadはまだ信頼できない入力です。",
      "署名はどこから読む仕様でしょうか。",
      "raw bodyに対する検証がありません。"
    ],
    issues: [
      {
        id: "webhook-trusts-payload-signature",
        title: "payload内の署名値を信用している",
        category: "security",
        pattern: "signature_checked_from_untrusted_body",
        startLine: 2,
        endLine: 4,
        difficulty: 5,
        summary: "未検証のJSONからsignatureを読み、secretと比較している。",
        explanation:
          "Webhook署名はヘッダーとraw bodyで検証します。payload自体は検証後に初めて信頼できるため、body内の値を署名として信用してはいけません。",
        correctCode: `signature = request.headers["X-Signature"]
    verify_signature(request.raw_body, signature, secret)
    payload = request.json()`,
        hints: [
          "payloadは攻撃者が自由に作れる値です。",
          "仕様はX-Signatureヘッダーです。",
          "JSON parseより前にraw bodyを検証します。"
        ],
        steps: reviewSteps(
          "security",
          {
            id: "signature_checked_from_untrusted_body",
            label: "未信頼body由来の署名検証",
            description: "検証前のpayload内の値を署名として信用している"
          },
          {
            id: "fix-header-raw-body-signature",
            label: "ヘッダーとraw bodyで検証する",
            description: "payloadを処理する前に署名を確認する",
            code: `signature = request.headers["X-Signature"]
    verify_signature(request.raw_body, signature, secret)
    payload = request.json()`
          },
          [
            {
              id: "fix-secret-in-body",
              label: "secretをbodyに入れる",
              description: "秘密値を外部入力に混ぜてしまう"
            },
            {
              id: "fix-process-first",
              label: "process後に検証する",
              description: "検証前に副作用が起きる"
            },
            {
              id: "fix-ignore-signature",
              label: "署名検証を削除する",
              description: "誰でもWebhookを送れる"
            }
          ]
        )
      }
    ]
  },
  {
    id: "inventory-allocation-priority-review",
    role: "Supply Allocation Reviewer",
    title: "在庫配分の優先度ソートレビュー",
    difficultyLabel: "Practical",
    estimatedMinutes: 5,
    timeLimitSeconds: 300,
    codeLanguage: "python",
    requirements: [
      "priority の数値が大きい注文を先に配分する",
      "在庫が不足する場合は高優先注文から満たす",
      "配分数量は注文数量と残在庫の小さい方にする",
      "残在庫が0になったら以降の注文は0配分"
    ],
    examples: [
      "priority=10 の注文は priority=1 より先に配分",
      "stock=5, qty=8 -> allocated=5"
    ],
    constraints: [
      "昇順と降順を確認する",
      "高優先の意味を仕様から読む"
    ],
    code: `def allocate(stock, orders):
    result = {}
    for order in sorted(orders, key=lambda order: order["priority"]):
        qty = min(stock, order["qty"])
        result[order["id"]] = qty
        stock -= qty
    return result`,
    challengeHints: [
      "priorityが大きいほど先です。",
      "sortedのデフォルトは昇順です。",
      "3行目の並び順を見てください。"
    ],
    issues: [
      {
        id: "allocation-sorts-low-priority-first",
        title: "低優先注文から先に配分している",
        category: "logic",
        pattern: "sort_direction_reversed",
        startLine: 3,
        endLine: 3,
        difficulty: 2,
        summary: "priorityが小さい順に並べているため、高優先注文が後回しになる。",
        explanation:
          "仕様ではpriorityの数値が大きい注文を先に扱います。sortedはデフォルト昇順なので、reverse=True が必要です。",
        correctCode: `for order in sorted(orders, key=lambda order: order["priority"], reverse=True):`,
        hints: [
          "sortedは何順でしょうか。",
          "priority=10とpriority=1の順番を考えてください。",
          "3行目にreverse=Trueを付けます。"
        ],
        steps: reviewSteps(
          "logic",
          {
            id: "sort_direction_reversed",
            label: "ソート方向が逆",
            description: "優先度や日付など、並び順の意味を反対に実装している"
          },
          {
            id: "fix-reverse-priority",
            label: "降順ソートにする",
            description: "priorityの大きい注文から処理する",
            code: `for order in sorted(orders, key=lambda order: order["priority"], reverse=True):`
          },
          [
            {
              id: "fix-sort-id",
              label: "id順にする",
              description: "優先度の仕様を無視している"
            },
            {
              id: "fix-no-sort",
              label: "入力順のまま処理する",
              description: "高優先注文が先とは限らない"
            },
            {
              id: "fix-min-reverse",
              label: "minをmaxにする",
              description: "在庫以上を配分してしまう"
            }
          ]
        )
      }
    ]
  },
  {
    id: "product-search-filter-and-review",
    role: "Search API Reviewer",
    title: "商品検索フィルタのAND条件レビュー",
    difficultyLabel: "Warm-up",
    estimatedMinutes: 5,
    timeLimitSeconds: 300,
    codeLanguage: "python",
    requirements: [
      "category が指定カテゴリと一致する商品だけ返す",
      "price は max_price 以下の商品だけ返す",
      "category と price の両方を満たす商品だけ返す",
      "どちらか片方だけ満たす商品は返さない"
    ],
    examples: [
      "category一致かつprice以下 -> 含める",
      "categoryだけ一致、price超過 -> 含めない"
    ],
    constraints: [
      "ORとANDの違いを見る",
      "検索条件が広がりすぎていないか確認する"
    ],
    code: `def filter_products(products, query):
    result = []
    for product in products:
        if product["category"] == query["category"] or product["price"] <= query["max_price"]:
            result.append(product)
    return result`,
    challengeHints: [
      "仕様は両方を満たす商品です。",
      "orは条件を広げます。",
      "4行目の論理演算子を見てください。"
    ],
    issues: [
      {
        id: "search-filter-uses-or",
        title: "検索条件をORで広げている",
        category: "logic",
        pattern: "and_condition_implemented_as_or",
        startLine: 4,
        endLine: 5,
        difficulty: 1,
        summary: "categoryまたはpriceの片方だけ満たす商品まで返している。",
        explanation:
          "検索条件は両方を満たす必要があります。orでは対象が広がりすぎるため、andにする必要があります。",
        correctCode: `if product["category"] == query["category"] and product["price"] <= query["max_price"]:`,
        hints: [
          "片方だけ一致した商品は返すべきでしょうか。",
          "orはどちらか一方で通ります。",
          "4行目はandが正しいです。"
        ],
        steps: reviewSteps(
          "logic",
          {
            id: "and_condition_implemented_as_or",
            label: "AND条件をORで実装",
            description: "両方満たすべき条件を、片方だけで通している"
          },
          {
            id: "fix-search-and",
            label: "AND条件にする",
            description: "カテゴリ一致かつ価格上限内の商品だけ返す",
            code: `if product["category"] == query["category"] and product["price"] <= query["max_price"]:`
          },
          [
            {
              id: "fix-not-category",
              label: "categoryを不一致にする",
              description: "検索対象が逆になる"
            },
            {
              id: "fix-price-greater",
              label: "priceを上限以上にする",
              description: "高額商品を返してしまう"
            },
            {
              id: "fix-append-all",
              label: "全商品をappendする",
              description: "フィルタがなくなる"
            }
          ]
        )
      }
    ]
  },
  {
    id: "invoice-tax-rounding-review",
    role: "Billing Calculation Reviewer",
    title: "請求税計算の丸め単位レビュー",
    difficultyLabel: "Intermediate",
    estimatedMinutes: 5,
    timeLimitSeconds: 300,
    codeLanguage: "python",
    requirements: [
      "税対象行だけを小計に含める",
      "税は小計合計に対して一度だけ計算する",
      "行ごとに丸めない",
      "最終合計をroundして返す"
    ],
    examples: [
      "2行の税対象は合算してから税計算",
      "taxable=False の行に税をかけない"
    ],
    constraints: [
      "丸めの単位を見る",
      "課税対象と非課税対象を分ける"
    ],
    code: `def invoice_total(lines, tax_rate):
    total = 0
    for line in lines:
        line_total = round(line["price"] * line["qty"] * (1 + tax_rate))
        total += line_total
    return total`,
    challengeHints: [
      "税は行ごとではなく小計合計にかけます。",
      "taxableフラグがコードに出てきますか。",
      "4行目が処理をまとめすぎています。"
    ],
    issues: [
      {
        id: "tax-rounded-per-line",
        title: "税を行ごとに丸めている",
        category: "spec",
        pattern: "rounding_granularity_wrong",
        startLine: 3,
        endLine: 5,
        difficulty: 3,
        summary: "行単位で税込金額をroundしてから合計している。",
        explanation:
          "請求では丸め単位が仕様として重要です。行ごとの丸めは合計後丸めと差が出るため、税対象小計を合算してから一度だけroundします。",
        correctCode: `subtotal = sum(line["price"] * line["qty"] for line in lines if line["taxable"])
    return round(subtotal * (1 + tax_rate))`,
        hints: [
          "roundがforループの中にあります。",
          "仕様は合計に対して一度だけ税計算です。",
          "taxableフラグも見てください。"
        ],
        steps: reviewSteps(
          "spec",
          {
            id: "rounding_granularity_wrong",
            label: "丸め単位の誤り",
            description: "行ごと・合計ごとなど、仕様で決まる丸め位置が違っている"
          },
          {
            id: "fix-taxable-subtotal-round-once",
            label: "税対象小計を合算して一度だけ丸める",
            description: "非課税行を除き、合計に税率をかけてからroundする",
            code: `subtotal = sum(line["price"] * line["qty"] for line in lines if line["taxable"])
    return round(subtotal * (1 + tax_rate))`
          },
          [
            {
              id: "fix-round-every-line",
              label: "行ごとroundのまま",
              description: "丸め誤差が仕様とずれる"
            },
            {
              id: "fix-all-lines-tax",
              label: "全行に税をかける",
              description: "非課税行まで課税される"
            },
            {
              id: "fix-no-tax",
              label: "税率を使わない",
              description: "税計算がなくなる"
            }
          ]
        )
      }
    ]
  },
  {
    id: "event-dedupe-tenant-success-review",
    role: "Event Processing Reviewer",
    title: "イベント重複排除のキーと成功記録レビュー",
    difficultyLabel: "Advanced",
    estimatedMinutes: 5,
    timeLimitSeconds: 300,
    codeLanguage: "python",
    requirements: [
      "重複判定は tenant_id と event id の組み合わせで行う",
      "別テナントの同じevent idは別イベントとして処理する",
      "処理が成功した後にだけ処理済みとして記録する",
      "失敗したイベントは再試行できる"
    ],
    examples: [
      "tenant A / id 1 と tenant B / id 1 は別扱い",
      "apply_eventが失敗したらPROCESSEDに入れない"
    ],
    constraints: [
      "dedupe keyの粒度を見る",
      "成功前に処理済みにしていないか確認する"
    ],
    code: `PROCESSED = set()

def handle_event(event):
    if event["id"] in PROCESSED:
        return "duplicate"
    PROCESSED.add(event["id"])
    apply_event(event)
    return "ok"`,
    challengeHints: [
      "event id だけでテナントを区別できますか。",
      "apply_eventが失敗した場合、再試行できるでしょうか。",
      "keyの作り方とaddの位置を見ます。"
    ],
    issues: [
      {
        id: "event-dedupe-key-misses-tenant",
        title: "重複排除キーにtenant_idが含まれていない",
        category: "data_flow",
        pattern: "dedupe_key_too_coarse",
        startLine: 4,
        endLine: 4,
        difficulty: 4,
        summary: "event idだけで重複判定しているため、別テナントの同じidが重複扱いになる。",
        explanation:
          "マルチテナントではidの衝突範囲を明確にする必要があります。tenant_idとevent idの組み合わせをキーにします。",
        correctCode: `key = (event["tenant_id"], event["id"])`,
        hints: [
          "event idは全テナントで一意とは限りません。",
          "tenant_idが仕様にあります。",
          "重複判定用のkeyを作ります。"
        ],
        steps: reviewSteps(
          "data_flow",
          {
            id: "dedupe_key_too_coarse",
            label: "重複排除キーが粗すぎる",
            description: "区別すべきスコープをkeyに含めていない"
          },
          {
            id: "fix-event-tenant-key",
            label: "tenant_idとidをキーにする",
            description: "テナントごとにイベント重複を分離する",
            code: `key = (event["tenant_id"], event["id"])`
          },
          [
            {
              id: "fix-id-only",
              label: "idだけのまま",
              description: "別テナントのイベントが衝突する"
            },
            {
              id: "fix-tenant-only",
              label: "tenant_idだけにする",
              description: "同一テナントの全イベントが重複扱いになる"
            },
            {
              id: "fix-random-key",
              label: "ランダムキーにする",
              description: "重複を検出できなくなる"
            }
          ]
        )
      },
      {
        id: "event-marked-before-success",
        title: "処理成功前に処理済みとして記録している",
        category: "data_flow",
        pattern: "success_marker_written_before_side_effect",
        startLine: 6,
        endLine: 7,
        difficulty: 4,
        summary: "apply_eventが失敗してもPROCESSEDに残り、再試行できなくなる。",
        explanation:
          "処理済みマークは副作用が成功した後に書くべきです。先に書くと、一時障害でイベントを永久に失います。",
        correctCode: `apply_event(event)
    PROCESSED.add(key)`,
        hints: [
          "apply_eventが例外を出すケースを考えてください。",
          "先にaddすると再試行がduplicateになります。",
          "成功後にPROCESSEDへ追加します。"
        ],
        steps: reviewSteps(
          "data_flow",
          {
            id: "success_marker_written_before_side_effect",
            label: "成功前の処理済み記録",
            description: "副作用が成功する前に完了マークを書いている"
          },
          {
            id: "fix-mark-after-success",
            label: "成功後に処理済みにする",
            description: "失敗時は再試行できるようにする",
            code: `apply_event(event)
    PROCESSED.add(key)`
          },
          [
            {
              id: "fix-never-mark",
              label: "処理済み記録を消す",
              description: "重複イベントを毎回処理してしまう"
            },
            {
              id: "fix-return-before-apply",
              label: "apply前にokを返す",
              description: "実処理が行われない"
            },
            {
              id: "fix-catch-ignore",
              label: "例外を握りつぶす",
              description: "失敗が隠れて再試行もできない"
            }
          ]
        )
      }
    ]
  },
  {
    id: "audit-log-pii-mask-review",
    role: "Privacy Review Candidate",
    title: "監査ログの個人情報マスキングレビュー",
    difficultyLabel: "Practical",
    estimatedMinutes: 5,
    timeLimitSeconds: 300,
    codeLanguage: "python",
    requirements: [
      "監査ログには user_id と action を残す",
      "email はドメインだけ分かる形にマスクする",
      "phone は末尾4桁だけ残す",
      "生のemailやphoneをログに出さない"
    ],
    examples: [
      "alice@example.com -> ***@example.com",
      "09012345678 -> *******5678"
    ],
    constraints: [
      "ログは外部流出しやすい前提で見る",
      "識別子と個人情報を分ける"
    ],
    code: `def create_audit_log(user):
    return {
        "user_id": user["id"],
        "email": user["email"],
        "phone": user["phone"],
        "action": "profile_view",
    }`,
    challengeHints: [
      "監査ログは長期保存されます。",
      "emailとphoneがそのまま出ていないか見てください。",
      "識別に必要な情報と不要なPIIを分けます。"
    ],
    issues: [
      {
        id: "audit-log-raw-pii",
        title: "監査ログに生のemailとphoneを出している",
        category: "security",
        pattern: "pii_written_to_log",
        startLine: 4,
        endLine: 5,
        difficulty: 3,
        summary: "マスキングすべき個人情報をそのままログ用dictに入れている。",
        explanation:
          "ログは参照範囲が広く保存期間も長いため、最小限の情報だけにします。emailとphoneは仕様どおりマスクします。",
        correctCode: `"email": mask_email(user["email"]),
        "phone": mask_phone(user["phone"]),`,
        hints: [
          "生のemailが残っています。",
          "phoneもマスク要件があります。",
          "4〜5行目はmask関数を通します。"
        ],
        steps: reviewSteps(
          "security",
          {
            id: "pii_written_to_log",
            label: "ログへのPII出力",
            description: "ログに不要な個人情報をそのまま書き込んでいる"
          },
          {
            id: "fix-mask-pii",
            label: "emailとphoneをマスクする",
            description: "監査に必要な粒度だけ残し、生値を出さない",
            code: `"email": mask_email(user["email"]),
        "phone": mask_phone(user["phone"]),`
          },
          [
            {
              id: "fix-remove-user-id",
              label: "user_idを削除する",
              description: "監査対象を追跡できなくなる"
            },
            {
              id: "fix-hash-action",
              label: "actionをハッシュ化する",
              description: "何をしたログか分からなくなる"
            },
            {
              id: "fix-email-only",
              label: "emailだけマスクする",
              description: "phoneの生値が残る"
            }
          ]
        )
      }
    ]
  },
  {
    id: "config-timeout-env-review",
    role: "Runtime Config Reviewer",
    title: "環境変数タイムアウトの型変換レビュー",
    difficultyLabel: "Warm-up",
    estimatedMinutes: 5,
    timeLimitSeconds: 300,
    codeLanguage: "python",
    requirements: [
      "REQUEST_TIMEOUT が未設定なら30を返す",
      "REQUEST_TIMEOUT が設定されていれば整数に変換して返す",
      "戻り値は常にintにする",
      "文字列のまま呼び出し元に渡さない"
    ],
    examples: [
      "REQUEST_TIMEOUT unset -> 30",
      "REQUEST_TIMEOUT='5' -> 5"
    ],
    constraints: [
      "環境変数は文字列で返る",
      "デフォルト値と型を同時に見る"
    ],
    code: `import os

def get_timeout():
    timeout = os.getenv("REQUEST_TIMEOUT") or 30
    return timeout`,
    challengeHints: [
      "os.getenvの戻り値の型は何でしょうか。",
      "設定されている場合と未設定の場合で型が変わっていませんか。",
      "戻り値は常にintである必要があります。"
    ],
    issues: [
      {
        id: "timeout-return-type-string",
        title: "環境変数が設定されていると文字列を返す",
        category: "data_flow",
        pattern: "env_value_not_cast",
        startLine: 4,
        endLine: 5,
        difficulty: 2,
        summary: "REQUEST_TIMEOUT='5' のとき、intではなく文字列'5'を返す。",
        explanation:
          "環境変数は文字列として読み込まれます。呼び出し元が数値比較やsleepに使うなら、必ずintへ変換します。",
        correctCode: `return int(os.getenv("REQUEST_TIMEOUT", "30"))`,
        hints: [
          "os.getenvは文字列を返します。",
          "未設定時だけintの30になります。",
          "読み込み時にintへ変換します。"
        ],
        steps: reviewSteps(
          "data_flow",
          {
            id: "env_value_not_cast",
            label: "環境変数の型変換漏れ",
            description: "文字列で読み込んだ設定値を、必要な型に変換していない"
          },
          {
            id: "fix-int-env-default",
            label: "文字列デフォルトごとint変換する",
            description: "設定あり・なしの両方でintを返す",
            code: `return int(os.getenv("REQUEST_TIMEOUT", "30"))`
          },
          [
            {
              id: "fix-str-default",
              label: "デフォルトを'30'にするだけ",
              description: "戻り値が常に文字列になる"
            },
            {
              id: "fix-float",
              label: "floatに変換する",
              description: "仕様のintと違う"
            },
            {
              id: "fix-no-default",
              label: "デフォルトを消す",
              description: "未設定時の要件を満たせない"
            }
          ]
        )
      }
    ]
  },
  {
    id: "async-gather-return-review",
    role: "Async Python Reviewer",
    title: "非同期APIの結果返却レビュー",
    difficultyLabel: "Advanced",
    estimatedMinutes: 5,
    timeLimitSeconds: 300,
    codeLanguage: "python",
    requirements: [
      "profile と orders を非同期に取得する",
      "戻り値には実データを入れる",
      "coroutine object を呼び出し元に返さない",
      "2つの取得は並列実行してよい"
    ],
    examples: [
      "return {'profile': dict, 'orders': list}",
      "return {'profile': coroutine, ...} は不合格"
    ],
    constraints: [
      "awaitされていないcoroutineを探す",
      "並列化と未実行を混同しない"
    ],
    code: `async def load_profile(user_id, api):
    profile_task = api.profile(user_id)
    orders_task = api.orders(user_id)
    return {"profile": profile_task, "orders": orders_task}`,
    challengeHints: [
      "profile_taskとorders_taskは実データでしょうか。",
      "async関数内でも呼ぶだけでは実行結果になりません。",
      "return前にawaitが必要です。"
    ],
    issues: [
      {
        id: "async-coroutines-returned",
        title: "awaitしていないcoroutineをそのまま返している",
        category: "data_flow",
        pattern: "coroutine_returned_without_await",
        startLine: 2,
        endLine: 4,
        difficulty: 4,
        summary: "api.profile/api.ordersの結果を待たず、coroutine objectを返している。",
        explanation:
          "非同期関数の呼び出し結果はawaitしなければ実データになりません。並列化したい場合も gather などで完了を待ちます。",
        correctCode: `profile, orders = await asyncio.gather(
        api.profile(user_id),
        api.orders(user_id),
    )
    return {"profile": profile, "orders": orders}`,
        hints: [
          "変数名はtaskですが、create_taskもawaitもありません。",
          "returnしているのは完了結果ではありません。",
          "asyncio.gatherで2つを待てます。"
        ],
        steps: reviewSteps(
          "data_flow",
          {
            id: "coroutine_returned_without_await",
            label: "await前のcoroutine返却",
            description: "非同期処理の完了結果ではなく、未実行または未完了のオブジェクトを返している"
          },
          {
            id: "fix-gather-await",
            label: "gatherで待って実データを返す",
            description: "profileとordersを並列に待ってからdictに入れる",
            code: `profile, orders = await asyncio.gather(
        api.profile(user_id),
        api.orders(user_id),
    )
    return {"profile": profile, "orders": orders}`
          },
          [
            {
              id: "fix-return-tasks",
              label: "task名のまま返す",
              description: "実データではない"
            },
            {
              id: "fix-sync-call",
              label: "asyncを消す",
              description: "非同期API呼び出しの前提と合わない"
            },
            {
              id: "fix-await-one",
              label: "profileだけawaitする",
              description: "ordersのcoroutineが残る"
            }
          ]
        )
      }
    ]
  },
  {
    id: "money-cents-float-review",
    role: "Money Calculation Reviewer",
    title: "クーポン割引のセント計算レビュー",
    difficultyLabel: "Intermediate",
    estimatedMinutes: 5,
    timeLimitSeconds: 300,
    codeLanguage: "python",
    requirements: [
      "price_cents は整数のセント額",
      "coupon_percent は0から100の整数",
      "戻り値も整数のセント額にする",
      "金額計算にfloatを混ぜない"
    ],
    examples: [
      "apply_coupon(1000, 15) -> 850",
      "apply_coupon(999, 10) -> 900"
    ],
    constraints: [
      "金額の単位を確認する",
      "floatが混ざっていないか見る"
    ],
    code: `def apply_coupon(price_cents, coupon_percent):
    discount = price_cents * (coupon_percent / 100)
    return price_cents - discount`,
    challengeHints: [
      "price_centsは整数です。",
      "/ はPythonでfloatを作ります。",
      "戻り値の型がintのままか確認してください。"
    ],
    issues: [
      {
        id: "money-cents-becomes-float",
        title: "セント金額計算にfloatを混ぜている",
        category: "data_flow",
        pattern: "money_amount_converted_to_float",
        startLine: 2,
        endLine: 3,
        difficulty: 3,
        summary: "coupon_percent / 100 によりdiscountがfloatになり、戻り値もfloatになる。",
        explanation:
          "金額をセント整数で扱う設計なら、途中でfloatにしてはいけません。整数除算で割引額を作り、戻り値もintにします。",
        correctCode: `discount = price_cents * coupon_percent // 100
    return price_cents - discount`,
        hints: [
          "Pythonの / はfloat除算です。",
          "戻り値は整数セントである必要があります。",
          "// を使って整数の割引額を作ります。"
        ],
        steps: reviewSteps(
          "data_flow",
          {
            id: "money_amount_converted_to_float",
            label: "金額のfloat化",
            description: "整数で扱うべき金額にfloatを混ぜている"
          },
          {
            id: "fix-integer-cents",
            label: "整数セントのまま計算する",
            description: "割引額を整数で計算し、intを返す",
            code: `discount = price_cents * coupon_percent // 100
    return price_cents - discount`
          },
          [
            {
              id: "fix-round-float",
              label: "最後にroundする",
              description: "途中でfloatにする設計が残る"
            },
            {
              id: "fix-yen",
              label: "円に変換して返す",
              description: "戻り値の単位が変わる"
            },
            {
              id: "fix-string",
              label: "文字列にする",
              description: "計算結果として使いにくくなる"
            }
          ]
        )
      }
    ]
  },
  {
    id: "soft-delete-owner-review",
    role: "Authorization Review Candidate",
    title: "ドキュメント削除の所有者確認レビュー",
    difficultyLabel: "Advanced",
    estimatedMinutes: 5,
    timeLimitSeconds: 300,
    codeLanguage: "python",
    requirements: [
      "所有者確認は認証済みsession_user.idで行う",
      "request bodyのowner_idを信用しない",
      "削除は物理削除ではなくsoft deleteにする",
      "権限がなければ PermissionError を送出する"
    ],
    examples: [
      "session_user.id != doc.owner_id -> PermissionError",
      "削除時はdeleted_atを設定する"
    ],
    constraints: [
      "認可に使う入力元を確認する",
      "物理削除と論理削除の違いを見る"
    ],
    code: `def delete_document(request, db):
    doc = db.get_document(request["document_id"])
    if doc["owner_id"] != request["owner_id"]:
        raise PermissionError("forbidden")
    db.delete(doc["id"])
    return True`,
    challengeHints: [
      "requestのowner_idは誰が送れる値でしょうか。",
      "認証済みユーザー情報が使われていません。",
      "deleteはsoft delete仕様と合っていますか。"
    ],
    issues: [
      {
        id: "owner-id-trusted-from-request",
        title: "request bodyのowner_idで認可している",
        category: "security",
        pattern: "authorization_uses_untrusted_request_field",
        startLine: 3,
        endLine: 4,
        difficulty: 5,
        summary: "攻撃者が書き換えられるrequest['owner_id']を所有者判定に使っている。",
        explanation:
          "認可は信頼済みの認証コンテキストで行います。request bodyのowner_idは自己申告なので、session_user.idと比較すべきです。",
        correctCode: `if doc["owner_id"] != request["session_user"]["id"]:
        raise PermissionError("forbidden")`,
        hints: [
          "request bodyはユーザーが送れる値です。",
          "所有者判定に自己申告値を使っています。",
          "認証済みsession_user.idを使います。"
        ],
        steps: reviewSteps(
          "security",
          {
            id: "authorization_uses_untrusted_request_field",
            label: "未信頼入力による認可",
            description: "権限判定に、攻撃者が変更できるリクエスト値を使っている"
          },
          {
            id: "fix-session-user-owner",
            label: "session_user.idで確認する",
            description: "信頼済みの認証コンテキストを使って所有者判定する",
            code: `if doc["owner_id"] != request["session_user"]["id"]:
        raise PermissionError("forbidden")`
          },
          [
            {
              id: "fix-no-owner-check",
              label: "所有者確認を削除する",
              description: "誰でも削除できる"
            },
            {
              id: "fix-document-id",
              label: "document_idで比較する",
              description: "所有者とは別の値を比べている"
            },
            {
              id: "fix-return-false",
              label: "Falseを返す",
              description: "認可の入力元問題は残る"
            }
          ]
        )
      },
      {
        id: "physical-delete-instead-soft-delete",
        title: "soft delete仕様なのに物理削除している",
        category: "spec",
        pattern: "hard_delete_instead_of_soft_delete",
        startLine: 5,
        endLine: 5,
        difficulty: 3,
        summary: "deleted_atを設定すべきところで db.delete を呼んでいる。",
        explanation:
          "監査や復旧が必要な文書削除ではsoft deleteが求められます。物理削除は履歴も復旧余地も失います。",
        correctCode: `db.mark_deleted(doc["id"], deleted_at=now())`,
        hints: [
          "仕様はsoft deleteです。",
          "db.deleteは物理削除に見えます。",
          "5行目はdeleted_at設定に変えます。"
        ],
        steps: reviewSteps(
          "spec",
          {
            id: "hard_delete_instead_of_soft_delete",
            label: "論理削除仕様の物理削除",
            description: "deleted_atなどで残すべきデータを完全削除している"
          },
          {
            id: "fix-mark-deleted",
            label: "deleted_atを設定する",
            description: "文書を残したまま削除状態にする",
            code: `db.mark_deleted(doc["id"], deleted_at=now())`
          },
          [
            {
              id: "fix-delete-again",
              label: "db.deleteのまま",
              description: "soft delete要件を満たさない"
            },
            {
              id: "fix-return-only",
              label: "Trueだけ返す",
              description: "削除状態が保存されない"
            },
            {
              id: "fix-clear-owner",
              label: "owner_idを消す",
              description: "所有者情報が失われるだけで削除状態ではない"
            }
          ]
        )
      }
    ]
  }
];

export const challenges: InterviewChallenge[] = [
  ...baseChallenges,
  ...additionalHandmadeChallenges
];

export function getChallengeById(id: string) {
  return challenges.find((challenge) => challenge.id === id);
}
