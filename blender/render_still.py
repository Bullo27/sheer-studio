# Render a still from the saved scene.
# Usage: blender -b <scene.blend> -P render_still.py -- <out.png> [camera] [percent] [samples]
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy

argv = sys.argv[sys.argv.index('--') + 1:]
out = argv[0]
cam = argv[1] if len(argv) > 1 else 'VIEW01'
pct = int(argv[2]) if len(argv) > 2 else 50
spp = int(argv[3]) if len(argv) > 3 else 96
scene = bpy.context.scene
scene.camera = bpy.data.objects[cam]
scene.render.resolution_percentage = pct
scene.cycles.samples = spp
prefs = bpy.context.preferences.addons['cycles'].preferences
prefs.compute_device_type = 'OPTIX'
prefs.get_devices()
for d in prefs.devices:
    d.use = (d.type == 'OPTIX')
scene.cycles.device = 'GPU'
# optional hook for look-dev experiments
hook = os.environ.get('SHEER_HOOK')
if hook and os.path.exists(hook):
    exec(open(hook).read())
scene.render.filepath = out
t = time.time()
bpy.ops.render.render(write_still=True)
print('[still] %s %.1fs' % (out, time.time() - t))
