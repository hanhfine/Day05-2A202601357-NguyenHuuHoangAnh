# Kế hoạch — OpportunityMatch AI (Hướng C)

> Tài liệu làm việc của nhóm. Không phải file nộp bài. File nộp: `spec.md`, `eval/`, `validation/`, `codebase/`, `reflection/`, `demo-slides.pdf`.

---

## 0. Rủi ro lớn nhất — đọc trước mọi thứ khác

**Data pack không có bằng chứng nào cho đề tài này.** Đã kiểm tra:

| Kiểm tra | Kết quả |
|---|---|
| Câu hỏi học viên trong chatlog VLearn nhắc học bổng / thực tập / nghề nghiệp / ứng tuyển / phỏng vấn / lương | **0 / 1.261** |
| Cùng bộ từ khoá, phía tutor | 9 / 1.261 (đều là tutor lấy ví dụ minh hoạ, không phải học viên hỏi) |
| Transcript bài giảng | Chỉ có 1 chỗ dùng được: mục "Ba track nghề nghiệp: AI Engineer / MLOps / AI PM" `[T03-014]`–`[T03-021]`, giảng viên nói giai đoạn 2 học viên **phải chọn 1 trong 3 track** |

Nghĩa là **đường B (mining data pack) chết** cho đề tài này. Hệ quả kế hoạch:

1. **Bằng chứng chính phải là đường A — khảo sát ≥20 người ngoài nhóm.** Đây là đường sống duy nhất cho R1 (15 điểm, khối nặng nhất). Không có 20 người + log nguyên văn → mất 6 điểm cứng, kéo theo cả §1 spec.
2. **Đường B thay bằng mining Discord khoá** (đề bài cho phép: hướng B không có pack, nhóm tự mining Discord — hướng C là làn mở nên càng được).
3. **Con số `0/1.261` vẫn dùng được, nhưng phải khai đúng bản chất.** Nó chứng minh *whitespace* — job này hiện không sản phẩm nào của khoá phục vụ. Nó **không** chứng minh pain. Viết trong spec đúng câu đó. Người chấm sẽ tự thấy nếu nhóm cố nhập nhèm hai chuyện; khai thẳng thì được điểm trung thực.

**Việc đầu tiên khi phát đề: cử 2 người đi khảo sát ngay, không chờ chốt lát cắt.** Ai chờ spec xong mới đi hỏi sẽ không kịp 20 người.

### 0b. Cần báo TA ngay: data pack đang nằm trong repo public

Kiểm tra lúc dựng CP2:

- `origin` = `github.com/hanhfine/Day05-2A202601357-NguyenHuuHoangAnh` — **repo đang PUBLIC**. API GitHub không cần đăng nhập vẫn tải được `data/vlearn-pack/chatlog/chat_history_anonymized_for_hackathon.csv` (1,9 MB, 2.522 dòng hội thoại thật) và 6 transcript.
- 10 file data pack **đang được git theo dõi**, do commit của BTC (`blue <maianh.anhntm@gmail.com>`) từ trước khi nhóm bắt đầu — **không phải nhóm gây ra**.

Việc này ngược đúng quy định trong README repo: *"không đưa vào bất kỳ dataset hay repo công khai nào"* và *"Không commit data pack vào repo nộp bài"*.

**Nên làm, theo thứ tự:**

1. **Báo TA tại CP2** (12:00 — đúng mốc hỗ trợ) kèm đúng ba dữ kiện trên. Đây là repo và data của BTC, quyết định là của họ.
2. **Chưa push** cho đến khi TA trả lời. Commit local thì cứ commit bình thường — CP2 chỉ đòi "repo có commit".
3. **Không tự ý `git rm` hay rewrite history.** Đó là commit của BTC; xoá đơn phương vừa mất data đang dùng để mining, vừa không thật sự xoá được khỏi history đã public.

---

## 1. Lát cắt đề xuất

Đề tài "agent tìm học bổng và thực tập" **quá rộng để nộp nguyên**: "tìm" nghĩa là crawl → demo phụ thuộc mạng, không có nhãn vàng để đo, và quyết định AI trung tâm bị mờ. Rubric chấm chuỗi quyết định, không chấm độ hoành tráng. Nên cắt vào chỗ có **phán quyết kiểm chứng được**:

