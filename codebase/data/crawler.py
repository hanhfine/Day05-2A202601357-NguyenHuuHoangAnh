"""Crawler tin thực tập/học bổng thật — dùng SerpAPI (Google Jobs).

SerpAPI search Google Jobs → trả JSON sạch, không bị block, không cần Selenium.
Free tier: 100 search/tháng. Mỗi lần chạy tốn len(QUERIES) search.
Đăng ký key miễn phí tại: https://serpapi.com/

Không cần cài gì thêm — gọi REST bằng urllib, không dùng SDK.
Key đặt trong codebase/.env:   SERPAPI_KEY=xxx

Chạy:
    python data/crawler.py                          # cần SERPAPI_KEY trong .env
    python data/crawler.py --preview                # xem trước, không ghi file
    python data/crawler.py --gioi-han 40            # số tin thật tối đa
    python data/crawler.py --mock                   # dùng data mẫu, không gọi API
    python data/crawler.py --bo-qua-kiem-url        # không bấm thử link (offline)
    python data/crawler.py --gop --gioi-han 200 --ngan-sach 150
                                                    # gộp thêm vào tin REAL-* đã có
                                                    # cho đủ 200, tiêu tối đa 150 search

Quota thì hữu hạn (free tier), nên hai cờ này đi cùng nhau:
    --gop        không crawl lại tin đã có trong corpus, chỉ crawl phần còn thiếu
    --ngan-sach  trần CỨNG số search; đặt bằng số search còn lại trong tháng
Xem còn bao nhiêu search: https://serpapi.com/account.json?api_key=...

Corpus có HAI lớp và script này CHỈ sở hữu lớp REAL-*:
    OPP-*   fixture giả, do data/gen_corpus.py sinh — dùng cho smoke_test/eval
    REAL-*  tin thật crawl về, link đã được máy bấm thử
"""
import argparse
import concurrent.futures as cf
import json
import re
import ssl
import sys
import time
import unicodedata
import urllib.request
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode, urlparse

sys.stdout.reconfigure(encoding="utf-8")

D = Path(__file__).resolve().parent
CODEBASE = D.parent


# ── đọc .env (copy từ llm.py để không import vòng) ───────────────────────────
def _nap_env():
    for f in (CODEBASE / ".env", CODEBASE.parent / ".env"):
        if not f.exists():
            continue
        for dong in f.read_text(encoding="utf-8").splitlines():
            dong = dong.strip()
            if not dong or dong.startswith("#") or "=" not in dong:
                continue
            ten, _, gia = dong.partition("=")
            ten, gia = ten.strip(), gia.strip().strip('"').strip("'")
            import os
            if gia and not os.environ.get(ten):
                os.environ[ten] = gia


_nap_env()
import os
SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "")


# ── helpers ──────────────────────────────────────────────────────────────────

def _sach(s) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", str(s).strip())


def _kd(s: str) -> str:
    # `đ` là U+0111, không phân rã được bằng NFD nên phải thay tay — xem chú thích
    # cùng chỗ trong core/tools.py.
    s = unicodedata.normalize("NFD", s.lower()).replace("đ", "d")
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _khop_tu(tu: str, van: str) -> bool:
    """Có `tu` đứng thành từ riêng trong `van` không (cả hai đã bỏ dấu, lowercase).

    BẢN CŨ DÙNG `tu in van` VÀ ĐÓ LÀ NGUỒN CỦA HAI TIN RÁC:
      · "ai" khớp substring trong "t[ai] Việt Nam" → REAL-005 "RECRUITMENT INTERN"
        (công ty headhunt tuyển intern Nhân sự) lọt qua filter lĩnh vực.
      · "intern" khớp trong "[intern]al developer tools" → tin "Backend Engineer
        Junior+/Senior" bị dán cap_do=["intern"].
    `core/tools.py` đã sửa đúng lỗi này cho phía tìm kiếm nhưng crawler thì chưa —
    nên rác vẫn vào được corpus từ đầu nguồn.
    """
    return re.search(rf"(?<![a-z0-9]){re.escape(tu.strip())}(?![a-z0-9])", van) is not None


# Từ khoá lĩnh vực MẠNH: nhắc ở đâu trong tin cũng đủ để nhận, vì gần như không
# có nghĩa nào khác ngoài IT/data/AI.
_LV_MANH = [
    "machine learning", "deep learning", "computer vision", "mlops", "nlp", "llm",
    "python", "java", "javascript", "sql", "backend", "frontend", "fullstack",
    "developer", "software engineer", "lap trinh", "phan mem",
    "cntt", "cong nghe thong tin", "khoa hoc may tinh", "khoa hoc du lieu",
    "ky thuat may tinh", "tri tue nhan tao", "hoc may", "du lieu", "analytics",
]

# Từ khoá lĩnh vực YẾU: CHỈ tính khi nằm ở TIÊU ĐỀ.
#
# "ai" hai chữ cái là thứ yếu nhất, và ranh giới từ cũng không cứu được:
#   · "phần mềm thiết kế (AI, Photoshop, Canva)" → AI ở đây là Adobe Illustrator,
#     đã kéo một tin thực tập NHÂN SỰ vào corpus;
#   · "supporting the adoption of AI in transfer pricing" → tin THUẾ;
#   · "có kỹ năng sử dụng các công nghệ AI" → tin QUẢN LÝ THIẾT KẾ.
# Cả ba chỉ nhắc thoáng AI trong phần mô tả. Còn "data" thì dính "data entry",
# "supply chain analyst". Nhắc thoáng trong mô tả không làm tin đó thành tin IT;
# nằm ở tiêu đề thì mới là tin về nó.
_LV_YEU = ["ai", "data"]


def _lien_quan_ai(title: str, desc: str) -> bool:
    """Tin có thuộc lĩnh vực hệ thống phục vụ (IT/data/AI) không.

    BỎ HẲN "intern"/"thuc tap"/"hoc bong" KHỎI DANH SÁCH NÀY. Mấy từ đó nói về
    LEVEL và LOẠI cơ hội, không nói gì về lĩnh vực — nên chúng khớp mọi tin thực
    tập bất kể ngành. Đó là đường mà REAL-005 "RECRUITMENT INTERN" (công ty
    headhunt tuyển intern Nhân sự) đi vào corpus rồi leo lên đầu bảng khi học
    viên tìm "thực tập AI". Từ lúc thêm query fresher/junior thì lỗ này rộng hơn
    nhiều: "Sales Fresher", "HR Junior", "Marketing Intern" đều sẽ lọt.
    Muốn vào corpus thì tin phải nhắc một từ THUỘC LĨNH VỰC.

    Cũng bỏ "software": nó khớp "Design software" trong tin Design Engineer /
    Detailing Engineer — mấy tin cơ khí-xây dựng, không phải IT.
    """
    t, d = _kd(title), _kd(title + " " + desc)
    if any(_khop_tu(k, d) for k in _LV_MANH):
        return True
    # Từ YẾU chỉ được tính khi nằm ở TIÊU ĐỀ — xem chú thích ở _LV_YEU.
    return any(_khop_tu(k, t) for k in _LV_YEU)


_HB = ["hoc bong", "scholarship", "hoc phi"]
_TT = ["intern", "internship", "thuc tap"]


# Level KHÔNG loại trừ nhau: một tin ghi "Intern/Fresher level" thuộc cả hai.
# Nên `cap_do` là LIST, không phải một giá trị — xếp REAL-014 vào đúng một ô là
# tự tay bỏ mất nửa số học viên đáng thấy nó.
_CAP_DO = {
    "intern": _TT + ["sinh vien thuc tap"],
    "fresher": ["fresher", "moi tot nghiep", "entry level", "entry-level",
                "sap tot nghiep", "new graduate", "no experience"],
    "junior": ["junior", "1-2 nam kinh nghiem", "1 nam kinh nghiem",
               "duoi 2 nam kinh nghiem"],
}

