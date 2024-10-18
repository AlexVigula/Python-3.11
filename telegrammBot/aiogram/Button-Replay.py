from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import asyncio

API_TOKEN = '----'  # Замените на ваш токен

# Инициализация бота и диспетчера
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    kb = [
        [
            types.KeyboardButton(text="Я кнопка 1"),
            types.KeyboardButton(text="Я кнопка 2")
        ],
    ]
    keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)  # Добавлено resize_keyboard для удобства

    await message.reply("Привет!\nЯ Эхобот от Vigula Alex!\nОтправь мне любое сообщение, а я тебе обязательно отвечу.", reply_markup=keyboard)

if __name__ == '__main__':
    # Запускаем бота 
    asyncio.run(dp.start_polling(bot))
