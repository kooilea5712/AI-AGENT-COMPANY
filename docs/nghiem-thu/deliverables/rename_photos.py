import os
import sys
import argparse
from datetime import datetime

def rename_photos(directory, dry_run=False):
    if not os.path.isdir(directory):
        print(f"Lỗi: Đường dẫn '{directory}' không phải là thư mục hợp lệ.")
        return

    # Danh sách các file ảnh (giả định các đuôi phổ biến)
    extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff')
    
    files = [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f)) and f.lower().endswith(extensions)]
    
    # Lưu trữ tên đã sử dụng để xử lý trùng lặp
    used_names = {}

    for filename in files:
        filepath = os.path.join(directory, filename)
        
        # Lấy thời gian chỉnh sửa (mtime)
        mtime = os.path.getmtime(filepath)
        dt = datetime.fromtimestamp(mtime)
        time_str = dt.strftime('%Y%m%d_%H%M%S')
        
        name_part, ext = os.path.splitext(filename)
        
        # Tạo tên cơ bản
        new_name = f"{time_str}_{name_part}{ext}"
        
        # Xử lý trùng lặp
        counter = 1
        while new_name in used_names or (not dry_run and os.path.exists(os.path.join(directory, new_name))):
            new_name = f"{time_str}_{name_part}_{counter}{ext}"
            counter += 1
        
        used_names[new_name] = True
        
        if dry_run:
            print(f"[DRY-RUN] {filename} -> {new_name}")
        else:
            old_path = filepath
            new_path = os.path.join(directory, new_name)
            try:
                os.rename(old_path, new_path)
                print(f"Đã đổi tên: {filename} -> {new_name}")
            except Exception as e:
                print(f"Lỗi khi đổi tên {filename}: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Đổi tên file ảnh theo thời gian chỉnh sửa.")
    parser.add_argument("directory", help="Đường dẫn đến thư mục chứa ảnh.")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ in ra kết quả dự kiến.")
    
    args = parser.parse_args()
    rename_photos(args.directory, args.dry_run)
