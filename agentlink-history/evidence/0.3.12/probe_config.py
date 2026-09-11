import sys,json,copy
from pathlib import Path
root=Path(__file__).parent
sys.path.insert(0,str(root/'source'))
from app.protocol import RpcClient
from app.review_workflow import scoped_settings
from app.storage import find_codex
for n in ('probe-source','probe-tests'):(root/n).mkdir(exist_ok=True)
results=[]
for mode in ('quoted_keys_0311','nested_objects_0312'):
 c=RpcClient([find_codex(),'app-server','--listen','stdio://'],root/'evidence'/mode)
 methods=[]
 original=c.call
 def call(method,params,**kw):
  methods.append(method)
  if method=='turn/start':raise AssertionError('No model requests allowed')
  result=original(method,params,**kw)
  if method=='config/read':
   result=copy.deepcopy(result)
   entries=result['config'].setdefault('mcp_servers',{})
   entries.setdefault('node_repl',{'command':sys.executable,'args':['-c','raise SystemExit(0)'],'enabled':False})
  return result
 c.call=call
 try:
  c.start()
  settings=scoped_settings({'model':'gpt-6-astra'},root/'probe-source',root/'probe-tests','review',[])
  if mode=='quoted_keys_0311':
   basecall=c.call
   def oldcall(method,params,**kw):
    if method=='thread/start':
     params=copy.deepcopy(params)
     for table in ('mcp_servers','plugins'):
      for key in params['config'].get(table,{}):
       params['config'][table+'.'+json.dumps(key)+'.enabled']=False
    return basecall(method,params,**kw)
   c.call=oldcall
  c.new_thread(settings,str(root/'probe-tests'),'Configuration parser check. No turn will be sent.')
  result={'mode':mode,'status':'thread_created'}
 except Exception as e:
  result={'mode':mode,'status':'blocked','error':str(e)}
 finally:c.close()
 result['model_requests']=methods.count('turn/start')
 results.append(result)
(root/'evidence'/'real-config-probe.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(results,ensure_ascii=False,indent=2))
