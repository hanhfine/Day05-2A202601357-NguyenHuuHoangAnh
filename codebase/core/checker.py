"""Checker trích dẫn — chiều chất lượng "grounding" do MÁY chấm, không phải cảm tính.

Đây là lý do nhóm chọn lát cắt này (spec §7): người ngoài nhóm chạy lại file này ra
đúng cùng một kết quả. Rubric R4 đòi "định nghĩa kiểm chứng được" — đây là nó.

Luật: mỗi khẳng định có `evidence_line` = k thì
  (a) k phải tồn tại trong tin, và
  (b) nội dung khẳng định phải thật sự nằm ở dòng k — đo bằng tỉ lệ từ nội dung
      của khẳng định xuất hiện trong dòng đó, ngưỡng NGUONG_TRUNG.
Model được phép diễn đạt lại (nên không đòi khớp chuỗi tuyệt đối), nhưng không được
trích một dòng chẳng liên quan.
"""
import re
import unicodedata

NGUONG_TRUNG = 0.6  # ≥60% từ nội dung của khẳng định phải có trong dòng được trích

# từ chức năng — bỏ khi so, vì chúng có mặt ở mọi dòng
TU_DUNG = {
    "và", "hoặc", "của", "là", "có", "không", "cho", "với", "các", "những", "được",
    "phải", "từ", "đến", "trên", "trong", "tại", "về", "một", "này", "đó", "thì",
    "bạn", "mình", "tin", "yêu", "cầu", "sinh", "viên", "ứng", "nêu",
}


def _chuan(s: str) -> str:
    """Bỏ dấu, hạ chữ thường — để 'GPA tối thiểu' khớp được 'gpa toi thieu'."""
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9\s./]", " ", s)


def _tu_noi_dung(s: str) -> list[str]:
    return [t for t in _chuan(s).split() if len(t) > 1 and t not in {_chuan(x) for x in TU_DUNG}]


# ── chiều thứ hai: vế HỒ SƠ của khẳng định ───────────────────────────────────
#
# Checker gốc chỉ soát vế TIN: "câu này có nằm ở dòng L15 không". Nó không bao giờ
# đụng tới `from_profile` — vế nói VÌ SAO học viên đáp ứng. Nên lỗi này lọt sạch:
#
#   requirement : "Currently enrolled in a PhD program in Computer Science…"  (L15)
#   from_profile: "nam_hoc: 3"
#   → matched, và grounding chấm 7/7 vì câu trích ĐÚNG là ở L15.
#
# Sinh viên năm 3 đại học được lấy làm bằng chứng đang học tiến sĩ. Cùng lỗi đó:
# "1+ years of experience" khớp bằng `ky_nang: [Python, C++]` — biết Python không
# phải là có một năm kinh nghiệm.
#
# Hồ sơ chỉ có 8 field (ten · nam_hoc · nganh · gpa · thanh_pho · ky_nang ·
# project · co_github). Mấy yêu cầu dưới đây KHÔNG field nào khai được, nên hệ
# thống không thể biết học viên đạt hay không — chỗ đúng của chúng là `gaps`
# ("hồ sơ không nêu"), không phải `matched` ("đã đáp ứng").
#
# Đây KHÔNG phải hard_fail và không mâu thuẫn luật 4: hạ xuống `gaps` là nói
# "mình không biết, bạn tự kiểm", không phải "bạn không đủ điều kiện". Tin vẫn
# hiện, học viên vẫn nộp được. Bịa một cái khớp mới là chặn họ theo kiểu tệ hơn —
# họ tin là đủ rồi thôi không kiểm nữa.
NGOAI_TAM_HO_SO = [
    (r"\bph\.?d\.?\b|tien si|doctoral|doctorate", "bậc tiến sĩ"),
    (r"thac si|master s (degree|program)|\bmsc\b", "bậc thạc sĩ"),
    (r"(published|publication|bai bao)[^.]{0,40}(conference|journal|hoi nghi|tap chi)"
     r"|(conference|journal|hoi nghi)[^.]{0,40}(paper|publication|bai bao)", "bài báo đã công bố"),
    (r"\d+\s*\+?\s*(nam|year)s?\b[^.]{0,30}(experience|kinh nghiem)", "số năm kinh nghiệm"),
    (r"expected graduation|du kien tot nghiep|graduation (date|in)\b", "thời điểm tốt nghiệp"),
]


