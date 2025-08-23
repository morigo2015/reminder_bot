from app.db.pool import pool


async def upsert_patient(pid: str, chat_id: int, name: str) -> None:
    sql = (
        "INSERT INTO patients (id, chat_id, name) VALUES (%s, %s, %s) AS new "
        "ON DUPLICATE KEY UPDATE chat_id = new.chat_id, name = new.name"
    )
    async with pool().acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, (pid, chat_id, name))
