"""Server Flask — phục vụ trang, chuyển tiếp sang core/, ghi feedback.

Server KHÔNG có logic phán quyết nào và KHÔNG giữ state hội thoại (client gửi lịch sử
mỗi lượt). Nếu logic rò vào đây thì UI và eval sẽ lệch nhau.

Chạy:  python server.py     →  http://127.0.0.1:5000
"""
import sys
import time
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

# console Windows là cp1252 → in tiếng Việt/mũi tên là crash NGAY khi khởi động server
sys.stdout.reconfigure(encoding="utf-8")

from core import agent, cv, llm
from core.tools import tai_corpus
from core.verdict import tai_data, verdict

CODEBASE = Path(__file__).resolve().parent
REPO = CODEBASE.parent

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024      # CV quá 8MB thì chặn


@app.get("/")
def trang_chu():
    return send_from_directory(CODEBASE / "web", "index.html")


@app.get("/api/data")
def api_data():
    _, ho_so = tai_data()
    return jsonify({
        "postings": [{k: v for k, v in t.items() if not k.startswith("_")}
                     for t in tai_corpus()],
        "profiles": ho_so,
        "provider": llm.provider(), "model": llm.model(), "co_api_key": llm.co_key(),
    })


@app.post("/api/verdict")
def api_verdict():
    """Đối chiếu trực tiếp, không qua chat. Chạy được ở mode=mock mà không cần key."""
    d = request.get_json(force=True)
    tin = (d.get("posting_text") or "").strip()
    if not tin:
        return jsonify({"loi": "Chưa có nội dung tin."}), 400
    try:
        kq = verdict(tin, d.get("profile") or {}, mode=d.get("mode") or "mock",
                     cau_hoi_them=d.get("cau_hoi_them"))
    except Exception as e:                                  # noqa: BLE001
        return jsonify({"loi": f"{type(e).__name__}: {e}"}), 500
    return jsonify(kq)


@app.post("/api/chat")
def api_chat():
    d = request.get_json(force=True)
    if not llm.co_key():
        return jsonify({"loi": "Chat cần API key. Đặt OPENAI_API_KEY rồi chạy lại server. "
                               "Trong lúc chưa có key, dùng ô \"Đối chiếu trực tiếp\"."}), 400
    try:
        r = agent.chat(d.get("lich_su") or [], d.get("profile") or {},
                       mode=d.get("mode") or "real")
    except Exception as e:                                  # noqa: BLE001
        return jsonify({"loi": f"{type(e).__name__}: {e}"}), 500
    return jsonify(r)


@app.post("/api/cv")
def api_cv():
    """CV → 6 field. KHÔNG lưu file, KHÔNG log nội dung CV (core/cv.py luật 1 & 3)."""
    try:
        if "file" in request.files:
            f = request.files["file"]
            text = cv.doc_file(f.filename or "cv.txt", f.read())
        else:
            text = (request.get_json(force=True).get("text") or "")
        if len(text.strip()) < 40:
            return jsonify({"loi": "Nội dung CV quá ngắn hoặc không đọc được text. "
                                   "Nếu là PDF scan ảnh, dán tay phần thông tin học vấn."}), 400
        return jsonify(cv.trich_ho_so(text, mode=request.args.get("mode", "real")))
    except Exception as e:                                  # noqa: BLE001
        return jsonify({"loi": f"{type(e).__name__}: {e}"}), 500


@app.post("/api/feedback")
def api_feedback():
    """G15 — 👍👎 kèm 'sai chỗ nào?' ghi vào validation/ để dùng cho rubric R6."""
    d = request.get_json(force=True)
    f = REPO / "validation" / "feedback-trong-app.md"
    f.parent.mkdir(parents=True, exist_ok=True)
    if not f.exists():
        f.write_text("# Feedback thu trong app (G15)\n\n"
                     "| Thời điểm | Tin | Verdict | 👍/👎 | Sai chỗ nào | Ghi chú |\n"
                     "|---|---|---|---|---|---|\n", encoding="utf-8")
    with f.open("a", encoding="utf-8") as fh:
        fh.write("| {} | {} | {} | {} | {} | {} |\n".format(
            time.strftime("%Y-%m-%d %H:%M"), d.get("opp_id", "?"), d.get("verdict", "?"),
            d.get("danh_gia", "?"), ", ".join(d.get("ly_do") or []) or "-",
            (d.get("ghi_chu") or "-").replace("|", "/").replace("\n", " ")))
    return jsonify({"ok": True})


if __name__ == "__main__":
    print(f"→ http://127.0.0.1:5000   (provider={llm.provider()} model={llm.model()} "
          f"key={'có' if llm.co_key() else 'CHƯA CÓ — chỉ chạy được mode mock'})")
    app.run(host="127.0.0.1", port=5000, debug=True)
