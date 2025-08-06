import asyncio
from aiogram import Bot
from aiogram.fsm.context import FSMContext
from reminder_bot.states import ReminderStates
from reminder_bot.config.dialogs_loader import DIALOGS

class ReminderManager:
    def __init__(self, bot: Bot, dispatcher, scheduler, log_service):
        self.bot = bot
        self.dp = dispatcher
        self.scheduler = scheduler
        self.log = log_service

    async def start_flow(self, event_name: str):
        """Entry point for a reminder flow. Sends main prompt and sets FSM state."""
        cfg = DIALOGS['events'][event_name]
        # For simplicity assume global chat_id configured
        chat_id = cfg.get('chat_id')
        if not chat_id:
            return
        # send main text
        await self.bot.send_message(chat_id, cfg['main_text'])
        # set FSM to waiting_confirmation
        state: FSMContext = self.dp.current_state(chat=chat_id, user=chat_id)
        await state.set_state(ReminderStates.waiting_confirmation)
        await state.update_data(current_event=event_name, attempts=0, clarifications=0)
        # schedule retry if needed
        delay = cfg.get('retry_delay_seconds', 0)
        retries = cfg.get('retries', 0)
        if retries > 0:
            job_id = f"retry_{event_name}_{chat_id}"
            self.scheduler.add_job(self._handle_retry,
                                   'date',
                                   run_date=asyncio.get_event_loop().time() + delay,
                                   args=[event_name, chat_id, 1],
                                   id=job_id)

    async def _handle_retry(self, event_name, chat_id, attempt):
        """Handle a retry attempt: send retry_text or escalate to clarification."""
        cfg = DIALOGS['events'][event_name]
        state: FSMContext = self.dp.current_state(chat=chat_id, user=chat_id)
        data = await state.get_data()
        if data.get('confirmed'):
            return
        if attempt <= cfg.get('retries',0):
            await self.bot.send_message(chat_id, cfg['retry_text'])
            await state.update_data(attempts=attempt)
            # schedule next
            if attempt < cfg['retries']:
                delay = cfg.get('retry_delay_seconds',0)
                self.scheduler.add_job(self._handle_retry,
                                       'date',
                                       run_date=asyncio.get_event_loop().time()+delay,
                                       args=[event_name, chat_id, attempt+1])
            else:
                # escalate to clarification
                await self._start_clarification(event_name, chat_id)

    async def _start_clarification(self, event_name, chat_id):
        cfg = DIALOGS['events'][event_name]
        await self.bot.send_message(chat_id, cfg.get('clarify_text','Please confirm (OK)'))
        state: FSMContext = self.dp.current_state(chat=chat_id, user=chat_id)
        await state.set_state(ReminderStates.waiting_clarification)
        await state.update_data(clarifications=1)
        # schedule further clarifications similar to retries if needed

    # Additional methods: cancel flow upon confirmation, escalation to nurse, etc.
