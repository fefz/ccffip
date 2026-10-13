#!/usr/bin/env python3
"""VPN Gate SSTP -> fefz/ccffip/data/sstp.txt; credentials use gh auth."""
import base64,json,subprocess,socket,ssl,time,uuid,fcntl,sys,threading,ipaddress
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
import requests
from bs4 import BeautifulSoup
from refresh import COUNTRIES,parse_rows,quality,parse_hk,build_output,validate_output,is_tokyo,rank_nodes,parse_ip2location,crosscheck_home
from egress import verify_egress
ROOT=Path(__file__).resolve().parent
REPO='fefz/ccffip';BRANCH='main';TARGET='data/sstp.txt'
FRONT_SOURCE='data/ip.txt'

def api(path,payload=None):
    args=['gh','api',path]
    if payload is not None:args+=['--method','PUT','--input','-']
    r=subprocess.run(args,input=json.dumps(payload) if payload is not None else None,capture_output=True,text=True,timeout=60)
    if r.returncode:
        if 'HTTP 404' in r.stderr:return None
        raise RuntimeError(r.stderr[:250])
    return json.loads(r.stdout)

def fetch_nodes():
    errors=[]
    for url in ['https://www.vpngate.net/en/','https://download.vpngate.jp/en/']:
        try:
            s=requests.Session();r=s.get(url,timeout=35);r.raise_for_status()
            soup=BeautifulSoup(r.text,'html.parser')
            fields={x['name']:x.get('value','') for x in soup.select('input[name]') if x['name'].startswith('__')}
            fields.update(C_SSTP='on',Button3='Refresh Servers List')
            try:
                r2=s.post(url,data=fields,timeout=35);r2.raise_for_status()
                if parse_rows(r2.text):r=r2
            except requests.RequestException:pass
            nodes=parse_rows(r.text)
            if not nodes:raise ValueError('no target-country SSTP rows')
            (ROOT/'source.html').write_text(r.text)
            return list({(n['host'],n['port']):n for n in nodes}.values()),url
        except Exception as exc:errors.append(f'{url}: {type(exc).__name__}')
    raise RuntimeError('; '.join(errors))

def locate_japan(nodes):
    cache_path=ROOT/'geo-cache.json'
    try:cache=json.loads(cache_path.read_text())
    except (OSError,ValueError):cache={}
    lock=threading.Lock();last_request=[0.0]
    def lookup(n):
        n=dict(n)
        try:
            ip=n.get('ip') or socket.gethostbyname(n['host'])
            if not ipaddress.ip_address(ip).is_global:raise ValueError('non-public IP')
            n['ip']=ip
            prior=cache.get(ip,{})
            if prior.get('success') and prior.get('source')=='ip2location.com/demo' and time.time()-prior.get('checked_at',0)<86400:
                n['geo']=prior;return n
            # Pace the free GeoIP service; cache successful answers per IP.
            with lock:
                delay=2.0-(time.monotonic()-last_request[0])
                if delay>0:time.sleep(delay)
                last_request[0]=time.monotonic()
            r=requests.get('https://www.ip2location.com/demo/'+ip,timeout=20);r.raise_for_status()
            n['geo']=parse_ip2location(r.text,ip)
            n['geo'].update(checked_at=time.time())
            with lock:cache[ip]=n['geo']
        except Exception as exc:n['geo']={'success':False,'error':type(exc).__name__}
        return n
    japan=[n for n in nodes if n['country']=='JP']
    with ThreadPoolExecutor(max_workers=4) as pool:japan=list(pool.map(lookup,japan))
    cache_path.write_text(json.dumps(cache,ensure_ascii=False,indent=2))
    return japan+[n for n in nodes if n['country']!='JP']

def probe(n):
    n=dict(n);checks=[]
    # VPN Gate uses self-signed certificates: pinning is not claimed here.
    for attempt in range(2):
        started=time.monotonic()
        try:
            with socket.create_connection((n['host'],n['port']),timeout=6) as raw:
                raw.settimeout(6)
                with ssl._create_unverified_context().wrap_socket(raw,server_hostname=n['host']) as conn:
                    conn.settimeout(6)
                    request=(f'SSTP_DUPLEX_POST /sra_{{BA195980-CD49-458b-9E23-C84EE0ADCD75}}/ HTTP/1.1\r\nHost: {n["host"]}:{n["port"]}\r\nSSTPCORRELATIONID: {{{uuid.uuid4()}}}\r\nContent-Length: 18446744073709551615\r\n\r\n')
                    conn.sendall(request.encode())
                    response=b''
                    while b'\r\n\r\n' not in response and len(response)<8192:
                        part=conn.recv(2048)
                        if not part:break
                        response+=part
                    if not re_status(response):raise ValueError('SSTP POST did not return HTTP 200')
                    # SSTP Call Connect Request, protocol ID PPP (1).
                    conn.sendall(bytes.fromhex('1001000e00010001000100060001'))
                    packet=b''
                    while len(packet)<8:
                        chunk=conn.recv(64)
                        if not chunk:break
                        packet+=chunk
                    if len(packet)<8 or packet[0]!=0x10 or int.from_bytes(packet[4:6],'big')!=2:
                        raise ValueError('missing SSTP CONNECT_ACK')
                    checks.append(round((time.monotonic()-started)*1000,1))
        except Exception as exc:
            n['probe_error']=type(exc).__name__+': '+str(exc)[:100]
    n['probe_successes']=len(checks);n['probe_ms']=min(checks) if checks else None
    n['probe_ok']=bool(checks)
    return n

def re_status(b):return b.startswith(b'HTTP/1.1 200') or b.startswith(b'HTTP/1.0 200')

