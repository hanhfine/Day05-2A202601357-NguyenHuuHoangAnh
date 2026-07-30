"""Lõi phán quyết — MỘT hàm `verdict()`, HAI người gọi: server.py (UI) và run_eval.py (đo).

Quyết định kiến trúc quan trọng nhất của nhóm (ke-hoach.md §3): nếu UI và eval chạy hai
đường prompt khác nhau thì bảng % ở eval không nói gì về cái đem đi demo.

Hai chế độ:
  mode="mock"  — luật if/else, KHÔNG gọi AI. Dùng cho CP2 (flow bấm được) và làm
                 baseline để so với AI ở CP3.
  mode="real"  — gọi LLM thật ở đúng quyết định trung tâm. Dùng từ CP3.
Cả hai chế độ trả về CÙNG một schema, nên UI và eval không cần biết đang chạy chế độ nào.
"""
import json
import re
import time
import unicodedata
from pathlib import Path

from . import llm

CODEBASE = Path(__file__).resolve().parent.parent

# ── nhận dạng cho chế độ mock ────────────────────────────────────────────────
RE_DONG_YEUCAU = re.compile(
    r"yêu cầu|điều kiện|đối tượng|ưu tiên|bắt buộc|hồ sơ|cam kết|dành cho|gpa|"
    r"sinh viên|ứng viên|thành thạo|biết |lưu ý|đóng phí", re.I)
# Hạn nộp phải là NHÃN "Hạn...:" chứ không phải chữ "hạn" nằm đâu đó trong tin.
# Bản cũ bắt trần `hạn|deadline` nên trên tin thật nó vớ phải "...BHXH, BHYT, BHTN...
# số lượng có hạn" và câu tiếng Anh "within established deadlines" — rồi báo nguyên
# dòng đó ra làm hạn nộp. Tức là bịa ra một cái hạn tin không hề có.
RE_HAN = re.compile(
    r"\bhạn\s*(?:nộp|chót|cuối|nhận|đăng\s*ký|ứng\s*tuyển)?\s*(?:hồ\s*sơ)?\s*:"
    r"|\bhết\s*hạn\b\s*:?"
    r"|\bdeadline\s*:", re.I)
RE_NGAY = re.compile(r"\b(\d{1,2})\s*[/-]\s*(\d{1,2})(?:\s*[/-]\s*(\d{2,4}))?\b")
RE_GPA = re.compile(r"gpa[^\d]{0,25}(\d[.,]\d{1,2})", re.I)
RE_MOI_NAM = re.compile(r"mọi năm|tất cả các năm|kể cả năm nhất|không yêu cầu năm", re.I)
RE_NAM_ONE = re.compile(r"năm\s*([1-6])(?![0-9])", re.I)
RE_NAM_LIST = re.compile(r"năm\s*((?:[1-6]\s*[,và ]+)*[1-6])(?![0-9])", re.I)
RE_NAM_RANGE = re.compile(r"năm\s*([1-6])\s*[-–]\s*([1-6])(?![0-9])", re.I)
RE_TRO_LEN = re.compile(r"trở lên", re.I)
# "chỉ nhận hồ sơ tại Đà Nẵng" KHÔNG vào đây: đó là chi phí đi lại, không phải
# điều kiện tư cách. Xếp nó là hard_fail sẽ chặn oan người vẫn apply được (luật 4).
RE_BAT_BUOC = re.compile(r"bắt buộc|tối thiểu|chính quy|phải chưa", re.I)
RE_UU_TIEN = re.compile(r"ưu tiên", re.I)
RE_PHI = re.compile(r"đóng phí|phí xử lý|phí hồ sơ|đặt cọc|chuyển khoản trước", re.I)
RE_BAT_THUONG = re.compile(r"\bzalo\b|\binbox\b|số lượng có hạn|tuyển gấp", re.I)
RE_CITY = re.compile(r"(hà nội|tp\.?\s?hcm|hồ chí minh|đà nẵng|huế|cần thơ)", re.I)
RE_ONSITE = re.compile(r"onsite|văn phòng|bản cứng|tại văn phòng", re.I)
RE_ONLINE = re.compile(r"\bonline\b|remote|từ xa", re.I)
RE_NGANH = re.compile(r"ngành", re.I)
RE_DOC = re.compile(
    r"\bcv\b|bảng điểm|thư giới thiệu|bài luận|đơn xin|portfolio|giấy xác nhận|"
    r"link 1 project", re.I)
