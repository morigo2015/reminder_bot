import csv
import os
from datetime import datetime

class LogService:
    def __init__(self, base_path='logs'):
        self.base_path = base_path
        os.makedirs(base_path, exist_ok=True)

    def _log(self, filename, row):
        path = os.path.join(self.base_path, filename)
        write_header = not os.path.exists(path)
        with open(path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(row.keys())
            writer.writerow(row.values())

    async def pressure(self, chat_id, high, low, pulse):
        row = {
            'timestamp': datetime.utcnow().isoformat(),
            'CHAT_ID': chat_id,
            'HIGH': high,
            'LOW': low,
            'PULSE': pulse,
        }
        self._log('pressure.csv', row)

    async def status(self, chat_id, text, dropped):
        row = {
            'timestamp': datetime.utcnow().isoformat(),
            'CHAT_ID': chat_id,
            'STATUS': text,
            'DROPPED': dropped,
        }
        self._log('status.csv', row)

    async def confirmation(self, chat_id, event_name, status, attempts, clarifications):
        row = {
            'timestamp': datetime.utcnow().isoformat(),
            'CHAT_ID': chat_id,
            'EVENT': event_name,
            'STATUS': status,
            'ATTEMPTS': attempts,
            'CLARIFICATIONS': clarifications,
        }
        self._log('confirmation.csv', row)
