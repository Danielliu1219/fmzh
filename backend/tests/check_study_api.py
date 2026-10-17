from datetime import date, timedelta
import json
import uuid
import httpx

# Run only against an isolated test database/server. Creates synthetic test accounts.
import argparse
parser=argparse.ArgumentParser()
parser.add_argument('--base-url', required=True)
args=parser.parse_args()
client=httpx.Client(base_url=args.base_url.rstrip('/')+'/api',timeout=60)
count=0
def check(name, ok):
    global count
    assert ok,name
    count+=1
    print('[PASS]',name)
def request(method,path,headers,**kwargs):
    r=client.request(method,path,headers=headers,**kwargs)
    assert r.status_code==200,(path,r.status_code,r.text)
    return r.json()
def account():
    data=request('POST','/auth/register',{},json={'username':'ws_'+uuid.uuid4().hex[:10],'password':'StudyQA123','student_no':'20240001'})
    return {'Authorization':'Bearer '+data['access_token']}
h=account();today=date.today().isoformat()
check('daily budget defaults to 240 shared minutes',request('GET','/study/settings',h)['daily_minutes']==240)
request('PUT','/study/settings',h,json={'daily_minutes':240})
check('daily focus goal follows shared budget',request('GET','/focus/today',h)['goal_minutes']==240)
exam_ids=[]
for i,subject in enumerate(['高等数学','大学英语','数据结构']):
    exam=request('POST','/exams',h,json={'subject':subject,'exam_date':(date.today()+timedelta(days=10+i*2)).isoformat()})
    exam_ids.append(exam['id'])
    request('POST','/materials',h,data={'exam_id':exam['id'],'title':subject+'资料','source_type':'老师重点'},files={'file':('study.txt','极限和导数。二叉树遍历。英语阅读与词汇。'.encode(),'text/plain')})
    request('POST','/ai/profile',h,json={'exam_id':exam['id'],'raw_text':'我的目标是保及格，我基础差，还有5天考试，每天能学4小时'})
    result=request('POST','/ai/analyze',h,json={'exam_id':exam['id']})
    check(subject+' analysis schedules against all courses',result['scheduling']['applied'])
tasks=request('GET','/tasks',h)
totals={}
for task in tasks:totals[task['plan_date']]=totals.get(task['plan_date'],0)+task['estimated_minutes']
check('all generated dates respect combined daily capacity',max(totals.values())<=240)
check('today includes more than one course',len({t['exam_id'] for t in tasks if t['plan_date']==today})>1)
done_id=tasks[0]['id'];request('POST',f'/tasks/{done_id}/checkin',h)
manual=request('POST','/tasks',h,json={'exam_id':exam_ids[0],'title':'手动保留的复盘','plan_date':today,'estimated_minutes':10,'priority':2})
before=request('GET','/tasks',h)
plan=request('GET','/study/plan/preview',h)
check('preview has no task mutations',request('GET','/tasks',h)==before)
request('PUT',f"/tasks/{manual['id']}",h,json={'title':'已修改的手动复盘'})
check('stale preview is rejected',client.post('/study/plan/confirm',headers=h,json={'fingerprint':plan['fingerprint']}).status_code==409)
plan=request('GET','/study/plan/preview',h)
request('POST','/study/plan/confirm',h,json={'fingerprint':plan['fingerprint']})
after=request('GET','/tasks',h)
check('manual task identity and date retained',any(t['id']==manual['id'] and t['plan_date']==today and t['title']=='已修改的手动复盘' for t in after))
check('completed record retained',any(t['id']==done_id and t['is_done'] for t in after))
check('total task minutes conserved',sum(t['estimated_minutes'] for t in before)==sum(t['estimated_minutes'] for t in after))
peer=account();check('other user cannot see schedule',not request('GET','/study/plan/preview',peer)['assignments'])
check('other user cannot confirm this plan',client.post('/study/plan/confirm',headers=peer,json={'fingerprint':plan['fingerprint']}).status_code==409)
request('PUT','/study/settings',h,json={'daily_minutes':30})
before=request('GET','/tasks',h)
failed=request('POST','/ai/analyze',h,json={'exam_id':exam_ids[0]})
check('infeasible generation is explicit',not failed['scheduling']['applied'] and bool(failed['scheduling']['conflicts']))
check('infeasible generation keeps prior tasks exactly',before==request('GET','/tasks',h))
check('invalid relief option rejected',client.get('/features/relief',headers=h,params={'option':'invalid'}).status_code==422)
request('PUT','/study/settings',h,json={'daily_minutes':240})
relief_user=account()
request('PUT','/study/settings',relief_user,json={'daily_minutes':180})
exam=request('POST','/exams',relief_user,json={'subject':'减负边界测试','exam_date':(date.today()+timedelta(days=3)).isoformat()})
request('POST','/tasks',relief_user,json={'exam_id':exam['id'],'title':'超长任务','plan_date':today,'estimated_minutes':360,'priority':1})
before=request('GET','/tasks',relief_user)
relief=request('GET','/features/relief',relief_user)
check('relief uses shared daily budget',relief['daily_hours']==3 and relief['today_capacity']==90)
check('oversized relief task reports conflict',bool(relief['conflicts']) and not relief['moves'])
check('infeasible relief cannot partially apply',client.post('/features/relief/apply',headers=relief_user,json={'option':'lighten'}).status_code==409)
check('failed relief preserves all tasks',request('GET','/tasks',relief_user)==before)
print('TOTAL',count)
