import tkinter as tk
from tkinter import messagebox
import subprocess
import platform

class PingApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Пинг")

        self.process = None

        # Создание и размещение виджетов для ввода хоста
        self.host_label = tk.Label(root, text="Введите хост:")
        self.host_label.pack(pady=10)

        self.host_entry = tk.Entry(root)
        self.host_entry.pack(pady=10)

        # Создание и размещение кнопки для выполнения пинга
        self.ping_button = tk.Button(root, text="Начать пинг", command=self.start_ping)
        self.ping_button.pack(pady=10)

    def start_ping(self):
        host = self.host_entry.get()
        if host:
            try:
                param = '-t' if platform.system().lower() == 'windows' else ''
                command = f'ping {param} {host}'
                self.process = subprocess.Popen(['cmd', '/c', 'start', 'cmd', '/k', command], shell=True)
                #messagebox.showinfo("Ping", f"Начат пинг хоста {host}")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось выполнить пинг: {e}")
        else:
            messagebox.showerror("Ошибка", "Введите хост")

    def stop_ping(self):
        if self.process is not None:
            try:
                self.process.terminate()
                messagebox.showinfo("Ping", "Пинг остановлен")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось остановить пинг: {e}")
        else:
            messagebox.showerror("Ошибка", "Пинг не запущен")

# Создание основного окна
root = tk.Tk()
app = PingApp(root)

# Запуск основного цикла
root.mainloop()
