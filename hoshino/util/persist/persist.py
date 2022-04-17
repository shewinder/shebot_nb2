import dataclasses
import json
from pathlib import Path
from typing import Dict, MutableMapping, MutableSequence, Union, TypeVar

from pydantic import BaseModel

from .hook import HookyDict, HookyList

_persist_container_root: Dict[str, "Persistent"] = {}


def _trans_mutable(node, root):
    if not node:
        return node
    if isinstance(node, MutableSequence):
        for i, item in enumerate(node):
            if type(item) is dict:
                node[i] = PersistDict(item)
                _persist_container_root[node[i]._identifier] = root
                _trans_mutable(node[i], root)
            elif type(item) is list:
                node[i] = PersistList(item)
                _persist_container_root[node[i]._identifier] = root
                _trans_mutable(node[i], root)
        return node

    if isinstance(node, MutableMapping):
        for k, v in node.items():
            if type(v) is list:
                tmp = PersistList(v)
                node[k] = tmp
                _persist_container_root[tmp._identifier] = root
                _trans_mutable(tmp, root)

            if type(v) is dict:
                tmp = PersistDict(v)
                node[k] = tmp
                _persist_container_root[tmp._identifier] = root
                _trans_mutable(tmp, root)
        return node
    return node


class PersistDict(HookyDict):
    def _hook(self):
        root = _persist_container_root.get(self._identifier)
        if root is not None:
            root.save_to_file()

    @property
    def _identifier(self):
        return self.__class__.__name__ + str(id(self))

    def _after_del(self, i, item):
        self._hook()

    def _after_set(self, i, item):
        self._hook()

    def _before_set(self, i, item):
        if isinstance(item, MutableSequence) or isinstance(item, MutableMapping):
            if (_persist_container_root.get(self._identifier)):
                item = _trans_mutable(
                    item, _persist_container_root.get(self._identifier))
        return i, item


class PersistList(HookyList):
    def _hook(self):
        root = _persist_container_root.get(self._identifier)
        if root is not None:
            root.save_to_file()

    @property
    def _identifier(self):
        return self.__class__.__name__ + str(id(self))

    def _after_add(self, i, item):
        self._hook()

    def _after_del(self, i, item):
        self._hook()

    def _after_set(self, i, item):
        self._hook()

    def _before_add(self, i, item):
        root = _persist_container_root.get(self._identifier)
        if isinstance(item, MutableSequence):
            if root:
                item = _trans_mutable(item, root)
                item = PersistList(item)
                _persist_container_root[item._identifier] = root
        if isinstance(item, MutableMapping):
            if root:
                item = _trans_mutable(item, root)
                item = PersistDict(item)
                _persist_container_root[item._identifier] = root
        return i, item

    def _before_set(self, i, item):
        if isinstance(item, MutableSequence) or isinstance(item, MutableMapping):
            if (_persist_container_root.get(self._identifier)):
                item = _trans_mutable(
                    item, _persist_container_root.get(self._identifier))
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

T = TypeVar('T')


class Persistent(BaseModel):
    """
    Persistent is a data class that binds a json file to a python object.
    whenever the object is modified, the json file will be updated.
    Notice: 
    1. python dataclass is not supported, so you need to inherit from pydantic.BaseModel
    2. only list and dict supported, modify to other mutable (eg.set) would not be persisted automatically, 
    you can manually call save_to_file()
    3. always use Class.get_instance() to get an instance
    """
    _instances: Dict[Path, "Persistent"] = {}

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
        _persit_files[self._identifier] = f
        # recursively transform all list and dict to hooky list and dict
        self.__dict__.update(_trans_mutable(self.__dict__, self))
        self.__class__._instances[f] = self

    @classmethod
    def get_instance(cls: T, file: Union[str, Path]) -> T:
        if isinstance(file, str):
            file = Path(file)
        if file not in cls._instances:
            cls(file)
        return cls._instances[file]

    def update(self, d: Dict):
        file = _persit_files[self._identifier]
        for k in d:
            if isinstance(self.__dict__[k], MutableSequence) or isinstance(self.__dict__[k], MutableMapping):
                del _persist_container_root[self.__dict__[k]._identifier]
        del self.__class__._instances[file]
        self.__dict__.update(_trans_mutable(d, self))
        self.save_to_file()

    def _clear(self):
        """
        This function will clear the link which makes persistence possible on mutable container 
        """
        global _persist_container_root
        for k in list(_persist_container_root.keys()):
            if _persist_container_root[k] == self:
                del _persist_container_root[k]

    @property
    def _identifier(self):
        return self.__class__.__name__ + str(id(self))

    @property
    def _file(self):
        return _persit_files[self._identifier]

    def save_to_file(self):
        dump(self.dict(), _persit_files[self._identifier])

    def __setattr__(self, key, value):
        if isinstance(value, (MutableSequence, MutableMapping)):
            # value = _trans_mutable(value, self)  # TODO: may cause memory leak
            raise ValueError(
                f'trying to set a mutable sequence or map to field "{key}"')
        super().__setattr__(key, value)
        self.save_to_file()

    class Config:
        arbitrary_types_allowed = True