# "senior" KHÔNG nằm trong thang hệ thống phục vụ, nhưng vẫn phải gán nhãn: query
# fresher/junior của Google Jobs trả về cả "Senior AI Engineer", "AI Engineer (Middle
# Level)", "AI Engineer Lead". Không nhãn thì cap_do rỗng, mà rỗng nghĩa là "tin không
# nêu level" nên xep_hang() không bao giờ loại — học viên hỏi fresher lại thấy tin
# Senior xếp hạng KHỚP HẲN.
#
# TÁCH RIÊNG VÌ CHỈ ĐƯỢC DÒ TRONG TIÊU ĐỀ. Trong mô tả thì mấy từ này gần như luôn nói
# chuyện khác: "Other tasks as assigned by direct manager" là mô tả công việc chứ không
# phải yêu cầu level, mà mọi việc đều có manager — nó làm tin "Data Analyst Ngân Hàng
# Shinhan" (thật ra entry level) bị dán senior rồi ẩn khỏi mắt học viên. Tương tự
# "Qualcomm's leadership in generative AI" là câu quảng cáo công ty.
# Cấp bậc cao thì gần như luôn nằm ở tiêu đề, nên chỉ đọc tiêu đề là đủ và sạch hơn.
_CAP_DO_TITLE = {
    "senior": ["senior", "middle", "mid-level", "middle level", "lead", "principal",
               "manager", "truong nhom", "3 nam kinh nghiem", "5 nam kinh nghiem"],
}


def _phan_loai(title: str, desc: str) -> tuple[str, list[str]]:
    """→ (kind, cap_do). Trả CẢ HAI cùng lúc, không tách thành hai hàm public.

    VÌ SAO GỘP: hai field phải nhất quán — `kind="thuc_tap"` thì `cap_do` buộc phải
    chứa "intern". Bản trước để hai hàm tự đọc tin độc lập nên chúng chỏi nhau:
    "Junior Industrial Data & AI Engineer" ra kind=thuc_tap (mô tả có nhắc "thực tập")
    nhưng cap_do=["junior"] (tiêu đề ghi Junior). Tin đó rồi hiện ra ở câu "tìm thực
    tập" như tin khớp hẳn, dù đúng ra là việc junior. Suy `kind` TỪ `cap_do` thì
    không còn đường nào để lệch.

    ĐỌC TIÊU ĐỀ TRƯỚC, MÔ TẢ SAU. Mô tả tuyển dụng nhắc level rất tuỳ tiện: tin
    "Design Engineer (Open for fresher)" có câu "Internship or academic project
    experience" ở phần yêu cầu; tin "Backend Engineer Junior+/Senior" có "internal
    developer tools". Tiêu đề thì gần như luôn nói đúng level.
    """
    t, d = _kd(title), _kd(desc)

    # Học bổng xét riêng và trước hết — nó không nằm trên thang level nào.
    for van in (t, d):
        if any(_khop_tu(k, van) for k in _HB):
            return "hoc_bong", []

    # Level: tiêu đề nêu thì lấy đúng nó và DỪNG, không xét mô tả nữa.
    # `_CAP_DO_TITLE` (senior) chỉ góp vào lượt đọc tiêu đề — xem chú thích ở dict đó.
    cap_do: list[str] = []
    for van, tu_dien in ((t, {**_CAP_DO, **_CAP_DO_TITLE}), (d, _CAP_DO)):
        cap_do = [lv for lv, tu in tu_dien.items()
                  if any(_khop_tu(k, van) for k in tu)]
        if cap_do:
            break

    # `intern` thắng khi tin nhận nhiều level (vd "AI Engineer (Intern/Fresher level)"):
    # thực tập là câu hỏi hay gặp nhất, mà nhánh fresher vẫn thấy tin đó nhờ `cap_do`.
    return ("thuc_tap" if "intern" in cap_do else "viec_lam"), cap_do




def _chuan_ngay(s: str) -> str:
    s = _sach(s)
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s[: len(fmt)], fmt).strftime("%d/%m/%Y")
        except ValueError:
            pass
    return s


# ── kiểm URL ─────────────────────────────────────────────────────────────────
#
# QUYẾT ĐỊNH THIẾT KẾ (CP5 sẽ hỏi): thà KHÔNG có link còn hơn link sai.
#
# Link nằm ở field riêng, KHÔNG nằm trong raw_text — nên nó đi vòng qua checker
# trích dẫn của verdict.py. Cả cơ chế chống bịa của hệ thống không soi tới link.
# Chỗ duy nhất chặn được là ở đây, lúc ghi corpus. Nên máy phải tự bấm thử từng
# link, và link nào không sống thì bị xoá trắng chứ không được đoán.
#
# Ba mức, vì "sống" không có nghĩa là "đúng tin":
#   tin        — link tới ĐÚNG tin tuyển dụng (chỉ SerpAPI apply_options mới có)
#   tuyen_dung — trang tuyển dụng của tổ chức, phải tự tìm tin trong đó
#   to_chuc    — chỉ có trang chủ tổ chức
# UI đọc mức này để đặt nhãn nút cho đúng thứ nó thật sự dẫn tới.

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
_RE_TUYEN_DUNG = re.compile(r"career|tuyen-?dung|job|recruit|hiring|viec-?lam", re.I)


def _muc_url(u: str) -> str:
    """Đoán mức từ đường dẫn — chỉ dùng khi crawler không tự khai."""
    return "tuyen_dung" if _RE_TUYEN_DUNG.search(u or "") else "to_chuc"


def _kiem_url(u: str, muc_khai: str = "") -> dict:
    """Bấm thử một link. Trả {url, url_loai, _url_status}.

    BA KẾT CỤC, KHÔNG PHẢI HAI — chỗ này sửa sau khi crawl thật lần đầu:

      chết          DNS không phân giải / 404 / 410 → trang thật sự không tồn tại,
                    xoá trắng url.
      không kiểm được  403 / 401 / 429 / 5xx / connection reset / timeout → trang
                    CHẶN BOT, không phải trang chết. LinkedIn, TopCV, JobsGO đều
                    chặn; mở bằng trình duyệt thì vào bình thường. GIỮ link, đánh dấu
                    là chưa xác minh để UI nói thật với học viên.
      ok            2xx.

    Lần crawl thật đầu tiên gộp hai nhóm đầu làm một và xoá mất 10/14 tin — toàn tin
    thật còn sống. Đúng cái lỗi mà cả hệ thống này tồn tại để chặn: máy không chắc thì
    không được âm thầm cắt cơ hội của học viên, phải nói ra là mình không kiểm được.
    """
    if not u:
        return {"url": "", "url_loai": "", "_url_status": "khong_co"}

    goc_sau = urlparse(u).path.strip("/")
    hdr = {"User-Agent": _UA,
           "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
           "Accept-Language": "vi,en-US;q=0.9,en;q=0.8"}
    try:
        req = urllib.request.Request(u, headers=hdr)
        with urllib.request.urlopen(req, timeout=15, context=_CTX) as resp:
            ma, cuoi = resp.status, resp.geturl()
    except urllib.error.HTTPError as e:
        if e.code in (404, 410):
            return {"url": "", "url_loai": "", "_url_status": f"chet:HTTP{e.code}"}
        # 403/401/429/5xx: bị chặn hoặc lỗi phía họ — không kết luận là chết.
        return {"url": u, "url_loai": muc_khai or _muc_url(u),
                "_url_status": f"khong_kiem_duoc:HTTP{e.code}"}
    except urllib.error.URLError as e:
        ly_do = str(getattr(e, "reason", e))
        if "getaddrinfo" in ly_do or "Name or service not known" in ly_do:
            return {"url": "", "url_loai": "", "_url_status": "chet:DNS"}
        return {"url": u, "url_loai": muc_khai or _muc_url(u),
                "_url_status": f"khong_kiem_duoc:{ly_do[:40]}"}
    except Exception as e:
        return {"url": u, "url_loai": muc_khai or _muc_url(u),
                "_url_status": f"khong_kiem_duoc:{type(e).__name__}"}

    if ma in (404, 410):
        return {"url": "", "url_loai": "", "_url_status": f"chet:HTTP{ma}"}
    if ma >= 400:
        return {"url": u, "url_loai": muc_khai or _muc_url(u),
                "_url_status": f"khong_kiem_duoc:HTTP{ma}"}

    # Soft-404: xin đường dẫn sâu mà bị đá về trang chủ → link tin đã mất,
    # giữ lại trang chủ nhưng phải hạ mức, không được để nhãn "Xem tin".
    if goc_sau and not urlparse(cuoi).path.strip("/"):
        return {"url": cuoi, "url_loai": "to_chuc", "_url_status": "chuyen_huong_trang_chu"}

    # LƯU LINK ĐÃ XIN, KHÔNG LƯU LINK ĐÍCH. Nhiều trang chủ đá sang campaign tạm
    # (samsung.com/vn → trang quảng cáo một mẫu điện thoại). Lưu link đích là tự
    # đóng băng cái campaign đó vào corpus — vài tuần nữa nó 404, đúng lại cái bệnh
    # đang chữa. Link đã xin thì ổn định hơn; trình duyệt sẽ tự đi nốt chặng redirect.
    muc = muc_khai or _muc_url(u)
    r = {"url": u, "url_loai": muc, "_url_status": f"ok:{ma}"}
    if cuoi.rstrip("/") != u.rstrip("/"):
        r["_url_dich"] = cuoi          # ghi lại để người sau soi được, không dùng để hiện
        # Link tự nhận trỏ ĐÚNG một tin mà bị đá sang chỗ khác → tin đó gần như đã gỡ.
        # CareerViet đá URL tin bịa về trang "tất cả việc làm" và vẫn trả 200, nên chỉ
        # nhìn mã 200 thì tưởng link tốt. Không dám khẳng định là chết, nhưng dứt khoát
        # không được gắn nhãn "đã xác minh" cho nó.
        r["_url_status"] = (f"khong_kiem_duoc:tin_bi_chuyen_huong"
                            if muc == "tin" else f"ok:{ma}:chuyen_huong")
    return r


