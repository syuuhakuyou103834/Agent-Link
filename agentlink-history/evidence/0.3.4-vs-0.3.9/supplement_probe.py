import json
from pathlib import Path
import sys
import tracemalloc

root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))
from app import __version__
from app.storage import atomic_json, read_json
from app.protocol import TurnView

path = root / 'supplement' / 'small.json'
atomic_json(path, {'text': '中文心跳', 'value': 1})
tracemalloc.start()
value = read_json(path)
current, peak = tracemalloc.get_traced_memory()
tracemalloc.stop()
assert value == {'text': '中文心跳', 'value': 1}
view = TurnView('A', '002-A', 'same-thread')
view.turn_id = 'new-turn'
view.feed('item/agentMessage/delta', {'threadId': 'same-thread', 'turnId': 'old-turn',
                                   'itemId': 'old', 'delta': 'STALE-DELTA'})
result = {'version': __version__, 'small_json_peak_bytes': peak,
          'stale_delta_answer': view.snapshot()['answer'], 'file_bytes': path.stat().st_size}
(root.parent / (__version__ + '-supplement-results.json')).write_text(
    json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=False))
