# Báo Cáo Cá Nhân — Lab Day 08: RAG Pipeline

**Họ và tên:** Chu Tuấn Nghĩa

**Vai trò trong nhóm:** Tech Lead

**Ngày nộp:** 13/04/2026

**Độ dài yêu cầu:** 500–800 từ

---

## 1. Tôi đã làm gì trong lab này? (100-150 từ)

> Trong lab này, tôi đã thực hiện code chính RAG pipeline. Cụ thể, tôi chịu trách nhiệm viết mã cho phần index.py và rag_answer.py.
> Trong index.py, tôi sử dụng model Embedding là BAAI/bge-m3 và rag_answer.py, sử dụng gpt4o-mini để sinh câu trả lời. 
> Bên cạnh đó, trong sprint 3, tôi có implement thêm rerank và transform_query. Rerank sử dụng cơ chế RRF; transform query thì áp dụng LLM để thực hiện 3 loại:
> - Mở rộng câu truy vấn
> - Phân rã câu truy vấn
> - HyDE

_________________

---

## 2. Điều tôi hiểu rõ hơn sau lab này (100-150 từ)

> Sau bài học này, tôi hiểu rõ hơn về cơ chế Hybrid retrieval và transform query. Cụ thể, tôi hiểu hơn về việc đánh giá giữa 2 nguồn truy vấn như nào và cách mở rộng câu truy vấn.
> Việc mở rộng câu truy vấn có thể giúp mở rộng không gian tìm kiếm và từ đó cải thiện truy vấn.

_________________

---

## 3. Điều tôi ngạc nhiên hoặc gặp khó khăn (100-150 từ)

> Điều ngạc nhiên nhất là việc sử dụng thêm các cơ chế transform query hay hybrid search đôi khi không làm tăng hiệu quả của RAG.
> Các cơ chế transform query hay kết hợp sparse retrieval đôi khi có thể tạo thêm nhiễu, giảm recall so với baseline chỉ sử dụng dense retrieval.
> Bên cạnh đó, tôi cũng gặp khó khăn khi triển khai cơ chế transform query HyDE khi LLM có thể bị Hallucinate.

_________________

---

## 4. Phân tích một câu hỏi trong scorecard (150-200 từ)

> Chọn 1 câu hỏi trong test_questions.json mà nhóm bạn thấy thú vị.
> Phân tích:
> - Baseline trả lời đúng hay sai? Điểm như thế nào?
> - Lỗi nằm ở đâu: indexing / retrieval / generation?
> - Variant có cải thiện không? Tại sao có/không?

**Câu hỏi:** Approval Matrix để cấp quyền hệ thống là tài liệu nào?

**Phân tích:** Đây là câu hỏi dạng alias test - thử thách khả năng tìm kiếm khi user không biết tên mới.\
Baseline đạt Completeness = 3 trong khi Variant đạt được 4. Việc ứng dụng query expansion đã giúp mở rộng không gian tìm kiếm.
Từ đó giúp kéo đủ chunk vào LLM để sinh kết quả đầu ra. Tuy nhiên vẫn chưa đạt 5 vì model không chủ động nêu rõ "tên hiện tại là...".

Lỗi nằm ở generation: prompt chưa hướng dẫn model khi tìm thấy alias phải nêu rõ cả tên cũ lẫn tên mới. Retrieval đã đúng từ đầu.


_________________

---

## 5. Nếu có thêm thời gian, tôi sẽ làm gì? (50-100 từ)

> Nếu có thêm thời gian, tôi sẽ phân tích kĩ hơn reason cho điểm số được chấm bởi LLM-as-a-judge. Từ đó phân tích kĩ hơn lí do mỗi answer sai, cần cải thiện gì.
> Bên cạnh đó, cần đánh giá thêm query expansion có thực sự hiệu quả không?

