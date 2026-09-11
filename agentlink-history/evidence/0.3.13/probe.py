import sys,json,hashlib
from pathlib import Path
sys.path.insert(0,r'C:\AgentLink-hotfix-0.3.13\source')
from app.protocol import RpcClient
from app.review_workflow import scoped_settings
root=Path(__file__).parent
for n in ('source','scratch'):(root/n).mkdir(exist_ok=True)
results=[]
for name,exe in [('configured',r'C:\Users\infin\AppData\Local\OpenAI\Codex\bin\codex.exe'),('current',r'C:\Users\infin\AppData\Local\OpenAI\Codex\bin\7ac07f4ce733f89a\codex.exe')]:
 c=RpcClient([exe,'app-server','--listen','stdio://'],root/name)
 methods=[]; orig=c.call
 def call(method,params,**kw):
  methods.append(method)
  if method=='turn/start':raise AssertionError('No model calls')
  return orig(method,params,**kw)
 c.call=call
 row={'runtime':name,'path':exe}
 try:
  c.start()
  c.call('config/read',{'includeLayers':False,'cwd':str(root/'scratch')},timeout=30)
  row['config_read']='PASS'
  for phase in ('implement','review','summary'):
   settings=scoped_settings({'model':'gpt-6-astra'},root/'source',root/'scratch',phase,[])
   c.new_thread(settings,str(root/'scratch'),'Local permission preflight only. No model turn will be sent.')
   row[phase]='thread_created_permission_confirmed'
 except Exception as ex:row['error']=str(ex)
 finally:c.close()
 row['model_requests']=methods.count('turn/start');results.append(row)
 print(json.dumps(row,ensure_ascii=False),flush=True)
(root/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
