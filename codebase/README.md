# codebase — OpportunityMatch AI

Chat tìm tin việc làm (thực tập · fresher · junior) trong thư viện của hệ thống, rồi đối chiếu **MỘT** tin với
hồ sơ học viên (khai tay hoặc lấy từ CV) → phán quyết `Nên apply` / `Rủi ro cao` /
`Thiếu thông tin` kèm **trích dẫn số dòng** trong tin.

## Chạy

```powershell
pip install -r requirements.txt
# mở codebase/.env, dán key vào dòng OPENAI_API_KEY=
python data/gen_corpus.py            # sinh corpus 40 tin (chạy 1 lần)
python server.py                     # → http://127.0.0.1:5000
python smoke_test.py                 # kiểm trước khi show
```

Dòng đầu log của `server.py` in ra `provider · model · key=có/chưa có` — xem dòng đó
trước khi kết luận "AI không chạy".

Không có key vẫn demo được phần lõi: tab **Tin đang xét** → *“Dán tin ngoài để đối chiếu”*
chạy `mode=mock`, không gọi mạng.

Console Windows là cp1252 nên in tiếng Việt sẽ crash — các script đã tự
`sys.stdout.reconfigure(encoding="utf-8")`. Viết script mới thì nhớ thêm dòng đó.

## Provider & key

Khai trong `codebase/.env` (file này **không bao giờ được commit** — `.gitignore` đã chặn):

```ini
OPENAI_API_KEY=sk-...
OPPM_PROVIDER=openai        # mặc định. hoặc "gemini"
OPPM_MODEL=gpt-4o-mini      # đổi nếu tài khoản có model khác
```

`core/llm.py._nap_env()` đọc file này lúc import — 12 dòng stdlib, không dùng
python-dotenv (bớt một thứ `pip install` được có thể lỗi). **Biến môi trường thật luôn
thắng file**, nên `$env:OPENAI_API_KEY = "..."` vẫn override được `.env` khi cần test nhanh.
Giá trị rỗng bị bỏ qua → `.env` chưa điền key thì app báo "chưa có key" đúng, không phải
lỗi 401 khó hiểu.

Kiểm `.env` có đang được chặn:

```powershell
git check-ignore -v codebase/.env    # phải in ra ".gitignore:4:.env" — không in gì là NGUY
```

`core/llm.py` là chỗ **duy nhất** biết provider là ai. Chat có tool hiện chỉ chạy với
OpenAI (Gemini dùng schema tool khác, không làm hai đường trong 1,5 ngày). Đường
`doi_chieu` chạy được với cả hai.

`temperature = 0` ở mọi lời gọi — golden set phải chạy lại ra cùng kết quả. Đừng đổi.

**Không viết key vào file trong repo.** Repo này đang public — xem `ke-hoach.md` §0b.

## Mức prototype: **Mock**

| Phần | Thật hay mock |
|---|---|
| Quyết định trung tâm `verdict()` | **AI thật** khi có key (`mode=real`) · mock bằng luật if/else khi không |
| Chat điều phối + gọi tool | **AI thật** (OpenAI function calling) |
| Rút hồ sơ từ CV | **AI thật** khi có key, fallback regex khi không |
| Thư viện 40 tin | **data giả tự sinh** — 10 tin gõ tay + 30 sinh bằng `gen_corpus.py` seed=42. Tên tổ chức bịa |
| 4 persona + CV mẫu | **giả toàn bộ** |
| Trích dẫn số dòng + checker | **thật**, không mock |
| Tìm tin trên internet | **KHÔNG CÓ** — chỉ search corpus local |
| Lưu hồ sơ/CV người dùng | **KHÔNG CÓ** — trong RAM, không DB, không ghi file |

## Kiến trúc

```
web/index.html
     │  POST /api/chat
     ▼
core/agent.py ──gọi tool──► core/tools.py ──► core/verdict.py ──► core/llm.py ──► OpenAI
   (điều phối)               tim_tin           verdict()            (provider)
                             doi_chieu ───────────┘  │
                                                     └──► core/checker.py (soát trích dẫn)
core/cv.py ──► core/llm.py        POST /api/cv
run_eval.py ─────────────────────► core/verdict.py   (CP3 — dùng ĐÚNG hàm mà UI dùng)
```

**Hai lời gọi AI trong một lượt đối chiếu:** ① agent chọn tool và viết câu trả lời;
② `verdict()` bên trong tool `doi_chieu`, với prompt nghiêm ngặt + checker máy.
**Quyết định trung tâm là ②.** Agent bị cấm tự phát biểu về yêu cầu của một tin —
nói rõ chuyện này trong spec §4, đừng để ai tưởng chat là quyết định.

`server.py` không chứa logic phán quyết và không giữ state hội thoại (client gửi lịch sử
mỗi lượt). Nếu logic rò vào server thì UI và `eval/` sẽ lệch nhau.

## Hai quyết định thiết kế ngược lẽ thường — CP5 sẽ hỏi

**1. Không có tool "đọc thô nội dung tin".** Nếu cho model đọc thô rồi tự kể lại yêu cầu,
nó sẽ diễn giải mà không trích dẫn — đúng lỗi ① phải chống. Muốn nói bất cứ điều gì về
một tin, model buộc đi qua `doi_chieu`, nơi có checker soát từng trích dẫn.

