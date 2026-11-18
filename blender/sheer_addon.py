# SHEER — Blender add-on: the original's "TensionData: Pantyhose" inspector as a sidebar panel
# (View3D > Sidebar > Pantyhose). Same fields, ranges and default values as in the video; moving a
# slider rebuilds the tights material live. Install: Preferences > Add-ons > Install... (this file,
# with the blender/ folder next to it) or run it from the Text Editor inside scene.blend.
bl_info = {
    "name": "SHEER — Pantyhose (TensionData)",
    "author": "SHEER",
    "version": (1, 0, 0),
    "blender": (4, 5, 0),
    "location": "View3D > Sidebar > Pantyhose",
    "description": "Inspector of the pantyhose tension/tear shader (values of the original demo)",
    "category": "Material",
}
import bpy, os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import sheer_params as SPRM

_busy = [False]


def _values(sc):
    td = sc.tension_data
    return {k: getattr(td, k) for k in SPRM.defaults()}


def _rebuild(self, context):
    if _busy[0]:
        return
    import sheer_materials as SM
    sc = context.scene
    insp = _values(sc)
    P = SPRM.internal(insp)
    sc['tights_inspector'] = json.dumps(insp)
    sc['tights_params'] = json.dumps(P)
    t = bpy.data.objects.get('tights')
    if t is None or 'damage_L' not in bpy.data.images:
        return
    knit = bpy.data.images.get('knit')
    if knit is None:
        knit, km = SM.knit_image(); sc['knit_mean'] = km
    km = sc.get('knit_mean', 0.5)
    old = [m for m in t.data.materials]
    t.data.materials[0] = SM.make_tights('tights_L', bpy.data.images['damage_L'], knit, km, P)
    t.data.materials[1] = SM.make_tights('tights_R', bpy.data.images['damage_R'], knit, km, P)
    for m in old:
        if m and m.users == 0:
            bpy.data.materials.remove(m)


def _make_group():
    ann = {}
    for _, _, fields in SPRM.SECTIONS:
        for key, label, val, mn, mx in fields:
            if key == 'tension_mode':
                ann[key] = bpy.props.EnumProperty(name=label, items=SPRM.TENSION_MODES, default=val, update=_rebuild)
            elif isinstance(val, int):
                ann[key] = bpy.props.IntProperty(name=label, default=val, min=mn, max=mx, update=_rebuild)
            else:
                ann[key] = bpy.props.FloatProperty(name=label, default=val, min=mn, max=mx,
                                                   precision=4 if mx <= 0.05 else 3, update=_rebuild)
    return type('SHEER_PG_TensionData', (bpy.types.PropertyGroup,), {'__annotations__': ann})


SHEER_PG_TensionData = _make_group()


class SHEER_OT_reset(bpy.types.Operator):
    bl_idname = 'sheer.reset_inspector'
    bl_label = "Reset to the video's values"

    def execute(self, context):
        _busy[0] = True
        for k, v in SPRM.defaults().items():
            setattr(context.scene.tension_data, k, v)
        _busy[0] = False
        _rebuild(None, context)
        return {'FINISHED'}


class SHEER_PT_inspector(bpy.types.Panel):
    bl_label = 'TensionData: Pantyhose'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Pantyhose'

    def draw(self, context):
        td = context.scene.tension_data
        for zh, en, fields in SPRM.SECTIONS:
            box = self.layout.box()
            box.label(text=('%s  %s' % (zh, en)).strip())
            for key, label, val, mn, mx in fields:
                box.prop(td, key, slider=not isinstance(val, (int, str)) and key != 'wrinkle_strength')
        self.layout.operator('sheer.reset_inspector', icon='LOOP_BACK')


classes = (SHEER_PG_TensionData, SHEER_OT_reset, SHEER_PT_inspector)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.tension_data = bpy.props.PointerProperty(type=SHEER_PG_TensionData)


def unregister():
    del bpy.types.Scene.tension_data
    for c in reversed(classes):
        bpy.utils.unregister_class(c)


if __name__ == '__main__':
    register()
