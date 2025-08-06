from apscheduler.schedulers.asyncio import AsyncIOScheduler

def create_scheduler():
    # Use Kyiv timezone by default
    return AsyncIOScheduler(timezone='Europe/Kyiv')
