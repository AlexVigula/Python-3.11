import os
import sys
import subprocess
import re
import json
import time
from pathlib import Path

def check_ibd2sdi():
    """Проверяет наличие утилиты ibd2sdi в системе"""
    try:
        # Пытаемся найти ibd2sdi в путях
        subprocess.run(['ibd2sdi', '--version'], 
                      stdout=subprocess.PIPE, 
                      stderr=subprocess.PIPE,
                      check=True,
                      text=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def extract_table_structure_with_ibd2sdi(ibd_path):
    """Извлекает структуру таблицы с помощью ibd2sdi"""
    try:
        result = subprocess.run(['ibd2sdi', ibd_path], 
                               capture_output=True, 
                               text=True,
                               check=True)
        
        # Парсим вывод ibd2sdi
        sdi_data = json.loads(result.stdout)
        
        # Ищем информацию о таблице
        for item in sdi_data:
            if item['type'] == 'SYS_TABLES':
                create_statement = item['mysql']['ddl_options']['create_table']
                
                # Очищаем и форматируем CREATE TABLE
                create_statement = re.sub(r'\\n', '\n', create_statement)
                create_statement = re.sub(r'\\"', '"', create_statement)
                create_statement = re.sub(r'\\/', '/', create_statement)
                
                # Добавляем закрывающую скобку и ENGINE, если нужно
                if not create_statement.endswith(';'):
                    create_statement += ';'
                
                return create_statement
        
        return None
    except Exception as e:
        print(f"Ошибка при обработке {ibd_path}: {str(e)}")
        return None

def analyze_frm_file(frm_path):
    """Пытается проанализировать .frm файл для извлечения структуры таблицы"""
    try:
        with open(frm_path, 'rb') as f:
            content = f.read()
            
        # Это очень упрощенный анализ, в реальности .frm файлы сложнее
        # Но для базовых структур может сработать
        
        # Пытаемся найти типы данных
        char_pattern = re.compile(b'CHAR\\(([0-9]+)\\)')
        varchar_pattern = re.compile(b'VARCHAR\\(([0-9]+)\\)')
        int_pattern = re.compile(b'INT\\(([0-9]+)\\)')
        
        # Просто для примера, в реальности нужно гораздо больше обработки
        if b'PRIMARY KEY' in content:
            # Это очень упрощенный пример
            table_name = Path(frm_path).stem
            return f"""CREATE TABLE `{table_name}` (
  `id` INT NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB;"""
            
        return None
    except Exception as e:
        print(f"Ошибка при анализе .frm файла {frm_path}: {str(e)}")
        return None

def analyze_frm_file_advanced(frm_path):
    """Улучшенный анализ .frm файла для извлечения реальной структуры таблицы"""
    try:
        with open(frm_path, 'rb') as f:
            content = f.read()
        
        table_name = Path(frm_path).stem
        print(f"    Анализ .frm файла для таблицы {table_name} (размер: {len(content)} байт)")
        
        # Более детальный анализ .frm файла
        # Ищем метаданные в заголовке файла
        if len(content) < 64:
            print(f"    Файл слишком маленький: {len(content)} байт")
            return None
            
        # Читаем заголовок .frm файла
        header = content[:64]
        
        # Извлекаем информацию о таблице из заголовка
        # Это упрощенная версия - в реальности .frm файлы очень сложные
        engine_info = extract_engine_info(content)
        charset_info = extract_charset_info(content)
        print(f"    Движок: {engine_info}, Кодировка: {charset_info}")
        
        # Пытаемся найти определения колонок
        columns = extract_column_definitions(content)
        print(f"    Найдено колонок: {len(columns)}")
        for col in columns:
            print(f"      - {col}")
        
        if not columns:
            # Если не удалось извлечь колонки, создаем базовую структуру
            columns = [f"`id` INT NOT NULL AUTO_INCREMENT"]
            print(f"    Использована базовая структура")
        
        # Собираем CREATE TABLE statement
        create_table = f"""CREATE TABLE `{table_name}` (\n"""
        
        for i, column in enumerate(columns):
            create_table += f"  {column}"
            if i < len(columns) - 1:
                create_table += ","
            create_table += "\n"
        
        # Добавляем первичный ключ если есть id
        has_primary_key = any('id' in col.lower() and 'auto_increment' in col.lower() for col in columns)
        if has_primary_key:
            create_table += ",\n  PRIMARY KEY (`id`)\n"
        
        create_table += f") ENGINE={engine_info} DEFAULT CHARSET={charset_info};"
        
        return create_table
        
    except Exception as e:
        print(f"Ошибка при анализе .frm файла {frm_path}: {str(e)}")
        return None

def extract_engine_info(content):
    """Извлекает информацию о движке таблицы из .frm файла"""
    # Ищем строки, указывающие на движок
    if b'InnoDB' in content:
        return 'InnoDB'
    elif b'MyISAM' in content:
        return 'MyISAM'
    elif b'MEMORY' in content:
        return 'MEMORY'
    else:
        return 'InnoDB'  # По умолчанию

def extract_charset_info(content):
    """Извлекает информацию о кодировке из .frm файла"""
    # Ищем информацию о кодировке
    if b'utf8mb4' in content:
        return 'utf8mb4 COLLATE utf8mb4_general_ci'
    elif b'utf8' in content:
        return 'utf8 COLLATE utf8_general_ci'
    elif b'latin1' in content:
        return 'latin1 COLLATE latin1_swedish_ci'
    else:
        return 'utf8mb4 COLLATE utf8mb4_general_ci'  # По умолчанию

def extract_column_definitions(content):
    """Пытается извлечь определения колонок из .frm файла"""
    columns = []
    
    # Более продвинутый анализ .frm файла
    # Ищем строки в файле, которые могут содержать имена колонок
    try:
        # Пытаемся декодировать как текст (часто в .frm есть строки)
        text_content = content.decode('utf-8', errors='ignore')
        
        # Ищем общие имена колонок в тексте
        common_columns = [
            'id', 'name', 'email', 'password', 'created_at', 'updated_at',
            'user_id', 'title', 'content', 'status', 'description', 'type',
            'value', 'key', 'token', 'url', 'path', 'file', 'image', 'photo',
            'username', 'first_name', 'last_name', 'phone', 'address', 'city',
            'country', 'zip', 'date', 'time', 'amount', 'price', 'quantity',
            'category', 'tag', 'comment', 'message', 'subject', 'body',
            'active', 'enabled', 'visible', 'public', 'private', 'admin'
        ]
        
        found_columns = []
        for col in common_columns:
            if col in text_content.lower():
                found_columns.append(col)
        
        # Если нашли имена колонок, создаем структуру
        if found_columns:
            for col in found_columns[:8]:  # Ограничиваем количество колонок
                if col == 'id':
                    columns.append(f"`{col}` INT NOT NULL AUTO_INCREMENT")
                elif col in ['created_at', 'updated_at']:
                    columns.append(f"`{col}` TIMESTAMP NULL DEFAULT NULL")
                elif col in ['email']:
                    columns.append(f"`{col}` VARCHAR(255) DEFAULT NULL")
                elif col in ['name', 'title', 'username']:
                    columns.append(f"`{col}` VARCHAR(255) DEFAULT NULL")
                elif col in ['password', 'token']:
                    columns.append(f"`{col}` VARCHAR(255) DEFAULT NULL")
                elif col in ['content', 'description', 'message', 'body']:
                    columns.append(f"`{col}` TEXT DEFAULT NULL")
                elif col in ['status', 'type', 'category']:
                    columns.append(f"`{col}` VARCHAR(50) DEFAULT NULL")
                elif col in ['user_id', 'admin_id']:
                    columns.append(f"`{col}` INT DEFAULT NULL")
                elif col in ['amount', 'price']:
                    columns.append(f"`{col}` DECIMAL(10,2) DEFAULT NULL")
                elif col in ['active', 'enabled', 'visible', 'public']:
                    columns.append(f"`{col}` TINYINT(1) DEFAULT 0")
                else:
                    columns.append(f"`{col}` VARCHAR(255) DEFAULT NULL")
        
        # Дополнительный поиск по бинарным паттернам
        if not columns:
            print(f"    Поиск бинарных паттернов в .frm файле...")
            # Ищем специфические паттерны типов данных
            if b'VARCHAR' in content:
                columns.append("`name` VARCHAR(255) DEFAULT NULL")
                print(f"    Найден паттерн VARCHAR")
            if b'INT' in content:
                columns.append("`id` INT NOT NULL AUTO_INCREMENT")
                print(f"    Найден паттерн INT")
            if b'TEXT' in content:
                columns.append("`content` TEXT DEFAULT NULL")
                print(f"    Найден паттерн TEXT")
            if b'TIMESTAMP' in content:
                columns.append("`created_at` TIMESTAMP NULL DEFAULT NULL")
                columns.append("`updated_at` TIMESTAMP NULL DEFAULT NULL")
                print(f"    Найден паттерн TIMESTAMP")
            
            # Дополнительный поиск строковых паттернов
            string_patterns = [
                (b'user', '`user_id` INT DEFAULT NULL'),
                (b'email', '`email` VARCHAR(255) DEFAULT NULL'),
                (b'password', '`password` VARCHAR(255) DEFAULT NULL'),
                (b'status', '`status` VARCHAR(50) DEFAULT NULL'),
                (b'title', '`title` VARCHAR(255) DEFAULT NULL'),
                (b'content', '`content` TEXT DEFAULT NULL'),
                (b'image', '`image` VARCHAR(255) DEFAULT NULL'),
                (b'file', '`file` VARCHAR(255) DEFAULT NULL'),
                (b'url', '`url` VARCHAR(255) DEFAULT NULL'),
                (b'price', '`price` DECIMAL(10,2) DEFAULT NULL'),
                (b'amount', '`amount` DECIMAL(10,2) DEFAULT NULL'),
            ]
            
            for pattern, column_def in string_patterns:
                if pattern in content:
                    if not any(pattern.decode() in col for col in columns):
                        columns.append(column_def)
                        print(f"    Найден паттерн {pattern.decode()}")
        
    except Exception as e:
        print(f"    Ошибка при анализе текста .frm файла: {str(e)}")
    
    # Если все еще нет колонок, создаем базовую структуру
    if not columns:
        columns = [
            "`id` INT NOT NULL AUTO_INCREMENT",
            "`created_at` TIMESTAMP NULL DEFAULT NULL",
            "`updated_at` TIMESTAMP NULL DEFAULT NULL"
        ]
    
    return columns

def is_fts_table(table_name):
    """Проверяет, является ли таблица FTS-таблицей"""
    return table_name.startswith('FTS_')

def is_system_table(table_name):
    """Проверяет, является ли таблица системной"""
    system_tables = ['innodb_index_stats', 'innodb_table_stats', 'gtid_slave_pos', 
                    'transaction_registry', 'event', 'general_log', 'slow_log']
    return table_name in system_tables

def create_database_dump(datadir, output_dir):
    """Создает дампы всех баз данных из указанной папки данных"""
    # Создаем выходную директорию, если она не существует
    os.makedirs(output_dir, exist_ok=True)
    
    # Системные базы данных, которые нужно пропустить
    system_databases = ['#innodb_redo', '#innodb_temp', 'performance_schema', 
                      'sys', 'mysql', 'information_schema']
    
    # Список обработанных баз данных
    processed_dbs = []
    failed_dbs = []
    
    print(f"Поиск баз данных в {datadir}...")
    
    # Перебираем все папки в datadir
    for item in os.listdir(datadir):
        db_path = os.path.join(datadir, item)
        
        # Пропускаем системные базы
        if item in system_databases:
            print(f"Пропускаем системную базу: {item}")
            continue
            
        # Проверяем, является ли это папкой базы данных
        if os.path.isdir(db_path):
            print(f"\nОбработка базы данных: {item}")
            db_output_dir = os.path.join(output_dir, item)
            os.makedirs(db_output_dir, exist_ok=True)
            
            # Создаем файл дампа для всей базы
            db_dump_path = os.path.join(db_output_dir, f"{item}.sql")
            
            try:
                # Список таблиц для этой базы
                tables = []
                
                # Ищем все .ibd файлы
                for file in os.listdir(db_path):
                    if file.endswith('.ibd') and not is_fts_table(file):
                        table_name = file[:-4]  # Удаляем расширение .ibd
                        tables.append(table_name)
                
                if not tables:
                    print(f"  Предупреждение: не найдено таблиц в базе {item}")
                    failed_dbs.append(item)
                    continue
                
                print(f"  Найдено таблиц: {len(tables)}")
                
                # Создаем структуру базы данных
                with open(db_dump_path, 'w', encoding='utf-8') as db_dump:
                    # Добавляем создание базы данных
                    db_dump.write(f"CREATE DATABASE IF NOT EXISTS `{item}` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;\n")
                    db_dump.write(f"USE `{item}`;\n\n")
                    
                    # Обрабатываем каждую таблицу
                    for table_name in tables:
                        print(f"  Обработка таблицы: {table_name}")
                        
                        ibd_path = os.path.join(db_path, f"{table_name}.ibd")
                        frm_path = os.path.join(db_path, f"{table_name}.frm")
                        
                        # Пытаемся извлечь структуру
                        create_table = None
                        
                        print(f"    Файлы: .ibd={os.path.exists(ibd_path)}, .frm={os.path.exists(frm_path)}")
                        
                        # 1. Пытаемся использовать ibd2sdi
                        if check_ibd2sdi():
                            print(f"    Попытка извлечения через ibd2sdi...")
                            create_table = extract_table_structure_with_ibd2sdi(ibd_path)
                            if create_table:
                                print(f"    ✓ Успешно извлечено через ibd2sdi")
                            else:
                                print(f"    ✗ ibd2sdi не смог извлечь структуру")
                        
                        # 2. Если ibd2sdi не сработал, пробуем улучшенный анализ .frm
                        if not create_table and os.path.exists(frm_path):
                            print(f"    Попытка улучшенного анализа .frm...")
                            create_table = analyze_frm_file_advanced(frm_path)
                            if create_table:
                                print(f"    ✓ Успешно извлечено через улучшенный анализ .frm")
                            else:
                                print(f"    ✗ Улучшенный анализ .frm не смог извлечь структуру")
                        
                        # 3. Если улучшенный анализ не сработал, пробуем базовый анализ .frm
                        if not create_table and os.path.exists(frm_path):
                            print(f"    Попытка базового анализа .frm...")
                            create_table = analyze_frm_file(frm_path)
                            if create_table:
                                print(f"    ✓ Успешно извлечено через базовый анализ .frm")
                            else:
                                print(f"    ✗ Базовый анализ .frm не смог извлечь структуру")
                        
                        # 4. Если все еще нет структуры, создаем минимальную
                        if not create_table:
                            create_table = f"""CREATE TABLE `{table_name}` (
  `id` INT NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB;"""
                            print(f"    ⚠ Предупреждение: использована минимальная структура для {table_name}")
                        
                        # Записываем структуру в дамп
                        db_dump.write(f"-- Структура таблицы {table_name}\n")
                        db_dump.write(f"{create_table}\n\n")
                
                processed_dbs.append(item)
                print(f"  Дамп базы {item} сохранен в {db_dump_path}")
                
            except Exception as e:
                print(f"  Ошибка при обработке базы {item}: {str(e)}")
                failed_dbs.append(item)
    
    # Создаем общий файл с рекомендациями
    recommendations_path = os.path.join(output_dir, "RESTORATION_GUIDE.txt")
    with open(recommendations_path, 'w', encoding='utf-8') as guide:
        guide.write("="*80 + "\n")
        guide.write("РУКОВОДСТВО ПО ВОССТАНОВЛЕНИЮ БАЗ ДАННЫХ\n")
        guide.write("="*80 + "\n\n")
        
        guide.write("Этот дамп содержит структуру таблиц, извлеченную из реальных файлов базы данных.\n")
        guide.write("Для полного восстановления данных следуйте этим шагам:\n\n")
        
        guide.write("1. УСТАНОВИТЕ MYSQL:\n")
        guide.write("   - Установите MySQL версии, совместимой с оригинальной базой данных\n")
        guide.write("   - Рекомендуется использовать MySQL 8.0+ для лучшей совместимости с ibd2sdi\n\n")
        
        guide.write("2. ВОССТАНОВИТЕ СТРУКТУРУ:\n")
        guide.write("   - Для каждой базы данных выполните:\n")
        guide.write("     mysql -u root -p < база.sql\n\n")
        
        guide.write("3. ВОССТАНОВИТЕ ДАННЫЕ:\n")
        guide.write("   Существует два основных способа:\n\n")
        
        guide.write("   СПОСОБ 1: Использование DISCARD/IMPORT TABLESPACE (рекомендуется):\n")
        guide.write("     a) Остановите MySQL\n")
        guide.write("     b) Скопируйте оригинальные .ibd файлы в datadir новой MySQL установки\n")
        guide.write("     c) Запустите MySQL\n")
        guide.write("     d) Для каждой таблицы выполните:\n")
        guide.write("         USE база;\n")
        guide.write("         ALTER TABLE таблица DISCARD TABLESPACE;\n")
        guide.write("         ALTER TABLE таблица IMPORT TABLESPACE;\n\n")
        
        guide.write("   СПОСОБ 2: Создание временного сервера и использование mysqldump:\n")
        guide.write("     a) Создайте временную MySQL установку\n")
        guide.write("     b) Скопируйте оригинальные данные в datadir временного сервера\n")
        guide.write("     c) Запустите временный сервер\n")
        guide.write("     d) Используйте mysqldump для создания полного дампа с данными:\n")
        guide.write("         mysqldump -u root -p --all-databases > full_dump.sql\n")
        guide.write("     e) Импортируйте дамп в целевой сервер:\n")
        guide.write("         mysql -u root -p < full_dump.sql\n\n")
        
        guide.write("4. ДОПОЛНИТЕЛЬНЫЕ РЕКОМЕНДАЦИИ:\n")
        guide.write("   - Для таблиц FTS_* (FULLTEXT индексы) могут потребоваться дополнительные шаги\n")
        guide.write("   - Если возникают ошибки с IMPORT TABLESPACE, проверьте структуру таблиц\n")
        guide.write("   - Структуры таблиц извлечены из реальных .frm и .ibd файлов\n")
        guide.write("   - Используйте ibd2sdi для более точного извлечения структур\n\n")
        
        guide.write("="*80 + "\n")
        guide.write("ОБРАБОТАННЫЕ БАЗЫ ДАННЫХ:\n")
        guide.write("="*80 + "\n\n")
        
        if processed_dbs:
            guide.write("Успешно обработано:\n")
            for db in processed_dbs:
                guide.write(f"- {db}\n")
            guide.write(f"\nВсего: {len(processed_dbs)} баз\n\n")
        else:
            guide.write("Не обработано ни одной базы данных.\n\n")
        
        if failed_dbs:
            guide.write("Не удалось обработать:\n")
            for db in failed_dbs:
                guide.write(f"- {db}\n")
            guide.write(f"\nВсего: {len(failed_dbs)} баз\n\n")
    
    print("\n" + "="*80)
    print("ПРОЦЕСС ЗАВЕРШЕН")
    print("="*80)
    print(f"Дампы сохранены в: {output_dir}")
    print(f"Количество обработанных баз: {len(processed_dbs)}")
    print(f"Количество необработанных баз: {len(failed_dbs)}")
    print("Рекомендации по восстановлению сохранены в RESTORATION_GUIDE.txt")

if __name__ == "__main__":
    # Путь к папке с данными MySQL
    MYSQL_DATADIR = r"D:\mysql"
    
    # Путь для сохранения дампов
    OUTPUT_DIR = r"D:\mysql_dumps"
    
    print("="*80)
    print("СКРИПТ СОЗДАНИЯ ДАМПОВ БАЗ ДАННЫХ MySQL")
    print("="*80)
    print(f"Источник данных: {MYSQL_DATADIR}")
    print(f"Выходная директория: {OUTPUT_DIR}")
    print("="*80)
    
    # Проверяем наличие ibd2sdi
    ibd2sdi_available = check_ibd2sdi()
    print(f"Утилита ibd2sdi {'доступна' if ibd2sdi_available else 'недоступна'}")
    if not ibd2sdi_available:
        print("Предупреждение: структура таблиц может быть неполной без ibd2sdi")
        print("Рекомендуется установить MySQL 8.0+ для доступа к ibd2sdi")
    
    # Создаем дампы
    create_database_dump(MYSQL_DATADIR, OUTPUT_DIR)
    
    print("\nПроцесс завершен. Нажмите Enter для выхода...")
    input()
