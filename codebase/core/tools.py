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
    """Bỏ dấu tiếng Việt. `đ` phải xử lý riêng: nó là U+0111, KHÔNG phân rã được bằng
    NFD như `à`/`ằ`, nên nếu không thay tay thì `đà nẵng` ra `đa nang` (còn nguyên đ)
    trong khi người dùng gõ `da nang` — hai chuỗi không bao giờ khớp nhau."""
    s = unicodedata.normalize("NFD", (s or "").lower()).replace("đ", "d")
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
    "software": ["software engineer", "software developer", "ky su phan mem",
                 "lap trinh vien", "developer", "frontend", "backend", "fullstack",
                 "full-stack", "full stack", "web developer", "mobile developer",
                 "ios developer", "android developer", "react", "nodejs", "java developer",
                 "net developer", "flutter developer"],
    "phan mem": ["phan mem", "software", "lap trinh", "developer", "backend",
                 "frontend", "fullstack", "ky su phan mem"],
    "lap trinh": ["lap trinh", "developer", "software", "phan mem", "code",
                  "backend", "frontend", "fullstack", "ky su"],
}

# Từ khoá nhận diện lĩnh vực để hỗ trợ loại trừ (linh_vuc_tru).
# Chỉ dùng khi học viên NÓI RÕ "không muốn AI" hay "chỉ phần mềm thuần" — không tự suy.
_LINH_VUC_TERMS: dict[str, list[str]] = {
    "ai": ["machine learning", "deep learning", "llm", "nlp", "computer vision",
           "data scientist", "tri tue nhan tao", "artificial intelligence"],
    "business": ["business analyst", "business development", "ke toan", "nhan su",
                 "marketing", "sale", "kinh doanh", "hr ", "tuyen dung"],
}

# Ngành NẰM NGOÀI thư viện. Corpus chỉ có tin CNTT/dữ liệu/AI — crawler chặn ở
# `_lien_quan_ai`, nên không có tin marketing/kế toán/y nào lọt vào, và sẽ không
# bao giờ có chừng nào chưa thêm nguồn khác.
#
# VÌ SAO PHẢI DÒ RIÊNG, KHÔNG ĐỂ XẾP HẠNG TỰ LO: `xep_hang` không bao giờ loại tin,
# nó chỉ dán `thieu`. Học viên hỏi "thực tập marketing" thì MỌI tin đều nhận
# `thieu=["không nhắc tới marketing"]`, `dat` rỗng, và hệ thống đáp đúng câu dành cho
# trường hợp khác hẳn: "không có tin nào khớp hẳn, dưới đây là tin GẦN ĐÚNG nhất".
# Tin Backend Engineer KHÔNG phải là tin marketing gần đúng — nó là ngành khác. Nói
# "gần đúng" ở đây là để học viên tưởng thư viện có mảng marketing mà họ chưa tìm ra
# từ khoá đúng, rồi ngồi thử lại. Sự thật là thư viện không có, và phải nói ra.
#
# Dò bằng danh sách ngành cụ thể chứ không suy từ "khớp 0 tin": "Rust", "Kubernetes"
# cũng khớp 0 tin nhưng chúng THUỘC phạm vi — thư viện chỉ tình cờ chưa có. Hai
# trường hợp đó phải nói hai câu khác nhau.
_NGOAI_LINH_VUC: dict[str, list[str]] = {
    "marketing / truyền thông": ["marketing", "truyen thong", "content", "seo",
                                 "quang cao", "pr", "social media", "brand"],
    "kinh doanh / bán hàng": ["sale", "sales", "ban hang", "kinh doanh", "telesale",
                              "cham soc khach hang", "customer service"],
    "nhân sự": ["nhan su", "hr", "human resource", "tuyen dung", "recruitment",
                "talent acquisition", "c&b"],
    "kế toán / tài chính": ["ke toan", "accounting", "kiem toan", "audit", "tai chinh",
                            "finance", "thue", "tax", "ngan quy"],
    "thiết kế đồ hoạ": ["thiet ke do hoa", "graphic design", "photoshop", "illustrator",
                        "ui ux designer", "dung phim", "video editor"],
    "y tế": ["y te", "dieu duong", "bac si", "duoc si", "nha khoa", "benh vien"],
    "giáo dục / gia sư": ["gia su", "giao vien", "giang day", "tro giang", "day hoc"],
    "xây dựng / cơ khí": ["xay dung", "kien truc", "co khi", "dien lanh", "cong trinh",
                          "civil engineer", "mechanical"],
    "logistics / xuất nhập khẩu": ["logistics", "xuat nhap khau", "chuoi cung ung",
                                   "supply chain", "kho van", "hai quan"],
    "nhà hàng / khách sạn / du lịch": ["nha hang", "khach san", "du lich", "barista",
                                       "phuc vu", "bep", "tour"],
    "luật": ["luat", "phap che", "legal", "phap ly"],
}