> **Học viên khoá AI Thực Chiến đang cân nhắc một cơ hội việc làm (thực tập · fresher · junior) · chọn MỘT tin (tìm trong thư viện của hệ thống hoặc dán vào) cùng hồ sơ của mình (khai tay hoặc lấy từ CV) · AI phán quyết `Nên apply` / `Rủi ro cao` / `Thiếu thông tin` kèm trích dẫn từng dòng yêu cầu đã đối chiếu · nhận về một thẻ quyết định có deadline + 3 việc phải chuẩn bị.**

**Đã bỏ vế học bổng khỏi lát cắt** *(sửa so với bản CP2)*. Lý do đo được, không phải đổi ý: crawl thật 90 query trong đó 7 query dành riêng cho học bổng, thu về **1 tin học bổng trên 200 tin** — và tin đó hoá ra là false positive (tin tuyển Software Engineer có chữ "đạt học bổng" ở phần ưu tiên ứng viên). Google Jobs index tin tuyển dụng, không index học bổng. Giữ vế đó trong lát cắt là hứa một mảng mà nguồn tin không cấp được, rồi để học viên hỏi "có học bổng nào không" và nhận về danh sách rỗng. Muốn làm học bổng thật thì phải thêm nguồn khác (VinIF, trang học bổng của trường) — việc đó nằm ngoài 1,5 ngày.

Tự kiểm theo guide §1.1 câu 2 — bỏ AI đi việc này còn không? **Còn.** Hôm nay học viên tự đọc tin, tự đoán mình có đủ điều kiện, hỏi bạn, hoặc bỏ qua. Đây là job thật, không phải chỗ nhét AI.

**Một quyết định AI, không phải hai.** Tìm tin và đọc CV là **đường vào**; quyết định AI được chấm là `verdict()` — phán quyết có trích dẫn. Chat chỉ điều phối và bị cấm tự phát biểu về yêu cầu của một tin (`codebase/README.md`, mục hai quyết định thiết kế).

### Non-goals (≥3, rubric R2 — 2 điểm)

1. **Không crawl/tìm tin lúc người dùng hỏi.** `tim_tin` chỉ đọc corpus local, không chạm internet trong luồng chạy. Corpus được nạp trước bằng `data/crawler.py` chạy offline (200 tin thật từ Google Jobs + 40 tin fixture) — *sửa so với bản CP2, khi đó corpus chỉ có 40 tin giả và non-goal này ghi là "không crawl". Đổi vì tin giả không cho học viên nộp hồ sơ vào đâu được; ranh giới thật nằm ở chỗ runtime không gọi mạng, không phải ở chỗ data từ đâu ra.*
2. **Không làm học bổng.** Sản phẩm chỉ phục vụ việc làm: thực tập · fresher · junior. `crawler.nhan_tin()` chặn tin học bổng ngay đầu nguồn, `hoc_bong` đã bỏ khỏi enum `loai` trong tool schema nên model không khai được, và SYSTEM cấm hỏi lại "bạn muốn học bổng hay việc làm". *(13 tin `kind=hoc_bong` còn trong corpus đều là fixture `OPP-*` — dữ liệu test, `tim_tin` mặc định không trả về, giữ vì `golden_set.json` tham chiếu đích danh.)*
3. Không viết CV / cover letter / essay hộ.
4. Không dự đoán xác suất đỗ, không chấm điểm hồ sơ. `tim_tin` xếp hạng theo **mức khớp từ khoá user nhập**, không phán "tin nào tốt nhất cho bạn", và **không loại tin nào theo điều kiện**.
5. **Không lưu hồ sơ/CV người dùng** — xử lý trong RAM, không DB, không ghi file.
6. **Không kết luận "không đủ điều kiện".** Verdict xấu nhất được phép là "Rủi ro cao".
7. Không đọc tin dạng PDF/ảnh — tin chỉ nhận text. (CV thì đọc được .pdf/.docx/.txt/.md.)

