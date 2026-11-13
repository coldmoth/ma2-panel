"""Independent, deliberately small console oracle for isolated quality tests.

No import of panel commands/settings. Fixture IDs and ranges are console facts.
"""
import re

RANGES = {'pan': (-270, 270), 'tilt': (-135, 135), 'zoom': (0, 100),
          'focus': (0, 100), 'strobe': (0, 100), 'dimmer': (0, 100),
          'colorrgb1': (0, 100), 'colorrgb2': (0, 100), 'colorrgb3': (0, 100)}
COLORS = {'colorrgb1': 'r', 'colorrgb2': 'g', 'colorrgb3': 'b'}
# The test desk has 40 heads, 16 RGB units and four dimmers.
FIXTURES = {n: set(RANGES) if n <= 40 else {'dimmer', *COLORS} if n <= 56 else {'dimmer'}
            for n in range(1, 61)}
GROUPS = {1: ('Фронт MA2', [1, 2]), 2: ('Контровой MA2', [55, 56])}
READ_ONLY = re.compile(r'(?:login "[^"\r\n]*" "[^"\r\n]*"|ListVar|List (?:Executor|Group|Preset|FixtureType|Fixture|Page|Show)(?: [\d.]+(?: Thru [\d.]+)?)?|Export (?:Fixture|FixtureType|Group|Preset|Page|Executor) [\d.]+(?: Thru [\d.]+)? "[^"\r\n]+")\Z')
MUTATING = re.compile(r'(?:Fixture \d+(?: \+ \d+)*|Group \d+|ClearAll|Fixture Thru At 0|Master \S+ At [\d.]+|(?:Go|Goto Cue 1|Off|StoreLook) Executor \S+(?: .*)?|Label (?:Executor|Page) .+)(?: Fade [\d.]+)?\Z')


# Exact read-only Lua protocol templates; arbitrary Lua remains rejected.
SCENE_PROBE = re.compile('Lua\\ "local\\ c=gma\\.show\\.getobj\\.handle\\(\'Executor\\ \\d+\\.\\d+\\ Cue\\ 1\'\\);\\ local\\ p=c\\ and\\ gma\\.show\\.getobj\\.parent\\(c\\);\\ local\\ n=p\\ and\\ gma\\.show\\.getobj\\.amount\\(p\\);\\ local\\ q=c\\ and\\ gma\\.show\\.getobj\\.child\\(c,0\\);\\ local\\ cmd;\\ if\\ q\\ then\\ for\\ i=0,gma\\.show\\.property\\.amount\\(q\\)\\-1\\ do\\ if\\ gma\\.show\\.property\\.name\\(q,i\\)==\'CMD\'\\ then\\ cmd=gma\\.show\\.property\\.get\\(q,i\\)\\ end\\ end\\ end;\\ local\\ ok=n\\ and\\ n>=1\\ and\\ n<=2\\ and\\ gma\\.show\\.property\\.get\\(c,\'trig\'\\)==\'Go\'\\ and\\ gma\\.show\\.getobj\\.amount\\(c\\)==1\\ and\\ cmd==\'\';\\ local\\ seen=0;\\ if\\ ok\\ then\\ for\\ i=0,n\\-1\\ do\\ local\\ h=gma\\.show\\.getobj\\.child\\(p,i\\);\\ local\\ k=h\\ and\\ tonumber\\(gma\\.show\\.getobj\\.number\\(h\\)\\);\\ if\\ not\\ h\\ then\\ if\\ i\\~=0\\ then\\ ok=false\\ end\\ elseif\\ h==c\\ and\\ k==1\\ then\\ seen=seen\\+1\\ elseif\\ k\\~=0\\ then\\ ok=false\\ end\\ end\\ end;\\ ok=ok\\ and\\ seen==1;\\ gma\\.show\\.setvar\\(\'PANELSCENE\',\'[0-9a-f]{16}\\ \'\\.\\.\\(ok\\ and\\ \'manual\'\\ or\\ \'unknown\'\\)\\)"')
GRAND_PROBE = re.compile('Lua\\ "local\\ h=gma\\.show\\.getobj\\.handle\\(\'SpecialMaster\\ 2\\.1\'\\);\\ local\\ v=h\\ and\\ gma\\.show\\.property\\.get\\(h,\'value\'\\);\\ gma\\.show\\.setvar\\(\'PANELGM\',\'[0-9a-f]{16}\\ \'\\.\\.tostring\\(v\\)\\)"')
SCENE_WRITE = re.compile(r'(?:(?:Store Executor \d+\.\d+ Cue 1 /Source=Output /Use=Allforselected)|(?:Assign Cue 1 Executor \d+\.\d+ /Trig=Go)|(?:Masterfade (?:\d+(?:\.\d+)?) Executor \d+\.\d+))\Z')


def is_read_only(command):
    return bool(READ_ONLY.fullmatch(command) or SCENE_PROBE.fullmatch(command) or GRAND_PROBE.fullmatch(command))


def validate(command, selection):
    group = re.fullmatch(r'Group (\d+)', command)
    if group and int(group[1]) not in GROUPS:
        return 'Unknown console group'
    m = re.fullmatch(r'(?:At|Attribute "([^"\n]+)" At) ([+-] )?(-?[\d.]+)(?: Fade [\d.]+)?', command)
    if m:
        attr = (m[1] or 'dimmer').lower()
        if attr not in RANGES:
            return 'Unknown attribute'
        if any(attr not in FIXTURES.get(n, set()) for n in selection):
            return 'Unsupported attribute for selected fixture'
        low, high = RANGES[attr]
        value = float(m[3])
        if not m[2] and not low <= value <= high:
            return 'Value outside console range'
        return None
    grand = re.fullmatch(r'SpecialMaster 2\.1 At (\d+(?:\.\d+)?)', command)
    if grand:
        return None if 0 <= float(grand[1]) <= 100 else 'Value outside console range'
    if is_read_only(command) or SCENE_WRITE.fullmatch(command) or MUTATING.fullmatch(command):
        return None
    return 'Unknown console command'
