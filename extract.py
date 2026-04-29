#!/usr/bin/env python3
"""
海水魚ガイドブック PDF → クイズ用データ抽出スクリプト

使い方:
  python3 extract.py                  # 全ページ処理
  python3 extract.py --start 20       # ページ20から再開
  python3 extract.py --dry-run        # 最初の5ページだけテスト
"""

import anthropic
import base64
import json
import os
import time
import argparse
from pathlib import Path
from pdf2image import convert_from_path

PDF_PATH   = "/Users/harutakizawa/Desktop/claude code/my-hq-bot/ネイチャーウォッチングガイドブック 海水魚.pdf"
OUTPUT_DIR = Path(__file__).parent / "images"
DATA_FILE  = Path(__file__).parent / "fish_data.json"

PAGE_START = 20
PAGE_END   = 392
MODEL      = "claude-haiku-4-5-20251001"
MAX_RETRIES = 3


def image_to_b64(img) -> str:
    import io
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=72)
    return base64.standard_b64encode(buf.getvalue()).decode()


def extract_fish_from_page(client, page_img, page_num: int) -> list[dict]:
    """Claude Haiku でページから魚情報を抽出。"""
    prompt = """この海水魚図鑑ページを解析してください。
1〜3種の魚が上から順に掲載されています。各魚の和名・学名・科名を返してください。

JSON形式のみで返答（説明不要）:
{"fish": [{"japanese_name": "...", "scientific_name": "...", "family": "..."}]}

魚の図鑑ページでない場合（目次・序文・撮影技術の解説など）:
{"fish": [], "skip": true}"""

    for attempt in range(MAX_RETRIES):
        try:
            resp = client.messages.create(
                model=MODEL,
                max_tokens=300,
                messages=[{"role": "user", "content": [
                    {"type": "image", "source": {
                        "type": "base64", "media_type": "image/jpeg",
                        "data": image_to_b64(page_img),
                    }},
                    {"type": "text", "text": prompt}
                ]}]
            )
            text = resp.content[0].text.strip()
            s, e = text.find("{"), text.rfind("}") + 1
            if s == -1:
                return []
            data = json.loads(text[s:e])
            if data.get("skip"):
                return []
            return data.get("fish", [])
        except Exception as ex:
            if attempt < MAX_RETRIES - 1:
                time.sleep(5)
            else:
                print(f"  [ERROR] p{page_num}: {ex}")
                return []


def crop_fish_photo(page_img, fish_index: int, total_fish: int):
    """ページ画像から魚の写真部分（左半分 × 縦1/N）をクロップ。"""
    w, h = page_img.size
    section_h = h // total_fish
    top    = max(0, section_h * fish_index + int(section_h * 0.03))
    bottom = min(h, section_h * (fish_index + 1) - int(section_h * 0.03))
    right  = int(w * 0.48)
    return page_img.crop((0, top, right, bottom))


def load_existing() -> list[dict]:
    if DATA_FILE.exists():
        with open(DATA_FILE, encoding="utf-8") as f:
            return json.load(f)
    return []


def save(data: list[dict]):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start",   type=int, default=PAGE_START)
    parser.add_argument("--end",     type=int, default=PAGE_END)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        args.end = args.start + 4

    OUTPUT_DIR.mkdir(exist_ok=True)

    from dotenv import load_dotenv
    load_dotenv("/Users/harutakizawa/Desktop/claude code/my-hq-bot/.env")
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    all_data  = load_existing()
    done_pages = {d["page"] for d in all_data}
    skipped = 0

    print(f"\n📚 抽出開始 (p{args.start}〜p{args.end})\n")

    for page_num in range(args.start, args.end + 1):
        if page_num in done_pages:
            print(f"  [skip] p{page_num} (既処理)")
            continue

        try:
            pages = convert_from_path(PDF_PATH, first_page=page_num, last_page=page_num, dpi=120)
            page_img = pages[0]
        except Exception as e:
            print(f"  [ERROR] p{page_num} PDF変換失敗: {e}")
            continue

        # 全ページ画像保存
        page_path = OUTPUT_DIR / f"page_{page_num:03d}.jpg"
        page_img.save(str(page_path), "JPEG", quality=82)

        print(f"  [p{page_num:03d}] 解析中...", end="", flush=True)
        fish_list = extract_fish_from_page(client, page_img, page_num)

        if not fish_list:
            skipped += 1
            print(" ← スキップ")
            page_path.unlink(missing_ok=True)
            continue

        n = len(fish_list)
        for i, fish in enumerate(fish_list):
            photo_path = OUTPUT_DIR / f"photo_{page_num:03d}_{i+1}.jpg"
            crop_fish_photo(page_img, i, n).save(str(photo_path), "JPEG", quality=85)
            all_data.append({
                "page":            page_num,
                "fish_index":      i + 1,
                "japanese_name":   fish.get("japanese_name", "不明"),
                "scientific_name": fish.get("scientific_name", ""),
                "family":          fish.get("family", ""),
                "page_image":      f"images/page_{page_num:03d}.jpg",
                "photo_image":     f"images/photo_{page_num:03d}_{i+1}.jpg",
            })

        save(all_data)
        names = " / ".join(f["japanese_name"] for f in fish_list)
        print(f" ✅ {names}")
        time.sleep(0.3)

    print(f"\n✅ 完了 | 魚種: {len(all_data)}件 | スキップ: {skipped}ページ")


if __name__ == "__main__":
    main()
