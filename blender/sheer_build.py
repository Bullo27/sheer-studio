# SHEER — build the full studio scene and save it.
# Usage: blender -b -P sheer_build.py -- <human_base_meshes_bundle.blend> <out.blend>
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
import sheer_body as SB
import sheer_tights as ST
import sheer_toebox as TB
import sheer_materials as SM
import sheer_scene as SS
import sheer_skirt as SK

# Material parameters — mirrors the original Unity inspector values
import sheer_params as SPRM
INSPECTOR = SPRM.defaults()              # the original's inspector values (player controls)
TIGHTS_P = SPRM.internal(INSPECTOR)


def main():
    argv = sys.argv[sys.argv.index('--') + 1:]
    bundle, out_blend = argv[0], argv[1]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'

    body = SB.import_body(bundle, level=3)
    SB.trim_upper(body)
    SB.reshape_legs(body)
    SB.widen_upper_thigh(body)
    SB.stance(body)
    SB.slim_hips(body)
    SB.feet(body)
    SB.shade_smooth(body)
    toes_mesh = body.data.copy()          # skin keeps its real toes (seen through the stocking)
    TB.close_forefoot(body)               # the stocking is built over the closed toe box

    skin = SM.make_skin()
    body.data.materials.append(skin)

    toes_ref = bpy.data.objects.new('toes_ref', toes_mesh); scene.collection.objects.link(toes_ref)
    tights, tables = ST.build_tights(body, collider=toes_ref)      # fabric clears the real toes
    bpy.data.objects.remove(toes_ref)
    closed = body.data
    body.data = toes_mesh
    toes_mesh.materials.clear(); toes_mesh.materials.append(skin)
    SB.shade_smooth(body)
    bpy.data.meshes.remove(closed)
    knit, knit_mean = SM.knit_image()
    scene['knit_mean'] = knit_mean
    dmgL = SM.damage_image('damage_L')
    dmgR = SM.damage_image('damage_R')
    for im in (dmgL, dmgR):
        im.pack()
    mL = SM.make_tights('tights_L', dmgL, knit, knit_mean, TIGHTS_P)
    mR = SM.make_tights('tights_R', dmgR, knit, knit_mean, TIGHTS_P)
    tights.data.materials.append(mL)
    tights.data.materials.append(mR)
    caps = []
    tights.visible_shadow = True

    proxy = SK.make_proxy(body)
    skirt = SK.build_skirt_mesh(body)
    SK.setup_cloth(skirt)
    SK.drape(skirt, frames=90)
    SK.finish(skirt, SM.make_skirt())
    SS.add_floor(SM.make_floor())
    SS.setup_lights()
    SS.link_rims([body, tights, skirt] + caps)
    SS.link_top(bpy.data.objects['floor'])
    SS.link_lowfill([body, tights])
    SS.link_key([body, tights, skirt])
    SS.setup_world()
    SS.setup_cameras()
    SS.setup_render(scene)
    scene['tights_params'] = json.dumps(TIGHTS_P)
    scene['tights_inspector'] = json.dumps(INSPECTOR)
    os.makedirs(os.path.dirname(out_blend), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=out_blend, compress=False)
    print('[build] saved', out_blend)


main()
