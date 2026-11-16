import sys

def main():
    total = 0
    try:
        with open('input.txt', 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    total += int(line)
                except ValueError:
                    continue
        print(f"TONG={total}")
    except FileNotFoundError:
        print("Lỗi: Không tìm thấy file input.txt")

if __name__ == "__main__":
    main()
