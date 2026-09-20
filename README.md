# Văn các — thư viện truyện tĩnh

Đây là một trang tĩnh để đọc nhiều tác phẩm. Trang có thư viện, mục lục và tìm kiếm chương theo từng truyện, điều hướng chương trước/sau, chế độ tối, chỉnh cỡ chữ và lưu riêng tiến độ/đánh dấu của từng tác phẩm trên trình duyệt.

## Thêm một tác phẩm

Mỗi tác phẩm có một slug riêng và cấu trúc sau:

```text
books/
  ten-slug-cua-truyen/
    book.json
    chapters/
      chap_0001_Tieu_de.txt
      chap_0002_Tieu_de.txt
```

`book.json` bắt buộc có `title` và `author`; có thể thêm `originalTitle`, `genres` (mảng chuỗi), `description`, `status`. Xem `books/ta-that-khong-muon-trung-sinh-a/book.json` làm mẫu. Tên slug chỉ dùng chữ thường, số và dấu gạch ngang. Dòng đầu của mỗi file chương là tiêu đề chương, phần còn lại là nội dung.

Nếu cần gom chương của một truyện thành tệp văn bản, chạy `python3 compile_novel.py <slug>`. Tệp kết quả nằm tại `compiled/<slug>.txt` (có thể đổi bằng `--output`).

## Xem tại máy

```bash
python3 tools/build_reader_data.py
python3 -m http.server 8000 -d site
```

Mở `http://localhost:8000`. Không mở trực tiếp `site/index.html`, vì trình duyệt sẽ chặn việc tải dữ liệu chương qua `fetch` khi dùng giao thức `file://`.

## Đưa lên GitHub Pages

1. Tạo một repository GitHub mới, rồi đẩy toàn bộ thư mục này lên nhánh `main`.
2. Vào **Settings → Pages** của repository và chọn **Source: GitHub Actions**.
3. Mỗi lần đẩy thay đổi lên `main`, workflow `.github/workflows/deploy-pages.yml` sẽ tạo dữ liệu reader và deploy thư mục `site/`.
4. Đường dẫn trang sẽ hiện trong tab **Actions**, ở lần chạy workflow `Deploy reader to GitHub Pages`.

Khi thêm hoặc sửa chương trong `books/<slug>/chapters/`, hoặc sửa `book.json`, chỉ cần commit và push; workflow sẽ tự đưa thay đổi lên trang. Lệnh build tạo dữ liệu tạm trong `site/data/`, nên những tệp này không cần commit.