def main():
    lock=open(ROOT/'run.lock','a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:print('SKIP another SSTP refresh is running');return
    now=datetime.now(timezone.utc).isoformat()
    print('START',now,flush=True)
    hk_doc=api(f'repos/{REPO}/contents/{FRONT_SOURCE}?ref={BRANCH}')
    if not hk_doc:raise RuntimeError('GitHub '+FRONT_SOURCE+' missing')
    hk=parse_hk(base64.b64decode(hk_doc['content']).decode())
    nodes,source=fetch_nodes()
    print('candidate counts',{c:sum(n['country']==c for n in nodes) for c in COUNTRIES},flush=True)
    nodes=locate_japan(nodes)
    tokyo=[n for n in nodes if is_tokyo(n)]
    other_japan=[n for n in nodes if n['country']=='JP' and not is_tokyo(n)]
    initial=tokyo+[n for n in nodes if n['country']=='KR']
    print('Tokyo candidates',len(tokyo),'other/unknown Japan',len(other_japan),flush=True)
    results=[]
    def check_batch(batch):
        with ThreadPoolExecutor(max_workers=10) as pool:
            futures=[pool.submit(probe,n) for n in batch]
            for f in as_completed(futures):results.append(f.result())
    check_batch(initial)
    if sum(n['probe_ok'] and is_tokyo(n) for n in results)<3:
        print('Tokyo verified fewer than 3; probing other Japan as fallback',flush=True)
        check_batch(other_japan)
    selected={}
    for country in COUNTRIES:
        ok=[n for n in results if n['country']==country and n['probe_ok']]
        # Metadata bandwidth is advertised, not measured SSTP goodput.
        ranked=rank_nodes(ok)
        selected[country]=ranked[:3]
    # Both countries must pass actual egress + fixed-line ISP/non-hosting crosscheck.
    egress_checks=[];selected={c:[] for c in COUNTRIES}
    for country in COUNTRIES:
        for n in rank_nodes([x for x in results if x['country']==country])[:12]:
            egress=verify_egress(n,ROOT);item=dict(n,egress=egress)
            if egress.get('egress_ip'):
                try:
                    ip=egress['egress_ip']
                    r=requests.get('https://www.ip2location.com/demo/'+ip,timeout=20);r.raise_for_status()
                    item['entry_geo']=item.get('geo');item['geo']=parse_ip2location(r.text,ip)
                    r=requests.get('https://www.iplocate.io/api/lookup/'+ip,timeout=20);r.raise_for_status();item['iplocate']=r.json()
                    if crosscheck_home(item):selected[country].append(item)
                except Exception as exc:item['egress_geo_error']=type(exc).__name__
            item['home_crosscheck_passed']=crosscheck_home(item)
            egress_checks.append(item)
            print(country,'egress/home check',n['host'],egress.get('egress_ip'),item.get('geo',{}).get('city'),'hosting',(item.get('iplocate',{}).get('privacy') or {}).get('is_hosting'),'accepted',item['home_crosscheck_passed'],flush=True)
            if len(selected[country])>=3:break
    output=build_output(hk,selected);count=validate_output(output,hk)
    report={'timestamp':now,'source':source,'repo':REPO,'branch':BRANCH,'hk_sha':hk_doc['sha'],'hk':hk,'selected':selected,'tested':results,'count':count,'shortfalls':{c:3-len(selected[c]) for c in COUNTRIES if len(selected[c])<3},'jp_tokyo_selected':sum(is_tokyo(n) for n in selected['JP']),'jp_fallback_selected':[n['host'] for n in selected['JP'] if not is_tokyo(n)],'tokyo_candidate_count':len(tokyo),'verification':'TLS + SSTP HTTP 200 + SSTP CONNECT_ACK; GeoIP is approximate; no PPP authentication or measured tunnel bandwidth'}
    (ROOT/'latest-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    report['egress_checks']=egress_checks
    report['front_source']=FRONT_SOURCE
    report['front_source_sha']=hk_doc['sha']
    report['front_endpoints']=hk
    report['verification']='JP and KR: authenticated SSTP/PPP actual egress + IP2Location fixed-line ISP + IPLocate non-hosting ISP; JP must be Tokyo in both databases. Database-supported classification, not proof of physical residence. No measured tunnel bandwidth.'
    (ROOT/'latest-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    candidate=ROOT/'sstp.txt';candidate.write_text(output)
    current=api(f'repos/{REPO}/contents/{TARGET}?ref={BRANCH}')
    if current and base64.b64decode(current['content'])==output.encode():commit=None
    else:
        payload={'message':f'Refresh VPN Gate SSTP endpoints ({count} verified)','branch':BRANCH,'content':base64.b64encode(output.encode()).decode()}
        if current:payload['sha']=current['sha']
        response=api(f'repos/{REPO}/contents/{TARGET}',payload);commit=response['commit']['sha']
    back=api(f'repos/{REPO}/contents/{TARGET}?ref={BRANCH}')
    if not back or base64.b64decode(back['content'])!=candidate.read_bytes():raise RuntimeError('GitHub readback mismatch')
    report['github_sha']=back['sha'];report['commit']=commit
    (ROOT/'latest-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print('VERIFIED',json.dumps({'count':count,'countries':{c:len(selected[c]) for c in COUNTRIES},'shortfalls':report['shortfalls'],'sha':back['sha'],'commit':commit},ensure_ascii=False),flush=True)

if __name__=='__main__':
    try:main()
    except Exception as exc:print('FAILED',type(exc).__name__,str(exc)[:350],flush=True);sys.exit(1)
