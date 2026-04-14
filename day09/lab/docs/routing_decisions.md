# Routing Decisions Log - Lab Day 09

**Nhóm:** ___________  
**Ngày:** 2026-04-14

> **Hướng dẫn:** Ghi lại ít nhất **3 quyết định routing** thực tế từ trace của nhóm.
> Không ghi giả định - phải từ trace thật (`artifacts/traces/`).
>
> Mỗi entry phải có: task đầu vào -> worker được chọn -> route_reason -> kết quả thực tế.

---

## Routing Decision #1

**Task đầu vào:**
> Ai phải phê duyệt để cấp quyền Level 3?

**Worker được chọn:** `policy_tool_worker`  
**Route reason (từ trace):** `task contains policy/access keyword`  
**MCP tools được gọi:** `search_kb`  
**Workers called sequence:** `policy_tool_worker -> retrieval_worker -> synthesis_worker`

**Kết quả thực tế:**
- final_answer (ngắn): Cần phê duyệt của Line Manager, IT Admin và IT Security.
- confidence: `0.55`
- Correct routing? Yes

**Nhận xét:** _(Routing này đúng hay sai? Nếu sai, nguyên nhân là gì?)_

Routing này đúng vì câu hỏi hỏi trực tiếp về phê duyệt quyền truy cập, nên keyword policy/access đã dẫn vào `policy_tool_worker` hợp lý. Trace cũng cho thấy worker này gọi `search_kb`, tìm đúng tài liệu `it/access-control-sop.md`, rồi mới chuyển sang retrieval và synthesis để tạo câu trả lời.

---

## Routing Decision #2

**Task đầu vào:**
> ERR-403-AUTH là lỗi gì và cách xử lý?

**Worker được chọn:** `human_review`  
**Route reason (từ trace):** `unknown error code + risk_high -> human review | human approved -> retrieval`  
**MCP tools được gọi:** `không có`  
**Workers called sequence:** `human_review -> retrieval_worker -> synthesis_worker`

**Kết quả thực tế:**
- final_answer (ngắn): Không đủ thông tin trong tài liệu nội bộ để xác định lỗi ERR-403-AUTH và cách xử lý.
- confidence: `0.3`
- Correct routing? Yes

**Nhận xét:**

Đây là routing đúng vì task chứa mã lỗi lạ, `risk_high=true`, và hệ thống đã kích hoạt HITL trước khi tiếp tục retrieval. Một điểm đáng chú ý là trong trace có lệch dữ liệu: `history` ghi supervisor route sang `human_review`, nhưng field `supervisor_route` lại là `retrieval_worker`. Khi debug nên ưu tiên xem `history` vì nó phản ánh rõ tiến trình thực thi thực tế.

---

## Routing Decision #3

**Task đầu vào:**
> Ticket P1 được tạo lúc 22:47. Ai sẽ nhận thông báo đầu tiên và qua kênh nào? Escalation xảy ra lúc mấy giờ?

**Worker được chọn:** `retrieval_worker`  
**Route reason (từ trace):** `default route: factual lookup / retrieval | risk_high flagged`  
**MCP tools được gọi:** `không có`  
**Workers called sequence:** `retrieval_worker -> synthesis_worker`

**Kết quả thực tế:**
- final_answer (ngắn): On-call nhận thông báo đầu tiên qua PagerDuty; escalation xảy ra lúc 22:57.
- confidence: `0.62`
- Correct routing? Yes

**Nhận xét:**

Routing này đúng vì đây là câu hỏi tra cứu fact kết hợp suy luận thời gian đơn giản từ tài liệu SLA. Dù `risk_high=true`, trace cho thấy hệ thống chưa đẩy sang HITL mà vẫn giữ default retrieval path, và kết quả trả lời đầy đủ dựa trên `support/sla-p1-2026.pdf`.

---

## Routing Decision #4 (tuỳ chọn - bonus)

**Task đầu vào:**
> ERR-403-AUTH là lỗi gì và cách xử lý?

**Worker được chọn:** `human_review`  
**Route reason:** `unknown error code + risk_high -> human review | human approved -> retrieval`

**Nhận xét: Đây là trường hợp routing khó nhất trong lab. Tại sao?**

Đây là case khó nhất vì chỉ từ chuỗi lỗi `ERR-403-AUTH` thì hệ thống không biết đó là lỗi ứng dụng, lỗi policy hay lỗi xác thực hạ tầng. Nếu route thẳng sang retrieval, hệ thống dễ bốc nhầm tài liệu gần nghĩa nhưng không đúng ngữ cảnh. HITL ở đây giúp chặn trả lời bịa khi knowledge base không có thông tin xác thực.

---

## Tổng kết

### Routing Distribution

| Worker | Số câu được route | % tổng |
|--------|-------------------|--------|
| retrieval_worker | 1 | 33.3% |
| policy_tool_worker | 1 | 33.3% |
| human_review | 1 | 33.3% |

### Routing Accuracy

> Trong số 3 câu nhóm đã chạy, bao nhiêu câu supervisor route đúng?

- Câu route đúng: `3 / 3`
- Câu route sai (đã sửa bằng cách nào?): `0`
- Câu trigger HITL: `1`

### Lesson Learned về Routing

> Quyết định kỹ thuật quan trọng nhất nhóm đưa ra về routing logic là gì?  
> (VD: dùng keyword matching vs LLM classifier, threshold confidence cho HITL, v.v.)

1. Nên tách rõ nhánh `policy/access` ra khỏi nhánh retrieval thường để các câu hỏi về quyền, phê duyệt, SOP đi đúng tài liệu ngay từ đầu.
2. Với mã lỗi lạ hoặc truy vấn mơ hồ có `risk_high`, cần ưu tiên HITL hoặc ít nhất một bước xác nhận trước khi tổng hợp câu trả lời.

### Route Reason Quality

> Nhìn lại các `route_reason` trong trace - chúng có đủ thông tin để debug không?  
> Nếu chưa, nhóm sẽ cải tiến format route_reason thế nào?

Các `route_reason` hiện tại đủ để hiểu hướng route ở mức cơ bản, nhưng chưa luôn đủ để debug triệt để. Ví dụ trace `run_20260414_170839` có mâu thuẫn giữa `history` và `supervisor_route`, nên chỉ nhìn một field là chưa đủ. Nên cải tiến format theo cấu trúc ổn định hơn, ví dụ: `classifier=<rule_name>; risk_high=<bool>; hitl=<bool>; final_route=<worker>; fallback=<worker_if_any>; why=<short_reason>`.