# Tín hiệu THUỘC phạm vi. Có một từ ở đây thì câu hỏi là về IT, chấm hết — kể cả khi
# nó cũng chứa một từ trong `_NGOAI_LINH_VUC`.
#
# CÁI NÀY BẮT BUỘC PHẢI CÓ, không phải cho chắc: "tuyển dụng" nằm trong nhóm nhân sự
# (vì "thực tập tuyển dụng" đúng là việc HR thật), nhưng nó cũng là từ chung của mọi
# câu tìm việc tiếng Việt. Không có quyền phủ quyết này thì "tuyển dụng IT",
# "tuyển dụng lập trình viên", "tuyển dụng backend" đều bị báo là ngành nhân sự ngoài
# phạm vi — chặn đúng nhóm học viên mà hệ thống sinh ra để phục vụ. Tương tự
# "sales engineer phần mềm" (kinh doanh) và "content developer" (marketing).
_TRONG_PHAM_VI = [
    "it", "cntt", "cong nghe thong tin", "phan mem", "software", "lap trinh",
    "developer", "dev", "engineer", "ky su phan mem", "backend", "frontend",
    "fullstack", "full-stack", "full stack", "web", "mobile", "app",
    "ai", "machine learning", "deep learning", "data", "du lieu", "database",
    "nlp", "computer vision", "mlops", "devops", "cloud", "python", "java",
    "javascript", "sql", "react", "nodejs", "golang", "tester", "qa", "qc",
    "khoa hoc may tinh", "khoa hoc du lieu", "tri tue nhan tao", "he thong",
    "mang", "security", "an toan thong tin", "embedded", "nhung",
]


def linh_vuc_ngoai_pham_vi(tu_khoa: str | None) -> str | None:
    """Từ khoá học viên gõ có nêu một ngành thư viện KHÔNG phục vụ không → tên ngành.

    Trả None nếu từ khoá thuộc phạm vi, hoặc không nêu ngành nào rõ ràng.

    Nhắc một từ IT nào đó là đủ để KHÔNG bị coi là ngoài phạm vi — xem `_TRONG_PHAM_VI`.
    Lệch về phía cho qua là cố ý: báo nhầm "không phục vụ ngành này" cho người đang hỏi
    đúng ngành mình phục vụ thì họ đóng tab và không quay lại, còn bỏ sót một câu hỏi
    marketing thì hệ quả tệ nhất là họ thấy danh sách tin IT và tự hiểu.
    """
    if not tu_khoa:
        return None
    van = _kd(tu_khoa)
    if any(_khop_tu(k, van) for k in _TRONG_PHAM_VI):
        return None
    for ten, tu in _NGOAI_LINH_VUC.items():
        if any(_khop_tu(k, van) for k in tu):
            return ten
    return None


# Từ đệm tiếng Việt — tách ra từ kỹ năng kiểu "Docker cơ bản" thì "co", "ban" khớp
# lung tung, phải bỏ. Chỉ dùng cho việc tách kỹ năng thành mảnh nhỏ để dò.
_DEM = {"co", "ban", "va", "cac", "cho", "tu", "voi", "tren", "duoc", "biet", "hieu",
        "kien", "thuc", "nang", "kha", "tot", "gioi", "the", "and", "the", "api"}


