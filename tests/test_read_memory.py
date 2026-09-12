"""A small mailbox record must not allocate its full 8 MiB size limit."""
import json
from pathlib import Path
import sys
import tracemalloc
import unittest
import uuid
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.storage import read_json, atomic_json

class ReadMemoryTests(unittest.TestCase):
    def test_small_record_peak_allocation_below_one_mib(self):
        root = __import__('fixture_paths').output_root() / ('mem-' + uuid.uuid4().hex[:8])
        path = root / 'small.json'
        atomic_json(path, {'text': '中文心跳', 'value': 1})
        tracemalloc.start()
        try:
            self.assertEqual(read_json(path), {'text': '中文心跳', 'value': 1})
            current, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        (root / 'allocation.json').write_text(json.dumps({'current': current, 'peak': peak,
            'file_bytes': path.stat().st_size, 'limit': 1024*1024}), encoding='utf-8')
        self.assertLess(peak, 1024*1024, 'Tiny record allocated a near-8-MiB read buffer')

    def test_oversized_record_still_rejected(self):
        root = __import__('fixture_paths').output_root() / ('mem-' + uuid.uuid4().hex[:8])
        path = root / 'big.json'
        atomic_json(path, {'text': 'x' * 100000})
        with self.assertRaisesRegex(ValueError, '消息过大'):
            read_json(path, limit=100)

if __name__ == '__main__':
    unittest.main(verbosity=2)
