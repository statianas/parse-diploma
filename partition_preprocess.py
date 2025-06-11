"""
Обработка (чистка) текста и разделение на абзацы. Скип сломанных json.
"""
import os
import json
import re
import sys
import argparse
import unicodedata
from razdel import sentenize

# Пороговые константы
MIN_FILE_SIZE = 1.5 * 1024  # байты
MIN_BLOCK_LEN = 600
MAX_BLOCK_LEN = 900         # символов без пробелов
LARGE_BLOCK_LEN = 1200      # слишком большой блок
MIN_SENT_WORDS = 3
MAX_NON_CYRILLIC_RATIO = 0.6
DIGIT_RATIO_CHECK = 0.7
MIN_PARAGRAPH_COUNT = 2
MIN_TRAILING_LEN = 200

# Регулярки
RE_REFERENCES = re.compile(r'\[\d+(-\d+)?(?:,\s*\d+(-\d+)?)*\]')
RE_CAPTION = re.compile(r'^\s*(Рис\.|Табл\.)')
RE_HEADING_NUM = re.compile(r'^\s*\d+(\.\d+)*\s+')
RE_HEADING_WORD = re.compile(r'^[\sA-ZА-ЯЁ]{2,}$')
RE_LIST_MARKER = re.compile(r'^\s*([-•]|\d+\.)\s*')
RE_MULTI_DOTS = re.compile(r'\.{4,}')
RE_SPACE_PUNCT = re.compile(r'([,;:.!?])([^\s])')
RE_CONTROL_CHARS = re.compile(r'[\u0000-\u001F\u007F-\u009F]')
VOWELS = set("аеёиоуыэюяAEЁИОУЫЭЮЯ")


def normalize_unicode(text: str) -> str:
    return unicodedata.normalize('NFC', text)


def clean_raw_text(text: str) -> str:
    """
    Первично очищаем исходный текст от символов переноса и табуляции.

    :param text: Сам текст.
    :return: Очищенный текст.
    """
    # Объединяем "-\n" -> ""
    text = text.replace('-\n', '')

    # Заменяем \n -> пробел
    text = text.replace('\n', ' ')

    # \t и \u00A0 -> пробел
    text = text.replace('\t', ' ').replace('\u00A0', ' ')

    # Сжимаем подряд идущие пробелы
    text = re.sub(r'\s+', ' ', text)

    # Сжать пробелы повторно (на всякий случай)
    text = re.sub(r' {2,}', ' ', text)

    return text.strip()


def remove_artifacts(text: str) -> str:
    """
    Вторично очищаем исходный текст от различных заголовков,
    нормализуем, делаем более читаемым.

    :param text: Сам текст.
    :return: Очищенный текст.
    """
    # Unicode-нормализация
    text = normalize_unicode(text)

    # убрать ссылки на литературу
    text = RE_REFERENCES.sub('', text)

    # удалить заголовки (числовые и капсом)
    if RE_HEADING_NUM.match(text) or RE_HEADING_WORD.match(text.strip()):
        return ''

    # пробел после пунктуации
    text = RE_SPACE_PUNCT.sub(r'\1 \2', text)

    # унификация многоточий
    text = RE_MULTI_DOTS.sub('...', text)

    # убрать нечитаемые / контрольные символы
    text = RE_CONTROL_CHARS.sub(' ', text)

    return text.strip()


def sentence_filters(sent: str) -> bool:
    """
    Фильтруем различными способами предложения, полученные с помощью razdel.

    :param sent: Предложение.
    :return: Корректность полученного предложения (bool).
    """
    # пустые
    if not sent.strip():
        return False

    # слишком короткие (< 3 слов)
    if len(sent.split()) < MIN_SENT_WORDS:
        return False

    # проверка не-Кириллицы
    total = len(sent)
    if total > 0:
        non_cyr = sum(1 for c in sent if not re.match(r'[А-Яа-яЁё]', c))
        if non_cyr / total > MAX_NON_CYRILLIC_RATIO:
            return False

    # начинается заглавной русской буквы
    first = sent.strip()[0]
    if not re.match(r'[А-ЯЁ]', first):
        return False

    return True


