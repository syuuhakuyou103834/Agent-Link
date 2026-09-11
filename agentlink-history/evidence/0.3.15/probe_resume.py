from pathlib import Path
import sys,json
r=Path(__file__).parent;sys.path.insert(0,str(r/'source'))
from app.protocol import RpcClient
from app.storage import find_codex
from app.review_workflow import scoped_settings
for n in ('probe-source','probe-tests'):(r/n).mkdir(exist_ok=True)
settings=scoped_settings({'model':'gpt-6-astra'},r/'probe-source',r/'probe-tests','review',[])
c=RpcClient([find_codex(),'app-server','--listen','stdio://'],r/'real-rpc')
result={'model_requests':0}
try:
 c.start();tid=c.new_thread(settings,str(r/'probe-tests'),'Permission-preserving resume check; no model turn will be sent.')
 result['start']='PASS'
 c.call('thread/inject_items',{'threadId':tid,'items':[{'type':'message','role':'user','content':[{'type':'input_text','text':'Local protocol persistence fixture. No model invocation.'}]}]})
 c.close();c.start()
 restored=c.scoped_thread(settings,str(r/'probe-tests'),'Permission-preserving resume check; no model turn will be sent.',resume_thread=tid)
 assert restored==tid;result['resume_same_id_and_permissions']='PASS'
 try:
  c.call('turn/steer',{'threadId':tid,'expectedTurnId':'not-an-active-turn','input':[{'type':'text','text':'Local stale steering check.'}]})
  result['inactive_steer']='UNEXPECTED_ACCEPT'
 except RuntimeError as e:result['inactive_steer']='REJECTED';result['inactive_error']=str(e)
except Exception as e:result['error']=str(e)
finally:c.close()
(r/'evidence/real-resume.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
