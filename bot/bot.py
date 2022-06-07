import sys
import ast
import time
import json
import logging
import requests

from datetime import datetime
from telebot.apihelper import ApiTelegramException


def run(bot, configs, sessions, database, merchant, handler, texts, buttons):
    @bot.message_handler(commands=['start', 'admin', 'promoter'])
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
                case 'promoter':
                    usertype = handler.recognition('usertype', user=message.from_user.id)
                    privileges = ast.literal_eval(
                        database.get_data_by_value('users', 'id', message.from_user.id)[0]['privileges']
                    )

                    if commands[0] in privileges or usertype == 'admin':
                        bot.send_message(
                            message.chat.id,
                            texts.menu('promoter', 'main', user=message.from_user.id),
                            parse_mode='markdown',
                            reply_markup=buttons.menu('promoter', 'main', user=message.from_user.id))

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
                text, markups = str(), str()

                if usertype == 'admin':
                    if 'админ панели' in message.text:
                        text = texts.menu('admin', 'main')
                        markups = buttons.menu('admin', 'main')

                    elif 'пользователям' in message.text:
                        text = texts.menu('admin', 'users')
                        markups = buttons.menu('admin', 'users')

                    elif 'финансам' in message.text:
                        text = texts.menu('admin', 'finances')
                        markups = buttons.menu('admin', 'finances')

                    elif 'меню платежей' in message.text:
                        text = texts.menu('admin', 'payments')
                        markups = buttons.menu('admin', 'payments')

                    elif 'проекту' in message.text:
                        text = texts.menu('admin', 'project')
                        markups = buttons.menu('admin', 'project')

                if 'главной панели' in message.text:
                    text = texts.menu('user', 'main', user=message.from_user.id)
                    markups = buttons.menu('user', 'main')

                try:
                    bot.send_message(message.chat.id, text, parse_mode='markdown', reply_markup=markups)
                except ApiTelegramException:
                    pass

                sessions.clear(message.from_user.id)

            # Buttons handling | Cancel
            if '❌ Отменить' in message.text:
                text, markups = str(), str()
                promoter = handler.recognition('user', 'privilege', user=message.from_user.id, privilege='promoter')
                print(promoter)

                if usertype == 'admin':
                    if 'поиск' in message.text:
                        if 'пользователя' in message.text:
                            text = texts.menu('admin', 'users')
                            markups = buttons.menu('admin', 'users')

                        elif 'платежа' in message.text:
                            text = texts.menu('admin', 'payments')
                            markups = buttons.menu('admin', 'payments')

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

                    elif 'изменение процента' in message.text:
                        text = texts.menu('admin', 'settings')
                        markups = buttons.menu('admin', 'settings')

                    elif 'изменение валюты' in message.text or 'изменение криптовалюты' in message.text:
                        if message.from_user.id in sessions.admins:
                            delete = sessions.admins[message.from_user.id]['message']['delete']
                            bot.delete_message(message.chat.id, delete)

                        text = texts.control('admin', 'currencies'),
                        markups = buttons.control('admin', 'currencies')

                if usertype == 'admin' or promoter:
                    if 'запрос вывода' in message.text:
                        bot.send_message(
                            message.chat.id, texts.menu('promoter', 'main', user=message.from_user.id),
                            parse_mode='markdown',
                            reply_markup=buttons.menu('promoter', 'main', user=message.from_user.id))


                try:
                    bot.send_message(message.from_user.id, text, parse_mode='markdown', reply_markup=markups)
                except ApiTelegramException:
                    pass

                sessions.clear(message.from_user.id)

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

            # Handling | Update balance
            if message.from_user.id in sessions.admins \
                    and sessions.admins[message.from_user.id]['type'] == 'update-user-percentage':
                if sessions.admins[message.from_user.id]['message']['id'] != message.message_id:
                    user = sessions.admins[message.from_user.id]['user']['id']

                    bot.delete_message(message.chat.id, message.id)

                    try:
                        percentage = int(message.text)

                        if percentage < 1:
                            text = texts.error('less')
                            markups = buttons.cancel_inline('update-percentage-user', user)

                        elif percentage > 100:
                            text = texts.error('more')
                            markups = buttons.cancel_inline('update-percentage-user', user)

                        else:
                            database.change_data('users', 'percentage', percentage, user)
                            bot.edit_message_text(chat_id=message.from_user.id,
                                                  message_id=sessions.admins[message.from_user.id]['message']['id'],
                                                  text=texts.success('updated-data', f'change-percentage'),
                                                  parse_mode='markdown')

                            userdata = database.get_data_by_value('users', 'id', user)[0]
                            text = "*Управление пользователем*\n\n" \
                                   f"{texts.show('user', 'full', item=userdata)}\n\n" \
                                   f"🔽 Управление данными 🔽"

                            markups = buttons.menu('admin', 'user', id=userdata['id'])
                            time.sleep(1)

                    except ValueError:
                        text = texts.error('not-numeric')
                        markups = buttons.cancel_inline('update-percentage-user', user)

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
                            elif message.text in handler.format('list', 'services', 'domains'):
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
                    status, text, menu = False, str(), 'service'
                    markups = buttons.cancel_inline(f"update-service-{data['mode']}", service['name'])
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
                            domains = ast.literal_eval(service['domains'])
                            all_domains = handler.format('list', 'services', 'domains')

                            if 'https' not in message.text or 'http' not in message.text:
                                text = texts.error('not-link')

                            elif message.text in domains or message.text in all_domains:
                                text = texts.error('exist', 'service-domain', domain=message.text)

                            else:
                                status, menu = True, 'domains'
                                domains.append(message.text)
                                database.change_data('services', 'domains', domains, service['name'], 'name')

                                bot.edit_message_text(
                                    chat_id=message.chat.id, message_id=edit, parse_mode='markdown',
                                    disable_web_page_preview=True, text=texts.success(
                                        'updated-data', 'service-domain', domain=message.text, service=service['name'])
                                )

                    if status:
                        service = database.get_data_by_value(
                            'services', 'name', message.text if data['mode'] == 'title' else service['name'])[0]

                        match menu:
                            case 'service':
                                text = f"*Управление сервисом*\n\n" \
                                       f"{texts.show('service', item=service)}\n\n" \
                                       f"🔽 Управление данными 🔽"
                                markups = buttons.menu('admin', 'service', markups_type='inline', array=service)

                            case 'domains':
                                text = texts.control('admin', 'domains', service=service['name'])
                                markups = buttons.control('admin', 'domains', service=service['name'])

                        time.sleep(1)
                        sessions.clear(message.from_user.id)

                    try:
                        bot.edit_message_text(chat_id=message.chat.id, message_id=edit,
                                              text=text, parse_mode='markdown', reply_markup=markups,
                                              disable_web_page_preview=True)
                    except ApiTelegramException:
                        pass

            # Display | Menu | Subscriptions
            if message.text == '🛍 Подписки' and not abuse:
                bot.send_message(message.from_user.id, texts.menu('admin', 'subscriptions'),
                                 parse_mode='markdown', reply_markup=buttons.menu('admin', 'subscriptions'))

            # Display | Menu | Finances
            if message.text == '💰 Финансы' and not abuse:
                bot.send_message(message.from_user.id, texts.menu('admin', 'finances'),
                                 parse_mode='markdown', reply_markup=buttons.menu('admin', 'finances'))

            # Display | Menu | Payments
            if message.text == '💳 Платежи' and not abuse:
                bot.send_message(message.from_user.id, texts.menu('admin', 'payments'),
                                 parse_mode='markdown', reply_markup=buttons.menu('admin', 'payments'))

            # Action | Display | Accruals
            if message.text == '🪙 Начисления' and not abuse:
                array = handler.format('dict', 'payments', 'accruals')['data']
                data = False if len(array) == 0 else texts.show('payments', array=array)
                data = handler.paginator(data, 'accruals') if data else ("- Начислений ещё нет 🤷🏻‍♂", '')
                bot.send_message(message.chat.id, f'*Начисления*\n\n{data[0]}',
                                 parse_mode='markdown', reply_markup=data[1])

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
                    text, markups = str(), str()
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
                                    settings = handler.file('read', 'settings')
                                    old = settings['prices'][data['subscription']]
                                    settings['prices'][data['subscription']] = value
                                    handler.file('write', 'settings', settings)
                                    sessions.clear(message.from_user.id)

                                    bot.send_message(
                                        message.from_user.id,
                                        texts.success('updated-data', 'subscription-price',
                                                      old=old, new=value, currency=settings['main']['currency']),
                                        parse_mode='markdown')

                                    text = texts.control('admin', 'subscription', subscription=data['subscription'])
                                    markups = buttons.control('admin', 'subscription', subscription=data['subscription'],
                                                              comeback='to-subscriptions-control')
                                    time.sleep(0.5)

                            except ValueError:
                                option = 'цены' if data['option'] == 'price' else 'продолжительности'
                                text = texts.error('not-numeric')
                                markups = buttons.cancel_reply(f'изменение {option}')

                    bot.delete_message(message.chat.id, delete)
                    delete = bot.send_message(message.chat.id, text, parse_mode='markdown', reply_markup=markups)

                    if message.from_user.id in sessions.admins:
                        sessions.admins[message.from_user.id]['message']['delete'] = delete.id

            # Action | Control | Payments
            if message.text == '👁 Посмотреть платежи' and not abuse:
                if len(database.get_data('payments')) > 0:
                    bot.send_message(message.from_user.id, texts.control('admin', 'payments'),
                                     parse_mode='markdown',
                                     reply_markup=buttons.control('admin', 'payments'))

                else:
                    bot.send_message(message.chat.id, texts.error('empty', 'payments'),
                                     parse_mode='markdown')

            # Process | Payment | Find payment
            if message.text == '🛠 Управлять' and not abuse:
                sessions.start(message.from_user.id, 'admin', 'find-payment', message.message_id)
                delete = bot.send_message(message.from_user.id, texts.processes('admin', 'find-payment'),
                                          parse_mode='markdown', reply_markup=buttons.cancel_reply('поиск платежа'))
                sessions.admins[message.from_user.id]['message']['delete'] = delete.id

            # Handling | Find payment
            if message.from_user.id in sessions.admins \
                    and sessions.admins[message.from_user.id]['type'] == 'find-payment':
                if sessions.admins[message.from_user.id]['message']['id'] != message.message_id:
                    delete = sessions.admins[message.from_user.id]['message']['delete']
                    text, markups, payment = str(), str(), database.get_data_by_value('payments', 'id', message.text)

                    bot.delete_message(message.chat.id, message.id)

                    if len(payment) == 0:
                        text = texts.error('not-exist', 'payment', id=message.text)
                        markups = buttons.cancel_reply('поиск платежа')

                    else:
                        payment = payment[0]

                        if payment['status'] != 'pending':
                            text = texts.error('incorrect-status', 'payment', id=message.text, status=payment['status'])
                            markups = buttons.cancel_reply('поиск платежа')

                        else:
                            bot.send_message(
                                message.chat.id, texts.success('found-data', 'payment', id=payment['id']),
                                parse_mode='markdown', reply_markup=buttons.comeback_reply('меню платежей'))
                            time.sleep(0.5)

                            text = "*Управление платежем*\n\n" \
                                   f"{texts.show('payment', item=payment)}\n\n" \
                                   "🔽 Управление данными 🔽"
                            markups = buttons.menu('admin', 'payment', markups_type='inline', payment=payment)

                    bot.delete_message(message.chat.id, delete)
                    delete = bot.send_message(message.chat.id, text, parse_mode='markdown', reply_markup=markups)
                    sessions.admins[message.from_user.id]['message']['delete'] = delete.id

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
            if message.text == '🪙 Валюта' and not abuse:
                bot.send_message(
                    message.chat.id, texts.control('admin', 'currencies'),
                    parse_mode='markdown', reply_markup=buttons.control('admin', 'currencies'))

            # Action | Change settings | Percentage
            if message.text == '🧮 Процент' and not abuse:
                sessions.start(message.from_user.id, 'admin', 'change-project-data', message.message_id)
                sessions.admins[message.from_user.id]['actions']['data']['type'] = 'percentage'

                delete = bot.send_message(
                    message.chat.id, texts.processes('admin', 'change-project-data', type='percentage'),
                    parse_mode='markdown', reply_markup=buttons.cancel_reply('изменение процента'))
                sessions.admins[message.from_user.id]['message']['delete'] = delete.id

            # Action | Change settings | Control domains
            if message.text == '🔗 Домены' and not abuse:
                bot.send_message(message.chat.id, texts.control('admin', 'domains'),
                                 parse_mode='markdown', reply_markup=buttons.control('admin', 'domains'))

            # Handling | Change | Project percentage and currencies
            if message.from_user.id in sessions.admins \
                    and sessions.admins[message.from_user.id]['type'] == 'change-project-data':
                if sessions.admins[message.from_user.id]['message']['id'] != message.message_id:
                    option = sessions.admins[message.from_user.id]['actions']['data']['type']
                    delete = sessions.admins[message.from_user.id]['message']['delete']
                    text, markups = str(), str()

                    if option == 'percentage':
                        value = "процента"
                    else:
                        option = sessions.admins[message.from_user.id]['actions']['data']['option']
                        value = 'валюты' if option == 'currency' else 'криптовалюты'

                    cancel = f"изменение {value}"
                    settings = handler.file('read', 'settings')
                    current = settings['main'][option]

                    bot.delete_message(message.chat.id, message.id)

                    if option == 'percentage':
                        try:
                            value = int(message.text)

                            if value == current:
                                text = texts.error('same', value=value)
                                markups = buttons.cancel_reply(cancel)

                            elif value < 0:
                                text = texts.error('less', value=0)
                                markups = buttons.cancel_reply(cancel)
                            else:
                                settings['main'][option] = value
                                handler.file('write', 'settings', settings)
                                bot.send_message(
                                    message.from_user.id,
                                    texts.success('updated-data', f'project-{option}', old=current, new=value),
                                    parse_mode='markdown')

                                text = texts.menu('admin', 'settings')
                                markups = buttons.menu('admin', 'settings')
                                sessions.clear(message.from_user.id)
                                time.sleep(0.5)

                        except ValueError:
                            text = texts.error('not-numeric')
                            markups = buttons.cancel_reply(cancel)
                    else:
                        value, status = message.text, False

                        try:
                            value = int(value)
                            text = texts.error('not-string')
                            markups = buttons.cancel_reply(cancel)

                        except ValueError:
                            if value.upper() == current:
                                text = texts.error('same', value=value)
                                markups = buttons.cancel_reply(cancel)
                            else:
                                match option:
                                    case 'currency':
                                        query = f'https://api.kuna.io/v3/tickers?symbols=btc{value.lower()}'
                                        result = requests.get(query).json()

                                        if type(result) is not list:
                                            text = texts.error('unavailable-or-incorrect', value=value.upper())
                                            markups = buttons.cancel_reply(cancel)
                                        else:
                                            status = True

                                    case 'cryptocurrency':
                                        query = f'https://api.kuna.io/v3/exchange-rates/{value.lower()}'
                                        result = requests.get(query).json()

                                        if 'messages' in result.keys():
                                            text = texts.error('unavailable-or-incorrect', value=value.upper())
                                            markups = buttons.cancel_reply(cancel)
                                        else:
                                            status = True

                        if status:
                            settings['main'][option] = value.upper()
                            handler.file('write', 'settings', settings)
                            bot.send_message(
                                message.from_user.id,
                                texts.success('updated-data', f'project-{option}', old=current, new=value.upper()),
                                parse_mode='markdown')

                            text = texts.control('admin', 'currencies'),
                            markups = buttons.control('admin', 'currencies')
                            sessions.clear(message.from_user.id)
                            time.sleep(0.5)

                    bot.delete_message(message.chat.id, delete)
                    delete = bot.send_message(message.chat.id, text, parse_mode='markdown', reply_markup=markups)
                    if message.from_user.id in sessions.admins:
                        sessions.admins[message.from_user.id]['message']['delete'] = delete.id

            # - USER

            # - PROMOTER
            promoter = handler.recognition('promoter', action=message.text,
                                           user=message.from_user.id, usertype=usertype)

            # Action | Display | Users
            if message.text == '👥 Пользователи' and promoter:
                array = database.get_data_by_value('users', 'inviter', message.from_user.id)
                data = False if len(array) == 0 else texts.show('referrals', array=array)
                data = handler.paginator(data, 'promoter-referrals') if data else ("- Рефералов ещё нет 🤷🏻‍♂", '')
                bot.send_message(message.chat.id, f'*Рефералы*\n\n{data[0]}',
                                 parse_mode='markdown', reply_markup=data[1])

            # Action | Display | Accruals
            if message.text == '💸 Начисления' and promoter:
                array = handler.format('list', 'promoter', 'accruals', user=message.from_user.id)
                data = False if len(array) == 0 else texts.show('payments', 'promoter', array=array)
                data = handler.paginator(data, 'promoter-accruals') if data else ("- Начислений ещё нет 🤷🏻‍♂", '')
                bot.send_message(message.chat.id, f'*Начисления*\n\n{data[0]}',
                                 parse_mode='markdown', reply_markup=data[1])

            # Action | Request | Withdraw
            if message.text == '💰 Запросить выплату' and promoter:
                result = handler.recognition('user', 'active-withdraw-requests', user=message.from_user.id)

                if result is None:
                    sessions.start(message.from_user.id, 'user', 'get-withdraw', message.message_id)
                    sessions.users[message.from_user.id]['actions']['step'] += 1
                    delete = bot.send_message(message.from_user.id, texts.processes('user', 'get-withdraw', step=1),
                                              parse_mode='markdown', reply_markup=buttons.cancel_reply('запрос вывода'))
                    sessions.users[message.from_user.id]['message']['delete'] = delete.id

                else:
                    # --- WARNING ---
                    print(result)
                    # --- WARNING ---

            # Handling | Get withdraw
            if message.from_user.id in sessions.users \
                    and sessions.users[message.from_user.id]['type'] == 'get-withdraw':
                if sessions.users[message.from_user.id]['message']['id'] != message.message_id:
                    text, markups, amount, wallet = str(), str(), None, None
                    user = database.get_data_by_value('users', 'id', message.from_user.id)[0]
                    step = sessions.users[message.from_user.id]['actions']['step']
                    delete = sessions.users[message.from_user.id]['message']['delete']

                    bot.delete_message(message.chat.id, message.id)

                    match step:
                        case 1:
                            try:
                                amount, text_error = int(message.text), None

                                if amount < 1:
                                    text_error = texts.error('less', embedded=True)

                                elif amount > user['balance']:
                                    currency = handler.file('read', 'settings')['main']['currency']
                                    value = f"{int(user['balance'])} ({currency})"
                                    text_error = texts.error('more', value=value, embedded=True)

                                else:
                                    step += 1
                                    sessions.users[message.from_user.id]['actions']['data']['amount'] = amount

                                text = texts.processes('user', 'get-withdraw', step=step, error=text_error,
                                                       amount=amount, wallet=wallet)
                                if text_error is not None:
                                    markups = buttons.cancel_reply('запрос вывода')
                                else:
                                    markups = buttons.comeback_inline('to-get-withdraw')

                            except ValueError:
                                text_error = texts.error('not-numeric', embedded=True)
                                text = texts.processes('user', 'get-withdraw', step=1, error=text_error)
                                markups = buttons.cancel_reply('запрос вывода')
                        case 2:
                            step += 1
                            wallet = message.text
                            amount = sessions.users[message.from_user.id]['actions']['data']['amount']
                            sessions.users[message.from_user.id]['actions']['data']['wallet'] = wallet

                            text = texts.processes('user', 'get-withdraw', step=step, amount=amount, wallet=wallet)
                            markups = buttons.confirm('request-withdraw', comeback='to-get-withdraw')

                    sessions.users[message.from_user.id]['actions']['step'] = step

                    try:
                        bot.edit_message_text(chat_id=message.chat.id, message_id=delete, parse_mode='markdown',
                                              text=text, reply_markup=markups)
                    except ApiTelegramException:
                        bot.delete_message(message.chat.id, delete)
                        delete = bot.send_message(message.chat.id, text, parse_mode='markdown', reply_markup=markups)

                        if message.from_user.id in sessions.users:
                            sessions.users[message.from_user.id]['message']['delete'] = delete.id








    @bot.callback_query_handler(func=lambda call: True)
    def queries_handler(call):
        queries = call.data.replace('-', ' ').split()
        print(queries)

        match queries[0]:
            case 'cancel':
                text, markups = str(), str()
                usertype = handler.recognition('usertype', user=call.from_user.id)

                if 'update-balance' in call.data:
                    text = texts.control('user', 'balance', id=queries[-1])
                    markups = buttons.control('user', 'balance', id=queries[-1])
                elif 'update-percentage' in call.data:
                    userdata = database.get_data_by_value('users', 'id', queries[-1])
                    text = "*Управление пользователем*\n\n" \
                           f"{texts.show('user', 'full', item=userdata[0])}\n\n" \
                           "🔽 Управление данными 🔽"

                    markups = buttons.menu('admin', 'user', id=userdata[0]['id'])

                elif 'update-service' in call.data:
                    service = database.get_data_by_value('services', 'name', queries[-1])[0]
                    match queries[-2]:
                        case 'title':
                            text = f"*Управление сервисом*\n\n" \
                                   f"{texts.show('service', item=service)}\n\n" \
                                   "🔽 Управление данными 🔽"
                            markups = buttons.menu('admin', 'service', markups_type='inline', array=service)
                        case 'domain':
                            text = texts.control('admin', 'domains', service=queries[-1])
                            markups = buttons.control('admin', 'domains', service=queries[-1])

                try:
                    bot.edit_message_text(chat_id=call.from_user.id, message_id=call.message.id,
                                          text=text, parse_mode='markdown', reply_markup=markups,
                                          disable_web_page_preview=True)
                except ApiTelegramException:
                    bot.answer_callback_query(callback_query_id=call.id, text='❎ Действие устарело')

                sessions.clear(call.from_user.id)

            case 'comeback':
                text, markups = str(), str()
                if 'to-user' in call.data:
                    if queries[3] == 'menu':
                        userdata = database.get_data_by_value('users', 'id', queries[-1])
                        text = "*Управление пользователем*\n\n" \
                               f"{texts.show('user', 'full', item=userdata[0])}\n\n" \
                               "🔽 Управление данными 🔽"
                        markups = buttons.menu('admin', 'user', id=userdata[0]['id'])

                    elif queries[-2] == 'privileges' and queries[-1] == 'control':
                        text = texts.control('user', 'privileges', id=int(queries[3]))
                        markups = buttons.control('user', 'privileges', id=int(queries[3]))
                elif 'to-menu' in call.data:
                    match queries[-1]:
                        case 'promoter':
                            bot.send_message(call.from_user.id, texts.menu('promoter', 'main', user=call.from_user.id),
                                             parse_mode='markdown',
                                             reply_markup=buttons.menu('promoter', 'main', user=call.from_user.id))

                elif 'to-service-control' in call.data:
                    service = database.get_data_by_value('services', 'name', queries[-1])[0]

                    if 'domains' in call.data:
                        text = texts.control('admin', 'domains', service=service['name'])
                        markups = buttons.control('admin', 'domains', service=service['name'])

                    else:
                        text = f"*Управление сервисом*\n\n" \
                               f"{texts.show('service', item=service)}\n\n" \
                               "🔽 Управление данными 🔽"
                        markups = buttons.menu('admin', 'service', markups_type='inline', array=service)

                elif 'to-domain-control' in call.data:
                    domain = call.data.replace('comeback-to-domain-control-', '')
                    service = handler.format('str', 'admin', 'domain-service', domain=domain)
                    text = texts.control('admin', 'domain', domain=domain, service=service)
                    markups = buttons.control('admin', 'domain', domain=domain)

                elif 'to-set-service' in call.data:
                    if call.from_user.id in sessions.admins:
                        step = sessions.admins[call.from_user.id]['actions']['step']
                        step -= 1
                        match queries[-1]:
                            case 'title':
                                text = texts.processes('admin', 'add-service', step=step)
                                markups = buttons.cancel_reply('добавление сервиса')

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

                elif 'to-project-settings' in call.data:
                    text = texts.menu('admin', 'settings')
                    markups = buttons.menu('admin', 'settings')

                elif 'to-domain-selection' in call.data:
                    text = texts.control('admin', 'domains')
                    markups = buttons.control('admin', 'domains')

                elif 'to-get-withdraw' in call.data:
                    if call.from_user.id in sessions.users:
                        sessions.users[call.from_user.id]['actions']['step'] -= 1
                        step = sessions.users[call.from_user.id]['actions']['step']

                        match step:
                            case 1:
                                text = texts.processes('user', 'get-withdraw', step=step)
                                markups = buttons.cancel_reply('запрос вывода')
                            case 2:
                                amount = sessions.users[call.from_user.id]['actions']['data']['amount']
                                text = texts.processes('user', 'get-withdraw', step=step, amount=amount)
                                markups = buttons.comeback_inline('to-get-withdraw')


                    else:
                        bot.answer_callback_query(callback_query_id=call.id, text='❎ Действие устарело')
                        bot.send_message(call.from_user.id, texts.menu('promoter', 'main', user=call.from_user.id),
                                         parse_mode='markdown',
                                         reply_markup=buttons.menu('promoter', 'main', user=call.from_user.id))



                try:
                    bot.edit_message_text(chat_id=call.from_user.id, message_id=call.message.id,
                                          text=text, parse_mode='markdown', reply_markup=markups)
                except ApiTelegramException:
                    try:
                        bot.delete_message(call.message.chat.id, call.message.message_id)
                        delete = bot.send_message(call.from_user.id, text, reply_markup=markups, parse_mode='markdown')

                        if call.from_user.id in sessions.admins:
                            sessions.admins[call.from_user.id]['message']['delete'] = delete.id

                        if call.from_user.id in sessions.users:
                            sessions.users[call.from_user.id]['message']['delete'] = delete.id


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

                        database.add_data('services', name=data['title'], domains=[data['domain']])
                        text = texts.menu('admin', 'services')
                        markups = buttons.menu('admin', 'services')
                        sessions.clear(call.from_user.id)

                    else:
                        bot.answer_callback_query(callback_query_id=call.id, text='❎ Действие устарело')
                        bot.delete_message(call.from_user.id, call.message.id)

                if 'request' in call.data:
                    if call.from_user.id in sessions.users:

                        match queries[-1]:
                            case 'withdraw':
                                settings = handler.file('read', 'settings')['main']

                                data = sessions.users[call.from_user.id]['actions']['data']
                                data['currency'] = settings['currency']
                                data['cryptocurrency'] = settings['cryptocurrency']

                                identifier = handler.generate('unique-id')
                                database.add_data('requests', id=identifier, type=queries[-1],
                                                  user=call.from_user.id, data=json.dumps(data))

                                text = texts.success('sent-request', 'withdraw', id=identifier)
                                markups = buttons.check(f'status-withdraw-{identifier}', menu='promoter')



                                sessions.clear(call.from_user.id)

                    else:
                        bot.answer_callback_query(callback_query_id=call.id, text='❎ Действие устарело')
                        bot.delete_message(call.from_user.id, call.message.id)
                        bot.send_message(call.from_user.id, texts.menu('promoter', 'main', user=call.from_user.id),
                                         parse_mode='markdown',
                                         reply_markup=buttons.menu('promoter', 'main', user=call.from_user.id))

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

                    case 'domain':
                        status = False

                        if 'service' in call.data:
                            try:
                                domain = int(queries[2])
                            except ValueError:
                                domain = queries[2]

                            service = database.get_data_by_value('services', 'name', queries[-1])[0]
                            domains = ast.literal_eval(service['domains'])

                            if type(domain) is int and len(domains) > domain:
                                status = True
                                del domains[domain]

                            elif type(domain) is str:
                                for value in domains:
                                    if domain in value:
                                        status = True
                                        domains.remove(value)

                            if len(domains) == 0 and service['status'] == 'active':
                                database.change_data('services', 'status', 'inactive', service['name'], 'name')

                            if status:
                                database.change_data('services', 'domains', domains, service['name'], 'name')
                                text = texts.processes('admin', 'update-service', 'domain',
                                                       action='delete', service=service['name'])
                                markups = buttons.control('admin', 'domains', action='delete', service=service['name'])

                            else:
                                bot.answer_callback_query(callback_query_id=call.id, text='❎ Действие устарело')

                        else:
                            domain = call.data.replace('delete-domain-', '')
                            service = handler.format('str', 'admin', 'domain-service', domain=domain)
                            service = database.get_data_by_value('services', 'name', service)[0]
                            domains = ast.literal_eval(service['domains'])

                            for value in domains:
                                if domain in value:
                                    domains.remove(value)

                            database.change_data('services', 'domains', domains, service['name'], 'name')

                            if len(domains) == 0 and service['status'] == 'active':
                                database.change_data('services', 'status', 'inactive', service['name'], 'name')
                            text = texts.control('admin', 'domains')
                            markups = buttons.control('admin', 'domains')

                        # ---------------------------- #
                        # DELETE DIRECTORY AND CONFIGS #
                        # ---------------------------- #

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

                elif queries[1] == 'privileges':
                    text = texts.control('user', 'privileges', step=2, type=queries[-1], id=int(queries[-2]))
                    markups = buttons.control('user', 'privileges', step=2, type=queries[-1], id=int(queries[-2]))

                elif queries[1] == 'service':
                    text = texts.control('admin', 'domains', service=queries[-2])
                    markups = buttons.control('admin', 'domains', service=queries[-2])

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
                    action = queries[-2] if len(queries) == 5 else None

                    if len(queries) == 4 or action == 'add':
                        sessions.start(call.from_user.id, 'admin', mode, call.message.id)
                        sessions.admins[call.from_user.id]['actions']['data']['mode'] = option
                        sessions.admins[call.from_user.id]['actions']['data']['service'] = service
                        sessions.admins[call.from_user.id]['actions']['data']['action'] = action

                    text = texts.processes('admin', mode, option, action=action, service=service)
                    if len(queries) == 4 or action == 'add':
                        markups = buttons.cancel_inline(f"{mode}-{option}", service)
                    else:
                        markups = buttons.control('admin', 'domains', action='delete', service=service)

                elif queries[1] == 'domain':
                    domain = call.data.replace('update-domain-', '')
                    service = handler.format('str', 'admin', 'domain-service', domain=domain)
                    services = handler.format('list', 'services', 'name')
                    services.remove(service)
                    text = texts.control('admin', 'domain', domain=domain, services=services)
                    markups = buttons.control('admin', 'services', domain=domain, services=services)

                elif queries[1] == 'subscription':
                    edit = False
                    mode, option, subscription = 'update-subscription-price', queries[-1], queries[2]

                    sessions.start(call.from_user.id, 'admin', 'update-subscription-price', call.message.id)
                    sessions.admins[call.from_user.id]['actions']['data']['subscription'] = subscription
                    sessions.admins[call.from_user.id]['actions']['data']['option'] = option
                    sessions.admins[call.from_user.id]['actions']['step'] += 1

                    text = texts.processes('admin', mode, option, subscription=subscription)
                    markups = buttons.cancel_reply(f"изменение цены")

                elif queries[1] == 'project':
                    if queries[-1] == 'currency' or queries[-1] == 'cryptocurrency':
                        edit = False
                        sessions.start(call.from_user.id, 'admin', 'change-project-data', call.message.id)
                        sessions.admins[call.from_user.id]['actions']['data']['type'] = 'currencies'
                        sessions.admins[call.from_user.id]['actions']['data']['option'] = queries[-1]

                        value = "валюты" if queries[-1] == 'currency' else "криптовалюты"
                        text = texts.processes('admin', 'change-project-data', type='currencies', option=queries[-1])
                        markups = buttons.cancel_reply(f"изменение {value}")

                elif queries[1] == 'user':
                    user = database.get_data_by_value('users', 'id', int(queries[2]))[0]

                    if 'privilege' in queries:
                        privilege, user_privileges = queries[-1], ast.literal_eval(user['privileges']),

                        match queries[3]:
                            case 'add':
                                user_privileges.append(privilege)

                            case 'delete':
                                user_privileges.remove(privilege)

                        database.change_data('users', 'privileges', user_privileges, user['id'])

                        text = texts.control('user', 'privileges', step=2, type=queries[3], id=user['id'])
                        markups = buttons.control('user', 'privileges', step=2, type=queries[3], id=user['id'])
                        bot.answer_callback_query(callback_query_id=call.id,
                                                  text=f"📍 Добавлена привилегия: "
                                                       f"{configs['users']['privileges'][privilege]}")
                    elif queries[3] == 'percentage':
                        sessions.start(
                            call.from_user.id, 'admin', 'update-user-percentage', call.message.id, user['id'])

                        text = texts.processes('admin', 'update-user-percentage', percentage=user['percentage'])
                        markups = buttons.cancel_inline('update-percentage-user', user['id'])

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
                text, markups, answer_success, answer_error, alert_display = str(), str(), str(), str(), False

                match queries[1]:
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

                        elif queries[2] == 'payments':
                            mode, page = queries[-2], int(queries[-1])
                            if mode == 'all':
                                title = "Все платежи"
                                array = database.get_data('payments')
                            else:
                                title = f"Платежи | {configs['payments']['statuses'][mode].capitalize()}"
                                array = database.get_data_by_value('payments', 'status', mode)

                            data = handler.paginator(texts.show('payments', array=array), f'payments-{mode}', page)

                        elif queries[2] == 'accruals':
                            title = "Начисления"
                            array = handler.format('dict', 'payments', 'accruals')['data']
                            data = False if len(array) == 0 else texts.show('payments', array=array)
                            data = handler.paginator(data, 'accruals', int(queries[-1])) \
                                if data else ("- Начислений ещё нет 🤷🏻‍♂", '')

                        elif queries[2] == 'promoter':
                            if queries[3] == 'referrals':
                                title = "Рефералы"
                                array = database.get_data_by_value('users', 'inviter', call.from_user.id)
                                data = False if len(array) == 0 else texts.show('referrals', array=array)
                                data = handler.paginator(data, 'promoter-referrals', int(queries[-1])) \
                                    if data else ("- Рефералов ещё нет 🤷🏻‍♂", '')

                            elif queries[3] == 'accruals':
                                title = "Начисления"
                                array = handler.format('list', 'promoter', 'accruals', user=call.from_user.id)
                                data = False if len(array) == 0 else texts.show('payments', 'promoter', array=array)
                                data = handler.paginator(data, 'promoter-accruals', int(queries[-1])) \
                                    if data else ("- Начислений ещё нет 🤷🏻‍♂", '')

                        text, markups = f"*{title}*\n\n{data[0]}", data[1]
                        answer_success, answer_error = '✅ Загружено', '❎ Ранее было загружено'

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

                    case 'service':
                        admin = database.get_data_by_value('users', 'id', call.from_user.id)[0]
                        usertype = handler.recognition('usertype', user=call.from_user.id)
                        service, mode = database.get_data_by_value('services', 'name', queries[2])[0], queries[-1]
                        domains = ast.literal_eval(service['domains'])
                        status = False if service['status'] == 'active' else True
                        answer_success = f"{'🟢' if status else '🔴'} Сервис {'включен' if status else 'выключен'}"
                        answer_error = '⛔️ Ошибка'

                        if status and len(domains) == 0:
                            alert_display = True
                            answer_error = "⛔️ Невозможно включить, так как нет добавленных доменов."
                        else:
                            database.change_data(
                                'services', 'status', 'active' if status else 'inactive', service['name'], 'name')

                            service = database.get_data_by_value('services', 'name', service['name'])[0]
                            text = f"*Управление сервисом*\n\n" \
                                   f"{texts.show('service', item=service)}\n\n" \
                                   "🔽 Управление данными 🔽"
                            markups = buttons.menu('admin', 'service', markups_type='inline', array=service)

                            sessions.clear(call.from_user.id)
                            database.add_data(
                                'logs', user=admin['id'], username=admin['name'], usertype=usertype,
                                action=texts.logs('admin', 'service', 'status', array=service)
                            )

                    case 'payment':

                        if queries[-2] == 'status':
                            payment, status = database.get_data_by_value('payments', 'id', queries[2])[0], queries[-1]

                            match status:
                                case 'success':
                                    user = database.get_data_by_value('users', 'id', payment['user'])[0]

                                    database.change_data(
                                        'users', 'balance', user['balance'] + payment['amount'], user['id'])

                                    if user['inviter']:
                                        inviter = database.get_data_by_value('users', 'id', user['inviter'])[0]

                                        amount = handler.calculate(
                                            'accrual', amount=payment['amount'], percentage=inviter['percentage'])
                                        summary = inviter['balance'] + amount

                                        database.change_data('users', 'balance', summary, inviter['id'])
                                        database.add_data('payments', id=handler.generate('unique-id'),
                                                          status='success', type='accrual', user=inviter['id'],
                                                          amount=amount, expiration=datetime.now())
                                        handler.send_message(bot, inviter['id'],
                                                             texts.notifications('new-accrual', user=inviter,
                                                                                 referral=user, amount=amount))

                                    payment = database.get_data_by_value('payments', 'id', queries[2])[0]
                                    handler.send_message(
                                        bot, user['id'], texts.notifications('deposit-accepted', payment=payment))

                                case 'error':
                                    handler.send_message(
                                        bot, payment['user'],
                                        texts.notifications('deposit-canceled', 'admin', payment=payment['id']),
                                        buttons.support()
                                    )

                            payment = database.get_data_by_value('payments', 'id', queries[2])[0]
                            text = "*Управление платежем*\n\n" \
                                   f"{texts.show('payment', item=payment)}\n\n" \
                                   "🔽 Управление данными 🔽"
                            markups = buttons.menu('admin', 'payment', markups_type='inline', payment=payment)

                try:
                    bot.edit_message_text(chat_id=call.from_user.id, message_id=call.message.id,
                                          text=text, reply_markup=markups, parse_mode='markdown',
                                          disable_web_page_preview=True)
                    bot.answer_callback_query(callback_query_id=call.id, text=answer_success)
                except ApiTelegramException:
                    bot.answer_callback_query(callback_query_id=call.id, text=answer_error, show_alert=alert_display)

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

                    case 'domain':
                        domain = call.data.replace('select-domain-', '')
                        service = handler.format('str', 'admin', 'domain-service', domain=domain)
                        text = texts.control('admin', 'domain', domain=domain, service=service)
                        markups = buttons.control('admin', 'domain', domain=domain)

                    case 'service':
                        status = False
                        service_new = database.get_data_by_value('services', 'name', queries[2])[0]
                        domains_new = ast.literal_eval(service_new['domains'])
                        domain = call.data.replace(f"select-service-{service_new['name']}-domain-", '')

                        service_old = handler.format('str', 'admin', 'domain-service', domain=domain)
                        service_old = database.get_data_by_value('services', 'name', service_old)[0]
                        domains_old = ast.literal_eval(service_old['domains'])

                        for value in domains_old:
                            if domain in value:
                                domains_old.remove(value)
                                domains_new.append(value)
                                database.change_data('services', 'domains', domains_old, service_old['name'], 'name')
                                database.change_data('services', 'domains', domains_new, service_new['name'], 'name')

                                if len(domains_old) == 0 and service_old['status'] == 'active':
                                    database.change_data('services', 'status', 'inactive', service_old['name'], 'name')

                                status = True

                        if status:
                            text = texts.control('admin', 'domain', domain=domain, service=service_new['name'])
                            markups = buttons.control('admin', 'domain', domain=domain)
                        else:
                            answer_error = '⛔️ Ошибка измененния сервиса'

                    case 'user':
                        pass

                try:
                    bot.edit_message_text(chat_id=call.from_user.id, message_id=call.message.id,
                                          text=text, reply_markup=markups, parse_mode='markdown',
                                          disable_web_page_preview=True)
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
                    case 'payments':
                        mode = queries[-1]
                        if mode == 'all':
                            title = "Все платежи"
                            array = database.get_data('payments')
                        else:
                            title = f"Платежи | {configs['payments']['statuses'][mode].capitalize()}"
                            array = database.get_data_by_value('payments', 'status', mode)

                        data = handler.paginator(texts.show('payments', array=array), f'payments-{mode}')

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
                        sessions.clear(call.from_user.id)

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
