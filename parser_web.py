# Readme
"""
Постраничный парсер сайта кафедры Системного программирования СПбГУ (2007–2024).
— Принимает куки
— Ждёт загрузки работ в #ThesisList
— Для каждой работы берёт заголовок (внутри год + тема диплома), ссылку на PDF по XPath
— Скачивает pdf и обрабатывает в отдельном модуле process_pdf.py
— Меняет страницу в url.
"""

import time
from pathlib import Path
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from parser_pdf import parse
import json
import hashlib
import traceback
from selenium.common.exceptions import TimeoutException, WebDriverException

BASE = "https://se.math.spbu.ru"
PARAMS = "search=&supervisor=0&course=0&startdate=2007&enddate=2022&worktype=1"
URL = f"{BASE}/theses.html?{PARAMS}"
HEAD = {"User-Agent": "Mozilla/5.0"}

# куда сохранять json и pdf (необработанные pdf сохраняются для ручного просмотра и отладки)
OUT = Path("downloads")


def download(session, href: str, title: str, topic: str):
    """
    Скачиваем pdf (если его нет) и обрабатываем (если не обработали) в отдельном модуле.
    """
    OUT.mkdir(exist_ok=True)

    id = href[href.find('=')+1:]
    fn = OUT/f"{get_md5_hash(title)}.pdf"
    fnj = OUT/f"{get_md5_hash(title)}.json"

    if fnj.exists():
        print(f"[✓] Уже обработан: {fn.name}")
        return
    if fn.exists():
        print(f"[.] Уже скачан, обработаем: {fn.name}")
        process_pdf(fn, title, topic, id)
        return

    print(f"[↓] {title}")
    r = session.get(href, stream=True, headers=HEAD, timeout=30)
    r.raise_for_status()

    with open(fn, "wb") as f:
        for c in r.iter_content(8192):
            f.write(c)
    print(f"[+] Сохранено: {fn.name}")

    process_pdf(fn, title, topic, id)


def process_pdf(pdf_path: Path, title: str, topic: str, id: str):
    """
    Вызывает обработку pdf и затем удаляет файл.
    Возвращает в качестве результата блоки двух разделов.
    """
    try:
        data = parse(pdf_path)
    except Exception as e:
        print(f"Ошибка при разборе файла: {e}")
        traceback.print_exc()
        print("Не удалось обработать")
        return

    save_json(data, title, topic, id)

    try:
        pdf_path.unlink()
        print(f"[🗑] Удалён PDF: {pdf_path.name}")
    except Exception as e:
        print(f"[!] Не удалось удалить {pdf_path}: {e}")
    return data


def save_json(data, title: str, topic: str, id: str):
    """
    Сохраняем в виде json полученные данные.
    """
    if not data:
        return

    titles, intro_pages, review_pages = data

    if not intro_pages:
        return

    fnj = OUT / f"{get_md5_hash(title)}.json"
    title, year = title[:-6], title[-6:]

    # Если у нас есть раздел "Обзор" или похожий
    if review_pages:
        result = {
            'id': id,
            'заголовок': title,
            'год': year,
            'тема': topic,
            titles[0]: intro_pages,
            titles[1]: review_pages
        }
    # Если у нас есть только "Введение"
    else:
        result = {
            'id': id,
            'заголовок': title,
            'год': year,
            'тема': topic,
            titles[0]: intro_pages
        }

    with open(fnj, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return


def get_md5_hash(header: str) -> str:
    """
    Возвращает MD5-хэш от строки.
    Результат между запусками интерпретатора будет одинаков.
    """
    # Переводим строку в байты. Кодируем в UTF-8.
    header_bytes = header.encode('utf-8')
    # Вычисляем MD5
    md5_obj = hashlib.md5(header_bytes)
    # Получаем шестнадцатеричное представление
    return md5_obj.hexdigest()


def main():
    # сессия requests для PDF
    sess = requests.Session()
    sess.headers.update(HEAD)

    # selenium
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--disable-gpu")
    driver = webdriver.Chrome(options=opts)
    opts.add_argument("--window-size=1920,1080")
    driver.get(URL)

    # принять куки, если есть
    try:
        btn = WebDriverWait(driver, 3).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.acceptcookies"))
        )
        btn.click()
        time.sleep(1)
    except:
        pass

    page = 1
    while True:
        print(f"\n=== Страница {page} ===")
        page_url = f"{BASE}/theses.html?page={page}&{PARAMS}"
        try:
            driver.get(page_url)
            # ждём, пока в #ThesisList появится хотя бы одна работа
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#ThesisList > div"))
            )
            # все прямые дочки #ThesisList — по ним и пройдём
            entries = driver.find_elements(By.CSS_SELECTOR, "#ThesisList > div")
            if not entries:
                print("[!] Нет записей в #ThesisList, выходим.")
                break

            for entry in entries:
                # ищем заголовок по full XPath (можно посмотреть в коде сайта), но относительно entry
                try:
                    title_el = entry.find_element(
                        By.XPATH,
                        ".//div/div/div[1]/h6/strong"
                    )
                    title = title_el.text.strip()
                except:
                    print("[!] Не удалось найти заголовок в entry, пропускаем.")
                    continue

                # ищем ссылку на pdf по full XPath внутри entry
                try:
                    a = entry.find_element(
                        By.XPATH,
                        ".//div/div/div[2]/a[1]"

                    )
                    href = a.get_attribute("href")
                    if not href.startswith("http"):
                        href = BASE + href
                except:
                    print(f"[!] PDF не найден для «{title}»")
                    continue

                # ищем тему (название направления/кафедры) по full XPath внутри entry
                try:
                    topic_el = entry.find_element(
                        By.XPATH,
                        ".//div[2]/p[3]/i"
                    )
                    topic = topic_el.text.strip()
                except:
                    print(f"[!] Topic не найден для «{title}»")
                    topic = None

                # скачиваем pdf
                download(sess, href, title, topic)

        # Поскольку сайт работает не совсем корректно (на некоторые страницы можно получить 404),
        # будем их пропускать (найдем эти файлы далее, но другим способом):
        except (TimeoutException, WebDriverException) as e:
            print(f"[!] Ошибка на странице {page}: {e}. Переходим к следующей.")

        finally:
            page += 1
            time.sleep(2)

    driver.quit()


if __name__ == "__main__":
    main()