def kiem_tat_ca(tin_list: list[dict]) -> list[dict]:
    """Kiểm song song mọi link, ghi kết quả thẳng vào từng tin."""
    print(f"\n[Kiểm URL] Đang bấm thử {len(tin_list)} link...")
    with cf.ThreadPoolExecutor(max_workers=10) as ex:
        ket = list(ex.map(lambda t: _kiem_url(t.get("url", ""),
                                              t.get("url_loai", "")), tin_list))
    for t, k in zip(tin_list, ket):
        t.update(k)

    for t in tin_list:
        s = t["_url_status"]
        dau = "✓" if s.startswith("ok") else ("?" if s.startswith("khong_kiem_duoc") else "✗")
        print(f"  {dau} [{t.get('id', '???')}] {s:42} "
              f"{t['url'][:72] or '(xoá — trang không tồn tại)'}")
    n_ok = sum(1 for t in tin_list if t["_url_status"].startswith("ok"))
    n_chua = sum(1 for t in tin_list if t["_url_status"].startswith("khong_kiem_duoc"))
    n_chet = sum(1 for t in tin_list if t["_url_status"].startswith("chet"))
    print(f"  → {n_ok} sống · {n_chua} bị chặn bot (giữ, đánh dấu chưa xác minh) · "
          f"{n_chet} chết thật (xoá trắng)")
    return tin_list


def _tach_dong(s: str) -> list[str]:
    """Tách mô tả Google Jobs thành từng dòng.

    Google trả mô tả dính liền: "...nhà thông minh.Hỗ trợ giải quyết Bài toán AI:..."
    — hết câu là viết hoa ngay, không có dấu cách. Để nguyên thì cả tin thành MỘT dòng,
    mà model phải trích `evidence_line` theo số dòng Lk → trích dẫn thành vô nghĩa và
    checker không soát được gì. Nên cắt trước mỗi chữ hoa đứng ngay sau . : ;
    """
    ra = []
    for ch in s.replace("\r", "\n"):
        if ra and ch.isupper() and ra[-1] and ra[-1][-1] in ".:;":
            ra.append("")
        if ch == "\n":
            ra.append("")
        else:
            if not ra:
                ra.append("")
            ra[-1] += ch
    # bỏ dòng rỗng / quá ngắn, gọn khoảng trắng
    return [d for d in (re.sub(r"[ \t]+", " ", x).strip() for x in ra) if len(d) > 1]


MAX_DONG, MAX_KY_TU = 60, 4000


def _to_raw_text(title: str, company: str, highlights: list, extensions: list,
                 location: str, mo_ta: str = "", ngay_dang: str = "") -> str:
    """Chuyển kết quả Google Jobs sang raw_text chuẩn schema corpus.

    HAI CHỖ ĐÃ SỬA, cả hai đều làm hỏng data thật:

    1. Trước đây chỉ đọc `job_highlights`. Nhưng Google Jobs trả highlights RỖNG cho
       10/10 tin thật crawl được — toàn bộ yêu cầu nằm ở `description` mà hàm này
       không hề nhận. Kết quả: mọi tin thật vào corpus đều cụt, verdict luôn ra
       "tin quá sơ sài". Giờ `description` là nguồn chính, highlights chỉ là dự phòng.

    2. Trước đây ghi `detected_extensions.posted_at` thành "Hạn nộp hồ sơ". Nhưng
       posted_at là NGÀY ĐĂNG, không phải hạn nộp — nó ra chuỗi kiểu "20 ngày trước".
       Ghi thế là bịa ra một hạn nộp không có trong tin, đúng cái lỗi hệ thống này
       sinh ra để chặn. Google Jobs KHÔNG cho hạn nộp, nên không ghi hạn nộp nữa;
       verdict sẽ tự xếp vào `not_stated` = "tin không nêu hạn nộp".
    """
    lines = [f"[{title} — {company}]"]

    for h in highlights:                       # dự phòng, hiếm khi có
        title_h = _sach(h.get("title", ""))
        if title_h:
            lines.append(f"{title_h}:")
        for item in h.get("items", []):
            lines.append(f"- {_sach(item)}")

    if mo_ta:
        lines += _tach_dong(mo_ta)

    for ext in (extensions or []):             # "Toàn thời gian", "Làm việc từ xa"...
        ext = _sach(ext)
        if ext and ext != _sach(ngay_dang):
            lines.append(ext)

    if location:
        lines.append(f"Địa điểm: {_sach(location)}.")
    if ngay_dang:
        # Nói rõ đây là ngày ĐĂNG. Không chứa chữ "hạn" nên RE_HAN của verdict.py
        # không nhặt nhầm thành hạn nộp.
        lines.append(f"Google Jobs ghi tin đăng: {_sach(ngay_dang)}. Tin không nêu ngày chốt hồ sơ.")

    lines = lines[:MAX_DONG]
    ra = "\n".join(lines)
    return ra if len(ra) <= MAX_KY_TU else ra[:MAX_KY_TU].rsplit("\n", 1)[0]


# ── SerpAPI Google Jobs ───────────────────────────────────────────────────────