Bản build **không được** vi phạm mấy dòng này. TA soát tại CP4. `smoke_test.py` có case canh non-goal #3 và #5.

### Automation: **Augment** (rubric R2 — 4 điểm, lý do phải theo cost-of-error)

AI không bao giờ nộp hộ, và **không bao giờ ra kết luận "bạn không đủ điều kiện"**. Lý do bất đối xứng:

| Lỗi | Ai chịu gì | Sửa đắt hay rẻ |
|---|---|---|
| AI nói "nên apply" nhưng học viên hard-fail điều kiện | mất 3-6h viết hồ sơ vô ích | rẻ — biết sau khi bị loại |
| **AI nói "chưa nên" nhưng học viên thật ra đủ** | **mất hẳn cơ hội, không biết mình đã mất** | **không sửa được — deadline qua rồi** |

Vì lỗi loại 2 không thể phục hồi, verdict xấu nhất mà AI được phép nói là **"Rủi ro cao — kiểm 2 điểm này"**, kèm chỉ rõ dòng nào trong tin làm nó lo. Bên trong augment có một cửa **conditional**: thiếu field quyết định → không ra verdict, hỏi lại đúng 1 câu.

### Ứng viên đã loại (rubric R1 — 3 điểm, phải giữ trong spec §2)

| Ứng viên | Vì sao loại |
|---|---|
| Trích deadline + checklist hồ sơ từ tin | Cost-of-error thấp, quyết định AI quá mỏng (gần như regex), demo 5' nhạt. Giữ lại làm **một phần** của thẻ kết quả. |
| Gom tin nhiều nguồn + xếp hạng top-3 | Loại **làm lát cắt được chấm**: cần crawl, ranking không có nhãn vàng → không đo được trong 1,5 ngày → vỡ R4 (15 điểm). Đã build một phần rút gọn làm **đường vào**: `tim_tin` search thư viện 40 tin local, xếp theo mức khớp từ khoá, không loại tin nào theo điều kiện. Quyết định được chấm vẫn là `verdict()` |
| Gap-map "khoá dạy gì `[Txx-NNN]` vs tin đòi gì" → lộ trình học | Hay nhưng là job dài hạn, không validate được trong một buổi. → **slide 6 "nếu có thêm 1 tuần"** |

Số cụ thể (bao nhiêu người × tần suất × tốn gì) điền từ khảo sát — xem §2.

---

## 2. Bằng chứng — làm song song ngay từ giờ đầu

### 2a. Đường A — khảo sát ≥20 người ngoài nhóm, ≥50% xác nhận, log nguyên văn

**Định nghĩa "xác nhận" — chốt TRƯỚC khi đi hỏi:** người đó trả lời **Có ở Q4 hoặc Q5 và kể được một lần cụ thể**. Không tính "em thấy cũng cần".

Bộ câu hỏi (hỏi về **lần gần nhất**, không hỏi ý kiến — guide §1.3.4):

| # | Câu hỏi | Dùng để |
|---|---|---|
| Q1 | 3 tháng gần nhất, bạn có tìm hoặc cân nhắc apply một tin thực tập/học bổng nào không? | sàng lọc |
| Q2 | Lần gần nhất là tin gì, bạn thấy nó ở đâu? | bối cảnh + nguồn tin thật để dựng corpus |
| Q3 | Từ lúc thấy tin đến lúc quyết định apply-hay-không, bạn mất bao lâu? Trong khoảng đó bạn làm những gì? | **số phút/lần → cột "tốn gì mỗi lần" bảng impact** |
| Q4 | Có lần nào bạn apply rồi mới biết mình không đủ điều kiện, **hoặc bỏ qua rồi sau mới biết mình đủ**? Kể lần gần nhất. | **câu xác nhận pain chính** |
| Q5 | Có lần nào bạn miss deadline một cơ hội vì không nắm rõ hạn hoặc hồ sơ cần gì? | xác nhận pain ④ |
| Q6 | Hiện tại bạn quyết định bằng cách nào — hỏi ai, dùng gì? Nó fail ở đâu? | alternatives + vì sao chưa bỏ nó |
| Q7 | Chiều nay có bản thử 5 phút, bạn thử giúp mình được không? | **willing users — cần ≥3 tên từ CP1** |

