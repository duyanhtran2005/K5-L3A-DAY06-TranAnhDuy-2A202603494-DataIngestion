# Báo cáo cá nhân — Day 6

## Dữ liệu và pipeline

- **Nguồn dữ liệu:** *Artificial Intelligence Risk Management Framework (AI RMF 1.0)*, NIST AI 100-1 (2023). Trong 48 trang vật lý, chọn trang PDF 6–47 làm 42 trang nội dung; loại trang 1–5 và 48. Quy tắc chọn trang, nguồn và quyền sử dụng được ghi trong `data/manifest.json`. 
- **Trích xuất và chuẩn hóa:** Dùng `pypdf`; chuẩn hóa Unicode NFC, khoảng trắng và từ bị ngắt ở cuối dòng. Không có trang rỗng trong 42 trang được chọn.
- **Embedding và lưu trữ:** OpenRouter `openai/text-embedding-3-small`, vector 1536 chiều; PostgreSQL 16.16 + pgvector 0.8.7; tìm kiếm cosine exact. Mỗi câu hỏi được embedding một lần rồi dùng chung cho A, B và C.
- **Metadata:** Mỗi chunk có `document_id`, `source`, `page` để truy nguồn. Trường lọc `section` được xác định từ tiêu đề và vị trí chunk, nhận GOVERN, MAP, MEASURE hoặc MANAGE. Chunk ngoài các phần này hoặc qua ranh giới phần có thể không có `section`.
- **Chi phí:** 41.433 token đã ghi nhận, ước tính 0,00082866 USD theo đơn giá OpenRouter 0,02 USD/triệu token.

## Cấu hình và benchmark

- A: Chia cố định 500 ký tự, overlap 50; truy xuất không lọc.
- B: Chia theo heading/câu, tối đa 500 ký tự; truy xuất không lọc.
- C: Dùng đúng chunk và vector của B; chỉ lọc `section` khi câu hỏi cung cấp GOVERN, MAP, MEASURE hoặc MANAGE. Vì vậy B–C chỉ khác bước lọc.
- Cả ba dùng cùng PDF NIST AI RMF 1.0, OpenRouter `openai/text-embedding-3-small` (1536 chiều), PostgreSQL 16.16 + pgvector 0.8.7 và cosine exact search.
- Benchmark có 30 câu đã ghi gold evidence: 20 dev và 10 test. Dev và test đều có câu filter cho cả bốn section, bộ câu hỏi và gold nằm trong `benchmark/questions.json`.
- Tiêu chí chọn chiến lược đã chốt trước khi xem test: ưu tiên Evidence Hit@3, sau đó khả năng tuân thủ filter và chi phí. B và C đang có cùng kết quả truy xuất tự động; C có cùng Hit@1 và Evidence Hit@3 với B trên dev; top-3 tuân thủ section ở cả 5 câu dev có filter. Chọn C để đánh giá test sau khi hoàn tất rà soát gold dev.

## Kết quả

| Cấu hình | Dev Hit@1 | Dev Evidence Hit@3 | Test Hit@1 | Test Evidence Hit@3 | Số chunk |
|---|---:|---:|---:|---:|---:|
| A | 3/20 | 7/20 | 3/10 | 4/10 | 244 |
| B | 8/20 | 9/20 | 7/10 | 10/10 | 351 |
| C | 8/20 | 9/20 | 7/10 | 10/10 | 351 |

Thời gian là 18,814 giây với A, 24,724 giây với B và 0,526 giây để lưu C từ vector của B. Lần chạy dev cuối mất 19,461 giây và lần chạy test mất 10,578 giây; mỗi lần bao gồm truy xuất cho cả ba cấu hình. Chi phí embedding tài liệu ước tính lần lượt là 0,00041628 USD cho A, 0,00037508 USD cho B và 0 USD bổ sung cho C. Chi phí embedding câu hỏi dùng chung cho các cấu hình.

| Cấu hình | Coherence trung bình /2 (10 vị trí) | Metadata đủ và đúng | Tuân thủ filter trên test | Grounding mức 0/1/2 (5 câu) | Grounding trung bình /2 |
|---|---:|---:|---:|---:|---:|
| A | 1,4 | 14/15 | N/A — không áp dụng filter | 2/1/2 | 1,0 |
| B | 2,0 | 15/15 | N/A — không áp dụng filter | 0/0/5 | 2,0 |
| C | 2,0 | 15/15 | 4/4 | 0/0/5 | 2,0 |

Coherence được chấm trên cùng 10 vị trí nguồn ứng với Q01–Q10. Grounding và metadata được kiểm tra trên cùng 5 câu test Q18, Q22, Q24, Q29, Q30; mỗi câu xét top-3 của cả ba cấu hình. Grounding ở đây là mức độ đầy đủ của bằng chứng truy xuất, không phải độ chính xác của câu trả lời do LLM tạo. Trace nằm trong `starter/results/`, còn lý do chấm từng trường hợp nằm trong `artifacts/manual_test_labels.csv` và `artifacts/manual_chunk_coherence.csv`.

## Phân tích và kết luận

- **A–B:** Chia theo heading và câu giúp B giữ ý tốt hơn trên mẫu đã chấm. Evidence Hit@3 tăng từ 7/20 lên 9/20 ở dev và từ 4/10 lên 10/10 ở test. B tạo nhiều chunk hơn (351 so với 244), ingest lâu hơn nhưng dùng ít token embedding tài liệu hơn; overlap của A là một nguyên nhân có thể góp phần tạo văn bản lặp.
- **Ví dụ lỗi:** Với Q22, top-3 của A thiếu bằng chứng về môi trường triển khai dự kiến ở trang PDF 31; B và C tìm được ở hạng 2. Với Q30, chunk A bị cắt giữa từ và thiếu phần đầu của ý ở trang PDF 43, còn B và C giữ trọn bằng chứng. Ở Q29, một hit của A đúng nội dung nhưng thiếu metadata `section`.
- **B–C:** Hit@1 và Evidence Hit@3 bằng nhau trên cả dev và test. C tuân thủ filter ở 4/4 câu test có filter và dùng lại vector của B, nên được chọn cho corpus này. Kết quả chưa đủ để kết luận C tốt hơn B trên dữ liệu khác.
- **Giới hạn:** Chỉ thử trên một PDF tiếng Anh và 10 câu test; 5 câu được chấm grounding thủ công. Câu hỏi tiếng Việt có thể ảnh hưởng khả năng truy xuất. Mẫu coherence Q01–Q10 và nhãn thủ công được chọn, đề xuất sau khi đã xem điểm tự động, nên có nguy cơ thiên lệch và cần tác giả rà soát. Chi phí chỉ là ước tính từ token đã ghi. Hướng mở rộng là thử thêm tài liệu, câu hỏi và truy xuất kết hợp từ khóa.