RE_DONG_HOSO = re.compile(r"^\s*(yêu cầu )?hồ sơ", re.I)      # dòng chỉ liệt kê giấy tờ
RE_DONG_TIEUDE = re.compile(r"^\s*[^:]{0,20}:\s*$")            # dòng tiêu đề trống, vd "Yêu cầu:"
RE_KHONG_YEUCAU = re.compile(r"^\s*không yêu cầu", re.I)

# ③ ngoài phạm vi — bắt qua ô "hỏi thêm" của UI
NGOAI_PHAM_VI = [
    (re.compile(r"viết (giúp|hộ|luôn)?\s*(cv|thư|cover letter|bài luận|đơn|email)", re.I),
     "Mình không viết hộ CV/thư/bài luận. Nhưng mình chỉ ra được 3 yêu cầu trong tin "
     "mà bạn nên nhắc tới khi tự viết — xem ô \"Việc cần làm\"."),
    (re.compile(r"(có đỗ|đỗ không|bao nhiêu ?%|xác suất|cơ hội bao nhiêu|khả năng đỗ)", re.I),
     "Mình không dự đoán bạn có đỗ hay không — mình không biết bạn cạnh tranh với ai. "
     "Mình chỉ đối chiếu được hồ sơ bạn khai với chữ trong tin."),
    (re.compile(r"(tìm|gợi ý|cho mình|liệt kê).{0,20}(tin|học bổng|cơ hội|chỗ)|tin nào khác", re.I),
     "Mình không đi tìm tin — mình chỉ đối chiếu MỘT tin bạn dán vào. "
     "Bạn dán tin tiếp theo thì mình đối chiếu tiếp."),
    (re.compile(r"(lương|mức lương|công ty nào tốt|nên chọn công ty|so sánh công ty)", re.I),
     "Mình không so sánh lương hay đánh giá công ty. Mình chỉ đọc được những gì tin này ghi."),
]

KY_NANG_TU = {
    "python": "Python", "sql": "SQL", "excel": "Excel", "pandas": "pandas",
    "machine learning": "ML", " ml ": "ML", "llm": "LLM API", "c++": "C++",
}


