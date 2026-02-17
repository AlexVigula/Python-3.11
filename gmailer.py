import os
import io
import re
import pickle
import time
import json
import logging
import base64
import threading
import queue
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime, parseaddr
import ssl
import sys

# ================= SSL FIXES =================
# Отключаем проверку SSL сертификатов (для корпоративных сетей)
os.environ['PYTHONHTTPSVERIFY'] = '0'
os.environ['CURL_CA_BUNDLE'] = ''
os.environ['REQUESTS_CA_BUNDLE'] = ''

# Создаем глобальный SSL контекст с отключенной верификацией
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE
ssl._create_default_https_context = ssl._create_unverified_context

# Настройка прокси (раскомментируйте если нужно)
# os.environ['HTTP_PROXY'] = 'http://your-proxy:port'
# os.environ['HTTPS_PROXY'] = 'http://your-proxy:port'

import customtkinter as ctk
import tkinter as tk
from tkcalendar import DateEntry

import pandas as pd
from bs4 import BeautifulSoup
import pdfplumber
from docx import Document

# Проверка наличия openpyxl для работы с Excel
try:
    import openpyxl
except ImportError:
    print("ОШИБКА: openpyxl не установлен. Установите его командой: pip install openpyxl")
    sys.exit(1)

from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.http import HttpError
import google_auth_httplib2
import httplib2
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ================= CONFIG =================
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
MAX_WORKERS = 1  # Минимум для снижения нагрузки на API
ATTACHMENT_WORKERS = 1
RETRY_COUNT = 3  # Уменьшено количество попыток
BATCH_SIZE = 10  # Уменьшено для снижения нагрузки
AUTOSAVE_EVERY = 25
API_DELAY = 0.5  # Задержка между запросами в секундах
BATCH_DELAY = 2.0  # Задержка между батчами в секундах
STATE_FILE = "progress_state.json"
LOG_FILE = "export_log.txt"

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ================= DATA CLASS =================
@dataclass
class EmailData:
    date: str
    from_email: str
    subject: str
    phone: str  # Все телефоны через запятую в нормализованном формате
    inn: str
    text: str
    fio: str = ""
    website: str = ""
    company: str = ""  # Название компании (ООО, ИП, ЗАО, ПАО и т.п.)
    address: str = ""  # Адрес компании
    has_attachments: bool = False
    processed_at: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

# ================= THREAD-SAFE STATE =================
class ThreadSafeState:
    def __init__(self):
        self._lock = threading.Lock()
        self._processed_ids = set()
        self._data_buffer = []
        self._total_processed = 0
        self._cancelled = False
    
    def is_cancelled(self) -> bool:
        with self._lock:
            return self._cancelled
    
    def cancel(self):
        with self._lock:
            self._cancelled = True
    
    def add_processed(self, msg_id: str, data: EmailData):
        with self._lock:
            if msg_id not in self._processed_ids:
                self._processed_ids.add(msg_id)
                self._data_buffer.append(data)
                self._total_processed += 1
                return True
            return False
    
    def get_and_clear_buffer(self) -> List[EmailData]:
        with self._lock:
            buffer = self._data_buffer.copy()
            self._data_buffer = []
            return buffer
    
    def get_stats(self) -> tuple:
        with self._lock:
            return len(self._processed_ids), self._total_processed

# ================= AUTH =================
def authenticate():
    creds = None
    
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as e:
            logger.error(f"Token refresh failed: {e}")
            creds = None
    
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
        creds = flow.run_local_server(port=0)
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    
    return creds

def create_gmail_service(creds):
    """Создание сервиса Gmail с обходом SSL-проблем"""
    try:
        # Пробуем стандартный способ
        logger.info("Попытка стандартного подключения к Gmail API...")
        service = build('gmail', 'v1', credentials=creds, cache_discovery=False, static_discovery=False)
        logger.info("Стандартное подключение успешно")
        return service
    except Exception as e:
        logger.warning(f"Стандартное подключение не удалось: {e}")
        
    try:
        # Пробуем с httplib2 и отключенным SSL
        logger.info("Пробуем подключение с отключенной SSL-верификацией...")
        http = httplib2.Http(disable_ssl_certificate_validation=True, timeout=60)
        authorized_http = google_auth_httplib2.AuthorizedHttp(creds, http=http)
        
        service = build('gmail', 'v1', http=authorized_http, cache_discovery=False, static_discovery=False)
        logger.info("Подключение с отключенным SSL успешно")
        return service
    except Exception as e:
        logger.error(f"Все попытки подключения не удались: {e}")
        raise

# ================= HELPERS =================
def clean_html(html: str) -> str:
    """Очистка HTML с сохранением текста"""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for script in soup(["script", "style", "head", "meta", "link"]):
        script.decompose()
    text = soup.get_text(separator=' ', strip=True)
    text = ' '.join(text.split())
    return text

def extract_email_from_sender(sender: str) -> str:
    """Извлечение чистого email из строки отправителя"""
    if not sender:
        return ""
    real_name, email_addr = parseaddr(sender)
    if email_addr:
        return email_addr.lower().strip()
    email_pattern = r'[\w\.-]+@[\w\.-]+\.\w+'
    match = re.search(email_pattern, sender)
    return match.group(0).lower().strip() if match else sender.strip()

def format_date(date_str: str) -> str:
    """Форматирование даты в читаемый вид"""
    if not date_str:
        return ""
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.strftime("%d %b %Y %H:%M")
    except:
        cleaned = re.sub(r'\s*[+-]\d{4}\s*\(.*?\)', '', date_str)
        cleaned = re.sub(r'\s*\(.*?\)', '', cleaned)
        return cleaned.strip()

def clean_text(text: str) -> str:
    """Очистка текста от мусора"""
    if not text:
        return ""
    
    text = clean_html(text)
    text = re.sub(r'[\u200b\u200c\u200d\ufeff\u00a0\u2060]', '', text)
    text = ' '.join(text.split())
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    text = '\n'.join(lines)
    
    if len(text) > 10000:
        text = text[:10000] + "... [текст обрезан]"
    
    return text.strip()

def normalize_phone(phone_str: str) -> str:
    """Нормализует телефон в формат +7XXXXXXXXXX"""
    if not phone_str:
        return ""
    
    # Убираем все нецифровые символы кроме +
    digits = re.sub(r'[^\d+]', '', phone_str.strip())
    
    # Если пусто, возвращаем пустую строку
    if not digits:
        return ""
    
    # Если начинается с 8, заменяем на +7
    if digits.startswith('8'):
        digits = '7' + digits[1:]
    elif digits.startswith('+7'):
        digits = digits[2:]  # Убираем +7 для обработки
    elif digits.startswith('7'):
        digits = digits[1:]  # Убираем первую 7
    
    # Проверяем длину (должно быть 10 цифр для российского номера)
    if len(digits) == 10 and digits.isdigit():
        return '+7' + digits
    elif len(digits) == 11 and digits.startswith('7') and digits[1:].isdigit():
        return '+7' + digits[1:]
    
    return ""

