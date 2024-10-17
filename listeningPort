import psutil
import tkinter as tk
from tkinter import messagebox

def get_listening_ports():
    listening_ports = []
    for conn in psutil.net_connections(kind='inet'):
        if conn.status == psutil.CONN_LISTEN:
            listening_ports.append((conn.laddr.port, conn.pid))
    return listening_ports

def on_check_button_click():
    listening_ports = get_listening_ports()
    if listening_ports:
        result = "Прослушиваемые порты PIDs:\n"
        for port, pid in listening_ports:
            result += f"Порт: {port}, PID: {pid}\n"
        messagebox.showinfo("Порты", result)
    else:
        messagebox.showinfo("Порты", "Прослушиваемых портов нет")

# Создание основного окна
root = tk.Tk()
root.title("Прослушиваемые порты")

# Создание и размещение виджетов
check_button = tk.Button(root, text="Показать", command=on_check_button_click)
check_button.pack(pady=20)

# Запуск основного цикла
root.mainloop()