# Mỗi query = 1 search SerpAPI. Free tier 100 search/tháng.
# ~60 query × 1 trang = ~60 search/lần chạy (vừa đủ free tier, dùng --trang 1).
# Muốn lấy thêm trang 2: --trang 2 (hết ~120 search, trả phí nếu vượt 100).
QUERIES = [
    # ════════════════════════════════════════════════════════════
    # INTERN / THỰC TẬP SINH
    # ════════════════════════════════════════════════════════════
    "thực tập sinh AI intern Hà Nội",
    "thực tập sinh data analyst intern Hà Nội",
    "thực tập sinh machine learning intern TP HCM",
    "thực tập sinh NLP AI intern",
    "thực tập sinh computer vision intern Việt Nam",
    "thực tập sinh software engineer intern Hà Nội",
    "thực tập sinh backend developer intern Việt Nam",
    "thực tập sinh frontend developer intern Việt Nam",
    "thực tập sinh DevOps cloud intern Việt Nam",
    "thực tập sinh data engineer intern Hà Nội",
    "thực tập sinh mobile developer intern Việt Nam",
    "thực tập sinh QA tester intern Việt Nam",
    "AI intern machine learning internship Vietnam",
    "machine learning intern Vietnam",
    "data science intern Vietnam",
    "software engineer intern Vietnam",

    # ════════════════════════════════════════════════════════════
    # FRESHER / ENTRY LEVEL (0–1 năm kinh nghiệm)
    # ════════════════════════════════════════════════════════════
    "fresher AI engineer Hà Nội",
    "fresher machine learning engineer Việt Nam",
    "fresher data analyst Việt Nam",
    "fresher data scientist Việt Nam",
    "fresher python developer Việt Nam",
    "fresher backend developer Việt Nam",
    "fresher frontend developer Việt Nam",
    "fresher fullstack developer Việt Nam",
    "fresher software engineer Đà Nẵng",
    "fresher DevOps cloud engineer Việt Nam",
    "fresher mobile developer iOS Android Việt Nam",
    "AI engineer entry level Vietnam fresher",
    "junior python developer Vietnam",

    # ════════════════════════════════════════════════════════════
    # JUNIOR (1–3 năm kinh nghiệm)
    # ════════════════════════════════════════════════════════════
    "junior AI engineer Hà Nội",
    "junior machine learning engineer Hà Nội",
    "junior data engineer TP HCM",
    "junior data analyst TP HCM",
    "junior backend developer Việt Nam",
    "junior frontend developer React Việt Nam",
    "junior fullstack developer Việt Nam",
    "junior DevOps cloud engineer Việt Nam",
    "junior mobile developer iOS Android Việt Nam",
    "junior software engineer Đà Nẵng",
    "junior QA automation engineer Việt Nam",

    # ════════════════════════════════════════════════════════════
    # MIDDLE / SENIOR (3+ năm)
    # ════════════════════════════════════════════════════════════
    "AI engineer middle senior Hà Nội",
    "machine learning engineer senior Việt Nam",
    "senior data scientist Việt Nam",
    "senior backend engineer Python Java Việt Nam",
    "senior frontend engineer React Việt Nam",
    "senior fullstack engineer Việt Nam",
    "middle senior DevOps cloud engineer Việt Nam",
    "lead AI engineer Việt Nam",
    "senior data engineer Việt Nam",
    "senior software engineer Hà Nội TP HCM",
    "middle senior mobile engineer iOS Android Việt Nam",
    "senior machine learning engineer Vietnam",

    # ════════════════════════════════════════════════════════════
    # HỌC BỔNG
    # ════════════════════════════════════════════════════════════
    "học bổng CNTT AI sinh viên Việt Nam 2026",
    "học bổng kỹ thuật phần mềm sinh viên 2026",
    "VinIF học bổng 2026",
    "scholarship CNTT AI Vietnam 2026",

    # ════════════════════════════════════════════════════════════
    # MỞ RỘNG — thêm để corpus lên ~200 tin.
    #
    # Query cũ bị chụm vào một nhóm hẹp (AI/data/web ở Hà Nội + TP.HCM), nên đào
    # sâu thêm trang chỉ trả về đúng mấy tin đã thấy. Muốn NHIỀU tin thì phải nới
    # theo hai trục Google Jobs thật sự phân biệt được: NGĂN XẾP công nghệ và
    # THÀNH PHỐ. Nới theo level thì không ăn thua — "junior X" và "fresher X" trả
    # về gần như cùng một tập.
    #
    # Vẫn nằm trong lĩnh vực hệ thống phục vụ (IT/data/AI): mọi tin về sau còn
    # phải qua `_lien_quan_ai`, nên query lạc ngành chỉ tốn quota chứ không làm
    # bẩn được corpus.
    # ════════════════════════════════════════════════════════════
    # — ngăn xếp chưa có query nào chạm tới —
    "tuyển dụng lập trình viên Java Spring Boot Việt Nam",
    "tuyển dụng lập trình viên .NET C# Việt Nam",
    "tuyển dụng lập trình viên PHP Laravel Việt Nam",
    "tuyển dụng lập trình viên Golang Việt Nam",
    "tuyển dụng lập trình viên NodeJS Việt Nam",
    "tuyển dụng lập trình viên React Vue Angular Việt Nam",
    "tuyển dụng lập trình viên Flutter React Native Việt Nam",
    "tuyển dụng lập trình nhúng embedded C++ Việt Nam",
    "tuyển dụng kỹ sư dữ liệu data warehouse ETL Việt Nam",
    "tuyển dụng business intelligence Power BI Tableau Việt Nam",
    "tuyển dụng kỹ sư an toàn thông tin security Việt Nam",
    "tuyển dụng lập trình game Unity Unreal Việt Nam",
    "tuyển dụng blockchain web3 developer Việt Nam",
    "tuyển dụng kiểm thử phần mềm QA QC automation Việt Nam",
    "tuyển dụng system admin SRE linux Việt Nam",
    "tuyển dụng AI engineer LLM generative AI Việt Nam",
    "tuyển dụng prompt engineer AI product Việt Nam",
    "tuyển dụng data analyst business analyst IT Việt Nam",

    # — thành phố ngoài Hà Nội / TP.HCM —
    "tuyển dụng IT lập trình viên Đà Nẵng",
    "thực tập sinh CNTT Đà Nẵng",
    "tuyển dụng IT lập trình viên Cần Thơ",
    "tuyển dụng IT lập trình viên Huế",
    "tuyển dụng IT lập trình viên Bình Dương Đồng Nai",
    "tuyển dụng IT lập trình viên Hải Phòng",
    "tuyển dụng IT phần mềm Nha Trang Quy Nhơn",
    "việc làm IT remote làm việc từ xa Việt Nam",

    # — công ty lớn hay tuyển sinh viên, tin thường không lên đầu query chung —
    "FPT Software tuyển thực tập sinh fresher",
    "Viettel VNPT tuyển kỹ sư phần mềm AI",
    "VNG Zalo tuyển engineer intern fresher",
    "Samsung LG tuyển kỹ sư phần mềm Việt Nam",
    "ngân hàng tuyển IT data analyst Việt Nam",

    # — học bổng, nới thêm vì 4 query cũ ra rất ít —
    "học bổng du học thạc sĩ khoa học máy tính",
    "học bổng nghiên cứu trí tuệ nhân tạo sinh viên",
    "scholarship computer science students Vietnam",
]


def _serpapi(params: dict) -> dict:
    """Gọi SerpAPI qua REST. Không dùng SDK `google-search-results` để bớt một
    dependency và một chỗ hỏng — endpoint này chỉ là GET trả JSON."""
    u = "https://serpapi.com/search.json?" + urlencode(params)
    req = urllib.request.Request(u, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=60, context=_CTX) as resp:
        return json.loads(resp.read())


def _token_trang_sau(results: dict) -> str | None:
    """Token trang kế tiếp, chấp nhận vài chỗ SerpAPI từng đặt nó.

    Đọc nhiều khoá vì hình dạng response của engine google_jobs đã đổi qua các
    đời API (khi thì `serpapi_pagination.next_page_token`, khi thì ở gốc). Dò cả
    hai rồi mới chịu dừng — đoán sai một khoá là mất hết trang 2 trở đi mà không
    có lỗi nào báo, chỉ thấy ít tin hơn mong đợi.
    """
    for o in (results.get("serpapi_pagination"), results.get("pagination"), results):
        if isinstance(o, dict) and o.get("next_page_token"):
            return o["next_page_token"]
    return None


