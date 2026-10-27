import json
import time
from .functool import study_score
from boto_orm.s3_manager import S3Manager

from app.config.config import s3_config, session
# from app.database import DBManage, db_phys, db_termex
from app.ydb_connect import ManageVK, Students
# from pathlib import Path


# def rate_score(bucket_name: str, db: DBManage):
#     start = time.time()
#     s3 = S3Manager(bucket_name, configure.s3_config, configure.session)
#     study_list = []
#     profile_list = []
#     message = []
#     try:
#         for item in db.all_user():
#             study = {
#             "name": item['name'],
#             "profile": item['profile'],
#             "score": study_score(item)
#             }
#             study_list.append(study)

#             if item['profile'] not in profile_list:
#                 profile_list.append(item['profile'])

#         for profile in profile_list:
#             lst = filter(lambda x: x['profile'] == profile, study_list)
#             data_json = []
#             for i, item in enumerate(sorted(lst, key=lambda x: x['score'], reverse=True), 1):
#                 item['rate'] = i
#                 data_json.append(item)
#             data = json.dumps(data_json, ensure_ascii=False, indent=4)
#             s3.put_object(body=data, name_file=f'rate/{profile}.json')
#             # message.append(f'File {profile}.json is created!')
#     except Exception as e:
#         finish = time.time()
#         return {
#         'message': e,
#         'time': str(finish - start)
#         }
#     finish = time.time()
#     return {
#         'message': data,
#         'time': str(finish - start)
#         }

# def handler(name: str):
#     db = {
#         'phys-bot': db_phys,
#         'termex-bot': db_termex
#     }
#     try:
#         return rate_score(name, db[name])
#     except Exception as e:
#         return e

def get_rate(profile: str, bucket_name: str):
    s3 = S3Manager(bucket_name, s3_config, session)
    data = s3.get_str_object(f'rate/{profile}.json')
    return json.loads(data)[:10]


async def maker(users: list, subject: str, stepik: list):
    start = time.time()
    study_list = []
    profile_list = []
    message = []
    s3 = S3Manager(f'{subject}-bot', s3_config, session)
    try:
        for item in users:
            step = None
            for elem in stepik:
                if elem.id == item.id:
                    step = elem
                    break
                    
            study = {
                "name": item.full_name,
                "profile": item.profile,
                "score": study_score(item, step)
            }
            study_list.append(study)

            if item.profile not in profile_list:
                profile_list.append(item.profile)

        for profile in profile_list:
            lst = filter(lambda x: x['profile'] == profile, study_list)
            data_json = []
            for i, item in enumerate(sorted(lst, key=lambda x: x['score'], reverse=True), 1):
                item['rate'] = i
                data_json.append(item)
            data = json.dumps(data_json, ensure_ascii=False, indent=4)
            s3.put_object(body=data, name_file=f'rate/{profile}.json')
            message.append(f'File {profile}.json is created!')

    except Exception as e:
        finish = time.time()
        return {
        'message': e,
        'time': str(finish - start)
        }
    finish = time.time()
    return {
        'message': '\n'.join(message),
        'time': str(finish - start)
        }

async def rate_score_vk():
    data = None
    buckets = ['phys', 'termex']
    text = []
    db = ManageVK()
    for subject in buckets:
        data = await db.select_keys(Students, subject=subject)
        step = await db.get_all_stepik()
        if not data:
            continue
        text.append(maker(data, subject, step))

    return text