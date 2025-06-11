"""
Парсер аннотаций с сайта HSE.

Идет по страницам, парсит года, заголовки, затем переходит на страницу с аннотацией.
"""

import time
import json
import argparse

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import parser_web
from parser_hse import load_or_build_faculty_dict
from pathlib import Path


def main(year, faculty_code):
    """
    Основной код парсера. Итерируемся по страницам и переходим на каждую работу.

    :param year: Год, в котором происходила защита работ.
    :param faculty_code: Факультет, на котором происходила защита работ.
    """
    # основная ссылка без параметров
    base_url = "https://www.hse.ru/edu/vkr/"

    # настраиваем driver
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    driver = webdriver.Chrome(options=chrome_options)

    try:
        faculty_dict = load_or_build_faculty_dict(driver, base_url, year)
        print("Факультеты:", faculty_dict)

        page = 1
        while True:
            # Добавляем параметры. Обязательно наличие текста, язык работ - русский.
            url = (
                f"{base_url}"
                f"?faculty={faculty_code}"
                f"&year={year}"
                f"&language=ru"
                f"&text_available=yes"
                f"&page={page}"
            )
            driver.get(url)
            # ждём, пока хотя бы одно вхождение карточки появится (или таймаут)
            try:
                WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "ul.vkr-list li.vkr-card"))
                )
            except:
                print(f"Страница {page}: карточек не найдено -> завершаем.")
                break

            cards = driver.find_elements(By.CSS_SELECTOR, "ul.vkr-list li.vkr-card")
            if not cards:
                print(f"Страница {page}: пусто -> завершаем.")
                break

            print(f"Страница {page} -> найдено {len(cards)} работ")

            # Собираем базовые данные без WebElement
            works = []
            for card in cards:
                title_el = card.find_element(By.CSS_SELECTOR, "h3.vkr-card__title a")
                title = title_el.text.strip()

                detail_url = title_el.get_attribute("href")
                year_el = card.find_element(By.XPATH, ".//p[contains(., 'Год защиты')]/span")

                work_year = year_el.text.strip()

                faculty_name = card.find_element(By.CSS_SELECTOR, "p.vkr-card__item a.link").text.strip()
                faculty_code_parsed = faculty_dict.get(faculty_name, "UNKNOWN")

                works.append({
                    "title": title,
                    "detail_url": detail_url,
                    "work_year": work_year,
                    "faculty_name": faculty_name,
                    "faculty_code": faculty_code_parsed
                })

            for work in works:
                print(f"— {work['title']} | {work['work_year']} | {work['faculty_name']} -> {work['faculty_code']}")
                driver.get(work["detail_url"])
                time.sleep(1)

                try:
                    # Находим блок с аннотацией по full Xpath
                    ann_el = driver.find_element(By.XPATH,
                                                 "/html/body/div/div[4]/div/div[2]/div/div[1]/div/div[1]/div/div")
                    annotation = ann_el.text.strip()
                    print(f"Аннотация ({len(annotation)} знаков): {annotation[:100]}…")
                except Exception as e:
                    print(f" Аннотация не найдена или ошибка парсинга: {e} — пропускаем.")
                    continue

                # Для удобства распакуем здесь
                title = work['title']
                year = work['work_year']
                topic = work['faculty_name']
                code = work['faculty_code']

                # Тут будут json
                OUT = Path("abstract")
                fnj = OUT / f"{parser_web.get_md5_hash(title + year)}.json"

                result = {
                    'заголовок': title,
                    'год': year,
                    'тема': topic,
                    'код_темы': code,
                    'аннотация': annotation
                }
                if not fnj.exists():
                    with open(fnj, 'w', encoding='utf-8') as f:
                        json.dump(result, f, ensure_ascii=False, indent=2)

            page += 1
            time.sleep(1)

        print("Парсинг завершён.")

    finally:
        driver.quit()


PARSE_YEARS = list(range(2022, 2012, -1))
PARSE_CODE = [
    "120026365",  # Факультет компьютерных наук
    "135303",     # Факультет информатики, математики и компьютерных наук (Нижний Новгород)
    "220964857",  # Школа информатики, физики и технологий
    "59315150",   # Московский институт электроники и математики им. А.Н. Тихонова / НИУ ВШЭ - Москва (только МИЭМ)
    "269069",     # Факультет математики
    "192237798",  # Факультет физики
    "226010837",  # Факультет химии
    "226090865",  # Факультет биологии и биотехнологии
    "313975295",  # Факультет географии и геоинформационных технологий
    "119655633",  # Международная лаборатория прикладного сетевого анализа
    "70333",      # Институт статистических исследований и экономики знаний
    "47713665",   # Институт проблем безопасности
    "575254662",  # Факультет социально-экономических и компьютерных наук
    "12895325",   # Факультет экономики, менеджмента и бизнес-информатики
    "12444967",   # Институт менеджмента инноваций
    "47629373",   # Школа инноватики и предпринимательства
    "5564494",    # Международный институт экономики и финансов
    "143571564",  # Высшая школа бизнеса
    "122842106",  # Факультет социальных наук
    "139191145",  # Факультет гуманитарных наук
    "119384956",  # Факультет креативных индустрий
    "216119596",  # Институт когнитивных нейронаук
    "30114029",   # Высшая школа урбанистики имени А.А. Высоковского
    "217273055",  # Базовая кафедра Музея современного искусства «Гараж»
    "172465912",  # Институт социальной политики
    "61470229",   # Институт образования
    "46566943",   # Магистерская программа «Управление образованием» (Санкт-Петербург)
    "261615",     # Кафедра демографии
    "137726",     # Институт торговой политики
    "263451",     # Банковский институт
    # "135288",     # НИУ ВШЭ - Нижний Новгород
    "135300",     # Факультет экономики НИУ ВШЭ (Нижний Новгород)
    "135294",     # Факультет менеджмента (Нижний Новгород)
    "135297",     # Факультет права (Нижний Новгород)
    "57954166",   # Факультет гуманитарных наук (Нижний Новгород)
    # "135213",     # НИУ ВШЭ - Пермь
    "135243",     # Вечерне-заочный факультет экономики и управления (Пермь)
    "573223908",  # Магистерская школа (Пермь)
    # "135083",     # НИУ ВШЭ - Санкт-Петербург
    "135415180",  # Институт востоковедения и африканистики
    "133639270",  # Санкт-Петербургская школа экономики и менеджмента
    "133639230",  # Санкт-Петербургская школа социальных наук
    "222774718",  # Санкт-Петербургская школа дизайна
    "222569607",  # Санкт-Петербургская школа гуманитарных наук и искусств
    "104610480",  # Школа иностранных языков
    "22723",      # НИУ ВШЭ - Москва (без МИЭМ)
    "22750",      # Факультет мировой экономики и мировой политики
    "22735",      # Факультет экономических наук
    "22753",      # Факультет права
    "1030791"     # Высшая школа юриспруденции и администрирования
]

# Итерируемся по всем годам и факультетам
# for code in PARSE_CODE:
#     for year in PARSE_YEARS:
#         print('* ' * 10 + str(code) + '  ' + str(year) + ' *' * 10)
#         main(year, code)
#     print('*' * 10)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Парсер дипломных работ НИУ ВШЭ")
    parser.add_argument("--year", required=True, help="Год защиты (например, 2021)")
    parser.add_argument("--faculty", required=True, help="Код факультета (из словаря)")
    args = parser.parse_args()
    main(args.year, args.faculty)
