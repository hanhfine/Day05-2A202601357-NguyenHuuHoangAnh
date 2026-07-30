"""Đọc CV → 8 field hồ sơ. BA LUẬT CỨNG, đừng ai sửa mà không đọc hết:

1. **Không ghi nội dung CV xuống đĩa.** Xử lý trong RAM rồi bỏ. Repo này đang PUBLIC —
   một file CV lọt vào repo là PII thật của người thật nằm trên internet.
2. **Redact trước khi gửi ra API.** Email / điện thoại / link / số CCCD bị thay bằng
   placeholder ngay tại máy, trước lời gọi mạng đầu tiên.
3. **Chỉ giữ 8 field** cần cho việc đối chiếu và xưng hô (tên · năm học · ngành · GPA ·
   thành phố · kỹ năng · project · có GitHub). Mọi thứ khác trong CV bị bỏ, không log.

Về field `ten` — đây là ngoại lệ CÓ CHỦ Ý của luật 3, quyết định ngày 2026-07-30:
trợ lý cần xưng hô được với học viên. Hai điều cần biết khi đánh giá lựa chọn này:
  · Tên VỐN ĐÃ đi ra API từ trước, vì redact() không bắt được tên người (xem đoạn
    "giới hạn" dưới đây). Thêm field này không mở đường rò mới.
  · Cái nó đổi: tên nằm trong hồ sơ gửi kèm MỌI lượt chat, không chỉ lượt đọc CV.
Email / SĐT / link / CCCD / địa chỉ VẪN bị chặn như cũ — chỉ mở đúng field tên.

Giới hạn phải nói thẳng: regex KHÔNG bắt được tên người. Bản redact vẫn có thể còn tên.
Vì vậy luật 1 và 3 mới là lớp bảo vệ chính, không phải luật 2.
"""
import re

from . import llm

RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
RE_PHONE = re.compile(r"(?:\+84|0)(?:[\s.-]?\d){8,10}\b")
RE_URL = re.compile(r"https?://\S+|(?:www|github\.com|linkedin\.com)/\S+", re.I)
RE_ID = re.compile(r"\b\d{9,12}\b")

# rút field khi không có API key (mode=mock)
RE_NAM = re.compile(r"(?:sinh viên|sv|năm thứ|năm)\s*([1-6])(?![0-9])", re.I)
RE_GPA = re.compile(r"(?:gpa|điểm trung bình|đtb)[^\d]{0,15}(\d[.,]\d{1,2})", re.I)
RE_CITY = re.compile(r"(hà nội|tp\.?\s?hcm|hồ chí minh|đà nẵng|huế|cần thơ)", re.I)
# Dò NHÃN "GitHub", không dò đường link — redact() đã thay link bằng [LINK] rồi mà
# nhãn thì còn nguyên ("GitHub: [LINK]"). Nhiều tin ghi "ưu tiên có GitHub/project",
# trước đây hồ sơ không có chỗ nào ghi nhận việc này nên học viên có GitHub vẫn bị
# báo là thiếu. Chỉ lưu true/false, không bao giờ lưu đường link.
RE_GITHUB = re.compile(r"github|gitlab|bitbucket", re.I)
RE_TEN_NHAN = re.compile(r"(?:họ và tên|họ tên|full\s?name|name)\s*[:\-]\s*([^\n]{2,40})", re.I)


def _ten(text: str) -> str | None:
    """Dò tên cho đường mock (không có API key). Không chắc thì trả None, không đoán bừa.

    Ưu tiên nhãn "Họ tên:". Không có nhãn thì tìm trong 15 dòng đầu một dòng ngắn gồm
    2-5 từ toàn chữ cái — kiểu dòng tên đứng riêng ở đầu CV. Dòng có chữ số hoặc dấu
    câu bị loại, nên câu văn thường không lọt vào.
    """
    m = RE_TEN_NHAN.search(text)
    if m:
        t = m.group(1).strip(" -–—:.")
        if 1 < len(t) <= 40:
            return t
    for dong in text.splitlines()[:15]:
        d = dong.strip()
        tu = d.split()
        if 1 < len(d) <= 40 and 2 <= len(tu) <= 5 \
                and all(re.fullmatch(r"[^\W\d_]{1,15}", x) for x in tu):
            return d
    return None
KY_NANG = ["Python", "SQL", "Excel", "pandas", "PyTorch", "TensorFlow", "Docker",
           "Java", "C++", "JavaScript", "LLM API", "OpenCV", "Git", "Power BI"]

