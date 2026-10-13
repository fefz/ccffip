"""Isolated full PPP authentication and actual SSTP egress test."""
import subprocess,socket,time,json,os,signal,ipaddress
from pathlib import Path

def verify_egress(n,root):
    nsname='sstp-egress-publisher';vh='sstpubh';vn='sstpubn';subnet='10.254.98.2/32'
    def cmd(*a,check=True):return subprocess.run(a,check=check,capture_output=True,text=True,timeout=25)
    def ns(*a,check=True):return cmd('ip','netns','exec',nsname,*a,check=check)
    before=cmd('ip','route','show','default').stdout
    outdev=json.loads(cmd('ip','-j','route','show','default').stdout)[0]['dev']
    rules=[['-t','nat','POSTROUTING','-s',subnet,'-o',outdev,'-j','MASQUERADE'],['FORWARD','-i',vh,'-j','ACCEPT'],['FORWARD','-o',vh,'-m','conntrack','--ctstate','ESTABLISHED,RELATED','-j','ACCEPT']]
    installed=[];proc=None;stream=None;result={'ppp_connected':False};host=n['host'];port=n['port'];label='publisher';log=Path(root)/'last-ppp.log'
    try:
        if Path('/var/run/netns/'+nsname).exists():raise RuntimeError('test namespace already in use')
        cmd('ip','netns','add',nsname);cmd('ip','link','add',vh,'type','veth','peer','name',vn);cmd('ip','link','set',vn,'netns',nsname)
        cmd('ip','addr','add','10.254.98.1/30','dev',vh);cmd('ip','link','set',vh,'up');ns('ip','link','set','lo','up');ns('ip','addr','add','10.254.98.2/30','dev',vn);ns('ip','link','set',vn,'up');ns('ip','route','add','default','via','10.254.98.1','dev',vn)
        for rule in rules:
            prefix=rule[:2] if rule[0]=='-t' else [];rest=rule[2:] if prefix else rule;cmd('iptables',*prefix,'-I',*rest);installed.append(rule)
        ip=socket.gethostbyname(host);ns('ip','route','add',ip+'/32','via','10.254.98.1','dev',vn)
        pty=f'sstpc --nolaunchpppd --cert-warn --tls-ext --ipparam {label} --log-stderr --log-level 2 {host}:{port}'
        stream=open(log,'w');proc=subprocess.Popen(['ip','netns','exec',nsname,'pppd','pty',pty,'name','vpn','password','vpn','plugin','sstp-pppd-plugin.so','sstp-sock',f'/var/run/sstpc/sstpc-{label}','noauth','noipdefault','nodefaultroute','refuse-eap','refuse-pap','refuse-chap','refuse-mschap','nobsdcomp','nodeflate','ifname','sstptest0','nodetach','logfd','2'],stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
        ready=False
        for _ in range(70):
            if proc.poll() is not None:break
            r=ns('ip','-j','addr','show','dev','sstptest0',check=False)
            if r.returncode==0 and any(a['family']=='inet' for d in json.loads(r.stdout) for a in d.get('addr_info',[])):ready=True;break
            time.sleep(.5)
        if not ready:raise RuntimeError('PPP authentication or address negotiation failed')
        result['ppp_connected']=True;ns('ip','route','replace','default','dev','sstptest0')
        for url in ['https://api.ipify.org','https://ipv4.icanhazip.com']:
            r=ns('curl','--interface','sstptest0','-4','-sS','--max-time','12',url,check=False)
            if r.returncode==0:
                try:
                    egress=str(ipaddress.ip_address(r.stdout.strip()))
                    result.update(egress_ip=egress,entry_ip=ip);break
                except ValueError:pass
        if not result.get('egress_ip'):raise RuntimeError('no public IP response through PPP')
    except Exception as exc:result['error']=type(exc).__name__+': '+str(exc)[:160]
    finally:
        if proc and proc.poll() is None:
            os.killpg(proc.pid,signal.SIGTERM)
            try:proc.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
        if stream:stream.close()
        for rule in reversed(installed):
            prefix=rule[:2] if rule[0]=='-t' else [];rest=rule[2:] if prefix else rule;cmd('iptables',*prefix,'-D',*rest,check=False)
        cmd('ip','netns','del',nsname,check=False);cmd('ip','link','del',vh,check=False)
        if cmd('ip','route','show','default').stdout!=before:raise RuntimeError('host default route changed')
    return result
