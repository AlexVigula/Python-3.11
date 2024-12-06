import pandas as pd
from reportlab.lib.pagesizes import landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.graphics.barcode import code128

# Загружаем данные из Excel-файла
df = pd.read_excel('marker.xlsx')

# Удаляем лишние пробелы в названиях столбцов
df.columns = df.columns.str.strip()

# Определяем размеры этикетки
label_width = 58 * mm  # Ширина этикетки
label_height = 40 * mm  # Высота этикетки

# Перебираем строки в DataFrame
for i in range(len(df)):
    # Создаем новый PDF-файл для каждой строки
    pdf_filename = f'label_{i + 1}.pdf'
    c = canvas.Canvas(pdf_filename, pagesize=(label_width, label_height))

    # Устанавливаем размер шрифта
    c.setFont("Helvetica", 8)  # Уменьшаем шрифт до 8

    # Получаем значение P/N для штрих-кода
    pn_code = df["P/N:"][i]

    # Создаем штрих-код Code 128
    barcode = code128.Code128(pn_code, barHeight=15 * mm)

    # Устанавливаем позицию для штрих-кода с отступами по 2 мм
    barcode.drawOn(c, 2 * mm, label_height - 15 * mm)  # Рисуем штрих-код на канвасе

    # Добавляем текст на этикетку
    c.drawString(2 * mm, label_height - 21 * mm, f'P/N: {pn_code}')
    c.drawString(2 * mm, label_height - 26 * mm, f'{df["Description"][i]}')
    c.drawString(2 * mm, label_height - 30 * mm, f'{df["Brand"][i]}')
    c.drawString(2 * mm, label_height - 34 * mm, f'{df["Manufacturer"][i]}')
    c.drawString(2 * mm, label_height - 38 * mm, f'{df["Country of origin"][i]}')

    # Сохраняем PDF-файл
    c.save()

print("PDF-файлы успешно созданы!")
