import datetime
from typing import Dict, List, Tuple
from hoshino import scheduled_job
from hoshino.log import logger
import requests
from pygtrie import CharTrie

_tags: List[str] = []


def get_tags() -> List[str]:
    return _tags


class TagParser:
    def __init__(self, dictionary: List[str] = []):
        self._tree = CharTrie()
        for tag in dictionary:
            self._tree[tag[::-1]] = True

    def append_dictionary(self, dictionary: List[str]):
        for tag in dictionary:
            self._tree[tag[::-1]] = True

    def parse(self, input: str) -> Tuple[str, List[str]]:
        input = input.strip()[::-1]
        tags = []
        while input:
            if (
                self._tree.longest_prefix(input).value
                and self._tree.longest_prefix(input).key
            ):
                tags.append(self._tree.longest_prefix(input).key[::-1])
                input = input[len(self._tree.longest_prefix(input).key) :]
            else:
                break
        if input:
            tags.append(input[::-1])
        keyword = tags[0]
        tags.pop(0)
        return keyword, tags


_parser: TagParser = None


def get_parser() -> TagParser:
    global _parser
    if not _parser:
        _parser = TagParser(_tags)
    return _parser

_translate: Dict[str, str] = {}
def get_translate() -> Dict[str, str]:
    return _translate

@scheduled_job("interval", minutes=30, next_run_time=datetime.datetime.now())
async def sync():
    logger.info("downloading tags from https://api.shewinder.win/setu/tags")
    base_url = "https://api.shewinder.win/setu/"
    tags: List[str] = requests.get(base_url + "tags").json()
    authors: List[Dict[str, str]] = requests.get(base_url + "authors").json()
    _tags.clear()
    _tags.extend(tags)
    _tags.extend([author["author"] for author in authors])
    _tags.extend([str(author["uid"]) for author in authors])
    global parser
    parser = TagParser(_tags)
    logger.info(f"update {len(tags)} tags")

    # update tag translation
    url = 'https://api.shewinder.win/tag-translate/'
    resp = requests.get(url)
    if resp.status_code == 200:
        d = resp.json()
        _translate.update(d)