def ngoai_tam_ho_so(requirement: str) -> str | None:
    """Yêu cầu này có nằm ngoài thứ 8 field hồ sơ khai được không → tên loại, hoặc None."""
    r = _chuan(requirement)
    for pat, ten in NGOAI_TAM_HO_SO:
        if re.search(pat, r):
            return ten
    return None


def kiem_tra(ket_qua: dict, tin_text: str) -> dict:
    """Trả về báo cáo grounding cho một output của verdict()."""
    dongs = {i: ln for i, ln in enumerate(tin_text.strip().splitlines(), start=1)}
    n = len(dongs)
    chi_tiet = []

    def soat(nhan: str, noi_dung: str, k):
        if k is None:
            chi_tiet.append({"nhan": nhan, "trich": None, "dat": False,
                             "vi_sao": "khẳng định không có evidence_line"})
            return
        if not isinstance(k, int) or k < 1 or k > n:
            chi_tiet.append({"nhan": nhan, "trich": k, "dat": False,
                             "vi_sao": f"số dòng ngoài khoảng 1..{n}"})
            return
        tu = _tu_noi_dung(noi_dung)
        if not tu:
            chi_tiet.append({"nhan": nhan, "trich": k, "dat": True,
                             "vi_sao": "không có từ nội dung để đối chiếu"})
            return
        dong_chuan = _chuan(dongs[k])
        trung = sum(1 for t in tu if t in dong_chuan)
        ti_le = trung / len(tu)
        chi_tiet.append({
            "nhan": nhan, "trich": k, "dat": ti_le >= NGUONG_TRUNG,
            "ti_le": round(ti_le, 2),
            "vi_sao": "" if ti_le >= NGUONG_TRUNG else f"chỉ {trung}/{len(tu)} từ có ở dòng L{k}",
        })

    # Vế TIN của mọi khẳng định.
    for m in ket_qua.get("matched") or []:
        soat("matched", m.get("requirement", ""), m.get("evidence_line"))
    for g in ket_qua.get("gaps") or []:
        soat("gap", g.get("requirement", ""), g.get("evidence_line"))
    for h in ket_qua.get("hard_fail") or []:
        soat("hard_fail", h.get("rule", ""), h.get("evidence_line"))

    dl = ket_qua.get("deadline") or {}
    if dl.get("raw"):
        soat("deadline", dl["raw"], dl.get("evidence_line"))

    # Vế HỒ SƠ, chỉ áp cho `matched`: khẳng định "học viên ĐÃ đáp ứng" mà điều
    # phải đáp ứng lại nằm ngoài thứ hồ sơ khai được thì không có căn cứ nào cả.
    # `gaps` không cần soát — nó vốn đã là "chưa rõ / chưa đạt".
    qua_tam = []
    for m in ket_qua.get("matched") or []:
        loai = ngoai_tam_ho_so(m.get("requirement", ""))
        if loai:
            qua_tam.append({"requirement": m.get("requirement", ""),
                            "evidence_line": m.get("evidence_line"),
                            "from_profile": m.get("from_profile"),
                            "loai": loai})

    tong = len(chi_tiet)
    dat = sum(1 for c in chi_tiet if c["dat"])
    return {
        "so_khang_dinh": tong,
        "so_dat": dat,
        # grounding_pass giờ đòi CẢ HAI vế: trích đúng dòng của tin, VÀ không
        # khẳng định đã đáp ứng một điều hồ sơ không khai nổi.
        "grounding_pass": tong == dat and not qua_tam,
        "deadline_co_trich": bool(dl.get("evidence_line")) if dl.get("raw") else None,
        "chi_tiet": chi_tiet,
        "qua_tam_ho_so": qua_tam,
    }
