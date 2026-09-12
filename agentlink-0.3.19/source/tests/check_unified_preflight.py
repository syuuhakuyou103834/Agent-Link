"""Installed Codex config/thread preflight only. Never sends turn/start."""
from dataclasses import asdict
import json,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.storage import Settings,default_data_dir
from app.protocol import RpcClient
from app.review_workflow import scoped_settings

def main():
    out=ROOT.parent/'evidence'/('real-preflight-'+uuid.uuid4().hex[:8]);out.mkdir(parents=True)
    source=out/'project';source.mkdir();scratch=out/'scratch';scratch.mkdir()
    evidence=out/'context-evidence';evidence.mkdir();(evidence/'index.json').write_text('{}',encoding='utf-8')
    cfg=Settings.load(default_data_dir())
    client=RpcClient([cfg.codex,'app-server','--listen','stdio://'],out/'private-rpc')
    results=[]
    try:
        client.start()
        for phase in ('summary','review','implement'):
            settings=scoped_settings(asdict(cfg),source,scratch,phase,[])
            settings['permission_profile']['filesystem'][str(evidence.resolve())]='read'
            try:
                thread=client.new_thread(settings,str(scratch),'AgentLink 0.3.18 permission preflight only. No model turn will be sent.')
                results.append(dict(phase=phase,thread_created=bool(thread),profile_confirmed=True))
            except Exception as e:
                results.append(dict(phase=phase,profile_confirmed=False,error=str(e)))
        result=dict(codex=cfg.codex,checks=results,model_turns=0,tool_execution_tested=False)
        (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False));print(out)
        return 0 if all(r['profile_confirmed'] for r in results) else 1
    finally:client.close()

if __name__=='__main__':sys.exit(main())
