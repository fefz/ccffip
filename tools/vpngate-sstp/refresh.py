#!/usr/bin/env python3
import re, math, ipaddress
from bs4 import BeautifulSoup
COUNTRIES=('JP','KR')
COUNTRY_NAMES={'Japan':'JP','Korea Republic of':'KR'}
def parse_rows(html):
    out=[]
    for tr in BeautifulSoup(html,'html.parser').select('tr'):
        cells=tr.find_all('td',recursive=False)
        if len(cells)!=10:continue
        values=[c.get_text(' ',strip=True) for c in cells]
        country=COUNTRY_NAMES.get(values[0]);host=re.search(r'SSTP Hostname\s*:\s*([A-Za-z0-9.-]+)(?::(\d+))?',values[7])
        sessions=re.search(r'([\d,]+) sessions',values[2]);speed=re.search(r'([\d,.]+) Mbps',values[3]);ping=re.search(r'Ping:\s*([\d,]+) ms',values[3])
        if not country or not host or not sessions or not speed:continue
        if not host[1].endswith('.opengw.net'):continue
        address=re.search(r'\b(?:\d{1,3}\.){3}\d{1,3}\b',values[1])
        n={'country':country,'host':host[1],'ip':address[0] if address else None,'port':int(host[2] or 443),'sessions':int(sessions[1].replace(',','')),'mbps':float(speed[1].replace(',','')),'ping_ms':int(ping[1].replace(',','')) if ping else 1000,'source_score':int(re.sub(r'\D','',values[9]) or 0)}
        if 1<=n['port']<=65535:out.append(n)
    return out

def quality(n):
    return math.log2(1+n['mbps'])/((1+n['sessions'])**0.35*(1+n['ping_ms']/100))

def parse_ip2location(html,ip):
    fields={}
    for row in BeautifulSoup(html,'html.parser').select('tr'):
        cells=row.find_all(['td','th'])
        if len(cells)==2:
            k,v=[x.get_text(' ',strip=True) for x in cells]
            if k not in fields:fields[k]=v
    country=re.search(r'\[([A-Z]{2})\]',fields.get('Country',''))
    if fields.get('IP Address')!=ip or not country or not fields.get('City') or fields.get('City')=='-':raise ValueError('IP2Location website has no valid city response')
    return {'success':True,'ip':ip,'country_code':country[1],'region':fields.get('Region',''),'city':fields['City'],'usage_type':fields.get('Usage Type',''),'isp':fields.get('ISP',''),'source':'ip2location.com/demo'}

def is_tokyo(n):
    geo=n.get('geo') or {}
    return n.get('country')=='JP' and geo.get('success') is True and geo.get('country_code')=='JP' and any(geo.get(k,'').strip().lower() in ('tokyo','tokyo-to','東京都','東京') for k in ('city','region'))

def crosscheck_home(n):
    geo=n.get('geo') or {};other=n.get('iplocate') or {};egress=n.get('egress') or {};country=n.get('country')
    ip=egress.get('egress_ip');privacy=other.get('privacy') or {}
    if not egress.get('ppp_connected') or not ip or geo.get('ip')!=ip or other.get('ip')!=ip:return False
    if geo.get('country_code')!=country or other.get('country_code')!=country:return False
    if privacy.get('is_hosting') is not False:return False
    if (other.get('company') or {}).get('type')!='isp' or (other.get('asn') or {}).get('type')!='isp':return False
    usage=geo.get('usage_type','').upper()
    if '(ISP)' not in usage or 'FIXED LINE' not in usage or '(DCH)' in usage or 'DATA CENTER' in usage:return False
    if country=='JP':
        if not is_tokyo(n):return False
        if not any(str(other.get(k,'')).lower() in ('tokyo','tokyo-to') for k in ('city','subdivision')):return False
    return country in COUNTRIES

def rank_nodes(nodes):
    def key(n):
        score=quality(n)*(1+n['probe_successes']/2)/(1+n['probe_ms']/1500)
        return (is_tokyo(n),score)
    return sorted([n for n in nodes if n.get('probe_ok')],key=key,reverse=True)

def parse_hk(text):
    lines=[x.strip() for x in text.splitlines() if x.strip() and not x.startswith('#')][:3]
    if len(lines)!=3:raise ValueError('GitHub hk.txt has fewer than three endpoints')
    result=[]
    for x in lines:
        endpoint=x.split('#',1)[0]
        host,port=endpoint.rsplit(':',1);ipaddress.ip_address(host.strip('[]'))
        if not port.isdigit() or not 1<=int(port)<=65535:raise ValueError('invalid HK port')
        result.append(endpoint)
    return result
def build_output(hk,selected):
    lines=[]
    for country in COUNTRIES:
        for i,n in enumerate(selected.get(country,[]),1):
            lines.append(f'{hk[(i-1)%3]}#Mine-{country}-家宽-{i}$sstp://vpn:vpn@{n["host"]}:{n["port"]}')
    return '\n'.join(lines)+'\n' if lines else ''

def validate_output(text,hk):
    lines=text.splitlines()
    if not lines:raise ValueError('no verified SSTP servers; preserve previous GitHub output')
    seen=set()
    for line in lines:
        m=re.fullmatch(r'([^#]+)#Mine-(JP|KR)-家宽-([1-3])\$sstp://vpn:vpn@([a-zA-Z0-9.-]+):(\d+)',line)
        if not m or m[1]!=hk[int(m[3])-1]:raise ValueError('invalid endpoint or numbering')
        key=(m[2],m[3])
        if key in seen:raise ValueError('duplicate country/number')
        seen.add(key)
    return len(lines)