# Tên thành phố có nhiều cách viết. Bản cũ so bằng `muon not in co` nên "TP.HCM" không
# khớp "Hồ Chí Minh" — tin AI Engineer Intern ở HCM bị loại sạch dù đúng là tin AI.
_TP_GOC = {
    "hanoi": "hà nội", "hn": "hà nội",
    "hochiminh": "tp.hcm", "tphcm": "tp.hcm", "hcm": "tp.hcm", "saigon": "tp.hcm",
    "sg": "tp.hcm", "thanhphohochiminh": "tp.hcm",
    "danang": "đà nẵng", "dn": "đà nẵng",
    "bacninh": "bắc ninh", "hue": "huế", "thuathienhue": "huế", "cantho": "cần thơ",
    "online": "online", "remote": "online", "tuxa": "online", "workfromhome": "online",
}


def chuan_tp(s: str | None) -> str:
    """'TP.HCM' / 'Hồ Chí Minh' / 'saigon' → cùng một chuỗi. Không nhận ra thì trả nguyên."""
    goc = re.sub(r"[^a-z0-9]", "", _kd(s or ""))
    return _TP_GOC.get(goc, _kd(s or "").strip())


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

# Thang level hệ thống phục vụ. Tin nêu rõ level NGOÀI thang này (senior/middle/lead)
# vẫn được giữ trong corpus nhưng phải bị hạ hạng và dán nhãn — xem xep_hang().
LV_SINH_VIEN = {"intern", "fresher", "junior"}


