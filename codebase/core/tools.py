"""Hai tool cho chat agent: `tim_tin` và `doi_chieu`.

HAI QUYẾT ĐỊNH THIẾT KẾ CẦN GIẢI THÍCH ĐƯỢC (CP5 sẽ hỏi):

1. KHÔNG có tool "đọc thô nội dung tin". Nghe vô lý, nhưng nếu cho model đọc thô một
   tin rồi tự kể lại yêu cầu, nó sẽ diễn giải mà không trích dẫn — đúng lỗi ① mình
   phải chống. Muốn nói BẤT CỨ điều gì về một tin, model buộc phải đi qua `doi_chieu`,
   nơi có checker máy soát từng trích dẫn.

2. `tim_tin` KHÔNG loại tin theo điều kiện (năm học, GPA). Nó chỉ xếp hạng và ghi
   chú "khớp/chưa khớp". Lý do y như lý do chọn augment: nếu regex của mình sai và
   search âm thầm bỏ mất một tin học viên thật ra đủ điều kiện, họ mất hẳn cơ hội và
   không có cách nào biết. Chỉ lọc theo cái user nói rõ (từ khoá, thành phố, loại).
"""
import json
import unicodedata
from pathlib import Path

from .verdict import (RE_CITY, RE_GPA, RE_ONLINE, _nam_cho_phep, danh_so_dong,
                      _han_nop, verdict)

D = Path(__file__).resolve().parent.parent / "data"


