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

    for m in ket_qua.get("matched") or []:
        soat("matched", m.get("requirement", ""), m.get("evidence_line"))
    for g in ket_qua.get("gaps") or []:
        soat("gap", g.get("requirement", ""), g.get("evidence_line"))
    for h in ket_qua.get("hard_fail") or []:
        soat("hard_fail", h.get("rule", ""), h.get("evidence_line"))

    dl = ket_qua.get("deadline") or {}
    if dl.get("raw"):
        soat("deadline", dl["raw"], dl.get("evidence_line"))

    tong = len(chi_tiet)
    dat = sum(1 for c in chi_tiet if c["dat"])
    return {
        "so_khang_dinh": tong,
        "so_dat": dat,
        "grounding_pass": tong == dat,          # pass/fail cho bảng eval
        "deadline_co_trich": bool(dl.get("evidence_line")) if dl.get("raw") else None,
        "chi_tiet": chi_tiet,
    }