def _khong_dau(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def danh_so_dong(text: str) -> list[tuple[int, str]]:
    """Tách tin thành [(số dòng, nội dung)], đánh số từ 1. Mọi trích dẫn dùng số này."""
    return list(enumerate(text.strip().splitlines(), start=1))


def dong_co_so(text: str) -> str:
    """Bản tin có tiền tố 'Lk: ' để đưa vào prompt."""
    return "\n".join(f"L{i}: {ln}" for i, ln in danh_so_dong(text))


# ── mock ─────────────────────────────────────────────────────────────────────
def _nam_cho_phep(line: str):
    if RE_MOI_NAM.search(line):
        return "moi_nam"
    if not re.search(r"năm", line, re.I):
        return None
    nam = set()
    for m in RE_NAM_RANGE.finditer(line):
        nam.update(range(int(m.group(1)), int(m.group(2)) + 1))
    for m in RE_NAM_LIST.finditer(line):
        nam.update(int(d) for d in re.findall(r"[1-6]", m.group(1)))
    for m in RE_NAM_ONE.finditer(line):
        nam.add(int(m.group(1)))
    if not nam:
        return None
    return set(range(min(nam), 7)) if RE_TRO_LEN.search(line) else nam


def _han_nop(dongs):
    for i, ln in dongs:
        if RE_HAN.search(ln):
            m = RE_NGAY.search(ln)
            if m:
                d, mo, y = m.group(1), m.group(2), m.group(3)
                if y:
                    y = int(y) + 2000 if len(y) == 2 else int(y)
                    return {"raw": ln.strip(), "evidence_line": i,
                            "parsed": f"{y:04d}-{int(mo):02d}-{int(d):02d}", "ambiguous": False}
                # thiếu năm → KHÔNG tự suy ra (luật ④)
                return {"raw": ln.strip(), "evidence_line": i, "parsed": None, "ambiguous": True}
            return {"raw": ln.strip(), "evidence_line": i, "parsed": None, "ambiguous": True}
    return {"raw": None, "evidence_line": None, "parsed": None, "ambiguous": True}


def _verdict_mock(tin_text: str, profile: dict, cau_hoi_them=None) -> dict:
    dongs = danh_so_dong(tin_text)
    co_chu = [(i, ln) for i, ln in dongs if ln.strip()]
    yc = [(i, ln) for i, ln in co_chu if RE_DONG_YEUCAU.search(ln)]

    matched, gaps, hard_fail, canh_bao, next_3 = [], [], [], [], []
    cau_hoi = None

    # ④ dấu hiệu bất thường
    for i, ln in co_chu:
        if RE_PHI.search(ln):
            canh_bao.append(f"L{i}: tin đòi đóng phí trước khi phỏng vấn — "
                            f"cơ hội thật gần như không thu phí ứng viên.")
        elif RE_BAT_THUONG.search(ln):
            canh_bao.append(f"L{i}: dấu hiệu gây áp lực gấp / liên hệ ngoài kênh chính thức.")
    co_phi = any("đòi đóng phí" in c for c in canh_bao)

    deadline = _han_nop(dongs)
    ky_nang_ho_so = {_khong_dau(k) for k in (profile.get("ky_nang") or [])}

    for i, ln in yc:
        uu_tien = bool(RE_UU_TIEN.search(ln))
        bat_buoc = bool(RE_BAT_BUOC.search(ln)) and not uu_tien
        req = ln.strip()

        # dòng tiêu đề trống ("Yêu cầu:") — không có gì để đối chiếu
        if RE_DONG_TIEUDE.match(ln):
            continue
        # tin ghi rõ "Không yêu cầu ..." → điều kiện được nới, KHÔNG phải gap
        if RE_KHONG_YEUCAU.match(ln.strip()):
            matched.append({"requirement": req, "evidence_line": i,
                            "from_profile": "tin ghi rõ không yêu cầu mục này"})
            continue
        # giấy tờ cần chuẩn bị → sang "việc cần làm", không phải gap
        for d in RE_DOC.findall(ln):
            next_3.append(f"Chuẩn bị {d.strip()} (L{i})")
        if RE_DONG_HOSO.match(ln):      # dòng chỉ liệt kê hồ sơ thì hết việc ở đây
            continue

        xet = False  # dòng này đã đối chiếu được chưa

        nam_ok = _nam_cho_phep(ln)
        if nam_ok is not None:
            xet = True
            if nam_ok == "moi_nam":
                matched.append({"requirement": req, "evidence_line": i,
                                "from_profile": "tin nhận mọi năm học — năm học không phải rào cản"})
            elif profile.get("nam_hoc") is None:
                cau_hoi = cau_hoi or "Bạn đang học năm mấy?"
            elif profile["nam_hoc"] in nam_ok:
                matched.append({"requirement": req, "evidence_line": i,
                                "from_profile": f"năm {profile['nam_hoc']}"})
            else:
                (hard_fail if bat_buoc else gaps).append(
                    {"rule": req, "evidence_line": i} if bat_buoc else
                    {"requirement": req, "evidence_line": i,
                     "why": f"hồ sơ khai năm {profile['nam_hoc']}"})

        m_gpa = RE_GPA.search(ln)
        if m_gpa:
            xet = True
            nguong = float(m_gpa.group(1).replace(",", "."))
            if profile.get("gpa") is None:
                cau_hoi = cau_hoi or "GPA hiện tại của bạn là bao nhiêu (thang 4)?"
            elif profile["gpa"] >= nguong:
                matched.append({"requirement": req, "evidence_line": i,
                                "from_profile": f"GPA {profile['gpa']}"})
            elif bat_buoc:
                hard_fail.append({"rule": req, "evidence_line": i})
            else:
                gaps.append({"requirement": req, "evidence_line": i,
                             "why": f"hồ sơ khai GPA {profile['gpa']} < {nguong}"})

        if RE_ONSITE.search(ln):
            city = RE_CITY.search(ln)
            if city:
                xet = True
                if _khong_dau(city.group(1)) in _khong_dau(profile.get("thanh_pho", "")):
                    matched.append({"requirement": req, "evidence_line": i,
                                    "from_profile": profile.get("thanh_pho", "")})
                else:
                    (hard_fail if bat_buoc else gaps).append(
                        {"rule": req, "evidence_line": i} if bat_buoc else
                        {"requirement": req, "evidence_line": i,
                         "why": f"hồ sơ khai ở {profile.get('thanh_pho')}"})

        for tu, nhan in KY_NANG_TU.items():
            if tu.strip() in _khong_dau(ln):
                xet = True
                if any(tu.strip() in k for k in ky_nang_ho_so):
                    matched.append({"requirement": req, "evidence_line": i,
                                    "from_profile": f"hồ sơ có {nhan}"})
                else:
                    gaps.append({"requirement": req, "evidence_line": i,
                                 "why": f"hồ sơ chưa khai {nhan}"})
                break

        if "paper" in _khong_dau(ln):
            xet = True
            if not profile.get("publish_paper"):
                gaps.append({"requirement": req, "evidence_line": i,
                             "why": "hồ sơ chưa có paper — đây là mục 'ưu tiên', không phải bắt buộc"
                             if uu_tien else "hồ sơ chưa có paper"})

        if not xet and not uu_tien:
            gaps.append({"requirement": req, "evidence_line": i,
                         "why": "chưa đối chiếu tự động được — bạn tự kiểm dòng này"})

    # ① những gì tin KHÔNG nêu — chống bịa, không được biến thành gap
    toan_van = " ".join(ln for _, ln in co_chu)
    not_stated = []
    if not any(_nam_cho_phep(ln) is not None for _, ln in yc):
        not_stated.append("tin không nêu yêu cầu năm học")
    if not RE_GPA.search(toan_van):
        not_stated.append("tin không nêu yêu cầu GPA")
    if not RE_NGANH.search(toan_van):
        not_stated.append("tin không nêu yêu cầu ngành")
    if deadline["raw"] is None:
        not_stated.append("tin không nêu hạn nộp")
    if not (RE_ONSITE.search(toan_van) or RE_ONLINE.search(toan_van)):
        not_stated.append("tin không nêu hình thức làm việc")

    if deadline["parsed"]:
        next_3.insert(0, f"Nộp trước {deadline['parsed']}")
    elif deadline["raw"]:
        next_3.insert(0, f"Hỏi lại nơi đăng về hạn nộp — tin ghi \"{deadline['raw']}\", "
                         f"không rõ năm (L{deadline['evidence_line']})")
    next_3 = list(dict.fromkeys(next_3))[:3]

    # ── cây quyết định ────────────────────────────────────────────────────────
    if len(co_chu) < 4 or not yc:
        kq = {"verdict": "thieu_thong_tin", "thieu_o_dau": "tin",
              "one_question": "Tin này chưa đủ để đối chiếu. Bạn dán giúp mình bản đầy đủ "
                              "(phần yêu cầu/đối tượng và hạn nộp) được không?"}
        matched, gaps, hard_fail = [], [], []
    elif cau_hoi:
        # G10 — hỏi thì chỉ hỏi. Không vừa hỏi vừa phán, vì user sẽ đọc phán quyết
        # nửa vời đó như kết luận rồi bỏ qua câu hỏi.
        kq = {"verdict": "thieu_thong_tin", "thieu_o_dau": "ho_so", "one_question": cau_hoi}
        matched, gaps, hard_fail = [], [], []
    elif co_phi:
        # tuyệt đối không nen_apply khi tin đòi phí
        kq = {"verdict": "rui_ro_cao", "thieu_o_dau": None, "one_question": None}
    elif hard_fail:
        kq = {"verdict": "rui_ro_cao", "thieu_o_dau": None, "one_question": None}
    else:
        kq = {"verdict": "nen_apply", "thieu_o_dau": None, "one_question": None}

    refusal = None
    for pat, loi in NGOAI_PHAM_VI:
        if cau_hoi_them and pat.search(cau_hoi_them):
            refusal = loi
            break

    kq.update({"matched": matched, "gaps": gaps, "hard_fail": hard_fail,
               "not_stated": not_stated, "deadline": deadline, "next_3": next_3,
               "canh_bao": canh_bao, "refusal": refusal,
               "_mode": "mock", "_model": None})
    return kq


# ── real (AI thật) ───────────────────────────────────────────────────────────
def _chuan_hoa(o: dict) -> dict:
    """Ép output của LLM về đúng schema — thiếu key thì điền mặc định, sai kiểu thì bỏ."""
    def ds(v):
        return v if isinstance(v, list) else []
    dl = o.get("deadline") if isinstance(o.get("deadline"), dict) else {}
    v = o.get("verdict")
    return {
        "verdict": v if v in ("nen_apply", "rui_ro_cao", "thieu_thong_tin") else "thieu_thong_tin",
        "thieu_o_dau": o.get("thieu_o_dau") if o.get("thieu_o_dau") in ("tin", "ho_so") else None,
        "matched": ds(o.get("matched")), "gaps": ds(o.get("gaps")),
        "hard_fail": ds(o.get("hard_fail")), "not_stated": ds(o.get("not_stated")),
        "one_question": o.get("one_question") or None,
        "deadline": {"raw": dl.get("raw"), "evidence_line": dl.get("evidence_line"),
                     "parsed": dl.get("parsed"), "ambiguous": bool(dl.get("ambiguous", True))},
        "next_3": ds(o.get("next_3"))[:3], "canh_bao": ds(o.get("canh_bao")),
        "refusal": o.get("refusal") or None,
    }


def _goi_llm(tin_text: str, profile: dict, cau_hoi_them=None) -> dict:
    from . import prompt as P
    return _chuan_hoa(llm.json_call(
        P.SYSTEM, P.build(dong_co_so(tin_text), profile, cau_hoi_them), nhan="verdict"))


# ── hàm công khai ────────────────────────────────────────────────────────────
def verdict(tin_text: str, profile: dict, mode: str = "mock",
            cau_hoi_them: str | None = None) -> dict:
    """Đối chiếu MỘT tin với MỘT hồ sơ. Trả về schema trong ke-hoach.md §3.

    mode="mock": luật if/else, không gọi AI.
    mode="real": gọi LLM thật ở quyết định trung tâm.
    """
    t0 = time.time()
    if mode == "real":
        kq = _goi_llm(tin_text, profile, cau_hoi_them)
        kq["_mode"], kq["_model"] = "real", llm.model()
    else:
        kq = _verdict_mock(tin_text, profile, cau_hoi_them)

    # checker chạy ở CẢ HAI chế độ — grounding không bao giờ được tin lời model
    from .checker import kiem_tra
    kq["_grounding"] = kiem_tra(kq, tin_text)

    # HẠ HẠNG những "đã khớp" mà hồ sơ không thể chứng minh (xem NGOAI_TAM_HO_SO
    # trong checker.py). Checker chỉ BÁO CÁO; nếu không ai hành động theo báo cáo
    # thì học viên vẫn đọc thấy "Ngành: phù hợp với yêu cầu" trên một tin đòi bằng
    # tiến sĩ. Chuyển sang `gaps` — vẫn không phải hard_fail, vẫn không kết luận
    # "không đủ điều kiện" (luật 4), chỉ nói thẳng là mình không biết.
    qua_tam = kq["_grounding"].get("qua_tam_ho_so") or []
    if qua_tam:
        khoa = {(q["requirement"], q["evidence_line"]) for q in qua_tam}
        kq["matched"] = [m for m in kq["matched"]
                         if (m.get("requirement"), m.get("evidence_line")) not in khoa]
        for q in qua_tam:
            kq["gaps"].append({
                "requirement": q["requirement"], "evidence_line": q["evidence_line"],
                "why": f"Hồ sơ không khai được {q['loai']} — hệ thống không có căn cứ để "
                       f"nói bạn đạt hay chưa. Bạn tự kiểm điều này trước khi nộp.",
            })
        # Đang nói "đã khớp" mà hoá ra không có căn cứ thì kết luận cũ không còn
        # đứng được: hạ nen_apply xuống thieu_thong_tin.
        if kq["verdict"] == "nen_apply":
            kq["verdict"] = "thieu_thong_tin"
        kq.setdefault("canh_bao", []).append(
            "Tin này có yêu cầu nằm ngoài thứ hồ sơ khai được ("
            + ", ".join(sorted({q["loai"] for q in qua_tam})) + ") — mình không kết luận thay bạn.")

    kq["_ms"] = int((time.time() - t0) * 1000)
    return kq


def tai_data() -> tuple[list, list]:
    tin = json.loads((CODEBASE / "data" / "postings.json").read_text(encoding="utf-8"))
    ho_so = json.loads((CODEBASE / "data" / "profiles.json").read_text(encoding="utf-8"))
    return tin["postings"], ho_so["profiles"]
