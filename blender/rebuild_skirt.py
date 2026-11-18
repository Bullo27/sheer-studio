# Rebuild only the skirt in an existing scene (fast look-dev iterations). Usage:
#   blender -b scene.blend -P rebuild_skirt.py -- <out.blend> [drape_frames]
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy, importlib
import sheer_skirt as SK, sheer_materials as SM
argv = sys.argv[sys.argv.index('--') + 1:]
out = argv[0]; frames = int(argv[1]) if len(argv) > 1 else 45
old = bpy.data.objects.get('skirt')
cols = list(old.users_collection) if old else []
if old:
    bpy.data.objects.remove(old, do_unlink=True)
body = bpy.data.objects['body']
skirt = SK.build_skirt_mesh(body)
SK.setup_cloth(skirt, frame_end=frames)
SK.drape(skirt, frames=frames)
SK.finish(skirt, SM.make_skirt())
for c in bpy.data.collections:
    if c.name.startswith('rim_receivers') and skirt.name not in c.objects:
        c.objects.link(skirt)
bpy.ops.wm.save_as_mainfile(filepath=out)
print('[rebuild_skirt] saved', out)
