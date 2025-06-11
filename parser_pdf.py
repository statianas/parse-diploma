"""
Парсер для pdf-файлов. Парсит 2 раздела "Введение" и "Обзор" (или похожий).
1) Пытается найти и прочитать содержание.
2) По содержанию находит нужные нам разделы.
3) Если содержания не нашлось, ищет среди жирных заголовков нужные нам во всем pdf.
"""


import fitz
import re
from pathlib import Path
from collections import Counter
from statistics import median


# Находим страницу содержания по ключевым словам
def find_content(doc):
    toc_idx = None
    for i, page in enumerate(doc):
        txt = page.get_text("text")
        if re.search(r'\b(Оглавление|Содержание)\b', txt, re.IGNORECASE) or \
            re.search(r'\b(Введение)\b', txt, re.IGNORECASE) and \
                re.search(r'\b(Заключение)\b', txt, re.IGNORECASE):
            toc_idx = i
            break
    if toc_idx is None:
        raise RuntimeError("Не найдена страница с оглавлением")
    return toc_idx


def get_real_page(doc, toc_idx: int) -> list:
    """
    Ищем номер страницы (блок с числом внизу) на самой странице.

    :param doc: Сам документ.
    :param toc_idx: Индекс страницы по ходу чтения pdf.
    :return: Список вариантов для номера страницы.
    """
    page = doc[toc_idx]
    blocks = page.get_text("blocks")

    page_numbers = []
    for b in blocks:
        x0, y0, x1, y1, text, _, _ = b
        for ln in text.splitlines():
            if re.fullmatch(r"\d|.\d", ln.strip()):
                if len(ln) == 2:
                    if ln[1].isnumeric():
                        num = int(ln[1])
                    else:
                        continue
                else:
                    num = int(ln.strip())
                page_numbers.append({
                    "num": num,
                    "x0": x0, "x1": x1, "y0": y0, "y1": y1
                })

    # Можно отобрать те, у кого y0 < page_height*0.1 или y1 > page_height*0.9
    ph = page.rect.height

    page_num_loc = [
        pn for pn in page_numbers
        if pn["y0"] < 0.1 * ph or pn["y1"] > 0.9 * ph
    ]

    return page_num_loc


def get_real_content_page(doc):
    """
    Ищем страницу содержания посредством перебора пар, поскольку на самой странице
    содержания блока с цифрой может просто не быть, но может быть на следующей странице.

    :param doc: Сам документ.
    :return: Номер страницы содержания.
    """
    toc_idx = find_content(doc)
    page_num_loc_cont = get_real_page(doc, toc_idx)

    if len(page_num_loc_cont) == 0:
        print(f"Нет вариантов для номера страницы содержания, ищем на следующей")
        page_num_loc_cont_next = get_real_page(doc, toc_idx + 1)

        if len(page_num_loc_cont_next) != 0:
            return page_num_loc_cont_next[0]['num'] - 1
        print(f"Не удалось распознать номера страниц ни на содержании, ни на следующей")
        return None

    if len(page_num_loc_cont) > 1:
        print(f"Двусмысленность в номере страницы содержания, смотрим на следующую")
        page_num_loc_cont_next = get_real_page(doc, toc_idx + 1)

        if len(page_num_loc_cont_next) > 1:
            print(f"Двусмысленность в странице идущей за страницей с содержанием")
            # пробуем все же найти нужную пару
            for cont_page in page_num_loc_cont:
                for next_page in page_num_loc_cont_next:
                    if abs(cont_page['num'] - next_page['num']) == 1:
                        return cont_page['num']
            print(f"Не нашелся номер содержания посредством перебора пар")
            return None
        return page_num_loc_cont_next[0]['num'] - 1

    return page_num_loc_cont[0]['num']