SYSTEM = """Bạn rút thông tin từ một CV đã được ẩn thông tin liên hệ.

Trả về DUY NHẤT JSON:
{"ten": str|null, "nam_hoc": int|null, "nganh": str|null, "gpa": number|null,
 "thanh_pho": str|null, "ky_nang": [str], "project": str|null, "co_github": true|false}

LUẬT:
- CV không ghi rõ field nào thì để null / mảng rỗng. TUYỆT ĐỐI không suy đoán.
  Không có GPA thì là null — đừng ước lượng từ học lực.
- `ten` là họ tên của ứng viên, chép đúng như CV ghi. CV không ghi tên rõ ràng thì
  null — không lấy tên người tham chiếu, tên giảng viên hay tên công ty thay vào.
- KHÔNG trả về email, số điện thoại, link, địa chỉ, số CCCD, tên trường dù chúng có
  xuất hiện. Chỉ 8 field trên.
- `gpa` quy về thang 4. CV ghi thang 10 thì chia 2.5 và làm tròn 2 số.
- `ky_nang` là tên công nghệ/kỹ năng cụ thể, tối đa 10 mục.
- `co_github` = true nếu CV có nhắc tới GitHub/GitLab/portfolio code, KỂ CẢ khi
  đường link đã bị thay bằng [LINK]. Đây chỉ là cờ true/false — TUYỆT ĐỐI không
  chép lại đường link vào bất kỳ field nào."""


def redact(text: str) -> tuple[str, dict]:
    """Thay PII bằng placeholder. Trả (text đã redact, số lượt thay từng loại)."""
    dem = {}
    for ten, pat, the in (("email", RE_EMAIL, "[EMAIL]"), ("link", RE_URL, "[LINK]"),
                          ("điện thoại", RE_PHONE, "[PHONE]"), ("số giấy tờ", RE_ID, "[ID]")):
        text, n = pat.subn(the, text)
        if n:
            dem[ten] = n
    return text, dem


def doc_file(ten: str, du_lieu: bytes) -> str:
    """Lấy text từ file upload. KHÔNG lưu file. Hỗ trợ .txt/.md/.pdf/.docx."""
    thap = ten.lower()
    if thap.endswith(".pdf"):
        try:
            import io

            from pypdf import PdfReader
        except ImportError as e:
            raise RuntimeError("Đọc PDF cần: pip install pypdf. "
                               "Hoặc dán text CV vào ô bên dưới.") from e
        return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(du_lieu)).pages)
    if thap.endswith(".docx"):
        try:
            import io
            import zipfile
            with zipfile.ZipFile(io.BytesIO(du_lieu)) as z:
                xml = z.read("word/document.xml").decode("utf-8", "ignore")
            return re.sub(r"<[^>]+>", " ", xml.replace("</w:p>", "\n"))
        except Exception as e:                      # noqa: BLE001
            raise RuntimeError(f"Không đọc được .docx: {e}. Dán text CV vào ô bên dưới.") from e
    return du_lieu.decode("utf-8", "ignore")


def _mock(text: str) -> dict:
    n, g, c = RE_NAM.search(text), RE_GPA.search(text), RE_CITY.search(text)
    gpa = float(g.group(1).replace(",", ".")) if g else None
    if gpa and gpa > 4:                      # CV ghi thang 10
        gpa = round(gpa / 2.5, 2)
    thap = text.lower()
    return {"ten": _ten(text),
            "nam_hoc": int(n.group(1)) if n else None,
            "nganh": None, "gpa": gpa, "thanh_pho": c.group(1) if c else None,
            "ky_nang": [k for k in KY_NANG if k.lower() in thap][:10], "project": None,
            "co_github": bool(RE_GITHUB.search(text))}


def trich_ho_so(text: str, mode: str = "real") -> dict:
    """CV text → 6 field. Trả kèm `_redact` để UI nói cho user biết đã ẩn những gì."""
    sach, dem = redact(text)
    if mode == "real" and llm.co_key():
        try:
            o = llm.json_call(SYSTEM, sach[:12000], nhan="cv")
        except Exception:                          # noqa: BLE001 — hỏng thì vẫn còn mock
            o = _mock(sach)
    else:
        o = _mock(sach)

    ky_nang = [str(x) for x in (o.get("ky_nang") or [])][:10]
    gpa = o.get("gpa")
    # Chốt lại co_github bằng regex trên bản đã redact: model có thể quên field này,
    # mà nhãn "GitHub" thì luôn còn trong text. Chỉ nâng lên true, không hạ xuống false.
    co_git = bool(o.get("co_github")) or bool(RE_GITHUB.search(sach))
    ten = str(o.get("ten")).strip() if o.get("ten") else None
    return {"ten": ten if ten and len(ten) <= 60 else None,
            "nam_hoc": o.get("nam_hoc") if isinstance(o.get("nam_hoc"), int) else None,
            "nganh": o.get("nganh") or None,
            "gpa": float(gpa) if isinstance(gpa, (int, float)) else None,
            "thanh_pho": o.get("thanh_pho") or None,
            "ky_nang": ky_nang, "project": o.get("project") or None,
            "co_github": co_git,
            "_redact": dem, "_so_ky_tu": len(text)}