def extract_data(text: str) -> tuple:
    """Извлечение телефона, ИНН, ФИО, сайта, компании и адреса с валидацией"""
    if not text:
        return "", "", "", "", "", ""
    
    # Телефон: находим все телефоны в различных форматах
    # Паттерны для разных форматов телефонов (более гибкие)
    phone_patterns = [
        r'\+7\s*\(?\d{3}\)?\s*\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',      # +7(XXX)XXX-XX-XX
        r'\+7\s*\(?\d{3}\)?\s*\d{3}[\s\-]?\d{4}',                  # +7(XXX)XXX-XXXX
        r'8\s*\(?\d{3}\)?\s*\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',       # 8(XXX)XXX-XX-XX
        r'8\s*\(?\d{3}\)?\s*\d{3}[\s\-]?\d{4}',                    # 8(XXX)XXX-XXXX
        r'\+7\s*\d{10}',                                            # +7XXXXXXXXXX
        r'8\s*\d{10}',                                              # 8XXXXXXXXXX
        r'\+7\s*\d{3}\s*\d{3}\s*\d{2}\s*\d{2}',                    # +7 XXX XXX XX XX
        r'\+7\s*\d{3}\s*\d{3}\s*\d{4}',                            # +7 XXX XXX XXXX
        r'8\s*\d{3}\s*\d{3}\s*\d{2}\s*\d{2}',                      # 8 XXX XXX XX XX
        r'8\s*\d{3}\s*\d{3}\s*\d{4}',                              # 8 XXX XXX XXXX
        r'\+7\s*\d{3}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',       # +7 XXX-XXX-XX-XX
        r'8\s*\d{3}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',         # 8 XXX-XXX-XX-XX
        r'\+7\s*\d{3}[\s\-]?\d{3}[\s\-]?\d{4}',                   # +7 XXX-XXX-XXXX
        r'8\s*\d{3}[\s\-]?\d{3}[\s\-]?\d{4}',                     # 8 XXX-XXX-XXXX
    ]
    
    all_phones = []
    seen_phones = set()
    
    for pattern in phone_patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            normalized = normalize_phone(match)
            if normalized and normalized not in seen_phones:
                all_phones.append(normalized)
                seen_phones.add(normalized)
    
    # Сортируем и объединяем через запятую
    phones_str = ", ".join(sorted(all_phones)) if all_phones else ""
    
    # ИНН: 10 или 12 цифр, но не часть другого числа
    inn_pattern = r'(?<!\d)\d{10}(?!\d)|(?<!\d)\d{12}(?!\d)'
    inns = re.findall(inn_pattern, text)
    inn = inns[0] if inns else ""
    
    # ФИО: ищем русские имена (2-3 слова с заглавной буквы)
    fio_pattern = r'\b[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?\b'
    fio_matches = re.findall(fio_pattern, text)
    # Берем первое найденное ФИО, но пропускаем слишком короткие (меньше 6 символов)
    fio = ""
    for match in fio_matches:
        if len(match.strip()) >= 6:
            fio = match.strip()
            break
    
    # Сайт: URL или доменное имя
    website_pattern = r'(?:https?://)?(?:www\.)?([a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.(?:[a-zA-Z]{2,}))'
    websites = re.findall(website_pattern, text)
    # Фильтруем популярные почтовые сервисы и соцсети
    exclude_domains = ['gmail.com', 'mail.ru', 'yandex.ru', 'yahoo.com', 'outlook.com', 
                       'vk.com', 'facebook.com', 'twitter.com', 'instagram.com', 'telegram.org']
    website = ""
    for w in websites:
        if w.lower() not in exclude_domains:
            website = w.lower()
            break
    
    # Компания: ищем ООО, ИП, ЗАО, ПАО, АО и т.п.
    # Ищем полное название компании с кавычками
    company_patterns = [
        r'(ООО|ИП|ЗАО|ПАО|АО|ОАО|НПО|НТЦ|ОП|ТД|ИЧП|ЧП|ЧУП|ТОО|АОЗТ)\s*["«]([^"»\n]{3,50})["»]',
        r'(ООО|ИП|ЗАО|ПАО|АО|ОАО|НПО|НТЦ|ОП|ТД|ИЧП|ЧП|ЧУП|ТОО|АОЗТ)\s+([А-ЯЁ][А-ЯЁа-яё\s\-]{2,40}?)(?:\s|$|,|\.|«|")',
    ]
    
    company = ""
    for pattern in company_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            # Берем первое найденное название компании
            prefix = matches[0][0].upper()
            comp_name = matches[0][1].strip()
            # Очищаем название от лишних символов
            comp_name = re.sub(r'["«»"]', '', comp_name).strip()
            if comp_name:
                company = f"{prefix} {comp_name}".strip()
                break
    
    # Адрес: ищем адреса (обычно содержат слова типа "г.", "ул.", "д.", "офис", "помещ.")
    # Ищем строки с индексами или адресными словами
    address_patterns = [
        # Индекс в начале (6 цифр) + адрес
        r'\d{6}[^,\n]*(?:,\s*[^,\n]+){0,5}(?:,\s*(?:г\.|город|г\s)[^,\n]+)?(?:,\s*(?:ул\.|улица|пр\.|проспект|пер\.|переулок|вн\.тер\.г\.)[^,\n]+)?(?:,\s*(?:д\.|дом)[^,\n]+)?(?:,\s*(?:лит\.|литера|лит)[^,\n]+)?(?:,\s*(?:помещ\.|помещение|офис|оф\.)[^,\n]+)?',
        # Адрес без индекса, начинающийся с города или улицы
        r'(?:г\.|город|г\s|ул\.|улица|пр\.|проспект|пер\.|переулок|вн\.тер\.г\.)[^,\n]+(?:,\s*[^,\n]+){0,6}(?:,\s*(?:д\.|дом)[^,\n]+)?(?:,\s*(?:лит\.|литера|лит)[^,\n]+)?(?:,\s*(?:помещ\.|помещение|офис|оф\.)[^,\n]+)?',
    ]
    
    address = ""
    found_addresses = []
    for pattern in address_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            found_addresses.extend(matches)
    
    if found_addresses:
        # Берем самый длинный адрес (обычно он самый полный)
        address = max(found_addresses, key=len).strip()
        # Очищаем от лишних символов в конце и начале
        address = re.sub(r'^[,\s]+', '', address)
        address = re.sub(r'[,\s]+$', '', address)
        # Ограничиваем длину адреса
        if len(address) > 200:
            address = address[:200] + "..."
    
    return phones_str, inn, fio, website, company, address

def is_reply_message(headers: dict) -> bool:
    """Определяет, является ли письмо ответом на другое письмо"""
    # Проверяем заголовки In-Reply-To и References
    in_reply_to = headers.get('in-reply-to', '')
    references = headers.get('references', '')
    
    # Также проверяем тему - если начинается с "Re:" или "Fwd:", это ответ/пересылка
    subject = headers.get('subject', '')
    subject_lower = subject.lower()
    
    return bool(in_reply_to or references or 
                subject_lower.startswith('re:') or 
                subject_lower.startswith('fwd:') or
                subject_lower.startswith('fwd') or
                subject_lower.startswith('fw:'))

