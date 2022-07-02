from queue import Queue
from typing import Optional

NR18 = Queue(10) # 非r18色图
R18 = Queue(10) # r18色图.

# infopush
from collections import defaultdict
_sub_data = defaultdict(
    list
)  # {checker_name: [Subscribe ...]}

_checkers = []