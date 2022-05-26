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
                        username = database.get_data_by_value('users', 'id', message.from_user.id)[0]['name']
                        database.change_data('users', 'ban', 1, message.from_user.id)
                        database.change_data('users', 'cause', 'abuse', message.from_user.id)
                        database.add_data('logs', user=message.from_user.id, username=username, usertype=usertype,
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
                    elif 'добавление сервиса' in message.text:
                        bot.send_message(message.from_user.id, texts.menu('admin', 'services'),
                                         parse_mode='markdown', reply_markup=buttons.menu('admin', 'services'))


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
                                         reply_markup=buttons.menu('admin', 'user', id=userdata[0]['id']))

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
                            balance = database.get_data_by_value('users', 'id', user)[0]['balance']

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

                            markups = buttons.menu('admin', 'user', id=userdata['id'])
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

            # Displays | Menu | Users
            if message.text == '🛠 Сервисы' and not abuse:
                bot.send_message(message.from_user.id, texts.menu('admin', 'services'),
                                 parse_mode='markdown', reply_markup=buttons.menu('admin', 'services'))

            # Process | Services | Add service
            if message.text == '➕ Добавить' and not abuse:
                sessions.start(message.from_user.id, 'admin', 'add-service', message.message_id)
                sessions.admins[message.from_user.id]['actions']['step'] += 1

                delete = bot.send_message(message.from_user.id,
                                          texts.processes('admin', 'add-service', step=1),
                                          parse_mode='markdown',
                                          reply_markup=buttons.cancel_reply('добавление сервиса'))
                sessions.admins[message.from_user.id]['message']['delete'] = delete.id

            # Handling | Add service
            if message.from_user.id in sessions.admins \
                    and sessions.admins[message.from_user.id]['type'] == 'add-service':
                if sessions.admins[message.from_user.id]['message']['id'] != message.message_id:
                    text, markups = str(), str()
                    step = sessions.admins[message.from_user.id]['actions']['step']
                    delete = sessions.admins[message.from_user.id]['message']['delete']

                    bot.delete_message(message.chat.id, message.id)

                    match step:
                        case 1:
                            step += 1
                            sessions.admins[message.from_user.id]['actions']['data']['title'] = message.text
                            text = texts.processes('admin', 'add-service', step=step, title=message.text)
                            markups = buttons.comeback_inline('to-set-service-title')
                        case 2:
                            if 'http' in message.text or 'https' in message.text:
                                step += 1
                                title = sessions.admins[message.from_user.id]['actions']['data']['title']
                                sessions.admins[message.from_user.id]['actions']['data']['domain'] = message.text

                                text = texts.processes('admin', 'add-service', option=False, step=step,
                                                       title=title, domain=message.text)
                                markups = buttons.confirm('add-service', comeback='to-set-service-domain')
                            else:
                                text = texts.processes('admin', 'add-service', step=step, title=message.text,
                                                       error='Неправильный формат домена. Попробуй ввести домен '
                                                             'ещё раз в формате https://yourdomain.com.')
                                markups = buttons.comeback_inline('to-set-service-title')

                    bot.delete_message(message.chat.id, delete)
                    delete = bot.send_message(message.chat.id, text=text, parse_mode='markdown',
                                              reply_markup=markups, disable_web_page_preview=True)
                    sessions.admins[message.from_user.id]['actions']['step'] = step
                    sessions.admins[message.from_user.id]['message']['delete'] = delete.id

            # Process | Services | Control services
            if message.text == '⚙️ Управлять' and not abuse:
                bot.send_message(message.from_user.id,
                                 texts.control('admin', 'services', step=1),
                                 parse_mode='markdown',
                                 reply_markup='')

                buttons.control('admin', 'services', step=1)

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
                    markups = buttons.menu('admin', 'user', id=userdata[0]['id'])

                elif 'to-set-service' in call.data:
                    if call.from_user.id in sessions.admins:
                        step = sessions.admins[call.from_user.id]['actions']['step']
                        step -= 1
                        match queries[-1]:
                            case 'title':
                                text = texts.processes('admin', 'add-service', step=step)
                                markups = buttons.cancel_reply('добавление сервиса')
                            case 'domain':
                                title = sessions.admins[call.from_user.id]['actions']['data']['title']
                                text = texts.processes('admin', 'add-service', step=step, title=title)
                                markups = buttons.comeback_inline('to-set-service-title')

                        sessions.admins[call.from_user.id]['actions']['step'] = step

                    else:
                        bot.answer_callback_query(callback_query_id=call.id, text='❎ Действие устарело')

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

            case 'confirm':
                text, markups = str(), str()

                if 'add-service' in call.data:
                    if call.from_user.id in sessions.admins:
                        data = sessions.admins[call.from_user.id]['actions']['data']
                        bot.answer_callback_query(callback_query_id=call.id, text='Успешно подтверждено ✅')

                        # ----------------------------------------------------- #
                        # CREATING DIRECTORY WITH DOMAIN AND INITIALIZE CONFIGS #
                        # ----------------------------------------------------- #

                        database.add_data('services', name=data['title'], domain=data['domain'])
                        text = texts.menu('admin', 'services')
                        markups = buttons.menu('admin', 'services')
                        sessions.clear(handler.recognition('usertype', user=call.from_user.id), call.from_user.id)

                    else:
                        bot.answer_callback_query(callback_query_id=call.id, text='❎ Действие устарело')
                        bot.delete_message(call.from_user.id, call.message.id)

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

                        database.change_data('users', 'ban', 1 if status else 0, userdata['id'])

                        text = texts.control(queries[3], queries[1], id=userdata['id'])
                        markups = buttons.control(queries[3], queries[1], id=userdata['id'])

                        database.add_data(
                            'logs', user=admin[0], username=admin[1], usertype=usertype,
                            action=texts.logs('admin', 'user', 'ban', status=status,
                                              name=userdata['name'], id=userdata['id'])
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

                        elif queries[2] == 'user':
                            title = call.message.text.split('\n')[0]
                            user, mode, page = int(queries[-2]), queries[3], int(queries[-1])
                            array = database.get_data_by_value(mode, 'user', user)
                            data = handler.paginator(
                                texts.show(mode, array=array), f'user-{mode}', id=user, page=page)

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
                        title = f"{handler.recognition('user', 'title', items=call)} пользователя"
                        user, mode = int(queries[2]), queries[-1]

                        if mode == 'referrals':
                            array = database.get_data_by_value('users', 'inviter', user)
                        else:
                            array = database.get_data_by_value(mode, 'user', user)
                        data = handler.paginator(texts.show(mode, array=array), f'user-{mode}', id=user)

                bot.send_message(call.message.chat.id, f'*{title}*\n\n{data[0]}',
                                 parse_mode='markdown', reply_markup=data[1])

    # -------------
    try:
        bot.infinity_polling()
    except Exception as error:
        path, file = 'data/logs/', f"log-{datetime.now().strftime('%d.%m.%Y-%H:%M:%S')}.txt"

        logging.basicConfig(filename=f"{path}{file}", level=logging.ERROR)
        logging.error(error, exc_info=True)

        bot.send_message(configs['chats']['notifications'], texts.notifications('bot-crashed', path=path, file=file),
                         parse_mode='markdown')
