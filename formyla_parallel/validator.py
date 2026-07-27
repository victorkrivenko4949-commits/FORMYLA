
import json, re, argparse
from pathlib import Path

def issues(t):
    out=[]
    for f in ['id','grade','method_code','difficulty','task_text','correct_answer','solution','theme','subtopic','method']:
        if not t.get(f) and t.get(f)!=0: out.append('missing_'+f)
    s=' '.join(str(t.get(f,'')) for f in ['task_text','correct_answer','solution'])
    if s.count('$')%2: out.append('odd_dollar')
    bal=0
    for ch in s:
        if ch=='{': bal+=1
        elif ch=='}': bal-=1
        if bal<0: out.append('brace_order'); break
    if bal: out.append('brace_balance')
    if t.get('difficulty',0)>=7 and len(str(t.get('solution','')))<260: out.append('short_solution_high_level')
    return out

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('json_file'); args=ap.parse_args()
    data=json.loads(Path(args.json_file).read_text(encoding='utf-8'))
    report=[{'id':t.get('id'),'issues':issues(t)} for t in data if issues(t)]
    print(json.dumps({'total':len(data),'bad':len(report),'report':report[:1000]},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
