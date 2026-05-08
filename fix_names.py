#!/usr/bin/env python3
"""
name_verify_report.json の検証結果を元に fish_data.json の和名を修正する。
科学名をキーに照合するので一括安全修正が可能。

修正カテゴリ:
  A: 明らかなOCR誤字（1〜2文字の読み間違い）
  B: Wikidataが正しく、保存名が完全に別の魚
  SKIP: Wikidataの誤ヒットまたは曖昧なもの → 変更しない
"""

import json
from pathlib import Path

FISH_DATA = Path(__file__).parent / "fish_data.json"

# 科学名 → 正しい和名
CORRECTIONS = {
    # ── A: OCR誤字 ──────────────────────────────────────────────
    "Rhincodon typus":              "ジンベエザメ",       # イ→エ
    "Sphyrna lewini":               "アカシュモクザメ",   # シモク→シュモク
    "Myripristis murdjan":          "ヨゴレマツカサ",     # ゴゴ→ヨゴ
    "Elagatis bipinnulata":         "ツムブリ",           # シ→ツ
    "Seriola quinqueradiata":       "ブリ",               # プ→ブ
    "Pterocaesio tile":             "クマササハナムロ",   # ケ→ク
    "Lethrinus nebulosus":          "ハマフエフキ",       # キ→フキ
    "Chaetodon bennetti":           "ウミヅキチョウチョウウオ",  # ウ脱落
    "Chaetodon lunula":             "チョウハン",         # バ→ハ
    "Chaetodon mertensii":          "ベニオチョウチョウウオ",    # ペ→ベ
    "Chaetodon plebeius":           "スミツキトノサマダイ",      # サダイ→サマダイ
    "Chaetodon speculum":           "トノサマダイ",       # サダイ→サマダイ
    "Amphiprion sandaracinos":      "セジロクマノミ",     # ダル→ジロ
    "Bodianus izuensis":            "タヌキベラ",         # ペ→ベ
    "Bodianus oxycephalus":         "キツネダイ",         # ゾ→ツ
    "Cheilio inermis":              "カマスベラ",         # ペ→ベ
    "Thalassoma quinquevittatum":   "ハコベラ",           # ゴ→コ、ペ→ベ
    "Pseudolabrus eoethinus":       "アカササノハベラ",   # ペ→ベ
    "Pseudolabrus sieboldi":        "ホシササノハベラ",   # ペ→ベ
    "Halichoeres chrysus":          "コガネキュウセン",   # ゴ→コ
    "Chlorurus microrhinos":        "ナンヨウブダイ",     # ブ脱落
    "Calotomus japonicus":          "ブダイ",             # プ→ブ
    "Scarus altipinnis":            "イトヒキブダイ",     # ヌ→ブ
    "Aspidontus taeniatus":         "ニセクロスジギンポ", # ボ→ポ
    "Xiphasia setifer":             "ウナギギンポ",       # ボ→ポ
    "Pterogobius elapoides":        "キヌバリ",           # ツ→ヌ
    "Stonogobiops nematodes":       "ヒレナガネジリンボウ",  # ネ脱落
    "Platax pinnatus":              "アカククリ",         # ク脱落
    "Siganus unimaculatus":         "ヒフキアイゴ",       # ビ→ヒ
    "Naso hexacanthus":             "テングハギモドキ",   # カ→グ
    "Naso brachycentron":           "オニテングハギ",     # カ→（削除）
    "Pseudobalistes fuscus":        "イソモンガラ",       # シ→ソ
    "Lactoria cornuta":             "コンゴウフグ",       # ゴ→コ（先頭）
    "Lactoria diaphana":            "ウミスズメ",         # アミメズメ→ウミスズメ
    "Lactoria fornasini":           "シマウミスズメ",     # ズメ→スズメ
    "Arothron meleagris":           "ミゾレフグ",         # シル→ゾレ
    "Chilomycterus reticulatus":    "イシガキフグ",       # ン→シ

    # ── B: Wikidataが正しく、別の魚名になっていたもの ───────────
    "Caesio teres":                 "ウメイロモドキ",     # ヤマトロモドキ→
    "Sebastiscus marmoratus":       "カサゴ",             # ナガサゴ→
    "Sebastes schlegelii":          "クロソイ",           # ムラソイ→
    "Grammistes sexlineatus":       "ヌノサラシ",         # マダラハゼ→
    "Uraspis helvola":              "オキアジ",           # オニアジ→
    "Sargocentron spiniferum":      "トガリエビス",       # イットウダイ→
    "Chaetodon trifascialis":       "ヤリカタギ",         # テンクチョウチョウウオ→
    "Labroides dimidiatus":         "ホンソメワケベラ",   # ニセクロジンベラ→
    "Gomphosus varius":             "クギベラ",           # タカノハダイ→
    "Plectroglyphidodon lacrymatus":"ルリホシスズメダイ", # ハクセンスズメダイ→
    "Kyphosus bigibbus":            "ノトイスズミ",       # イスズミ→
    "Scarus psittacus":             "オウムブダイ",       # イチモンジウブダイ→
    "Scarus ghobban":               "ヒブダイ",           # ダイダイフダイ→
    "Naso maculatus":               "ゴマテングハギモドキ", # ゴマニジダイ→

    # SKIP（変更しない）:
    # Apistus carinatus        ハチ  → Wikidata: ハチ(魚)  ← 同じ魚、表記ゆれのみ
    # Amblyeleotris japonica   ハチ  → Wikidata: ダテハゼ  ← Wikidata誤ヒット
    # Chaetodon ocellicaudus   コクテンカタギ → スポット… ← Wikidata英語名
    # Hemitaurichthys thompsoni トンプソン… → ・付き  ← 表記ゆれのみ
    # Paralichthys olivaceus   イソギンボ → ヒラメ  ← Wikidata誤ヒット
    # Platyrhina tangi         ウチワザメ → 制御文字付き  ← 同じ魚
    # Diodon hystrix           ヒトヅラハリセンボン → ネズミフグ  ← 種同定不確か
    # Enneapterygius etheostoma クレナイヘビギンポ → ヘビギンポ  ← 不確か
}


def main():
    with open(FISH_DATA, encoding="utf-8") as f:
        data = json.load(f)

    fixed = 0
    for entry in data:
        sci = entry.get("scientific_name", "").strip()
        if sci in CORRECTIONS:
            old = entry["japanese_name"]
            new = CORRECTIONS[sci]
            if old != new:
                print(f"  {old} → {new}  ({sci})")
                entry["japanese_name"] = new
                fixed += 1

    with open(FISH_DATA, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ {fixed} 件を修正しました")


if __name__ == "__main__":
    main()
