from collections import UserList, UserDict


class HookyList(UserList):

    def _before_add(self, i, item):
        """i, item should be returned"""
        return i, item

    def _before_set(self, i, item):
        """i, item should be returned"""
        return i, item

    def _before_del(self, i, item):
        """i, item should be returned"""
        return i, item

    def _after_add(self, i, item):
        return
    
    def _after_set(self, i, item):
        return

    def _after_del(self, i, item):
        return

    def __setitem__(self, i, item): 
        i, item = self._before_set(i, item)
        self.data[i] = item
        self._after_set(i, item)

    def __delitem__(self, i): 
        i = self._before_del(i)
        del self.data[i]
        self._after_del(i)

    def append(self, item): 
        i, item = self._before_add(len(self), item)
        self.data.append(item)
        self._after_add(i, item)

    def insert(self, i, item):
        i, item = self._before_add(i, item)
        self.data.insert(i, item)
        self._after_add(i, item)

    def remove(self, item):
        i, item = self._before_del(None, item)
        self.data.remove(item)
        self._after_del(i, item)

    def clear(self):
        i, item = self._before_del(None, None)
        self.data.clear()
        self._after_del(i, item)

    def reverse(self): 
        i, item = self._before_set(None, None)
        self.data.reverse()
        self._after_set(i, item)

    def sort(self, /, *args, **kwds): 
        i, item = self._before_set(None, None)
        self.data.sort(*args, **kwds)
        self._after_set(i, item)

    def extend(self, other):
        i, item = self._before_add(None, None)
        if isinstance(other, UserList):
            self.data.extend(other.data)
        else:
            self.data.extend(other)
        self._after_add(i, item)

class HookyDict(UserDict):

    def _before_set(self, i, item):
        """i, item should be returned"""
        return i, item

    def _before_del(self, i, item):
        """i, item should be returned"""
        return i, item
    
    def _after_set(self, i, item):
        return

    def _after_del(self, i, item):
        return

    def __setitem__(self, key, item):
        i, item = self._before_set(key, item)
        self.data[key] = item
        self._after_set(i, item)

    def __delitem__(self, key): 
        i, item = self._before_del(key)
        del self.data[key]
        self._after_del(i, item)

