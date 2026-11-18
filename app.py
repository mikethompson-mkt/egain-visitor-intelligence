"""eGain Visitor Intelligence — sales-facing prototype."""
import sqlite3
import gzip
import shutil
import tempfile
from pathlib import Path
import pandas as pd
import streamlit as st

# Conservative, explainable network-owner qualification. Not a visitor identity match.
CLOUD_TERMS = (
 'amazon.com, inc.', 'amazon web services', 'google llc', 'microsoft corporation',
 'cloudflare', 'ovh', 'hivelocity', 'hosting technology', 'serverchoice',
 'servers tech', 'datacamp limited', 'ip volume', 'webair internet',
 'digitalocean', 'hetzner', 'linode', 'akamai', 'vultr', 'leaseweb',
 'contabo', 'oracle cloud', 'alibaba cloud', 'choopa', 'scaleway',
)
ISP_TERMS = (
 'comcast', 'versatel', 'pccw', 'transitx', 'telecom', 'telecommunications',
 'broadband', 'internet service', 'cable communications', 'netzdienste',
 'telefonica', 'verizon', 'at&t', 't-mobile', 'vodafone', 'bt group',
 'orange s.a.', 'deutsche telekom', 'telstra', 'centurylink', 'lumen technologies',
 'network transit', 'carrier', 'isp',
)

def qualify_network(owner):
    name = str(owner).strip().casefold()
    if not name or name in ('unknown', 'n/a', 'none', 'nan'):
        return 'Unclassified'
    if any(term in name for term in CLOUD_TERMS):
        return 'Cloud / Hosting'
    if any(term in name for term in ISP_TERMS):
        return 'ISP / Transit'
    return 'Organization - Review'

st.set_page_config(page_title='eGain Visitor Intelligence',page_icon='🔎',layout='wide')
COMPRESSED=Path(__file__).parent/'data'/'visitors.sqlite.gz'
DB=Path(tempfile.gettempdir())/'egain_visitors_v1.sqlite'
if not DB.exists() and COMPRESSED.exists():
 with gzip.open(COMPRESSED,'rb') as src, open(DB,'wb') as dst:shutil.copyfileobj(src,dst)
st.markdown('''<style>
.block-container{padding-top:1.7rem;max-width:1450px}h1{letter-spacing:-.035em}div[data-testid="stMetric"]{border:1px solid #e0e6ef;border-radius:12px;padding:14px 18px;background:#f8fafc}div[data-testid="stMetricLabel"]{font-weight:600}
</style>''',unsafe_allow_html=True)
@st.cache_resource
def connection():
 return sqlite3.connect(f'file:{DB}?mode=ro',uri=True,check_same_thread=False)
@st.cache_data(ttl=3600)
def read(sql,params=()):return pd.read_sql_query(sql,connection(),params=params)

st.title('eGain Visitor Intelligence')
st.caption('Evidence-based website engagement signals for sales teams  ·  February 2025 sample')
if not DB.exists():
 st.error('Prepared database missing. Run build_data.py on the supplied workbook.');st.stop()

with st.sidebar:
 st.header('Explore activity')
 query=st.text_input('IP or page contains',placeholder='e.g. 193.186 or knowledge')
 tier=st.multiselect('Intent tier',['High','Medium','Low'],default=['High','Medium'])
 min_days=st.slider('Minimum active days',0,15,0)
 include_bots=st.checkbox('Include likely automated-heavy IPs',False)
 st.divider()
 st.info('Company names and individual contacts are **not present** in the logs. IP addresses are not verified account identities.')

meta=dict(connection().execute('SELECT k,v FROM metadata').fetchall())
where=['v.active_days>=?'];args=[min_days]
if tier:
 where.append('v.intent IN ('+','.join('?'*len(tier))+')');args.extend(tier)
if not include_bots:where.append('v.bot_requests * 5 <= v.requests * 4')
if query.strip():
 where.append('(v.ip LIKE ? OR EXISTS (SELECT 1 FROM activity a WHERE a.ip=v.ip AND a.path LIKE ?))')
 args.extend(['%'+query.strip()+'%']*2)
