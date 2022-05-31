import sys
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
                    elif 'проекту' in message.text:
                        bot.send_message(message.from_user.id, texts.menu('admin', 'project'),
                                         parse_mode='markdown', reply_markup=buttons.menu('admin', 'project'))

            # Buttons handling | Cancel
            if '❌ Отменить' in message.text:
                text, markups = str(), str()
                if usertype == 'admin':
                    if 'поиск' in message.text:
                        if 'пользователя' in message.text:
                            text = texts.menu('admin', 'users')
                            markups = buttons.menu('admin', 'users')

                    elif 'добавление сервиса' in message.text:
                        text = texts.menu('admin', 'services')
                        markups = buttons.menu('admin', 'services')

                    elif 'формировку сообщения' in message.text:
                        text = texts.menu('admin', 'messaging')
                        markups = buttons.menu('admin', 'messaging')

                    elif 'изменение цены' in message.text:
                        if message.from_user.id in sessions.admins:
                            session = sessions.admins[message.from_user.id]
                            delete = session['message']['delete']
                            subscription = session['actions']['data']['subscription']

                            bot.delete_message(message.from_user.id, delete)

                            text = texts.control('admin', 'subscription', subscription=subscription)
                            markups = buttons.control('admin', 'subscription', subscription=subscription,
                                                      comeback='to-subscriptions-control')
                        else:
                            text = texts.menu('admin', 'subscriptions')
                            markups = buttons.menu('admin', 'subscriptions')

                bot.send_message(message.from_user.id, text, parse_mode='markdown', reply_markup=markups)
                sessions.clear(usertype, message.from_user.id)


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
                               "🔽 Управление данными 🔽"

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
                    and sessions.admins[message.from_user.id]['type'] == 'update-user-balance':
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
                            if message.text not in handler.format('list', 'services', 'name'):
                                step += 1
                                sessions.admins[message.from_user.id]['actions']['data']['title'] = message.text
                                text = texts.processes('admin', 'add-service', step=step, title=message.text)
                                markups = buttons.comeback_inline('to-set-service-title')
                            else:
                                text = texts.processes('admin', 'add-service', step=1,
                                                       error=texts.error('exist', 'service-title', title=message.text))
                                markups = buttons.cancel_reply('добавление сервиса')

                        case 2:
                            title = sessions.admins[message.from_user.id]['actions']['data']['title']

                            if 'http' not in message.text or 'https' not in message.text:
                                text = texts.processes('admin', 'add-service', step=step, title=title,
                                                       error=texts.error('not-links').replace('🚫 *Ошибка*\n\n⚠️ ', ''))
                                markups = buttons.comeback_inline('to-set-service-title')
                            elif message.text in handler.format('list', 'services', 'domain'):
                                service = database.get_data_by_value('services', 'domain', message.text)[0]['name']
                                text = texts.processes('admin', 'add-service', step=step, title=title,
                                                       error=texts.error('exist', 'service-title', title=service))
                                markups = buttons.comeback_inline('to-set-service-title')
                            else:
                                step += 1
                                sessions.admins[message.from_user.id]['actions']['data']['domain'] = message.text

                                text = texts.processes('admin', 'add-service', option=False, step=step,
                                                       title=title, domain=message.text)
                                markups = buttons.confirm('add-service', comeback='to-set-service-domain')

                    bot.delete_message(message.chat.id, delete)
                    delete = bot.send_message(message.chat.id, text=text, parse_mode='markdown',
                                              reply_markup=markups, disable_web_page_preview=True)
                    sessions.admins[message.from_user.id]['actions']['step'] = step
                    sessions.admins[message.from_user.id]['message']['delete'] = delete.id

            # Process | Services | Control services
            if message.text == '⚙️ Управлять' and not abuse:
                bot.send_message(message.from_user.id, texts.control('admin', 'services', step=1),
                                 parse_mode='markdown', reply_markup=buttons.control('admin', 'services', step=1))

            # Handling | Update service
            if message.from_user.id in sessions.admins \
                    and sessions.admins[message.from_user.id]['type'] == 'update-service':
                if sessions.admins[message.from_user.id]['message']['id'] != message.message_id:
                    edit = sessions.admins[message.from_user.id]['message']['id']
                    data = sessions.admins[message.from_user.id]['actions']['data']
                    service = database.get_data_by_value('services', 'name', data['service'])[0]
                    status, text, markups = False, str(), buttons.cancel_inline('update-service', service['name'])

                    bot.delete_message(message.chat.id, message.id)

                    match data['mode']:
                        case 'title':
                            if message.text == service['name']:
                                text = texts.error('same', value=message.text)
                            elif message.text in handler.format('list', 'services', 'name'):
                                text = f"🚫 *Ошибка*\n\n⚠️ {texts.error('exist', 'service-title', title=message.text)}"
                            else:
                                status = True
                                database.change_data('services', 'name', message.text, service['name'], 'name')

                                # --------------------------------------------------- #
                                # RENAME DIRECTORY WITH DOMAIN AND INITIALIZE CONFIGS #
                                # --------------------------------------------------- #

                                bot.edit_message_text(
                                    chat_id=message.chat.id, message_id=edit, parse_mode='markdown',
                                    text=texts.success('updated-data', 'service-title',
                                                       old=service['name'], new=message.text))

                        case 'domain':
                            if 'https' not in message.text or 'http' not in message.text:
                                text = texts.error('not-link')
                            elif message.text == service['domain']:
                                text = texts.error('same', value=message.text)
                            elif message.text in handler.format('list', 'services', 'domain'):
                                text = texts.error('exist', 'service-domain', domain=message.text)
                            else:
                                status = True
                                database.change_data('services', 'domain', message.text, service['name'], 'name')

                                bot.edit_message_text(
                                    chat_id=message.chat.id, message_id=edit, parse_mode='markdown',
                                    disable_web_page_preview=True, text=texts.success(
                                        'updated-data', 'service-domain',
                                        old=service['domain'], new=message.text)
                                )

                    if status:
                        service = database.get_data_by_value(
                            'services', 'name', message.text if data['mode'] == 'title' else service['name'])[0]
                        text = f"*Управление сервисом*\n\n" \
                               f"{texts.show('service', item=service)}\n\n" \
                               f"🔽 Управление данными 🔽"
                        markups = buttons.menu('admin', 'service', markups_type='inline', array=service)
                        time.sleep(1)
                        sessions.clear(usertype, message.from_user.id)

                    try:
                        bot.edit_message_text(chat_id=message.chat.id, message_id=edit,
                                              text=text, parse_mode='markdown', reply_markup=markups,
                                              disable_web_page_preview=True)
                    except ApiTelegramException:
                        pass

            # Display | Menu | Subscriptions
            if message.text == '🛍 Подписки' and not abuse:
                bot.send_message(message.from_user.id, texts.menu('admin', 'subscriptions'),
                                 parse_mode='markdown',
                                 reply_markup=buttons.menu('admin', 'subscriptions'))

            # Display | Subscriptions | Demo
            if message.text == 'Пробная' and not abuse:
                bot.send_message(
                    message.from_user.id, texts.control('admin', 'subscription', subscription='demo'),
                    parse_mode='markdown', reply_markup=buttons.control('admin', 'subscription', subscription='demo'))

            # Display | Subscriptions | Week
            if message.text == 'Недельная' and not abuse:
                bot.send_message(
                    message.from_user.id, texts.control('admin', 'subscription', subscription='week'),
                    parse_mode='markdown', reply_markup=buttons.control('admin', 'subscription', subscription='week'))

            # Display | Subscriptions | Month
            if message.text == 'Месячная' and not abuse:
                bot.send_message(
                    message.from_user.id, texts.control('admin', 'subscription', subscription='month'),
                    parse_mode='markdown', reply_markup=buttons.control('admin', 'subscription', subscription='month'))

            # Handling | Change | Subscription price
            if message.from_user.id in sessions.admins \
                    and sessions.admins[message.from_user.id]['type'] == 'update-subscription-price':
                if sessions.admins[message.from_user.id]['message']['id'] != message.message_id:
                    text, markups, status = str(), str(), False
                    data = sessions.admins[message.from_user.id]['actions']['data']
                    step = sessions.admins[message.from_user.id]['actions']['step']
                    delete = sessions.admins[message.from_user.id]['message']['delete']

                    bot.delete_message(message.chat.id, message.id)

                    match step:
                        case 1:
                            try:
                                value = int(message.text)
                                price = handler.file('read', 'settings')['prices'][data['subscription']]

                                if value == price:
                                    text = texts.error('same', value=value)
                                    markups = buttons.cancel_reply('изменение цены')

                                else:
                                    status = True
                                    settings = handler.file('read', 'settings')
                                    old = settings['prices'][data['subscription']]
                                    settings['prices'][data['subscription']] = value
                                    handler.file('write', 'settings', settings)
                                    text = texts.success('updated-data', 'subscription-price', old=old, new=value,
                                                         currency=settings['main']['currency'])

                            except ValueError:
                                option = 'цены' if data['option'] == 'price' else 'продолжительности'
                                text = texts.error('not-numeric')
                                markups = buttons.cancel_reply(f'изменение {option}')

                    bot.delete_message(message.chat.id, delete)
                    delete = bot.send_message(message.chat.id, text, parse_mode='markdown', reply_markup=markups)
                    sessions.admins[message.from_user.id]['message']['delete'] = delete.id

                    if status:
                        time.sleep(1)
                        bot.send_message(
                            message.from_user.id,
                            texts.control('admin', 'subscription', subscription=data['subscription']),
                            parse_mode='markdown',
                            reply_markup=buttons.control('admin', 'subscription', subscription=data['subscription'],
                                                         comeback='to-subscriptions-control'))


        # Display | Menu | Project
            if message.text == '⭐️ Проект' and not abuse:
                bot.send_message(message.from_user.id, texts.menu('admin', 'project'),
                                 parse_mode='markdown',
                                 reply_markup=buttons.menu('admin', 'project'))

            # Display | Project | Logs
            if message.text == '🗞 Логи' and not abuse:
                logs = database.get_data('logs')
                data = False if len(logs) == 0 else texts.show('logs', array=logs)
                data = handler.paginator(data, 'logs') if data else ("- Логов ещё нет 🤷🏻‍♂", '')
                bot.send_message(message.chat.id, f"*Логи*\n\n{data[0]}",
                                 parse_mode='markdown', reply_markup=data[1])

            # Display | Project | Messaging
            if message.text == '📨 Рассылка' and not abuse:
                bot.send_message(message.chat.id, texts.menu('admin', 'messaging'), parse_mode='markdown',
                                 reply_markup=buttons.menu('admin', 'messaging'))

            # Action | Send message | All
            if message.text == '👥 Всем':
                sessions.start(message.from_user.id, 'admin', 'send-message', message.message_id)
                sessions.admins[message.from_user.id]['actions']['data']['mode'] = 'all'
                sessions.admins[message.from_user.id]['actions']['step'] += 1

                delete = bot.send_message(
                    message.from_user.id, texts.processes('admin', 'send-message', 'all', 1),
                    parse_mode='markdown', reply_markup=buttons.cancel_reply('формировку сообщения'))

                sessions.admins[message.from_user.id]['message']['delete'] = delete.id

            # Action | Send Message | Individual
            if message.text == '👤 Одному' and not abuse:
                sessions.start(message.from_user.id, 'admin', 'send-message', message.message_id)
                sessions.admins[message.from_user.id]['actions']['data']['mode'] = 'individual'
                sessions.admins[message.from_user.id]['actions']['step'] += 1

                delete = bot.send_message(
                    message.from_user.id, texts.processes('admin', 'send-message', 'individual', 1),
                    parse_mode='markdown', reply_markup=buttons.cancel_reply('формировку сообщения'))

                sessions.admins[message.from_user.id]['message']['delete'] = delete.id

            # Handling | Send message
            if message.from_user.id in sessions.admins \
                    and sessions.admins[message.from_user.id]['type'] == 'send-message':
                if sessions.admins[message.from_user.id]['message']['id'] != message.message_id:
                    text, markups = str(), str()
                    mode = sessions.admins[message.from_user.id]['actions']['data']['mode']
                    step = sessions.admins[message.from_user.id]['actions']['step']
                    delete = sessions.admins[message.from_user.id]['message']['delete']
                    bot.delete_message(message.chat.id, message.id)

                    match step:
                        case 1:
                            if mode == 'all':
                                sessions.admins[message.from_user.id]['actions']['step'] += 1
                                sessions.admins[message.from_user.id]['actions']['data']['message'] = message.text

                                text = texts.processes('admin', 'send-message', mode, step + 1, text=message.text)
                                markups = buttons.control('admin', 'send-message', type=mode, step=step)

                            elif mode == 'individual':
                                try:
                                    identifier = int(message.text)
                                    user = database.get_data_by_value('users', 'id', identifier)

                                    if len(user) != 0:
                                        sessions.admins[message.from_user.id]['actions']['step'] += 1
                                        sessions.admins[message.from_user.id]['user']['id'] = identifier

                                        text = texts.processes('admin', 'send-message', mode,
                                                               step + 1, id=identifier)
                                        markups = buttons.comeback_inline(f'to-messaging-{mode}-{step}')

                                    else:
                                        text = texts.error('not-exist', 'user', id=identifier)
                                        markups = buttons.cancel_reply('формировку сообщения')

                                except ValueError:
                                    text = texts.error('not-numeric')
                                    markups = buttons.cancel_reply('формировку сообщения')

                            bot.delete_message(message.chat.id, delete)

                        case 2:
                            if mode == 'all':
                                pass
                            elif mode == 'individual':
                                sessions.admins[message.from_user.id]['actions']['step'] += 1
                                sessions.admins[message.from_user.id]['actions']['data']['message'] = message.text
                                identifier = sessions.admins[message.from_user.id]['user']['id']

                                text = texts.processes('admin', 'send-message', mode, step + 1,
                                                       id=identifier, text=message.text)
                                markups = buttons.control('admin', 'send-message', type=mode, step=step)

                            bot.delete_message(message.chat.id, delete)

                    try:
                        delete = bot.send_message(message.chat.id, text=text,
                                                  parse_mode='markdown', reply_markup=markups)
                    except ApiTelegramException:
                        delete = bot.send_message(message.chat.id, text='error', parse_mode='markdown')
                    sessions.admins[message.from_user.id]['message']['delete'] = delete.id

            # Display | Project | Messaging
            if message.text == '⚙️ Настройки' and not abuse:
                bot.send_message(message.chat.id, texts.menu('admin', 'settings'), parse_mode='markdown',
                                 reply_markup=buttons.menu('admin', 'settings'))

            # Action | Change settings | Currencies
            elif message.text == '🪙 Валюта' and not abuse:
                pass

            # Action | Change settings | Percentage
            elif message.text == '🧮 Процент' and not abuse:
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

                elif 'update-service' in call.data:
                    service = database.get_data_by_value('services', 'name', queries[-1])[0]
                    text = f"*Управление сервисом*\n\n" \
                           f"{texts.show('service', item=service)}\n\n" \
                           "🔽 Управление данными 🔽"
                    markups = buttons.menu('admin', 'service', markups_type='inline', array=service)

                try:
                    bot.edit_message_text(chat_id=call.from_user.id, message_id=call.message.id,
                                          text=text, parse_mode='markdown', reply_markup=markups,
                                          disable_web_page_preview=True)
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

                elif 'select-services-admin' in call.data:
                    text = texts.control('admin', 'services', step=1)
                    markups = buttons.control('admin', 'services', step=1)

                elif 'to-messaging' in call.data:
                    mode, step = queries[-2], int(queries[-1])

                    try:
                        sessions.admins[call.from_user.id]['actions']['step'] -= 1

                        match mode:
                            case 'all':
                                if step == 1:
                                    sessions.admins[call.from_user.id]['actions']['data']['message'] = None
                                    text = texts.processes('admin', 'send-message', mode, step)
                                    markups = buttons.cancel_reply('формировку сообщения')

                            case 'individual':
                                if step == 1:
                                    sessions.admins[call.from_user.id]['user']['id'] = None
                                    text = texts.processes('admin', 'send-message', mode, step)
                                    markups = buttons.cancel_reply('формировку сообщения')

                                if step == 2:
                                    identifier = sessions.admins[call.from_user.id]['user']['id']
                                    sessions.admins[call.from_user.id]['actions']['data']['message'] = None
                                    text = texts.processes('admin', 'send-message', mode, step, id=identifier)

                    except KeyError:
                        text = texts.processes('admin', 'messaging')
                        markups = buttons.menu('admin', 'messaging')

                elif 'to-subscriptions-control' in call.data:
                    text = texts.menu('admin', 'subscriptions')
                    markups = buttons.menu('admin', 'subscriptions')

                elif 'to-subscription-control' in call.data:
                    text = texts.control('admin', 'subscription', subscription=queries[-1])
                    markups = buttons.control('admin', 'subscription', subscription=queries[-1],
                                              comeback='to-subscriptions-control')



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

            case 'delete':
                text, markups, answer_success, answer_error = str(), str(), str(), str()

                match queries[1]:
                    case 'service':
                        admin = database.get_data_by_value('users', 'id', call.from_user.id)[0]
                        usertype = handler.recognition('usertype', user=call.from_user.id)
                        service = database.get_data_by_value('services', 'name', queries[2])[0]
                        answer_success, answer_error = '✅ Сервис удалён', '⛔️ Ошибка'

                        database.delete_data('services', 'name', service['name'])

                        # ---------------------------- #
                        # DELETE DIRECTORY AND CONFIGS #
                        # ---------------------------- #

                        text = texts.control('admin', 'services', step=1)
                        markups = buttons.control('admin', 'services', step=1)

                        database.add_data(
                            'logs', user=admin['id'], username=admin['name'], usertype=usertype,
                            action=texts.logs('admin', 'service', 'deleted', array=service)
                        )

                try:
                    bot.answer_callback_query(callback_query_id=call.id, show_alert=True, text=answer_success)
                    bot.edit_message_text(chat_id=call.from_user.id, message_id=call.message.id,
                                          text=text, reply_markup=markups, parse_mode='markdown')
                except ApiTelegramException:
                    bot.answer_callback_query(callback_query_id=call.id, text=answer_error)

            case 'control':
                text, markups = str(), str()

                if queries[1] == 'user':
                    mode, user = queries[-1], int(queries[-2])
                    text = texts.control(queries[1], mode, id=user)
                    markups = buttons.control(queries[1], mode, id=user)

                elif queries[1] == 'subscription':
                    mode, subscription = queries[-1], queries[2]
                    text = texts.control('admin', 'subscription', subscription=subscription, users=True)
                    markups = buttons.control('admin', 'subscription', subscription=subscription,
                                              users=True, comeback=f'to-subscription-control-{subscription}')

                bot.edit_message_text(chat_id=call.from_user.id, message_id=call.message.id,
                                      text=text, reply_markup=markups, parse_mode='markdown')

            case 'update':
                edit, text, markups = True, str(), str()
                if queries[2] == 'user':
                    mode, option, user = queries[1], queries[-1], int(queries[3])

                    match mode:
                        case 'balance':
                            sessions.start(call.from_user.id, 'admin', 'update-user-balance', call.message.id, user)
                            sessions.admins[call.from_user.id]['actions']['option'] = option

                            text = texts.processes('user', mode, option)
                            markups = buttons.cancel_inline('update-balance-user', user)

                elif queries[1] == 'service':
                    mode, option, service = 'update-service', queries[-1], queries[2]

                    sessions.start(call.from_user.id, 'admin', mode, call.message.id)
                    sessions.admins[call.from_user.id]['actions']['data']['mode'] = option
                    sessions.admins[call.from_user.id]['actions']['data']['service'] = service

                    text = texts.processes('admin', mode, option, service=service)
                    markups = buttons.cancel_inline(mode, service)

                elif queries[1] == 'subscription':
                    edit = False
                    mode, option, subscription = 'update-subscription-price', queries[-1], queries[2]

                    sessions.start(call.from_user.id, 'admin', 'update-subscription-price', call.message.id)
                    sessions.admins[call.from_user.id]['actions']['data']['subscription'] = subscription
                    sessions.admins[call.from_user.id]['actions']['data']['option'] = option
                    sessions.admins[call.from_user.id]['actions']['step'] += 1

                    text = texts.processes('admin', mode, option, subscription=subscription)
                    markups = buttons.cancel_reply(f"изменение цены")

                if edit:
                    try:
                        bot.edit_message_text(chat_id=call.from_user.id, message_id=call.message.id,
                                              text=text, parse_mode='markdown', reply_markup=markups,
                                              disable_web_page_preview=True)

                    except ApiTelegramException:
                        bot.answer_callback_query(callback_query_id=call.id, text='❎ Действие устарело')
                else:
                    bot.delete_message(call.from_user.id, call.message.id)
                    delete = bot.send_message(call.from_user.id, text, parse_mode='markdown', reply_markup=markups)
                    sessions.admins[call.from_user.id]['message']['delete'] = delete.id

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

                        elif queries[2] == 'subscription':
                            title = 'Все пользователи' if queries[4] == 'all' \
                                else 'Пользователи с активной подпиской'
                            array = handler.format('list', 'subscribers',
                                                   'active' if queries[4] == 'active' else None,
                                                   subscription=queries[3], sort='users')

                            data = handler.paginator(
                                texts.show('users', array=array),
                                f'subscription-{queries[3]}-{queries[4]}-users',
                                int(queries[-1])
                            )
                        text, markups = f"*{title}*\n\n{data[0]}", data[1]
                        answer_success, answer_error = '✅ Загружено', '❎ Ранее было загружено'

                    case 'service':
                        admin = database.get_data_by_value('users', 'id', call.from_user.id)[0]
                        usertype = handler.recognition('usertype', user=call.from_user.id)
                        service, mode = database.get_data_by_value('services', 'name', queries[2])[0], queries[-1]
                        status = False if service['status'] == 'active' else True
                        answer_success = f"{'🟢' if status else '🔴'} Сервис {'включен' if status else 'выключен'}"
                        answer_error = '⛔️ Ошибка'

                        database.change_data(
                            'services', 'status', 'active' if status else 'inactive', service['name'], 'name')

                        service = database.get_data_by_value('services', 'name', service['name'])[0]
                        text = f"*Управление сервисом*\n\n" \
                               f"{texts.show('service', item=service)}\n\n" \
                               "🔽 Управление данными 🔽"
                        markups = buttons.menu('admin', 'service', markups_type='inline', array=service)

                        sessions.clear(handler.recognition('usertype', user=call.from_user.id), call.from_user.id)
                        database.add_data(
                            'logs', user=admin['id'], username=admin['name'], usertype=usertype,
                            action=texts.logs('admin', 'service', 'status', array=service)
                        )
                try:
                    bot.answer_callback_query(callback_query_id=call.id, text=answer_success)
                    bot.edit_message_text(chat_id=call.from_user.id, message_id=call.message.id,
                                          text=text, reply_markup=markups, parse_mode='markdown',
                                          disable_web_page_preview=True)
                except ApiTelegramException:
                    bot.answer_callback_query(callback_query_id=call.id, text=answer_error)

            case 'select':
                text, markups, answer_success, answer_error = str(), str(), '✅ Загружено', '❎ Ранее было загружено'

                match queries[1]:
                    case 'admin':
                        if queries[2] == 'service':
                            service = database.get_data_by_value('services', 'name', queries[-1])[0]
                            text = f"*Управление сервисом*\n\n" \
                                   f"{texts.show('service', item=service)}\n\n" \
                                   "🔽 Управление данными 🔽"
                            markups = buttons.menu('admin', 'service', markups_type='inline', array=service)
                    case 'user':
                        pass

                try:
                    bot.answer_callback_query(callback_query_id=call.id, text=answer_success)
                    bot.edit_message_text(chat_id=call.from_user.id, message_id=call.message.id,
                                          text=text, reply_markup=markups, parse_mode='markdown',
                                          disable_web_page_preview=True)
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

                    case 'subscription':
                        match queries[-2]:
                            case 'users':
                                title = 'Все пользователи' if queries[-1] == 'all' \
                                    else 'Пользователи с активной подпиской'
                                array = handler.format('list', 'subscribers',
                                                       'active' if queries[-1] == 'active' else None,
                                                       subscription=queries[2], sort='users')

                                data = handler.paginator(
                                    texts.show('users', array=array),
                                    f'subscription-{queries[2]}-{queries[-1]}-users'
                                )

                bot.send_message(call.message.chat.id,
                                 f"*{title}*\n\n{' - Пользователей ещё нет 🤷🏻‍♂️' if len(data[0]) == 0 else data[0]}",
                                 parse_mode='markdown', reply_markup=data[1])

            case 'send':
                if queries[1] == 'message':
                    try:
                        user = sessions.admins[call.from_user.id]['user']['id']
                        mode = sessions.admins[call.from_user.id]['actions']['data']['mode']
                        message = sessions.admins[call.from_user.id]['actions']['data']['message']

                        answer = "✅ Принято на отправку"
                        text = f"✅ Сообщение было принято на отправку и в ближайше время будет доставлено " \
                               f"{'получателям' if mode == 'all' else 'получателю'}."

                        processes = handler.file('read', 'processes')
                        match mode:
                            case 'all':
                                processes['messages'][mode][call.from_user.id] = {'text': message}
                            case 'individual':
                                if user not in processes['messages'][mode].keys():
                                    processes['messages'][mode][user] = {'text': message}
                                else:
                                    answer = "❎ Уже доставляется сообщение"
                                    text = "❎ Сообщение не может быть доставлено, так как в данный момент уже " \
                                           "производится отправка сообщения данному пользователю. Попробуй позже."
                                    bot.delete_message(call.message.chat.id, call.message.message_id)

                        handler.file('write', 'processes', processes)
                        bot.answer_callback_query(callback_query_id=call.id, text=answer)
                        sessions.clear(handler.recognition('usertype', user=call.from_user.id), call.from_user.id)

                        bot.edit_message_text(chat_id=call.from_user.id, message_id=call.message.id,
                                              text=text, parse_mode='markdown')

                        time.sleep(1)
                        bot.send_message(call.from_user.id, texts.menu('admin', 'messaging'),
                                         parse_mode='markdown',
                                         reply_markup=buttons.menu('admin', 'messaging'))

                    except KeyError:
                        bot.answer_callback_query(callback_query_id=call.id, text='❎ Действие устарело')
                        bot.delete_message(call.message.chat.id, call.message.message_id)

    # -------------
    try:
        bot.infinity_polling()
    except Exception as error:
        path, file = 'sources/logs/', f"log-{datetime.now().strftime('%d.%m.%Y-%H:%M:%S')}.txt"

        logging.basicConfig(filename=f"{path}{file}", level=logging.ERROR)
        logging.error(error, exc_info=True)

        bot.send_message(configs['chats']['notifications'], texts.notifications('bot-crashed', path=path, file=file),
                         parse_mode='markdown')

        sys.exit()