# ================= SAFE API CALLS =================
def safe_api_call(func, *args, **kwargs):
    last_exception = None
    
    # Добавляем задержку перед каждым запросом для снижения нагрузки
    time.sleep(API_DELAY)
    
    for attempt in range(RETRY_COUNT):
        try:
            if attempt > 0:
                delay = min(2 ** attempt + 3, 30)
                logger.info(f"Повторная попытка через {delay} секунд (попытка {attempt+1}/{RETRY_COUNT})")
                time.sleep(delay)
            
            request = func(*args, **kwargs)
            
            if hasattr(request, 'execute'):
                return request.execute()
            return request
            
        except (ssl.SSLError, urllib3.exceptions.SSLError) as e:
            error_str = str(e)
            logger.warning(f"SSL Error (attempt {attempt+1}/{RETRY_COUNT}): {error_str[:100]}")
            last_exception = e
            
            # Для SSL ошибок делаем меньше попыток
            if attempt >= 2:
                logger.error(f"SSL ошибка после {attempt+1} попыток, пропускаем")
                return None
            time.sleep(3)
            
        except HttpError as e:
            if e.resp.status in [429, 503, 500]:
                logger.warning(f"HTTP {e.resp.status} (attempt {attempt+1}/{RETRY_COUNT})")
                last_exception = e
                time.sleep(5)
                continue
            raise
            
        except Exception as e:
            error_str = str(e)
            if "IncompleteRead" in error_str or "Remote end closed" in error_str:
                logger.warning(f"Сетевая ошибка (attempt {attempt+1}/{RETRY_COUNT}): {e}")
                last_exception = e
                time.sleep(3)
                continue
            
            if "SSL" in error_str or "DECRYPTION_FAILED" in error_str or "WRONG_VERSION_NUMBER" in error_str:
                logger.warning(f"SSL-related error (attempt {attempt+1}/{RETRY_COUNT}): {error_str[:100]}")
                last_exception = e
                if attempt >= 2:
                    return None
                time.sleep(3)
                continue
                
            logger.warning(f"API error (attempt {attempt+1}/{RETRY_COUNT}): {e}")
            last_exception = e
            if attempt < RETRY_COUNT - 1:
                time.sleep(2)
                continue
    
    logger.error(f"Все попытки исчерпаны: {last_exception}")
    raise last_exception if last_exception else Exception("Неизвестная ошибка API")

# ================= ATTACHMENTS =================
def parse_attachment(service, msg_id: str, part: Dict) -> str:
    MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024
    
    try:
        filename = part.get("filename", "").lower()
        if not filename:
            return ""
        
        att_id = part['body'].get('attachmentId')
        if not att_id:
            return ""
        
        size = int(part['body'].get('size', 0))
        if size > MAX_ATTACHMENT_SIZE:
            return f"[Вложение слишком большое: {filename}]"
        
        attachment = safe_api_call(
            service.users().messages().attachments().get,
            userId='me', messageId=msg_id, id=att_id
        )
        
        if attachment is None:
            return "[Ошибка загрузки вложения: SSL ошибка]"
        
        file_data = base64.urlsafe_b64decode(attachment['data'])
        text = ""
        
        if filename.endswith(".pdf"):
            with pdfplumber.open(io.BytesIO(file_data)) as pdf:
                for i, page in enumerate(pdf.pages):
                    if i > 20:
                        text += "\n[Обрезано после 20 страниц]"
                        break
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
                        
        elif filename.endswith((".docx", ".doc")):
            doc = Document(io.BytesIO(file_data))
            for para in doc.paragraphs:
                text += para.text + "\n"
                
        elif filename.endswith(".txt"):
            text = file_data.decode('utf-8', errors='ignore')
            
        return clean_text(text)
        
    except Exception as e:
        logger.error(f"Attachment error: {e}")
        return f"[Ошибка вложения: {str(e)}]"

# ================= MESSAGE PROCESSING =================
def process_message(service, msg_id: str, state: ThreadSafeState, skip_replies: bool = False, skip_text: bool = False) -> Optional[EmailData]:
    if state.is_cancelled():
        return None
    
    try:
        msg = safe_api_call(
            service.users().messages().get,
            userId='me', id=msg_id, format='full'
        )
        
        if msg is None:
            logger.warning(f"Пропуск письма {msg_id} из-за SSL ошибки")
            return None
        
        payload = msg.get('payload', {})
        headers = {h['name'].lower(): h['value'] for h in payload.get('headers', [])}
        
        # Проверяем, является ли письмо ответом
        if skip_replies and is_reply_message(headers):
            logger.info(f"Пропуск ответа: {msg_id}")
            return None
        
        subject = headers.get('subject', 'Без темы')
        subject = clean_text(subject)
        
        date_str = format_date(headers.get('date', ''))
        
        sender_raw = headers.get('from', 'Неизвестно')
        sender = extract_email_from_sender(sender_raw)
        
        body = ""
        has_attachments = False
        attachment_tasks = []
        
        def process_parts(parts):
            nonlocal body, has_attachments
            for part in parts:
                mime_type = part.get('mimeType', '')
                
                if mime_type == 'text/plain' and part['body'].get('data'):
                    try:
                        decoded = base64.urlsafe_b64decode(part['body']['data'])
                        body += decoded.decode('utf-8', errors='ignore')
                    except Exception as e:
                        logger.warning(f"Ошибка декодирования text/plain: {e}")
                    
                elif mime_type == 'text/html' and part['body'].get('data'):
                    try:
                        decoded = base64.urlsafe_b64decode(part['body']['data'])
                        html = decoded.decode('utf-8', errors='ignore')
                        body += clean_html(html)
                    except Exception as e:
                        logger.warning(f"Ошибка декодирования text/html: {e}")
                    
                elif part.get('filename'):
                    has_attachments = True
                    attachment_tasks.append(part)
                
                if 'parts' in part:
                    process_parts(part['parts'])
        
        if 'parts' in payload:
            process_parts(payload['parts'])
        elif payload.get('body', {}).get('data'):
            try:
                decoded = base64.urlsafe_b64decode(payload['body']['data'])
                body = decoded.decode('utf-8', errors='ignore')
            except Exception as e:
                logger.warning(f"Ошибка декодирования тела письма: {e}")
        
        body = clean_text(body)
        
        # Если установлена галочка "не читать текст", не обрабатываем вложения
        # Но нам все равно нужно прочитать текст для извлечения данных
        if not skip_text and attachment_tasks and not state.is_cancelled():
            with ThreadPoolExecutor(max_workers=ATTACHMENT_WORKERS) as pool:
                futures = [
                    pool.submit(parse_attachment, service, msg_id, p) 
                    for p in attachment_tasks
                ]
                for future in futures:
                    try:
                        att_text = future.result(timeout=30)
                        if att_text:
                            body += "\n\n[ВЛОЖЕНИЕ]:\n" + att_text
                    except Exception as e:
                        logger.error(f"Attachment processing error: {e}")
        
        body = clean_text(body)
        
        # Извлекаем данные из текста (телефон, ИНН, ФИО, сайт, компания, адрес)
        phone, inn, fio, website, company, address = extract_data(body)
        
        # Если установлена галочка "не читать текст", очищаем текст после извлечения данных
        if skip_text:
            body = ""
        
        return EmailData(
            date=date_str,
            from_email=sender,
            subject=subject,
            phone=phone,
            inn=inn,
            text=body,
            fio=fio,
            website=website,
            company=company,
            address=address,
            has_attachments=has_attachments,
            processed_at=datetime.now().isoformat()
        )
        
    except Exception as e:
        logger.error(f"Message processing error {msg_id}: {e}")
        return None