clause=' AND '.join(where)
summary=read('SELECT COUNT(*) accounts, COALESCE(SUM(relevant),0) relevant, COALESCE(SUM(CASE WHEN intent="High" THEN 1 ELSE 0 END),0) high FROM visitors v WHERE '+clause,tuple(args)).iloc[0]
a,b,c,d=st.columns(4)
a.metric('Raw web requests',f'{int(meta.get("records",0)):,}')
b.metric('Distinct IPs',f'{int(meta.get("ip_count",0)):,}')
c.metric('Matching IPs',f'{int(summary.accounts):,}')
d.metric('High-intent matches',f'{int(summary.high):,}')

explore, accounts, trends, method=st.tabs(['Account / IP explorer','Company intelligence','Traffic & interest','Scoring & data quality'])
with explore:
 st.subheader('Prioritized IP activity')
 st.caption('An IP is a network identifier, not necessarily a company, person, or unique visitor. Rankings reflect observed page requests only.')
 limit=st.selectbox('Results per page',[25,50,100,250],index=1)
 page=st.number_input('Page',min_value=1,max_value=max(1,(int(summary.accounts)+limit-1)//limit),value=1)
 data=read('SELECT v.ip AS "IP address",v.intent AS "Intent",v.score AS "Score / 100",v.relevant AS "Relevant requests",v.active_days AS "Active days",v.topics AS "Topics",v.requests AS "All requests",v.bot_requests AS "Bot-flagged",v.last_seen AS "Last seen (UTC)",v.top_path AS "Top relevant page" FROM visitors v WHERE '+clause+' ORDER BY v.score DESC,v.relevant DESC LIMIT ? OFFSET ?',tuple(args+[limit,(page-1)*limit]))
 st.dataframe(data,use_container_width=True,hide_index=True,height=440)
 if not data.empty:
  selected=st.selectbox('Inspect IP evidence',data['IP address'].tolist(),key='selected')
  v=read('SELECT * FROM visitors WHERE ip=?',(selected,)).iloc[0]
  l,r=st.columns([2,1])
  with l:
   st.markdown(f'#### {selected}  ·  {v["intent"]} intent')
   st.write(v['reasons'])
   st.markdown('**Suggested sales action**')
   if v['score']>=65:st.success('Investigate whether this IP belongs to a target account using an approved enrichment source; then review topic interests before outreach.')
   elif v['score']>=30:st.info('Monitor additional relevant activity and check CRM for an existing account match.')
   else:st.info('Low-confidence signal. Do not prioritize outreach based on this activity alone.')
  with r:
   st.metric('Engagement score',f'{int(v["score"])}/100')
   st.metric('Active days',int(v['active_days']))
  history=read('SELECT ts AS "UTC time",path AS "Page URL",topic AS "Topic",referrer AS "Referrer",CASE WHEN bot=1 THEN "Flagged" ELSE "No explicit bot flag" END AS "Automation flag" FROM activity WHERE ip=? ORDER BY ts DESC LIMIT 300',(selected,))
  topics=read('SELECT topic AS "Topic",COUNT(*) AS "Requests" FROM activity WHERE ip=? AND bot=0 AND weight>0 GROUP BY topic ORDER BY COUNT(*) DESC',(selected,))
  col1,col2=st.columns([1,2])
  with col1:
   st.markdown('**Observed topics**')
   if len(topics):st.bar_chart(topics.set_index('Topic'))
   else:st.write('No qualifying product activity')
  with col2:
   st.markdown('**Recent request evidence**')
   st.dataframe(history,hide_index=True,use_container_width=True,height=300)
  st.download_button('Download selected IP activity',history.to_csv(index=False).encode(),file_name='egain_ip_activity.csv',mime='text/csv')
with accounts:
 st.subheader('Network & company intelligence (optional enrichment)')
 st.caption('IPinfo Lite returns ASN network owners, not verified website visitors. Network type is a heuristic classification and is not evidence of company identity or buying intent.')
 st.info('Upload a CSV containing: ip, company, company_domain, provider, confidence, lookup_date. The dashboard automatically loads a sample of 100 IPinfo-enriched IP addresses. Uploading a CSV is optional and temporarily replaces the sample for your session. A CSV template is included in the project folder.')
 uploaded=st.file_uploader('Upload company enrichment CSV',type=['csv'],key='company_upload')
 if uploaded is None and not Path('egain_ipinfo_network_enrichment.csv').exists():
  st.warning('No company enrichment loaded. Company names are unavailable in the original data; the IP explorer and other analytics remain fully functional.')
 else:
  try:
   source=uploaded if uploaded is not None else 'egain_ipinfo_network_enrichment.csv'
   enrichment=pd.read_csv(source,dtype=str).fillna('')
   required={'ip','company','company_domain','provider','confidence','lookup_date'}
   if not required.issubset(enrichment.columns):
    st.error('Missing CSV columns: '+', '.join(sorted(required-set(enrichment.columns))))
   else:
    enrichment=enrichment[list(sorted(required))].copy()
    enrichment=enrichment[(enrichment.ip.str.strip()!='') & (enrichment.company.str.strip()!='')]
    enrichment=enrichment.drop_duplicates(subset=['ip'],keep='last')
    if enrichment.empty:
     st.warning('No populated company matches were provided.')
    else:
     ip_list=enrichment.ip.tolist()
     activity_rows=[]
     # Query in batches to respect SQLite parameter limits.
     for start in range(0,len(ip_list),500):
      chunk=ip_list[start:start+500]
      placeholders=','.join('?' for _ in chunk)
      activity_rows.append(read('SELECT ip,score,intent,relevant,active_days,requests,bot_requests,last_seen FROM visitors WHERE ip IN ('+placeholders+')',tuple(chunk)))
     matches=pd.concat(activity_rows,ignore_index=True) if activity_rows else pd.DataFrame()
     if matches.empty:
      st.warning('None of the uploaded IPs matched the supplied website logs.')
     else:
      merged=matches.merge(enrichment,on='ip',how='inner')
      merged['network_type']=merged['company'].map(qualify_network)
      st.markdown('**Network qualification**')
      totals=merged.groupby('network_type').ip.nunique()
      qcols=st.columns(4)
      for col, label in zip(qcols, ['Cloud / Hosting', 'ISP / Transit', 'Organization - Review', 'Unclassified']):
       col.metric(label, int(totals.get(label, 0)))
      st.caption('Counts are enriched IP addresses, not unique visitors or verified accounts. Classification uses network-owner names and may be imperfect.')
      options=['Cloud / Hosting', 'ISP / Transit', 'Organization - Review', 'Unclassified']
      chosen=st.multiselect('Filter by network type', options, default=options, key='network_filter')
      merged=merged[merged.network_type.isin(chosen)]
      company_query=st.text_input('Search company name or domain',placeholder='e.g. example.com',key='company_query').strip()
      if company_query:
       merged=merged[merged.company.str.contains(company_query,case=False,regex=False) | merged.company_domain.str.contains(company_query,case=False,regex=False)]
      if merged.empty:
       st.info('No matching company associations for this search.')
      else:
       account_summary=merged.groupby(['company','company_domain','network_type'],dropna=False).agg(associated_ips=('ip','nunique'),highest_score=('score','max'),relevant_requests=('relevant','sum'),latest_activity=('last_seen','max')).reset_index().sort_values(['highest_score','relevant_requests'],ascending=False)
       st.dataframe(account_summary,hide_index=True,use_container_width=True)
       selected_company=st.selectbox('Inspect company association',account_summary.company.drop_duplicates().tolist())
       selected_rows=merged[merged.company==selected_company].sort_values('score',ascending=False)
       st.markdown('**Associated IPs and provenance**')
       st.dataframe(selected_rows[['ip','network_type','score','intent','relevant','active_days','company_domain','provider','confidence','lookup_date']],hide_index=True,use_container_width=True)
       company_ips=selected_rows.ip.tolist()
       topic_rows=[]
       for start in range(0,len(company_ips),500):
        chunk=company_ips[start:start+500]
        placeholders=','.join('?' for _ in chunk)
        topic_rows.append(read('SELECT topic,COUNT(*) AS requests FROM activity WHERE ip IN ('+placeholders+') AND bot=0 AND weight>0 GROUP BY topic',tuple(chunk)))
       if topic_rows:
        topic_mix=pd.concat(topic_rows).groupby('topic',as_index=False).requests.sum().sort_values('requests',ascending=False)
        st.markdown('**Observed product interests across associated IPs**')
        st.bar_chart(topic_mix.set_index('topic'))
        leading_topic=topic_mix.iloc[0].topic if not topic_mix.empty else None
       else:
        leading_topic=None
       st.markdown('**Suggested next step**')
       network_type=selected_rows.iloc[0]['network_type']
       if network_type=='Cloud / Hosting':
        st.warning('Infrastructure-associated IPs: do not treat the network owner as a prospect. Review request patterns and seek independently verified account attribution before outreach.')
       elif network_type=='ISP / Transit':
        st.warning('ISP/transit network: the provider may serve many unrelated customers. Do not attribute this traffic to the provider as a sales lead.')
       elif network_type=='Unclassified':
        st.info('Network owner is unknown. Seek additional evidence before considering account-level outreach.')
       elif leading_topic:
        st.info(f'Review the existing CRM account record and validate the enrichment source before outreach. If the association checks out, consider a conversation about {leading_topic.lower()}, based on observed page requests.')
       else:
        st.info('Validate the IP-to-company association and review the account in CRM before any outreach.')
       st.caption('Network type is a heuristic based on ASN owner names; Organization - Review is NOT a verified prospect. These are historical February 2025 requests. IP associations may have changed since collection. Multiple people or devices can share one IP.')
       st.download_button('Export matched account evidence',selected_rows.to_csv(index=False).encode('utf-8'),file_name='egain_company_evidence.csv',mime='text/csv')
  except Exception as exc:
   st.error(f'Could not read enrichment CSV: {exc}')
with trends:
 st.subheader('Traffic patterns')
 daily=read('SELECT day AS date,COUNT(*) AS requests,SUM(CASE WHEN bot=1 THEN 1 ELSE 0 END) AS flagged_bot_requests, SUM(CASE WHEN bot=0 AND weight>0 THEN 1 ELSE 0 END) AS relevant_requests FROM activity GROUP BY day ORDER BY day')
 st.line_chart(daily.set_index('date'))
 left,right=st.columns(2)
 with left:
  st.markdown('**Topic mix (non-flagged requests)**')
  topics=read('SELECT topic,COUNT(*) AS requests FROM activity WHERE bot=0 AND weight>0 GROUP BY topic ORDER BY requests DESC')
  st.bar_chart(topics.set_index('topic'))
 with right:
  st.markdown('**Most requested relevant pages**')
  pages=read('SELECT path,COUNT(*) AS requests FROM activity WHERE bot=0 AND weight>0 GROUP BY path ORDER BY requests DESC LIMIT 15')
  st.dataframe(pages,hide_index=True,use_container_width=True,height=390)
with method:
 st.subheader('Transparent intent model')
 st.markdown('''The prototype scores **observed engagement**, not purchase probability. For each IP:

- **Breadth:** up to 5 relevant content topics (8 points per topic).
- **Repeat engagement:** up to 6 distinct days with relevant activity (6 points per day).
- **Depth:** up to 12 relevant page requests (3 points per request).
- **Page relevance:** weighted product-topic requests, capped at 40 weighted points (0.35 points each).
- **Bot safeguard:** if more than 80% of requests are explicitly flagged as automated, cap the score at 15.

Scores are capped at 100. **High ≥65; Medium 30–64; Low <30.** Repeated requests, IP sharing, VPNs, NAT, proxies, crawlers, and missing session identifiers limit confidence. Bot detection is heuristic and cannot guarantee human traffic. The Domain column in the workbook is the requested eGain website host, **not a visitor's employer**.

**No individual identity or corporate affiliation is asserted.** Optional enrichment should use permissioned IP-to-company services, retain source/confidence and lookup dates, and treat ISP/cloud-provider matches as unqualified. This sample contains historical February 2025 data, not live intent.''')
 st.markdown('**Network qualification:** IPinfo ASN owners are classified with a conservative, editable name-based heuristic into Cloud / Hosting, ISP / Transit, Organization - Review, or Unclassified. The classification is not verified company identity, and a network owner may host unrelated customers.')
 st.markdown('**Reproducibility:** The source workbook is processed locally into a read-only SQLite database by `build_data.py`. The published demo needs the SQLite file, not the raw workbook.')
st.divider()
st.caption('Prototype for eGain sales-engineering evaluation · Data-derived observations only · Not a contact-identification system')