**Log bắt buộc:** `người trả lời (tên/vai) | Q1..Q7 nguyên văn | thời điểm`. Không log = không tính là bằng chứng. File: `validation/khao-sat-log.md`. Ghi cả người trả lời **Không** — tỉ lệ % phải có mẫu số thật.

Giờ nghỉ là lúc lấy được nhiều nhất. Cả lớp ~1.000 học viên đều là user thật.

### 2b. Đường B — mining Discord khoá

Đếm tin nhắn liên quan cơ hội trong Discord khoá. **Ghi phương pháp để người khác kiểm lại được** (rubric đòi đúng chữ này):

- channel nào đã tìm, khoảng thời gian nào, bộ từ khoá nào (liệt kê hết), quy tắc xếp loại tin nào tính / không tính
- output: `X/Y tin nhắn, Z người khác nhau, trong N ngày`
- giữ **≥5 quote nguyên văn** — **mask username** trước khi đưa vào repo

### 2c. Bảng impact (rubric R1 — 3 điểm)

Điền sau khi có ~15 phiếu khảo sát, không điền bằng cảm nhận:

`ứng viên | bao nhiêu người gặp (từ Q1/Q4) | tần suất (từ Q1) | tốn gì mỗi lần (phút từ Q3 / cơ hội mất từ Q4) | build nổi trong 1,5 ngày? | chọn?`

---

## 3. Prototype

### Quyết định kiến trúc quan trọng nhất

**Một hàm `verdict(posting_text, profile) -> JSON`, hai người gọi: UI và eval runner.** Nếu UI và eval chạy hai đường prompt khác nhau thì bảng % ở R4 không nói gì về cái đem demo. Đây là chỗ dễ hỏng nhất.

### Đánh số dòng + kiểm trích dẫn bằng máy

App tách tin đã dán thành dòng `L1..Ln`, đưa bản có số dòng vào prompt, và **bắt model trích `evidence_line` cho mọi khẳng định**. Sau đó một hàm checker xác minh chuỗi được trích **có thật nằm trong dòng đó**.

Đây là lý do nên chọn lát cắt này: chiều chất lượng "grounding" trở thành **pass/fail do máy chấm**, không phải cảm tính — đúng yêu cầu R4 "người ngoài nhóm chấm ra cùng kết quả" (4 điểm).

### Hợp đồng output

```json
{
  "verdict": "nen_apply | rui_ro_cao | thieu_thong_tin",
  "matched":    [{"requirement": "...", "evidence_line": 12, "from_profile": "..."}],
  "gaps":       [{"requirement": "...", "evidence_line": 14, "why": "..."}],
  "hard_fail":  [{"rule": "...", "evidence_line": 9}],
  "not_stated": ["tin không nêu yêu cầu GPA"],
  "one_question": "Bạn đang học năm mấy?",
  "deadline": {"raw": "...", "evidence_line": 21, "parsed": "2026-08-05", "ambiguous": false},
  "next_3": ["...", "...", "..."],
  "refusal": null
}
```

- `not_stated` là ô chống bịa: yêu cầu nào tin không nêu thì **phải** vào đây, không được suy diễn.
- `one_question` chỉ được có **đúng 1 câu**, và chỉ khi `verdict = thieu_thong_tin`.
- `hard_fail` chỉ được điền khi tin **ghi thẳng bằng chữ** điều kiện đó.

### Stack (đã build — xem `codebase/README.md`)

**Flask + một trang HTML thuần**, không framework front-end. LLM: **OpenAI** (`gpt-4o-mini`, đổi bằng `OPPM_MODEL`), chat có **function calling** 2 tool. `core/llm.py` là chỗ duy nhất biết provider — đổi sang Gemini là đổi một biến môi trường.

Mức prototype khai: **Mock** — AI thật ở lõi phán quyết + chat + đọc CV; thư viện tin và persona là data giả. Khai đúng thực tế (R5 — 2 điểm).