def processing_block(blocks):
    """
    Обрабатываем блоки страницы содержания и конвертируем их в словарь.
    Также обрабатываем старые версии оформления pdf.

    :param blocks: Блоки из оглавления pdf.
    :return: Содержание pdf в виде списка словарей.
    """
    entries = []
    for b in blocks:
        x0, y0, x1, y1, text, _, _ = b

        old_case = False
        # блок должен содержать буквы и цифры
        if not re.search(r'[А-Яа-яA-Za-z]', text) or not re.search(r'\d', text):
            continue
        # поддерживаем старые версии
        if '...' in text:
            text = re.sub(r'\.{2,}', '\n', text)
            old_case = True

        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

        # если вдруг цифры из оглавления стали отдельными линиями
        if len(lines) < 2 and not old_case:
            continue

        title = lines[0]
        begin = 1

        # если склеилось оглавление
        if re.search(r'\b(Оглавление|Содержание)\b', title, re.IGNORECASE):
            title = lines[1]
            begin = 2

        # слишком маленький блок, может быть например номером текущей страницы
        if len(title) <= 2:
            title = lines[1]
            begin = 2

        num_lines = len(lines)
        tail = 0

        # парсим все линии блока
        while begin < num_lines:
            page_num = None
            # найдем первое чистое число в оставшихся строках
            for i in range(len(lines[begin:])):
                m = re.match(r'^\s*(\d+)\s*$', lines[begin+i])
                if m:
                    page_num = int(m.group(1))
                    tail = i
                    break
            if page_num is None:
                begin = begin + tail + 2
                continue

            entries.append({
                "title": title,
                "page": page_num,
                "y0":    y0
            })

            title = lines[begin+tail+1 if begin+tail+1 < num_lines else 0]
            begin = begin+tail+2

    return entries


def repair_content(doc):
    """
    Восстанавливаем лист словарей в единый словарь.

    :param doc: Сам документ.
    :return: Словарь, где ключи - заголовки диплома.
    """
    toc_idx = find_content(doc)
    page = doc[toc_idx]

    blocks = page.get_text("blocks")  # [(x0,y0,x1,y1, text, block_no), ...]
    entries = processing_block(blocks)

    if not entries:
        raise RuntimeError("Не удалось распарсить ни одного пункта оглавления")

    # сортируем по y0 (чтобы сохранить верх→низ)
    entries.sort(key=lambda e: e["y0"])

    # отбрасываем последний пункт, если его page == toc_idx+1 (номер страницы оглавления)
    entries = [e for e in entries if get_page_doc(doc, e["page"], toc_idx) != toc_idx]
    return [(e["title"], e["page"]) for e in entries]


def get_page_doc(doc, num_real: int, num_cont=None):
    """
    Получаем индекс страницы (не тот, что в самом pdf) для итерации.

    :param doc: Сам документ.
    :param num_real: Номер страницы в самом pdf.
    :param num_cont: Индекс страницы содержания.
    :return: Индекс страницы искомой страницы.
    """
    if not num_cont:
        num_cont = find_content(doc)
    real_num_cont = get_real_content_page(doc)
    return (num_cont - real_num_cont) + num_real


# Находим диапазон страниц для введения
def get_introduction_range(entries: list):
    """
    Ищем диапазон страниц, на которых располагается "Введение".

    :param entries: Содержание.
    :return: Индекс введения в содеражании, диапазон в виде двух чисел (включая концы), заголовок,
    который используется в содержании.
    """
    intro_keywords = ['введение', 'вступление']
    for i, (title, page) in enumerate(entries):
        title_lower = title.lower()
        if any(kw in title_lower for kw in intro_keywords):
            if page >= 10:
                raise ValueError(f"Номер страницы введения должен быть меньше 10, найдено: {page}")
            if i + 1 < len(entries):
                next_page = entries[i + 1][1]
                end_page = next_page - 1
            else:
                end_page = None
            return i, page, end_page, title_lower

    raise ValueError("Раздел 'Введение' не найден в содержании")


