import os,sys,json
from pathlib import Path
root=Path(__file__).parent
sys.path.insert(0,r"C:\AgentLink-GUI\dist\AgentLink-GUI-0.3.14")
from app.protocol import RpcClient
from app.review_workflow import scoped_settings
# Emulate an ordinary desktop launch without the Codex host's inherited PATH.
os.environ['PATH']=str(Path(os.environ['WINDIR'])/'System32')
for n in ('probe-source','probe-scratch'):(root/n).mkdir(exist_ok=True)
c=RpcClient([str(root/'runtime-fixture'/'codex.exe'),'app-server','--listen','stdio://'],root/('packaged-rpc-'+sys.argv[1]))
methods=[];orig=c.call

def call(method,params,**kwargs):
 methods.append(method)
 if method=='turn/start':raise AssertionError('No model calls')
 return orig(method,params,**kwargs)
c.call=call
result={'mode':sys.argv[1]}
try:
 c.start()
 for phase in ('implement','review','summary'):
  settings=scoped_settings({'model':'gpt-6-astra'},root/'probe-source',root/'probe-scratch',phase,[])
  c.new_thread(settings,str(root/'probe-scratch'),'Preflight only. No model turns.')
  result[phase]='permission_confirmed'
except Exception as e:result['error']=str(e)
finally:c.close()
result['model_requests']=methods.count('turn/start')
(root/'evidence'/('packaged-'+sys.argv[1]+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))