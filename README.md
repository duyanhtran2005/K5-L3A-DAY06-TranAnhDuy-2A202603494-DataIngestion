# Day 06 · Data Ingestion Engineering

**Lab cá nhân** · **4 giờ** · **Dữ liệu tự chọn**

Biến tài liệu thành kho tri thức có thể truy xuất cho AI agent, rồi đo xem cách chuẩn bị dữ liệu nào hiệu quả nhất.

| 📄 Dữ liệu | 🧩 Chiến lược | 🎯 Benchmark |
|---|---|---|
| Tối thiểu **30 trang nội dung** | Tối thiểu **3 cấu hình** | Tối thiểu **20 câu hỏi** |

## Bắt đầu nhanh

Dùng [starter PostgreSQL + pgvector](starter/README.md) để dựng database. Các hàm TODO trong `starter/src/` đã được hoàn thiện cho bài làm này; lệnh chạy nằm ở phần cuối README.

## 1. Xây pipeline

![Đọc tài liệu, chuẩn hóa, chia chunk, tạo vector, lưu và kiểm tra](assets/ingestion-pipeline.svg)

Chọn tài liệu được phép sử dụng; giữ **ID tài liệu, nguồn, trang/vị trí** và metadata phù hợp. Dùng embedding model thật qua API hoặc chạy local; lưu và truy xuất bằng pgvector, Qdrant, Chroma hoặc một store tương đương.

## 2. So sánh và đánh giá

![Ba chiến lược được đánh giá trên cùng corpus và benchmark dev/test](assets/benchmark-workflow.svg)

Dùng cùng dữ liệu, model và câu hỏi cho cả ba cấu hình. Tách **15 câu dev / 5 câu test** trước khi chạy; chọn cấu hình trên dev, rồi đánh giá test sau khi cố định. Mỗi câu hỏi cần có đoạn bằng chứng và trang nguồn; thiết kế bộ câu hỏi và đánh giá theo [BENCHMARK.md](BENCHMARK.md).

Đánh giá theo năm khía cạnh: **độ chính xác truy xuất**, **tính mạch lạc của chunk**, **tính hữu dụng của metadata**, **chất lượng grounding** và **tác động của chiến lược dữ liệu**. Giải thích lựa chọn bằng kết quả, ví dụ lỗi và các đánh đổi.

## 3. Chuẩn bị bài nộp

1. Chạy pipeline và lưu cấu hình, kết quả top-3, trace cùng nhãn đánh giá thủ công.
2. Điền [thông tin học viên](STUDENT.md), [nhật ký thí nghiệm](artifacts/experiment_log.csv) và bản sao [mẫu báo cáo cá nhân](report/individual/MSSV_HoTen.md).
3. Kiểm tra mã nguồn, cách chạy, manifest dữ liệu và checklist trong [SUBMISSION.md](SUBMISSION.md).

## Tài liệu hướng dẫn

| Bạn cần tìm | Tài liệu |
|---|---|
| Setup baseline PostgreSQL + pgvector | [starter/README.md](starter/README.md) |
| Các bước làm và cách tính chỉ số | [GUIDE.md](GUIDE.md) |
| Tiến độ trong 4 giờ | [CHECKPOINTS.md](CHECKPOINTS.md) |
| Năm tiêu chí benchmark và bộ câu hỏi | [BENCHMARK.md](BENCHMARK.md) |
| Tiêu chí chấm điểm | [RUBRIC.md](RUBRIC.md) |
| Quy tắc sử dụng dữ liệu, AI và API | [RULES.md](RULES.md) |
| Cách nộp bài | [SUBMISSION.md](SUBMISSION.md) |

[data/format-example.json](data/format-example.json) chỉ minh họa định dạng, không phải corpus đủ điều kiện. Phần xử lý và benchmark do bạn tự hiện thực; không bắt buộc xây chatbot.

## Bài làm và cách chạy

Ba cấu hình được so sánh trên cùng PDF:

| Cấu hình | Chia chunk | Truy xuất |
|---|---|---|
| A | Cố định 500 ký tự, overlap 50 | Không lọc |
| B | Theo heading và câu, tối đa 500 ký tự | Không lọc |
| C | Cùng chunk và vector với B | Lọc `section` khi câu hỏi yêu cầu |

Cả ba dùng OpenRouter `openai/text-embedding-3-small` (1536 chiều), PostgreSQL 16.16 + pgvector 0.8.7 và cosine exact search. Benchmark gồm 20 câu dev và 10 câu test trong `benchmark/questions.json`.

| Cấu hình | Dev Hit@1 | Dev Evidence Hit@3 | Test Hit@1 | Test Evidence Hit@3 |
|---|---:|---:|---:|---:|
| A | 3/20 | 7/20 | 3/10 | 4/10 |
| B | 8/20 | 9/20 | 7/10 | 10/10 |
| C | 8/20 | 9/20 | 7/10 | 10/10 |

### Dữ liệu

Tải [PDF NIST AI RMF 1.0](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf) và đặt tên `NIST.AI.100-1.pdf` tại thư mục gốc của repo. Pipeline dùng các trang PDF 6–47. Nguồn, quyền sử dụng, quy tắc chọn trang và SHA-256 của file được ghi trong `data/manifest.json`.

### Thiết lập

Cần Python 3.13, Docker Compose và OpenRouter API key. Chạy trong PowerShell từ thư mục gốc của repo:

```powershell
cd starter
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install pypdf==6.21.3 requests==2.34.2
Copy-Item .env.example .env
```

Trong `starter/.env`, điền `OPENROUTER_API_KEY` và đặt:

```text
EMBEDDING_MODEL=openai/text-embedding-3-small
```

`DATABASE_URL` mẫu trỏ tới database local `Lab06` ở cổng `55433`. Không commit `.env` hoặc API key.

### Chạy thí nghiệm

```powershell
docker compose -p day6_student_starter up -d --wait
python scripts/check_setup.py
python -m src.run
python -m src.run dev
python -m src.run test
```

`python -m src.run` đọc PDF, tạo chunk, embedding và lưu A/B/C. Hai lệnh sau truy xuất top-3 và ghi kết quả riêng cho dev, test. Chạy `dev` trước, chốt cấu hình, rồi mới xem `test`. Việc chạy lại lệnh ingest sẽ gọi API embedding và phát sinh thêm token.

### Kết quả và báo cáo

- `data/manifest.json`: nguồn dữ liệu và các trang được chọn.
- `benchmark/questions.json`: câu hỏi, split, đáp án và gold evidence.
- `artifacts/experiment_log.csv`: cấu hình, giả thuyết và kết quả A/B/C.
- `starter/results/ingest_summary.json`: số chunk, thời gian và token ingest.
- `starter/results/dev_metrics.json`, `starter/results/test_metrics.json`: Hit@1 và Evidence Hit@3.
- `starter/results/dev_traces.json`, `starter/results/test_traces.json`: đầy đủ top-3, điểm tương đồng và metadata.
- `artifacts/manual_test_labels.csv`, `artifacts/manual_chunk_coherence.csv`: nhãn và lý do chấm thủ công.
- `report/individual/2A202603494_TranAnhDuy.md`: phân tích và kết luận.
- `STUDENT.md`: thông tin học viên và repo bài nộp.

Số ký tự của cả 42 trang trong manifest đã được đối chiếu với bộ chuẩn hóa của pipeline bằng `pypdf` 6.21.3; không có trang được chọn nào rỗng.
