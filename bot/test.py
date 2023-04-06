import re

_recipient, _sender = 'ulrikpiazza1966@poczta.onet.pl', 'support@365fx.online'
identifier, status, description, array = None, None, None, dict()

with open('mail.log', 'r') as file:
    sender, recipient = None, None
    logs = file.readlines()

    for line in logs[::-1]:
        if 'removed' in line:
            identifier = line.split()[-2].replace(':', '')

            if identifier not in array.keys():
                array[identifier] = list()

        if identifier is not None and identifier in array.keys():
            line = re.sub('^\s+|\n|\r|"|\s+$', ' ', line)

            if identifier in line:
                line = line.split(f'{identifier}:')
            else:
                line = line.split(']:')

            array[identifier].append(line[-1])

    for identifier, data in array.items():
        for line in data:
            if 'to=' in line:
                recipient = line
            if 'from=' in line:
                sender = line

        if _recipient in recipient and _sender in sender:
            break

    if 'status=sent' in recipient:
        status = True
    if 'status=bounced' in recipient:
        status, description = False, recipient.split('status=bounced')[-1][2:-2]

print(status)
print(description)




    # if not sender and not recipient:
    #     for identifier, data in array.items():
    #         if not _sender and not _recipient:
    #     print(f'{identifier}\n')
    #
    #     for line in data:
    #         print(line)
    #
    #     print('\n\n')



# DKIM-Signature field added
# no MX host for mailhub.online has a valid address record