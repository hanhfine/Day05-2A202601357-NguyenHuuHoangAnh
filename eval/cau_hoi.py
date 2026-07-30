"""Rút câu hỏi thật của người dùng từ eval/traces/ để soi lỗ hổng của hệ thống.

    python eval/cau_hoi.py              →  eval/cau_hoi.csv + bảng cờ đỏ ra màn hình
    python eval/cau_hoi.py --co-van-de  →  chỉ in các lượt bị gắn cờ
    python eval/cau_hoi.py --tom-tat    →  chỉ in tóm tắt, không ghi file

VÌ SAO TỰ ĐỘNG GẮN CỜ, KHÔNG CHỈ DUMP CÂU HỎI:
Đọc tay 112 dòng thì mắt sẽ trượt qua đúng những lỗi cần tìm — câu trả lời trông
mượt nhưng sai. Nên mỗi lượt được máy soi theo các luật đã khai trong prompt
(`core/agent.py`): tự bịa link, tự ghép mã tin, nói "không có tin nào" rồi dừng,
đòi tìm tin mà không gọi tool, vượt 150 từ, bị cắt giữa chừng. Cờ là GIẢ THUYẾT
cần người xác nhận, không phải kết luận.

QUYỀN RIÊNG TƯ — đọc trước khi commit file CSV sinh ra:
  · BỎ HẲN trace `cv`. Nội dung CV là PII, không đưa vào bảng review.
  · Text rút ra đều đi qua `cv.redact()` để thay email/SĐT/link/CCCD.
  · redact KHÔNG bắt được tên người (xem `core/cv.py`). Nếu có người từng gõ tên
    vào chat thì tên vẫn còn trong CSV — soát mắt trước khi commit.
"""
import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

D = Path(__file__).resolve().parent
sys.path.insert(0, str(D.parent / "codebase"))
sys.stdout.reconfigure(encoding="utf-8")

from core import cv  # noqa: E402  — cần sys.path ở trên

TRACES = D / "traces"
COT = ["thoi_gian", "loai", "cau_hoi", "tool_da_goi", "tool_args", "tra_loi",
       "co_van_de", "finish_reason", "so_message", "file"]

# Ý định người dùng đang muốn TÌM TIN — nếu lượt này không gọi tool nào mà model
# vẫn trả lời, rất dễ là nó tự phát biểu từ trí nhớ. Đúng lỗi ① phải chống.
RE_MUON_TIM = re.compile(r"tìm|tim\b|có tin|vị trí|việc|job|intern|thực tập|học bổng", re.I)
RE_MUON_DOI_CHIEU = re.compile(r"đối chiếu|doi chieu|xem tin|chi tiết|phù hợp không", re.I)
RE_NOI_KHONG_CO = re.compile(
    r"không có tin nào|không tìm thấy tin|hiện tại không có|chưa có tin nào", re.I)
RE_LINK = re.compile(r"https?://|www\.|\.com|\.vn/|github\.com", re.I)
RE_MA_TIN = re.compile(r"\b(?:OPP|REAL)[-A-Za-z]*-?\d{3}\b")
RE_MA_DUNG = re.compile(r"^(?:OPP|REAL)-\d{3}$")


def _tach_ten(ten: str) -> tuple[str, str]:
    p = ten.removesuffix(".json").split("-")
    if len(p) < 3 or len(p[0]) != 8:
        return "", "?"
    d, t = p[0], p[1]
    return f"{d[:4]}-{d[4:6]}-{d[6:]} {t[:2]}:{t[2:4]}:{t[4:]}", p[2]


def _sach(s: str, n: int = 400) -> str:
    """Redact rồi gộp khoảng trắng. CSV một dòng nên phải bỏ newline."""
    s, _ = cv.redact(s or "")
    return re.sub(r"\s+", " ", s).strip()[:n]


def _da_dung_tool(messages: list) -> bool:
    """Lượt này đã có kết quả tool chưa?

    MỘT LƯỢT CHAT SINH NHIỀU TRACE: trace 1 model gọi tool (finish=tool_calls),
    trace 2 model viết câu trả lời TỪ kết quả tool đó. Trace 2 không tự gọi tool
    nữa — đúng quy trình, không phải vi phạm. Bản đầu của hàm _soi() gắn cờ nhầm
    toàn bộ trace 2, cho ra 31% "vi phạm" mà thực chất gần hết là dương tính giả.
    Nên phải hỏi: sau câu user gần nhất, có message role=tool nào không.
    """
    idx = max((i for i, m in enumerate(messages) if m.get("role") == "user"), default=-1)
    return any(m.get("role") == "tool" for m in messages[idx + 1:])