# ================= STATE MANAGEMENT =================
def save_state(data: List[EmailData], processed_ids: set, output_file: str = "emails_chunk"):
    try:
        state = {
            "processed_ids": list(processed_ids),
            "last_save": datetime.now().isoformat(),
            "count": len(data)
        }
        
        temp_state = STATE_FILE + ".tmp"
        with open(temp_state, 'w', encoding='utf-8') as f:
            json.dump(state, f)
        os.replace(temp_state, STATE_FILE)
        
        if data:
            df = pd.DataFrame([d.to_dict() for d in data])
            temp_excel = f"{output_file}.tmp.xlsx"
            final_excel = f"{output_file}.xlsx"
            try:
                logger.info(f"Создание Excel файла: {final_excel} ({len(data)} записей)")
                df.to_excel(temp_excel, index=False, engine='openpyxl')
                
                if os.path.exists(temp_excel):
                    file_size = os.path.getsize(temp_excel)
                    logger.info(f"Временный файл создан: {temp_excel}, размер: {file_size} байт")
                    
                    if os.path.exists(final_excel):
                        try:
                            os.remove(final_excel)
                            logger.info(f"Удален старый файл: {final_excel}")
                        except Exception as remove_err:
                            logger.warning(f"Не удалось удалить старый файл {final_excel}: {remove_err}")
                            backup_name = f"{output_file}_old_{int(time.time())}.xlsx"
                            try:
                                os.rename(final_excel, backup_name)
                                logger.info(f"Старый файл переименован в: {backup_name}")
                            except:
                                pass
                    
                    os.replace(temp_excel, final_excel)
                    
                    if os.path.exists(final_excel):
                        abs_path = os.path.abspath(final_excel)
                        logger.info(f"✓ Excel файл успешно сохранен: {abs_path} ({len(data)} записей)")
                    else:
                        logger.error(f"Файл не найден после переименования: {final_excel}")
                else:
                    logger.error(f"Временный файл не создан: {temp_excel}")
            except PermissionError as perm_error:
                error_msg = f"Нет доступа к файлу {final_excel}. Возможно, файл открыт в другой программе: {perm_error}"
                logger.error(error_msg)
                raise Exception(error_msg)
            except Exception as excel_error:
                logger.error(f"Ошибка создания Excel файла {final_excel}: {excel_error}", exc_info=True)
                raise
            
    except Exception as e:
        logger.error(f"State save error: {e}")
        raise

def load_state() -> tuple:
    if not os.path.exists(STATE_FILE):
        return set(), []
    
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            state = json.load(f)
        processed_ids = set(state.get("processed_ids", []))
        
        data = []
        if os.path.exists("emails_chunk.xlsx"):
            df = pd.read_excel("emails_chunk.xlsx")
            data = [EmailData(**row) for row in df.to_dict('records')]
            
        return processed_ids, data
    except Exception as e:
        logger.error(f"State load error: {e}")
        return set(), []

