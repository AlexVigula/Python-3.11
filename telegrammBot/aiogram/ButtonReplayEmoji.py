from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import asyncio

########################################################
#                                                       #
#    Функционал клавиатуры                              #
#         dev Alex Vigula      tg @gunsxp               #
#                                                       #
#########################################################

API_TOKEN = '-----'  # Замените на ваш токен

# Инициализация бота и диспетчера
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    kb = [
        [
            types.KeyboardButton(text='👤 Профиль'),
            types.KeyboardButton(text="🚕 Меню"),
            types.KeyboardButton(text='🚖 Создать заказ'),
            types.KeyboardButton(text='💰 Баланс'),
            types.KeyboardButton(text="💳 Пополнить"),
            types.KeyboardButton(text='❓ Помощь'),
        ],
    ]
    keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)  # Добавлено resize_keyboard для удобства

    await message.reply("Привет!\nЯ ТаксиБот от компании VIGULA !\nДавай я помогу тебе?", reply_markup=keyboard)

if __name__ == '__main__':
    # Запускаем бота 
    asyncio.run(dp.start_polling(bot))