def crawl_google_jobs(gioi_han: int = 50, so_trang: int = 3, ngan_sach: int = 0,
                      da_co: set | None = None) -> list[dict]:
    """Dùng SerpAPI để tìm Google Jobs.

    `so_trang` = số trang đọc MỖI query. MỖI TRANG LÀ MỘT SEARCH tính vào quota.
    `ngan_sach` = trần cứng số search được phép gọi (0 = không chặn, chỉ chịu trần
    len(QUERIES) × so_trang). `da_co` = khoá của tin đã nằm sẵn trong corpus, để
    chế độ --gop không đếm lại tin cũ thành tin mới.

    QUÉT RỘNG TRƯỚC, ĐÀO SÂU SAU — vòng lặp ngoài là TRANG, vòng trong là QUERY.
    Bản trước chạy ngược lại (xong hết trang của query 1 rồi mới sang query 2).
    Với danh sách query dài mà quota thì hữu hạn, cách đó tiêu sạch ngân sách vào
    mấy query đầu bảng rồi chết trước khi chạm tới nhóm cuối — mà nhóm cuối chính
    là mấy query mở rộng (Đà Nẵng, embedded, học bổng) chứa tin KHÔNG query nào
    khác trả về. Quét rộng trước thì lúc hết ngân sách ta mất phần SÂU (trang 2, 3
    — vốn trùng lặp nhiều nhất), chứ không mất nguyên một mảng lĩnh vực.
    """
    if not SERPAPI_KEY:
        print("  ✗ Chưa có SERPAPI_KEY. Đặt vào .env rồi chạy lại.")
        print("    Đăng ký miễn phí tại: https://serpapi.com/ (100 search/tháng)")
        return []

    tran = len(QUERIES) * so_trang
    if ngan_sach:
        tran = min(tran, ngan_sach)
    print(f"\n[Google Jobs / SerpAPI] {len(QUERIES)} query × tối đa {so_trang} trang")
    print(f"  Ngân sách: tối đa {tran} search"
          + (f" (trần --ngan-sach {ngan_sach})" if ngan_sach else "")
          + f". Mục tiêu {gioi_han} tin. Dừng sớm nếu đủ tin hoặc hết trang.")

    ket_qua: list[dict] = []
    seen_titles: set = set(da_co or ())
    thong_ke = {"trung": 0, "sai_linh_vuc": 0, "khong_tieu_de": 0}
    da_goi = 0
    het_quota = False
    token: dict[str, str | None] = {q: None for q in QUERIES}   # None = chưa đọc trang nào
    con_trang = list(QUERIES)                                   # query vẫn còn trang để đọc

    for trang in range(1, so_trang + 1):
        if not con_trang or het_quota or len(ket_qua) >= gioi_han:
            break
        print(f"\n  ── Lượt {trang}: đọc trang {trang} của {len(con_trang)} query ──")
        ke_tiep = []

        for query in con_trang:
            if het_quota or len(ket_qua) >= gioi_han or da_goi >= tran:
                break

            params = {
                "engine": "google_jobs",
                "q": query,
                "hl": "vi",
                "gl": "vn",
                "api_key": SERPAPI_KEY,
                "chips": "date_posted:month",  # chỉ tin trong 1 tháng gần đây
            }
            if token[query]:
                params["next_page_token"] = token[query]

            try:
                results = _serpapi(params)
                da_goi += 1
            except Exception as e:
                print(f"  ✗ '{query[:34]}' trang {trang}: {type(e).__name__}: {str(e)[:60]}")
                continue

            # SerpAPI báo lỗi trong JSON (hết quota, key sai) chứ không phải HTTP 4xx.
            if results.get("error"):
                loi = results["error"]
                # "hasn't returned any results" = query này không có tin, KHÔNG phải
                # lỗi hệ thống. Gộp nó vào nhánh hết-quota là tự dừng cả lượt crawl
                # chỉ vì một query rỗng.
                if "run out" in loi.lower() or "quota" in loi.lower():
                    print(f"  ✗ HẾT QUOTA sau {da_goi} search: {loi[:70]}")
                    print("    → Dừng crawl, giữ nguyên tin đã lấy được.")
                    het_quota = True
                    break
                print(f"  · '{query[:34]}' trang {trang}: {loi[:60]}")
                continue

            jobs = results.get("jobs_results", [])
            if not jobs:
                continue

            them = _nap_jobs(jobs, ket_qua, seen_titles, gioi_han, thong_ke)
            print(f"  '{query[:34]}' t{trang}: {len(jobs)} jobs → +{them} "
                  f"(tổng {len(ket_qua)}/{gioi_han}, search {da_goi}/{tran})")

            tk = _token_trang_sau(results)
            if tk:
                token[query] = tk
                ke_tiep.append(query)       # còn trang → cho vào lượt sau
            time.sleep(0.5)   # SerpAPI không cần delay nhiều như crawl trực tiếp

        con_trang = ke_tiep

    # In luôn chỗ hao hụt. Không có bảng này thì "crawl 170 search ra 200 tin" là
    # con số mù: không biết nên thêm query (nếu rụng vì TRÙNG) hay nên sửa filter
    # (nếu rụng vì SAI LĨNH VỰC), nên lần chỉnh sau chỉ còn nước đoán.
    print(f"\n  → đã gọi {da_goi} search · giữ {len(ket_qua)} tin")
    print(f"    hao hụt: {thong_ke['trung']} trùng · "
          f"{thong_ke['sai_linh_vuc']} sai lĩnh vực · "
          f"{thong_ke['khong_tieu_de']} thiếu tiêu đề")
    return ket_qua


def _nap_jobs(jobs: list, ket_qua: list, seen_titles: set, gioi_han: int,
              thong_ke: dict | None = None) -> int:
    """Lọc + nạp một trang kết quả vào `ket_qua`. Trả số tin thêm được.

    Tách khỏi crawl_google_jobs() để vòng lặp phân trang gọi lại được — `seen_titles`
    dùng chung nên tin trùng giữa các TRANG và giữa các QUERY đều bị loại một lần.
    """
    tk = thong_ke if thong_ke is not None else {}
    them = 0
    for j in jobs:
        if len(ket_qua) >= gioi_han:
            break

        title = _sach(j.get("title", ""))
        company = _sach(j.get("company_name", "Không rõ"))
        location = _sach(j.get("location", ""))
        # KHÔNG _sach() ở đây: nó gộp mọi khoảng trắng kể cả xuống dòng, mà xuống
        # dòng chính là ranh giới ý trong mô tả — _tach_dong() cần giữ để cắt dòng.
        description = j.get("description") or ""
        highlights = j.get("job_highlights", [])   # list [{title, items}]
        extensions = j.get("extensions", [])        # ["Full-time", "Work from home"...]
        detected = j.get("detected_extensions", {})
        ngay_dang = _sach(detected.get("posted_at", ""))   # NGÀY ĐĂNG, không phải hạn nộp

        if not title:
            tk["khong_tieu_de"] = tk.get("khong_tieu_de", 0) + 1
            continue

        key = _kd(title + company)
        if key in seen_titles:
            tk["trung"] = tk.get("trung", 0) + 1
            continue
        seen_titles.add(key)

        if not _lien_quan_ai(title, description):
            tk["sai_linh_vuc"] = tk.get("sai_linh_vuc", 0) + 1
            continue

        # SerpAPI trả apply_options[0].link hoặc share_link.
        # apply_options mới thật sự trỏ vào ĐÚNG tin → mức "tin";
        # share_link chỉ là trang kết quả Google → để máy tự xếp mức.
        apply_opts = j.get("apply_options") or []
        url = _sach(apply_opts[0].get("link") if apply_opts else None)
        url_loai = "tin" if url else ""
        if not url:
            url = _sach(j.get("share_link", ""))
        raw_text = _to_raw_text(
            title, company, highlights, extensions, location,
            mo_ta=description, ngay_dang=ngay_dang
        )
        ket_qua.append({
            "title": title,
            "company": company,
            "url": url,
            "url_loai": url_loai,
            "raw_text": raw_text,
            "nguon": "google_jobs",
        })
        them += 1

    return them


# ── mock data (không cần API key, để test flow) ───────────────────────────────

