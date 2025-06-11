"""
Парсер титульников дипломов. Необходим для парсинга страничек через id.
"""

import fitz
import re
import sys


def extract_title_and_year(pdf_path):
    """
    Извлекаем первую страницу диплома и возвращаем тему (заголовок) и год. Как правило, год в самом низу страницы.
    Заголовок же - самый большой центрированный по размеру шрифта блок.

    :param pdf_path: Путь к pdf.
    :return: Заголовок диплома и год защиты.
    """
    doc = fitz.open(pdf_path)
    if doc.page_count == 0:
        return None, None

    page = doc[0]
    W, H = page.rect.width, page.rect.height
    data = page.get_text("dict")

    # Собираем все текстовые спаны, ищем max_size
    candidates = []
    max_size = 0.0

    for b in data["blocks"]:
        if b.get("type") != 0:
            continue
        for line in b["lines"]:
            for span in line["spans"]:
                txt = span["text"].strip()
                if not txt:
                    continue
                size = span["size"]
                bbox = span["bbox"]  # [x0, y0, x1, y1]
                candidates.append({
                    "text": txt,
                    "size": size,
                    "bbox": bbox
                })
                if size > max_size:
                    max_size = size

    # Отбираем все спаны с размером примерно max_size
    title_spans = [
        c for c in candidates
        if abs(c["size"] - max_size) < 1e-3
    ]

    # Фильтруем по горизонтальной центрированности
    center_tol = W * 0.1
    title_spans = [
        c for c in title_spans
        if abs((c["bbox"][0] + c["bbox"][2]) / 2 - W/2) <= center_tol
    ]

    # Если не нашли ни одного центрированного, пробуем взять все с max_size
    if not title_spans:
        title_spans = [
            c for c in candidates
            if abs(c["size"] - max_size) < 1e-3
        ]

    title = None
    if title_spans:
        # Сортируем по y0 (вертикаль), затем x0 (горизонталь)
        spans = sorted(title_spans, key=lambda c: (c["bbox"][1], c["bbox"][0]))
        # Группируем в строки по близости y0
        lines = []
        line_tol = max_size * 0.5  # допускаем половину размера шрифта
        current = [spans[0]]
        for prev, cur in zip(spans, spans[1:]):
            if abs(cur["bbox"][1] - prev["bbox"][1]) <= line_tol:
                current.append(cur)
            else:
                lines.append(current)
                current = [cur]
        lines.append(current)

        # В каждой строке сортируем по x0 и соединяем через пробел
        parts = []
        for ln in lines:
            ln_sorted = sorted(ln, key=lambda c: c["bbox"][0])
            parts.append(" ".join(c["text"] for c in ln_sorted))

        # Собираем финальный заголовок
        title = " ".join(parts)

    # Теперь ищем год 20xx — сначала внизу страницы
    year = None
    for c in candidates:
        if c["bbox"][3] >= H * 0.8:  # y1 ≥ 80% высоты
            m = re.search(r"\b20\d{2}\b", c["text"])
            if m:
                year = m.group()
                break

    # Если не нашли внизу — ищем по всему тексту
    if not year:
        for c in candidates:
            m = re.search(r"\b20\d{2}\b", c["text"])
            if m:
                year = m.group()
                break

    return title, year


def main():
    if len(sys.argv) != 2:
        print("Использование: python extract_title_year.py <путь_к_pdf>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    title, year = extract_title_and_year(pdf_path)

    print("Заголовок (title): ", title if title else "<не найден>")
    print("Год (year): ", year if year else "<не найден>")


if __name__ == "__main__":
    main()
