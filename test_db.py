import asyncio
from app.infrastructure.db.session import AsyncSessionLocal
from app.infrastructure.db.seed import seed_database

async def main():
    async with AsyncSessionLocal() as session:
        res = await seed_database(session)
        await session.commit()
        print("Seed result:", res)

if __name__ == "__main__":
    asyncio.run(main())