# ================= EXPORT ENGINE =================
class ExportEngine:
    def __init__(self, gui_queue: queue.Queue, skip_replies: bool = False, skip_text: bool = False):
        self.gui_queue = gui_queue
        self.state = ThreadSafeState()
        self.service = None
        self._stop_event = threading.Event()
        self.skip_replies = skip_replies
        self.skip_text = skip_text
        
    def stop(self):
        self._stop_event.set()
        self.state.cancel()
        
    def log_progress(self, processed: int, total: int, current_id: str = "", current_subject: str = "", current_from: str = ""):
        try:
            self.gui_queue.put({
                'type': 'progress',
                'processed': processed,
                'total': total,
                'current_id': current_id,
                'current_subject': current_subject,
                'current_from': current_from,
                'speed': self._calculate_speed(processed)
            })
        except:
            pass
    
    def _calculate_speed(self, processed: int) -> float:
        if not hasattr(self, '_start_time'):
            self._start_time = time.time()
        elapsed = (time.time() - self._start_time) / 60
        return processed / elapsed if elapsed > 0 else 0
    
    def build_query(self, start_date: Optional[datetime], end_date: Optional[datetime]) -> str:
        query_parts = []
        
        if start_date:
            query_parts.append(f"after:{start_date.strftime('%Y/%m/%d')}")
        if end_date:
            next_day = end_date + pd.Timedelta(days=1)
            query_parts.append(f"before:{next_day.strftime('%Y/%m/%d')}")
            
        return " ".join(query_parts)
    
    def fetch_message_ids(self, query: str) -> List[str]:
        all_ids = []
        next_page = None
        
        while not self._stop_event.is_set():
            try:
                result = safe_api_call(
                    self.service.users().messages().list,
                    userId='me', 
                    q=query,
                    maxResults=500,
                    pageToken=next_page
                )
                
                if result is None:
                    logger.error("Не удалось получить список писем из-за SSL ошибки")
                    break
                
                messages = result.get('messages', [])
                all_ids.extend([m['id'] for m in messages])
                
                self.gui_queue.put({
                    'type': 'status',
                    'message': f"Загружено ID: {len(all_ids)}"
                })
                
                next_page = result.get('nextPageToken')
                if not next_page:
                    break
                
                # Добавляем небольшую задержку между запросами страниц для снижения нагрузки
                time.sleep(API_DELAY)
                    
            except Exception as e:
                logger.error(f"Fetch error: {e}")
                raise
                
        return all_ids
    
    def process_batch(self, batch_ids: List[str], batch_start_index: int = 0, total_count: int = 0) -> List[EmailData]:
        results = []
        batch_start_time = time.time()
        BATCH_TIMEOUT = 600  # 10 минут на батч
        
        logger.info(f"Обработка батча из {len(batch_ids)} писем (skip_replies={self.skip_replies}, skip_text={self.skip_text})")
        
        # Если MAX_WORKERS = 1, обрабатываем последовательно для снижения нагрузки
        if MAX_WORKERS == 1:
            completed_count = 0
            for msg_id in batch_ids:
                if time.time() - batch_start_time > BATCH_TIMEOUT:
                    logger.warning(f"Таймаут батча ({BATCH_TIMEOUT} сек), прерываем обработку")
                    break
                
                if self._stop_event.is_set():
                    logger.info("Остановка запрошена пользователем")
                    break
                
                try:
                    result = process_message(self.service, msg_id, self.state, self.skip_replies, self.skip_text)
                    if result and self.state.add_processed(msg_id, result):
                        results.append(result)
                        completed_count += 1
                        
                        current_index = batch_start_index + completed_count
                        subject_preview = result.subject[:50] + "..." if len(result.subject) > 50 else result.subject
                        from_preview = result.from_email[:30] + "..." if len(result.from_email) > 30 else result.from_email
                        
                        self.log_progress(
                            processed=current_index,
                            total=total_count,
                            current_id=msg_id,
                            current_subject=subject_preview,
                            current_from=from_preview
                        )
                except Exception as e:
                    error_str = str(e)
                    logger.error(f"Ошибка обработки письма {msg_id}: {error_str}")
                    completed_count += 1
                    current_index = batch_start_index + completed_count
                    self.log_progress(
                        processed=current_index,
                        total=total_count,
                        current_id=msg_id,
                        current_subject="[Ошибка - пропущено]",
                        current_from=""
                    )
        else:
            # Параллельная обработка для MAX_WORKERS > 1
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                future_to_id = {
                    executor.submit(process_message, self.service, mid, self.state, self.skip_replies, self.skip_text): mid 
                    for mid in batch_ids
                }
                
                completed_count = 0
                for future in as_completed(future_to_id):
                    if time.time() - batch_start_time > BATCH_TIMEOUT:
                        logger.warning(f"Таймаут батча ({BATCH_TIMEOUT} сек), прерываем обработку")
                        executor.shutdown(wait=False)
                        break
                    
                    if self._stop_event.is_set():
                        logger.info("Остановка запрошена пользователем")
                        executor.shutdown(wait=False)
                        break
                        
                    msg_id = future_to_id[future]
                    try:
                        result = future.result(timeout=180)
                        if result and self.state.add_processed(msg_id, result):
                            results.append(result)
                            completed_count += 1
                            
                            current_index = batch_start_index + completed_count
                            subject_preview = result.subject[:50] + "..." if len(result.subject) > 50 else result.subject
                            from_preview = result.from_email[:30] + "..." if len(result.from_email) > 30 else result.from_email
                            
                            self.log_progress(
                                processed=current_index,
                                total=total_count,
                                current_id=msg_id,
                                current_subject=subject_preview,
                                current_from=from_preview
                            )
                            
                    except TimeoutError:
                        logger.error(f"Таймаут при обработке письма {msg_id}")
                        completed_count += 1
                        current_index = batch_start_index + completed_count
                        self.log_progress(
                            processed=current_index,
                            total=total_count,
                            current_id=msg_id,
                            current_subject="[Таймаут обработки]",
                            current_from=""
                        )
                    except Exception as e:
                        error_str = str(e)
                        logger.error(f"Ошибка обработки письма {msg_id}: {error_str}")
                        completed_count += 1
                        current_index = batch_start_index + completed_count
                        self.log_progress(
                            processed=current_index,
                            total=total_count,
                            current_id=msg_id,
                            current_subject="[Ошибка - пропущено]",
                            current_from=""
                        )
                        continue
        
        logger.info(f"Батч завершен: обработано {completed_count}/{len(batch_ids)} писем, получено {len(results)} результатов")
        return results
    
    def run(self, start_date: Optional[datetime], end_date: Optional[datetime]):
        try:
            current_dir = os.getcwd()
            test_file = os.path.join(current_dir, ".write_test")
            try:
                with open(test_file, 'w') as f:
                    f.write("test")
                os.remove(test_file)
                logger.info(f"Рабочая директория: {current_dir}")
            except Exception as e:
                error_msg = f"Нет прав на запись в директорию {current_dir}: {e}"
                logger.error(error_msg)
                self.gui_queue.put({'type': 'error', 'message': error_msg})
                return
            
            self.gui_queue.put({'type': 'status', 'message': 'Аутентификация...'})
            creds = authenticate()
            
            self.service = create_gmail_service(creds)
            
            processed_ids, existing_data = load_state()
            
            query = self.build_query(start_date, end_date)
            self.gui_queue.put({'type': 'status', 'message': f'Query: {query}'})
            
            all_ids = self.fetch_message_ids(query)
            total = len(all_ids)
            
            if total == 0:
                self.gui_queue.put({'type': 'error', 'message': 'Писем не найдено'})
                return
            
            remaining_ids = [mid for mid in all_ids if mid not in processed_ids]
            self.gui_queue.put({
                'type': 'status', 
                'message': f'Всего писем: {total}, осталось обработать: {len(remaining_ids)}'
            })
            
            if total > 0:
                self.log_progress(
                    processed=len(processed_ids),
                    total=total,
                    current_id="",
                    current_subject="Подготовка к обработке...",
                    current_from=""
                )
            
            all_data = existing_data.copy()
            logger.info(f"Начало обработки. Существующих данных: {len(existing_data)}, ID для обработки: {len(remaining_ids)}")
            
            if existing_data:
                try:
                    logger.info(f"Создание начального файла из существующих данных: {len(existing_data)} записей")
                    df_init = pd.DataFrame([d.to_dict() for d in existing_data])
                    df_init = df_init.drop_duplicates(subset=['date', 'from_email', 'subject'])
                    init_file = "gmail_export_final.xlsx"
                    temp_init = "gmail_export_final.tmp.xlsx"
                    df_init.to_excel(temp_init, index=False, engine='openpyxl')
                    if os.path.exists(temp_init):
                        os.replace(temp_init, init_file)
                        abs_path = os.path.abspath(init_file)
                        logger.info(f"Начальный файл создан: {abs_path}")
                        self.gui_queue.put({
                            'type': 'status',
                            'message': f'Начальный файл создан: {len(df_init)} записей'
                        })
                except Exception as init_err:
                    logger.warning(f"Не удалось создать начальный файл: {init_err}")
            
            for i in range(0, len(remaining_ids), BATCH_SIZE):
                if self._stop_event.is_set():
                    logger.warning("Процесс прерван пользователем")
                    if all_data:
                        logger.info(f"Сохранение данных перед прерыванием: {len(all_data)} записей")
                        try:
                            save_state(all_data, self.state._processed_ids)
                            df = pd.DataFrame([d.to_dict() for d in all_data])
                            df = df.drop_duplicates(subset=['date', 'from_email', 'subject'])
                            interrupted_file = "gmail_export_interrupted.xlsx"
                            temp_interrupted = "gmail_export_interrupted.tmp.xlsx"
                            df.to_excel(temp_interrupted, index=False, engine='openpyxl')
                            if os.path.exists(temp_interrupted):
                                os.replace(temp_interrupted, interrupted_file)
                                abs_path = os.path.abspath(interrupted_file)
                                logger.info(f"Создан файл после прерывания: {abs_path}")
                                self.gui_queue.put({
                                    'type': 'status',
                                    'message': f'Создан файл после прерывания: {abs_path}'
                                })
                        except Exception as save_err:
                            logger.error(f"Ошибка сохранения при прерывании: {save_err}")
                    break
                    
                batch = remaining_ids[i:i+BATCH_SIZE]
                batch_num = i // BATCH_SIZE + 1
                total_batches = (len(remaining_ids) + BATCH_SIZE - 1) // BATCH_SIZE
                logger.info(f"Обработка батча {batch_num}/{total_batches}: {len(batch)} сообщений")
                
                self.gui_queue.put({
                    'type': 'status',
                    'message': f'Обработка батча {batch_num}/{total_batches}...'
                })
                
                batch_start_index = len(processed_ids) + i
                batch_start_time = time.time()
                try:
                    logger.info(f"Начало обработки батча {batch_num}, таймаут: 600 секунд")
                    batch_results = self.process_batch(batch, batch_start_index=batch_start_index, total_count=total)
                    batch_duration = time.time() - batch_start_time
                    logger.info(f"Батч {batch_num} обработан за {batch_duration:.1f} сек: получено {len(batch_results)} результатов")
                    all_data.extend(batch_results)
                    
                    # Добавляем задержку между батчами для снижения нагрузки на API
                    if batch_num < total_batches:
                        logger.info(f"Пауза {BATCH_DELAY} сек перед следующим батчем...")
                        time.sleep(BATCH_DELAY)
                    
                    processed_count = len(processed_ids) + i + len(batch_results)
                    
                    if all_data:
                        if processed_count % AUTOSAVE_EVERY == 0:
                            logger.info(f"Автосохранение на {processed_count} записях")
                            try:
                                save_state(all_data, self.state._processed_ids)
                                self.gui_queue.put({'type': 'autosave', 'count': processed_count})
                            except Exception as save_err:
                                logger.error(f"Ошибка автосохранения: {save_err}")
                        
                        try:
                            df_interim = pd.DataFrame([d.to_dict() for d in all_data])
                            df_interim = df_interim.drop_duplicates(subset=['date', 'from_email', 'subject'])
                            interim_file = "gmail_export_interim.xlsx"
                            temp_interim = "gmail_export_interim.tmp.xlsx"
                            df_interim.to_excel(temp_interim, index=False, engine='openpyxl')
                            if os.path.exists(temp_interim):
                                os.replace(temp_interim, interim_file)
                                abs_interim = os.path.abspath(interim_file)
                                logger.info(f"✓ Промежуточный файл обновлен: {abs_interim} ({len(df_interim)} записей)")
                                final_interim = "gmail_export_final.xlsx"
                                try:
                                    os.replace(interim_file, final_interim)
                                    logger.info(f"✓ Финальный файл обновлен: {os.path.abspath(final_interim)}")
                                except Exception as final_err:
                                    logger.warning(f"Не удалось обновить финальный файл: {final_err}")
                        except Exception as interim_err:
                            logger.warning(f"Не удалось создать промежуточный файл: {interim_err}")
                            
                except Exception as batch_err:
                    logger.error(f"Ошибка обработки батча {batch_num}: {batch_err}", exc_info=True)
                    self.gui_queue.put({
                        'type': 'status',
                        'message': f'Ошибка в батче {batch_num}, продолжаем...'
                    })
                    if all_data:
                        try:
                            logger.info(f"Экстренное сохранение после ошибки батча: {len(all_data)} записей")
                            save_state(all_data, self.state._processed_ids)
                        except:
                            pass
            
            logger.info(f"Обработка завершена. Всего данных: {len(all_data)}")
            
            if not all_data:
                chunk_file = "emails_chunk.xlsx"
                if os.path.exists(chunk_file):
                    try:
                        logger.info(f"Загрузка данных из {chunk_file}...")
                        df_chunk = pd.read_excel(chunk_file)
                        all_data = [EmailData(**row) for row in df_chunk.to_dict('records')]
                        logger.info(f"Загружено из {chunk_file}: {len(all_data)} записей")
                    except Exception as chunk_err:
                        logger.error(f"Ошибка загрузки {chunk_file}: {chunk_err}")
                
            if not all_data:
                interim_file = "gmail_export_interim.xlsx"
                if os.path.exists(interim_file):
                    logger.info(f"Используем промежуточный файл: {interim_file}")
                    try:
                        df_interim = pd.read_excel(interim_file)
                        all_data = [EmailData(**row) for row in df_interim.to_dict('records')]
                        logger.info(f"Загружено из промежуточного файла: {len(all_data)} записей")
                    except Exception as load_err:
                        logger.error(f"Ошибка загрузки промежуточного файла: {load_err}")
            
            logger.info(f"Начало создания финального файла... Всего данных: {len(all_data) if all_data else 0}")
            
            if all_data:
                try:
                    logger.info("Финальное сохранение состояния...")
                    save_state(all_data, self.state._processed_ids)
                    logger.info("Состояние сохранено успешно")
                except Exception as save_err:
                    logger.warning(f"Ошибка финального сохранения состояния: {save_err}")
            
            try:
                if all_data:
                    try:
                        df = pd.DataFrame([d.to_dict() for d in all_data])
                        df = df.drop_duplicates(subset=['date', 'from_email', 'subject'])
                        
                        final_file = "gmail_export_final.xlsx"
                        logger.info(f"Создание финального Excel файла: {final_file} ({len(df)} записей)")
                        
                        temp_final = "gmail_export_final.tmp.xlsx"
                        
                        try:
                            df.to_excel(temp_final, index=False, engine='openpyxl')
                        except Exception as create_err:
                            error_msg = f"Ошибка создания временного Excel файла: {create_err}"
                            logger.error(error_msg, exc_info=True)
                            raise Exception(error_msg)
                        
                        if os.path.exists(temp_final):
                            file_size = os.path.getsize(temp_final)
                            logger.info(f"Временный файл создан: {temp_final}, размер: {file_size} байт")
                            
                            if os.path.exists(final_file):
                                try:
                                    os.remove(final_file)
                                    logger.info(f"Удален старый финальный файл: {final_file}")
                                except PermissionError:
                                    backup_name = f"gmail_export_final_backup_{int(time.time())}.xlsx"
                                    try:
                                        os.rename(final_file, backup_name)
                                        logger.info(f"Старый файл переименован в: {backup_name}")
                                    except Exception as rename_err:
                                        logger.warning(f"Не удалось переименовать старый файл: {rename_err}")
                                except Exception as remove_err:
                                    logger.warning(f"Ошибка удаления старого файла: {remove_err}")
                            
                            try:
                                os.replace(temp_final, final_file)
                            except PermissionError as perm_err:
                                error_msg = f"Нет доступа к файлу {final_file}. Возможно, файл открыт в Excel или другой программе: {perm_err}"
                                logger.error(error_msg)
                                alt_file = f"gmail_export_final_{int(time.time())}.xlsx"
                                try:
                                    os.rename(temp_final, alt_file)
                                    abs_path = os.path.abspath(alt_file)
                                    logger.info(f"Файл сохранен под альтернативным именем: {abs_path}")
                                    self.gui_queue.put({
                                        'type': 'complete',
                                        'count': len(df),
                                        'file': abs_path
                                    })
                                    return
                                except Exception as alt_err:
                                    logger.error(f"Не удалось сохранить под альтернативным именем: {alt_err}")
                                raise Exception(error_msg)
                            
                            if os.path.exists(final_file):
                                logger.info(f"Финальный Excel файл успешно создан: {final_file}")
                                
                                for f in [STATE_FILE, "emails_chunk.xlsx"]:
                                    if os.path.exists(f):
                                        try:
                                            os.remove(f)
                                            logger.info(f"Удален временный файл: {f}")
                                        except Exception as e:
                                            logger.warning(f"Не удалось удалить временный файл {f}: {e}")
                                
                                abs_file_path = os.path.abspath(final_file)
                                logger.info(f"✓ Файл успешно создан: {abs_file_path} ({len(df)} записей)")
                                
                                self.gui_queue.put({
                                    'type': 'complete',
                                    'count': len(df),
                                    'file': abs_file_path
                                })
                                logger.info("Процесс экспорта завершен успешно")
                            else:
                                error_msg = f"Файл не найден после переименования: {final_file}"
                                logger.error(error_msg)
                                self.gui_queue.put({'type': 'error', 'message': error_msg})
                        else:
                            error_msg = f"Временный файл не создан: {temp_final}"
                            logger.error(error_msg)
                            self.gui_queue.put({'type': 'error', 'message': error_msg})
                        
                    except Exception as excel_error:
                        error_msg = f"Ошибка создания финального Excel файла: {excel_error}"
                        logger.exception(error_msg)
                        self.gui_queue.put({'type': 'error', 'message': error_msg})
                        if all_data:
                            try:
                                logger.info("Попытка создать файл после ошибки...")
                                df = pd.DataFrame([d.to_dict() for d in all_data])
                                df = df.drop_duplicates(subset=['date', 'from_email', 'subject'])
                                error_file = f"gmail_export_error_{int(time.time())}.xlsx"
                                df.to_excel(error_file, index=False, engine='openpyxl')
                                abs_path = os.path.abspath(error_file)
                                logger.info(f"Файл создан после ошибки: {abs_path}")
                                self.gui_queue.put({
                                    'type': 'status',
                                    'message': f'Файл создан после ошибки: {abs_path}'
                                })
                            except Exception as fallback_err:
                                logger.error(f"Не удалось создать файл даже после ошибки: {fallback_err}")
                else:
                    if existing_data:
                        logger.info(f"Используем существующие данные: {len(existing_data)} записей")
                        try:
                            df = pd.DataFrame([d.to_dict() for d in existing_data])
                            df = df.drop_duplicates(subset=['date', 'from_email', 'subject'])
                            
                            final_file = "gmail_export_final.xlsx"
                            temp_final = "gmail_export_final.tmp.xlsx"
                            df.to_excel(temp_final, index=False, engine='openpyxl')
                            
                            if os.path.exists(temp_final):
                                os.replace(temp_final, final_file)
                                abs_file_path = os.path.abspath(final_file)
                                logger.info(f"Файл создан из существующих данных: {abs_file_path}")
                                self.gui_queue.put({
                                    'type': 'complete',
                                    'count': len(df),
                                    'file': abs_file_path
                                })
                            else:
                                error_msg = "Не удалось создать файл из существующих данных"
                                logger.error(error_msg)
                                self.gui_queue.put({'type': 'error', 'message': error_msg})
                        except Exception as e:
                            error_msg = f"Ошибка создания файла из существующих данных: {e}"
                            logger.exception(error_msg)
                            self.gui_queue.put({'type': 'error', 'message': error_msg})
                    else:
                        error_msg = "Нет данных для экспорта"
                        logger.warning(error_msg)
                        self.gui_queue.put({'type': 'error', 'message': error_msg})
                        
            except Exception as excel_final_error:
                error_msg = f"Ошибка создания финального файла: {excel_final_error}"
                logger.exception(error_msg)
                self.gui_queue.put({'type': 'error', 'message': error_msg})
            
        except Exception as e:
            logger.exception("Export failed")
            error_msg = f"Ошибка экспорта: {str(e)}"
            self.gui_queue.put({'type': 'error', 'message': error_msg})
            
            try:
                buffer_data = self.state.get_and_clear_buffer()
                
                try:
                    _, existing_data = load_state()
                    if existing_data:
                        logger.info(f"Найдены существующие данные: {len(existing_data)} записей")
                        buffer_data.extend(existing_data)
                except:
                    pass
                
                if buffer_data:
                    logger.info(f"Сохранение данных при ошибке: {len(buffer_data)} записей")
                    
                    try:
                        save_state(buffer_data, self.state._processed_ids)
                    except:
                        pass
                    
                    try:
                        df = pd.DataFrame([d.to_dict() for d in buffer_data])
                        df = df.drop_duplicates(subset=['date', 'from_email', 'subject'])
                        partial_file = "gmail_export_partial.xlsx"
                        temp_partial = "gmail_export_partial.tmp.xlsx"
                        df.to_excel(temp_partial, index=False, engine='openpyxl')
                        
                        if os.path.exists(temp_partial):
                            os.replace(temp_partial, partial_file)
                            abs_path = os.path.abspath(partial_file)
                            logger.info(f"Создан файл с частичными данными: {abs_path} ({len(df)} записей)")
                            self.gui_queue.put({
                                'type': 'status',
                                'message': f'Создан файл с частичными данными: {abs_path}'
                            })
                        else:
                            logger.error("Не удалось создать файл с частичными данными")
                    except Exception as excel_err:
                        logger.error(f"Ошибка создания файла с частичными данными: {excel_err}")
                else:
                    logger.warning("Нет данных для сохранения при ошибке")
            except Exception as save_error:
                logger.error(f"Ошибка при сохранении данных после сбоя: {save_error}")

