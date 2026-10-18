"""Build a reviewable source ZIP including .git history, excluding runtime state."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parent.parent


def build(output):
    output=Path(output).resolve()
    output.mkdir(parents=True,exist_ok=True)
    revision=subprocess.check_output(['git','rev-parse','--short','HEAD'],cwd=ROOT,text=True).strip()
    archive=output/('newagent-with-git-'+revision+'.zip')
    with tempfile.TemporaryDirectory(prefix='newagent-delivery-') as temporary:
        checkout=Path(temporary)/'newagent'
        subprocess.run(['git','clone','--no-local',str(ROOT),str(checkout)],check=True,capture_output=True)
        subprocess.run(['git','remote','set-url','origin','https://github.com/Qfish-417/newagent.git'],cwd=checkout,check=True)
        tracked=subprocess.check_output(['git','ls-files','-z'],cwd=checkout).decode().split('\0')
        forbidden=[p for p in tracked if p and (p=='.env' or p.startswith(('data/','.venv/')) or (p.startswith('.env.') and p!='.env.example') or p.endswith(('.db','.sqlite','.log')))]
        if forbidden:
            raise ValueError('Runtime/private files are tracked; packaging stopped')
        keys=[v.encode() for k,v in os.environ.items() if k in {'DEEPSEEK_API_KEY','OPENAI_API_KEY','SEARCH_API_KEY'} and len(v)>12]
        files=[p for p in checkout.rglob('*') if p.is_file()]
        for path in files:
            if any(key in path.read_bytes() for key in keys):
                raise ValueError('Actual local API key detected; packaging stopped')
        with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as bundle:
            for path in files:
                bundle.write(path,Path('newagent')/path.relative_to(checkout))
        with zipfile.ZipFile(archive) as bundle:
            names=bundle.namelist()
            assert 'newagent/.git/HEAD' in names and 'newagent/start.cmd' in names
            assert 'newagent/migrations/005_accounts.sql' in names
            assert bundle.testzip() is None
    return archive


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default=str(ROOT/'data/deliverables'))
    args=parser.parse_args()
    print(build(args.output))

if __name__=='__main__':
    main()
