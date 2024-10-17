import socket
import psutil
import tkinter as tk
from tkinter import messagebox, ttk
import subprocess
import os
import platform
# Раширенная версия чеккера сети
class PingApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Чеккер")

        self.process = None

        # Создание и размещение виджетов для ввода порта
        self.port_label = tk.Label(root, text="Введите порт:")
        self.port_label.pack(pady=10)

        self.port_entry = tk.Entry(root)
        self.port_entry.pack(pady=10)

        self.check_port_button = tk.Button(root, text="Проверить порт", command=self.on_check_port_button_click)
        self.check_port_button.pack(pady=10)

        # Привязка события нажатия клавиши Enter к функции проверки порта
        self.port_entry.bind("<Return>", self.on_check_port_button_click)

        # Создание и размещение виджетов для проверки всех слушающих портов
        self.check_listening_ports_button = tk.Button(root, text="Прослушиваемые порты", command=self.on_check_listening_ports_button_click)
        self.check_listening_ports_button.pack(pady=10)

        # Создание и размещение виджетов для просмотра таблицы маршрутов
        self.check_routing_table_button = tk.Button(root, text="Таблица маршрутов", command=self.on_check_routing_table_button_click)
        self.check_routing_table_button.pack(pady=10)

        # Создание и размещение виджетов для ввода хоста
        self.host_label = tk.Label(root, text="Введите хост:")
        self.host_label.pack(pady=10)

        self.host_entry = tk.Entry(root)
        self.host_entry.pack(pady=10)

        # Создание и размещение кнопки для выполнения пинга
        self.ping_button = tk.Button(root, text="Начать пинг", command=self.start_ping)
        self.ping_button.pack(pady=10)

        # Создание и размещение виджетов для выполнения команд восстановления сети
        self.restore_network_button = tk.Button(root, text="Восстановить сеть", command=self.on_restore_network_button_click)
        self.restore_network_button.pack(pady=10)

    def get_pid_by_port(self, port):
        for conn in psutil.net_connections(kind='inet'):
            if conn.laddr.port == port:
                return conn.pid
        return None

    def check_port(self, port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('0.0.0.0', port))
            except socket.error as e:
                pid = self.get_pid_by_port(port)
                if pid:
                    return f"Порт {port} уже используется процессом с PID {pid}"
                else:
                    return f"Порт {port} уже используется, но не удалось определить PID"
            else:
                return f"Порт {port} свободен"

    def get_listening_ports(self):
        listening_ports = []
        for conn in psutil.net_connections(kind='inet'):
            if conn.status == psutil.CONN_LISTEN:
                listening_ports.append((conn.laddr.port, conn.pid))
        return listening_ports

    def on_check_port_button_click(self, event=None):
        port = self.port_entry.get()
        try:
            port = int(port)
            if 0 <= port <= 65535:
                result = self.check_port(port)
                messagebox.showinfo("Порты", result)
            else:
                messagebox.showerror("Ошибка 11", "Порт должен быть в диапазоне 0 and 65535")
        except ValueError:
            messagebox.showerror("Ошибка 12", "Введите порт")

    def on_check_listening_ports_button_click(self):
        listening_ports = self.get_listening_ports()
        if listening_ports:
            self.show_listening_ports_window(listening_ports)
        else:
            messagebox.showinfo("Порты", "Не найдено прослушиваемых портов")

    def show_listening_ports_window(self, ports):
        window = tk.Toplevel(self.root)
        window.title("Прослушиваемые порты")

        tree = ttk.Treeview(window, columns=("Port", "PID"), show="headings")
        tree.heading("Port", text="Порт")
        tree.heading("PID", text="PID")

        for port, pid in ports:
            tree.insert("", "end", values=(port, pid))

        tree.pack(pady=10)

        def sort_ports(by_pid=False):
            sorted_ports = sorted(ports, key=lambda x: x[1] if by_pid else x[0])
            tree.delete(*tree.get_children())
            for port, pid in sorted_ports:
                tree.insert("", "end", values=(port, pid))

        sort_by_port_button = tk.Button(window, text="Сортировать по порту", command=lambda: sort_ports(by_pid=False))
        sort_by_port_button.pack(pady=5)

        sort_by_pid_button = tk.Button(window, text="Сортировать по PID", command=lambda: sort_ports(by_pid=True))
        sort_by_pid_button.pack(pady=5)

        def kill_process():
            selected_item = tree.selection()
            if selected_item:
                pid = tree.item(selected_item)['values'][1]
                try:
                    process = psutil.Process(pid)
                    process.terminate()
                    messagebox.showinfo("Успех", f"Процесс с PID {pid} завершен")
                except psutil.NoSuchProcess:
                    messagebox.showerror("Ошибка 13", f"Процесс с PID {pid} не найден")
                except psutil.AccessDenied:
                    messagebox.showerror("Ошибка 14", f"Нет доступа для завершения процесса с PID {pid}")

        kill_process_button = tk.Button(window, text="Завершить процесс", command=kill_process)
        kill_process_button.pack(pady=5)

    def get_routing_table(self):
        routing_table = []
        for route in psutil.net_if_addrs().values():
            for addr in route:
                routing_table.append((addr.address, addr.netmask, addr.broadcast))
        return routing_table

    def on_check_routing_table_button_click(self):
        routing_table = self.get_routing_table()
        if routing_table:
            self.show_routing_table_window(routing_table)
        else:
            messagebox.showinfo("Маршруты", "Не найдено маршрутов")

    def show_routing_table_window(self, table):
        window = tk.Toplevel(self.root)
        window.title("Таблица маршрутов")

        tree = ttk.Treeview(window, columns=("Address", "Netmask", "Broadcast"), show="headings")
        tree.heading("Address", text="Адрес")
        tree.heading("Netmask", text="Маска")
        tree.heading("Broadcast", text="Broadcast")

        for address, netmask, broadcast in table:
            tree.insert("", "end", values=(address, netmask, broadcast))

        tree.pack(pady=10)

        def sort_routing_table(by_address=False):
            sorted_table = sorted(table, key=lambda x: x[0] if by_address else x[1])
            tree.delete(*tree.get_children())
            for address, netmask, broadcast in sorted_table:
                tree.insert("", "end", values=(address, netmask, broadcast))

        sort_by_address_button = tk.Button(window, text="Сортировать по адресу", command=lambda: sort_routing_table(by_address=True))
        sort_by_address_button.pack(pady=5)

        sort_by_netmask_button = tk.Button(window, text="Сортировать по маске", command=lambda: sort_routing_table(by_address=False))
        sort_by_netmask_button.pack(pady=5)

        def clear_routing_table():
            try:
                subprocess.run(['ip', 'route', 'flush', 'cache'], check=True)
                messagebox.showinfo("Успех", "Таблица маршрутизации очищена")
            except subprocess.CalledProcessError as e:
                messagebox.showerror("Ошибка ", f"Не удалось очистить таблицу маршрутизации: {e}")

        clear_routing_table_button = tk.Button(window, text="Очистить таблицу маршрутизации", command=clear_routing_table)
        clear_routing_table_button.pack(pady=5)

    def ping_host(self, host):
        try:
            result = subprocess.run(['ping', '-c', '4', host], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            return result.stdout
        except Exception as e:
            return str(e)

    def start_ping(self):
        host = self.host_entry.get()
        if host:
            try:
                param = '-t' if platform.system().lower() == 'windows' else ''
                command = f'ping {param} {host}'
                self.process = subprocess.Popen(['cmd', '/c', 'start', 'cmd', '/k', command], shell=True)
                #messagebox.showinfo("Пинг", f"Начат пинг хоста {host}")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось выполнить пинг: {e}")
        else:
            messagebox.showerror("Ошибка 16", "Введите хост")

    def stop_ping(self):
        if self.process is not None:
            try:
                self.process.terminate()
                messagebox.showinfo("Пинг", "Пинг остановлен")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось остановить пинг: {e}")
        else:
            messagebox.showerror("Ошибка", "Пинг не запущен")

    def execute_network_commands(self):
        commands = [
            ('ipconfig', '/renew'),
            ('ipconfig', '/all'),
            ('ipconfig', '/flushdns')
        ]
        results = []
        for cmd in commands:
            try:
                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                results.append(result.stdout)
            except Exception as e:
                results.append(str(e))
        return "\n".join(results)

    def on_restore_network_button_click(self):
        result = self.execute_network_commands()
        messagebox.showinfo("Настройка сети", result)

# Создание основного окна
root = tk.Tk()
app = PingApp(root)

# Запуск основного цикла
root.mainloop()
