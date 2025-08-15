# pillsbot/debug_ids.py
from __future__ import annotations

import sys
from typing import Iterable, Optional, Dict, Tuple

from aiogram.types import Message
from aiogram import Bot


async def _name_tuple_from_user(u) -> Tuple[Optional[str], Optional[str]]:
    username = u.username or None
    realname = f"{u.first_name or ''} {u.last_name or ''}".strip() or None
    return username, realname


async def print_group_and_users_best_effort(
    bot: Bot,
    message: Message,
    known_user_ids: Optional[Iterable[int]] = None,
) -> None:
    """
    Print to stdout:
      - group_id
      - For each participant we can discover: user_id, @username, real name
    No messages are sent or deleted in chat; no state is changed.

    Strategy (best-effort, platform-appropriate):
      1) Include chat administrators (get_chat_administrators).
      2) Include the message sender (if any).
      3) Include the bot itself.
      4) Include any known user ids (e.g., patient, nurse) via get_chat_member.
         This covers non-admin, silent members (like a nurse who hasn't spoken).
    """
    chat = message.chat
    group_id = chat.id

    users: Dict[int, Tuple[Optional[str], Optional[str]]] = {}

    # 1) Admins
    try:
        admins = await bot.get_chat_administrators(group_id)
        for a in admins:
            u = a.user
            users[u.id] = await _name_tuple_from_user(u)
    except Exception:
        pass  # ignore, proceed with other sources

    # 2) Sender
    if message.from_user:
        u = message.from_user
        users.setdefault(u.id, await _name_tuple_from_user(u))

    # 3) Bot itself
    try:
        me = await bot.get_me()
        users.setdefault(me.id, await _name_tuple_from_user(me))
    except Exception:
        pass

    # 4) Known user ids (patient, nurse) — fetch membership info even if not admins/senders
    if known_user_ids:
        for uid in known_user_ids:
            try:
                member = await bot.get_chat_member(group_id, uid)
                u = member.user
                users.setdefault(u.id, await _name_tuple_from_user(u))
            except Exception:
                # If not found or inaccessible, still record the raw uid
                users.setdefault(uid, (None, None))

    # Print to console/stdout
    print(f"group_id={group_id}", file=sys.stdout, flush=True)
    for uid, (uname, realname) in users.items():
        print(
            f"user_id={uid} username={uname!r} name={realname!r}",
            file=sys.stdout,
            flush=True,
        )
