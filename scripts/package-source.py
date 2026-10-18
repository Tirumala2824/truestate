"""Create a clean, portable source download; no credentials, runtime state, or build output."""
from pathlib import Path
import zipfile
import os
root=Path(__file__).resolve().parents[1]
out=root/'public/downloads/truestate-source.zip';out.parent.mkdir(parents=True,exist_ok=True)
blocked={'node_modules','.git','.sites-runtime','.wrangler','.next','.vinext','.pytest_cache','__pycache__','dist','downloads','.private-evidence','vendor'}
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    paths=[]
    for directory, dirs, files in os.walk(root):
        dirs[:]=[d for d in dirs if d not in blocked and not (Path(directory)==root/'frontend' and d=='public')]
        paths.extend(Path(directory)/name for name in files)
    for p in sorted(paths):
        rel=p.relative_to(root)
        if not p.is_file() or any(x in blocked for x in rel.parts):continue
        if p.name.startswith('.env') and p.name!='.env.example':continue
        if p.suffix in {'.db','.pyc','.tsbuildinfo'} or p.name=='next-env.d.ts':continue
        # Site identity belongs to the hosted project; a portable source copy starts unregistered.
        if str(rel)=='.openai/hosting.json':
            z.writestr('truestate/.openai/hosting.json','{"d1":"DB","r2":"BUCKET"}\n');continue
        z.write(p,'truestate/'+str(rel))
print(f'Source package: {out.stat().st_size:,} bytes')