Đường không cần key vẫn chạy: tab *Tin đang xét* → "Dán tin ngoài để đối chiếu" (`mode=mock`). Giữ đường này để demo không chết nếu hết quota.

### Data — luật cứng

- **40 tin giả** `OPP-001..040`: 10 tin gõ tay mỗi tin bắn vào một lớp chỗ khó + 30 tin sinh bằng `data/gen_corpus.py` **seed=42** — người ngoài chạy lại ra đúng cùng 30 tin (phương pháp kiểm lại được). Tên tổ chức bịa hết.
- **4 persona hồ sơ giả** `P-01..P-04` + 1 CV mẫu bịa. **Không** dùng GPA/CV thật của bạn cùng lớp.
- **CV upload xử lý trong RAM, không ghi đĩa; PII bị redact trước khi gửi API; chỉ giữ 6 field.** Ba luật này ở đầu `core/cv.py`. Giới hạn phải nói khi demo: regex **không** bắt được tên người.
- Vòng user test: người thử dùng CV mẫu hoặc CV của họ, nhưng **log chỉ ghi quan sát + quote, không ghi nội dung CV vào repo**.
- Không commit data pack. Trích transcript bằng mã `[Txx-NNN]`.

### ≥4 nguyên tắc HAX, mỗi cái trỏ vào một chỗ có thật (rubric R2 — 6 điểm, khối con nặng nhất)

| Nguyên tắc | Áp vào đâu trong prototype |
|---|---|
| **G1** — làm rõ làm được gì | Dòng đầu màn hình: "Mình đối chiếu MỘT tin bạn dán với hồ sơ bạn khai. Mình không đi tìm tin, không viết CV, không đoán bạn có đỗ." |
| **G2** — làm rõ tốt đến đâu | Badge cạnh verdict: "Chỉ đối chiếu chữ có trong tin" + ô **"Tin không nêu"** hiện `not_stated` |
| **G10** — thu hẹp khi nghi ngờ *(bắt buộc)* | Thiếu field quyết định → **không ra verdict**, hỏi lại đúng 1 câu. Verdict xấu nhất là "Rủi ro cao", không có "Không đủ điều kiện" |
| **G11** — giải thích vì sao | Mỗi dòng matched/gap có chip `L12`, bấm vào **highlight đúng dòng đó** trong tin gốc bên cạnh |
| **G9** — sửa dễ | Sửa hồ sơ inline ngay trên thẻ kết quả → chạy lại tại chỗ |
| **G15** — mời feedback chi tiết | 👍👎 + "sai chỗ nào? [thiếu điều kiện / trích sai dòng / giọng]" → ghi thẳng vào `validation/` |

### 4 đường đi trải nghiệm (R3 — 3 điểm) — phải thấy được trong bản build

| Đường | Trạng thái UI |
|---|---|
| Happy | `nen_apply` + matched có chip dòng + 3 việc cần làm |
| Low-confidence ② | `thieu_thong_tin` → đúng 1 câu hỏi lại, verdict bị giữ lại |
| Failure / không căn cứ ① | Tin quá ngắn/mơ hồ → "không đủ căn cứ để đối chiếu", liệt kê `not_stated`, **không đoán** |
| Correction | User sửa hồ sơ trên thẻ → verdict đổi, hiện rõ cái gì vừa đổi |

---

## 4. Bốn lớp chỗ khó + kịch bản (R3 — 8 điểm)

Mỗi lớp ≥2 case tương ứng trong golden set.

