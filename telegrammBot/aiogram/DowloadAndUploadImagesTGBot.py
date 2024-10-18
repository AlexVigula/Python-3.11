########################################################
#                                                       #
#    Отправка и изменения изображения в телеграмм боте  #
#    dev Alex Vigula      tg @gunsxp                    #
#                                                       #
#########################################################

import os
import asyncio
import aiomysql
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram import F
from aiogram.types import Message, InputFile, KeyboardButton, ReplyKeyboardMarkup, FSInputFile
from dotenv import load_dotenv
import imghdr
from PIL import Image
import io

load_dotenv()

API_TOKEN = os.getenv('BOT_TOKEN_TEST')  # Замените на ваш токен
MYSQL_HOST = os.getenv('MYSQL_HOST')
MYSQL_USER = os.getenv('MYSQL_USER')
MYSQL_PASS = os.getenv('MYSQL_PASS')
MYSQL_DB = os.getenv('MYSQL_DB')

# Инициализация бота и диспетчера
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Папка для хранения изображений
IMAGES_DIR = 'imagesss'
if not os.path.exists(IMAGES_DIR):
    os.makedirs(IMAGES_DIR)

# Создаем клавиатуру с кнопками "Профиль" и "Изменить изображение"
def create_main_kb() -> ReplyKeyboardMarkup:
    profile_button = KeyboardButton(text="👤 Профиль")
    edit_button = KeyboardButton(text="🖼 Изменить изображение")
    keyboard = ReplyKeyboardMarkup(keyboard=[[profile_button, edit_button]], resize_keyboard=True)
    return keyboard

async def save_photo_path_to_db(user_id, file_path):
    try:
        conn = await aiomysql.connect(
            host=os.getenv('MYSQL_HOST'),
            port=3306,
            user=os.getenv('MYSQL_USER'),
            password=os.getenv('MYSQL_PASS'),
            db=os.getenv('MYSQL_DB')
        )
        async with conn.cursor() as cursor:
            await cursor.execute("UPDATE users SET photo_path=%s WHERE id=%s", (file_path, user_id))
            await conn.commit()
        print(f"Путь к изображению успешно сохранен для пользователя {user_id}")
    except Exception as e:
        print(f"Ошибка при сохранении пути к фото в базу данных: {e}")
    finally:
        if conn:
            conn.close()

async def get_photo_path_from_db(user_id):
    try:
        conn = await aiomysql.connect(
            host=os.getenv('MYSQL_HOST'),
            port=3306,
            user=os.getenv('MYSQL_USER'),
            password=os.getenv('MYSQL_PASS'),
            db=os.getenv('MYSQL_DB')
        )
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT photo_path FROM users WHERE id=%s", (user_id,))
            result = await cursor.fetchone()
            if result and result[0]:
                return result[0]
            else:
                print("Путь к изображению не найден в базе данных")
                return None
    except Exception as e:
        print(f"Ошибка при получении пути к фото из базы данных: {e}")
        return None
    finally:
        if conn:
            conn.close()

@dp.message(Command("start"))
async def send_welcome(message: Message):
    await message.answer("Привет! Отправь мне изображение, и я его сохраню.", reply_markup=create_main_kb())

@dp.message(F.photo)
async def handle_photo(message: Message):
    user_id = message.from_user.id
    file_id = message.photo[-1].file_id  # Получаем файл самого высокого разрешения
    file = await bot.get_file(file_id)

    # Создаем уникальное имя файла
    file_extension = os.path.splitext(file.file_path)[1]
    file_name = f"{user_id}_{file_id}{file_extension}"
    file_path = os.path.join(IMAGES_DIR, file_name)

    # Загружаем изображение
    await bot.download_file(file.file_path, file_path)
    
    # Сохраняем путь к файлу в базу данных
    await save_photo_path_to_db(user_id, file_path)
    
    await message.answer("Изображение сохранено!", reply_markup=create_main_kb())

@dp.message(F.text)
async def handle_text(message: types.Message):
    user_id = message.from_user.id
    if message.text == "👤 Профиль":
        photo_path = await get_photo_path_from_db(user_id)
        if photo_path and os.path.exists(photo_path):
            await message.answer_photo(FSInputFile(photo_path), caption="Вот ваше текущее изображение.")
        else:
            await message.answer("У вас еще нет сохраненного изображения.")
    elif message.text == "🖼 Изменить изображение":
        await message.answer("Пожалуйста, отправь новое изображение.", reply_markup=types.ReplyKeyboardRemove())
    else:
        await message.answer("Я не понимаю эту команду. Пожалуйста, выбери действие.")

async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
