"""Injected native close failure; never modifies the frozen 0.3.7 source."""
import ctypes
import json
from pathlib import Path
import sys
from unittest.mock import patch
source=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(source))
from app.process_job import ProcessJob
job=ProcessJob()
handle=job.handle
raised=None
try:
    with patch.object(job.api,'CloseHandle',return_value=0):
        ctypes.set_last_error(5)
        try:job.close()
        except OSError as e:raised=str(e)
    result={'source':str(source),'injected':'CloseHandle returns FALSE, error 5',
        'error_reported':raised,'ownership_handle_retained':job.handle==handle}
    result['passed']=bool(raised) and result['ownership_handle_retained']
finally:
    # Only close the exact empty job created by this probe, even if product lost it.
    if job.handle:job.close()
    else:job.api.CloseHandle(handle)
target=Path(__file__).parent/'evidence'/sys.argv[2]
target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
sys.exit(not result['passed'])