| # | Tình huống cụ thể | Lớp | Hành vi mong muốn | Nguyên tắc |
|---|---|---|---|---|
| 1 | Tin không nêu GPA, AI tự thêm "yêu cầu GPA 3.2" | ① | Vào `not_stated`, tuyệt đối không thành gap | G2 |
| 2 | Tin ghi "ưu tiên ứng viên có kinh nghiệm ML" — AI khẳng định "bạn không đủ" | ① | Là gap có trích dòng, **không** phải hard_fail | G10 |
| 3 | Tin viết "hạn: 5/8", không có năm | ② + ④ | `deadline.ambiguous = true`, hiện nguyên văn dòng, **không** tự điền năm | G2 |
| 4 | Hồ sơ chưa khai năm học, tin đòi "sinh viên năm 3-4" | ② | `thieu_thong_tin` + đúng 1 câu: "Bạn đang học năm mấy?" | G10 |
| 5 | "Viết luôn cover letter cho tôi đi" | ③ | Từ chối + nêu cái làm được: "mình chỉ ra 3 điểm nên nhắc trong thư" | G1 |
| 6 | "Tin này tôi có đỗ không? Bao nhiêu %?" | ③ | Từ chối dự đoán, giải thích vì sao không dự đoán được | G1, G2 |
| 7 | "Tìm cho tôi 10 tin học bổng AI đi" | ③ | Từ chối rõ ràng — ngoài lát cắt, không bịa danh sách | G1 |
| 8 | Tin đòi đóng "phí xử lý hồ sơ" trước | ④ | Cảnh báo dấu hiệu bất thường + **không** ra verdict nên-apply | G10 |
| 9 | Hồ sơ đủ mọi điều kiện → AI nói "hồ sơ bạn rất mạnh" | ④ | Chỉ nói khớp bao nhiêu yêu cầu nào; không khen, không hứa | G2 |
| 10 | Tin nhận "sinh viên mọi năm", hồ sơ năm 2 → AI nói "chưa tốt nghiệp nên không đủ" | ④ | Sai nguy hiểm nhất: chặn người đủ điều kiện. Phải là `nen_apply` | G10 |

**Kịch bản làm nhóm sợ nhất khi demo: #10.** Chưa có case nào đáng sợ = chưa đủ hiểm (guide §2.5). Đem đúng #10 hoặc #8 lên demo live — case lỗi được xử lý là phần được đánh giá cao.

---

## 5. Kiểm thử (R4 — 15 điểm)

### Chiều chất lượng — mỗi chiều một định nghĩa máy hoặc người-thứ-hai chấm ra cùng kết quả

| Chiều | Định nghĩa | Ai chấm |
|---|---|---|
| Grounding | 100% `evidence_line` tồn tại **và** chuỗi trích nằm thật trong dòng đó | **máy** (checker) |
| Verdict đúng | Khớp nhãn vàng ở 3 mức | người, nhãn có sẵn |
| Không bịa yêu cầu | 0 requirement trong `gaps`/`hard_fail` mà không có trong tin | **máy** |
| Hành vi khi thiếu tin | Đúng 1 câu hỏi lại, và hỏi vào đúng field quyết định | người |
| Đúng cỡ / an toàn | ≤150 từ · không hứa kết quả · không khuyên ngoài phạm vi | người |

Hai người chấm độc lập 5 output → lệch thì **viết lại định nghĩa**, không chấm tiếp (guide §2.6.4).

### Golden set ≥20 case

Cơ cấu: **≥2 case/lớp** (8 case, lấy từ bảng §4) + **8-10 case thường** + **2-4 case hiếm**.

**Xử lý xung đột rubric — "≥10 case từ chatlog thật":** chatlog pack có 0/1.261 câu hỏi thuộc chủ đề này, nên không thể lấy case chủ đề từ đó. Cách làm và **phải viết rõ trong spec §7**:

- ≥10 case lấy **cách hỏi thật của học viên** từ hai nguồn: tin nhắn Discord khoá (mining §2b) và pattern hỏi trong chatlog VLearn (hỏi cụt, thiếu ngữ cảnh, hỏi ngoài phạm vi).
- Mỗi case có cột `nguồn`: `Discord <mã tin đã mask>` / `chatlog C0xxx-T0xxx (pattern)` / `synthetic`.
- Nói thẳng lý do thay thế, kèm con số `0/1.261` và phương pháp đếm. Khai minh bạch một hạn chế được điểm; im lặng thì bị trừ.

File: `eval/golden-set.md` (hoặc `.csv`). Mỗi lượt chạy một bản ghi riêng `eval/run-01.md`, `run-02.md`... **đủ mọi case kể cả fail.**

### Quality bar — chốt trong `spec.md` trước 23:59 N1, sau đó KHÔNG đổi

Đề xuất (nhóm tự chốt số sau khi chạy tay 10-20 input theo guide §2.6.1):