**2. `tim_tin` không loại tin theo điều kiện** (năm học, GPA). Nó xếp hạng và ghi chú
"năm học khớp" / "tin ghi năm 3-4 — vẫn nên xem". Lý do y như lý do chọn augment: nếu
regex sai và search âm thầm bỏ mất một tin học viên thật ra đủ điều kiện, họ mất hẳn cơ hội
và không có cách nào biết. Chỉ lọc theo cái user nói rõ: từ khoá, thành phố, loại.
`smoke_test.py` có case canh đúng luật này.

## CV — ba luật cứng trong `core/cv.py`

1. **Không ghi nội dung CV xuống đĩa.** Xử lý trong RAM rồi bỏ. Repo public — một file CV
   lọt vào repo là PII thật của người thật nằm trên internet.
2. **Redact trước khi gửi ra API.** Email / điện thoại / link / số giấy tờ bị thay bằng
   placeholder ngay tại máy, trước lời gọi mạng đầu tiên.
3. **Chỉ giữ 6 field** (năm học · ngành · GPA · thành phố · kỹ năng · project). Còn lại bỏ.

Giới hạn phải nói thẳng khi demo: **regex không bắt được tên người.** Bản redact vẫn có thể
còn tên. Nên luật 1 và 3 mới là lớp bảo vệ chính, không phải luật 2.

Vòng validation: cho người thử dùng `data/cv-mau/CV-mau-01.txt` (CV bịa) hoặc CV của chính
họ, nhưng **log chỉ ghi quan sát + quote, không ghi nội dung CV**.

## Grounding do máy chấm

`core/checker.py` xác minh mọi `evidence_line`: số dòng phải tồn tại **và** ≥60%
(`NGUONG_TRUNG`) từ nội dung khẳng định phải thật sự có ở dòng đó. Chiều chất lượng
"grounding" vì thế là **pass/fail do máy** — người ngoài nhóm chạy lại ra đúng cùng kết quả
(rubric R4). Checker chạy ở **cả hai** chế độ mock và real: không bao giờ tin lời model.

## Nguyên tắc HAX — chỗ áp trong code

| Nguyên tắc | Vị trí |
|---|---|
| G1 làm rõ phạm vi | `index.html` `<p class="sc">` ở header + khối PHẠM VI đầu `agent.SYSTEM` |
| G2 làm rõ tốt đến đâu | ô **“Tin không nêu”** (`not_stated`) + dòng đếm trích dẫn dưới mỗi thẻ verdict |
| G10 thu hẹp khi nghi ngờ | `verdict.py` cây quyết định: thiếu field → `thieu_thong_tin` + đúng 1 câu, **xoá sạch** matched/gaps để không vừa hỏi vừa phán. Không có verdict "không đủ điều kiện" |
| G11 giải thích vì sao | chip `L12` → nhảy tab *Tin đang xét* và sáng đúng dòng |
| G9 sửa dễ | sửa field hồ sơ bất cứ lúc nào rồi nhắc đối chiếu lại |
| G15 mời feedback | 👍👎 + “trích sai dòng” / “thiếu điều kiện” → `POST /api/feedback` ghi vào `validation/feedback-trong-app.md` |

## Giới hạn đã biết của bản mock `verdict`

Ghi ra để không ai tưởng mock là AI, và để chọn failure đau nhất mà sửa ở CP3:

- Chỉ đối chiếu 4 loại yêu cầu: **năm học · GPA · địa điểm · kỹ năng theo từ khoá**.
  Ngoài 4 loại đó rơi vào gap *"chưa đối chiếu tự động được — bạn tự kiểm"*.
- Chỉ bắt phủ định dạng mở đầu `Không yêu cầu ...`.
- Không hiểu điều kiện dạng "chưa từng tham gia chương trình tuyển dụng của công ty".

## File

```
core/llm.py      lớp provider — chỗ duy nhất biết OpenAI/Gemini. Ghi trace vào eval/traces/
core/agent.py    điều phối chat + vòng lặp tool-calling (tối đa 4 vòng)
core/tools.py    2 tool: tim_tin (corpus local) · doi_chieu (quyết định trung tâm)
core/verdict.py  verdict() — mock + real, cùng một schema
core/prompt.py   system prompt + schema cho verdict real
core/checker.py  kiểm trích dẫn bằng máy
core/cv.py       CV → 6 field, redact PII, không ghi đĩa
data/postings.json  10 tin gõ tay, mỗi tin bắn vào 1 lớp chỗ khó (field _muc_tieu)
data/gen_corpus.py  sinh corpus.json = 10 + 30 tin, seed=42, chạy lại ra đúng cùng kết quả
data/cv-mau/        CV bịa để demo upload
server.py        Flask: / · /api/data · /api/verdict · /api/chat · /api/cv · /api/feedback
web/index.html   UI chat 2 cột — không framework
smoke_test.py    11 verdict + 4 case ③ + 5 kiểm tool + 6 kiểm CV + 6 endpoint. KHÔNG phải golden set.
```

## Vibe-coding rule

CP5 hỏi ngẫu nhiên một người về phần có tên mình. Ghi tên người phụ trách từng file vào
`README.md` gốc của repo. Hai chỗ chắc chắn bị hỏi: **vì sao không có tool đọc thô tin**,
và **vì sao `tim_tin` không lọc theo điều kiện**.
