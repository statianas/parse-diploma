"""
Создает json с уже обработанными названиями файлов.
Необходимо при парсинге работ через kaggle.
"""
import os
import sys
import glob
import json


def save_json_filenames(input_dir: str, output_file: str):
    """
    Рассматривает папку input_dir в поисках файлов *.json,
    собирает их имена и сохраняет список в output_file.
    """
    # Собираем пути к JSON-файлам
    pattern = os.path.join(input_dir, "*.json")
    json_paths = sorted(glob.glob(pattern))

    # Извлекаем только имена файлов
    filenames = [os.path.basename(path) for path in json_paths]

    # Сохраняем список в JSON
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(filenames, f, ensure_ascii=False, indent=2)

    print(f"Найдено {len(filenames)} файлов. Список сохранён в '{output_file}'.")


def main():
    if len(sys.argv) not in (1, 3):
        print("Использование:")
        print("  python name-collection.py <downloads_dir> <output_json>")
        sys.exit(1)

    if len(sys.argv) == 1:
        downloads_dir = "../downloads"
        output_json = "processed_ids.json"
    else:
        downloads_dir = sys.argv[1]
        output_json = sys.argv[2]

    if not os.path.isdir(downloads_dir):
        print(f"[!] Папка '{downloads_dir}' не найдена")
        sys.exit(1)

    save_json_filenames(downloads_dir, output_json)


if __name__ == "__main__":
    main()