MOCK_POSTINGS = [
    {
        "title": "Thực tập sinh AI Engineer",
        "company": "VNG Corporation",
        "url": "https://vng.com.vn",
        "raw_text": (
            "[Thực tập sinh AI Engineer — VNG Corporation]\n"
            "VNG tuyển thực tập sinh AI để hỗ trợ nhóm nghiên cứu ứng dụng LLM.\n"
            "Yêu cầu:\n"
            "- Sinh viên năm 3 hoặc năm 4 ngành CNTT, Khoa học dữ liệu\n"
            "- Thành thạo Python, hiểu cơ bản về LLM API và prompt engineering\n"
            "- GPA từ 3.2/4.0 trở lên\n"
            "- Cam kết 3 buổi/tuần tại văn phòng TP.HCM (quận 10)\n"
            "Quyền lợi: phụ cấp 6 triệu/tháng, laptop được cấp.\n"
            "Hồ sơ: CV + link GitHub project.\n"
            "Hạn nhận hồ sơ: 20/08/2026."
        ),
        "nguon": "mock",
    },
    {
        "title": "Intern Data Analyst — FPT Software",
        "company": "FPT Software",
        "url": "https://fptsoftware.com",
        "raw_text": (
            "[Intern Data Analyst — FPT Software]\n"
            "FPT Software tuyển thực tập sinh phân tích dữ liệu cho nhóm BI.\n"
            "Đối tượng: sinh viên năm 2 trở lên mọi ngành.\n"
            "Yêu cầu:\n"
            "- Biết SQL cơ bản và Excel\n"
            "- Ưu tiên biết Power BI hoặc Tableau\n"
            "Hình thức: hybrid, 3 ngày/tuần tại Hà Nội.\n"
            "Hồ sơ: CV.\n"
            "Hạn ứng tuyển: 15/09/2026."
        ),
        "nguon": "mock",
    },
    {
        "title": "Thực tập sinh Machine Learning",
        "company": "Zalo AI",
        "url": "https://zalo.ai",
        "raw_text": (
            "[Thực tập sinh Machine Learning — Zalo AI]\n"
            "Nhóm nghiên cứu Zalo AI tuyển intern ML để hỗ trợ dự án nhận dạng giọng nói.\n"
            "Yêu cầu:\n"
            "- Sinh viên năm 3-4 hoặc học viên cao học ngành CNTT, Điện tử\n"
            "- Python thành thạo, đã làm qua ít nhất 1 project deep learning\n"
            "- Ưu tiên có kinh nghiệm với PyTorch hoặc TensorFlow\n"
            "- GPA từ 3.0/4.0\n"
            "Cam kết 4 buổi/tuần onsite tại văn phòng TP.HCM.\n"
            "Hồ sơ: CV + bảng điểm.\n"
            "Hạn: 30/08/2026."
        ),
        "nguon": "mock",
    },
    {
        "title": "AI Intern — Techcombank",
        "company": "Techcombank",
        "url": "https://techcombank.com",
        "raw_text": (
            "[AI Intern — Techcombank]\n"
            "Techcombank Digital tuyển AI Intern cho nhóm AI/ML Banking.\n"
            "Yêu cầu:\n"
            "- Sinh viên năm 3 trở lên ngành CNTT, Toán Tin, Tài chính Ngân hàng\n"
            "- Thành thạo Python, SQL\n"
            "- Không yêu cầu GPA tối thiểu\n"
            "- Cam kết full-time 2 tháng hè tại Hà Nội\n"
            "Ưu tiên ứng viên có project liên quan đến NLP hoặc phân tích dữ liệu tài chính.\n"
            "Hồ sơ: CV + link 1 project.\n"
            "Hạn: 10/08/2026."
        ),
        "nguon": "mock",
    },
    {
        "title": "Học bổng VinIF cho sinh viên xuất sắc 2026",
        "company": "Vingroup Innovation Foundation",
        "url": "https://vinif.org",
        "raw_text": (
            "[Học bổng VinIF cho sinh viên xuất sắc 2026 — Vingroup Innovation Foundation]\n"
            "VinIF cấp học bổng toàn phần cho sinh viên đại học xuất sắc nghiên cứu AI/CNTT.\n"
            "Đối tượng: sinh viên năm 2, 3, 4 ngành CNTT, Khoa học dữ liệu, Điện tử.\n"
            "Điều kiện: GPA từ 3.5/4.0, không có môn thi lại.\n"
            "Giá trị: 40.000.000 VNĐ/năm + cơ hội thực tập tại VinAI.\n"
            "Yêu cầu hồ sơ: bảng điểm, thư giới thiệu của giảng viên, bài luận 1000 từ.\n"
            "Hạn nộp: 01/09/2026."
        ),
        "nguon": "mock",
    },
    {
        "title": "Thực tập sinh NLP Engineer",
        "company": "Coc Coc",
        "url": "https://careers.coccoc.com",
        "raw_text": (
            "[Thực tập sinh NLP Engineer — Coc Coc]\n"
            "Coc Coc tuyển intern cho nhóm NLP phát triển tính năng tìm kiếm tiếng Việt.\n"
            "Yêu cầu:\n"
            "- Sinh viên năm 3 hoặc năm 4 ngành CNTT\n"
            "- Python, hiểu embedding và transformer cơ bản\n"
            "- GPA từ 3.0/4.0\n"
            "Hình thức: online toàn thời gian.\n"
            "Hồ sơ: CV + link GitHub.\n"
            "Hạn: 25/08/2026."
        ),
        "nguon": "mock",
    },
    {
        "title": "Data Science Intern — MoMo",
        "company": "MoMo (M_Service)",
        "url": "https://www.momo.vn",
        "raw_text": (
            "[Data Science Intern — MoMo (M_Service)]\n"
            "MoMo tuyển Data Science Intern cho nhóm phân tích hành vi người dùng.\n"
            "Yêu cầu:\n"
            "- Sinh viên năm 2 trở lên, mọi ngành\n"
            "- Python (pandas, numpy), SQL\n"
            "- Ưu tiên biết thống kê và A/B testing\n"
            "Không yêu cầu GPA tối thiểu. Nhận mọi năm học.\n"
            "Hình thức: hybrid 3 ngày/tuần tại TP.HCM.\n"
            "Hồ sơ: CV.\n"
            "Hạn: 05/09/2026."
        ),
        "nguon": "mock",
    },
    {
        "title": "Thực tập sinh Computer Vision",
        "company": "VinAI Research",
        "url": "https://www.vinai.io/careers",
        "raw_text": (
            "[Thực tập sinh Computer Vision — VinAI Research]\n"
            "VinAI tuyển thực tập sinh CV để hỗ trợ dự án xe tự hành và nhận dạng ảnh y tế.\n"
            "Yêu cầu:\n"
            "- Sinh viên năm 3-4 hoặc thạc sĩ ngành CNTT, Điện tử, Toán ứng dụng\n"
            "- Python, OpenCV, PyTorch\n"
            "- GPA từ 3.5/4.0 — ĐIỀU KIỆN BẮT BUỘC\n"
            "- Ưu tiên có paper hoặc project CV thực tế\n"
            "Cam kết full-time 3 tháng, onsite Hà Nội.\n"
            "Hồ sơ: CV + bảng điểm + link project.\n"
            "Hạn: 12/08/2026."
        ),
        "nguon": "mock",
    },
    {
        "title": "MLOps Intern",
        "company": "Grab Vietnam",
        "url": "https://www.grab.careers",
        "raw_text": (
            "[MLOps Intern — Grab Vietnam]\n"
            "Grab tuyển MLOps intern để hỗ trợ team platform ML.\n"
            "Yêu cầu:\n"
            "- Sinh viên năm 3 trở lên ngành CNTT\n"
            "- Python, Docker, cơ bản về CI/CD\n"
            "- Ưu tiên biết Kubernetes hoặc Airflow\n"
            "Hình thức: hybrid, TP.HCM.\n"
            "Hồ sơ: CV + link GitHub.\n"
            "Hạn: 18/09/2026."
        ),
        "nguon": "mock",
    },
    {
        "title": "Học bổng Samsung Innovation Campus 2026",
        "company": "Samsung Electronics Vietnam",
        "url": "https://www.samsung.com/vn",
        "raw_text": (
            "[Học bổng Samsung Innovation Campus 2026 — Samsung Electronics Vietnam]\n"
            "Samsung cấp học bổng kèm khóa đào tạo AI cho sinh viên xuất sắc.\n"
            "Đối tượng: sinh viên năm 2, 3 ngành CNTT, Điện tử, Khoa học dữ liệu.\n"
            "Điều kiện: GPA từ 3.2/4.0.\n"
            "Giá trị: 20.000.000 VNĐ + khóa đào tạo AI 3 tháng + cơ hội tuyển dụng.\n"
            "Hồ sơ: CV + bảng điểm.\n"
            "Hạn nộp: 28/08/2026."
        ),
        "nguon": "mock",
    },
]


def crawl_mock() -> list[dict]:
    """Data mẫu: tên tổ chức có thật, nội dung tin là BỊA. Không cần API key."""
    print(f"\n[Mock] Dùng {len(MOCK_POSTINGS)} tin mẫu — tên tổ chức thật, "
          f"nội dung tin là bịa để test (không gọi API)...")
    return [dict(t) for t in MOCK_POSTINGS]


# ── gộp và ghi corpus ─────────────────────────────────────────────────────────

