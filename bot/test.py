import time
from datetime import datetime, timedelta

data = {'title': 'недельная', 'type': 'day', 'duration': 7}
now, calculated = int(time.time()), 0

formatted_now = datetime.fromtimestamp(now)
match data['type']:
    case 'hour':
        calculated = formatted_now + timedelta(hours=data['duration'])
    case 'day':
        calculated = formatted_now + timedelta(hours=data['duration'])

expiration = int(calculated.timestamp())
result = {'now': now, 'expiration': expiration}
print(result)