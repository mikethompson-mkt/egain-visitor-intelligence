"""Stream the provided Excel workbook into a compact SQLite dashboard database."""
import argparse, collections, datetime as dt, json, re, sqlite3, zipfile
from pathlib import Path
from lxml import etree as ET

NS='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
BOT=re.compile(r'bot|spider|crawler|headless|check_http|nagios|python-requests|curl/|wget|feedparser|scrapy|semrush|ahrefs|expanse|broken link|monitor|uptime|facebookexternalhit|meta-externalagent|httpclient|go-http-client|mozilla/5\.0/5\.0',re.I)
STATIC=re.compile(r'\.(?:css|js|png|jpg|jpeg|gif|svg|ico|woff2?|ttf|webp|xml|txt|map)(?:\?|$)',re.I)
TOPICS=[('AI & Automation',r'(^|/)(ai[-/]|generative-ai|genai|agentic|automation|chatbot|virtual-agent|ai-coach|ai-knowledge)'),('Knowledge Management',r'knowledge|\bkcs\b|knowledge-hub'),('Customer Service',r'customer-service|contact-center|customer-experience|service-cloud|agent-assist|customer-engagement'),('Integrations',r'integration|servicenow|salesforce|microsoft|api|connectors'),('Pricing & Evaluation',r'pricing|demo|request-a-demo|contact-us|trial|roi|case-stud|customer-stor|white.paper|datasheet')]
EXCLUDE=re.compile(r'^/(?:$|copyright/?$|privacy|terms|company/(?:investors|careers|news|events|about|leadership)|feed|wp-|robots|sitemap)',re.I)
def classify(path):
 p=path.lower().split('?')[0]
 if STATIC.search(p): return 'Asset',0
 for label,pattern in TOPICS:
  if re.search(pattern,p):return label, 5 if label=='Pricing & Evaluation' else 3
 if EXCLUDE.search(p):return 'Corporate / low intent',0
 return 'Other product content',1

def build(source,out):
 out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
 if out.exists():out.unlink()
 db=sqlite3.connect(out)
 db.executescript('''PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;
 CREATE TABLE activity(ip TEXT,day TEXT,ts TEXT,path TEXT,topic TEXT,weight INT,referrer TEXT,bot INT);
 CREATE TABLE visitors(ip TEXT PRIMARY KEY, requests INT, relevant INT, active_days INT, topics INT, score INT, bot_requests INT, last_seen TEXT, first_seen TEXT, intent TEXT, reasons TEXT, top_path TEXT);
 CREATE INDEX ix_activity_ip ON activity(ip);CREATE INDEX ix_activity_day ON activity(day);CREATE INDEX ix_visitors_score ON visitors(score DESC);''')
 with zipfile.ZipFile(source) as z:
  strings=[]
  for _,elem in ET.iterparse(z.open('xl/sharedStrings.xml'),events=('end',),tag=NS+'si'):
   strings.append(''.join(elem.itertext()));elem.clear()
  count=0; batch=[]
  for _,row in ET.iterparse(z.open('xl/worksheets/sheet1.xml'),events=('end',),tag=NS+'row'):
   if row.get('r')=='1':row.clear();continue
   values=['']*7
   for c in row:
    ref=c.get('r',''); col=re.match('[A-Z]+',ref)
    if not col:continue
    idx=ord(col.group())-65
    if idx>6:continue
    v=c.find(NS+'v')
    if v is not None and v.text is not None:values[idx]=strings[int(v.text)] if c.get('t')=='s' else v.text
   ip,domain,timestamp,method,path,ref,ua=values
   row.clear()
   if not ip or not timestamp:continue
   try:ts=dt.datetime.strptime(timestamp,'%d/%b/%Y:%H:%M:%S').isoformat(sep=' ')
   except ValueError:continue
   topic,weight=classify(path)
   isbot=int(bool(BOT.search(ua)) or method!='GET')
   batch.append((ip,ts[:10],ts,path,topic,weight,ref if ref!='-' else '',isbot));count+=1
   if len(batch)>=10000:
    if count%100000==0:print('rows',count,flush=True)
    db.executemany('INSERT INTO activity VALUES (?,?,?,?,?,?,?,?)',batch);batch=[]
  if batch:db.executemany('INSERT INTO activity VALUES (?,?,?,?,?,?,?,?)',batch)
 db.commit()
 # Aggregate by IP, counting distinct topics and dates. Score capped to avoid runaway traffic.
 q='''SELECT ip,COUNT(*),SUM(CASE WHEN bot=0 AND weight>0 THEN 1 ELSE 0 END),
 COUNT(DISTINCT CASE WHEN bot=0 AND weight>0 THEN day END),
 COUNT(DISTINCT CASE WHEN bot=0 AND weight>0 THEN topic END),SUM(bot),MIN(ts),MAX(ts),
 SUM(CASE WHEN bot=0 THEN weight ELSE 0 END)
 FROM activity GROUP BY ip'''
 rows=[]
 for ip,total,relevant,days,topics,bots,first,last,weighted in db.execute(q):
  relevant=relevant or 0;days=days or 0;topics=topics or 0;weighted=weighted or 0
  # No corporate identity inference: score indicates only on-site interest.
  score=min(100,int(min(relevant,12)*3+min(days,6)*6+min(topics,5)*8+min(weighted,40)*.35))
  if bots/max(total,1)>.8:score=min(score,15)
  level='High' if score>=65 else 'Medium' if score>=30 else 'Low'
  reasons=f'{relevant} relevant requests across {days} days and {topics} topics; {bots} explicitly flagged automated requests'
  rows.append((ip,total,relevant,days,topics,score,bots,last,first,level,reasons,''))
 db.executemany('INSERT INTO visitors VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',rows)
 # Top relevant page per IP
 db.execute('''UPDATE visitors SET top_path=COALESCE((SELECT path FROM activity a WHERE a.ip=visitors.ip AND a.bot=0 AND a.weight>0 GROUP BY path ORDER BY COUNT(*) DESC LIMIT 1),'') WHERE score>=65''')
 db.execute('CREATE TABLE metadata(k TEXT PRIMARY KEY,v TEXT)')
 db.executemany('INSERT INTO metadata VALUES (?,?)',[('records',str(count)),('ip_count',str(len(rows))),('source',Path(source).name),('methodology','Heuristic request-based interest score; IP is not an identified company or individual')]);db.commit();db.execute('VACUUM');db.close()
 print(f'Processed {count:,} requests and {len(rows):,} IPs -> {out} ({out.stat().st_size/1048576:.1f} MB)')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('--output',default='data/visitors.sqlite');a=p.parse_args();build(a.source,a.output)