# ================= GUI =================
class GmailExportApp:
    def __init__(self):
        try:
            logger.info("Инициализация GUI...")
            self.root = ctk.CTk()
            logger.info("Окно создано")
            self.root.geometry("800x600")
            self.root.title("Gmail Export PRO ENTERPRISE v2.0")
            
            self.engine: Optional[ExportEngine] = None
            self.gui_queue = queue.Queue()
            self.processing_thread: Optional[threading.Thread] = None
            
            logger.info("Настройка UI...")
            self._setup_ui()
            logger.info("UI настроен")
            
            logger.info("Запуск проверки очереди...")
            self._check_queue()
            logger.info("Проверка очереди запущена")
            
            self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
            logger.info("GUI инициализирован успешно")
        except Exception as e:
            logger.exception(f"Ошибка инициализации GUI: {e}")
            raise
        
    def _setup_ui(self):
        try:
            logger.info("Создание элементов интерфейса...")
            date_frame = ctk.CTkFrame(self.root)
            date_frame.pack(pady=20, padx=20, fill='x')
            
            ctk.CTkLabel(date_frame, text="Диапазон дат", font=("Arial", 16, "bold")).pack()
            
            start_frame = tk.Frame(date_frame)
            start_frame.pack(pady=10)
            start_label = ctk.CTkLabel(date_frame, text="С:")
            start_label.pack(side='left', padx=5)
            logger.info("Создание DateEntry для начальной даты...")
            try:
                self.start_date = DateEntry(start_frame, width=12)
                self.start_date.pack(side='left')
            except Exception as date_err:
                logger.error(f"Ошибка создания DateEntry для начальной даты: {date_err}")
                raise
            
            end_frame = tk.Frame(date_frame)
            end_frame.pack(pady=10)
            end_label = ctk.CTkLabel(date_frame, text="По:")
            end_label.pack(side='left', padx=5)
            logger.info("Создание DateEntry для конечной даты...")
            try:
                self.end_date = DateEntry(end_frame, width=12)
                self.end_date.pack(side='left')
            except Exception as date_err:
                logger.error(f"Ошибка создания DateEntry для конечной даты: {date_err}")
                raise
            logger.info("DateEntry созданы успешно")
            
            # Добавляем галочки для опций
            options_frame = ctk.CTkFrame(date_frame)
            options_frame.pack(pady=10, fill='x')
            
            self.skip_replies_var = ctk.BooleanVar(value=False)
            self.skip_replies_checkbox = ctk.CTkCheckBox(
                options_frame,
                text="Не парсить ответы на письма (только первое входящее)",
                variable=self.skip_replies_var
            )
            self.skip_replies_checkbox.pack(side='left', padx=10)
            
            self.skip_text_var = ctk.BooleanVar(value=False)
            self.skip_text_checkbox = ctk.CTkCheckBox(
                options_frame,
                text="Не читать текст письма (только данные: телефон, ИНН, ФИО, сайт)",
                variable=self.skip_text_var
            )
            self.skip_text_checkbox.pack(side='left', padx=10)
        except Exception as e:
            logger.exception(f"Ошибка создания элементов дат: {e}")
            raise
        
        self.progress = ctk.CTkProgressBar(self.root, width=700)
        self.progress.pack(pady=20)
        self.progress.set(0)
        
        self.status_label = ctk.CTkLabel(self.root, text="Готов к работе", font=("Arial", 12))
        self.status_label.pack()
        
        self.speed_label = ctk.CTkLabel(self.root, text="")
        self.speed_label.pack()
        
        self.current_label = ctk.CTkLabel(self.root, text="")
        self.current_label.pack()
        
        btn_frame = ctk.CTkFrame(self.root)
        btn_frame.pack(pady=20)
        
        self.start_btn = ctk.CTkButton(
            btn_frame, 
            text="▶ Начать выгрузку",
            command=self.start_export,
            width=200,
            fg_color="green",
            hover_color="darkgreen"
        )
        self.start_btn.pack(side='left', padx=10)
        
        self.stop_btn = ctk.CTkButton(
            btn_frame,
            text="⏹ Остановить",
            command=self.stop_export,
            width=200,
            fg_color="red",
            hover_color="darkred",
            state="disabled"
        )
        self.stop_btn.pack(side='left', padx=10)
        
        self.log_text = ctk.CTkTextbox(self.root, height=150, width=700)
        self.log_text.pack(pady=10)
        self.log_text.insert("end", "Лог инициализирован...\n")
        self.log_text.configure(state="disabled")
        
    def log(self, message: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"{datetime.now().strftime('%H:%M:%S')} - {message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        
    def start_export(self):
        try:
            start = self.start_date.get_date()
            end = self.end_date.get_date()
            
            if start and end and start > end:
                self.show_error("Дата 'с' должна быть раньше 'по'")
                return
                
        except Exception as e:
            self.show_error(f"Ошибка дат: {e}")
            return
        
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.progress.set(0)
        
        # Получаем значения галочек
        skip_replies = self.skip_replies_var.get()
        skip_text = self.skip_text_var.get()
        
        logger.info(f"Запуск экспорта: skip_replies={skip_replies}, skip_text={skip_text}")
        
        self.engine = ExportEngine(self.gui_queue, skip_replies=skip_replies, skip_text=skip_text)
        self.processing_thread = threading.Thread(
            target=self.engine.run,
            args=(start, end),
            daemon=True
        )
        self.processing_thread.start()
        self.log("Экспорт запущен")
        
    def stop_export(self):
        if self.engine:
            self.engine.stop()
            self.log("Остановка запрошена...")
        self.stop_btn.configure(state="disabled")
        
    def _check_queue(self):
        try:
            while True:
                msg = self.gui_queue.get_nowait()
                
                if msg['type'] == 'progress':
                    processed = msg['processed']
                    total = msg['total']
                    progress_value = processed / total if total > 0 else 0
                    self.progress.set(progress_value)
                    
                    percent = int(progress_value * 100) if total > 0 else 0
                    status_text = f"Письмо {processed} из {total} ({percent}%)"
                    if msg.get('current_subject'):
                        subject = msg['current_subject']
                        if len(subject) > 60:
                            subject = subject[:57] + "..."
                        status_text += f" | {subject}"
                    self.status_label.configure(text=status_text)
                    
                    speed_text = f"Скорость: {msg['speed']:.1f} писем/мин"
                    if total > 0 and processed > 0 and msg['speed'] > 0:
                        remaining = total - processed
                        eta_minutes = remaining / msg['speed']
                        if eta_minutes < 1:
                            speed_text += f" | Осталось: <1 мин"
                        elif eta_minutes < 60:
                            speed_text += f" | Осталось: ~{eta_minutes:.0f} мин"
                        else:
                            eta_hours = eta_minutes / 60
                            speed_text += f" | Осталось: ~{eta_hours:.1f} ч"
                    self.speed_label.configure(text=speed_text)
                    
                    if msg.get('current_from'):
                        self.current_label.configure(text=f"От: {msg['current_from']}")
                    elif msg.get('current_id'):
                        self.current_label.configure(text=f"ID: {msg['current_id'][:30]}...")
                    else:
                        self.current_label.configure(text="")
                        
                elif msg['type'] == 'status':
                    if 'Обработка батча' not in msg['message']:
                        self.status_label.configure(text=msg['message'])
                    self.log(msg['message'])
                    
                elif msg['type'] == 'autosave':
                    self.log(f"Автосохранение: {msg['count']} писем")
                    
                elif msg['type'] == 'complete':
                    self.progress.set(1)
                    file_path = msg.get('file', 'gmail_export_final.xlsx')
                    self.show_success(f"Готово! Экспортировано {msg['count']} писем\n\nФайл сохранен:\n{file_path}")
                    self.log(f"✓ Файл успешно создан: {file_path}")
                    self.reset_ui()
                    
                elif msg['type'] == 'error':
                    self.show_error(f"Ошибка: {msg['message']}")
                    self.reset_ui()
                    
        except queue.Empty:
            pass
            
        self.root.after(100, self._check_queue)
        
    def reset_ui(self):
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.engine = None
        
    def show_error(self, message: str):
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Ошибка")
        dialog.geometry("400x150")
        dialog.transient(self.root)
        dialog.grab_set()
        
        icon_label = ctk.CTkLabel(
            dialog, 
            text="✕",
            font=("Arial", 40),
            text_color="red"
        )
        icon_label.pack(pady=10)
        
        msg_label = ctk.CTkLabel(dialog, text=message, wraplength=350)
        msg_label.pack(pady=10)
        
        btn = ctk.CTkButton(dialog, text="OK", command=dialog.destroy, width=100)
        btn.pack(pady=10)
        
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (400 // 2)
        y = (dialog.winfo_screenheight() // 2) - (150 // 2)
        dialog.geometry(f"+{x}+{y}")

    def show_success(self, message: str):
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Успех")
        dialog.geometry("400x150")
        dialog.transient(self.root)
        dialog.grab_set()
        
        icon_label = ctk.CTkLabel(
            dialog, 
            text="✓",
            font=("Arial", 40),
            text_color="green"
        )
        icon_label.pack(pady=10)
        
        msg_label = ctk.CTkLabel(dialog, text=message, wraplength=350)
        msg_label.pack(pady=10)
        
        btn = ctk.CTkButton(dialog, text="OK", command=dialog.destroy, width=100)
        btn.pack(pady=10)
        
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (400 // 2)
        y = (dialog.winfo_screenheight() // 2) - (150 // 2)
        dialog.geometry(f"+{x}+{y}")
        
    def on_closing(self):
        if self.engine:
            self.engine.stop()
        self.root.destroy()
        
    def run(self):
        try:
            logger.info("Запуск главного цикла GUI...")
            self.root.mainloop()
            logger.info("Главный цикл завершен")
        except Exception as e:
            logger.exception(f"Ошибка в главном цикле GUI: {e}")
            raise

if __name__ == "__main__":
    try:
        logger.info("Запуск приложения...")
        app = GmailExportApp()
        logger.info("GUI инициализирован, запуск главного цикла...")
        app.run()
    except Exception as e:
        error_msg = f"Критическая ошибка при запуске: {e}"
        logger.exception(error_msg)
        print(f"ОШИБКА: {error_msg}")
        print("Проверьте файл export_log.txt для подробностей")
        import traceback
        traceback.print_exc()
        input("Нажмите Enter для выхода...")
