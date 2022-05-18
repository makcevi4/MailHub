import logging

from datetime import datetime


def run(bot, configs, sessions, database, merchant, handler, texts, buttons):
    @bot.message_handler(commands=['start', 'admin'])
    def start(message):
        commands = message.text.replace('/', '').split()
        handler.initialization('user', commands=commands,
                               user=message.from_user.id,
                               first=message.from_user.first_name,
                               last=message.from_user.last_name)

        if not handler.recognition('ban', 'user', user=message.from_user.id):
            match commands[0]:
                case 'start':
                    bot.send_message(message.chat.id, texts.menu('user', 'main', user=message.from_user.id),
                                     parse_mode='markdown', reply_markup='')

                case 'admin':
                    usertype = handler.recognition('usertype', user=message.from_user.id)

                    if usertype == 'admin':
                        bot.send_message(message.chat.id, texts.menu('admin', 'main'), parse_mode='markdown',
                                         reply_markup='')
                    else:
                        username = database.get_data_by_value('users', 'id', message.from_user.id)[0][1]
                        database.change_data('users', 'ban', 1, message.from_user.id)
                        database.change_data('users', 'cause', 'abuse', message.from_user.id)
                        database.add_data('logs', userid=message.from_user.id, username=username, usertype=usertype,
                                          action="Пользователь попытался запустить админ-панель, но не смог, так как "
                                                 "у него нет прав. Пользователь был автоматически заблокирован.")

                        bot.send_message(message.chat.id, texts.error('banned', user=message.from_user.id),
                                         parse_mode='markdown', reply_markup=buttons.support())

        else:
            bot.send_message(message.chat.id, texts.error('banned', user=message.from_user.id), parse_mode='markdown',
                             reply_markup=buttons.support())

    @bot.message_handler(content_types=['text'])
    def text_handler(message):
        # dates = handler.calculate('subscription', 'dates', type='demo')
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
