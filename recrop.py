#!/usr/bin/env python3
"""
既存の page_XXX.jpg から photo / section を再クロップするスクリプト。
API呼び出しなし・コスト0で修正できる。

4ステップ処理:
  1. fish_data.json に登録済みの魚ページのみ対象（図鑑ページ確定済み）
  2. セクション行ごとに左寄り写真か右寄り写真かを輝度分散で分類
  3. 写真欄の列だけを切り取る（左 or 右半分）
  4. 写真列の中で、魚全体が映り、解説文が映らないよう縦にトリム
"""

import json
import numpy as np
from pathlib import Path
from PIL import Image

IMAGES_DIR = Path(__file__).parent / "images"
DATA_FILE  = Path(__file__).parent / "fish_data.json"

# 写真が左側にある場合の列範囲（全幅に対する割合）
PHOTO_LEFT_START  = 0.04   # 左端の縦書き科名帯を除く（答えのヒントになるため）
PHOTO_LEFT_END    = 0.49   # テキスト列との境界を安全に除く

# 写真が右側にある場合の列範囲
PHOTO_RIGHT_START = 0.45   # テキスト列との境界バッファ
PHOTO_RIGHT_END   = 0.96   # 右端の縦書き科名帯を除く（答えのヒントになるため）

# セクション内の縦トリム
# 上端マージン: セパレータ線だけ除く（最小限）
SECTION_TOP_MARGIN    = 0.01
# 下端マージン: 撮影地テキストは残してOKなので最小限
SECTION_BOTTOM_MARGIN = 0.05


def classify_photo_side(section_img: Image.Image) -> str:
    """
    セクション画像の左右を「彩度の平均値」で比較して写真側を判定する。
    海洋写真（青・緑・橙など色豊か）は彩度が高く、
    白地テキスト・線画図解（無彩色）は彩度が低い。
    中央20%（セパレータ帯）はスキップして干渉を避ける。
    """
    arr = np.array(section_img, dtype=np.float32)  # shape: (H, W, 3)
    w   = arr.shape[1]

    # セパレータ帯を避けて比較（左5〜45%、右55〜95%）
    l_start, l_end = int(w * 0.05), int(w * 0.45)
    r_start, r_end = int(w * 0.55), int(w * 0.95)

    # 彩度の近似 = max(R,G,B) - min(R,G,B)（ピクセルごと）
    left_region  = arr[:, l_start:l_end, :]
    right_region = arr[:, r_start:r_end, :]

    left_sat  = float(np.mean(left_region.max(axis=2)  - left_region.min(axis=2)))
    right_sat = float(np.mean(right_region.max(axis=2) - right_region.min(axis=2)))

    return "left" if left_sat >= right_sat else "right"


def recrop(data: list[dict]) -> list[dict]:
    # ページごとに魚の数をカウント
    page_counts: dict[int, int] = {}
    for entry in data:
        p = entry["page"]
        page_counts[p] = page_counts.get(p, 0) + 1

    updated = 0
    for entry in data:
        page_num   = entry["page"]
        fish_index = entry["fish_index"] - 1   # 0-based
        n          = page_counts[page_num]      # このページの魚の総数

        page_path = IMAGES_DIR / f"page_{page_num:03d}.jpg"
        if not page_path.exists():
            continue

        img = Image.open(page_path)
        w, h = img.size

        # ── セクション境界（縦方向） ─────────────────────────────────────
        sec_h   = h // n
        sec_top = sec_h * fish_index
        sec_bot = sec_h * (fish_index + 1)

        # セクション行を切り出す（分類用）
        section_row = img.crop((0, sec_top, w, sec_bot))

        # ── ステップ2: 写真側を分類 ───────────────────────────────────────
        photo_side = classify_photo_side(section_row)

        # ── ステップ3: 写真列を切り取る ──────────────────────────────────
        if photo_side == "left":
            col_left  = int(w * PHOTO_LEFT_START)
            col_right = int(w * PHOTO_LEFT_END)
        else:
            col_left  = int(w * PHOTO_RIGHT_START)
            col_right = int(w * PHOTO_RIGHT_END)

        # ── ステップ4: 縦トリム（解説テキスト行を除く） ──────────────────
        top_trim    = max(0, sec_top + int(sec_h * SECTION_TOP_MARGIN))
        bottom_trim = min(h, sec_bot - int(sec_h * SECTION_BOTTOM_MARGIN))

        photo_crop = img.crop((col_left, top_trim, col_right, bottom_trim))
        photo_path = IMAGES_DIR / f"photo_{page_num:03d}_{fish_index+1}.jpg"
        photo_crop.save(str(photo_path), "JPEG", quality=87)
        entry["photo_image"] = f"images/photo_{page_num:03d}_{fish_index+1}.jpg"

        # ── 解説画像: セクション行 全幅（上下3%バッファ付き） ──────────
        buf          = int(sec_h * 0.03)
        section_crop = img.crop((
            0,
            max(0, sec_top - buf),
            w,
            min(h, sec_bot + buf),
        ))
        section_path = IMAGES_DIR / f"section_{page_num:03d}_{fish_index+1}.jpg"
        section_crop.save(str(section_path), "JPEG", quality=85)
        entry["page_image"] = f"images/section_{page_num:03d}_{fish_index+1}.jpg"

        updated += 1
        if updated % 100 == 0:
            print(f"  {updated} 件処理済み...")

    return data


def main():
    print("📐 再クロップ開始...\n")
    with open(DATA_FILE, encoding="utf-8") as f:
        data = json.load(f)

    print(f"対象: {len(data)} 件")
    data = recrop(data)

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 完了: {len(data)} 件を再クロップ")
    print(f"   photo_XXX_N.jpg   ← 魚写真（左右自動判定 + 下部トリム）")
    print(f"   section_XXX_N.jpg ← 解説行（ページ 1/N 行）")


if __name__ == "__main__":
    main()
