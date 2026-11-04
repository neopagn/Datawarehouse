# Kho dữ liệu OULAD (CO4031, HK261)

Bài tập lớn môn Kho dữ liệu và Hệ hỗ trợ quyết định (CO4031), Trường Đại học Bách Khoa, ĐHQG TP.HCM.
Repo này chứa phần phân tích yêu cầu và thiết kế kho dữ liệu, kèm quy trình ETL, trên bộ dữ liệu
Open University Learning Analytics Dataset (OULAD): DDL, SQL mẫu của ETL, các script khảo sát dữ liệu
và kiểm chứng thiết kế.

## Cấu trúc

```
├── src/
│   ├── profiling/
│   │   ├── profile_oulad.py        # khảo sát 7 tệp CSV; mọi con số trong tài liệu thiết kế lấy từ đây
│   │   ├── profile_followup.py     # kiểm tra thêm cho các quyết định thiết kế
│   │   ├── validate_design.py      # dựng toàn bộ kho bằng pandas, nạp qua DDL thật, đối chiếu, trả lời Q1-Q6
│   │   ├── check_etl_samples.py    # chạy SQL mẫu của ETL, so với bảng do pandas dựng
│   │   └── draw_schema.py          # vẽ lược đồ ra docs/schema_dw.png
│   └── sql/
│       ├── 00_ddl_staging.sql      # vùng staging: giữ nguyên dữ liệu gốc dạng TEXT
│       ├── 01_ddl_dw.sql           # 6 bảng chiều, 4 bảng fact, 1 bảng tổng hợp
│       ├── 02_ddl_etl_log.sql      # nhật ký chạy ETL
│       ├── 03_kiem_tra_sau_nap.sql # các phép kiểm tra sau khi nạp (job J13)
│       └── etl_mau/                # SQL mẫu đã chạy thử của job J03, J08, J10
├── docs/
│   ├── phan_tich_thiet_ke.md       # tài liệu thiết kế: bảng ánh xạ, danh sách job, quy ước
│   ├── schema_dw.png               # lược đồ galaxy
│   └── *_output.txt                # kết quả của các script trong src/profiling
├── data/raw/                       # 7 tệp CSV gốc, không có trong repo (xem mục Dữ liệu)
└── requirements.txt
```

## Dữ liệu

Dữ liệu không nằm trong repo vì `studentVle.csv` nặng khoảng 433 MB, vượt giới hạn 100 MB mỗi tệp của GitHub.
Tải bản trên Kaggle rồi giải nén 7 tệp CSV vào `data/raw/`:

- Kaggle: https://www.kaggle.com/datasets/anlgrbz/student-demographics-online-education-dataoulad
- Bản gốc của Open University: https://analyse.kmi.open.ac.uk/open_dataset

Nếu đã cài Kaggle CLI và có `kaggle.json`:

```bash
kaggle datasets download -d anlgrbz/student-demographics-online-education-dataoulad -p data/raw --unzip
```

Sau khi giải nén, `data/raw/` phải có: `assessments.csv`, `courses.csv`, `studentAssessment.csv`,
`studentInfo.csv`, `studentRegistration.csv`, `studentVle.csv`, `vle.csv`.

Bộ dữ liệu được mô tả trong: J. Kuzilek, M. Hlosta, Z. Zdrahal (2017), *Open University Learning Analytics
dataset*, Scientific Data 4, 170171. https://doi.org/10.1038/sdata.2017.171

## Cài đặt

Đã chạy với Python 3.12.

```bash
pip install -r requirements.txt
```

Gói `pgserver` mang theo sẵn PostgreSQL 16, nên không cần cài PostgreSQL hay Docker.
`validate_design.py` và `check_etl_samples.py` nhận thêm tham số là thư mục chứa gói `pgserver`.
Nếu cài như trên thì truyền `.`; nếu muốn cài riêng:

```bash
pip install --target .pgserver pgserver
```

rồi truyền `.pgserver`. Các lệnh dưới đây dùng cách cài riêng này.

## Chạy lại các kết quả

Chạy từ thư mục gốc của repo, theo thứ tự:

```bash
python src/profiling/profile_oulad.py data/raw > docs/profiling_output.txt
```

```bash
python src/profiling/profile_followup.py data/raw > docs/profiling_followup.txt
```

```bash
python src/profiling/validate_design.py data/raw work .pgserver src/sql > docs/validation_output.txt
```

```bash
python src/profiling/check_etl_samples.py work .pgserver src/sql > docs/etl_check_output.txt
```

```bash
python src/profiling/draw_schema.py docs/schema_dw.png
```

`validate_design.py` dựng mọi bảng bằng pandas, nạp vào PostgreSQL qua `src/sql/01_ddl_dw.sql`, đối chiếu
tổng với dữ liệu nguồn và trả lời các câu hỏi nghiệp vụ. Đây là bản kiểm chứng thiết kế, không phải ETL
chính thức. `check_etl_samples.py` dùng lại cơ sở dữ liệu trong `work/` nên phải chạy sau nó.

## Thứ tự chạy SQL

1. `00_ddl_staging.sql`, rồi nạp 7 tệp CSV vào staging bằng `COPY` (cách nạp ghi ở đầu tệp).
2. `01_ddl_dw.sql` và `02_ddl_etl_log.sql`.
3. Các job ETL J03–J12. SQL mẫu của J03, J08, J10 nằm trong `src/sql/etl_mau/`; các bảng còn lại làm theo
   bảng ánh xạ trong `docs/phan_tich_thiet_ke.md`.
4. `03_kiem_tra_sau_nap.sql`: mọi dòng phải có `passed = true`.
