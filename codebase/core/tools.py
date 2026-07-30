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
import re
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


# ── khớp từ khoá ─────────────────────────────────────────────────────────────
#
# Khớp theo RANH GIỚI TỪ, không phải substring. Bản cũ dùng `k in van` nên gõ "AI"
# (bỏ dấu thành "ai") là trúng "t[ai] Việt Nam", "tr[ai] nghiệm", "b[ai] đăng" —
# tiếng Việt đầy từ chứa "ai", nên tin tuyển nhân sự cũng leo lên đầu bảng khi tìm
# "thực tập AI". Từ khoá càng ngắn càng loạn.

DONG_NGHIA = {
    "ai": ["ai", "tri tue nhan tao", "artificial intelligence", "machine learning",
           "hoc may", "deep learning", "hoc sau"],
    "ml": ["ml", "machine learning", "hoc may"],
    "nlp": ["nlp", "xu ly ngon ngu tu nhien", "natural language", "ngon ngu tu nhien"],
    "data": ["data", "du lieu", "phan tich du lieu", "analytics", "analyst"],
    "cv": ["computer vision", "thi giac may tinh", "opencv", "xu ly anh"],
    "mlops": ["mlops", "devops", "ci/cd", "kubernetes", "docker"],
}

# Từ đệm tiếng Việt — tách ra từ kỹ năng kiểu "Docker cơ bản" thì "co", "ban" khớp
# lung tung, phải bỏ. Chỉ dùng cho việc tách kỹ năng thành mảnh nhỏ để dò.
_DEM = {"co", "ban", "va", "cac", "cho", "tu", "voi", "tren", "duoc", "biet", "hieu",
        "kien", "thuc", "nang", "kha", "tot", "gioi", "the", "and", "the", "api"}


def _khop_tu(tu: str, van: str) -> bool:
    """Có `tu` đứng thành từ riêng trong `van` không (cả hai đã bỏ dấu, lowercase)."""
    if not tu:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(tu)}(?![a-z0-9])", van) is not None


def _bien_the(ky_nang: str) -> list[str]:
    """Kỹ năng trong CV → các chuỗi đáng dò.

    'LLM API (OpenAI, Gemini)' → ['llm api', 'llm', 'openai', 'gemini']
    Phần trong ngoặc KHÔNG bị vứt: 'OpenAI', 'Gemini' là tên công nghệ thật, tin nào
    nhắc tới thì đó là khớp mạnh. Nhưng cụm đầy đủ chỉ lấy phần trước ngoặc, vì
    'llm api openai gemini' thì chẳng tin nào viết y hệt.
    """
    s = _kd(ky_nang)
    sach = re.sub(r"[^a-z0-9+#. ]", " ", s)
    truoc = re.sub(r"[^a-z0-9+#. ]", " ", s.split("(")[0]).strip()
    manh = [p for p in sach.split() if len(p) >= 2 and p not in _DEM]
    cum = [truoc] if truoc and truoc not in _DEM and " " in truoc else []
    return list(dict.fromkeys(cum + manh))


TRAN_TIN = 25          # trần cứng số tin trả về một lượt
MAC_DINH_TIN = 8


def xep_hang(tu_khoa: str | None = None, thanh_pho: str | None = None,
             loai: str | None = None, nam_hoc: int | None = None,
             gom_fixture: bool = False, profile: dict | None = None) -> list[dict]:
    """Toàn bộ tin khớp, đã xếp hạng, CHƯA cắt bớt. `tim_tin` mới là bản cắt."""
    kq = []
    tk = [t for t in _kd(tu_khoa or "").split() if len(t) > 1]
    ho_so = profile or {}
    ky_nang_hs = [k for k in (ho_so.get("ky_nang") or []) if str(k).strip()]
    nganh_hs = _kd(str(ho_so.get("nganh") or ""))
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

        # điểm từ khoá người dùng gõ — tính riêng vì CHỈ nó được quyền loại tin
        diem_tk = sum(2 for k in tk
                      if any(_khop_tu(b, van) for b in DONG_NGHIA.get(k, [k])))
        if tk and diem_tk == 0:
            continue

        # điểm từ hồ sơ — CHỈ xếp hạng, KHÔNG BAO GIỜ loại tin. Hồ sơ không khớp
        # kỹ năng nào thì tin tụt xuống dưới, chứ không được biến mất: học viên
        # phải còn thấy nó để tự quyết, y như luật không lọc theo năm học/GPA.
        khop_kn = [k for k in ky_nang_hs
                   if any(_khop_tu(b, van) for b in _bien_the(k))]
        diem = diem_tk + 2 * len(khop_kn)
        khop_nganh = bool(nganh_hs) and _khop_tu(nganh_hs, van)
        if khop_nganh:
            diem += 2

        # ghi chú khớp — KHÔNG dùng để loại tin
        if nam_hoc is None or m["nam"] is None:
            ghi = "tin không nêu năm học" if m["nam"] is None else "chưa biết năm học của bạn"
        elif m["nam"] == "mọi năm":
            ghi, diem = "tin nhận mọi năm học", diem + 1
        elif nam_hoc in m["nam"]:
            ghi, diem = "năm học khớp", diem + 1
        else:
            ghi = f"tin ghi năm {'-'.join(map(str, m['nam']))} — vẫn nên xem"

        # Nói ra tin này được gợi ý NHỜ CÁI GÌ. Xếp hạng im lặng thì học viên không
        # có cách nào biết thứ tự này từ đâu ra, cũng không cãi lại được.
        if khop_kn:
            ghi = f"khớp {', '.join(khop_kn[:4])} · {ghi}"
        if khop_nganh:
            ghi = f"khớp ngành · {ghi}"
        # url/url_loai đã được crawler bấm thử; link chết ở đó đã bị xoá thành "".
        # link_xac_minh=False nghĩa là trang chặn bot nên máy không tự vào kiểm được —
        # link vẫn giữ, nhưng phải nói rõ chứ không được im lặng cho qua.
        kq.append({"opp_id": t["id"], "title": t["title"], "loai": t["kind"],
                   "thanh_pho": m["thanh_pho"], "gpa_yeu_cau": m["gpa_min"],
                   "han_nop": (m["han_nop"]["parsed"] or m["han_nop"]["raw"]),
                   "ghi_chu": ghi, "url": t.get("url") or "",
                   "url_loai": t.get("url_loai") or "",
                   "link_xac_minh": str(t.get("_url_status", "")).startswith("ok"),
                   "khop_ky_nang": khop_kn, "khop_nganh": khop_nganh,
                   "_diem": diem})
    kq.sort(key=lambda x: -x["_diem"])
    for x in kq:
        x.pop("_diem")
    return kq


