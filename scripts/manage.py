"""Change display branding without changing URLs, saved record IDs, or archives."""
import argparse
from core import ROOT, plain, read_json, run_lock, write_json

def rename(name,english=None,tagline=None):
    if not isinstance(name,str) or not 1<=len(name.strip())<=24 or plain(name)!=name.strip():raise ValueError('站名需为 1—24 字的纯文本')
    config=read_json(ROOT/'config/site.json')
    config['name']=name.strip()
    if english is not None:
        if not 1<=len(english.strip())<=50 or plain(english)!=english.strip():raise ValueError('英文名需为 1—50 字的纯文本')
        config['english_name']=english.strip()
    if tagline is not None:
        if not 1<=len(tagline.strip())<=100 or plain(tagline)!=tagline.strip():raise ValueError('简介需为纯文本，最多 100 字')
        config['tagline']=tagline.strip()
    with run_lock():write_json(ROOT/'config/site.json',config)
    print('显示名称已修改。运行 build / publish 后页面、详情、RSS、日历和页签将同步更新；网址保持不变。')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True)
    cmd=sub.add_parser('rename');cmd.add_argument('--name',required=True);cmd.add_argument('--english');cmd.add_argument('--tagline')
    args=parser.parse_args();rename(args.name,args.english,args.tagline)
