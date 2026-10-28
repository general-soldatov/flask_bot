import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '/Users/general_soldatov/own_app/flask_bot/')))

import asyncio
import aiohttp
from dotenv import load_dotenv
from app.ydb_connect import Students, ManageVK
from app.config.config import WEB, TERMEX, service
from app.config.dictionary import lexicon
from app.features.user_api import Contingent
from app.features.stepik import StepikParser

# async def main():
#     db = ManageVK()
#     result = await db.select_keys(Students, subject='phys')
#     print(result)

# async def main():
#     async with aiohttp.ClientSession() as session:
#         async with session.get(TERMEX) as response:
#             page: dict = await response.json(content_type=None)
#             print(page)

# async def main():
#     user = await Contingent.get('Солдатов Юрий Игоревич', 'termex')
#     print(user)

async def main():
    step = StepikParser(service.stepik)
    await step.get_token()

if __name__ == "__main__":
    asyncio.run(main())
# load_dotenv()
# data = dict(name = f"sast_name",
#                         subject=lexicon.subject['phys'], web=WEB)

# print(lexicon.users['profile'].format(**data))