def tim_tin(tu_khoa: str | None = None, thanh_pho: str | None = None,
            loai: str | None = None, nam_hoc: int | None = None,
            gioi_han: int = MAC_DINH_TIN, gom_fixture: bool = False,
            profile: dict | None = None) -> list[dict]:
    """Tìm tin trong corpus local. Không gọi mạng, không crawl.

    MẶC ĐỊNH BỎ TIN FIXTURE. Corpus trộn hai lớp: OPP-* là tin bịa để smoke_test/eval
    bắn vào các chỗ khó, REAL-* là tin thật crawl về. Trước đây tìm gộp cả hai nên
    40 tin fixture lấn hết 10 tin thật — học viên thấy toàn tin của "Sao Mai Tech",
    "Đại Tín" (tên bịa), bấm vào không có link, và không có gì báo đó là tin giả.
    Gửi họ đi ứng tuyển một tin không tồn tại là lỗi nặng hơn cả bịa yêu cầu.

    `gom_fixture` chỉ dành cho smoke_test/eval — KHÔNG khai trong schema tool nên
    model không bao giờ bật được nó. `profile` do dispatch bơm vào, model không tự
    truyền được: hồ sơ chỉ dùng để XẾP HẠNG, không bao giờ dùng để loại tin.
    """
    return xep_hang(tu_khoa, thanh_pho, loai, nam_hoc, gom_fixture,
                    profile)[:max(1, min(gioi_han, TRAN_TIN))]


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
                       "Hệ thống TỰ xếp hạng theo hồ sơ học viên (kỹ năng, ngành, năm học) — "
                       "bạn không cần và không thể truyền hồ sơ vào. "
                       "Trả về `con_chua_hien` = số tin khớp còn lại chưa hiện: nếu > 0 phải "
                       "nói cho học viên biết còn bao nhiêu tin nữa. "
                       "Trả danh sách rút gọn — KHÔNG được dùng kết quả này để nói về "
                       "yêu cầu của một tin cụ thể, muốn vậy phải gọi doi_chieu.",
        "parameters": {"type": "object", "properties": {
            "tu_khoa": {"type": "string",
                        "description": "Chủ đề học viên muốn, vd 'AI', 'data', 'NLP'. "
                                       "Bỏ trống nếu họ chỉ nói 'tìm tin hợp với em' — "
                                       "khi đó hệ thống xếp hạng thuần theo hồ sơ."},
            "thanh_pho": {"type": "string", "description": "Hà Nội / TP.HCM / Đà Nẵng / online"},
            "loai": {"type": "string", "enum": ["thuc_tap", "hoc_bong"]},
            "nam_hoc": {"type": "integer", "description": "năm học của học viên, nếu đã biết"},
            "gioi_han": {"type": "integer",
                         "description": f"số tin trả về, mặc định {MAC_DINH_TIN}, "
                                        f"tối đa {TRAN_TIN}"}}}}},
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
        a = {k: v for k, v in args.items()
             if k in ("tu_khoa", "thanh_pho", "loai", "nam_hoc")}
        # Model hay quên truyền nam_hoc dù hồ sơ đã khai. Thiếu nó thì mọi tin bị ghi
        # "chưa biết năm học của bạn" — nói sai với học viên vừa khai xong năm học.
        # Lấy thẳng từ hồ sơ; vẫn chỉ dùng để ghi chú + xếp hạng, không loại tin.
        if not isinstance(a.get("nam_hoc"), int) and isinstance((profile or {}).get("nam_hoc"), int):
            a["nam_hoc"] = profile["nam_hoc"]
        gh = args.get("gioi_han")
        gh = MAC_DINH_TIN if not isinstance(gh, int) else max(1, min(gh, TRAN_TIN))
        # Hồ sơ do server bơm vào, model KHÔNG tự truyền được — nó chỉ đổi thứ tự,
        # không đổi tập tin trả về.
        tat_ca = xep_hang(**a, profile=profile)
        ds = tat_ca[:gh]
        con = len(tat_ca) - len(ds)
        # Nói thẳng còn bao nhiêu tin bị cắt. Im lặng cắt bớt là âm thầm giấu cơ hội —
        # học viên không có cách nào biết mình chưa xem hết.
        kq_model = {"so_tin_hien": len(ds), "tong_so_tin_khop": len(tat_ca),
                    "con_chua_hien": con, "danh_sach": ds}
        if con:
            kq_model["nhac"] = (f"Còn {con} tin khớp nữa chưa hiện. Nói rõ cho học viên "
                                f"biết và mời họ xin xem thêm nếu muốn.")
        return kq_model, {"loai": "tim_tin", "data": ds, "con_chua_hien": con,
                          "tong": len(tat_ca)}
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
