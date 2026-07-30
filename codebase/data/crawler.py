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


def _lien_quan_ai(title: str, desc: str) -> bool:
    txt = _kd(title + " " + desc)
    return any(k in txt for k in [
        "ai ", "machine learning", "data", "python", "nlp", "llm",
        "deep learning", "computer vision", "mlops", "analytics",
        "backend", "software", "cntt", "cong nghe", "ky thuat",
        "hoc bong", "scholarship", "intern", "thuc tap",
    ])


def _kind(title: str, desc: str) -> str:
    txt = _kd(title + " " + desc)
    if any(k in txt for k in ["hoc bong", "scholarship"]):
        return "hoc_bong"
    return "thuc_tap"


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

QUERIES = [
    "thực tập sinh AI intern Hà Nội",
    "thực tập sinh data analyst intern Hà Nội",
    "thực tập sinh machine learning intern TP HCM",
    "thực tập sinh NLP AI intern",
    "intern AI fresher data science Vietnam",
    "học bổng CNTT sinh viên 2026",
]


def _serpapi(params: dict) -> dict:
    """Gọi SerpAPI qua REST. Không dùng SDK `google-search-results` để bớt một
    dependency và một chỗ hỏng — endpoint này chỉ là GET trả JSON."""
    u = "https://serpapi.com/search.json?" + urlencode(params)
    req = urllib.request.Request(u, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=60, context=_CTX) as resp:
        return json.loads(resp.read())


def crawl_google_jobs(gioi_han: int = 50) -> list[dict]:
    """Dùng SerpAPI để tìm Google Jobs."""
    if not SERPAPI_KEY:
        print("  ✗ Chưa có SERPAPI_KEY. Đặt vào .env rồi chạy lại.")
        print("    Đăng ký miễn phí tại: https://serpapi.com/ (100 search/tháng)")
        return []

    print(f"\n[Google Jobs / SerpAPI] Đang crawl ({len(QUERIES)} queries)...")
    ket_qua = []
    seen_titles = set()

    for query in QUERIES:
        if len(ket_qua) >= gioi_han:
            break

        params = {
            "engine": "google_jobs",
            "q": query,
            "hl": "vi",
            "gl": "vn",
            "api_key": SERPAPI_KEY,
            "chips": "date_posted:month",  # chỉ tin trong 1 tháng gần đây
        }

        try:
            results = _serpapi(params)
        except Exception as e:
            print(f"  ✗ query '{query}': {type(e).__name__}: {str(e)[:80]}")
            continue

        # SerpAPI báo lỗi trong JSON (hết quota, key sai) chứ không phải HTTP 4xx.
        if results.get("error"):
            print(f"  ✗ query '{query}': SerpAPI báo lỗi — {results['error']}")
            if "run out" in results["error"].lower() or "quota" in results["error"].lower():
                print("    → Hết quota tháng. Dừng crawl, giữ nguyên tin đã lấy được.")
                break
            continue

        jobs = results.get("jobs_results", [])
        if not jobs:
            print(f"  query '{query}': 0 kết quả")
            continue

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
                continue

            key = _kd(title + company)
            if key in seen_titles:
                continue
            seen_titles.add(key)

            if not _lien_quan_ai(title, description):
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

        print(f"  '{query[:40]}': {len(jobs)} jobs → thêm {them} tin (tổng {len(ket_qua)})")
        time.sleep(0.5)  # SerpAPI không cần delay nhiều như crawl trực tiếp

    return ket_qua


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

def loai_trung(tin_list: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for t in tin_list:
        key = _kd(t["title"] + t.get("company", ""))
        if key not in seen:
            seen.add(key)
            out.append(t)
    return out


def main():
    parser = argparse.ArgumentParser(description="Crawler tin thực tập/học bổng thật")
    parser.add_argument("--preview", action="store_true",
                        help="In ra màn hình, không ghi file")
    parser.add_argument("--gioi-han", type=int, default=50,
                        help="Số tin thật tối đa (mặc định 50)")
    parser.add_argument("--mock", action="store_true",
                        help="Dùng data mẫu thay vì gọi API (không cần SERPAPI_KEY)")
    parser.add_argument("--bo-qua-kiem-url", action="store_true",
                        help="Không bấm thử link (chỉ dùng khi offline — corpus sẽ có link chưa kiểm)")
    args = parser.parse_args()

    print(f"=== Crawler bắt đầu: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")

    if args.mock or not SERPAPI_KEY:
        if not SERPAPI_KEY and not args.mock:
            print("⚠ Chưa có SERPAPI_KEY → tự động dùng --mock mode")
            print("  Đặt SERPAPI_KEY=your_key vào codebase/.env để crawl tin thật")
            print("  Đăng ký miễn phí (100 search/tháng): https://serpapi.com/\n")
        tin_moi = crawl_mock()
    else:
        print(f"Giới hạn: {args.gioi_han} tin thật | API: SerpAPI Google Jobs")
        tin_moi = crawl_google_jobs(args.gioi_han)

    tin_moi = loai_trung(tin_moi)[: args.gioi_han]

    # Chuẩn hóa format
    for i, t in enumerate(tin_moi, start=1):
        t["id"] = f"REAL-{i:03d}"
        t["kind"] = _kind(t["title"], t["raw_text"])
        t["_nguon"] = t.pop("nguon", "unknown")
        t["_crawled_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
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
        print(f"  [{t['id']}] [{t['kind']:9}] [{t['_nguon']:12}] {t['title'][:55]}")

    if args.preview:
        print("\n--preview: không ghi file.")
        return

    corpus_path = D / "corpus.json"

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
