"""Thay họ tên thật trong eval/traces/*.json bằng [TÊN] trước khi commit.

    python eval/an_danh.py --thu    →  chỉ liệt kê sẽ sửa gì, không ghi
    python eval/an_danh.py          →  sửa tại chỗ

VÌ SAO CẦN: `core/cv.py` cố ý KHÔNG redact họ tên — hồ sơ giữ field `ten` để xưng
hô với học viên (xem docstring cv.py, đó là ngoại lệ có chủ ý của luật tối thiểu
hoá PII). Hệ quả là tên đi theo hồ sơ vào system prompt của MỌI lượt chat
(`agent.py` chèn cả hồ sơ vào prompt), nên nó nằm rải khắp trace chứ không riêng
trace `cv`. Bỏ file `*-cv-*.json` là chưa đủ.

VÌ SAO SỬA CHỨ KHÔNG BỎ HẲN TRACE: giá trị bằng chứng của trace (rubric R5) nằm ở
prompt, lời gọi tool, phán quyết và số token — không nằm ở cái tên. Thay tên đi thì
trace vẫn dựng lại được đúng hành vi hệ thống, mà không công khai dữ liệu cá nhân
của người thật (README luật 4).

ĐÁNH ĐỔI PHẢI NÓI RÕ: sau khi chạy, trace KHÔNG còn là bản sao nguyên văn của lời
gọi API nữa. Đó là lý do có file script này nằm trong repo thay vì sửa tay — ai
đọc cũng thấy được đã thay cái gì và thay thế nào.
"""
import argparse
import json
import re
import sys
from pathlib import Path

D = Path(__file__).resolve().parent
TRACES = D / "traces"
THAY_BANG = "[TÊN]"
sys.stdout.reconfigure(encoding="utf-8")

# Tên xuất hiện trong trace dưới dạng `"ten": "..."` (trong hồ sơ đính vào prompt,
# và trong JSON model trả về ở bước cv). Rút từ chính dữ liệu thay vì gõ cứng danh
# sách — chạy lại sau này vẫn bắt được tên mới.
RE_TEN = re.compile(r'\\?"ten\\?"\s*:\s*\\?"([^"\\]{2,60})\\?"')


def an_toan_de_thay(t: str) -> bool:
    """Chỉ thay tên đủ dài và có ≥2 chữ.

    Tên ngắn một chữ là quá nguy hiểm cho phép thay chuỗi: field `ten` từng nhận
    giá trị "Test" (tên tôi gõ lúc chạy thử), mà thay "Test" khắp file thì
    "Automation Tester" thành "Automation [TÊN]er" và "test automation" thành
    "[TÊN] automation" — hỏng chính nội dung tin tuyển dụng đang cần làm bằng chứng.
    Tên thật của người Việt luôn ≥2 chữ nên ràng buộc này không bỏ sót ai.
    """
    return len(t) >= 8 and len(t.split()) >= 2


def tim_ten() -> tuple[set[str], set[str]]:
    """→ (tên sẽ thay, tên bỏ qua vì quá ngắn/một chữ)."""
    thay, bo = set(), set()
    for f in TRACES.glob("*.json"):
        for m in RE_TEN.findall(f.read_text(encoding="utf-8")):
            t = m.strip()
            if not t or t.upper() in ("NULL", "NONE") or t == THAY_BANG:
                continue
            (thay if an_toan_de_thay(t) else bo).add(t)
    return thay, bo


def main() -> int:
    ap = argparse.ArgumentParser(description="Ẩn danh họ tên trong trace")
    ap.add_argument("--thu", action="store_true", help="chỉ liệt kê, không ghi file")
    # tim_ten() chỉ bắt được tên nằm ở field `"ten"`. Tên viết trong THÂN CV (dòng
    # đầu file CV) thì không có nhãn nào để bám — nếu lượt đó model trả `ten: null`
    # thì tên vẫn nằm nguyên trong prompt mà máy không thấy. Ca thật: một CV có
    # "NGUYEN HUU HOANG ANH" ở dòng đầu, lọt qua lượt quét đầu tiên.
    # Nên phải luôn soát mắt sau khi chạy, và khai tay bằng cờ này.
    ap.add_argument("--them", nargs="*", default=[], metavar="TÊN",
                    help="tên khai tay, cho trường hợp không nằm ở field `ten`")
    a = ap.parse_args()

    if not TRACES.exists():
        print("Chưa có eval/traces/.")
        return 1
    ten, bo_qua = tim_ten()
    for t in a.them:
        (ten if an_toan_de_thay(t) else bo_qua).add(t.strip())
    if bo_qua:
        print(f"⚠ BỎ QUA {len(bo_qua)} giá trị quá ngắn/một chữ: {', '.join(sorted(bo_qua))}")
        print("  (thay chuỗi ngắn sẽ phá nội dung tin — xem an_toan_de_thay().")
        print("   Nếu đó là tên người thật thì phải xử lý tay.)\n")
    if not ten:
        print("✓ Không có họ tên nào cần thay.")
        return 0

    print(f"Sẽ thay {len(ten)} tên: {', '.join(sorted(ten))}\n")
    # Thay tên DÀI trước: nếu không, thay "NGUYEN" trước sẽ phá vỡ "NGUYEN VAN A"
    # thành "[TÊN] VAN A" và phần đuôi ở lại.
    thu_tu = sorted(ten, key=len, reverse=True)
    sua = 0
    for f in sorted(TRACES.glob("*.json")):
        s = goc = f.read_text(encoding="utf-8")
        for t in thu_tu:
            s = s.replace(t, THAY_BANG)
        if s == goc:
            continue
        sua += 1
        n = sum(goc.count(t) for t in thu_tu)
        print(f"  {'(thử) ' if a.thu else ''}{f.name}: {n} chỗ")
        if not a.thu:
            # Ghi xong phải đọc lại được bằng JSON — thay chuỗi trong file JSON có
            # thể làm hỏng cú pháp nếu tên chứa ký tự đặc biệt.
            try:
                json.loads(s)
            except json.JSONDecodeError as e:
                print(f"    ✗ BỎ QUA — thay xong không parse được JSON: {e}")
                continue
            f.write_text(s, encoding="utf-8")

    print(f"\n{'Sẽ sửa' if a.thu else '✓ Đã sửa'} {sua} file.")
    if a.thu:
        print("Chạy lại không kèm --thu để ghi thật.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