> **Đạt khi ≥75% case qua đủ 5 chiều, VÀ 0 case nói "nên apply" trên nhóm hard-fail, VÀ 100% khẳng định về deadline có trích dẫn dòng.**

Hai điều kiện cứng nằm đúng chỗ hậu quả thật. **Thấy kết quả thấp rồi hạ bar = mất điểm.** Không đạt mà phân tích được nguyên nhân thì vẫn đủ điểm — khoảng cách đó chính là nội dung slide 4.

### Nhịp lặp

`chạy trọn bộ → bảng % → chọn MỘT failure đau nhất → sửa → chạy lại TRỌN BỘ`. Sửa prompt chỗ này vỡ chỗ kia là chuyện thường.

---

## 6. Lịch khoá 3 — giờ theo giờ

**Hai cửa sổ quyết định cả bài. Mất là không lấy lại được:**

- **12:00-13:00 giờ nghỉ trưa = cửa sổ bằng chứng.** Đề bài nói thẳng: khảo sát 20 người ngay trong giờ nghỉ. Đây là lúc duy nhất cả lớp rảnh cùng lúc, và evidence chuẩn A phải xong trước CP4 17:30. **Không dùng giờ này để debug** — ai đang kẹt code thì kẹt tiếp sau 13:00.
- **16:00-17:30 = cửa sổ user test.** Ngay sau CP3 là lúc AI đã chạy thật *và* lớp vẫn còn ở đó. Lấy ≥3 phiên tại đây. Chờ đến tối thì không còn ai để thử, mà CP5 09:00 N2 đòi log ≥5 người.

| Giờ | Ai làm gì | Mốc |
|---|---|---|
| 09:00-09:30 | Cả nhóm chốt lát cắt (§1). **R1 + 1 người rời phòng đi khảo sát ngay.** R3 sinh 10 tin giả + 3 persona | |
| 09:30-10:00 | R4 viết Canvas 7 dòng. R1 về với 6-8 phiếu + **≥3 tên willing user** | |
| **10:00** | Canvas 7 dòng · lát cắt đúng format 1 câu · bằng chứng đầu · phân công có tên | **CP1** |
| 10:00-12:00 | R2 dựng flow bấm được với data giả, **chưa cần AI**. R3 viết `verdict()` + hợp đồng JSON + checker trích dẫn. R1 khảo sát tiếp | |
| **12:00** | Flow chính bấm hết được · commit đầu | **CP2** |
| **12:00-13:00** | **Cả nhóm trừ R3 đi khảo sát — mục tiêu chạm 20 phiếu.** R3 nối AI thật vào lõi verdict | ⚠️ bằng chứng |
| 13:00-14:00 | R3 chạy tay 10-15 input, đọc từng output, **đặt tên lỗi** → đây là cơ sở để chốt quality bar. R4 viết 4 lớp + kịch bản | |
| 14:00-15:00 | R3+R4 dựng golden set ≥20 (8 case lấy sẵn từ bảng §4). R2 gắn chip số dòng + highlight tin gốc | |
| 15:00-16:00 | Chạy lượt 1 **trọn bộ** → `eval/run-01.md` có %, đủ mọi case kể cả fail | |
| **16:00** | AI thật ở lõi (có log/trace) · golden set ≥20 · bảng lượt 1 có % | **CP3** |
| **16:00-17:30** | **≥3 phiên user test 10'** (giao task, im lặng quan sát, 3 câu hỏi, log nguyên văn) — song song R3 sửa MỘT failure đau nhất rồi chạy lại trọn bộ | ⚠️ user test |
| **17:30** | Evidence chuẩn A có log · bảng impact + ứng viên loại · 4 lớp + ≥8 kịch bản · **quality bar bằng số** | **CP4** |
| 17:30-20:00 | R4 hoàn thiện spec §1-§9 và **chốt quality bar**. R5 dựng slide 6 trang | |
| 20:00-23:00 | Lượt chạy 2 sau khi sửa → `eval/run-02.md`. Changelog từ feedback. Reflection cá nhân mỗi người 1 file | |
| **23:59** | **HẠN CỨNG `spec.md`** — quality bar chốt từ đây, sau đó không đổi | 🔒 |
| 08:00-09:00 N2 | 2 phiên test còn lại cho đủ **≥5 người có tên**. Dry run bấm giờ. Backup screenshot/video | |
| **09:00 N2** | Log ≥5 mẩu có tên · changelog · slide final · dry run xong · mọi người giải thích được phần mình | **CP5** |
| 09:00-10:00 N2 | Sửa nốt theo CP5. Mỗi người tập nói ≥1 phần | |
| **10:00 N2** | 5' trình bày + 5' Q&A · demo live 1 case chuẩn + **1 case chỗ khó** | **CP6** |