def xep_hang(tu_khoa: str | None = None, thanh_pho: str | None = None,
             loai: str | None = None, nam_hoc: int | None = None,
             cap_do: str | None = None, linh_vuc_tru: list[str] | None = None,
             gom_fixture: bool = False, profile: dict | None = None) -> list[dict]:
    """Toàn bộ tin, đã xếp hạng, CHƯA cắt bớt. Mỗi tin kèm `thieu` = các điều kiện
    người dùng nêu mà tin KHÔNG đạt.

    KHÔNG LOẠI TIN NÀO. Bản cũ lọc cứng theo thành phố / loại / từ khoá, nên hỏi
    "AI intern" ở một thành phố không có tin là trả về RỖNG — học viên tưởng không
    có cơ hội nào, trong khi corpus đang có tin AI ở thành phố khác. Trả rỗng là dạng
    nặng nhất của việc âm thầm cắt cơ hội.

    Giờ mọi tin đều đi tiếp, sắp theo (số điều kiện thiếu, rồi tới điểm). Tin đạt đủ
    luôn đứng trước; tin gần đúng xếp sau và PHẢI mang nhãn thiếu gì để học viên tự
    quyết, chứ không biến mất.
    """
    kq = []
    tk = [t for t in _kd(tu_khoa or "").split() if len(t) > 1]
    ho_so = profile or {}
    ky_nang_hs = [k for k in (ho_so.get("ky_nang") or []) if str(k).strip()]
    nganh_hs = _kd(str(ho_so.get("nganh") or ""))
    tp_muon = chuan_tp(thanh_pho) if thanh_pho else ""
    for t in tai_corpus():
        if la_fixture(t) and not gom_fixture:
            continue
        m = meta(t["raw_text"])
        van = _kd(t["title"] + " " + t["raw_text"])
        thieu = []

        # RANH GIỚI THẬT CHỈ CÓ MỘT: học bổng vs việc (thực tập/fresher/junior).
        # `thuc_tap` vs `viec_lam` thực chất là khác LEVEL, nên để `cap_do` lo. Ghi
        # thiếu ở cả hai chỗ là phạt tin đa level HAI LẦN cho cùng một chuyện:
        # REAL-014 "AI Engineer (Intern/Fresher level)" sẽ bị đẩy xuống cuối bảng
        # ở CẢ câu "tìm thực tập" lẫn câu "tìm fresher" — đúng hai câu nó khớp nhất.
        cap_do_tin = t.get("cap_do") or []
        if loai == "hoc_bong" and t["kind"] != "hoc_bong":
            thieu.append("học bổng")
        elif t["kind"] == "hoc_bong" and (loai in ("thuc_tap", "viec_lam") or cap_do):
            # `or cap_do`: hỏi level nghĩa là muốn VIỆC LÀM — intern/fresher/junior là
            # thang bậc của việc, học bổng không có thang đó. Thiếu điều kiện này thì
            # học bổng lọt vào hàng ĐẠT ở câu "tìm job fresher" (cap_do rỗng nên luật
            # level dưới đây không bắt được nó).
            thieu.append("việc/thực tập")

        # Level: CHỈ ghi thiếu khi tin NÊU RÕ level khác cái được hỏi. Tin không nêu
        # (`cap_do` rỗng) thì vẫn hiện bình thường — cùng lý do với luật không lọc
        # theo năm học/GPA, im lặng cắt một tin là học viên mất hẳn cơ hội đó.
        lv_muon = cap_do or ("intern" if loai == "thuc_tap" else None)
        if lv_muon and cap_do_tin and lv_muon not in cap_do_tin:
            thieu.append(f"tin cho {'/'.join(cap_do_tin)}, không phải {lv_muon}")
        elif not lv_muon and cap_do_tin and not (set(cap_do_tin) & LV_SINH_VIEN):
            # Tin NÊU RÕ một level ngoài thang hệ thống phục vụ (senior/middle/lead).
            # Phải nói ra ngay cả khi học viên không hỏi level nào: query fresher của
            # Google Jobs trả về cả "Senior AI Engineer", và tin đó im lặng thì trông
            # y như tin khớp hẳn. Vẫn KHÔNG loại — chỉ hạ hạng và dán nhãn.
            thieu.append(f"tin cho {'/'.join(cap_do_tin)}")

        if tp_muon:
            tp_tin = chuan_tp(m["thanh_pho"])
            if tp_tin != tp_muon and not (tp_muon == "online" and tp_tin == "online"):
                thieu.append(f"ở {m['thanh_pho'] or 'nơi tin không nêu'}, không phải {thanh_pho}")

        # điểm từ khoá người dùng gõ
        diem_tk = sum(2 for k in tk
                      if any(_khop_tu(b, van) for b in DONG_NGHIA.get(k, [k])))
        if tk and diem_tk == 0:
            thieu.append(f"không nhắc tới {tu_khoa}")

        # Học viên nói rõ "không AI" / "không business" thì phải đánh dấu lệch ngay.
        # Vẫn không loại hẳn khỏi danh sách — chỉ đẩy xuống và nói rõ vì sao lệch.
        for lv in (linh_vuc_tru or []):
            if any(_khop_tu(term, van) for term in _LINH_VUC_TERMS.get(lv, [])):
                thieu.append(f"thuộc lĩnh vực {lv} mà bạn muốn loại")

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
        # Tin gần đúng phải tự khai chỗ lệch, ngay đầu ghi chú — không được để học viên
        # tưởng nó đạt đủ điều kiện họ hỏi.
        if thieu:
            ghi = f"GẦN ĐÚNG ({'; '.join(thieu)}) · {ghi}"
        # url/url_loai đã được crawler bấm thử; link chết ở đó đã bị xoá thành "".
        # link_xac_minh=False nghĩa là trang chặn bot nên máy không tự vào kiểm được —
        # link vẫn giữ, nhưng phải nói rõ chứ không được im lặng cho qua.
        kq.append({"opp_id": t["id"], "title": t["title"], "loai": t["kind"],
                   "cap_do": cap_do_tin,
                   "thanh_pho": m["thanh_pho"], "gpa_yeu_cau": m["gpa_min"],
                   "han_nop": (m["han_nop"]["parsed"] or m["han_nop"]["raw"]),
                   "ghi_chu": ghi, "url": t.get("url") or "",
                   "url_loai": t.get("url_loai") or "",
                   "link_xac_minh": str(t.get("_url_status", "")).startswith("ok"),
                   "khop_ky_nang": khop_kn, "khop_nganh": khop_nganh,
                   "thieu": thieu, "_diem": diem})
    # Đạt đủ điều kiện lên trước, rồi mới tới tin thiếu ít nhất, trong mỗi nhóm thì
    # điểm cao trước. Nhờ vậy cắt bớt kiểu gì cũng không bao giờ ra danh sách rỗng.
    kq.sort(key=lambda x: (len(x["thieu"]), -x["_diem"]))
    for x in kq:
        x.pop("_diem")
    return kq


