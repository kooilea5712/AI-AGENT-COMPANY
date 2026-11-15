Mục tiêu: Script Python đổi tên hàng loạt file JPG dựa trên ngày chụp (EXIF) hoặc ngày sửa file.

Đầu ra:
- file: rename_script.py (Python script)
- định dạng: .py
- yêu cầu: Chạy được trên Linux, sử dụng thư viện Pillow.

Ràng buộc:
- Ưu tiên đọc EXIF DateTimeOriginal.
- Nếu không có EXIF, dùng ngày sửa file (mtime).
- Định dạng tên mới: YYYYMMDD_HHMMSS_tên_gốc.jpg.
- Có tham số --dry-run để xem trước thay đổi.
- Nhận đường dẫn thư mục đầu vào qua tham số dòng lệnh.

Nằm ngoài phạm vi:
- Xử lý các định dạng file khác ngoài JPG.
- Xử lý các thư mục con bên trong thư mục đầu vào.

Tiêu chí nghiệm thu:
1. Chạy script với --dry-run: In ra danh sách các file sẽ được đổi tên và tên mới tương ứng.
2. Chạy script thực tế: Các file trong thư mục đầu vào được đổi tên đúng định dạng.
3. Kiểm tra fallback: File không có EXIF vẫn được đổi tên dựa trên ngày sửa file.
4. Kiểm tra lỗi: Script không bị crash khi gặp file không phải ảnh hoặc file lỗi.