def split_to_sentences(text: str) -> list:
    """
    Разбиваем на предложения.
    """
    return [s.text.strip() for s in sentenize(text)]


def clean_and_filter_block(block: str, is_last: bool = False) -> list:
    """
    Возвращает список чистых, отфильтрованных предложений из блока.

    :param block: Блок текста.
    :param is_last: Флаг, указывающий на то, является ли предложение последним в блоке.
    :return:
    """
    txt = clean_raw_text(block)
    txt = remove_artifacts(txt)

    if not txt:
        return []

    # Проверка на "много точек подряд" (знак того, что спарсилось введение)
    if re.search(r'(\.\s*){7,}', txt):
        return []

    # цифры составляют большую часть (знак того, что спарсилось введение)
    digits = sum(1 for c in txt if c.isdigit())
    if len(txt) > 0 and digits / len(txt) > DIGIT_RATIO_CHECK:
        return []

    # разбиваем на предложения и фильтруем
    sents = split_to_sentences(txt)

    # удаляем подряд идущие дубли
    filtered = [s for s in sents if sentence_filters(s)]
    if is_last and block.strip() and block.strip()[-1] not in '.!?':
        if filtered:
            filtered = filtered[:-1]

    dedup = []
    prev = None
    for s in filtered:
        if s != prev:
            dedup.append(s)
        prev = s
    return dedup


def handle_lists(sentences: list) -> list:
    """
    Склеиваем/Делим преложения из одного списка в один абзац либо фильтруем их.

    :param sentences: Предложения.
    :return: Абзацы.
    """
    result = []
    i = 0
    while i < len(sentences):
        s = sentences[i]
        if RE_LIST_MARKER.match(s):
            items = []
            # добавляем в список пока есть маркеры списка
            while i < len(sentences) and RE_LIST_MARKER.match(sentences[i]):
                items.append(RE_LIST_MARKER.sub('', sentences[i]).strip())
                i += 1

            if result:
                prev = result.pop()
                group = prev + " " + " ".join(items)
            else:
                group = " ".join(items)

            nospace_len = len(group.replace(" ", ""))

            if not result and nospace_len < 300:
                # нет предыдущего предложения и список слишком маленький – пропускаем
                continue

            if nospace_len > 800:
                # разбиваем на два по точке около середины
                mid = len(group)//2
                cut = group.find('.', mid)
                if cut != -1:
                    part1 = group[:cut+1].strip()
                    part2 = group[cut+1:].strip()
                    result.extend([part1, part2])
                else:
                    result.append(group)
            else:
                result.append(group)
        else:
            result.append(s)
            i += 1
    return result


def split_paragraphs(sentences: list) -> list:
    """
    Берёт список предложений, возвращает абзацы MIN_BLOCK_LEN–MAX_BLOCK_LEN
    символов без пробелов.

    :param sentences: Список предложений.
    :return: Список абзацев.
    """
    paragraphs = []
    buf = ""
    buf_nospace = 0

    for s in sentences:
        slen = len(s.replace(" ", ""))
        # слишком длинное предложение - разбиваем
        if slen > LARGE_BLOCK_LEN:
            # попытаемся найти точку около середины
            mid = len(s) // 2
            cut = s.find('.', mid)
            if cut == -1:
                # нет точки — просто режем по символу
                cut = mid
            part1 = s[:cut + 1].strip()
            part2 = s[cut + 1:].strip()
            # сбросим буфер
            if buf:
                paragraphs.append(buf)
                buf, buf_nospace = "", 0
            # добавляем две части отдельно
            if part1:
                paragraphs.append(part1)
            if part2:
                paragraphs.append(part2)
            continue

        # добавляем абзацы
        if buf_nospace + slen <= MAX_BLOCK_LEN:
            buf = (buf + " " + s).strip() if buf else s
            buf_nospace += slen
            if buf_nospace >= MIN_BLOCK_LEN and buf.endswith(('.', '!', '?')):
                paragraphs.append(buf)
                buf, buf_nospace = "", 0
        else:
            if buf:
                paragraphs.append(buf)
            buf, buf_nospace = s, slen

    # остаток буфера
    if buf:
        paragraphs.append(buf)

    return paragraphs