def tim_tin(tu_khoa: str | None = None, thanh_pho: str | None = None,
            loai: str | None = None, nam_hoc: int | None = None,
            cap_do: str | None = None, linh_vuc_tru: list[str] | None = None,
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
    return xep_hang(tu_khoa=tu_khoa, thanh_pho=thanh_pho, loai=loai, nam_hoc=nam_hoc,
                    cap_do=cap_do, linh_vuc_tru=linh_vuc_tru,
                    gom_fixture=gom_fixture, profile=profile)[:max(1, min(gioi_han, TRAN_TIN))]


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
        "description": "Tìm tin thực tập / việc làm fresher-junior / học bổng trong "
                       "thư viện tin của hệ thống. "
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
            "loai": {"type": "string", "enum": ["thuc_tap", "hoc_bong", "viec_lam"],
                     "description": "thuc_tap = thực tập · hoc_bong = học bổng · "
                                    "viec_lam = việc làm fresher/junior"},
            "cap_do": {"type": "string", "enum": ["intern", "fresher", "junior"],
                       "description": "level học viên muốn. Bỏ trống nếu họ không nói rõ. "
                                      "Một tin có thể nhận nhiều level cùng lúc."},
            "linh_vuc_tru": {"type": "array",
                              "items": {"type": "string", "enum": ["ai", "business"]},
                              "description": "Lĩnh vực học viên nói rõ là không muốn. Ví dụ ['ai'] khi họ nói 'chỉ phần mềm, không AI'."},
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
            "opp_id": {"type": "string",
                       "description": "mã tin, chép y nguyên field opp_id từ tim_tin "
                                      "(vd 'REAL-001' hoặc 'OPP-001')"}},
            "required": ["opp_id"]}}},
]


