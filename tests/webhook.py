import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '/Users/general_soldatov/own_app/flask_bot/')))

import asyncio
from app.ydb_connect import Students, ManageVK

async def main():
    db = ManageVK()
    result = await db.select_keys(Students, subject='phys')
    print(result)

if __name__ == "__main__":
    asyncio.run(main())

