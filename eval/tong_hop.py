"""Gộp eval/traces/*.json thành một bảng CSV đọc được bằng mắt.

    python eval/tong_hop.py            →  eval/traces.csv  + bảng tóm tắt ra màn hình
    python eval/tong_hop.py --tom-tat  →  chỉ in tóm tắt, không ghi file

VÌ SAO GIỮ CẢ HAI, KHÔNG THAY JSON BẰNG CSV:
  · JSON là BẰNG CHỨNG — có nguyên prompt và nguyên response. Rubric R5 đòi log lời
    gọi AI thật; một dòng CSV không dựng lại được prompt, nên không thay thế được.
  · CSV là MỤC LỤC — 112 file JSON thì không ai mở từng cái. CSV cho phép nhìn một
    phát ra: lượt nào tốn token nhất, lượt nào bị cắt giữa chừng (finish_reason =
    length), lượt nào gọi tool, chi phí dồn theo ngày.
Hai thứ trả lời hai câu hỏi khác nhau, bỏ cái nào cũng mất thông tin.
"""
import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

D = Path(__file__).resolve().parent
TRACES = D / "traces"

COT = ["thoi_gian", "loai", "provider", "model", "prompt_tokens", "cached_tokens",
       "completion_tokens", "total_tokens", "finish_reason", "so_message",
       "so_tool_call", "ten_tool", "file"]


def _tach_ten(ten: str) -> tuple[str, str]:
    """'20260730-121651-cv-gpt-4o-mini.json' → ('2026-07-30 12:16:51', 'cv').

    Tên model có dấu gạch ('gpt-4o-mini') nên KHÔNG tách bằng split('-')[-2] được —
    kiểu đó trả về '4o'. Nhãn luôn là mảnh thứ 3, phần còn lại là model.
    """
    p = ten.removesuffix(".json").split("-")
    if len(p) < 3 or len(p[0]) != 8:
        return "", "?"
    d, t = p[0], p[1]
    return f"{d[:4]}-{d[4:6]}-{d[6:]} {t[:2]}:{t[2:4]}:{t[4:]}", p[2]


def doc_mot(f: Path) -> dict | None:
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"  ⚠ bỏ qua {f.name}: {e}")
        return None
    req = d.get("request") or {}
    resp = d.get("response") or {}
    if isinstance(req, str):
        req = json.loads(req)
    if isinstance(resp, str):
        resp = json.loads(resp)

    u = resp.get("usage") or {}
    ch = (resp.get("choices") or [{}])[0]
    tc = (ch.get("message") or {}).get("tool_calls") or []
    thoi_gian, loai = _tach_ten(f.name)
    return {
        "thoi_gian": thoi_gian,
        "loai": loai,
        "provider": d.get("provider", ""),
        "model": d.get("model", ""),
        "prompt_tokens": u.get("prompt_tokens", ""),
        "cached_tokens": (u.get("prompt_tokens_details") or {}).get("cached_tokens", ""),
        "completion_tokens": u.get("completion_tokens", ""),
        "total_tokens": u.get("total_tokens", ""),
        "finish_reason": ch.get("finish_reason", ""),
        "so_message": len(req.get("messages") or []),
        "so_tool_call": len(tc),
        "ten_tool": "|".join(sorted({c.get("function", {}).get("name", "") for c in tc})),
        "file": f.name,
    }


def tom_tat(hang: list[dict]) -> None:
    if not hang:
        print("Chưa có trace nào trong eval/traces/.")
        return
    tong_tok = sum(int(h["total_tokens"] or 0) for h in hang)
    cached = sum(int(h["cached_tokens"] or 0) for h in hang)
    prompt = sum(int(h["prompt_tokens"] or 0) for h in hang)
    theo_loai = Counter(h["loai"] for h in hang)
    tool = Counter(t for h in hang for t in h["ten_tool"].split("|") if t)
    cat = [h["file"] for h in hang if h["finish_reason"] not in ("stop", "tool_calls", "")]

    print(f"\n{len(hang)} lời gọi · {tong_tok:,} token"
          f" (prompt {prompt:,}, trong đó {cached:,} được cache"
          f"{f' = {cached/prompt:.0%}' if prompt else ''})")
    print("  theo loại:", ", ".join(f"{k}={v}" for k, v in theo_loai.most_common()))
    print("  tool gọi :", ", ".join(f"{k}={v}" for k, v in tool.most_common()) or "không có")
    # finish_reason='length' nghĩa là model bị cắt giữa chừng — JSON trả về hỏng,
    # đây đúng là loại lỗi mà mở từng file JSON sẽ không bao giờ thấy.
    print(f"  bị cắt   : {len(cat)}" + (f" → {cat[:5]}" if cat else " (không có)"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Gộp trace JSON thành CSV")
    ap.add_argument("--tom-tat", action="store_true", help="chỉ in tóm tắt, không ghi CSV")
    ap.add_argument("--ra", default=str(D / "traces.csv"), help="đường dẫn CSV ra")
    a = ap.parse_args()

    if not TRACES.exists():
        print("Chưa có eval/traces/ — chạy app với API key thật để sinh trace.")
        return 1

    hang = [r for r in (doc_mot(f) for f in sorted(TRACES.glob("*.json"))) if r]
    tom_tat(hang)

    if a.tom_tat:
        return 0
    ra = Path(a.ra)
    with ra.open("w", encoding="utf-8-sig", newline="") as f:
        # utf-8-sig: Excel trên Windows mở utf-8 không BOM sẽ vỡ hết tiếng Việt.
        w = csv.DictWriter(f, fieldnames=COT)
        w.writeheader()
        w.writerows(hang)
    print(f"\n✓ Đã ghi {ra} ({len(hang)} dòng)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
