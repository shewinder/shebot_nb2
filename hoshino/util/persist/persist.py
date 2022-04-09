import dataclasses
import json
from pathlib import Path
from typing import Dict, MutableMapping, MutableSequence, Union

from pydantic import BaseModel

from .hook import HookyDict, HookyList

_persist_container_root: Dict[str, "Persistent"] = {}

def _trans_mutable(node, root):
    if isinstance(node, MutableSequence):
        for i, item in enumerate(node):
            if type(item) is dict:
                node[i] = PersistDict(item)
                _persist_container_root[node[i].identifier] = root
                _trans_mutable(node[i], root)
            elif type(item) is list:
                node[i] = PersistList(item)
                _persist_container_root[node[i].identifier] = root
                _trans_mutable(node[i], root)
        tmp = PersistList(node)
        _persist_container_root[tmp.identifier] = root
        return tmp

    if isinstance(node, MutableMapping):
        for k, v in node.items():
            if type(v) is list:
                tmp = PersistList(v)
                node[k] = tmp
                _persist_container_root[tmp.identifier] = root
                _trans_mutable(tmp, root)

            if type(v) is dict:
                tmp = PersistDict(v)
                node[k] = tmp
                _persist_container_root[tmp.identifier] = root
                _trans_mutable(tmp, root)
        tmp = PersistDict(node)
        _persist_container_root[tmp.identifier] = root
        return tmp
    return node

class PersistDict(HookyDict):
    def _hook(self):
        root = _persist_container_root.get(self.identifier)
        if root is not None:
            root.save_to_file()

    @property
    def identifier(self):
        return self.__class__.__name__ + str(id(self))

    def _after_del(self, i, item):
        self._hook()

    def _after_set(self, i, item):
        self._hook()

    def _before_set(self, i, item):
        if isinstance(item, MutableSequence) or isinstance(item, MutableMapping):
            if (_persist_container_root.get(self.identifier)):
                item = _trans_mutable(item, _persist_container_root.get(self.identifier))
        return i, item

class PersistList(HookyList):
    def _hook(self):
        root = _persist_container_root.get(self.identifier)
        if root is not None:
            root.save_to_file()
    @property
    def identifier(self):
        return self.__class__.__name__ + str(id(self))

    def _after_add(self, i, item):
        self._hook()

    def _after_del(self, i, item):
        self._hook()

    def _after_set(self, i, item):
        self._hook()

    def _before_add(self, i, item):
        if isinstance(item, MutableSequence) or isinstance(item, MutableMapping):
            if (_persist_container_root.get(self.identifier)):
                item = _trans_mutable(item, _persist_container_root.get(self.identifier))
        return i, item

    def _before_set(self, i, item):
        if isinstance(item, MutableSequence) or isinstance(item, MutableMapping):
            if (_persist_container_root.get(self.identifier)):
                item = _trans_mutable(item, _persist_container_root.get(self.identifier))
        return i, item
    


class EnhancedJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        if isinstance(o, HookyList):
            return list(o)
        if isinstance(o, HookyDict):
            return dict(o)
        if isinstance(o, BaseModel):
            return o.dict()
        return super().default(o)

def dump(config: dict, path: str, indent=2):
    with open(path, 'w', encoding='utf8') as f:
        json.dump(config, f, ensure_ascii=False,
                  indent=indent, cls=EnhancedJSONEncoder)
    return True


def load(path) -> Dict:
    try:
        with open(path, mode='r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        return {}


_persit_files: Dict[str, Path] = {}


class Persistent(BaseModel):
    """
    Persistent is a data class that binds a json file to a python object.
    whenever the object is modified, the json file will be updated.
    Notice: 
    1. python dataclass is not supported, so you need to inherit from BaseModel
    2. only list and dict supported, modify to other mutable (eg.set) would not be persisted automatically, 
    you can manually call save_to_file()
    """

    def __init__(self, file: Union[str, Path]) -> None:
        f = file if isinstance(file, Path) else Path(file)
        if not f.is_file:
            raise ValueError(f'{f} is a directory, not a file')
        if not f.parent.exists():
            f.parent.mkdir(parents=True)
        if f.exists():
            super(__class__, self).__init__(**load(f))
        else:
            f.touch()
            super().__init__()
        _persit_files[self.identifier] = f
        # recursively transform all list and dict to hooky list and dict
        self.__dict__.update(_trans_mutable(self.__dict__, self))

    @property
    def identifier(self):
        return self.__class__.__name__ + str(id(self))

    def save_to_file(self):
        dump(self.dict(), _persit_files[self.identifier])

    def __setattr__(self, key, value):
        if isinstance(value, (MutableSequence, MutableMapping)):
            value = _trans_mutable(value, self)
        super().__setattr__(key, value)
        self.save_to_file()

    class Config:
        arbitrary_types_allowed = True

###############################################################################
if __name__ == '__main__':
    from typing import List


    class Address(BaseModel):
        street: str
        city: str
        state: str

    class Person(Persistent):
        # name: str = 'anonymous'
        # age: int = 24
        # hobbys: list = []
        girls: Dict[str, int] = {'rose': 14, 'lucy': 20}
        # addr: Address = Address(street='tmpn', city='york', state='alala')
        nest_li: List[List[List[str]]] = [[[]]]

    def clear_file():
        f = Path('tmp.json')
        if f.exists():
            f.write_text('')

    clear_file()
    p = Person('tmp.json')
    assert p.girls['rose'] == 14
    print(type(p.girls))
    print(p.girls.identifier)
    print(_persist_container_root)
    print(p.girls.identifier in _persist_container_root)
    print(_persist_container_root.get(p.girls.identifier))
    p.girls['rose'] = 18
    print(p.girls)
    ann = Person('tmp.json')
    assert ann.girls['rose'] == 18
    print(type(p.nest_li))
    p.nest_li.append([[123]])







