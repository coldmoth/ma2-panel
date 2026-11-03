"""Read evidence with monotonic expiry; wall time is only a display timestamp."""
import time


class Evidence:
    def __init__(self, source='ma2', *, clock=time.monotonic, wall=time.time):
        self.source, self.clock, self.wall = source, clock, wall
        self.records = {}

    def observe(self, key, value):
        self.records[key] = (value, self.clock(), self.wall())

    def invalidate(self, keys=None):
        if keys is None:
            self.records.clear()
        else:
            for key in keys:
                self.records.pop(key, None)

    def snapshot(self, keys):
        values, meta = {}, {}
        now = self.clock()
        for key in keys:
            record = self.records.get(key)
            if record is None:
                values[key] = None
                meta[key] = {'source': 'unknown', 'freshness': 'unknown', 'updated_at': None}
            else:
                value, stamp, wall = record
                fresh = now - stamp < 6
                values[key] = value if fresh else None
                meta[key] = {'source': self.source, 'freshness': 'fresh' if fresh else 'stale', 'updated_at': wall}
        return values, meta
