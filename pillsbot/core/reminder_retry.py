# pillsbot/core/reminder_retry.py
from __future__ import annotations

import asyncio
from typing import Callable, Awaitable
from pillsbot.core.logging_utils import kv
from pillsbot.core.reminder_state import Status, DoseInstance


class RetryManager:
    """
    Runs the retry loop for a DoseInstance, escalating at the end.
    Keeps all timing policy here so engines stay small and testable.
    """

    def __init__(
        self,
        interval_seconds: int,
        max_attempts: int,
        *,
        send_repeat: Callable[[DoseInstance], Awaitable[None]],
        on_escalate: Callable[[DoseInstance], Awaitable[None]],
        set_status: Callable[[DoseInstance, Status], None],
        get_status: Callable[[DoseInstance], Status],
        logger,
    ) -> None:
        self.interval_seconds = interval_seconds
        self.max_attempts = max_attempts
        self.send_repeat = send_repeat
        self.on_escalate = on_escalate
        self.set_status = set_status
        self.get_status = get_status
        self.log = logger

    async def run(self, inst: DoseInstance) -> None:
        """
        Retry until confirmed or attempts exhausted. On exhaustion, escalate.
        Caller is responsible for storing/ cancelling the created task.
        """
        try:
            while self.get_status(inst) not in (Status.CONFIRMED, Status.ESCALATED):
                # Wait for the configured interval
                await asyncio.sleep(self.interval_seconds)

                # Maybe user confirmed in the meantime
                if self.get_status(inst) in (Status.CONFIRMED, Status.ESCALATED):
                    break

                # Attempt another reminder
                inst.attempts_sent += 1
                if inst.attempts_sent > self.max_attempts:
                    # Escalate
                    self.set_status(inst, Status.ESCALATED)
                    self.log.info(
                        "retry.escalate "
                        + kv(
                            patient_id=inst.patient_id,
                            time=inst.dose_key.time_str,
                            attempts=inst.attempts_sent,
                        )
                    )
                    await self.on_escalate(inst)
                    break

                self.log.debug(
                    "retry.repeat "
                    + kv(
                        patient_id=inst.patient_id,
                        time=inst.dose_key.time_str,
                        attempt=inst.attempts_sent,
                    )
                )
                await self.send_repeat(inst)
        except asyncio.CancelledError:  # normal shutdown path
            raise
        except Exception as e:  # pragma: no cover - defensive
            self.log.error(
                "retry.loop.error "
                + kv(
                    patient_id=inst.patient_id, time=inst.dose_key.time_str, err=str(e)
                )
            )