def _khoa_tin(t: dict) -> str:
    """Khoá nhận dạng một tin: tiêu đề + tổ chức, đã bỏ dấu.

    PHẢI ĐỌC ĐƯỢC CẢ HAI HÌNH DẠNG. Tin vừa crawl còn field `company`, nhưng tin
    đã nằm trong corpus thì KHÔNG — main() gọi `t.pop("company")` trước khi ghi.
    Chế độ --gop so tin mới với tin cũ, nên khoá phải khớp nhau ở cả hai phía;
    chỉ đọc `t["company"]` thì mọi tin cũ có khoá kết thúc bằng rỗng và không tin
    trùng nào bị bắt — corpus sẽ có hai bản của cùng một tin, ID khác nhau.

    Tin cũ vẫn giữ tổ chức ở dòng đầu raw_text, dạng "[tiêu đề — tổ chức]" do
    `_to_raw_text` sinh ra, nên moi ngược lại được. Tách bằng rsplit vì tiêu đề
    tuyển dụng có thể tự chứa dấu gạch; phần sau dấu gạch CUỐI mới là tổ chức.
    """
    cty = t.get("company")
    if cty is None:
        dong_dau = (t.get("raw_text") or "").split("\n", 1)[0].strip()
        if dong_dau.startswith("[") and dong_dau.endswith("]") and " — " in dong_dau:
            cty = dong_dau[1:-1].rsplit(" — ", 1)[1]
    return _kd(t.get("title", "") + (cty or ""))


def loai_trung(tin_list: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for t in tin_list:
        key = _khoa_tin(t)
        if key not in seen:
            seen.add(key)
            out.append(t)
    return out


def phan_loai_lai(preview: bool = False) -> None:
    """Áp lại luật phân loại lên tin REAL-* SẴN CÓ trong corpus. Không gọi mạng.

    VÌ SAO CẦN: `raw_text` của tin đã crawl nằm sẵn trong corpus.json, nên mỗi lần sửa
    `_kind`/`_cap_do`/`_lien_quan_ai` thì không có lý gì phải crawl lại — free tier chỉ
    có 100 search/tháng, một lần chạy đủ query đã tốn 12. Tách hàm này ra để sửa luật
    phân loại được kiểm ngay trên đúng data thật, không phải trả tiền để xem kết quả.

    Tin trượt `_lien_quan_ai` bị LOẠI KHỎI corpus và các tin còn lại được đánh số lại.
    Đây là chỗ duy nhất trong hệ thống được xoá tin — vì tin sai lĩnh vực không phải
    "cơ hội có thể học viên vẫn muốn", nó là rác từ đầu nguồn.
    """
    f = D / "corpus.json"
    d = json.loads(f.read_text(encoding="utf-8"))
    giu = [t for t in d["postings"] if not str(t.get("id", "")).startswith("REAL-")]
    real = [t for t in d["postings"] if str(t.get("id", "")).startswith("REAL-")]

    loai_bo, moi = [], []
    for t in real:
        if not _lien_quan_ai(t["title"], t["raw_text"]):
            loai_bo.append(t)
            continue
        cu = (t["kind"], tuple(t.get("cap_do") or []))
        t["kind"], t["cap_do"] = _phan_loai(t["title"], t["raw_text"])
        t["_doi"] = cu != (t["kind"], tuple(t["cap_do"]))
        moi.append(t)

    print(f"\n=== Phân loại lại {len(real)} tin REAL-* ===")
    if loai_bo:
        print(f"\nLOẠI {len(loai_bo)} tin sai lĩnh vực:")
        for t in loai_bo:
            print(f"  ✗ [{t['id']}] {t['title'][:60]}")
    print(f"\nGIỮ {len(moi)} tin (đánh số lại):")
    for i, t in enumerate(moi, start=1):
        cu_id = t["id"]
        t["id"] = f"REAL-{i:03d}"
        dau = "★" if t.pop("_doi") else " "
        print(f"  {dau} [{t['id']}] [{t['kind']:9}] [{'/'.join(t['cap_do']) or '-':22}] "
              f"{t['title'][:42]}"
              + (f"   (was {cu_id})" if cu_id != t["id"] else ""))
    print("  ★ = phân loại đã đổi so với corpus cũ")

    if preview:
        print("\n--preview: không ghi file.")
        return
    d["postings"] = giu + moi
    f.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✓ Đã ghi {f}\n  Tổng: {len(d['postings'])} tin "
          f"({len(giu)} OPP-* + {len(moi)} REAL-*)")


