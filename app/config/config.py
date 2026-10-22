import os
import yaml
from pydantic import BaseModel
from typing import Dict, List, Optional, Union
# from boto_orm.models.config import AWSConfig, AWSSession


VK_TOKEN = os.getenv('ACCESS_KEY')
GROUP_ID = os.getenv('GROUP_ID', None)
ADMIN = os.getenv('ADMIN')
PHYS = os.getenv('PHYS')
TERMEX = os.getenv('TERMEX')
DIR = os.getenv('DIR')


class YamlProject(BaseModel):
    @classmethod
    def model_validate_yaml(cls, path, encoding='utf-8'):
        with open(path, 'r', encoding=encoding) as file:
            data = yaml.safe_load(file.read())
            return cls.model_validate(data)

class Schedule(BaseModel):
    weekday: List[str]
    selector: List[str]
    source: str
    profile: str

class Reference(YamlProject):
    library: Dict[str, Dict[str, Dict[str, str]]]
    schedule: Schedule
    courses: Dict[str, str]
    contacts: Dict[str, str]
    tasks: Dict[str, Optional[List[str | int]]]
    admin: Dict[str, str]
    groups: Dict[str, Dict[str, List[str]]]
    classes: Dict[str, str]

class Lexicon(YamlProject):
    library: Dict[str, Dict[str, Dict[str, str]]]
    schedule: Dict[str, str]
    users: Dict[str, str]
    students: Dict[str, str]
    admin: Dict[str, str]
    subject: Dict[str, str]
    buttons: Dict[str, str]
    inline: Dict[str, str]
    contacts: Dict[str, str]

# session = AWSSession(
#     access_key = os.getenv('AWS_ACCESS_KEY_ID'), 
#     secret_key = os.getenv('AWS_SECRET_ACCESS_KEY'))

# db_config = AWSConfig(
#     service_name = 'dynamodb', 
#     endpoint_url = os.getenv('ENDPOINT'), 
#     region_name = os.getenv('REGION_NAME'),
#     retries={'max_attempts': 3, 'mode': 'standard'})

# termex_config = AWSConfig(
#     service_name = 'dynamodb', 
#     endpoint_url = os.getenv('TERMEX_ENDPOINT'), 
#     region_name = os.getenv('REGION_NAME'))

# s3_config = AWSConfig(
#     service_name = 's3',
#     endpoint_url = 'https://storage.yandexcloud.net',
#     region_name = os.getenv('REGION_NAME')
# )


class Service(YamlProject):
    stepik: Dict[str, str]
    course: Dict[str, int]
    colab: List[Dict[str, str]]

service = Service.model_validate_yaml(os.path.join(DIR, 'session.yaml'))
