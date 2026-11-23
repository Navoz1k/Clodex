"""Build a detached Codex test copy, leaving the installed MSIX untouched."""
import argparse
import base64
import hashlib
import json
import shutil
import struct
import tempfile
from pathlib import Path

from stamp_desktop_copy import stamp_archive

HERE = Path(__file__).resolve().parent
PET_DIR = HERE / 'pets' / 'clodex'
LOCAL_IDS = ('kav-clodex', 'custom:kav-clodex')
PLAYER_PATH = 'webview/assets/async/911644.eaf037cac0.js'
OVERLAY_PATH = 'webview/assets/async/355340.de1f371a7a.js'


def replace_once(data, old, new):
    if data.count(old) != 1:
        raise ValueError(f'Unexpected installed code: expected one occurrence of {old[:100]}')
    return data.replace(old, new, 1)


def extended_windows_path(path):
    absolute = str(path.resolve())
    if absolute.startswith('\\\\?\\'):
        return absolute
    if absolute.startswith('\\\\'):
        return '\\\\?\\UNC\\' + absolute[2:]
    return '\\\\?\\' + absolute


def load_clips():
    package = json.loads((PET_DIR / 'pet.json').read_text(encoding='utf8'))
    states = package['states']
    groups = {name: states[name] for name in ('idle', 'running', 'success')}
    groups['approval'] = ['6032848502915079777']
    for group, weight in [('rare', 8_000), ('veryRare', 1_250), ('legendary', 100)]:
        groups[group] = [item['clip'] for item in package['idleChoices'] if item['weight'] == weight]
    clips = {}
    for group in groups.values():
        for clip in group:
            metadata = package['clips'][clip]
            data = (PET_DIR / 'clips' / f'{clip}.webp').read_bytes()
            clips[clip] = {
                **metadata,
                'rows': max(2, (metadata['frames'] + 7) // 8),
                'image': 'data:image/webp;base64,' + base64.b64encode(data).decode('ascii'),
            }
    return groups, clips


def patch_player(data, groups, resting_clips):
    start = data.index('FPUb:(function')
    end = data.index('}),xgWs:', start) + 2
    player = data[start:end]
    player = replace_once(player, 'function m(e,t,n=!1){let r=f[e];',
        '''const claudeTurnVariants=new Map;
function claudeUsesAlternate(turn){
    if(typeof turn!=="string"||turn.length===0)return false;
    if(!claudeTurnVariants.has(turn)){
        claudeTurnVariants.set(turn,Math.random()>=0.5);
        if(claudeTurnVariants.size>128)claudeTurnVariants.delete(claudeTurnVariants.keys().next().value);
    }
    return claudeTurnVariants.get(turn);
}
function m(e,t,n=!1,claude=!1){let r=f[e];''')
    player = replace_once(player, 'if(n)return{frames:r,loopStartIndex:0};let i=',
        '''if(claude&&(e==="review"||e==="failed"))return{frames:[...r,...h],loopStartIndex:r.length};
if(n||(claude&&(e==="running"||e==="waiting")))return{frames:r,loopStartIndex:0};let i=''')
    player = replace_once(player, 'E=null==c.assetRef?c.spriteRowCount:l.rows;return',
        '''E=null==c.assetRef?c.spriteRowCount:l.rows;
const claude=c.claudePlayback===true;
const claudeApproval=claude&&c.claudeApproval===true;
const claudeWorking=claude&&!claudeApproval&&I==="running"&&(!c.claudePaused||null==n);
const claudeAlt=claudeWorking&&claudeUsesAlternate(c.claudeTurnKey);
const claudeResting=claude&&(claudeApproval||I==="idle"||I==="review"||I==="failed");
const claudeLook=claudeResting||claudeWorking?null:n;
const spriteUrl=c.spritesheetUrl??e[c.assetRef];
const spriteSize=null==E?void 0:`${100*l.columns}% ${100*E}%`;
return''')
    player = replace_once(player, 'if(null!=n){e.style.backgroundPosition=v(n,E);return}let t=m(I,y,o)',
        '''if(claude){
    e.style.backgroundImage=`url(${spriteUrl})`;
    e.style.backgroundSize=spriteSize??"";
    if(claudeResting||claudeWorking)return claudePlayResting(e,claudeApproval?"approval":I,y,E,claudeAlt);
}
if(null!=claudeLook){e.style.backgroundPosition=v(claudeLook,E);return}let t=m(I,y,o,claude)''')
    player = replace_once(player, '[I,n,o,y,E]', '[I,claudeLook,o,y,E,claude,claudeApproval,claudeResting,claudeWorking,claudeAlt,c.claudeTurnKey,spriteUrl,spriteSize]')
    player = replace_once(player, 'style:{backgroundImage:`url(${c.spritesheetUrl??e[c.assetRef]})`,backgroundSize:null==E?void 0:`${100*l.columns}% ${100*E}%`}',
        'style:claude?void 0:{backgroundImage:`url(${spriteUrl})`,backgroundSize:spriteSize}')
    resting_code = ('const claudeGroups=' + json.dumps(groups, separators=(',', ':')) + ';\n'
                    'const claudeClips=' + json.dumps(resting_clips, separators=(',', ':')) + ';\n'
                    'const claudeEqualIdleOdds=false;\n'
                    + (HERE / 'idle_playback.js').read_text(encoding='utf-8') + '\n')
    player = replace_once(player, 'const claudeTurnVariants=new Map;', resting_code + 'const claudeTurnVariants=new Map;')
    return data[:start] + player + data[end:], player


def patch_overlay(data, pet_ids):
    matches_pet = json.dumps(pet_ids) + '.includes(em.id)'
    old = 'source:(0,tV.aN)(em),state:ad.mascotState,style:'
    new = '''source:{...(0,tV.aN)(em),claudePlayback:''' + matches_pet + ''',claudePaused:eg,
claudeApproval:["exec","network","patch","permission","tool"].includes(eE[0]?.waitingRequest?.kind),
claudeTurnKey:(eE[0]?.isLoading?eE[0]:eE.find(item=>item.isLoading))?.turnKey??null},
state:''' + matches_pet + '''&&ad.mascotState==="idle"&&eE.some(item=>item.isLoading)?"running":ad.mascotState,style:'''
    data = replace_once(data, old, new)
    # Allocate an unused memo slot without changing any existing slot index.
    origin = data.index('let ad=l,am=eb.quickChat')
    start = data.rfind('el=(0,n.c)(', 0, origin)
    if start < 0:
        raise ValueError('Overlay memo allocation was not found')
    count_start = start + len('el=(0,n.c)(')
    stop = data.index(')', count_start)
    count = int(data[count_start:stop])
    data = data[:start] + f'el=(0,n.c)({count + 1}' + data[stop:]
    data = replace_once(data, 'el[204]!==aY?(B=', f'el[204]!==aY||el[{count}]!==eE?(B=')
    return replace_once(data, 'el[204]=aY,el[205]=B)', f'el[204]=aY,el[205]=B,el[{count}]=eE,B)')


def archive_entries(tree, prefix=''):
    for name, item in tree['files'].items():
        path = prefix + name
        if 'files' in item:
            yield from archive_entries(item, path + '/')
        elif 'offset' in item:
            yield path, item


def read_header(stream):
    _, header_size, _, json_size = struct.unpack('<4I', stream.read(16))
    return json.loads(stream.read(json_size)), header_size + 8


def encode_header(tree):
    data = json.dumps(tree, ensure_ascii=False, separators=(',', ':')).encode('utf8')
    padding = b'\0' * (-len(data) % 4)
    payload_size = 4 + len(data) + len(padding)
    return struct.pack('<4I', 4, 4 + payload_size, payload_size, len(data)) + data + padding


def build_archive(source, target, pet_ids, diagnostics):
    with source.open('rb') as old:
        tree, base = read_header(old)
        entries = sorted(archive_entries(tree), key=lambda pair: int(pair[1]['offset']))
        lookup = dict(entries)
        if not all(path in lookup for path in (PLAYER_PATH, OVERLAY_PATH)):
            raise ValueError('Unsupported Codex build. Expected the Windows desktop package 26.1117.4957.0.')

        def read_chunk(path):
            entry = lookup[path]
            old.seek(base + int(entry['offset']))
            return old.read(entry['size']).decode('utf8')

        player, module = patch_player(read_chunk(PLAYER_PATH), *load_clips())
        overlay = patch_overlay(read_chunk(OVERLAY_PATH), pet_ids)
        diagnostics.mkdir(parents=True, exist_ok=True)
        (diagnostics / 'patched-renderer.cjs').write_text('module.exports={' + module + '};\n', encoding='utf8')
        (diagnostics / 'patched-overlay.js').write_text(overlay, encoding='utf8')
        patches = {PLAYER_PATH: player.encode('utf8'), OVERLAY_PATH: overlay.encode('utf8')}
        positions = [(base + int(item['offset']), item['size']) for _, item in entries]
        cursor = 0
        for path, entry in entries:
            entry['offset'] = str(cursor)
            if path in patches:
                data = patches[path]
                entry['size'] = len(data)
                if 'integrity' in entry:
                    integrity = entry['integrity']
                    size = integrity['blockSize']
                    assert integrity['algorithm'] == 'SHA256'
                    integrity['hash'] = hashlib.sha256(data).hexdigest()
                    integrity['blocks'] = [hashlib.sha256(data[i:i+size]).hexdigest()
                                           for i in range(0, len(data), size)]
            cursor += entry['size']
        with target.open('wb') as new:
            new.write(encode_header(tree))
            for (path, _), (offset, size) in zip(entries, positions):
                if path in patches:
                    new.write(patches[path])
                else:
                    old.seek(offset)
                    for count in range(0, size, 4 << 20):
                        new.write(old.read(min(4 << 20, size - count)))
    with target.open('rb') as out:
        header, offset = read_header(out)
        layout = dict(archive_entries(header))
        for path, data in patches.items():
            entry = layout[path]
            out.seek(offset + int(entry['offset']))
            assert out.read(entry['size']) == data


def main():
    args = argparse.ArgumentParser()
    args.add_argument('app', type=Path)
    args.add_argument('--pet-id', action='append', default=[], help='Exact account-scoped Pets ID')
    options = args.parse_args()
    source = options.app.resolve(strict=True)
    target = HERE / 'desktop-copy'
    if target.exists():
        args.error('The modified app is already prepared. Use a fresh checkout to prepare a new copy.')
    pet_ids = [*LOCAL_IDS, *options.pet_id]
    with tempfile.TemporaryDirectory(prefix='.prepare-', dir=HERE) as temporary_dir:
        staged = Path(temporary_dir) / 'desktop-copy'
        archive = staged / 'resources/app.asar'
        archive.parent.mkdir(parents=True)
        build_archive(source / 'resources/app.asar', archive, pet_ids, HERE / 'diagnostics')
        shutil.copytree(extended_windows_path(source), extended_windows_path(staged),
                        dirs_exist_ok=True, ignore=shutil.ignore_patterns('app.asar'))
        runtime_ini = staged / 'resources/owl-app.ini'
        runtime_ini.write_text(replace_once(runtime_ini.read_text(encoding='utf8'),
                                           'UserDataDirectoryName=Codex\n',
                                           'UserDataDirectoryName=ClodexCodexMod\n'), encoding='utf8')
        stamp_archive(staged)
        (staged / 'clodex-build.json').write_text(json.dumps({
            'originalExecutable': str(source / 'ChatGPT.exe'),
            'petIds': pet_ids,
        }), encoding='utf8')
        staged.rename(target)
    print('Prepared modified Codex:', target)


if __name__ == '__main__':
    main()
