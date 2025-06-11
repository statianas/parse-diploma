"""
Id-парсер pdf c сайта кафедры Системного программирования СПбГУ (2007–2024).
— Принимает куки
— Переходит на страницы с необработанными id и скачивает pdf.
— Обрабатывает pdf в модулях parser_pdf.py и parser_diploma.py (парсит текст и титульник).
"""

import requests
import os
import time
import sys
import json
import parser_web
import parser_diploma
from pathlib import Path


def load_processed_ids(json_path: str) -> set:
    """
    Загружает JSON-файл с уже обработанными ID.
    """
    if not os.path.exists(json_path):
        return set()
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return set(data)
    except (json.JSONDecodeError, IOError):
        print(f"[!] Не удалось прочитать {json_path}, начинаем с пустого списка.")
        return set()


def save_processed_ids(processed: set, json_path: str):
    """
    Сохраняет множество processed в JSON-файл (списком).
    """
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(sorted(processed), f, ensure_ascii=False, indent=2)


def process_pdf(file_path: str, id: str):
    """
    Соединяет год и заголовок для дальнейшей обработки (используя уже написанные функции).
    """
    title, year = parser_diploma.extract_title_and_year(file_path)
    title = title + f"[{year}]"

    topic = "Системное программирование"

    parser_web.process_pdf(Path(file_path), title, topic, id)


def download_and_process(start_id: int,
                         end_id: int,
                         save_dir: str = "downloads",
                         json_path: str = "processed_ids.json",
                         delay: float = 0.5,
                         max_retries=3):
    """
    Для каждого thesis_id в диапазоне:
      1) пропускает, если ID уже в processed_ids.json; иначе скачивает PDF;
      2) вызывает process_pdf;
      3) добавляет ID в JSON.
    """
    os.makedirs(save_dir, exist_ok=True)

    processed = load_processed_ids(json_path)

    for thesis_id in range(start_id, end_id + 1):
        if thesis_id in processed:
            print(f"[{thesis_id}] Уже обработан, пропускаем.")
            continue

        url = f"https://se.math.spbu.ru/thesis_download?thesis_id={thesis_id}"
        success = False
        backoff = delay

        pdf_path = None
        thesis_id = ""

        # Пробуем скачать
        for attempt in range(1, max_retries + 1):
            try:
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200 and "pdf" in resp.headers.get("Content-Type", "").lower():
                    pdf_path = os.path.join(save_dir, f"{thesis_id}.pdf")
                    with open(pdf_path, "wb") as fout:
                        fout.write(resp.content)
                    print(f"[{thesis_id}] Скачан → {pdf_path}")
                    success = True
                else:
                    print(f"[{thesis_id}] Нет PDF или статус {resp.status_code}")
                break

            except requests.exceptions.ConnectTimeout as e:
                print(f"[{thesis_id}] Попытка {attempt}/{max_retries}: таймаут соединения.")
            except requests.RequestException as e:
                print(f"[{thesis_id}] Ошибка запроса: {e}")
                break

            # задержка перед следующей попыткой
            time.sleep(backoff)
            backoff *= 2

        if not success:
            print(f"[{thesis_id}] Не удалось скачать после {max_retries} попыток, пропускаем.")
            continue

        # Обработка
        try:
            process_pdf(pdf_path, thesis_id)
            print(f"[{thesis_id}] Обработан успешно.")
            processed.add(thesis_id)
            save_processed_ids(processed, json_path)
        except Exception as e:
            print(f"[{thesis_id}] Ошибка в process_pdf: {e}")

        # Небольшая пауза между ID
        time.sleep(delay)


def main():
    if len(sys.argv) != 3:
        print("Использование:")
        print("  python parser_web_id.py <start_id> <end_id>")
        sys.exit(1)

    try:
        start_id = int(sys.argv[1])
        end_id = int(sys.argv[2])
    except ValueError:
        print("Ошибка: <start_id> и <end_id> должны быть целыми числами.")
        sys.exit(1)

    if start_id > end_id:
        print("Ошибка: start_id не может быть больше end_id.")
        sys.exit(1)

    download_and_process(start_id, end_id)


if __name__ == "__main__":
    main()
