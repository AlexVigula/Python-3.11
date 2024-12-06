import pandas as pd
from reportlab.lib.pagesizes import landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

# Загружаем данные из Excel-файла
df = pd.read_excel('marker.xlsx')

# Удаляем лишние пробелы в названиях столбцов
df.columns = df.columns.str.strip()

# Определяем размеры этикетки
label_width = 58 * mm
label_height = 40 * mm

# Перебираем строки в DataFrame
for i in range(len(df)):
    # Создаем новый PDF-файл для каждой строки
    pdf_filename = f'label_{i + 1}.pdf'
    c = canvas.Canvas(pdf_filename, pagesize=(label_width, label_height))
     # Устанавливаем размер шрифта
    c.setFont("Helvetica", 8)  # Устанавливаем шрифт Helvetica размером 10
    # Добавляем текст на этикетку
    c.drawString(2 * mm, label_height - 10 * mm, f'P/N: {df["P/N:"][i]}')
    c.drawString(2 * mm, label_height - 15 * mm, f'{df["Description"][i]}')
    c.drawString(2 * mm, label_height - 20 * mm, f'{df["Brand"][i]}')
    c.drawString(2 * mm, label_height - 25 * mm, f'MANUFACTURER: {df["Manufacturer"][i]}')
    c.drawString(2 * mm, label_height - 30 * mm, f'{df["AND"][i]}')
    c.drawString(2 * mm, label_height - 35 * mm, f'MADE IN {df["Country of origin"][i]}')
    # Сохраняем PDF-файл
    c.save()

print("PDF-файлы успешно созданы!")
