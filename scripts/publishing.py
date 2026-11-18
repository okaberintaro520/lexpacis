"""Explicit, configured publishing only. Default is a local ZIP, without credentials."""
import hashlib
import json
import shutil
import subprocess
import zipfile
from core import ROOT, log, now, read_json, run_lock, write_json

def verify_release(folder=None):
    folder=folder or ROOT/'dist'
    manifest=read_json(folder/'release.json')
    if not manifest: raise ValueError('发布前请先运行 build；缺少 release.json')
    actual={str(p.relative_to(folder)).replace('\\','/') for p in folder.rglob('*') if p.is_file()}
    if actual!=set(manifest['files'])|{'release.json'}:
        raise ValueError('发布目录包含未登记文件或缺少文件，请重新 build')
    for name,expected in manifest['files'].items():
        path=(folder/name).resolve()
        if not path.is_relative_to(folder.resolve()) or not path.is_file(): raise ValueError('发布文件缺失或越界：'+name)
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected: raise ValueError('发布文件发生变化，请重新 build：'+name)
    return manifest

def publish(config):
    with run_lock():
        manifest=verify_release()
        deploy=config.get('deploy',{}); provider=deploy.get('provider','none')
        if provider=='none':
            output=ROOT/'artifacts'; output.mkdir(exist_ok=True)
            path=output/'lexatlas-web.zip'
            with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as archive:
                for item in (ROOT/'dist').rglob('*'):
                    if item.is_file(): archive.write(item,item.relative_to(ROOT/'dist'))
            print('已生成可部署静态包：'+str(path)+'；尚未上传至托管服务。')
            log('package_created',path=str(path)); return
        if provider!='cloudflare': raise ValueError('当前发布器只支持 none / cloudflare')
        project=deploy.get('cloudflare_project','')
        if not project or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in project):
            raise ValueError('请先在 config/site.json 填写已创建的 Cloudflare Pages 项目名')
        npx=shutil.which('npx.cmd') or shutil.which('npx')
        if not npx: raise ValueError('Cloudflare 自动发布需要安装 Node.js 与 Wrangler')
        # --no-install prevents unattended downloading; install Wrangler once during setup.
        result=subprocess.run([npx,'--no-install','wrangler','pages','deploy',str(ROOT/'dist'),'--project-name',project],cwd=ROOT,timeout=300,check=False)
        if result.returncode: raise RuntimeError('Cloudflare 发布失败；保留本地发布包，未记录为成功')
        write_json(ROOT/'runtime'/'last-deployment.json',{'provider':provider,'project':project,'at':now(),'release_built_at':manifest['built_at']})
        log('published',provider=provider,project=project)

def rollback():
    with run_lock():
        previous=ROOT/'dist.previous'; current=ROOT/'dist'; temporary=ROOT/'.dist-stage-rollback'
        if not previous.exists(): raise ValueError('尚无可回滚版本')
        if temporary.exists(): raise ValueError('回滚暂存目录已存在；请先检查未完成任务')
        verify_release(previous)
        if current.exists(): current.rename(temporary)
        try:
            previous.rename(current)
            if temporary.exists(): temporary.rename(previous)
        except Exception:
            if temporary.exists() and not current.exists(): temporary.rename(current)
            raise
        log('local_rollback'); print('已切换到上一版本；远程恢复需要再次运行 publish。')
