from collections import OrderedDict


class MessageCache:
    def __init__(self, max_size=500, evict_batch=100):
        self.max_size = max_size
        self.evict_batch = evict_batch
        self._cache = OrderedDict()

    def put(self, message_id, data):
        self._cache[message_id] = data
        self._cache.move_to_end(message_id)
        while len(self._cache) > self.max_size:
            for _ in range(self.evict_batch):
                if not self._cache:
                    break
                self._cache.popitem(last=False)

    def pop(self, message_id):
        return self._cache.pop(message_id, None)

    def __len__(self):
        return len(self._cache)
