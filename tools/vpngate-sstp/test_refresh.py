import unittest
import importlib.util
from pathlib import Path

class FormatTest(unittest.TestCase):
    def test_country_number_and_hk_round_robin(self):
        path=Path(__file__).with_name('refresh.py')
        self.assertTrue(path.exists(), 'publisher implementation missing')
        spec=importlib.util.spec_from_file_location('refresh',path)
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        selected={'JP':[{'host':'vpn1.opengw.net','port':443},{'host':'vpn2.opengw.net','port':1443},{'host':'vpn3.opengw.net','port':443}],'KR':[],'US':[],'TW':[]}
        result=m.build_output(['1.2.3.4:11','1.2.3.5:12','1.2.3.6:13'],selected)
        self.assertEqual(result,'1.2.3.4:11#Mine-JP-家宽-1$sstp://vpn:vpn@vpn1.opengw.net:443\n1.2.3.5:12#Mine-JP-家宽-2$sstp://vpn:vpn@vpn2.opengw.net:1443\n1.2.3.6:13#Mine-JP-家宽-3$sstp://vpn:vpn@vpn3.opengw.net:443\n')

class SelectionTest(unittest.TestCase):
    def test_parse_rank_and_hk_validation(self):
        import sys
        sys.path.insert(0,str(Path(__file__).parent))
        import refresh as m
        self.assertTrue(callable(getattr(m,'parse_rows',None)), 'parser missing')
        html='<table><tr><td>Japan</td><td>vpn1.opengw.net 1.2.3.4</td><td>2 sessions 5 days</td><td>100 Mbps Ping: 10 ms</td><td>x</td><td>x</td><td>x</td><td>SSTP Hostname : vpn1.opengw.net:1443</td><td>x</td><td>1000</td></tr></table>'
        n=m.parse_rows(html)[0]
        self.assertEqual((n['country'],n['sessions'],n['mbps'],n['port']),('JP',2,100.0,1443))
        self.assertGreater(m.quality(n),m.quality(dict(n,sessions=100)))
        self.assertGreater(m.quality(n),m.quality(dict(n,mbps=2)))
        self.assertEqual(m.parse_hk('1.2.3.4:11#old\n1.2.3.5:12#old\n1.2.3.6:13#old\n'),['1.2.3.4:11','1.2.3.5:12','1.2.3.6:13'])
        with self.assertRaises(ValueError):m.parse_hk('1.2.3.4:11#one\n')

class GuardTest(unittest.TestCase):
    def test_empty_result_is_rejected(self):
        import sys
        sys.path.insert(0,str(Path(__file__).parent))
        import refresh as m
        self.assertTrue(callable(getattr(m,'validate_output',None)), 'output guard missing')
        with self.assertRaises(ValueError):m.validate_output('', ['1.2.3.4:11','1.2.3.5:12','1.2.3.6:13'])
        good=m.build_output(['1.2.3.4:11','1.2.3.5:12','1.2.3.6:13'],{'KR':[{'host':'vpn1.opengw.net','port':443}]})
        self.assertEqual(m.validate_output(good,['1.2.3.4:11','1.2.3.5:12','1.2.3.6:13']),1)

class RegionTest(unittest.TestCase):
    def test_us_tw_are_excluded(self):
        import refresh as m
        self.assertEqual(m.COUNTRIES,('JP','KR'))
        row='<tr><td>{}</td><td>vpn1.opengw.net 1.2.3.4</td><td>2 sessions</td><td>100 Mbps Ping: 10 ms</td><td>x</td><td>x</td><td>x</td><td>SSTP Hostname : vpn1.opengw.net:1443</td><td>x</td><td>1000</td></tr>'
        self.assertEqual(m.parse_rows('<table>'+row.format('United States')+row.format('Taiwan')+'</table>'),[])
        with self.assertRaises(ValueError):m.validate_output('1.2.3.4:11#Mine-US-家宽-1$sstp://vpn:vpn@vpn1.opengw.net:443\n',['1.2.3.4:11','1.2.3.5:12','1.2.3.6:13'])

    def test_tokyo_preference_over_score(self):
        import refresh as m
        self.assertTrue(callable(getattr(m,'rank_nodes',None)), 'Tokyo ranking missing')
        base={'country':'JP','sessions':2,'mbps':100,'ping_ms':10,'probe_ms':100,'probe_successes':2,'probe_ok':True}
        osaka=dict(base,host='osaka',geo={'success':True,'country_code':'JP','city':'Osaka','region':'Osaka'},mbps=1000)
        tokyo=dict(base,host='tokyo',geo={'success':True,'country_code':'JP','city':'Tokyo','region':'Tokyo'})
        unknown=dict(base,host='unknown',geo={'success':False},mbps=2000)
        self.assertEqual(m.rank_nodes([osaka,unknown,tokyo])[0]['host'],'tokyo')
        self.assertFalse(m.is_tokyo(dict(base,geo={'success':True,'country_code':'US','city':'Tokyo','region':'Tokyo'})))

class WebsiteTest(unittest.TestCase):
    def test_parse_ipinfo_geo_not_timezone(self):
        import refresh as m
        d=m.parse_ipinfo({'ip':'1.2.3.4','country':'JP','region':'Toyama','city':'Toyama','timezone':'Asia/Tokyo'},'1.2.3.4')
        self.assertEqual(d['city'],'Toyama');self.assertFalse(m.is_tokyo({'country':'JP','geo':d}))
        with self.assertRaises(ValueError):m.parse_ipinfo({'ip':'1.2.3.5','country':'JP','city':'Tokyo'},'1.2.3.4')
        with self.assertRaises(ValueError):m.parse_ipinfo({'ip':'1.2.3.4','country':'JP'},'1.2.3.4')

class ResidentialTest(unittest.TestCase):
    def test_crosscheck_rejects_hosting_unknown_and_non_tokyo(self):
        import refresh as m
        self.assertTrue(callable(getattr(m,'crosscheck_home',None)), 'residential crosscheck missing')
        n={'country':'JP','geo':{'success':True,'ip':'1.2.3.4','country_code':'JP','region':'Tokyo','city':'Tokyo','source':'ipinfo.io/json'},'egress':{'ppp_connected':True,'egress_ip':'1.2.3.4'},'iplocate':{'ip':'1.2.3.4','country_code':'JP','city':'Shinjuku','subdivision':'Tokyo','privacy':{'is_hosting':False,'is_vpn':True},'company':{'type':'isp'},'asn':{'type':'isp'}}}
        self.assertTrue(m.crosscheck_home(n))
        import copy
        bad=copy.deepcopy(n);bad['iplocate']['privacy']['is_hosting']=True;self.assertFalse(m.crosscheck_home(bad))
        bad=copy.deepcopy(n);bad['iplocate']['privacy'].pop('is_hosting');self.assertFalse(m.crosscheck_home(bad))
        bad=copy.deepcopy(n);bad['iplocate']['city']='Osaka';bad['iplocate']['subdivision']='Osaka';self.assertFalse(m.crosscheck_home(bad))
        bad=copy.deepcopy(n);bad['geo']['source']='ip2location.com/demo';self.assertFalse(m.crosscheck_home(bad))
        bad=copy.deepcopy(n);bad['iplocate']['ip']='1.2.3.5';self.assertFalse(m.crosscheck_home(bad))

class SourceTest(unittest.TestCase):
    def test_front_source_is_github_ip_txt(self):
        import run as publisher
        self.assertEqual(getattr(publisher,'FRONT_SOURCE',None),'data/ip.txt')

if __name__=='__main__':unittest.main()