def dispatch(ten: str, args: dict, profile: dict, mode: str) -> tuple[dict, dict]:
    """Trả (kết quả cho model, event cho UI)."""
    if ten == "tim_tin":
        a = {k: v for k, v in args.items()
             if k in ("tu_khoa", "thanh_pho", "loai", "nam_hoc", "cap_do")}
        lv_tru = args.get("linh_vuc_tru")
        if isinstance(lv_tru, list):
            lv_tru = [x for x in lv_tru if x in _LINH_VUC_TERMS]
        else:
            lv_tru = None
        # Model hay quên truyền nam_hoc dù hồ sơ đã khai. Thiếu nó thì mọi tin bị ghi
        # "chưa biết năm học của bạn" — nói sai với học viên vừa khai xong năm học.
        # Lấy thẳng từ hồ sơ; vẫn chỉ dùng để ghi chú + xếp hạng, không loại tin.
        if not isinstance(a.get("nam_hoc"), int) and isinstance((profile or {}).get("nam_hoc"), int):
            a["nam_hoc"] = profile["nam_hoc"]
        gh = args.get("gioi_han")
        gh = MAC_DINH_TIN if not isinstance(gh, int) else max(1, min(gh, TRAN_TIN))
        # Hồ sơ do server bơm vào, model KHÔNG tự truyền được — nó chỉ đổi thứ tự,
        # không đổi tập tin trả về.
        tat_ca = xep_hang(**a, linh_vuc_tru=lv_tru, profile=profile)
        if lv_tru:
            hop_lv = [x for x in tat_ca
                      if not any(t.startswith("thuộc lĩnh vực ") for t in x["thieu"])]
        else:
            hop_lv = tat_ca
        dat = [x for x in hop_lv if not x["thieu"]]
        ds = (hop_lv or tat_ca)[:gh]          # ưu tiên đúng lĩnh vực trước, hết mới fallback
        so_gan = sum(1 for x in ds if x["thieu"])
        con = max(0, len(dat) - (len(ds) - so_gan))
        # Nói thẳng còn bao nhiêu tin bị cắt, và tin nào chỉ là gần đúng. Im lặng cắt
        # bớt hay im lặng trộn tin gần đúng vào đều là nói dối học viên theo kiểu khác.
        kq_model = {"so_tin_hien": len(ds), "so_tin_dat_du_dieu_kien": len(dat),
                    "so_tin_gan_dung_dang_hien": so_gan,
                    "con_chua_hien": con, "danh_sach": ds}

        # Ngành ngoài phạm vi phải chặn TRƯỚC nhánh "gần đúng" bên dưới, vì hai chuyện
        # này nghe giống nhau mà bản chất khác hẳn: "gần đúng" nghĩa là thư viện CÓ mảng
        # đó nhưng tin lệch vài điều kiện, còn đây là thư viện KHÔNG CÓ mảng đó. Gộp
        # chung thì học viên hỏi thực tập marketing sẽ nhận một list tin Backend gắn nhãn
        # "gần đúng" — hiểu nhầm là mình gõ sai từ khoá, rồi thử lại mấy lượt cho một
        # thứ không tồn tại trong corpus.
        ngoai = linh_vuc_ngoai_pham_vi(a.get("tu_khoa"))
        if ngoai:
            kq_model["ngoai_pham_vi"] = ngoai
            kq_model["nhac"] = (
                f"THƯ VIỆN KHÔNG CÓ TIN NGÀNH {ngoai.upper()}. Toàn bộ tin trong hệ thống "
                f"là CNTT / dữ liệu / AI — đây là giới hạn của nguồn tin, không phải học "
                f"viên gõ sai từ khoá. Nói thẳng ngay câu đầu là hệ thống không phục vụ "
                f"ngành này và không có tin nào để đối chiếu. TUYỆT ĐỐI không gọi mấy tin "
                f"dưới đây là 'gần đúng' — chúng là ngành khác hẳn, không phải bản gần "
                f"giống của thứ học viên hỏi. Được phép nói thêm rằng thư viện đang có "
                f"tin CNTT/dữ liệu/AI nếu họ muốn xem, nhưng phải để họ tự chọn.")
        elif not dat:
            kq_model["nhac"] = (
                "KHÔNG có tin nào đạt đủ điều kiện học viên nêu. Danh sách dưới đây là "
                "tin GẦN ĐÚNG nhất — mỗi tin có field `thieu` ghi rõ nó lệch chỗ nào. "
                "Nói thẳng là không có tin khớp hẳn, rồi vẫn giới thiệu mấy tin này kèm "
                "chỗ lệch, để học viên tự quyết. TUYỆT ĐỐI không trả lời suông là "
                "'không tìm thấy tin nào' rồi dừng.")
        elif so_gan:
            kq_model["nhac"] = (f"{len(dat)} tin đạt đủ điều kiện, {so_gan} tin cuối chỉ "
                                f"GẦN ĐÚNG — phải nói rõ tin nào lệch và lệch chỗ nào.")
        elif con:
            kq_model["nhac"] = (f"Còn {con} tin đạt đủ điều kiện nữa chưa hiện. Nói rõ cho "
                                f"học viên biết và mời họ xin xem thêm nếu muốn.")
        # `ngoai_pham_vi` đi kèm event để UI tự dựng biển báo, KHÔNG phụ thuộc vào việc
        # model có chịu nói ra hay không. Cùng một luật ở hai chỗ: model được nhắc, còn
        # giao diện thì cứ hiện — đúng cách checker.py soát trích dẫn thay vì tin model.
        return kq_model, {"loai": "tim_tin", "data": ds, "con_chua_hien": con,
                          "tong": len(dat), "so_gan_dung": so_gan,
                          "ngoai_pham_vi": ngoai}
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
