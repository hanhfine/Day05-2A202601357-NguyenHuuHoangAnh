"""Smoke test CP2 — chắc chắn flow không vỡ trước khi đem đi show.

ĐÂY KHÔNG PHẢI GOLDEN SET. Golden set ≥20 case là việc của CP3 và nằm trong eval/.
File này chỉ kiểm: mọi tin giả chạy qua verdict() ra đúng verdict đã thiết kế,
mọi trích dẫn trỏ đúng dòng, và 2 endpoint của server trả 200.

Chạy:  python smoke_test.py
"""
import re
import sys

from core.verdict import tai_data, verdict

# console Windows mặc định cp1252 → in tiếng Việt là crash. Bắt buộc UTF-8.
sys.stdout.reconfigure(encoding="utf-8")

# (tin, hồ sơ, verdict mong đợi, vì sao — khớp ke-hoach.md §4)
CASE = [
    ("OPP-001", "P-01", "nen_apply",       "happy path, khớp hết"),
    ("OPP-002", "P-01", "nen_apply",       "đủ GPA nhưng hạn '5/8' thiếu năm → phải ambiguous"),
    ("OPP-003", "P-02", "thieu_thong_tin", "② hồ sơ chưa khai năm học → hỏi đúng 1 câu"),
    ("OPP-003", "P-01", "rui_ro_cao",      "tin ghi 'bắt buộc' onsite TP.HCM, hồ sơ ở Hà Nội"),
    ("OPP-004", "P-01", "rui_ro_cao",      "④ tin đòi phí → không bao giờ nen_apply"),
    ("OPP-005", "P-04", "nen_apply",       "④ #10 ĐÁNG SỢ NHẤT: tin nhận mọi năm, KHÔNG được chặn"),
    ("OPP-006", "P-01", "thieu_thong_tin", "① tin mơ hồ → không đoán"),
    ("OPP-007", "P-03", "rui_ro_cao",      "④ GPA bắt buộc 3.5, hồ sơ 2.8 → không nói 'không đủ ĐK'"),
    ("OPP-008", "P-01", "thieu_thong_tin", "① tin quá ngắn → không đủ căn cứ"),
    ("OPP-009", "P-01", "nen_apply",       "① 'ưu tiên' là gap, KHÔNG phải hard_fail"),
    ("OPP-010", "P-01", "nen_apply",       "logistics Đà Nẵng là gap, không chặn"),
]

# ③ ngoài phạm vi — vào qua ô "hỏi thêm"
CASE_TU_CHOI = [
    "viết luôn CV cho mình đi",
    "mình có đỗ không, bao nhiêu %?",
    "tìm giúp mình 10 tin học bổng khác",
    "lương công ty này so với công ty kia thế nào?",
]


