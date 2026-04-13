# Báo Cáo Cá Nhân — Lab Day 08: RAG Pipeline

**Họ và tên:** Mai Đức Thuận
**Vai trò trong nhóm:** Documentation Owner
**Ngày nộp:** 13/4/2026

---

## 1. Tôi đã làm gì trong lab này?

Trong lab này, tôi đảm nhận vai trò Documentation Owner, tập trung chủ yếu ở Sprint 3 và Sprint 4. Cụ thể, tôi chịu trách nhiệm viết và hoàn thiện hai tài liệu thiết kế quan trọng: `architecture.md` (mô tả chunking decision, retrieval config baseline/variant, sơ đồ pipeline) và `tuning-log.md` (ghi lại quá trình A/B experiment, so sánh baseline vs variant theo metrics). Về mặt code, tôi implement hai hàm `retrieve_sparse()` và `retrieve_hyprid()` trong `rag_answer.py` — phần cốt lõi của variant hybrid retrieval sử dụng BM25 kết hợp với Reciprocal Rank Fusion (RRF). Công việc của tôi kết nối chặt chẽ với Retrieval Owner (người làm chunking và indexing) vì tôi cần hiểu metadata và chunk structure để BM25 hoạt động đúng, đồng thời phối hợp với Eval Owner để đảm bảo scorecard baseline/variant có số liệu thực phục vụ tuning-log.

---

## 2. Điều tôi hiểu rõ hơn sau lab này

Trước lab này, tôi hiểu hybrid retrieval theo lý thuyết — rằng nó kết hợp dense và sparse search để bù điểm yếu cho nhau. Nhưng khi tự tay implement `retrieve_sparse()` và `retrieve_hybrid()`, tôi mới thực sự thấy *tại sao* và *khi nào* hybrid tạo ra khác biệt. Cụ thể, BM25 rất mạnh khi query chứa exact term như mã lỗi, tên tài liệu cũ ("Approval Matrix"), trong khi dense embedding lại giỏi với câu paraphrase ("SLA ticket P1 đã thay đổi thế nào?"). Điều trước đây chỉ là khái niệm trong slide giờ trở nên cụ thể: tôi thấy rõ sự khác biệt về score giữa hai retrieval mode khi chạy `compare_retrieval_strategies()`. Ngoài ra, việc phải điền `architecture.md` theo template giúp tôi hiểu sâu hơn về mối quan hệ giữa chunking decision (size, overlap, strategy) và retrieval quality — chunk cắt sai ranh giới thì retrieval dù có tốt đến đâu cũng trả về context thiếu.

---

## 3. Điều tôi ngạc nhiên hoặc gặp khó khăn

Điều khiến tôi ngạc nhiên nhất là việc BM25, một thuật toán cũ và đơn giản, lại hiệu quả đến vậy với một số query cụ thể. Ban đầu tôi nghĩ dense retrieval với embedding hiện đại là đủ, nhưng khi test với câu hỏi như "Approval Matrix để cấp quyền là tài liệu nào?" — query dùng tên cũ/alias — dense retrieval không tìm được expected source vì chunk trong docs dùng tên mới ("Access Control SOP"). Chỉ khi thêm BM25 vào hybrid, exact keyword "Approval Matrix" mới được match. Khó khăn lớn nhất tôi gặp phải là tuning weights cho RRF: ban đầu tôi để `dense=0.5, sparse=0.5` nhưng kết quả cho ra quá nhiều chunk BM25 trùng lặp; sau khi giảm xuống `dense=0.6, sparse=0.4`, hybrid mới thực sự cải thiện so với baseline. Tôi cũng mất thời gian xử lý deduplication giữa hai ranked list vì cùng một chunk có thể xuất hiện ở cả dense và sparse result với rank khác nhau.

---

## 4. Phân tích một câu hỏi trong scorecard

**Câu hỏi:** q07 — *"Approval Matrix để cấp quyền hệ thống là tài liệu nào?"* (Difficulty: hard, category: Access Control)

**Phân tích:**

Baseline (dense retrieval) không retrieve được expected source `it/access-control-sop.md`. Lý do nằm ở retrieval: query dùng tên cũ "Approval Matrix" trong khi tài liệu trong index có tiêu đề "Access Control SOP". Embedding của `bge-m3` không match được alias này vì chúng khác nhau về semantic surface — một cái là tên document cũ, một cái là tên SOP hiện tại. Context recall cho câu này ở baseline = 0/5 vì expected source hoàn toàn vắng mặt trong top-10 candidates.

Variant (hybrid + query expansion) xử lý tốt hơn nhờ hai cơ chế: (1) BM25 match exact keyword "Approval Matrix" — dù chunk không chứa cụm này, nhưng query expansion tạo thêm alternative query như "Access Control SOP" và "system access approval", trong đó "Access Control" match được với filename và section heading trong index. Kết quả là expected source được retrieve ở rank cao, context recall tăng từ 0 lên 5. Tuy nhiên, faithfulness score không thay đổi đáng kể vì cả baseline và variant đều generate được câu trả lời grounded — vấn đề của baseline là answer "I don't know" do không có context, chứ không hallucinate.

Root cause của failure ở baseline là **retrieval gap do alias/naming mismatch** — một vấn đề thực tế trong enterprise RAG mà slide đã cảnh báo. Hybrid retrieval + query expansion giải quyết được vấn đề này mà không cần thay đổi indexing.

---

## 5. Nếu có thêm thời gian, tôi sẽ làm gì?

Tôi muốn thử **HyDE (Hypothetical Document Embeddings)** làm query transform thay vì expansion đơn thuần. Kết quả eval cho thấy query expansion giúp với q07 nhưng ít tác dụng với các câu khác — tôi nghi ngờ HyDE sẽ hiệu quả hơn vì nó sinh một hypothetical answer passage rồi embed passage đó để retrieve, thay vì chỉ paraphrase câu hỏi. Ngoài ra, tôi muốn thử thay đổi chunking strategy từ heading-based sang paragraph-based cho tài liệu HR policy, vì scorecard cho thấy q08 (remote work policy) có completeness score thấp — có thể chunk hiện tại đang cắt ngang điều khoản quan trọng.

---

