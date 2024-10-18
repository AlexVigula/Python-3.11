import socket
import psutil
import tkinter as tk
from tkinter import messagebox

def get_pid_by_port(port):
    for conn in psutil.net_connections(kind='inet'):
        if conn.laddr.port == port:
            return conn.pid
    return None

def check_port(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('0.0.0.0', port))
        except socket.error as e:
            pid = get_pid_by_port(port)
            if pid:
                return f"Порт {port} уже используется процессом с PID {pid}"
            else:
                return f"Порт {port} уже используется, но не удалось определить PID"
        else:
            return f"Порт {port} свободен"

def on_check_button_click():
    port = port_entry.get()
    try:
        port = int(port)
        if 0 <= port <= 65535:
            result = check_port(port)
            messagebox.showinfo("Result", result)
        else:
            messagebox.showerror("Ошибка 11", "Порт должен быть в диапазоне 0 and 65535")
    except ValueError:
        messagebox.showerror("Ошибка 12", "Введите порт")

# Создание основного окна
root = tk.Tk()
root.title("Проверка портов")

# Создание и размещение виджетов
port_label = tk.Label(root, text="Введите порт:")
port_label.pack(pady=10)

port_entry = tk.Entry(root)
port_entry.pack(pady=10)

check_button = tk.Button(root, text="Проверить", command=on_check_button_click)
check_button.pack(pady=10)

# Запуск основного цикла
root.mainloop()
