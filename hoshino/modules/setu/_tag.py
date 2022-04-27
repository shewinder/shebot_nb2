from typing import Dict, List
from hoshino.util.persist import Persistent
from hoshino import userdata_dir
from hoshino.log import logger
import requests

class TagData(Persistent):
    tags: List[str] = []

setu_dir = userdata_dir / 'setu'
tag_file = setu_dir / 'tags.json'

if not setu_dir.exists():
    setu_dir.mkdir()

if not tag_file.exists():
    tag_file.touch()
    tag_data = TagData(tag_file)
    logger.info('downloading tags from https://api.shewinder.win/setu/tags')
    base_url = 'https://api.shewinder.win/setu/'
    tags: List[str] = requests.get(base_url + 'tags').json()
    authors: List[Dict[str, str]] = requests.get(base_url + 'authors').json()
    tags.extend([author['author'] for author in authors])
    tags.extend([str(author['uid']) for author in authors])
    logger.info(f'update {len(tags)} tags')
    tag_data.tags.extend(tags)
else:
    tag_data = TagData(tag_file)


