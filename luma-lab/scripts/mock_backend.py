"""Local lab harness. Imports the unmodified release backend; never connects to a desk."""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = Path(os.environ.get('LUMA_RUNTIME_DIR', ROOT / 'luma-lab' / '.runtime')).expanduser().resolve()
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
from concert_demo import demo_data, seed_mock, network_guard
from ma2panel import bridge


def main():
    RUNTIME.mkdir(parents=True, exist_ok=True)
    config_path, settings_path = RUNTIME / 'config.json', RUNTIME / 'settings.json'
    ports = [int(os.environ.get('LUMA_BACKEND_PORT', '18781')), int(os.environ.get('LUMA_SIMPLE_PORT', '18782'))]
    if not config_path.exists():
        resources = ROOT / 'ma2panel' / 'resources'
        cfg = json.loads((resources / 'config.example.json').read_text())
        settings = json.loads((resources / 'settings.example.json').read_text())
        cfg, settings = demo_data(cfg, settings, RUNTIME, ports)
        # Isolated mock show, not the user's show or LUMA's hard-coded fixture array.
        samples = cfg['fixtures']
        picks = [*range(40, 48), *range(0, 6), *range(48, 52), *range(56, 58)]
        coords = [(.2,.12),(.4,.12),(.6,.12),(.8,.12),(.05,.35),(.05,.6),(.95,.35),(.95,.6),
                  (.12,.22),(.5,.22),(.88,.22),(.18,.86),(.5,.88),(.82,.86),
                  (.12,.73),(.34,.84),(.66,.84),(.88,.73),(.4,.98),(.6,.98)]
        fixtures = []
        for i, (sample, xy) in enumerate(zip(picks, coords), 1):
            f = dict(samples[sample]);kind = 'bar' if i<=8 else 'head' if i<=14 else 'par' if i<=18 else 'fresnel'
            f.update(id=i, label=f'{dict(bar="LED Bar",head="Moving Head",par="PAR",fresnel="Fresnel")[kind]} {i:02}',
                     name=f'LUMA mock {i}', x=xy[0], y=xy[1], icon=kind)
            fixtures.append(f)
        cfg.update(show='LUMA · Mock Hall',fixtures=fixtures,scenes=cfg['scenes'][:6],presets=[],ma2groups=[],
                   scene_fade=1.5,groups=[{'id':'bars','label':'LED-бары','fixtures':list(range(1,9))},
                   {'id':'heads','label':'Движущиеся головы','fixtures':list(range(9,15))},
                   {'id':'front','label':'Фронтальный свет','fixtures':list(range(15,21))}])
        settings['safety']['allow_show_load']=False
        settings['safety']['allow_show_save']=False
        config_path.write_text(json.dumps(cfg,ensure_ascii=False,indent=2))
        settings_path.write_text(json.dumps(settings,ensure_ascii=False,indent=2))
    # Even after editing settings, listeners and every outbound socket stay isolated.
    readback = os.environ.get('LUMA_MOCK_READBACK') == '1'
    settings=json.loads(settings_path.read_text());settings.update(bind='127.0.0.1',port=ports[0],simple_port=ports[1])
    if readback:
        settings['dmx_seconds'] = 1
        settings.setdefault('safety', {})['allow_layout_import'] = True
        cfg_live = json.loads(config_path.read_text())
        for f in cfg_live.get('fixtures', []):
            if f.get('channels') and f.get('footprint', 0) < f['channels']:
                f['footprint'] = f['channels']
        config_path.write_text(json.dumps(cfg_live, ensure_ascii=False, indent=2))
    settings_path.write_text(json.dumps(settings,ensure_ascii=False,indent=2))
    allowed=set();sys.addaudithook(network_guard(allowed))
    original_start=bridge.start_mock
    async def start(*args,**kwargs):
        mock=await original_start(*args,**kwargs);allowed.add(mock.port)
        cfg = json.loads(config_path.read_text())
        # A saved plan can omit the footprint until FixtureType discovery.
        for fixture in cfg["fixtures"]:
            fixture.setdefault("footprint", fixture.get("channels") or 0)
        seed_mock(mock, cfg, RUNTIME)
        if cfg.get('show') and cfg['show'] not in mock.shows:
            mock.shows.insert(0, cfg['show'])
        mock.configure_simulation(cfg)
        # Test-state initialization, never an action sent by the browser.
        palettes=[[[100,58,20],[100,80,42]],[[16,28,100],[56,46,100]],[[55,30,100],[100,20,58]],
                  [[100,86,64],[100,96,82]],[[100,8,24],[100,35,46]],[[5,50,62],[22,26,60]]]
        for index,scene in enumerate(cfg['scenes']):
            for fid,values in mock.sim_scenes[scene['exec']].items():
                values.update(rgb=palettes[index%6][fid%2],dim=65 if fid<=14 else 38,zoom=35,tilt=60)
        mock.sim_active={ex:mock.sim_scenes[ex] for ex in mock.running if ex in mock.sim_scenes}
        mock.cues={s['exec']:{1:{}} for s in cfg['scenes']}
        if readback:
            from ma2panel.commands import absolute
            type_list_path = RUNTIME / 'tests' / 'list_fixturetype_3.9.60.txt'
            orig_answer = mock._answer
            def answer_with_dmx(text):
                if text == 'List FixtureType' and type_list_path.exists():
                    return f"Executing : {text}\r\n" + type_list_path.read_text(encoding='utf-8').replace('\n', '\r\n') + "[Channel]>"
                if 'PANELDMX' in text:
                    live_cfg = json.loads(config_path.read_text())
                    dmx_map = live_cfg.get('dmx_map', {})
                    out = mock.simulation_output(master=True)
                    dmx = {}
                    for f in live_cfg.get('fixtures', []):
                        start_addr = absolute(f.get('address'))
                        spec = dmx_map.get(f.get('type') or '')
                        vals = out.get(f['id'])
                        if not start_addr or not spec or not vals:
                            continue
                        if spec.get('dim'):
                            dmx[start_addr + spec['dim'] - 1] = int(round(max(0, min(100, vals['dim'])) * 2.55))
                        rgb = vals.get('rgb') or [100, 100, 100]
                        for idx, ch in enumerate(('r', 'g', 'b')):
                            if spec.get(ch):
                                dmx[start_addr + spec[ch] - 1] = int(round(max(0, min(100, rgb[idx])) * 2.55))
                        if spec.get('shutter') and spec.get('shutter_open'):
                            dmx[start_addr + spec['shutter'] - 1] = spec['shutter_open'][0][0]
                    mock.dmx = dmx
                return orig_answer(text)
            mock._answer = answer_with_dmx
        return mock
    bridge.start_mock=start
    sys.argv=[str(ROOT/'bridge.py'),'--mock','--config',str(config_path),'--settings',str(settings_path)]
    bridge.main()

if __name__=='__main__':main()