Khoá 3 được một lợi thế: CP3 (16:00) và CP4 (17:30) đều xong **trước** hạn spec 23:59, nên quality bar được chốt sau khi đã có số thật — không phải chốt mù. Đừng phá lợi thế đó bằng cách viết bar trước khi chạy lượt 1.

**Sau CP4 không thêm feature mới.** Từ đó đến demo chỉ sửa theo failure và feedback.

**25 điểm nộp là điểm dễ nhất trong rubric:** mỗi CP1-CP5 5 điểm, đúng hạn ăn đủ, muộn 0. **Mỗi thành viên nộp riêng, cùng một link repo.** Cử **một người canh giờ nộp** — mất 5 điểm ở đây đau hơn mọi thứ khác vì nó không đổi lấy được gì.

---

## 7. Phân công 5 vai

Ai cũng phải giải thích được phần có tên mình — CP5 hỏi ngẫu nhiên, không giải thích được thì phần đó 0 điểm.

| Vai | Việc | Ra artifact nào |
|---|---|---|
| **R1 · Evidence** | Khảo sát đến ≥20 người + mining Discord + bảng impact | `validation/khao-sat-log.md`, spec §1-§2 |
| **R2 · Build UI** | Flow bấm được → thẻ kết quả + chip dòng + highlight | `codebase/` |
| **R3 · Prompt + eval** | Hàm `verdict()`, checker trích dẫn, golden set, các lượt chạy | `codebase/`, `eval/` |
| **R4 · Spec** | Spec §3-§7, 4 lớp, 8+ kịch bản, chốt quality bar | `spec.md` |
| **R5 · Validation + demo** | Điều phối 5 phiên test, slide 6 trang, dry run, **canh giờ nộp CP** | `validation/`, `demo-slides.pdf` |

Nhóm 4 người: gộp R4 vào R3 hoặc R5.

---

## 8. Ba việc làm ngay trong 30 phút đầu

1. **R1 + một người nữa đi khảo sát** với bộ Q1-Q7 ở §2a. Không chờ chốt spec. Mục tiêu giờ đầu: 8 phiếu + 3 tên willing user.
2. **R3 sinh 10 tin giả `OPP-001..010` + 3 persona** — đủ để R2 dựng flow, đủ để chạy tay 10 input lấy cơ sở chốt quality bar.
3. **R4 viết Canvas 7 dòng** cho CP1, lấy lát cắt ở §1 làm bản nháp và sửa theo cái nhóm thật sự tin.

## 9. Checklist trước CP6

- [ ] `README.md` — thành viên (mã HV + tên) + **phân công có tên từng phần**
- [ ] `spec.md` đủ §1-§9, quality bar y nguyên bản 23:59 N1
- [ ] `eval/` — golden set + **mọi lượt chạy, đủ case fail**
- [ ] `validation/` — log ≥5 người có tên + 4 dòng tổng hợp
- [ ] `reflection/` — mỗi người 1 file
- [ ] `demo-slides.pdf` 6 trang — **mỗi slide ≥1 con số / quote có nguồn**
- [ ] `codebase/` ghi rõ phần nào mock
- [ ] Không API key, không data pack, không thông tin cá nhân người thật trong repo
- [ ] Backup screenshot/video phòng live hỏng
- [ ] Cả nhóm trả lời được: "Augment hay automate — vì sao?" · "Failure nguy hiểm nhất?" · "Phần bạn làm là gì?"
