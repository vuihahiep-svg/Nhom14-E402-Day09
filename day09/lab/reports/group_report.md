# Báo Cáo Nhóm - Lab Day 09: Multi-Agent Orchestration

**Tên nhóm:** Nhóm 14  
**Thành viên:**

| Tên | Vai trò | Email |
|-----|---------|-------|
| ___ | Supervisor Owner | ___ |
| ___ | Worker Owner | ___ |
| ___ | MCP Owner | ___ |
| Chu Tuấn Nghĩa | Trace & Docs Owner | nghiahh2004@gmail.com |

**Ngày nộp:** 2026-04-14  
**Repo:** `https://github.com/vuihahiep-svg/Nhom14-E402-Day09`  
**Độ dài khuyến nghị:** 600-1000 từ

---

## 1. Kiến trúc nhóm đã xây dựng (150-200 từ)

**Hệ thống tổng quan:**

Nhóm xây dựng hệ thống theo pattern Supervisor-Worker bằng LangGraph. Luồng chính bắt đầu từ `supervisor_node` trong `graph.py`, nơi hệ thống đọc `task`, gán `supervisor_route`, `route_reason`, `risk_high` và `needs_tool`. Từ đó graph điều phối sang một trong ba nhánh: `retrieval_worker`, `policy_tool_worker`, hoặc `human_review`. Sau bước xử lý chuyên trách, toàn bộ dữ liệu được gom lại ở `synthesis_worker` để sinh `final_answer`, `sources` và `confidence`.

Hệ thống hiện có 3 worker chính. `retrieval_worker` thực hiện semantic retrieval từ ChromaDB collection `rag_lab`, trả về `retrieved_chunks` và `retrieved_sources`. `policy_tool_worker` chịu trách nhiệm phân tích policy bằng LLM, đồng thời có thể gọi MCP tools khi thiếu context hoặc khi câu hỏi liên quan ticket. `synthesis_worker` chỉ tổng hợp câu trả lời dựa trên evidence đã có, tránh dùng kiến thức ngoài prompt. Ngoài graph, nhóm triển khai một MCP server HTTP bằng FastMCP trong `mcp_server.py` để cung cấp tool tra cứu KB, ticket, access control và tạo ticket mock.

**Routing logic cốt lõi:**
> Mô tả logic supervisor dùng để quyết định route (keyword matching, LLM classifier, rule-based, v.v.)

Supervisor dùng **rule-based keyword matching**. Nếu task chứa các từ như `refund`, `hoàn tiền`, `policy`, `access`, `level 3` thì route sang `policy_tool_worker`. Nếu task có tín hiệu rủi ro như `p1`, `sev1`, `khẩn cấp` thì `risk_high=True`. Nếu đồng thời có `err-` thì graph chuyển sang `human_review` để HITL thay vì tiếp tục tự động.

**MCP tools đã tích hợp:**
> Liệt kê tools đã implement và 1 ví dụ trace có gọi MCP tool.

- `search_kb`: Dùng để semantic search qua MCP khi `policy_tool_worker` chưa có chunk; ví dụ rõ nhất là trace `run_20260414_170733.json` cho câu `q03 - "Ai phải phê duyệt để cấp quyền Level 3?"`. Trace này có `supervisor_route = "policy_tool_worker"`, `needs_tool = true`, `history` ghi `[policy_tool_worker] called MCP search_kb`, và trong `mcp_tools_used` có đúng một tool call `search_kb` trả về 3 chunks từ `it/access-control-sop.md`.
- `get_ticket_info`: Dùng để lấy thông tin ticket mock khi task chứa `ticket`, `p1`, `jira`; ví dụ trace `gq03` và `gq09` có `mcp_tools_used` gồm `get_ticket_info`.
- `check_access_permission`: Đã implement trong MCP server để trả về `required_approvers`, `can_grant`, `emergency_override`; chưa được gọi trực tiếp trong `grading_run.jsonl`.

Ví dụ trace cụ thể từ `run_20260414_170733.json`:

```text
task = "Ai phải phê duyệt để cấp quyền Level 3?"
supervisor_route = "policy_tool_worker"
history:
- [policy_tool_worker] called MCP search_kb
- [retrieval_worker] retrieved 3 chunks from ['it/access-control-sop.md']
workers_called = ["policy_tool_worker", "retrieval_worker", "synthesis_worker"]
mcp_tools_used[0].tool = "search_kb"
```

---

## 2. Quyết định kỹ thuật quan trọng nhất (200-250 từ)

