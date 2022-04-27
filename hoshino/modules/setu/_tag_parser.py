import json
from typing import Dict, List, Tuple, Union
from pygtrie import CharTrie
from ._tag import tag_data

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

parser = TagParser()
parser.append_dictionary(tag_data.tags)
