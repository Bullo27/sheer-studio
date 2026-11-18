# Rebuild skin + tights materials in an existing scene from the current sheer_materials code.
# Usage: blender -b scene.blend -P rebuild_materials.py -- <out.blend>
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
import sheer_materials as SM
out = sys.argv[sys.argv.index('--') + 1]
import sheer_params as SPRM
sc = bpy.context.scene
insp = json.loads(sc['tights_inspector']) if 'tights_inspector' in sc else SPRM.defaults()
P = SPRM.internal(insp)
sc['tights_params'] = json.dumps(P); sc['tights_inspector'] = json.dumps(insp)
knit, knit_mean = SM.knit_image()
sc['knit_mean'] = knit_mean
t = bpy.data.objects['tights']
mL = SM.make_tights('tights_L', bpy.data.images['damage_L'], knit, knit_mean, P)
mR = SM.make_tights('tights_R', bpy.data.images['damage_R'], knit, knit_mean, P)
t.data.materials[0] = mL; t.data.materials[1] = mR
b = bpy.data.objects['body']
b.data.materials[0] = SM.make_skin()
bpy.ops.wm.save_as_mainfile(filepath=out)
print('[rebuild_materials] saved', out)