**Quyết định:** Dùng supervisor route theo luật và keyword thay vì LLM router toàn phần

**Bối cảnh vấn đề:**

Ngay từ đầu nhóm cần một cơ chế điều phối đủ đơn giản để các worker có thể được test độc lập, nhưng vẫn đủ rõ để trace được vì sao mỗi câu đi qua nhánh nào. Nếu dùng một prompt LLM để route, nhóm sẽ có nguy cơ gặp hai vấn đề: khó giải thích quyết định route trong trace, và khó tái hiện lỗi khi grading questions bị route sai.

**Các phương án đã cân nhắc:**

| Phương án | Ưu điểm | Nhược điểm |
|-----------|---------|-----------|
| LLM router | Linh hoạt, hiểu câu hỏi đa dạng hơn | Khó debug, khó giải thích route, chi phí và độ bất định cao |
| Rule-based keyword router | Dễ kiểm soát, dễ trace, dễ sửa nhanh trong lab | Bao phủ intent kém hơn, phụ thuộc từ khóa |

**Phương án đã chọn và lý do:**

Nhóm chọn rule-based router trong `supervisor_node`. Lý do chính là bài lab Day 09 ưu tiên orchestration, traceability và khả năng chứng minh hành vi qua log hơn là tối ưu semantic classification. Với cách này, mỗi run đều lưu rõ `supervisor_route` và `route_reason`, nên khi pipeline trả lời sai nhóm vẫn biết sai ở bước route hay ở worker phía sau. Thiết kế này cũng giúp tích hợp HITL rõ ràng: chỉ cần thêm một điều kiện `risk_high` + `err-` là có thể chuyển sang `human_review`.

**Bằng chứng từ trace/code:**
> Dẫn chứng cụ thể (VD: route_reason trong trace, đoạn code, v.v.)

```text
gq02:
supervisor_route = "policy_tool_worker"
route_reason = "task contains policy/access keyword"

gq07:
supervisor_route = "retrieval_worker"
route_reason = "default route: factual lookup / retrieval | risk_high flagged"

Code trong graph.py:
- policy/access/refund keywords -> policy_tool_worker
- risk_high + "err-" -> human_review
```

---

## 3. Kết quả grading questions (150-200 từ)

**Tổng điểm raw ước tính:** 79 / 96

**Câu pipeline xử lý tốt nhất:**
- ID: `gq07` - Lý do tốt: pipeline abstain đúng, trả lời rõ "Không đủ thông tin trong tài liệu nội bộ", có cite nguồn, không bịa mức phạt tài chính và `confidence=0.3`, phù hợp đúng rubric anti-hallucination.

**Câu pipeline fail hoặc partial:**
- ID: `gq02` - Fail ở đâu: hệ thống nhận ra case này liên quan policy và có nhắc tới policy v3, nhưng vẫn tự kết luận "không được hoàn tiền do quá 7 ngày".  
  Root cause: temporal scoping chưa chặt; worker đã đúng ở bước route nhưng policy analysis vẫn suy diễn thêm nội dung của policy v3 dù tài liệu hiện tại không chứa policy này.

**Câu gq07 (abstain):** Nhóm xử lý thế nào?

Nhóm xử lý khá đúng. Trace cho thấy câu này đi qua `retrieval_worker -> synthesis_worker`, không gọi tool thừa. Output nói thẳng là không đủ thông tin trong tài liệu nội bộ về mức phạt tài chính khi vi phạm SLA P1 resolution time. Đây là một điểm mạnh vì hệ thống giữ được grounding và không hallucinate.

**Câu gq09 (multi-hop khó nhất):** Trace ghi được 2 workers không? Kết quả thế nào?

Có. Trace `gq09` ghi `workers_called = ["policy_tool_worker", "retrieval_worker", "synthesis_worker"]`, nên có đủ 2 worker chính trước khi synthesis. Kết quả nhìn chung là **partial**: pipeline đã lấy được cả bối cảnh SLA P1 và access control, nhưng phần điều kiện cấp Level 2 emergency access chưa bám sát SOP trong MCP server, nên nhiều khả năng không đạt full điểm cho câu multi-hop này.

---

## 4. So sánh Day 08 vs Day 09 - Điều nhóm quan sát được (150-200 từ)

> Dựa vào `docs/single_vs_multi_comparison.md` — trích kết quả thực tế.

**Metric thay đổi rõ nhất (có số liệu):**

