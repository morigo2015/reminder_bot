# tests/test_group_template_backcompat.py
import pytest
from pillsbot.core.reminder_messaging import ReminderMessenger
from pillsbot.core.i18n import MESSAGES


class FakeAdapter:
    def __init__(self):
        self.group = []

    async def send_group_message(self, group_id, text, reply_markup=None):
        self.group.append((group_id, text))
        return 1


@pytest.mark.asyncio
async def test_send_group_template_backcompat():
    ad = FakeAdapter()
    ms = ReminderMessenger(adapter=ad, log=None)
    await ms.send_group_template(1, "reminder_line", pill_text="Вітамін Д")
    assert ad.group[-1][1] == MESSAGES["reminder_line"].format(pill_text="Вітамін Д")
