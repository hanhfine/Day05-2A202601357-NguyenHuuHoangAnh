"""run_eval.py — Chạy golden set qua verdict() và in bảng điểm.

Dùng ĐÚNG hàm mà UI dùng (core.verdict.verdict) — không fork sang đường riêng.
Kết quả trace ghi vào eval/traces/<timestamp>.json để so sánh mock vs real.

Chạy:
    python run_eval.py              # mode mock (không cần key)
    python run_eval.py --mode real  # mode real (cần OPENAI_API_KEY)
    python run_eval.py --mode real --save-trace
"""
import sys
import json
import time
import argparse
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

CODEBASE = Path(__file__).resolve().parent
sys.path.insert(0, str(CODEBASE))

from core.verdict import tai_data, verdict  # noqa: E402 — cần sys.path trước

# ── load data ─────────────────────────────────────────────────────────────────
GOLDEN_SET_PATH = CODEBASE / "eval" / "golden_set.json"
TRACES_DIR = CODEBASE / "eval" / "traces"


def load_golden_set() -> list[dict]:
    return json.loads(GOLDEN_SET_PATH.read_text(encoding="utf-8"))["cases"]


def _get(obj: dict, dotpath: str):
    """Lấy giá trị từ dict theo dotpath 'a.b.c'."""
    for k in dotpath.split("."):
        if not isinstance(obj, dict):
            return None
        obj = obj.get(k)
    return obj


def _kiem_them(kq: dict, kiem: dict) -> list[str]:
    """Kiểm các điều kiện phụ, trả về danh sách lỗi (rỗng = pass)."""
    loi = []
    for k, v in (kiem or {}).items():
        if k == "thieu_o_dau":
            if kq.get("thieu_o_dau") != v:
                loi.append(f"thieu_o_dau mong '{v}', nhận '{kq.get('thieu_o_dau')}'")
        elif k == "one_question_not_null":
            if v and not kq.get("one_question"):
                loi.append("one_question phải != null")
        elif k == "matched_empty":
            if v and kq.get("matched"):
                loi.append("matched phải rỗng khi thieu_thong_tin (vi phạm G10)")
        elif k == "hard_fail_empty":
            if v and kq.get("hard_fail"):
                loi.append("hard_fail phải rỗng (đây là gap, không phải hard_fail)")
        elif k == "gaps_not_empty":
            if v and not kq.get("gaps"):
                loi.append("gaps phải có ít nhất 1 phần tử")
        elif k == "canh_bao_not_empty":
            if v and not kq.get("canh_bao"):
                loi.append("canh_bao phải có ít nhất 1 phần tử")
        elif k == "canh_bao_min_length":
            n = len(kq.get("canh_bao") or [])
            if n < v:
                loi.append(f"canh_bao cần ≥{v} phần tử, có {n}")
        elif k == "deadline.ambiguous":
            actual = _get(kq, "deadline.ambiguous")
            if actual != v:
                loi.append(f"deadline.ambiguous mong {v}, nhận {actual}")
        elif k == "deadline.parsed":
            actual = _get(kq, "deadline.parsed")
            if actual != v:
                loi.append(f"deadline.parsed mong {v!r}, nhận {actual!r}")
        elif k == "not_stated_contains_gpa":
            ns = kq.get("not_stated") or []
            if v and not any("gpa" in s.lower() for s in ns):
                loi.append("not_stated phải chứa thông tin về GPA")
    return loi


