import time
import json
import logging

from datetime import datetime
from telebot.apihelper import ApiTelegramException


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
                                     parse_mode='markdown', reply_markup=buttons.menu('user', 'main'))

                case 'admin':
                    usertype = handler.recognition('usertype', user=message.from_user.id)

                    if usertype == 'admin':
                        bot.send_message(message.chat.id, texts.menu('admin', 'main'), parse_mode='markdown',
                                         reply_markup=buttons.menu('admin', 'main'))
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
        # dates = handler.calculate('subscription', 'dates', type='demo') # now, expiration

        handler.initialization('user', user=message.from_user.id,
                               first=message.from_user.first_name,
                               last=message.from_user.last_name)

        if handler.recognition('ban', 'user', user=message.from_user.id):
            bot.send_message(message.chat.id, texts.error('banned', user=message.from_user.id), parse_mode='markdown',
                             reply_markup=buttons.support())
        else:
            usertype = handler.recognition('usertype', user=message.from_user.id)

            # Buttons handling | Comeback
            if '↩️ Назад к' in message.text:
                sessions.clear(usertype, message.from_user.id)

                if usertype == 'admin':
                    if 'админ панели' in message.text:
                        bot.send_message(message.from_user.id, texts.menu('admin', 'main'),
                                         parse_mode='markdown', reply_markup=buttons.menu('admin', 'main'))

                    elif 'пользователям' in message.text:
                        bot.send_message(message.from_user.id, texts.menu('admin', 'users'),
                                         parse_mode='markdown', reply_markup=buttons.menu('admin', 'users'))


            # Buttons handling | Cancel
            if '❌ Отменить' in message.text:
                sessions.clear(usertype, message.from_user.id)

                if usertype == 'admin':
                    if 'поиск' in message.text:
                        if 'пользователя' in message.text:
                            bot.send_message(message.from_user.id, texts.menu('admin', 'users'),
                                             parse_mode='markdown', reply_markup=buttons.menu('admin', 'users'))

            #  - ADMIN
            abuse = handler.recognition('abuse', action=message.text, user=message.from_user.id, usertype=usertype,
                                        bot=bot, texts=texts, buttons=buttons)

            # Displays | Menu | Users
            if message.text == '👨🏻‍💻 Пользователи' and not abuse:
                bot.send_message(message.from_user.id, texts.menu('admin', 'users'),
                                 parse_mode='markdown', reply_markup=buttons.menu('admin', 'users'))

            # Displays | Users | All
            if message.text == '👁 Посмотреть всех' and not abuse:
                users = database.get_data('users')
                data = False if len(users) == 0 else texts.show('users', array=users)
                data = handler.paginator(data, 'users') if data else ("- Пользователей ещё нет 🤷🏻‍♂", '')
                bot.send_message(message.chat.id, f'*Пользователи*\n\n{data[0]}',
                                 parse_mode='markdown', reply_markup=data[1])

            # Process | Users | Find user
            if message.text == '🕹 Управлять' and not abuse:
                if len(database.get_data('users')) > 0:
                    sessions.start(message.from_user.id, 'admin', 'find-user', message.message_id)

                    text = texts.processes('admin', 'find-user')
                    markups = buttons.cancel_reply('поиск пользователя')

                else:
                    text = texts.error('empty', 'users')
                    markups = ''

                delete = bot.send_message(message.chat.id, text, parse_mode='markdown', reply_markup=markups)
                sessions.admins[message.from_user.id]['message']['delete'] = delete.id

            # Handling | Find user
            if message.from_user.id in sessions.admins \
                    and sessions.admins[message.from_user.id]['type'] == 'find-user':
                if sessions.admins[message.from_user.id]['message']['id'] != message.message_id:
                    delete = sessions.admins[message.from_user.id]['message']['delete']
                    userdata = database.get_data_by_value('users', 'id', message.text)

                    bot.delete_message(message.chat.id, delete)
                    bot.delete_message(message.chat.id, message.id)

                    if len(userdata):
                        bot.send_message(
                            message.chat.id, texts.success('found-data', 'user', id=message.text),
                            parse_mode='markdown', reply_markup=buttons.comeback_reply('пользователям'))
                        time.sleep(0.5)

                        text = "*Управление пользователем*\n\n" \
                               f"{texts.show('user', 'full', item=userdata[0])}\n\n" \
                               f"🔽 Управление данными 🔽"

                        bot.send_message(message.chat.id, text, parse_mode='markdown',
                                         reply_markup=buttons.menu('admin', 'user', id=userdata[0][0]))

                        del sessions.admins[message.from_user.id]
                    else:
                        delete = bot.send_message(message.from_user.id,
                                                  texts.error('not-found', 'user', id=message.text),
                                                  parse_mode='markdown',
                                                  reply_markup=buttons.cancel_reply('поиск пользователя'))
                        sessions.admins[message.from_user.id]['message']['delete'] = delete.id

            # Handling | Update balance
            if message.from_user.id in sessions.admins \
                    and sessions.admins[message.from_user.id]['type'] == 'update-balance':
                if sessions.admins[message.from_user.id]['message']['id'] != message.message_id:
                    option = sessions.admins[message.from_user.id]['actions']['option']
                    user = sessions.admins[message.from_user.id]['user']['id']

                    bot.delete_message(message.chat.id, message.id)

                    try:
                        summary = int(message.text)

                        if summary > 0:
                            balance = database.get_data_by_value('users', 'id', user)[0][3]

                            match option:
                                case 'add':
                                    balance += summary

                                case 'change':
                                    balance = summary

                            database.change_data('users', 'balance', balance, user)
                            bot.edit_message_text(chat_id=message.from_user.id,
                                                  message_id=sessions.admins[message.from_user.id]['message']['id'],
                                                  text=texts.success('updated-data', f'{option}-balance'),
                                                  parse_mode='markdown')

                            userdata = database.get_data_by_value('users', 'id', user)[0]
                            text = "*Управление пользователем*\n\n" \
                                   f"{texts.show('user', 'full', item=userdata)}\n\n" \
                                   f"🔽 Управление данными 🔽"

                            markups = buttons.menu('admin', 'user', id=userdata[0])
                            time.sleep(1)

                        else:
                            text = texts.error('less')
                            markups = buttons.cancel_inline('update-balance-user', user)

                    except ValueError:
                        text = texts.error('not-numeric')
                        markups = buttons.cancel_inline('update-balance-user', user)

                    try:
                        bot.edit_message_text(chat_id=message.from_user.id,
                                              message_id=sessions.admins[message.from_user.id]['message']['id'],
                                              text=text, parse_mode='markdown', reply_markup=markups)
                    except ApiTelegramException:
                        pass



            # - USER

    @bot.callback_query_handler(func=lambda call: True)
    def queries_handler(call):
        queries = call.data.replace('-', ' ').split()
        print(queries)

        match queries[0]:
            case 'cancel':
                text, markups = str(), str()
                usertype = handler.recognition('usertype', user=call.from_user.id)
                sessions.clear(usertype, call.from_user.id)

                if 'update-balance' in call.data:
                    text = texts.control('user', 'balance', id=queries[-1])
                    markups = buttons.control('user', 'balance', id=queries[-1])

                try:
                    bot.edit_message_text(chat_id=call.from_user.id, message_id=call.message.id,
                                          text=text, parse_mode='markdown', reply_markup=markups)
                except ApiTelegramException:
                    bot.answer_callback_query(callback_query_id=call.id, text='❎ Действие устарело')

            case 'comeback':
                text, markups = str(), str()
                if 'to-user-menu' in call.data:
                    userdata = database.get_data_by_value('users', 'id', queries[-1])
                    text = "*Управление пользователем*\n\n" \
                           f"{texts.show('user', 'full', item=userdata[0])}\n\n" \
                           "🔽 Управление данными 🔽"
                    markups = buttons.menu('admin', 'user', id=userdata[0][0])

                try:
                    bot.edit_message_text(chat_id=call.from_user.id, message_id=call.message.id,
                                          text=text, parse_mode='markdown', reply_markup=markups)
                except ApiTelegramException:
                    try:
                        bot.delete_message(call.message.chat.id, call.message.message_id)
                        delete = bot.send_message(call.from_user.id, text, reply_markup=markups, parse_mode='markdown')

                        if call.from_user.id in sessions.admins:
                            sessions.admins[call.from_user.id]['message']['delete'] = delete.id

                    except ApiTelegramException:
                        bot.answer_callback_query(callback_query_id=call.id, text='❎ Действие устарело')

            case 'close':
                bot.answer_callback_query(callback_query_id=call.id, text='Закрыто ✅')
                bot.delete_message(call.from_user.id, call.message.id)

            case 'control':
                text, markups = str(), str()

                if queries[1] == 'user':
                    mode, user = queries[-1], int(queries[-2])
                    text = texts.control(queries[1], mode, id=user)
                    markups = buttons.control(queries[1], mode, id=user)

                bot.edit_message_text(chat_id=call.from_user.id, message_id=call.message.id,
                                      text=text, reply_markup=markups, parse_mode='markdown')

            case 'update':
                text, markups = str(), str()
                match queries[2]:
                    case 'user':
                        mode, option, user = queries[1], queries[-1], int(queries[3])

                        match mode:
                            case 'balance':
                                sessions.start(call.from_user.id, 'admin', 'update-balance', call.message.id, user)
                                sessions.admins[call.from_user.id]['actions']['option'] = option

                                text = texts.processes('user', mode, option)
                                markups = buttons.cancel_inline('update-balance-user', user)

                try:
                    bot.edit_message_text(chat_id=call.from_user.id, message_id=call.message.id,
                                          text=text, parse_mode='markdown', reply_markup=markups)

                except ApiTelegramException:
                    bot.answer_callback_query(callback_query_id=call.id, text='❎ Действие устарело')

            case 'set':
                text, markups, answer_success, answer_error = str(), str(), str(), str()

                match queries[1]:
                    case 'ban':
                        status = json.loads(queries[2].lower())
                        userdata = database.get_data_by_value('users', 'id', int(queries[-1]))[0]
                        admin = database.get_data_by_value('users', 'id', call.from_user.id)[0]
                        usertype = handler.recognition('usertype', user=call.from_user.id)
                        answer_success = f"{'🔴' if status else '🟢'} Пользователь {'забанен' if status else 'разбанен'}"
                        answer_error = '⛔️ Ошибка'

                        database.change_data('users', 'ban', 1 if status else 0, userdata[0])

                        text = texts.control(queries[3], queries[1], id=userdata[0])
                        markups = buttons.control(queries[3], queries[1], id=userdata[0])

                        database.add_data(
                            'logs', userid=admin[0], username=admin[1], usertype=usertype,
                            action=texts.logs('admin', 'user', 'ban', status=status, name=userdata[1], id=userdata[0])
                        )
                    case 'page':
                        data, title = list(), str()

                        if queries[2] == 'logs':
                            title = 'Логи'
                            logs = database.get_data('logs')
                            data = False if len(logs) == 0 else texts.show('logs', array=logs)
                            data = handler.paginator(data, 'logs', int(queries[-1])) \
                                if data else ("- Логов ещё нет 🤷🏻‍♂", '')

                        elif queries[2] == 'users':
                            title = "Пользователи"
                            users = database.get_data('users')
                            data = False if len(users) == 0 else texts.show('users', array=users)
                            data = handler.paginator(data, 'users', int(queries[-1])) \
                                if data else ("- Пользователей ещё нет 🤷🏻‍♂", '')

                        text, markups = f"*{title}*\n\n{data[0]}", data[1]
                        answer_success, answer_error = '✅ Загружено', '❎ Ранее было загружено'

                try:
                    bot.edit_message_text(chat_id=call.from_user.id, message_id=call.message.id,
                                          text=text, reply_markup=markups, parse_mode='markdown')
                    bot.answer_callback_query(callback_query_id=call.id, text=answer_success)
                except ApiTelegramException:
                    bot.answer_callback_query(callback_query_id=call.id, text=answer_error)

            case 'get':
                title, data = None, list()

                match queries[1]:
                    case 'user':
                        print('do user get data')

                # bot.send_message(call.message.chat.id, f'*{title}*\n\n{data[0]}',
                #                  parse_mode='markdown', reply_markup=data[1])

    # -------------
    try:
        bot.infinity_polling()
    except Exception as error:
        path, file = 'data/logs/', f"log-{datetime.now().strftime('%d.%m.%Y-%H:%M:%S')}.txt"

        logging.basicConfig(filename=f"{path}{file}", level=logging.ERROR)
        logging.error(error, exc_info=True)

        bot.send_message(configs['chats']['notifications'], texts.notifications('bot-crashed', path=path, file=file),
                         parse_mode='markdown')