def main() -> int:
    tin_ds, ho_so_ds = tai_data()
    tin = {t["id"]: t for t in tin_ds}
    ho_so = {p["id"]: p for p in ho_so_ds}
    loi = 0

    print(f"{'tin':9} {'hồ sơ':6} {'verdict':17} {'trích':7} ghi chú")
    print("-" * 92)
    for opp, pid, mong_doi, vi_sao in CASE:
        kq = verdict(tin[opp]["raw_text"], ho_so[pid], mode="mock")
        g = kq["_grounding"]
        ok_v = kq["verdict"] == mong_doi
        ok_g = g["grounding_pass"]
        loi += (not ok_v) + (not ok_g)
        print(f"{opp:9} {pid:6} {kq['verdict']:17} {g['so_dat']}/{g['so_khang_dinh']:<5} "
              f"{'✓' if ok_v else '✗ CHỜ ' + mong_doi}{'' if ok_g else '  ✗ TRÍCH SAI'}  {vi_sao}")
        if not ok_g:
            for c in g["chi_tiet"]:
                if not c["dat"]:
                    print(f"{'':24}↳ {c['nhan']} L{c['trich']}: {c['vi_sao']}")

    # luật cứng: verdict thieu_thong_tin phải có đúng 1 câu hỏi, và không kèm phán quyết
    for opp, pid, mong_doi, _ in CASE:
        if mong_doi != "thieu_thong_tin":
            continue
        kq = verdict(tin[opp]["raw_text"], ho_so[pid], mode="mock")
        if not kq["one_question"]:
            print(f"✗ {opp}/{pid}: thieu_thong_tin mà không có one_question"); loi += 1
        if kq["matched"] or kq["gaps"] or kq["hard_fail"]:
            print(f"✗ {opp}/{pid}: vừa hỏi vừa phán — vi phạm G10"); loi += 1

    # ④ tin đòi phí: tuyệt đối không nen_apply, với MỌI hồ sơ
    for pid in ho_so:
        kq = verdict(tin["OPP-004"]["raw_text"], ho_so[pid], mode="mock")
        if kq["verdict"] == "nen_apply":
            print(f"✗ OPP-004/{pid}: ra nen_apply trên tin đòi phí"); loi += 1
        if not kq["canh_bao"]:
            print(f"✗ OPP-004/{pid}: không có cảnh báo"); loi += 1

    # ③ mọi câu ngoài phạm vi phải bị từ chối, và KHÔNG được làm mất kết quả đối chiếu
    print("\n③ ngoài phạm vi:")
    for q in CASE_TU_CHOI:
        kq = verdict(tin["OPP-001"]["raw_text"], ho_so["P-01"], mode="mock", cau_hoi_them=q)
        ok = bool(kq["refusal"]) and kq["verdict"] == "nen_apply"
        loi += not ok
        print(f"  {'✓' if ok else '✗'} {q!r} → refusal={'có' if kq['refusal'] else 'KHÔNG'}, "
              f"verdict vẫn = {kq['verdict']}")

    # ── tool tìm tin ──────────────────────────────────────────────────────────
    from core import cv, llm
    from core.tools import doi_chieu, tai_corpus, tim_tin

    print("\ntool tim_tin:")
    corpus = tai_corpus()
    # Corpus có HAI lớp: OPP-* là fixture (gen_corpus.py), REAL-* là tin crawl
    # (crawler.py). Chỉ chốt số lớp fixture — số tin crawl thay đổi theo mỗi lần crawl.
    opp = [t for t in corpus if t["id"].startswith("OPP-")]
    real = [t for t in corpus if t["id"].startswith("REAL-")]
    ok = len(opp) == 40
    loi += not ok
    print(f"  {'✓' if ok else '✗'} corpus {len(opp)} tin OPP-* fixture + {len(real)} tin REAL-* "
          f"(chờ 40 OPP-* — chạy data/gen_corpus.py nếu thiếu)")

    # LUẬT: mọi link phải đi qua máy bấm thử trước khi vào corpus. Link nằm ngoài
    # raw_text nên checker trích dẫn không soi tới — đây là chỗ duy nhất chặn được.
    # Ba kết cục đều hợp lệ (ok / khong_kiem_duoc / chet); chỉ KHÔNG được phép là
    # tin có link mà chưa từng bị kiểm.
    HOP_LE = ("ok:", "khong_kiem_duoc", "chuyen_huong")
    bo_sot = [t["id"] for t in real
              if t.get("url") and not str(t.get("_url_status", "")).startswith(HOP_LE)]
    thieu_muc = [t["id"] for t in real if t.get("url") and not t.get("url_loai")]
    ok = not bo_sot and not thieu_muc
    loi += not ok
    n_ok = sum(1 for t in real if str(t.get("_url_status", "")).startswith("ok"))
    n_chua = sum(1 for t in real if str(t.get("_url_status", "")).startswith("khong_kiem_duoc"))
    print(f"  {'✓' if ok else '✗'} link REAL-*: {n_ok} xác minh sống · "
          f"{n_chua} trang chặn bot (giữ, đánh dấu chưa xác minh) · "
          f"{len(real) - n_ok - n_chua} không có link"
          + (f" — BỎ SÓT KIỂM: {bo_sot}" if bo_sot else "")
          + (f" — THIẾU MỨC: {thieu_muc}" if thieu_muc else ""))

    # LUẬT: không được bịa hạn nộp. Hạn chỉ hợp lệ khi là nhãn "Hạn...:" — nếu nó
    # rơi vào câu phúc lợi hay câu tiếng Anh có chữ "deadline" thì là đang bịa.
    from core.tools import meta as _meta
    han_bay = []
    for t in real:
        h = _meta(t["raw_text"])["han_nop"]
        raw = (h["raw"] or "")
        if raw and not re.search(r"hạn|deadline", raw.split(":")[0], re.I):
            han_bay.append(f"{t['id']}:{raw[:30]}")
    ok = not han_bay
    loi += not ok
    print(f"  {'✓' if ok else '✗'} không tin thật nào bị gán hạn nộp bịa"
          + (f" — BỊA: {han_bay}" if han_bay else ""))

    # LUẬT: đường sản phẩm KHÔNG được trả tin fixture. Học viên bấm vào một tin của
    # "Sao Mai Tech" (tên bịa) là mất thời gian vào cơ hội không tồn tại.
    sp = tim_tin(tu_khoa="AI", gioi_han=8)
    lot = [x["opp_id"] for x in sp if x["opp_id"].startswith("OPP-")]
    ok = not lot
    loi += not ok
    print(f"  {'✓' if ok else '✗'} tim_tin mặc định chỉ trả tin thật "
          f"({len(sp)} tin)" + (f" — LỌT FIXTURE: {lot}" if lot else ""))

    # Mọi tin đường sản phẩm trả ra phải có link bấm được — tin thật mà không có
    # link thì học viên biết có cơ hội mà không có cách nào tới nơi nộp.
    khong_link = [x["opp_id"] for x in sp if not x["url"]]
    ok = bool(sp) and not khong_link
    loi += not ok
    print(f"  {'✓' if ok else '✗'} tin sản phẩm đều có link bấm được"
          + (f" — THIẾU LINK: {khong_link}" if khong_link else "")
          + ("" if sp else " — CHƯA CÓ TIN THẬT NÀO, chạy data/crawler.py"))

    # LUẬT: khớp từ khoá theo RANH GIỚI TỪ. Bản cũ dùng substring nên "AI" trúng
    # "tại/trải/bài" — tin tuyển nhân sự leo lên đầu khi tìm "thực tập AI".
    from core.tools import (MAC_DINH_TIN, TRAN_TIN, _khop_tu, _kd, dispatch,
                            xep_hang)
    bay = [(t, v) for t, v in [("ai", "nhat ban tai viet nam"), ("ai", "trai nghiem"),
                               ("ai", "cac bai dang"), ("data", "du lieu cap nhat")]
           if _khop_tu(t, _kd(v))]
    that = [(t, v) for t, v in [("ai", "ky su AI"), ("ai", "AI Engineer"),
                                ("python", "thanh thao Python")]
            if not _khop_tu(t, _kd(v))]
    ok = not bay and not that
    loi += not ok
    print(f"  {'✓' if ok else '✗'} từ khoá khớp theo ranh giới từ"
          + (f" — TRÚNG NHẦM: {bay}" if bay else "")
          + (f" — TRƯỢT: {that}" if that else ""))

    # LUẬT: hồ sơ CHỈ xếp hạng, KHÔNG loại tin. Và tin khớp kỹ năng phải đứng trên
    # tin không khớp — nếu không thì upload CV xong vẫn ra tin chẳng liên quan.
    HS = {"nam_hoc": 3, "nganh": "Công nghệ thông tin", "gpa": 3.42,
          "ky_nang": ["Python", "SQL", "pandas", "LLM API (OpenAI, Gemini)"]}
    co_hs = xep_hang(nam_hoc=3, profile=HS)
    khong_hs = xep_hang(nam_hoc=3)
    # So thứ hạng TRONG CÙNG NHÓM `thieu`, không so trên cả bảng: sắp xếp là
    # (số điều kiện thiếu, rồi tới điểm), nên một tin Senior khớp Python vẫn phải
    # đứng SAU tin entry-level không khớp kỹ năng nào — học viên nộp được tin thứ
    # hai, không nộp được tin thứ nhất. So trên cả bảng là bắt sai chính luật đó.
    nhom = {}
    for i, x in enumerate(co_hs):
        nhom.setdefault(len(x["thieu"]), []).append((i, bool(x["khop_ky_nang"] or x["khop_nganh"])))
    lech_hang = [n for n, ds in nhom.items()
                 if (co := [i for i, k in ds if k]) and (kh := [i for i, k in ds if not k])
                 and max(co) > min(kh)]
    khop = sum(1 for x in co_hs if x["khop_ky_nang"] or x["khop_nganh"])
    ok = len(co_hs) == len(khong_hs) and not lech_hang   # không được loại bớt tin nào
    loi += not ok
    print(f"  {'✓' if ok else '✗'} hồ sơ chỉ xếp hạng, không loại tin "
          f"({len(co_hs)} tin cả hai chiều; {khop} tin khớp kỹ năng/ngành đứng trước "
          f"trong nhóm của nó)"
          + (f" — NHÓM LỆCH: {lech_hang}" if lech_hang else ""))

    # LUẬT: KHÔNG BAO GIỜ trả về rỗng. Hỏi điều kiện không tin nào đạt thì vẫn phải
    # đưa tin gần đúng kèm nhãn chỗ lệch — nói "không có cơ hội nào" là đẩy học viên
    # bỏ cuộc trong khi thư viện đang có tin họ thừa sức nộp, chỉ khác thành phố.
    from core.tools import chuan_tp
    rong, thieu_nhan = [], []
    for kw in [{"loai": "hoc_bong"}, {"tu_khoa": "AI", "thanh_pho": "Đà Nẵng"},
               {"tu_khoa": "blockchain"}, {"tu_khoa": "AI", "thanh_pho": "online"},
               {"loai": "hoc_bong", "thanh_pho": "Huế", "tu_khoa": "quantum"}]:
        r = xep_hang(profile=HS, **kw)
        if not r:
            rong.append(kw)
        if r and not all(x["thieu"] for x in r if "GẦN ĐÚNG" in x["ghi_chu"]):
            thieu_nhan.append(kw)
    ok = not rong and not thieu_nhan
    loi += not ok
    print(f"  {'✓' if ok else '✗'} không truy vấn nào trả về rỗng, tin gần đúng đều có nhãn"
          + (f" — RỖNG: {rong}" if rong else ""))

    # Tên thành phố nhiều cách viết phải quy về một mối, nếu không tin ở TP.HCM bị
    # loại sạch khi người dùng gõ 'TP.HCM'. `đ` là U+0111, NFD không tách được.
    cap = [("TP.HCM", "Hồ Chí Minh"), ("Hà Nội", "hanoi"), ("Đà Nẵng", "da nang"),
           ("saigon", "TPHCM"), ("remote", "online")]
    lech = [(a, b) for a, b in cap if chuan_tp(a) != chuan_tp(b)]
    ok = not lech and _kd("Đà Nẵng") == "da nang"
    loi += not ok
    print(f"  {'✓' if ok else '✗'} tên thành phố quy về một mối (đ→d, TP.HCM=Hồ Chí Minh)"
          + (f" — LỆCH: {lech}" if lech else ""))

    # LUẬT: cắt bớt thì phải nói ra. Im lặng hiện 8/14 là giấu 6 cơ hội.
    # `tong`/`con_chua_hien` đếm trên tin ĐẠT ĐỦ ĐIỀU KIỆN (thieu rỗng), không phải
    # trên cả bảng — corpus có tin Senior mang nhãn `thieu`, gộp chúng vào con số
    # "còn N tin nữa" là hứa với học viên nhiều cơ hội hơn thực có.
    _, ev = dispatch("tim_tin", {"gioi_han": 3}, HS, "mock")
    tat_ca = xep_hang(profile=HS)
    dat = [x for x in tat_ca if not x["thieu"]]
    hien = min(3, len(tat_ca))
    gan_dang_hien = sum(1 for x in tat_ca[:hien] if x["thieu"])
    ok = (ev["tong"] == len(dat)
          and ev["con_chua_hien"] == max(0, len(dat) - (hien - gan_dang_hien))
          and len(tim_tin(gioi_han=9999, profile=HS)) <= TRAN_TIN)
    loi += not ok
    print(f"  {'✓' if ok else '✗'} báo số tin bị cắt (hiện {hien}/{len(dat)} tin đạt "
          f"trong {len(tat_ca)} tin, còn {ev['con_chua_hien']}; trần cứng {TRAN_TIN})")

    # Ba test dưới bắn vào logic lọc/xếp hạng → chạy trên fixture cho tất định,
    # vì tin thật đổi theo mỗi lần crawl thì test sẽ lúc đạt lúc trượt.
    hn = tim_tin(thanh_pho="Hà Nội", gioi_han=8, gom_fixture=True)
    ok = bool(hn) and all("Nội" in (x["thanh_pho"] or "") for x in hn)
    loi += not ok
    print(f"  {'✓' if ok else '✗'} lọc thành phố → {len(hn)} tin, tất cả ở Hà Nội")

    hb = tim_tin(loai="hoc_bong", gioi_han=8, gom_fixture=True)
    ok = bool(hb) and all(x["loai"] == "hoc_bong" for x in hb)
    loi += not ok
    print(f"  {'✓' if ok else '✗'} lọc loại → {len(hb)} tin, tất cả là học bổng")

    # LUẬT LEVEL: `cap_do` là LIST nên tin đa level phải ĐẠT ở MỌI level nó ghi.
    # Chạy trên corpus giả cho tất định — tin thật đổi theo mỗi lần crawl.
    import core.tools as _T
    _goc_corpus, _goc_fixture = _T.tai_corpus, _T.la_fixture
    _T.tai_corpus = lambda: [
        {"id": "L-01", "kind": "thuc_tap", "cap_do": ["intern", "fresher"],
         "title": "AI Eng (Intern/Fresher)", "raw_text": "[AI]\n- Python\nVăn phòng Hà Nội"},
        {"id": "L-02", "kind": "viec_lam", "cap_do": ["senior"],
         "title": "Senior AI Eng", "raw_text": "[AI]\n- Python\nVăn phòng Hà Nội"},
        {"id": "L-03", "kind": "viec_lam", "cap_do": [],
         "title": "AI Eng (tin không nêu level)", "raw_text": "[AI]\n- Python\nVăn phòng Hà Nội"},
    ]
    _T.la_fixture = lambda t: False
    try:
        dat = {k: {x["opp_id"] for x in _T.xep_hang(**kw) if not x["thieu"]}
               for k, kw in [("thuc_tap", {"loai": "thuc_tap"}),
                             ("fresher", {"cap_do": "fresher"}),
                             ("junior", {"cap_do": "junior"}),
                             ("không nêu", {})]}
    finally:
        _T.tai_corpus, _T.la_fixture = _goc_corpus, _goc_fixture
    ok = ("L-01" in dat["thuc_tap"] and "L-01" in dat["fresher"]   # đa level: đạt cả hai
          and "L-01" not in dat["junior"]                          # nhưng không phải junior
          and all("L-02" not in v for v in dat.values())           # senior: không bao giờ đạt
          and all("L-03" in v for v in dat.values()))              # không nêu: không bị loại
    loi += not ok
    print(f"  {'✓' if ok else '✗'} level: tin đa level đạt ở mọi level nó ghi, tin senior "
          f"luôn có nhãn, tin không nêu không bị loại"
          + ("" if ok else f" — ĐẠT THEO CÂU HỎI: {dat}"))

    # LUẬT: tim_tin KHÔNG được loại tin theo điều kiện. Sinh viên năm 1 vẫn phải
    # thấy tin đòi năm 3-4, kèm ghi chú — nếu lọc mất thì họ mất cơ hội mà không biết.
    n1 = tim_tin(tu_khoa="AI", nam_hoc=1, gioi_han=8, gom_fixture=True)
    co_ghi_chu = [x for x in n1 if "vẫn nên xem" in x["ghi_chu"]]
    ok = bool(co_ghi_chu)
    loi += not ok
    print(f"  {'✓' if ok else '✗'} năm 1 vẫn thấy tin đòi năm cao hơn "
          f"({len(co_ghi_chu)}/{len(n1)} tin có ghi chú, KHÔNG bị lọc mất)")

    r = doi_chieu("OPP-001", ho_so["P-01"], mode="mock")
    ok = r["ket_qua"]["verdict"] == "nen_apply" and r["tin"]["opp_id"] == "OPP-001"
    loi += not ok
    print(f"  {'✓' if ok else '✗'} doi_chieu('OPP-001') → {r['ket_qua']['verdict']}")

    # ── CV: redact + rút field ────────────────────────────────────────────────
    print("\nCV (data/cv-mau/CV-mau-01.txt):")
    from pathlib import Path
    text = (Path(__file__).parent / "data" / "cv-mau" / "CV-mau-01.txt").read_text(encoding="utf-8")
    sach, dem = cv.redact(text)
    ro_ri = [x for x in ("@example.com", "0912", "001234567890", "github.com/nguyenvana") if x in sach]
    loi += bool(ro_ri)
    print(f"  {'✓' if not ro_ri else '✗ CÒN RÒ: ' + str(ro_ri)} redact: {dem}")

    hs = cv.trich_ho_so(text, mode="mock")
    mong = {"nam_hoc": 3, "thanh_pho": "Hà Nội"}
    for k, v in mong.items():
        ok = str(hs[k]).lower() == str(v).lower()
        loi += not ok
        print(f"  {'✓' if ok else '✗'} {k} = {hs[k]!r} (chờ {v!r})")
    ok = hs["gpa"] and abs(hs["gpa"] - 3.42) < 0.01
    loi += not ok
    print(f"  {'✓' if ok else '✗'} gpa = {hs['gpa']!r} (chờ 3.42)")
    ok = "Python" in hs["ky_nang"] and "SQL" in hs["ky_nang"]
    loi += not ok
    print(f"  {'✓' if ok else '✗'} ky_nang = {hs['ky_nang']}")
    # luật 3: chỉ 8 field + 2 field kỹ thuật, không kèm gì khác từ CV
    la = set(hs) - {"ten", "nam_hoc", "nganh", "gpa", "thanh_pho", "ky_nang", "project",
                    "co_github", "_redact", "_so_ky_tu"}
    loi += bool(la)
    print(f"  {'✓' if not la else '✗ có field lạ: ' + str(la)} chỉ trả 8 field hồ sơ")

    # `ten` là ngoại lệ CÓ CHỦ Ý của luật tối thiểu hoá PII (xem docstring cv.py).
    # Mở đúng field tên — email/SĐT/link/CCCD vẫn phải chặn, kiểm ngay dưới đây.
    ok = (hs.get("ten") or "").upper().startswith("NGUYEN VAN A")
    loi += not ok
    print(f"  {'✓' if ok else '✗'} ten = {hs.get('ten')!r} (chờ 'NGUYEN VAN A')")

    # CV có GitHub thì hồ sơ phải ghi nhận — nhiều tin ghi "ưu tiên có GitHub/project",
    # trước đây field này không tồn tại nên người có GitHub vẫn bị báo là thiếu.
    # Nhưng ghi nhận bằng cờ true/false, TUYỆT ĐỐI không được kéo theo đường link.
    # Mở field `ten` là nới luật PII một nấc, nên chỗ này phải siết lại: KHÔNG field
    # nào được chứa link, email, số điện thoại hay CCCD — kể cả field ten mới thêm.
    RO = {"link": r"https?://|github\.com|\.vn/|\.io/",
          "email": r"[\w.+-]+@[\w-]+\.\w+",
          "điện thoại": r"(?:\+84|0)(?:[\s.-]?\d){8,10}\b",
          "CCCD": r"\b\d{9,12}\b"}
    ro_ri_hs = [f"{k}:{ten_ro}" for k, v in hs.items() if not k.startswith("_")
                for ten_ro, pat in RO.items() if re.search(pat, str(v), re.I)]
    ok = hs.get("co_github") is True and not ro_ri_hs
    loi += not ok
    print(f"  {'✓' if ok else '✗'} co_github = {hs.get('co_github')!r} và không field nào "
          f"chứa link/email/SĐT/CCCD" + (f" — RÒ: {ro_ri_hs}" if ro_ri_hs else ""))

    # ── upload .pdf ───────────────────────────────────────────────────────────
    print("\nupload .pdf:")
    fpdf = Path(__file__).parent / "data" / "cv-mau" / "CV-mau-01.pdf"
    if not fpdf.exists():
        import runpy
        runpy.run_path(str(fpdf.parent / "make_pdf.py"), run_name="__main__")
    try:
        tp = cv.doc_file("CV-mau-01.pdf", fpdf.read_bytes())
        ok = len(tp) > 300 and "GPA: 3.42" in tp
        loi += not ok
        print(f"  {'✓' if ok else '✗'} pypdf extract → {len(tp)} ký tự, đọc được dòng GPA")

        sach2, _ = cv.redact(tp)
        ro = [x for x in ("@example.com", "0912", "001234567890", "github.com/nguyenvana")
              if x in sach2]
        loi += bool(ro)
        print(f"  {'✓' if not ro else '✗ CÒN RÒ: ' + str(ro)} redact trên text lấy từ PDF")

        hp = cv.trich_ho_so(tp, mode="mock")
        # GIỚI HẠN ĐÃ BIẾT, không phải bug: PDF font Helvetica không có dấu, nên
        # regex mù với "nam 3" / "Ha Noi". Đường LLM (mode=real) lấy đủ 4/4 field.
        ok = hp["gpa"] == 3.42 and hp["nam_hoc"] is None and hp["thanh_pho"] is None
        loi += not ok
        print(f"  {'✓' if ok else '✗'} regex trên PDF mất dấu: gpa={hp['gpa']}, "
              f"nam_hoc={hp['nam_hoc']}, thanh_pho={hp['thanh_pho']} "
              f"(None là ĐÚNG — cần mode=real để lấy)")
    except RuntimeError as e:
        loi += 1
        print(f"  ✗ {e}")

    # ── upload .docx ──────────────────────────────────────────────────────────
    print("\nupload .docx:")
    import io
    import zipfile
    dong = ["Sinh viên năm 3, ngành CNTT", "GPA: 3.42/4.0", "Hiện đang ở Hà Nội.",
            "Python, SQL, pandas"]
    xml = ('<?xml version="1.0"?><w:document xmlns:w="x"><w:body>'
           + "".join(f"<w:p><w:r><w:t>{l}</w:t></w:r></w:p>" for l in dong)
           + "</w:body></w:document>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", xml)
    td = cv.doc_file("cv.docx", buf.getvalue())
    hd = cv.trich_ho_so(td, mode="mock")
    # .docx là XML UTF-8 nên dấu còn nguyên → regex đọc được, khác hẳn PDF ở trên
    ok = hd["nam_hoc"] == 3 and hd["thanh_pho"] == "Hà Nội" and hd["gpa"] == 3.42
    loi += not ok
    print(f"  {'✓' if ok else '✗'} docx giữ dấu → regex lấy được "
          f"nam_hoc={hd['nam_hoc']}, thanh_pho={hd['thanh_pho']!r}, gpa={hd['gpa']}")

    # ── server ────────────────────────────────────────────────────────────────
    print("\nserver:")
    import server
    c = server.app.test_client()
    kiem = [("GET /", c.get("/"), 200),
            ("GET /api/data", c.get("/api/data"), 200),
            ("POST /api/verdict", c.post("/api/verdict", json={
                "posting_text": tin["OPP-001"]["raw_text"],
                "profile": ho_so["P-01"], "mode": "mock"}), 200),
            ("POST /api/cv", c.post("/api/cv?mode=mock", json={"text": text}), 200),
            ("POST /api/cv (rỗng)", c.post("/api/cv?mode=mock", json={"text": "x"}), 400)]
    if not llm.co_key():
        kiem.append(("POST /api/chat (chưa có key → phải 400)",
                     c.post("/api/chat", json={"lich_su": [], "profile": {}}), 400))
    for ten, r, cho in kiem:
        ok = r.status_code == cho
        loi += not ok
        print(f"  {'✓' if ok else '✗'} {ten} → {r.status_code} (chờ {cho})")
    if llm.co_key():
        print(f"  · POST /api/chat: bỏ qua — có key thật, smoke test không gọi API tốn tiền")
    print(f"  · provider={llm.provider()} model={llm.model()} "
          f"key={'có' if llm.co_key() else 'chưa có'}")

    print("\n" + ("TẤT CẢ ĐẠT" if loi == 0 else f"{loi} LỖI"))
    return 1 if loi else 0


if __name__ == "__main__":
    raise SystemExit(main())
