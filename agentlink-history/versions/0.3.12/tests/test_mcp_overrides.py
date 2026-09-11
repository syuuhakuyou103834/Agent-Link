import copy
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.protocol import RpcClient
from app.review_workflow import scoped_settings

class OverrideTests(unittest.TestCase):
 def run_case(self, config):
  original=copy.deepcopy(config);sent=[]
  c=RpcClient([],ROOT/'test-output')
  settings=scoped_settings({'model':'mock'},ROOT/'example-source',ROOT/'example-tests','review',[])
  def call(method,params,**kwargs):
   sent.append((method,params))
   if method=='config/read':return {'config':config}
   if method=='thread/start':return {'thread':{'id':'fixture'},'activePermissionProfile':{'id':params['permissions']},'approvalPolicy':'never','approvalsReviewer':'user','cwd':params['cwd']}
   raise AssertionError('No model request expected')
  c.call=call
  c.new_thread(settings,str(ROOT/'example-tests'),'test')
  self.assertEqual(config,original,'Do not mutate original configuration')
  return sent[-1][1]['config']
 def test_preserves_stdio_and_http_transport_and_disables_servers(self):
  config={'mcp_servers':{'node_repl':{'command':'node.exe','args':['server.js'],'enabled':True},'http-mcp':{'url':'https://example.invalid/mcp','enabled':True}},'plugins':{}}
  result=self.run_case(config)
  self.assertEqual(result['mcp_servers']['node_repl'],{'command':'node.exe','args':['server.js'],'enabled':False})
  self.assertEqual(result['mcp_servers']['http-mcp']['url'],'https://example.invalid/mcp')
  self.assertFalse(result['mcp_servers']['http-mcp']['enabled'])
  self.assertFalse(any(k.startswith('mcp_servers.') for k in result))
 def test_literal_names_and_plugin_settings_survive(self):
  name='with.dot-and-quote"';plugin='tools.v2@marketplace'
  result=self.run_case({'mcp_servers':{name:{'command':'mock'}},'plugins':{plugin:{'enabled':True,'config':{'option':'retained'}}}})
  self.assertEqual(set(result['mcp_servers']),{name})
  self.assertFalse(result['mcp_servers'][name]['enabled'])
  self.assertEqual(result['plugins'][plugin],{'enabled':False,'config':{'option':'retained'}})
 def test_malformed_entry_rejected_before_thread_or_model(self):
  c=RpcClient([],ROOT);calls=[]
  def call(method,params,**kwargs):
   calls.append(method);return {'config':{'mcp_servers':{'invalid':None}}}
  c.call=call
  settings=scoped_settings({'model':'mock'},ROOT/'example-source',ROOT/'example-tests','review',[])
  with self.assertRaisesRegex(RuntimeError,'配置格式无效'):c.new_thread(settings,str(ROOT/'example-tests'),'test')
  self.assertEqual(calls,['config/read'])

if __name__=='__main__':unittest.main(verbosity=2)