# Находим диапазон страниц для обзора или метода
def get_review_range(entries: list):
    """
    Ищем диапазон страниц, на которых располагается "Обзор" или похожие разделы.

    :param entries: Содержание.
    :return: Заголовок этого раздела, который используется в содержании, диапазон в виде двух чисел (включая концы).
    """
    review_keywords = ['обзор', 'литератур', 'исследований']
    not_review_keywords = ['список литературы']
    fallback_keywords = ['постановка', 'задач', 'цель']

    # шаблон для вложенных глав типа "2.1" или "2.1.2"
    ignore_pattern = re.compile(r'^\s*\d+\.\d')

    # индекс введения в содержании
    intro_index, _, _, _ = get_introduction_range(entries)

    # поиск обзора
    for j in range(intro_index + 1, len(entries)):
        title, page = entries[j]
        # пропускаем вложенные главы
        if ignore_pattern.match(title):
            continue
        # пропускаем главы, содержащие цели и задачи диплома
        if any(kw in title.lower() for kw in review_keywords) and \
                not any(kw in title.lower() for kw in not_review_keywords):
            i = 0
            # ищем следующий раздел для нахождения правой границы
            while True:
                next_title = entries[j + 1 + i][0] if j + i + 1 < len(entries) else None
                if not next_title:
                    break
                if ignore_pattern.match(next_title):
                    i += 1
                    continue

                next_page = entries[j + i + 1][1] if j + i + 1 < len(entries) else None
                end_page = next_page - 1 if next_page is not None else None

                if end_page < page:
                    end_page = page
                title = 'Обзор'
                return title.lower(), page, end_page

    print('Обзор не найден, ищем "Метод" или похожие разделы')

    # fallback – поиск "Метода" или похожих разделов
    for j in range(intro_index + 1, len(entries)):
        title, _ = entries[j]
        if ignore_pattern.match(title):
            continue
        # если нашли раздел с целями, то следующий раздел нам подходит
        if any(kw in title.lower() for kw in fallback_keywords):
            title_new = entries[j + 1][0] if j + 1 < len(entries) else None
            page_new = entries[j + 1][1] if j + 1 < len(entries) else None
            i = 0
            # ищем следующий раздел для нахождения правой границы
            while True:
                next_title = entries[j + 2 + i][0] if j + 2 + i < len(entries) else None
                if not next_title:
                    break
                if ignore_pattern.match(next_title):
                    i += 1
                    continue

                next_page = entries[j + 2 + i][1] if j + 2 + i < len(entries) else None
                end_page = next_page - 1 if next_page is not None else None

                if end_page < next_page:
                    end_page = next_page
                return title_new, page_new, end_page

        # либо нам подходит раздел после введения, не содержащий цели и задачи диплома
        if not any(kw in title.lower() for kw in fallback_keywords):
            title_new = entries[j][0]
            page_new = entries[j][1]
            i = 0
            while True:
                next_title = entries[j + i + 1][0] if j + 1 + i < len(entries) else None
                if not next_title:
                    break
                if ignore_pattern.match(next_title):
                    i += 1
                    continue

                next_page = entries[j + 1 + i][1] if j + 1 + i < len(entries) else None
                end_page = next_page - 1 if next_page is not None else None

                if end_page < next_page:
                    end_page = next_page
                return title_new, page_new, end_page

    raise ValueError("Разделы 'Обзор' или 'Метод' не найдены в содержании")


def get_pages_for_parsing(doc):
    """
    Получаем листы со страницами, которые необходимо парсить.

    :param doc: Сам документ.
    :return: Пара заголовков глав для парсинга, лист страниц введения, лист страниц обзора (если есть),
    флаг наличия содержания, флаг наличия "Введения".
    """
    entries = None
    flag_content = True

    flag_review = True
    review_pages = None
    beg_review, end_review = None, None

    review_title = 'обзор'

    try:
        entries = repair_content(doc)
    except Exception as err:
        print(err)

    # если нет содержания, выполняем поиск по всему pdf
    if not entries:
        intro_title = 'введение'
        review_title = 'обзор'

        beg_intro, end_intro = find_section_range(doc, intro_title, False)

        try:
            beg_review, end_review = find_section_range(doc, review_title, False)
        except Exception as err:
            print(f"Ошибка при поиске 'Обзора' при отсутствии содержания: {err}")
            flag_review = False

        flag_content = False
    else:
        _, beg_intro, end_intro, intro_title = get_introduction_range(entries)
        beg_intro, end_intro = get_page_doc(doc, beg_intro), get_page_doc(doc, end_intro)

        try:
            review_title, beg_review, end_review = get_review_range(entries)
            beg_review, end_review = get_page_doc(doc, beg_review), get_page_doc(doc, end_review)
        except Exception as err:
            print(f"Ошибка при поиске 'Обзора' при найденном содержании: {err}")
            flag_review = False

    if beg_intro and end_intro:
        intro_pages = list(range(beg_intro, end_intro + 1))
    else:
        intro_pages = None

    # поскольку не у всех документов есть "Обзор" и похожие разделы
    if flag_review:
        review_pages = list(range(beg_review, end_review + 1))

    return (intro_title, review_title), intro_pages, review_pages, flag_content, flag_review


