"""Re-generate everything: render the 6 music loops in parallel, master + encode + verify, then the SFX.
usage: python3 build_all.py [track_module ...]"""
import os
import sys
import json
import subprocess
from concurrent.futures import ProcessPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
TRACKS = {'track_lofi': 'sakura_lofi', 'track_futurebass': 'kawaii_future_bass', 'track_chip': 'pixel_heart_8bit',
          'track_musicbox': 'music_box_dream', 'track_citypop': 'city_pop_night', 'track_koto': 'koto_breeze'}


def render(mod):
    subprocess.run([sys.executable, mod + '.py'], check=True, cwd=HERE)
    return mod


def master_one(name):
    sys.path.insert(0, HERE)
    import master
    return master.process(name)


if __name__ == '__main__':
    os.chdir(HERE)
    mods = sys.argv[1:] or list(TRACKS)
    with ProcessPoolExecutor(6) as ex:
        list(ex.map(render, mods))
    with ProcessPoolExecutor(6) as ex:
        reps = list(ex.map(master_one, [TRACKS[m] for m in mods]))
    subprocess.run([sys.executable, 'sfx.py'], check=True, cwd=HERE)
    print('\n%-20s %6s %8s %8s %8s %8s %8s %8s %8s %6s' % ('track', 'dur', 'LUFS', 'TP', 'ff_I', 'ff_TP', 'seam', 'd99',
                                                         'hd/tl', 'KB'))
    for r in reps:
        lo = r['loop_ogg']
        print('%-20s %6.1f %8.2f %8.2f %8s %8s %8.4f %8.4f %4.1f/%4.1f %6.0f' % (
            r['name'], r['dur_s'], r['lufs_ogg'], r['tp_ogg'], r['ffmpeg_I'], r['ffmpeg_TP'], lo['seam'], lo['d99'],
            lo['rms_head_db'], lo['rms_tail_db'], r['size_kb']))
