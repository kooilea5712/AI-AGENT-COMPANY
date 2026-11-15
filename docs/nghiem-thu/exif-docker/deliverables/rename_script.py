import os
import sys
import argparse
from datetime import datetime
from PIL import Image
from PIL.ExifTags import TAGS

def get_image_date(file_path):
    try:
        with Image.open(file_path) as img:
            exif_data = img._getexif()
            if exif_data:
                for tag, value in exif_data.items():
                    decoded = TAGS.get(tag, tag)
                    if decoded == 'DateTimeOriginal':
                        # Format: "YYYY:MM:DD HH:MM:SS"
                        return datetime.strptime(value, '%Y:%m:%d %H:%M:%S')
    except Exception:
        pass
    
    # Fallback to mtime
    mtime = os.path.getmtime(file_path)
    return datetime.fromtimestamp(mtime)

def rename_files(directory, dry_run=False):
    if not os.path.isdir(directory):
        print(f"Error: {directory} is not a directory.")
        return

    files = [f for f in os.listdir(directory) if f.lower().endswith('.jpg')]
    
    if not files:
        print("No JPG files found.")
        return

    for filename in files:
        file_path = os.path.join(directory, filename)
        
        if not os.path.isfile(file_path):
            continue

        try:
            date_obj = get_image_date(file_path)
            date_str = date_obj.strftime('%Y%m%d_%H%M%S')
            
            base_name = os.path.splitext(filename)[0]
            new_name = f"{date_str}_{base_name}.jpg"
            new_path = os.path.join(directory, new_name)

            if dry_run:
                print(f"[DRY-RUN] {filename} -> {new_name}")
            else:
                if os.path.exists(new_path) and file_path != new_path:
                    print(f"Skip: {new_name} already exists.")
                else:
                    os.rename(file_path, new_path)
                    print(f"Renamed: {filename} -> {new_name}")
        except Exception as e:
            print(f"Error processing {filename}: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rename JPG files based on EXIF date or mtime.")
    parser.add_argument("directory", help="Path to the directory containing JPG files.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without renaming.")
    
    args = parser.parse_args()
    rename_files(args.directory, args.dry_run)