def get_meta(uni: str, data):
    """
    Строит словарь в зависимости от вуза, поскольку ключи отличаются.

    :param uni: Университет: {'spbu', 'hse'}.
    :param data: Слоаварь исходного json.
    """
    if uni == "spbu":
        meta = {k: data[k] for k in ('id', 'заголовок', 'год', 'тема')}
    else:
        meta = {k: data[k] for k in ('заголовок', 'год', 'тема', 'код_темы')}
    return meta


def process_file(path_in: str, path_out: str, uni: str):
    """
    Обрабатываем получившиеся json файлы, фильтруем мелкие и пораздельно фильтруем.
    После фильтрации текстов отбрасываем мелкие абзацы или фрагменты.

    :param path_in: Папка с json.
    :param path_out: Папка, куда будут сохранены обработанные тексты.
    :param uni: Университет: {'hse', 'spbu'}.
    """
    # Пропустить мелкие файлы
    if os.path.getsize(path_in) < MIN_FILE_SIZE:
        return
    with open(path_in, 'r', encoding='utf-8') as f:
        data = json.load(f)
    meta = get_meta(uni, data)

    # найти ключи, под которыми лежат тексты
    sec_keys = [k for k in data if k not in meta]

    if not sec_keys:
        return

    out = {**meta}

    for idx, key in enumerate(sec_keys):
        role = 'введение' if idx == 0 else 'обзор'

        all_sents = []
        blocks = data.get(key, [])

        for j, blk in enumerate(blocks):
            is_last = (j == len(blocks) - 1)
            all_sents += clean_and_filter_block(blk, is_last=is_last)

        all_sents = handle_lists(all_sents)
        paras = split_paragraphs(all_sents)

        # обрезаем короткие хвостовые абзацы
        while paras and len(paras[-1].replace(" ", "")) < MIN_TRAILING_LEN:
            paras.pop()
        if len(paras) < MIN_PARAGRAPH_COUNT:
            return
        out[role] = paras

    os.makedirs(os.path.dirname(path_out), exist_ok=True)
    if out:
        with open(path_out, 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="Чистка и разбиение json-файлов"
    )
    parser.add_argument(
        '--uni',
        choices=['spbu', 'hse'],
        required=True,
        help="Университет: 'spbu' или 'hse'"
    )
    parser.add_argument(
        '--in-dir',
        required=True,
        help="Папка с исходными JSON-файлами"
    )
    parser.add_argument(
        '--out-dir',
        required=True,
        help="Папка для сохранения результатов"
    )
    args = parser.parse_args()

    in_dir = args.in_dir
    out_dir = args.out_dir
    uni = args.uni

    # Проверяем, что входная папка существует
    if not os.path.isdir(in_dir):
        print(f"Ошибка: входная папка '{in_dir}' не найдена.", file=sys.stderr)
        sys.exit(1)

    # Создаем выходную папку, если её нет
    os.makedirs(out_dir, exist_ok=True)

    # Обходим все файлы в папке
    for fname in os.listdir(in_dir):
        if not fname.lower().endswith('.json'):
            continue
        path_in = os.path.join(in_dir, fname)
        path_out = os.path.join(out_dir, fname)
        try:
            process_file(path_in, path_out, uni)
            print(f"[OK]  Обработан файл: {fname}")
        except Exception as e:
            print(f"[ERR] {fname}: {e}", file=sys.stderr)


if __name__ == '__main__':
    main()
