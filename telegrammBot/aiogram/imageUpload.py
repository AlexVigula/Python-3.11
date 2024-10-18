import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram import F
from aiogram.types import Message
###########
Функционал загрузки изображения в телеграмм бот с искользованием библиотеки aiogramm
###########
API_TOKEN = 'Ваш токен'

# Инициализация бота и диспетчера
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Папка для хранения изображений
if not os.path.exists('imagesss'):
    os.makedirs('imagesss')

@dp.message(Command("start"))
async def send_welcome(message: Message):
    await message.answer("Привет! Отправь мне изображение, и я его сохраню.")

@dp.message(F.photo)
async def handle_photo(message: Message):
    # Получаем файл изображения
    file_id = message.photo[-1].file_id  # Получаем файл самого высокого разрешения
    file = await bot.get_file(file_id)

    # Загружаем изображение
    await bot.download_file(file.file_path, f'imagesss/{file_id}.jpg')  # Сохраняем изображение с уникальным именем 
    await message.answer("Изображение сохранено!")

async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
