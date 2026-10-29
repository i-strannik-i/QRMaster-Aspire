import io
import json
import math
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw
from lupa import LuaRuntime
import zxingcpp
from shapely.geometry import Polygon
from shapely.ops import unary_union

from qr_engine import generate, lua
from version import VERSION
from updates import check_update, version_tuple

ROOT=Path(__file__).resolve().parent


def regions(result):
    polygons=[]
    outer=None
    holes=[]
    for ring in result['contours']:
        area=sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(ring,ring[1:]))
        if area>0:
            if outer is not None: polygons.append(Polygon(outer,holes))
            outer=ring;holes=[]
        else: holes.append(ring)
    if outer is not None: polygons.append(Polygon(outer,holes))
    return unary_union(polygons)


def render(result,machined=False):
    dark=regions(result)
    if machined:
        radius=result['cutter']/2
        dark=dark.buffer(-radius).buffer(radius)
    factor=16/result['pitch']
    size=math.ceil(result['size']*factor)
    image=Image.new('L',(size,size),255)
    draw=ImageDraw.Draw(image)
    polygons=[dark] if dark.geom_type=='Polygon' else list(dark.geoms)
    polygons.sort(key=lambda p:(p.bounds[2]-p.bounds[0])*(p.bounds[3]-p.bounds[1]),reverse=True)
    def points(ring):return [(x*factor,size-y*factor) for x,y in ring.coords]
    for polygon in polygons:
        draw.polygon(points(polygon.exterior),fill=0)
        for hole in polygon.interiors:draw.polygon(points(hole),fill=255)
    return image


