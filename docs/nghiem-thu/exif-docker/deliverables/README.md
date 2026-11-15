# Rename JPG Files Script

Script Python dùng để đổi tên hàng loạt file JPG dựa trên ngày chụp (EXIF) hoặc ngày sửa file (mtime).

## Cài đặt
Yêu cầu thư viện `Pillow`.
```bash
pip install Pillow
```

## Cách sử dụng
```bash
python3 rename_script.py <đường_dẫn_thư_mục> [--dry-run]
```

- `<đường_dẫn_thư_mục>`: Đường dẫn đến thư mục chứa các file JPG.
- `--dry-run`: (Tùy chọn) Hiển thị danh sách các file sẽ được đổi tên mà không thực hiện đổi tên thật.
