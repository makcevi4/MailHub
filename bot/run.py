import bot as bot_processor
from core import Configs, Sessions, Processes, Database, Merchant, Mailing, Handler, Texts, Buttons
from telebot import TeleBot
from threading import Thread

if __name__ == '__main__':
    configs_processor = Configs()
    configs = configs_processor.initialization()
    database = Database()

    handler = Handler()
    mailing = Mailing()
    merchant = Merchant()

    texts = Texts()
    buttons = Buttons()

    sessions = Sessions()
    processes = Processes()

    bot = TeleBot(configs['bot']['token'])

    thread_bot = Thread(target=bot_processor.run, args=())
    thread_processes = Thread(target=processes.run, args=())

    thread_bot.start()
    thread_processes.start()