Metric thay đổi rõ nhất là **khả năng debug và quan sát route**, đi cùng với thay đổi về confidence và latency. Theo tài liệu so sánh, `avg confidence` tăng từ `0.525` ở Day 08 lên `0.574` ở Day 09, tức tăng `+0.049` hay khoảng `+9.3%`. Đổi lại, `avg latency` tăng từ `9856ms` lên `12819ms`, tức tăng khoảng `+30%`. Tuy nhiên, lợi ích vận hành lớn nhất không nằm ở điểm số mà nằm ở trace: Day 08 gần như không có routing visibility, còn Day 09 ghi rõ `supervisor_route`, `route_reason`, `workers_called` và MCP usage, giúp thời gian debug ước tính giảm từ khoảng `15 phút` xuống còn khoảng `3 phút`.

**Điều nhóm bất ngờ nhất khi chuyển từ single sang multi-agent:**

Điều bất ngờ nhất là multi-agent không chỉ cải thiện ở câu khó, mà còn làm việc an toàn hơn ở các câu thiếu dữ liệu. Trong tài liệu so sánh, case `ERR-403-AUTH` cho thấy Day 09 có thể route sang `human_review`, sau đó synthesis trả lời theo hướng abstain với confidence thấp thay vì cố bịa đáp án. Ngoài ra, ở các câu multi-hop như `q15`, nhóm quan sát thấy `policy_tool_worker` kết hợp được retrieval và MCP search để gom đúng cả SLA lẫn access-control context, điều mà single-agent khó làm ổn định.

**Trường hợp multi-agent KHÔNG giúp ích hoặc làm chậm hệ thống:**

Multi-agent không đem lại khác biệt lớn cho các câu hỏi đơn giản, một tài liệu, một fact. Với các câu như hỏi SLA P1 hay quy định mật khẩu, Day 08 đã trả lời khá tốt; Day 09 chủ yếu chỉ tăng nhẹ confidence nhưng phải trả giá bằng thêm bước supervisor routing, nên thường chậm hơn khoảng `1-3 giây`. Nói cách khác, nếu hệ thống chỉ phục vụ truy vấn đơn giản và yêu cầu latency thấp, single-agent vẫn là lựa chọn gọn hơn. Multi-agent chỉ thực sự đáng giá khi cần policy compliance, cross-document reasoning, tool calling hoặc HITL.

---

## 5. Phân công và đánh giá nhóm (100-150 từ)

**Phân công thực tế:**

| Thành viên | Phần đã làm | Sprint |
|------------|-------------|--------|
| Chu Tuấn Nghĩa | Xây dựng Langgraph Graph, MCP server HTTP và chạy `eval_trace.py` | 1 + 2 + 4 |
| ___ |  |  |
| ___ |  |  |
| ___ |  |  |

**Điều nhóm làm tốt:**

Nhóm đã tách được các vai trò kỹ thuật tương đối rõ giữa orchestration, worker logic, MCP layer và trace. Điều này thể hiện trực tiếp trong code và cũng phản ánh được trong `grading_run.jsonl` qua các field như `supervisor_route`, `workers_called`, `mcp_tools_used`, `confidence`.

**Điều nhóm làm chưa tốt hoặc gặp vấn đề về phối hợp:**

Điểm yếu chính là contract giữa các phần chưa thật đồng bộ. Ví dụ `mcp_tools_used` trong state và dữ liệu thực tế append vào trace chưa hoàn toàn thống nhất, còn flow policy -> retrieval cũng có nguy cơ ghi đè dữ liệu.

**Nếu làm lại, nhóm sẽ thay đổi gì trong cách tổ chức?**

Nhóm nên chốt state contract và rubric đánh giá nội bộ sớm hơn, rồi mới triển khai worker. Làm vậy sẽ giảm lỗi lệch giữa trace, report và hành vi thực tế của pipeline.

---

## 6. Nếu có thêm 1 ngày, nhóm sẽ làm gì? (50-100 từ)

Nhóm sẽ ưu tiên 2 việc. Thứ nhất là sửa `policy_tool_worker` để các case temporal policy như `gq02` không được tự suy diễn policy v3 khi không có tài liệu nguồn. Thứ hai là nối trực tiếp `check_access_permission` vào nhánh access control để `gq09` dùng đúng SOP thay vì chỉ dựa vào retrieval + LLM synthesis. Hai điểm này có tác động rõ nhất lên raw score.

---

*File này lưu tại: `reports/group_report.md`*  
*Commit sau 18:00 được phép theo SCORING.md*