def extract_paragraphs_from_pages(pdf_path: Path, page_numbers: list[int], flag_content=True) -> list[str]:
    """
    Извлекает блоки текстов из указанных страниц PDF, сохраняя их целиком,
    склеивая незаконченные предложения между блоками и страницами,
    и отбрасывая подписи к картинкам (центрованные короткие блоки).
    Абзац гарантированно заканчивается точкой, вопросительным или
    восклицательным знаком. Если последний блок на странице не заканчивается
    таким знаком, он склеивается с первым непустым абзацем следующей страницы.

    :param pdf_path: Путь к PDF-файлу.
    :param page_numbers: Список номеров страниц, из которых нужно извлекать текст;
    :param flag_content: Флаг наличия содержания.
    :return: Список строк, каждая строка – извлечённый блок текста.
    """
    doc = fitz.open(pdf_path)
    paragraphs: list[str] = []

    # Шаблон для проверки окончания предложения
    sentence_endings = re.compile(r'[\.!?]$')

    # Эвристики:
    FONT_SIZE_DIFF_THRESHOLD = 1.0    # Порог отклонения шрифта от доминирующего
    MIN_BLOCK_CHARS = 15              # Блоки короче этого порога сразу пропускаются
    MIN_BLOCK_WIDTH_RATIO = 0.5       # Блоки уже половины страницы по ширине считаются «узкими» и фильтруются
    CAPTION_MAX_CHARS = 60            # Максимальное число символов в подписи к картинке
    CENTER_TOLERANCE_RATIO = 0.7      # Допуск по смещению центра блока относительно центра страницы
    MIN_CYRILLIC_RATIO = 0.5
    LIST_START_PATTERN = re.compile(r'^\s*(?:\d+[\)]|[-•–])')
    GAP_MULTIPLIER = 2.5

    # Незавершённый текст с предыдущей страницы
    carryover = ""

    # Предыдущий блок оканчивается переносом
    prev_ended_with_hyphen = False

    for page_num in page_numbers:
        page = doc.load_page(page_num)
        page_dict = page.get_text("dict")
        blocks = page_dict["blocks"]

        page_rect = page.rect
        page_width = page_rect.width

        # Собираем все размеры шрифтов на странице
        all_font_sizes = []
        all_font_names = []

        for block in blocks:
            # Нужны текстовые блоки
            if block.get("type") != 0:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    all_font_sizes.append(span["size"])
                    all_font_names.append(span["font"])
        if not all_font_sizes:
            # Нет текста на странице
            continue

        # Определяем доминирующий размер шрифта
        font_counter = Counter(all_font_sizes)
        dominant_font_size = font_counter.most_common(1)[0][0]

        # Определяем доминирующий шрифт
        font_name_counter = Counter(all_font_names)
        dominant_font_name = font_name_counter.most_common(1)[0][0]

        # Фильтруем блоки: по размеру текста, шрифту, ширине и «центрированности» (подписи)
        prelim_blocks = []
        for block in blocks:
            if block.get("type") != 0:
                continue

            # Соберём весь текст блока и все размеры шрифтов внутри, сохраняя переносы строк
            block_font_sizes = []
            line_texts = []
            block_font_names = []

            for line in block["lines"]:
                span_texts = []
                for span in line["spans"]:
                    block_font_sizes.append(span["size"])
                    block_font_names.append(span["font"])
                    # Если содержания нет, возможно сбилась кодировка
                    if not flag_content:
                        raw_text = span["text"]
                        try:
                            # Пытаемся перекодировать из Latin-1 -> CP1251
                            span_text = raw_text.encode("latin-1").decode("cp1251", errors="ignore")
                        except Exception:
                            # Если по какой-то причине не получилось — оставляем как есть
                            span_text = raw_text
                    else:
                        span_text = span["text"]
                    span_texts.append(span_text)
                # Собираем текст одной строки
                line_text = "".join(span_texts).strip()
                line_texts.append(line_text)
            # Объединяем строки с \n — таким образом сохраняем переносы строк
            total_text = "\n".join(line_texts)

            x0, y0, x1, y1 = block["bbox"]

            # Если текст оканчивается переносом и находится в начале страниц и при этом не подпись -
            # берем его сразу, поскольку иначе можно случайно отфильтровать
            if prev_ended_with_hyphen and x0 < 90 and "рис." not in total_text.lower():
                prelim_blocks.append({
                                        "bbox": block["bbox"],
                                        "text": total_text})
                prev_ended_with_hyphen = total_text.strip().endswith('-')

                continue

            if not total_text:
                continue

            # русский текст
            chars = [ch for ch in total_text if ch.isalpha()]
            if chars:
                cyrillic_count = sum(1 for ch in chars if "А" <= ch <= "я" or ch in "Ёё")
                if cyrillic_count / len(chars) < MIN_CYRILLIC_RATIO:
                    continue

            # Длины без учёта переносов
            first_line = total_text.split("\n", 1)[0].lstrip()
            last_line = total_text.split("\n")[-1].strip()

            cnt_open = total_text.count("(")
            cnt_close = total_text.count(")")

            # Если вдруг скобка одна, то скорее всего продолжение
            # в следующей строке и такие блоки лучше не фильтровать
            single_bracket = (cnt_open + cnt_close == 1)

            # Отсеиваем очень короткие блоки
            if len(total_text.replace("\n", "").strip()) < MIN_BLOCK_CHARS:
                if not LIST_START_PATTERN.match(first_line) and not last_line.endswith(":")\
                        and not single_bracket:
                    continue

            # Отсеиваем подписи
            if first_line.startswith("рис."):
                continue

            # Средний размер шрифта в блоке
            avg_block_font_size = sum(block_font_sizes) / len(block_font_sizes)
            block_name_counter = Counter(block_font_names)
            block_dominant_name = block_name_counter.most_common(1)[0][0]
            if (abs(avg_block_font_size - dominant_font_size) > FONT_SIZE_DIFF_THRESHOLD
                    or block_dominant_name != dominant_font_name):
                # Части листов лучше сразу не отбрасывать
                if not LIST_START_PATTERN.match(first_line):
                    continue

            # Отсеиваем узкие блоки (часто колонки, подписи под изображениями в колонках)
            x0, y0, x1, y1 = block["bbox"]
            block_width = x1 - x0
            if block_width < MIN_BLOCK_WIDTH_RATIO * page_width:
                if not LIST_START_PATTERN.match(first_line) and not last_line.endswith(":") and not single_bracket:
                    # print(total_text, 'узкие')
                    continue

            prelim_blocks.append({
                "bbox": block["bbox"],
                "text": total_text
            })

            prev_ended_with_hyphen = total_text.strip().endswith('-') or total_text.strip().endswith('-')

        if not prelim_blocks:
            continue

        # Определяем медианный вертикальный зазор между блоками для фильтрации подписей
        sorted_prelim = sorted(prelim_blocks, key=lambda b: b["bbox"][1])
        gaps = []
        for i in range(1, len(sorted_prelim)):
            prev_y1 = sorted_prelim[i - 1]["bbox"][3]
            curr_y0 = sorted_prelim[i]["bbox"][1]
            gaps.append(max(0, int(curr_y0) - int(prev_y1)))
        median_gap = median(gaps) if gaps else 0

        # Окончательная фильтрация
        filtered_blocks = []
        for i, tb in enumerate(sorted_prelim):
            total_text = tb["text"]
            x0, y0, x1, y1 = tb["bbox"]
            plain_len = len(total_text.replace("\n", "").strip())

            block_center_x = (x0 + x1) / 2
            page_center_x = page_width / 2
            gap_to_prev = 0
            if i > 0:
                prev_y1 = sorted_prelim[i - 1]["bbox"][3]
                gap_to_prev = max(0, y0 - prev_y1)

            # Вычисляем центрированность блока
            is_centered = abs(block_center_x - page_center_x) < CENTER_TOLERANCE_RATIO * page_width

            # Вычисляем есть ли числа с точкой внутри
            has_num_dot_inside = bool(re.search(r"\d+\.", total_text)) and not total_text.strip().endswith(".")

            # Условие «подписи»:
            #  - одна линия,
            #  - длина <= CAPTION_MAX_CHARS,
            #  - центрирован,
            #  - gap_to_prev > GAP_MULTIPLIER * median_gap,
            #  - внутри есть «число.»
            if ("\n" not in total_text
                    and plain_len <= CAPTION_MAX_CHARS
                    and is_centered
                    and gap_to_prev > GAP_MULTIPLIER * median_gap
                    and has_num_dot_inside):
                continue

            filtered_blocks.append(tb)

        # Формируем абзацы из отфильтрованных блоков, склеивая незаконченные предложения.
        page_paragraphs = []
        temp_para = carryover
        prev_ended_with_hyphen = False
        page_center_x = page_width / 2

        for blk in filtered_blocks:
            if not flag_content:
                raw_text = blk["text"]
                try:
                    # Пытаемся «перекодировать» из Latin-1 → CP1251
                    blk_text = raw_text.encode("latin-1").decode("cp1251", errors="ignore")
                except Exception:
                    # Если по какой-то причине не получилось — оставляем как есть
                    blk_text = raw_text
            else:
                blk_text = blk["text"]

            x0, _, x1, _ = blk["bbox"]
            block_center_x = (x0 + x1) / 2
            is_centered = abs(block_center_x - page_center_x) < CENTER_TOLERANCE_RATIO * page_width

            # Если предыдущий блок заканчивался дефисом, и текущий не центрирован,
            # то просто берём весь следующий блок целиком в temp_para
            if prev_ended_with_hyphen and not is_centered:
                if temp_para:
                    temp_para = f"{temp_para}\n{blk_text}"
                else:
                    temp_para = blk_text
                # Обновляем флаг для возможной цепочки дефисов
                prev_ended_with_hyphen = blk_text.strip().endswith('-')
                continue
            if not blk_text:
                continue

            # Если блок начинается с буллета ('-' или '•'),
            # считаем его отдельным абзацем независимо от пунктуации:
            first_line = blk_text.split("\n", 1)[0].lstrip()
            if first_line.startswith('-') or first_line.startswith('•'):
                # Сначала, если temp_para уже заканчивается на точку/?/!
                if temp_para and sentence_endings.search(temp_para):
                    page_paragraphs.append(temp_para)
                    temp_para = ""
                # Добавляем сам буллет-абзац (с переносами внутри, если они были)
                page_paragraphs.append(blk_text)
                continue

            # Если temp_para не пуст, пытаемся склеить его с текущим блоком
            if temp_para:
                candidate = f"{temp_para}\n{blk_text}"
            else:
                candidate = blk_text

            # Проверяем, заканчивается ли на точку/?/!
            last_line = candidate.split("\n")[-1]
            if sentence_endings.search(last_line.strip()):
                # Завершённый абзац
                page_paragraphs.append(candidate)
                temp_para = ""
            else:
                # Всё ещё незаконченный абзац — сохраняем в temp_para
                temp_para = candidate
            prev_ended_with_hyphen = blk_text.strip().endswith('-') or blk_text.strip().endswith('-')

        # После всех блоков страницы: temp_para может быть незавершённым
        carryover = temp_para

        # Добавляем все полные абзацы из этой страницы в общий список
        paragraphs.extend(page_paragraphs)

    # После перебора всех страниц: если carryover остаётся, добавляем его как последний абзац
    if carryover:
        paragraphs.append(carryover)

    return paragraphs