def chay_eval(mode: str = "mock", save_trace: bool = False) -> int:
    """Chạy toàn bộ golden set. Trả về số case lỗi."""
    tin_ds, ho_so_ds = tai_data()
    tin_map = {t["id"]: t for t in tin_ds}
    hs_map = {p["id"]: p for p in ho_so_ds}
    cases = load_golden_set()

    traces = []
    loi_total = 0
    pass_count = 0

    # header
    col = f"{'ID':6} {'Tin':9} {'HồSơ':6} {'VerdictChờ':17} {'VerdictNhận':17} {'Grounding':10} {'Phụ':5} Ghi chú"
    print(col)
    print("─" * 110)

    for c in cases:
        opp_id = c["opp_id"]
        pid = c["profile_id"]
        mong = c["verdict_mong_doi"]
        kiem = c.get("kiem_them", {})

        if opp_id not in tin_map:
            print(f"  ⚠ {c['id']}: không tìm thấy {opp_id} trong data/postings.json")
            loi_total += 1
            continue
        if pid not in hs_map:
            print(f"  ⚠ {c['id']}: không tìm thấy {pid} trong data/profiles.json")
            loi_total += 1
            continue

        kq = verdict(tin_map[opp_id]["raw_text"], hs_map[pid], mode=mode)
        g = kq["_grounding"]

        ok_v = kq["verdict"] == mong
        ok_g = g["grounding_pass"]
        loi_phu = _kiem_them(kq, kiem)
        ok_phu = len(loi_phu) == 0

        case_pass = ok_v and ok_g and ok_phu
        if case_pass:
            pass_count += 1
        else:
            loi_total += 1

        verdict_icon = "✓" if ok_v else "✗"
        ground_icon = "✓" if ok_g else "✗"
        phu_icon = "✓" if ok_phu else "✗"

        print(
            f"{c['id']:6} {opp_id:9} {pid:6} {mong:17} {kq['verdict']:17} "
            f"{ground_icon} {g['so_dat']}/{g['so_khang_dinh']:<4} {phu_icon} {verdict_icon}  {c['nhan'][:45]}"
        )

        if not ok_v:
            print(f"       {'':9} {'':6} └─ verdict: chờ '{mong}', nhận '{kq['verdict']}'")
        if not ok_g:
            for chi in g.get("chi_tiet", []):
                if not chi["dat"]:
                    print(f"       {'':9} {'':6} └─ grounding L{chi['trich']}: {chi['vi_sao']}")
        for lp in loi_phu:
            print(f"       {'':9} {'':6} └─ phụ: {lp}")

        if save_trace:
            traces.append({
                "id": c["id"], "opp_id": opp_id, "profile_id": pid,
                "verdict_mong_doi": mong, "verdict_nhan": kq["verdict"],
                "grounding": g, "pass": case_pass, "mode": mode,
                "kq": kq,
            })

    total = len(cases)
    print("─" * 110)
    pct = pass_count / total * 100 if total else 0
    print(f"\n📊 Kết quả: {pass_count}/{total} pass ({pct:.0f}%)  |  mode={mode}")

    # phân tích theo rubric
    rubric_stats: dict[str, list[bool]] = {}
    for c, case_data in zip(cases, [None] * len(cases)):
        pass
    print(f"   nen_apply cases: {sum(1 for c in cases if c['verdict_mong_doi'] == 'nen_apply')}")
    print(f"   rui_ro_cao cases: {sum(1 for c in cases if c['verdict_mong_doi'] == 'rui_ro_cao')}")
    print(f"   thieu_thong_tin cases: {sum(1 for c in cases if c['verdict_mong_doi'] == 'thieu_thong_tin')}")

    if loi_total == 0:
        print("\n✅ TẤT CẢ GOLDEN SET ĐẠT")
    else:
        print(f"\n❌ {loi_total} CASE CHƯA ĐẠT")

    if save_trace and traces:
        TRACES_DIR.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        trace_file = TRACES_DIR / f"eval_{mode}_{ts}.json"
        trace_file.write_text(
            json.dumps({"mode": mode, "timestamp": ts, "traces": traces},
                       ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        print(f"\n💾 Trace đã lưu: {trace_file.relative_to(CODEBASE)}")

    return loi_total


def main() -> int:
    parser = argparse.ArgumentParser(description="Chạy golden set eval cho OpportunityMatch AI")
    parser.add_argument("--mode", choices=["mock", "real"], default="mock",
                        help="mock=không gọi AI, real=gọi LLM thật (cần OPENAI_API_KEY)")
    parser.add_argument("--save-trace", action="store_true",
                        help="Lưu kết quả trace vào eval/traces/ (dùng cho rubric R4)")
    parser.add_argument("--case", default=None,
                        help="Chỉ chạy 1 case theo ID, ví dụ: --case G-05")
    args = parser.parse_args()

    if args.case:
        # Chạy đơn case
        cases = load_golden_set()
        found = [c for c in cases if c["id"] == args.case]
        if not found:
            print(f"Không tìm thấy case '{args.case}'")
            return 1
        tin_ds, ho_so_ds = tai_data()
        tin_map = {t["id"]: t for t in tin_ds}
        hs_map = {p["id"]: p for p in ho_so_ds}
        c = found[0]
        kq = verdict(tin_map[c["opp_id"]]["raw_text"], hs_map[c["profile_id"]], mode=args.mode)
        print(json.dumps(kq, ensure_ascii=False, indent=2))
        return 0

    return 1 if chay_eval(mode=args.mode, save_trace=args.save_trace) > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