def main():
    parser = argparse.ArgumentParser(description="Crawler tin thực tập/học bổng thật")
    parser.add_argument("--preview", action="store_true",
                        help="In ra màn hình, không ghi file")
    parser.add_argument("--gioi-han", type=int, default=300,
                        help="Số tin thật tối đa (mặc định 300)")
    # `--so-trang` là tên cờ của bản phân trang song song (commit 56d806c) mà bản này
    # thay thế. Giữ làm bí danh vì đó là thứ DUY NHẤT bản kia có mà bản này không —
    # bỏ đi thì lệnh của ai đang chạy theo tên cũ gãy im lặng, đổi lấy đúng 0 lợi ích.
    parser.add_argument("--trang", "--so-trang", type=int, default=3, dest="trang",
                        help="Số trang đọc mỗi query (mặc định 3). MỖI TRANG TỐN 1 SEARCH: "
                             "tổng = số query × số trang. Free tier 100 search/tháng.")
    parser.add_argument("--ngan-sach", type=int, default=0,
                        help="Trần CỨNG số search SerpAPI được gọi (0 = không chặn). "
                             "Đặt bằng số search còn lại trong tháng để không vỡ quota.")
    parser.add_argument("--gop", action="store_true",
                        help="GỘP tin mới vào tin REAL-* sẵn có thay vì thay sạch. "
                             "Tin trùng (cùng tiêu đề + tổ chức) chỉ giữ bản cũ.")
    parser.add_argument("--mock", action="store_true",
                        help="Dùng data mẫu thay vì gọi API (không cần SERPAPI_KEY)")
    parser.add_argument("--bo-qua-kiem-url", action="store_true",
                        help="Không bấm thử link (chỉ dùng khi offline — corpus sẽ có link chưa kiểm)")
    parser.add_argument("--phan-loai-lai", action="store_true",
                        help="Chạy lại _kind/_cap_do/_lien_quan_ai trên tin REAL-* SẴN CÓ "
                             "trong corpus. Không gọi API, không tốn quota SerpAPI.")
    args = parser.parse_args()

    print(f"=== Crawler bắt đầu: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")

    if args.phan_loai_lai:
        return phan_loai_lai(args.preview)

    # --gop: nạp tin REAL-* sẵn có TRƯỚC khi crawl, để đưa khoá của chúng vào bộ
    # lọc trùng. Không làm vậy thì crawler tiêu quota vào đúng mấy tin đã nằm
    # trong corpus rồi mới vứt đi ở bước loai_trung() — trả tiền search cho thứ
    # mình đã có. `gioi_han` cũng phải trừ đi phần đã có, vì nó đếm TỔNG tin REAL
    # muốn có trong corpus chứ không phải số tin crawl thêm.
    cu_real: list[dict] = []
    corpus_path = D / "corpus.json"
    if args.gop and corpus_path.exists():
        try:
            cu = json.loads(corpus_path.read_text(encoding="utf-8"))["postings"]
            cu_real = [t for t in cu if str(t.get("id", "")).startswith("REAL-")]
        except (json.JSONDecodeError, KeyError) as e:
            print(f"  ⚠ corpus.json cũ đọc không được ({e}) — --gop bỏ qua, crawl mới.")

        # LỌC LẠI TIN CŨ BẰNG LUẬT HIỆN TẠI, không cho đi thẳng vào corpus.
        # `_lien_quan_ai` là luật KẾT NẠP của corpus, không phải một bước trong
        # đường ống crawl — tin sai lĩnh vực thì sai bất kể nó vào từ lần chạy nào.
        # Bản đầu của --gop cho tin cũ đi vòng qua đây, nên ba tin rác đã lọt từ
        # đợt crawl trước ("Intern - Tax", "Thực tập sinh Quản lý thiết kế",
        # "Supply Chain Analyst") được giữ nguyên: cùng một corpus mà tin cũ theo
        # luật cũ, tin mới theo luật mới. Sửa filter mà tin cũ không bị soi lại thì
        # sửa cũng bằng thừa.
        bo = [t for t in cu_real if not _lien_quan_ai(t["title"], t["raw_text"])]
        if bo:
            print(f"\n[Gộp] LOẠI {len(bo)} tin cũ không qua được luật lĩnh vực hiện tại:")
            for t in bo:
                print(f"  ✗ [{t['id']}] {t['title'][:60]}")
            cu_real = [t for t in cu_real if t not in bo]
    can_them = max(0, args.gioi_han - len(cu_real))
    if args.gop:
        print(f"[Gộp] Đã có {len(cu_real)} tin REAL-* → cần crawl thêm {can_them} "
              f"tin để đạt {args.gioi_han}.")

    if args.mock or not SERPAPI_KEY:
        if not SERPAPI_KEY and not args.mock:
            print("⚠ Chưa có SERPAPI_KEY → tự động dùng --mock mode")
            print("  Đặt SERPAPI_KEY=your_key vào codebase/.env để crawl tin thật")
            print("  Đăng ký miễn phí (100 search/tháng): https://serpapi.com/\n")
        tin_moi = crawl_mock()
    elif args.gop and can_them == 0:
        print("[Gộp] Đã đủ tin, không cần gọi API.")
        tin_moi = []
    else:
        print(f"Giới hạn: {args.gioi_han} tin thật | API: SerpAPI Google Jobs")
        tin_moi = crawl_google_jobs(
            can_them if args.gop else args.gioi_han, args.trang,
            ngan_sach=args.ngan_sach,
            da_co={_khoa_tin(t) for t in cu_real},
        )

    tin_moi = loai_trung(tin_moi)[: max(0, args.gioi_han - len(cu_real))]

    # Gộp tin cũ lên TRƯỚC tin mới rồi đánh số lại toàn bộ. Tin cũ giữ nguyên nội
    # dung (không crawl lại), chỉ đổi ID và được kiểm URL lại cùng lượt bên dưới —
    # link mục nào chết trong thời gian qua thì lần này bị xoá đúng như tin mới.
    if args.gop and cu_real:
        tin_moi = loai_trung(cu_real + tin_moi)

    # Chuẩn hóa format.
    #
    # `nguon`/`_nguon` và `_crawled_at`: tin VỪA crawl khai field `nguon`, tin lấy
    # lại từ corpus (--gop) đã đổi tên thành `_nguon` từ lần chạy trước. Ghi đè
    # thẳng như bản cũ thì mọi tin cũ thành `_nguon="unknown"` và `_crawled_at`
    # thành giờ hiện tại — tức là khai man rằng tin crawl từ tháng trước vừa được
    # lấy về lúc nãy. Đúng loại khẳng định không kiểm được mà hệ thống này tồn tại
    # để chặn, nên chỉ đặt khi tin THẬT SỰ mới.
    bay_gio = datetime.now().strftime("%Y-%m-%d %H:%M")
    for i, t in enumerate(tin_moi, start=1):
        t["id"] = f"REAL-{i:03d}"
        t["kind"], t["cap_do"] = _phan_loai(t["title"], t["raw_text"])
        if "nguon" in t or not t.get("_nguon"):
            t["_nguon"] = t.pop("nguon", "unknown")
            t["_crawled_at"] = bay_gio
        t.pop("nguon", None)
        t.setdefault("_crawled_at", bay_gio)
        t["url"] = t.get("url") or ""   # link gốc để user click
        t.setdefault("url_loai", "")
        t.pop("company", None)

    # Bấm thử từng link TRƯỚC khi ghi corpus — link chết bị xoá trắng.
    if args.bo_qua_kiem_url:
        print("\n[Kiểm URL] BỎ QUA (--bo-qua-kiem-url) — corpus sẽ có link chưa kiểm chứng.")
        for t in tin_moi:
            t["_url_status"] = "chua_kiem"
            t["url_loai"] = t["url_loai"] or _muc_url(t["url"])
    else:
        kiem_tat_ca(tin_moi)

    print(f"\n=== Kết quả: {len(tin_moi)} tin ===")
    for t in tin_moi:
        print(f"  [{t['id']}] [{t['kind']:9}] [{'/'.join(t['cap_do']) or '-':18}] "
              f"{t['title'][:45]}")

    if args.preview:
        print("\n--preview: không ghi file.")
        return

    # GIỮ LẠI TIN OPP-*, CHỈ THAY TIN REAL-*.
    # Bản cũ ghi đè sạch corpus.json, mà gen_corpus.py cũng ghi đè sạch chính file đó —
    # hai script đạp lên nhau. Chạy crawler là mất 40 tin OPP-* mà smoke_test và eval
    # dựa vào (đó là fixture bắn vào từng chỗ khó), và không có gì báo là vừa mất.
    # Hai lớp data phải sống chung: OPP-* là fixture kiểm thử, REAL-* là tin ngoài đời.
    giu = []
    if corpus_path.exists():
        try:
            cu = json.loads(corpus_path.read_text(encoding="utf-8"))["postings"]
            giu = [t for t in cu if not str(t.get("id", "")).startswith("REAL-")]
        except (json.JSONDecodeError, KeyError) as e:
            print(f"  ⚠ corpus.json cũ đọc không được ({e}) — ghi mới hoàn toàn.")
    if giu:
        print(f"\n[Gộp] Giữ {len(giu)} tin OPP-* sẵn có, thay {len(tin_moi)} tin REAL-*.")
    else:
        print("\n[Gộp] Chưa có tin OPP-* nào trong corpus — chạy data/gen_corpus.py "
              "để sinh 40 tin fixture cho smoke_test.")

    # Ghi chú phải nói ĐÚNG data này là gì. Bản cũ ghi "toàn bộ là tin thật mới nhất"
    # kể cả khi đang chạy mock — chính là kiểu khẳng định không kiểm được mà hệ thống
    # tồn tại để chống. Giờ nguồn và số link sống đều đếm từ data.
    n_mock = sum(1 for t in tin_moi if t["_nguon"] == "mock")
    n_ok = sum(1 for t in tin_moi if str(t["_url_status"]).startswith("ok"))
    n_chua = sum(1 for t in tin_moi if str(t["_url_status"]).startswith("khong_kiem_duoc"))
    n_chet = sum(1 for t in tin_moi if str(t["_url_status"]).startswith("chet"))
    n_tin = sum(1 for t in tin_moi if t["url_loai"] == "tin")
    nguon_mo_ta = (
        f"DATA MẪU ({n_mock} tin gõ tay trong crawler.py) — KHÔNG phải tin tuyển dụng thật, "
        f"nội dung là bịa để test. Đặt SERPAPI_KEY vào codebase/.env để crawl tin thật."
        if n_mock == len(tin_moi) else
        f"{len(tin_moi) - n_mock} tin crawl thật từ Google Jobs (SerpAPI)"
        + (f" + {n_mock} tin mẫu" if n_mock else "")
    )
    out = {
        "_ghi_chu": (
            f"Hai lớp data. OPP-* ({len(giu)} tin): fixture GIẢ tự sinh bằng gen_corpus.py "
            f"(seed=42), tên tổ chức bịa, dùng cho smoke_test/eval — crawler không đụng vào. "
            f"REAL-* ({len(tin_moi)} tin, crawl lúc {datetime.now().strftime('%Y-%m-%d %H:%M')}): "
            f"{nguon_mo_ta} "
            f"Link của REAL-*: {n_ok} bấm thử sống, {n_chua} trang chặn bot nên chưa xác "
            f"minh được (vẫn giữ link, UI ghi rõ), {n_chet} chết thật đã xoá trắng. "
            f"{n_tin}/{len(tin_moi)} link trỏ đúng tin"
            + (f", {len(tin_moi) - n_tin} chỉ tới trang tuyển dụng/trang chủ tổ chức"
               if n_tin < len(tin_moi) else "")
            + ". Không đoán link thay. Xem _url_status của từng tin."
        ),
        "postings": giu + tin_moi,
    }

    corpus_path.write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n✓ Đã ghi {corpus_path}")
    print(f"  Tổng: {len(out['postings'])} tin ({len(giu)} OPP-* + {len(tin_moi)} REAL-*)")
    tt = sum(1 for t in out["postings"] if t["kind"] == "thuc_tap")
    hb = sum(1 for t in out["postings"] if t["kind"] == "hoc_bong")
    print(f"  Thực tập: {tt} · Học bổng: {hb}")


if __name__ == "__main__":
    main()