def find_section_range(doc, section_title: str, flag_content=True):
    """
    Находим диапазон для "Введения" в случае если содержания найти не удается, либо не получается его спарсить.
    Для этого ищем среди потенциальных заголовков.

    :param doc: Сам документ.
    :param section_title: Название раздела, который требуется найти.
    :param flag_content: Флаг наличия содержания
    :return:
    """
    # Регулярное выражение для заголовка с номером раздела перед именем
    heading_with_number = re.compile(r'\b\d+(\.\d+)*\s*' + re.escape(section_title), re.IGNORECASE)

    total_pages = doc.page_count

    page_found = None

    # Найдем страницу, где впервые встречается section_title как заголовок
    for zero_based_page in range(total_pages):
        page = doc.load_page(zero_based_page)
        # Получаем всю текстовую структуру страницы в виде dict, чтобы вытащить спаны с информацией о шрифте
        text_dict = page.get_text("dict")
        for block in text_dict["blocks"]:
            # пропускаем не текстовые блоки
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    raw_text = span["text"]
                    try:
                        # Пытаемся «перекодировать» из Latin-1 → CP1251
                        span_text = raw_text.encode("latin-1").decode("cp1251", errors="ignore")
                    except Exception:
                        # Если по какой-то причине не получилось — оставляем как есть
                        span_text = raw_text

                    span_font = span["font"]

                    # Проверяем, найдено ли ключевое слово section_title
                    if re.search(re.escape(section_title), span_text.lower(), re.IGNORECASE):
                        # Если шрифт жирный
                        if "bold" in span_font.lower() or "f44" in span_font.lower():
                            page_found = zero_based_page
                            break
                        # Или перед заголовком стоит номер раздела
                        if heading_with_number.search(span_text):
                            page_found = zero_based_page
                            break
                if page_found is not None:
                    break
            if page_found is not None:
                break
        if page_found is not None:
            if flag_content:
                flag_content = False
                continue
            break

    if page_found is None:
        raise ValueError(f"Заголовок «{section_title}» не найден ни в одном жирном спане и без номера раздела")

    # Найдем первую страницу после page_found, где появляется любой следующий заголовок
    next_heading_page = None

    # Регулярное выражение для любого нового заголовка с номером раздела в начале строки
    any_heading_pattern = re.compile(r'^\s*\d+(\.\d+)*\[а-яА-я]+\b')

    for zero_based_page in range(page_found + 1, total_pages):
        page = doc.load_page(zero_based_page)
        text_dict = page.get_text("dict")
        found_heading_here = False

        for block in text_dict["blocks"]:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    raw_text = span["text"]
                    try:
                        # Пытаемся «перекодировать» из Latin-1 → CP1251
                        span_text = raw_text.encode("latin-1").decode("cp1251", errors="ignore")
                    except Exception:
                        # Если по какой-то причине не получилось - оставляем как есть
                        span_text = raw_text
                    span_font = span["font"]
                    # Если шрифт жирный - принимаем это за заголовок любого уровня
                    if "bold" in span_font.lower() or "f44" in span_font.lower():
                        next_heading_page = zero_based_page
                        found_heading_here = True
                        break
                    # Или перед заголовком стоит номер раздела
                    if any_heading_pattern.match(span_text):
                        next_heading_page = zero_based_page
                        found_heading_here = True
                        print(span_text)
                        break
                if found_heading_here:
                    break
            if found_heading_here:
                break
        if found_heading_here:
            break

    if next_heading_page is not None:
        end_page = next_heading_page - 1
    else:
        end_page = None

    return page_found, end_page


def parse(pdf_name: str):
    """
    Основная функция, запускающая весь парсинг.

    :param pdf_name: Путь к pdf файлу.
    :return: Заголовки искомых разделов (1 или 2), лист с блоками текста "Введения", лист с блоками текста "Обзора"
    """
    print(f"******* {str(pdf_name)} **********")

    doc = fitz.open(pdf_name)
    review_paragraphs = None

    titles, intro_pages, review_pages, flag_content, flag_review = get_pages_for_parsing(doc)
    intro_paragraphs = extract_paragraphs_from_pages(Path(pdf_name), intro_pages, flag_content)

    if flag_review:
        review_paragraphs = extract_paragraphs_from_pages(Path(pdf_name), review_pages, flag_content)

    return titles, intro_paragraphs, review_paragraphs

