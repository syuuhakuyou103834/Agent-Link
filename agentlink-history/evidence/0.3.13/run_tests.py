from pathlib import Path
import subprocess,sys,json
root=Path(__file__).parent;out=root/'evidence';out.mkdir(exist_ok=True)
results=[]
for name in ('test_mcp_overrides.py','test_runtime_discovery.py','test_projects.py','test_code_workflow.py','test_authority.py','test_code_gui.py','test_gui.py'):
 p=subprocess.run([sys.executable,str(root/'source'/'tests'/name)],cwd=root/'source',capture_output=True)
 (out/(name+'.log')).write_bytes(p.stdout+p.stderr)
 results.append({'test':name,'exit_code':p.returncode})
 print(name,p.returncode,flush=True)
(out/'regression.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
assert all(r['exit_code']==0 for r in results)
