"""
Создает json с уже обработанными id. Необходимо при парсинге работ через id (для обхода
неработающих страниц).
"""
import os
import json
import glob
import sys


def collect_ids_from_jsons(downloads_dir: str) -> set:
    """
    Проходит по всем файлам .json в папке downloads_dir,
    извлекает из каждого значение поля "id" и возвращает множество этих ID.
    """
    ids = set()
    pattern = os.path.join(downloads_dir, "*.json")
    for path in glob.glob(pattern):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            raw = data.get("id")
            if raw is None:
                print(f"[!] в {os.path.basename(path)} нет поля 'id', пропускаем")
                continue
            # Приводим к целому
            id_val = int(raw)
            ids.add(id_val)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"[!] Не удалось прочитать или преобразовать id в {os.path.basename(path)}: {e}")
        except IOError as e:
            print(f"[!] Ошибка ввода-вывода при открытии {os.path.basename(path)}: {e}")

    return ids


def save_processed_ids(ids: set, output_path: str):
    """
    Сохраняет отсортированный список ID в JSON-файл output_path.
    """
    sorted_ids = sorted(ids)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(sorted_ids, f, ensure_ascii=False, indent=2)

    print(f"[✓] Сохранено {len(sorted_ids)} ID в {output_path}")


def main():
    if len(sys.argv) not in (1, 3):
        print("Использование:")
        print("  python ids-collection.py <downloads_dir> <output_json>")
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

    ids = collect_ids_from_jsons(downloads_dir)
    save_processed_ids(ids, output_json)


if __name__ == "__main__":
    main()