class QRTests(unittest.TestCase):
    def test_vectors_and_machined_pockets_decode(self):
        for url in ('https://example.com','https://youtube.com/watch?v=AbCd123&list=456',
                    'https://пример.рф/страница?имя=тест','https://example.com/'+'a'*400):
            for cutter in (2,4,6):
                with self.subTest(url=url,cutter=cutter):
                    result=generate(dict(url=url,cutter=str(cutter)))
                    self.assertTrue(regions(result).is_valid)
                    for machined in (False,True):
                        decoded=zxingcpp.read_barcode(np.array(render(result,machined)))
                        self.assertIsNotNone(decoded)
                        self.assertEqual(decoded.text,url)
                    for ring in result['contours']:
                        self.assertEqual(ring[0],ring[-1])
                        for x,y in ring:
                            self.assertGreaterEqual(x,4*result['pitch']-1e-8)
                            self.assertGreaterEqual(y,4*result['pitch']-1e-8)

    def test_auto_size_and_legacy_settings_ignored(self):
        previous=0
        for cutter in (2,4,6):
            result=generate(dict(url='example.com',cutter=str(cutter)))
            self.assertGreater(result['size'],previous)
            self.assertGreaterEqual(result['pitch'],cutter*1.1-1e-9)
            self.assertAlmostEqual(result['size']*100,round(result['size']*100))
            self.assertEqual(result['shape'],'squares')
            legacy=generate(dict(url='example.com',cutter=str(cutter),shape='circles',size='1000',x='50',y='50'))
            self.assertEqual(result,legacy)
            previous=result['size']

    def test_validation(self):
        for options in ({'url':''},{'url':'ftp://example.com'},{'url':'https://'},
                        {'url':'https://example.com\nsize=900'},
                        {'url':'example.com','cutter':'nan'},
                        {'url':'example.com','cutter':'0'}):
            with self.subTest(options=options),self.assertRaises(ValueError):generate(options)
        result=generate({'url':'example.com'})
        self.assertEqual(zxingcpp.read_barcode(np.array(render(result))).text,'https://example.com')

    def test_native_mm_inches_auto_close_and_error_retry(self):
        for in_mm in (True,False):
            for fits in (True,False):
                runtime=LuaRuntime()
                result=generate(dict(url='example.com',cutter='4'))
                runtime.execute('RESULT='+lua(result))
                runtime.globals().IN_MM=in_mm
                runtime.globals().FITS=fits
                runtime.execute(r"""
                    added={};selected={};layer_names={};dialogs=0;shows=0;message=nil
                    function Point2D(x,y)return {x=x,y=y} end
                    function Contour(z)return {points={},AppendPoint=function(s,p)table.insert(s.points,p)end,
                        LineTo=function(s,p)table.insert(s.points,p)end}end
                    function CreateCadContour(c)return c end
                    layer={AddObject=function(s,o)table.insert(added,o)end}
                    job={Exists=true,InMM=IN_MM,MinX=-10,MinY=-20,
                        Width=FITS and (IN_MM and 500 or 500/25.4) or 1,
                        Height=IN_MM and 500 or 500/25.4,
                        LayerManager={GetLayerWithName=function(s,n)table.insert(layer_names,n);return layer end},
                        Selection={Clear=function()end,Add=function(s,o)table.insert(selected,o)end},
                        Refresh2DView=function()end}
                    function VectricJob()return job end
                    function MessageBox(m)message=m end
                    function Registry()return {GetString=function()return '4'end,SetString=function()end}end
                    function HTML_Dialog()
                        dialogs=dialogs+1
                        local fields={}
                        return {AddTextField=function(s,k,v)assert(k=='url' or k=='cutter');fields[k]=v end,
                            AddLabelField=function()end,
                            ShowDialog=function(s)
                                shows=shows+1
                                if shows==1 then fields.url='https://example.com';return true end
                                assert(fields.url=='https://example.com');return false
                            end,
                            GetTextField=function(s,k)assert(fields[k]~=nil);return fields[k]end}
                    end
                    os.tmpname=function()return 'qr-test-request.tmp'end
                    io.open=function()
                        last_request=''
                        return {write=function(s,...)for _,v in ipairs({...})do last_request=last_request..v end end,
                            close=function()end}
                    end
                    os.execute=function()end;os.remove=function()end
                    loadfile=function()return function()
                        if last_request:find('task=update_check',1,true)then
                            return {ok=true,available=false,message='Version current'}
                        end
                        assert(not last_request:find('shape=',1,true))
                        assert(not last_request:find('size=',1,true))
                        return RESULT
                    end end
                """)
                runtime.execute((ROOT/'QRMaster_Aspire.lua').read_text(encoding='utf-8'))
                runtime.execute("main([[C:\\QA]])")
                if fits:
                    self.assertIsNone(runtime.globals().message)
                    self.assertEqual(runtime.globals().dialogs,1)
                    self.assertEqual(len(runtime.globals().added),result['count'])
                    self.assertEqual(len(runtime.globals().selected),result['count'])
                    actual=runtime.globals().added[1].points[1]
                    self.assertAlmostEqual(actual.x,-10+result['contours'][0][0][0]*(1 if in_mm else 1/25.4))
                else:
                    self.assertEqual(len(runtime.globals().added),0)
                    self.assertEqual(runtime.globals().dialogs,2)
                    self.assertIn('не помещается',runtime.globals().message)

    def test_built_engine(self):
        exe=ROOT/'bin/QRMasterEngine.exe'
        if not exe.exists():self.skipTest('Build engine first')
        with tempfile.TemporaryDirectory(prefix='QR проверка ')as folder:
            request=Path(folder)/'request.txt';response=Path(folder)/'result.lua'
            for url in ('https://пример.рф/тест?a=1&b=2',''):
                request.write_text('url='+url+'\ncutter=4\n',encoding='utf-8')
                subprocess.run([str(exe),str(request),str(response)],check=True,timeout=60)
                result=LuaRuntime().execute(response.read_text(encoding='ascii'))
                self.assertEqual(result.ok,bool(url))
                if url:
                    self.assertEqual(result.version,VERSION)
                    native={'size':result.size,'pitch':result.pitch,'cutter':result.cutter,
                        'contours':[[list(p.values())for p in ring.values()]for ring in result.contours.values()]}
                    self.assertEqual(zxingcpp.read_barcode(np.array(render(native,True))).text,url)


class UpdateTests(unittest.TestCase):
    def test_api_rate_limit_uses_public_release_page(self):
        response = io.BytesIO()
        response.geturl = lambda: 'https://github.com/i-strannik-i/QRMaster-Aspire/releases/tag/v99.0.0'
        with patch('urllib.request.urlopen', side_effect=[TimeoutError(), response]):
            result = check_update()
        self.assertTrue(result['available'])
        self.assertEqual(result['latest'], '99.0.0')

    def test_version_comparison_and_prereleases(self):
        current=tuple(map(int,VERSION.split('.')))
        new=f'{current[0]}.{current[1]}.{current[2]+1}'
        for tag,draft,pre,expected in [('v'+new,False,False,True),(VERSION,False,False,False),
                                     ('v'+new,False,True,False),('v'+new,True,False,False)]:
            payload=dict(tag_name=tag,draft=draft,prerelease=pre)
            with patch('urllib.request.urlopen',return_value=io.BytesIO(json.dumps(payload).encode())):
                result=check_update();self.assertEqual(result['available'],expected)
                if expected:self.assertIn(new,result['message'])
        self.assertIsNone(version_tuple('not a version'))

    def test_offline_check_is_nonfatal(self):
        with patch('urllib.request.urlopen',side_effect=TimeoutError()):
            result=check_update()
        self.assertTrue(result['ok']);self.assertFalse(result['available'])


if __name__=='__main__':unittest.main()
