import os
import csv
import datetime
from asyncio import Lock

class CSVLogger:
    _locks = {}
    def __init__(self, type_name: str):
        self.type_name = type_name
        base = os.path.join(os.path.dirname(__file__), "..", "data", "logs")
        os.makedirs(base, exist_ok=True)
        self.path = os.path.join(base, f"{type_name}.csv")
        if not os.path.exists(self.path):
            with open(self.path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                if type_name == "reminder":
                    writer.writerow(["timestamp", "chat_id", "event_key", "action"])
                elif type_name == "pressure":
                    writer.writerow(["timestamp", "chat_id", "systolic", "diastolic", "pulse"])
                elif type_name == "status":
                    writer.writerow(["timestamp", "chat_id", "messages"])
        if type_name not in CSVLogger._locks:
            CSVLogger._locks[type_name] = Lock()
        self._lock = CSVLogger._locks[type_name]

    async def log(self, chat_id: int, **data):
        async with self._lock:
            with open(self.path, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                row = [datetime.datetime.utcnow().isoformat(), chat_id]
                if self.type_name == "reminder":
                    row.extend([data["event_key"], data["action"]])
                elif self.type_name == "pressure":
                    row.extend([data["systolic"], data["diastolic"], data["pulse"]])
                elif self.type_name == "status":
                    row.append(data["messages"])
                writer.writerow(row)
