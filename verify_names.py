#!/usr/bin/env python3
"""
Wikidata API を使って fish_data.json の和名を一括検証するスクリプト。
API コスト0 / 外部ライブラリ不要（urllib・json のみ）

処理フロー:
  Phase 1: 科学名 → Wikidata エンティティ ID（逐次検索）
  Phase 2: ID リスト → 日本語ラベル（50件ずつバッチ取得）
  Phase 3: 差異を報告
"""

import json
import urllib.error
import urllib.request
import urllib.parse
import time
from pathlib import Path

FISH_DATA = Path(__file__).parent / "fish_data.json"
REPORT    = Path(__file__).parent / "name_verify_report.json"

WIKIDATA  = "https://www.wikidata.org/w/api.php"
DELAY     = 1.0    # 秒（Wikidata レート制限回避、約30req/min）
RETRY_MAX = 5      # 429 時の最大リトライ回数
BATCH     = 50     # ラベル取得のバッチサイズ


# ── ユーティリティ ────────────────────────────────────────────────

def fetch_json(url: str) -> dict | None:
    """429 の場合は exponential backoff でリトライする。"""
    wait = 5.0
    for attempt in range(RETRY_MAX):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "FishQuizVerifier/1.0 (https://github.com/HaruTakiFreelance/fish-quiz)"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                print(f"  [429] レート制限。{wait:.0f}秒後にリトライ ({attempt+1}/{RETRY_MAX})...")
                time.sleep(wait)
                wait *= 2
            else:
                return None
        except Exception:
            return None
    return None


def search_entity(sci_name: str) -> str | None:
    """科学名で Wikidata エンティティ ID を検索する。
    フィルターなし・件数10で最初の生物分類一致を返す。
    """
    query = urllib.parse.urlencode({
        "action":   "wbsearchentities",
        "search":   sci_name,
        "language": "en",
        "type":     "item",
        "format":   "json",
        "limit":    "10",
    })
    data = fetch_json(f"{WIKIDATA}?{query}")
    if not data:
        return None

    results = data.get("search", [])
    if not results:
        return None

    # 説明文に分類学キーワードが含まれる最初の結果を優先
    TAXON_KW = {"taxon", "species", "genus", "family", "fish", "shark", "ray"}
    for result in results:
        desc = result.get("description", "").lower()
        if any(kw in desc for kw in TAXON_KW):
            return result["id"]

    # なければ先頭を返す
    return results[0]["id"]


def batch_get_labels(entity_ids: list[str]) -> dict[str, str]:
    """最大 BATCH 件の ID に対して日本語ラベルをまとめて取得する。
    | はエンコードせず直接 URL に埋め込む。
    """
    base = urllib.parse.urlencode({
        "action":    "wbgetentities",
        "languages": "ja",
        "props":     "labels",
        "format":    "json",
    })
    ids_str = urllib.parse.quote("|".join(entity_ids), safe="|")
    url = f"{WIKIDATA}?{base}&ids={ids_str}"
    data = fetch_json(url)
    if not data:
        return {}

    result = {}
    for qid, entity in data.get("entities", {}).items():
        ja = entity.get("labels", {}).get("ja", {}).get("value")
        if ja:
            result[qid] = ja
    return result


def normalize(name: str) -> str:
    """比較用の正規化（全角スペース・長音符の表記ゆれを吸収）。"""
    return name.strip().replace("　", "").replace(" ", "")


# ── メイン ───────────────────────────────────────────────────────

def main():
    with open(FISH_DATA, encoding="utf-8") as f:
        raw = json.load(f)

    # 重複科学名は 1 件だけ処理
    seen: set[str] = set()
    fish_list: list[dict] = []
    for entry in raw:
        sci = entry.get("scientific_name", "").strip()
        if sci and sci not in seen:
            seen.add(sci)
            fish_list.append({
                "sci":    sci,
                "stored": entry.get("japanese_name", ""),
                "family": entry.get("family", ""),
            })

    total = len(fish_list)
    print(f"検証開始: {total} 件（ユニーク科学名）\n")

    # ── Phase 1: エンティティ ID を収集 ───────────────────────────
    sci_to_qid: dict[str, str]  = {}
    not_found:  list[dict]      = []

    print("Phase 1: Wikidata 検索中...")
    for i, fish in enumerate(fish_list):
        sci = fish["sci"]
        if (i + 1) % 100 == 0 or i == 0:
            print(f"  {i+1}/{total} 処理中...")

        qid = search_entity(sci)
        if qid:
            sci_to_qid[sci] = qid
        else:
            not_found.append({"sci": sci, "stored": fish["stored"]})
        time.sleep(DELAY)

    print(f"  → ID 取得: {len(sci_to_qid)} 件 / 未発見: {len(not_found)} 件\n")

    # ── Phase 2: 日本語ラベルをバッチ取得 ─────────────────────────
    qid_to_ja: dict[str, str] = {}
    qids = list(sci_to_qid.values())

    print("Phase 2: 日本語ラベル取得中...")
    for i in range(0, len(qids), BATCH):
        batch = qids[i : i + BATCH]
        labels = batch_get_labels(batch)
        qid_to_ja.update(labels)
        print(f"  {min(i + BATCH, len(qids))}/{len(qids)} 完了")
        time.sleep(DELAY)

    print(f"  → ラベル取得: {len(qid_to_ja)} 件\n")

    # ── Phase 3: 比較 ─────────────────────────────────────────────
    ok:        list[dict] = []
    mismatches:list[dict] = []
    no_label:  list[dict] = []

    for fish in fish_list:
        sci     = fish["sci"]
        stored  = fish["stored"]
        qid     = sci_to_qid.get(sci)
        if not qid:
            continue
        ja = qid_to_ja.get(qid)
        if not ja:
            no_label.append({"sci": sci, "stored": stored, "qid": qid})
            continue

        if normalize(ja) == normalize(stored):
            ok.append({"sci": sci, "name": stored})
        else:
            mismatches.append({
                "sci":      sci,
                "stored":   stored,
                "wikidata": ja,
                "qid":      qid,
                "family":   fish["family"],
            })

    # ── レポート出力 ──────────────────────────────────────────────
    report = {
        "summary": {
            "total":       total,
            "ok":          len(ok),
            "mismatches":  len(mismatches),
            "not_found":   len(not_found),
            "no_ja_label": len(no_label),
        },
        "mismatches": mismatches,
        "not_found":  not_found,
        "no_ja_label": no_label,
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 60)
    print(f"  検証完了")
    print(f"  ✅ 一致:       {len(ok)} 件")
    print(f"  ❌ 不一致:     {len(mismatches)} 件")
    print(f"  ⚠️  Wikidata未発見: {len(not_found)} 件")
    print(f"  ⚠️  和名ラベルなし: {len(no_label)} 件")
    print(f"  📄 レポート:   {REPORT}")
    print("=" * 60)

    if mismatches:
        print("\n--- 不一致トップ30 ---")
        for m in mismatches[:30]:
            print(f"  [{m['family']}] {m['stored']} → Wikidata: {m['wikidata']}  ({m['sci']})")


if __name__ == "__main__":
    main()