def _soi(cau_hoi: str, tool: str, tra_loi: str, finish: str,
         da_dung_tool: bool = False, loai: str = "chat") -> list[str]:
    """Gắn cờ theo đúng các luật đã khai trong core/agent.py. Cờ = nghi vấn, không phải án.

    LUẬT TOOL CHỈ ÁP CHO TRACE `chat`. `verdict` là lời gọi JSON một phát, KHÔNG khai
    tool nào — bắt nó "không gọi tim_tin" là vô nghĩa. Bản đầu áp chung nên 15/23 cờ
    là dương tính giả từ verdict. Luật giọng (≤150 từ) cũng không áp: verdict trả JSON
    theo schema, dài là đúng.
    """
    co = []
    if finish not in ("stop", "tool_calls", ""):
        co.append(f"bị cắt giữa chừng ({finish})")
    if loai != "chat":
        return co
    # Luật 2 agent.py: cấm tự gõ URL — link chỉ đến từ field url của tim_tin.
    if RE_LINK.search(tra_loi):
        co.append("tự gõ link trong câu trả lời")
    # Luật 9: mã tin phải chép y nguyên opp_id.
    sai_ma = [m for m in RE_MA_TIN.findall(tra_loi) if not RE_MA_DUNG.match(m)]
    if sai_ma:
        co.append(f"mã tin sai định dạng: {sorted(set(sai_ma))}")
    # Luật 0: cấm trả lời suông "không có tin nào" rồi dừng.
    if RE_NOI_KHONG_CO.search(tra_loi) and not RE_MA_TIN.search(tra_loi):
        co.append("nói không có tin mà không đưa tin gần đúng nào")
    # Luật 1: muốn biết gì về tin đều phải gọi tool, không được nói từ trí nhớ.
    # `da_dung_tool` chặn dương tính giả ở trace thứ 2 của cùng một lượt — xem
    # chú thích ở _da_dung_tool().
    if not tool and not da_dung_tool and tra_loi:
        if RE_MUON_DOI_CHIEU.search(cau_hoi):
            co.append("đòi đối chiếu mà không gọi doi_chieu")
        elif RE_MUON_TIM.search(cau_hoi) and not RE_MA_TIN.search(tra_loi):
            co.append("đòi tìm tin mà không gọi tim_tin")
    # Luật 9: giọng — tối đa 150 từ.
    if len(tra_loi.split()) > 150:
        co.append(f"dài {len(tra_loi.split())} từ (luật: ≤150)")
    return co


def doc_mot(f: Path) -> dict | None:
    loai = _tach_ten(f.name)[1]
    if loai == "cv":            # PII — không đưa nội dung CV vào bảng review
        return None
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    req = d.get("request") or {}
    resp = d.get("response") or {}
    if isinstance(req, str):
        req = json.loads(req)
    if isinstance(resp, str):
        resp = json.loads(resp)

    us = [m for m in (req.get("messages") or []) if m.get("role") == "user"]
    if not us:
        return None
    cau_hoi = _sach(us[-1].get("content") or "", 300)   # message user mới nhất = câu kích hoạt lượt này

    ch = (resp.get("choices") or [{}])[0]
    msg = ch.get("message") or {}
    tc = msg.get("tool_calls") or []
    tra_loi = _sach(msg.get("content") or "")
    tool = "|".join(c.get("function", {}).get("name", "") for c in tc)
    args = _sach("|".join(c.get("function", {}).get("arguments", "") for c in tc), 200)
    finish = ch.get("finish_reason", "")

    return {"thoi_gian": _tach_ten(f.name)[0], "cau_hoi": cau_hoi,
            "tool_da_goi": tool, "tool_args": args, "tra_loi": tra_loi,
            "loai": loai,
            "co_van_de": " ; ".join(_soi(cau_hoi, tool, tra_loi, finish,
                                         _da_dung_tool(req.get("messages") or []), loai)),
            "finish_reason": finish, "so_message": len(req.get("messages") or []),
            "file": f.name}


def tom_tat(hang: list[dict]) -> None:
    if not hang:
        print("Chưa có trace chat/verdict nào trong eval/traces/.")
        return
    co_co = [h for h in hang if h["co_van_de"]]
    cờ = Counter(c.split(" (")[0].split(":")[0].strip()
                 for h in co_co for c in h["co_van_de"].split(" ; "))
    hoi = Counter(h["cau_hoi"] for h in hang if h["cau_hoi"])

    print(f"\n{len(hang)} lượt gọi · {len(hoi)} câu hỏi khác nhau · "
          f"{len(co_co)} lượt bị gắn cờ ({len(co_co)/len(hang):.0%})")
    print("\nCỜ ĐỎ theo loại (là nghi vấn cần soát tay, không phải kết luận):")
    for k, v in cờ.most_common():
        print(f"  {v:3}  {k}")
    if not cờ:
        print("  (không có)")
    print("\nCâu hỏi hay gặp nhất:")
    for q, n in hoi.most_common(8):
        print(f"  {n:3}×  {q[:78]}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Rút câu hỏi người dùng từ trace để soi lỗ hổng")
    ap.add_argument("--co-van-de", action="store_true", help="chỉ in các lượt bị gắn cờ")
    ap.add_argument("--tom-tat", action="store_true", help="chỉ in tóm tắt, không ghi CSV")
    ap.add_argument("--ra", default=str(D / "cau_hoi.csv"))
    a = ap.parse_args()

    if not TRACES.exists():
        print("Chưa có eval/traces/.")
        return 1
    hang = [r for r in (doc_mot(f) for f in sorted(TRACES.glob("*.json"))) if r]
    tom_tat(hang)

    if a.co_van_de:
        print("\n── Chi tiết các lượt bị gắn cờ ──")
        for h in hang:
            if h["co_van_de"]:
                print(f"\n[{h['thoi_gian']}] {h['file']}")
                print(f"  hỏi   : {h['cau_hoi'][:150]}")
                print(f"  tool  : {h['tool_da_goi'] or '(không gọi tool)'} {h['tool_args'][:90]}")
                print(f"  đáp   : {h['tra_loi'][:150]}")
                print(f"  ⚠ CỜ  : {h['co_van_de']}")
        return 0
    if a.tom_tat:
        return 0

    ra = Path(a.ra)
    with ra.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COT)
        w.writeheader()
        w.writerows(hang)
    print(f"\n✓ Đã ghi {ra} ({len(hang)} dòng)")
    print("  ⚠ CSV này chứa text người dùng đã gõ. redact bắt email/SĐT/link/CCCD "
          "nhưng KHÔNG bắt tên người — soát mắt trước khi commit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
