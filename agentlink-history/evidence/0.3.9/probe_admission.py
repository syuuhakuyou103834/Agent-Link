import json
import sys
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent
SOURCE=Path(sys.argv[1]).resolve()
sys.path[:0]=[str(SOURCE),str(SOURCE/'tests')]
from test_repairs import RepairComponentTests, Fixture
from app.engine import NodeService
from app.storage import Settings, atomic_json, FileLock

case=RepairComponentTests('test_T18_request_protocol_and_legal_control')
case.setUp()
try:
    node=case.node
    node.status='idle'
    atomic_json(case.box.root/'nodes/B-owner.json',{'role':'B','instance':node.instance})
    def failed_turn(*args):
        case.client.cleanup_pending=True
        raise RuntimeError('injected: tool process still alive; cleanup failed')
    with patch.object(case.client,'run_turn',side_effect=failed_turn):
        node.run_initiator('cleanup failure admission probe',1)
    events=[]
    contender=NodeService(Settings(role='A',shared_root=str(case.box.root)),case.root/'contender',lambda k,v:events.append((k,v)))
    contender.box,contender.connected=case.box,True
    contender.client=Fixture(case.root)
    contender._admit_start({'request_id':'after-cleanup-failure','topic':'must reject','rounds':1})
    admitted=not contender.commands.empty()
    while not contender.commands.empty():
        _,args=contender.commands.get_nowait()
        if args.get('_dispatch'):args['_dispatch'].close()
    result={'source':str(SOURCE),'layer':'local service with injected cleanup-pending fixture',
            'cleanup_pending':case.client.cleanup_pending,'peer_new_request_admitted':admitted,
            'expected_admitted':False,'status':'FAIL' if admitted else 'PASS','evidence':str(case.root),'events':events}
    (ROOT/(sys.argv[2]+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
finally:
    if getattr(node,'execution_lock',None):
        node.execution_lock.close();node.execution_lock=None
    case.tearDown()
