from collections import defaultdict
from typing import Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from ._model import SubscribeRecord, BaseInfoChecker


CHECKERS: List["BaseInfoChecker"] = [] 
SUBS: Dict[str, Dict[str, "SubscribeRecord"]] = defaultdict(dict)