def _kd(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def tai_corpus() -> list[dict]:
    f = D / "corpus.json"
    if not f.exists():                      # chưa chạy gen_corpus.py
        f = D / "postings.json"
    return json.loads(f.read_text(encoding="utf-8"))["postings"]


def meta(raw: str) -> dict:
    """Rút thông tin lọc/xếp hạng từ tin — dùng lại đúng regex của verdict.py."""
    dongs = danh_so_dong(raw)
    nam = None
    for _, ln in dongs:
        n = _nam_cho_phep(ln)
        if n is not None:
            nam = "mọi năm" if n == "moi_nam" else sorted(n)
            break
    g = RE_GPA.search(raw)
    c = RE_CITY.search(raw)
    return {"nam": nam,
            "gpa_min": float(g.group(1).replace(",", ".")) if g else None,
            "thanh_pho": c.group(1) if c else ("online" if RE_ONLINE.search(raw) else None),
            "han_nop": _han_nop(dongs)}


def la_fixture(t: dict) -> bool:
    """Tin OPP-* là fixture kiểm thử do gen_corpus.py sinh — tổ chức bịa, không có link."""
    return str(t.get("id", "")).startswith("OPP-")


def tim_tin(tu_khoa: str | None = None, thanh_pho: str | None = None,
            loai: str | None = None, nam_hoc: int | None = None,
            gioi_han: int = 5, gom_fixture: bool = False) -> list[dict]:
    """Tìm tin trong corpus local. Không gọi mạng, không crawl.

    MẶC ĐỊNH BỎ TIN FIXTURE. Corpus trộn hai lớp: OPP-* là tin bịa để smoke_test/eval
    bắn vào các chỗ khó, REAL-* là tin thật crawl về. Trước đây tìm gộp cả hai nên
    40 tin fixture lấn hết 10 tin thật — học viên thấy toàn tin của "Sao Mai Tech",
    "Đại Tín" (tên bịa), bấm vào không có link, và không có gì báo đó là tin giả.
    Gửi họ đi ứng tuyển một tin không tồn tại là lỗi nặng hơn cả bịa yêu cầu.

    `gom_fixture` chỉ dành cho smoke_test/eval — KHÔNG khai trong schema tool nên
    model không bao giờ bật được nó.
    """
    kq = []
    tk = [t for t in _kd(tu_khoa or "").split() if len(t) > 1]
    for t in tai_corpus():
        if la_fixture(t) and not gom_fixture:
            continue
        m = meta(t["raw_text"])
        if loai and t["kind"] != loai:
            continue
        if thanh_pho:
            muon, co = _kd(thanh_pho), _kd(m["thanh_pho"] or "")
            if muon not in co and not (muon in ("online", "remote") and co == "online"):
                continue
        van = _kd(t["title"] + " " + t["raw_text"])
        diem = sum(2 for k in tk if k in van)
        if tk and diem == 0:
            continue
        # ghi chú khớp — KHÔNG dùng để loại tin
        if nam_hoc is None or m["nam"] is None:
            ghi = "tin không nêu năm học" if m["nam"] is None else "chưa biết năm học của bạn"
        elif m["nam"] == "mọi năm":
            ghi, diem = "tin nhận mọi năm học", diem + 1
        elif nam_hoc in m["nam"]:
            ghi, diem = "năm học khớp", diem + 1
        else:
            ghi = f"tin ghi năm {'-'.join(map(str, m['nam']))} — vẫn nên xem"
        # url/url_loai đã được crawler bấm thử; link chết ở đó đã bị xoá thành "".
        # link_xac_minh=False nghĩa là trang chặn bot nên máy không tự vào kiểm được —
        # link vẫn giữ, nhưng phải nói rõ chứ không được im lặng cho qua.
        kq.append({"opp_id": t["id"], "title": t["title"], "loai": t["kind"],
                   "thanh_pho": m["thanh_pho"], "gpa_yeu_cau": m["gpa_min"],
                   "han_nop": (m["han_nop"]["parsed"] or m["han_nop"]["raw"]),
                   "ghi_chu": ghi, "url": t.get("url") or "",
                   "url_loai": t.get("url_loai") or "",
                   "link_xac_minh": str(t.get("_url_status", "")).startswith("ok"),
                   "_diem": diem})
    kq.sort(key=lambda x: -x["_diem"])
    for x in kq:
        x.pop("_diem")
    return kq[:max(1, min(gioi_han, 8))]


def doi_chieu(opp_id: str, profile: dict, mode: str = "real") -> dict:
    """Quyết định trung tâm. Mọi khẳng định về tin phải đi qua đây."""
    tin = next((t for t in tai_corpus() if t["id"] == opp_id), None)
    if not tin:
        return {"loi": f"Không có tin {opp_id} trong corpus."}
    kq = verdict(tin["raw_text"], profile, mode=mode)
    return {"tin": {"opp_id": tin["id"], "title": tin["title"], "raw_text": tin["raw_text"]},
            "ket_qua": kq}


# ── schema cho OpenAI function calling ───────────────────────────────────────
TOOLS = [
    {"type": "function", "function": {
        "name": "tim_tin",
        "description": "Tìm tin thực tập/học bổng trong thư viện tin của hệ thống. "
                       "Trả danh sách rút gọn — KHÔNG được dùng kết quả này để nói về "
                       "yêu cầu của một tin cụ thể, muốn vậy phải gọi doi_chieu.",
        "parameters": {"type": "object", "properties": {
            "tu_khoa": {"type": "string", "description": "vd 'AI', 'data', 'NLP'"},
            "thanh_pho": {"type": "string", "description": "Hà Nội / TP.HCM / Đà Nẵng / online"},
            "loai": {"type": "string", "enum": ["thuc_tap", "hoc_bong"]},
            "nam_hoc": {"type": "integer", "description": "năm học của học viên, nếu đã biết"},
            "gioi_han": {"type": "integer", "description": "số tin trả về, tối đa 8"}}}}},
    {"type": "function", "function": {
        "name": "doi_chieu",
        "description": "Đối chiếu MỘT tin với hồ sơ học viên. Đây là cách DUY NHẤT để "
                       "biết và nói về yêu cầu, điều kiện, hạn nộp của một tin. Kết quả đã "
                       "được máy soát trích dẫn — trình bày lại đúng nội dung, không thêm bớt.",
        "parameters": {"type": "object", "properties": {
            "opp_id": {"type": "string", "description": "mã tin, vd OPP-001"}},
            "required": ["opp_id"]}}},
]


def dispatch(ten: str, args: dict, profile: dict, mode: str) -> tuple[dict, dict]:
    """Trả (kết quả cho model, event cho UI)."""
    if ten == "tim_tin":
        ds = tim_tin(**{k: v for k, v in args.items() if k in
                        ("tu_khoa", "thanh_pho", "loai", "nam_hoc", "gioi_han")})
        return {"so_tin": len(ds), "danh_sach": ds}, {"loai": "tim_tin", "data": ds}
    if ten == "doi_chieu":
        r = doi_chieu(args.get("opp_id", ""), profile, mode)
        if "loi" in r:
            return r, {"loai": "loi", "data": r["loi"]}
        kq = r["ket_qua"]
        # gửi cho model bản gọn — bỏ field nội bộ để nó không bình luận về chúng
        gon = {k: v for k, v in kq.items() if not k.startswith("_")}
        gon["_trich_dan_dat"] = f"{kq['_grounding']['so_dat']}/{kq['_grounding']['so_khang_dinh']}"
        return gon, {"loai": "doi_chieu", "data": r}
    return {"loi": f"tool lạ: {ten}"}, {"loai": "loi", "data": ten}
