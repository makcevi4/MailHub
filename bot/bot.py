import logging

from datetime import datetime


def run(bot, configs, sessions, database, merchant, handler, texts, buttons):
    @bot.message_handler(commands=['start', 'admin'])
    def start(message):
        print(message.text)

    @bot.message_handler(content_types=['text'])
    def text_handler(message):
        print(message.text)

    @bot.callback_query_handler(func=lambda call: True)
    def queries_handler(call):
        queries = call.data.replace('-', ' ').split()
        print(queries)

    try:
        bot.infinity_polling()
    except Exception as error:
        path, file = 'data/logs/', f"log-{datetime.now().strftime('%d.%m.%Y-%H:%M:%S')}.txt"

        logging.basicConfig(filename=f"{path}{file}", level=logging.ERROR)
        logging.error(error, exc_info=True)

        bot.send_message(configs['chats']['notifications'], texts.notifications('bot-crashed', path=path, file=file),
                         parse_mode='markdown')
