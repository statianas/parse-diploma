"""
Выбираем рандомно несколько файлов для ручного просмотра и поиска артефактов.
"""
import os
import json
import random

# Собираем файлы из папки
downloads_folder = 'downloads'
all_files = [f for f in os.listdir(downloads_folder) if f.endswith('.json')]

# Случайным образом выбираем 30 файлов
selected_files = random.sample(all_files, 30)

result = {}

for filename in selected_files:
    file_path = os.path.join(downloads_folder, filename)

    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Получаем все ключи и берем два последних
    keys = list(data.keys())
    if len(keys) < 2:
        continue
    last_two_keys = keys[-2:]

    # Собираем первые 50 символов из первой строки каждого из двух списков
    extracted = {}
    for key in last_two_keys:
        value = data[key]
        if isinstance(value, list) and len(value) > 1 and isinstance(value[0], str):
            extracted[key] = value[0][:150] + value[1][:150]
        else:
            extracted[key] = None

    result[filename] = extracted

output_file = '../result.json'
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=4)

print(f"Готово. Результат в {output_file}")
