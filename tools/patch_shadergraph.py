#!/usr/bin/env python3
# SHEER — turns HDRP's default Shader Graphs (created in batch mode by unity/Assets/SheerSetup/Editor/GraphSetup.cs,
# so the target settings are serialized by Unity) into the Sheer materials: blackboard properties, input nodes,
# a File-mode Custom Function calling the HLSL surface function, output blocks and material settings.
# Idempotent: re-running rebuilds the Sheer wiring from the pristine default kept next to each graph (*.orig).
# Usage: python3 tools/patch_shadergraph.py unity/Assets/Sheer/Graphs
import json, os, shutil, sys, uuid

HDRP_SKIN_PROFILE = '404820c4cf36ad944862fa59c56064f0'
# dyed nylon yarn albedo: fitted to the original's pulled tents (nylon seen against the backdrop: 42,42,47 sRGB at 13.1 s)
YARN_COLOR = (0.016, 0.015, 0.019, 1.0)
FROST_COLOR = (0.060, 0.050, 0.058, 1.0)                   # the worn knit's matte haze ('frost'): what the stocking looks like on the leg
SKIN_NYLON_SHADOW, SKIN_NYLON_TINT = 0.0, (1.0, 1.0, 1.0, 1.0)   # light into the skin crosses the yarn too (double pass; fitted 2026-11-14)      # HDRP package: Runtime/RenderPipelineResources/SkinDiffusionProfile.asset

# TensionData inspector -> material properties (reference name, video value); same names as TensionData.Push()
TIGHTS_PROPS = [
    ('_NormalStrength', 1.0), ('_WeaveTiling', 12.0), ('_WeaveNormalStrength', 0.845), ('_WeaveContrast', 0.025),
    ('_TensionMode', 1.0), ('_WrinkleStrength', 9.0), ('_TensionNormalBoost', 1.5),
    ('_PearlStrength', 0.387), ('_PearlGrainScale', 572.0), ('_PearlRandomness', 0.435), ('_PearlSpecularStrength', 0.64),
    ('_PearlEdgeStrength', 0.128), ('_PearlEdgeStart', 0.0), ('_PearlEdgeWidthPower', 0.54), ('_PearlPullEdgeWidth', 0.0122),
    ('_PearlGlintStrength', 0.85), ('_PearlGlintDensity', 0.117),
    ('_FrostBodyCoverage', 0.829), ('_FrostFootCoverage', 0.889), ('_FrostClearAtStretch', 1.0), ('_FrostMatteSmoothness', 0.837),
    ('_FrostBoundaryStrength', 1.0), ('_FrostBoundaryWidthM', 5.9 * 0.0076), ('_KnitMean', 0.8),
    ('_PreExp', 0.8),                                         # internal: static pre-stretch -> see-through
    ('_SheenGain', 1.0),                                      # internal: fibre sheen albedo per unit pearl edge strength
    ('_NylonShadow', 1.0),                                    # the yarn's shadow on what lies behind it (in its own opacity)
    ('_AngleFalloff', 0.4),                                   # view-angle exponent of the knit's opacity
    ('_LiftShadow', 0.25),                                    # share of the yarn's shadow kept by nylon lifted off the skin
    ('_DebugTension', 0.0),                                   # look-dev: draw the cloth simulation's stretch / squeeze / lift
]


# ------------------------------------------------------------------------------------------ multi-JSON io
def load(path):
    txt = open(path).read(); dec = json.JSONDecoder(); i = 0; objs = []
    while i < len(txt):
        while i < len(txt) and txt[i].isspace():
            i += 1
        if i >= len(txt):
            break
        o, j = dec.raw_decode(txt, i); objs.append(o); i = j
    return objs


def save(path, objs):
    with open(path, 'w') as fh:
        fh.write('\n\n'.join(json.dumps(o, indent=4) for o in objs) + '\n')


def nid():
    return uuid.uuid4().hex


def meta_guid(path):
    for line in open(path + '.meta'):
        if line.startswith('guid:'):
            return line.split()[1]
    raise RuntimeError('no guid in ' + path + '.meta')


# ------------------------------------------------------------------------------------------ slots
SG = 'UnityEditor.ShaderGraph.'


def _slot(typ, sid, name, io, stage=3, out_name=None, **kw):
    s = {"m_SGVersion": 0, "m_Type": typ if '.' in typ else SG + typ, "m_ObjectId": nid(), "m_Id": sid,
         "m_DisplayName": name, "m_SlotType": io, "m_Hidden": False, "m_ShaderOutputName": out_name or name,
         "m_StageCapability": stage}
    s.update(kw)
    return s


def _vec(n, v=0.0):
    return v if n == 1 else {k: v for k in 'xyzw'[:n]}


def vslot(n, sid, name, io, stage=3, out_name=None, value=0.0):
    t = {1: 'Vector1MaterialSlot', 2: 'Vector2MaterialSlot', 3: 'Vector3MaterialSlot', 4: 'Vector4MaterialSlot'}[n]
    return _slot(t, sid, name, io, stage, out_name, m_Value=_vec(n, value), m_DefaultValue=_vec(n, value), m_Labels=[])


def tex_in(sid, name):
    return _slot('Texture2DInputMaterialSlot', sid, name, 0, m_BareResource=False,
                 m_Texture={"m_SerializedTexture": "{\"texture\":{\"instanceID\":0}}", "m_Guid": ""}, m_DefaultType=0)


def sampler_in(sid, name):
    return _slot('SamplerStateMaterialSlot', sid, name, 0, m_BareResource=False)


# block slots (input, fragment stage)
def block_slot(desc):
    name = desc.split('.')[-1]
    common = dict(m_HideConnector=False, m_CustomBinding="", m_Labels=[])
    if name in ('BaseColor', 'Specular'):
        disp = 'Base Color' if name == 'BaseColor' else 'Specular Color'
        v = 0.5 if name == 'BaseColor' else 0.04
        return _slot('ColorRGBMaterialSlot', 0, disp, 0, 2, name, m_Value=_vec(3, v), m_DefaultValue=_vec(3, v),
                     m_ColorMode=0, m_DefaultColor={"r": v, "g": v, "b": v, "a": 1.0}, **common)
    if name in ('NormalWS', 'NormalTS', 'BentNormal'):
        sp = {'NormalWS': 2, 'NormalTS': 3, 'BentNormal': 3}[name]
        disp = {'NormalWS': 'Normal (World Space)', 'NormalTS': 'Normal (Tangent Space)', 'BentNormal': 'Bent Normal'}[name]
        return _slot('NormalMaterialSlot', 0, disp, 0, 2, name, m_Value=_vec(3), m_DefaultValue=_vec(3), m_Space=sp, **common)
    if name in ('TangentWS', 'TangentTS'):
        sp = 2 if name == 'TangentWS' else 3
        disp = 'Tangent (World Space)' if name == 'TangentWS' else 'Tangent (Tangent Space)'
        return _slot('TangentMaterialSlot', 0, disp, 0, 2, name, m_Value=_vec(3), m_DefaultValue=_vec(3), m_Space=sp, **common)
    if name == 'Emission':
        return _slot('ColorRGBMaterialSlot', 0, 'Emission', 0, 2, name, m_Value=_vec(3), m_DefaultValue=_vec(3),
                     m_ColorMode=1, m_DefaultColor={"r": 0.0, "g": 0.0, "b": 0.0, "a": 1.0}, **common)
    if name == 'DiffusionProfileHash':
        ser = json.dumps({"diffusionProfileAsset": {"fileID": 11400000, "guid": HDRP_SKIN_PROFILE, "type": 2}}, indent=4)
        return _slot('UnityEditor.Rendering.HighDefinition.DiffusionProfileInputMaterialSlot', 0, 'Diffusion Profile', 0, 2,
                     name, m_Value=0.0, m_DefaultValue=0.0, m_Labels=[],
                     m_DiffusionProfile={"selectedEntry": 0, "popupEntries": []}, m_SerializedDiffusionProfile=ser, m_Version=1)
    defaults = {'Smoothness': 0.5, 'Alpha': 1.0, 'Occlusion': 1.0, 'Metallic': 0.0, 'Anisotropy': 0.0,
                'SubsurfaceMask': 1.0, 'CoatMask': 0.0, 'Thickness': 1.0}
    disp = {'Occlusion': 'Ambient Occlusion', 'SubsurfaceMask': 'Subsurface Mask', 'CoatMask': 'Coat Mask'}.get(name, name)
    v = defaults.get(name, 0.0)
    return _slot('Vector1MaterialSlot', 0, disp, 0, 2, name, m_Value=v, m_DefaultValue=v, m_LiteralMode=False, **common)


# ------------------------------------------------------------------------------------------ graph editing
class Graph:
    def __init__(self, path):
        self.path = path
        self.objs = load(path)
        self.g = self.objs[0]
        self.byid = {o['m_ObjectId']: o for o in self.objs}
        self.col = {}

    def add(self, o):
        self.objs.append(o); self.byid[o['m_ObjectId']] = o
        return o

    def drop(self, oid):
        o = self.byid.pop(oid, None)
        if o is not None:
            self.objs.remove(o)

    def data(self, name):
        return [o for o in self.objs if o['m_Type'].split('.')[-1] == name]

    def node(self, typ, name, slots, col=0, sgver=0, **kw):
        y = self.col.get(col, 0); self.col[col] = y + 170
        o = {"m_SGVersion": sgver, "m_Type": SG + typ, "m_ObjectId": nid(), "m_Group": {"m_Id": ""}, "m_Name": name,
             "m_DrawState": {"m_Expanded": True, "m_Position": {"serializedVersion": "2", "x": -1500.0 + 380 * col,
                                                                "y": float(y), "width": 220.0, "height": 150.0}},
             "m_Slots": [{"m_Id": s['m_ObjectId']} for s in slots], "synonyms": [], "m_Precision": 0,
             "m_PreviewExpanded": False, "m_DismissedVersion": 0, "m_PreviewMode": 0,
             "m_CustomColors": {"m_SerializableColors": []}}
        o.update(kw)
        for s in slots:
            self.add(s)
        self.add(o)
        self.g['m_Nodes'].append({"m_Id": o['m_ObjectId']})
        return o

    def edge(self, src, sslot, dst, dslot):
        self.g['m_Edges'].append({"m_OutputSlot": {"m_Node": {"m_Id": src['m_ObjectId']}, "m_SlotId": sslot},
                                  "m_InputSlot": {"m_Node": {"m_Id": dst['m_ObjectId']}, "m_SlotId": dslot}})

    # --- blackboard
    def _category(self):
        return self.byid[self.g['m_CategoryData'][0]['m_Id']]

    def _prop_common(self, typ, ref, sgver=1):
        disp = ref.lstrip('_')
        return {"m_SGVersion": sgver, "m_Type": typ, "m_ObjectId": nid(), "m_Guid": {"m_GuidSerialized": str(uuid.uuid4())},
                "m_Name": disp, "m_DefaultRefNameVersion": 1, "m_RefNameGeneratedByDisplayName": disp,
                "m_DefaultReferenceName": ref, "m_OverrideReferenceName": "", "m_GeneratePropertyBlock": True,
                "m_UseCustomSlotLabel": False, "m_CustomSlotLabel": "", "m_DismissedVersion": 0, "m_Precision": 0,
                "overrideHLSLDeclaration": False, "hlslDeclarationOverride": 0, "m_Hidden": False}

    def _register(self, p):
        self.add(p)
        self.g['m_Properties'].append({"m_Id": p['m_ObjectId']})
        self._category()['m_ChildObjectList'].append({"m_Id": p['m_ObjectId']})
        return p

    def float_prop(self, ref, value):
        p = self._prop_common(SG + 'Internal.Vector1ShaderProperty', ref)
        p.update({"m_PerRendererData": False, "m_customAttributes": [], "m_Value": float(value), "m_FloatType": 0,
                  "m_RangeValues": {"x": 0.0, "y": 1.0}, "m_SliderType": 0, "m_SliderPower": 3.0, "m_EnumType": 0,
                  "m_CSharpEnumString": "", "m_EnumNames": ["Default"], "m_EnumValues": [0]})
        return self._register(p)

    def vector4_prop(self, ref, value):
        p = self._prop_common(SG + 'Internal.Vector4ShaderProperty', ref)
        p.update({"m_PerRendererData": False, "m_customAttributes": [],
                  "m_Value": {"x": float(value[0]), "y": float(value[1]), "z": float(value[2]), "w": float(value[3])}})
        return self._register(p)

    def texture_prop(self, ref, col=0, default=0):
        """default: 0 white, 1 black, 2 grey (what an unassigned texture reads as)."""
        p = self._prop_common(SG + 'Internal.Texture2DShaderProperty', ref, sgver=0)
        p.update({"m_Value": {"m_SerializedTexture": "{\"texture\":{\"instanceID\":0}}", "m_Guid": ""},
                  "isMainTexture": False, "useTilingAndOffset": False, "m_Modifiable": True, "m_DefaultType": default})
        self._register(p)
        out = _slot('Texture2DMaterialSlot', 0, ref.lstrip('_'), 1, out_name='Out', m_BareResource=False)
        return self.node('PropertyNode', 'Property', [out], col=col, m_Property={"m_Id": p['m_ObjectId']})

    # --- input nodes
    def uv(self, channel, col=0):
        return self.node('UVNode', 'UV', [vslot(4, 0, 'Out', 1)], col=col, m_OutputChannel=channel)

    def vector(self, typ, name, space, col=0, sgver=0, **kw):
        return self.node(typ, name, [vslot(3, 0, 'Out', 1)], col=col, sgver=sgver, m_Space=space, **kw)

    def custom_function(self, func, source_guid, ins, outs, col=1):
        slots = []; sid = 0
        for kind, name in ins:
            slots.append(tex_in(sid, name) if kind == 'tex' else sampler_in(sid, name) if kind == 'smp' else vslot(kind, sid, name, 0))
            sid += 1
        for n, name in outs:
            slots.append(vslot(n, sid, name, 1)); sid += 1
        node = self.node('CustomFunctionNode', func + ' (Custom Function)', slots, col=col, sgver=1,
                         m_SourceType=0, m_FunctionName=func, m_FunctionSource=source_guid, m_FunctionBody="")
        node['_index'] = {name: i for i, (_, name) in enumerate(list(ins) + list(outs))}
        return node

    # --- master stack
    def set_fragment_blocks(self, descriptors):
        want = ['SurfaceDescription.' + d for d in descriptors]
        blocks = {self.byid[b['m_Id']]['m_SerializedDescriptor']: self.byid[b['m_Id']] for b in self.g['m_FragmentContext']['m_Blocks']}
        for desc, blk in blocks.items():
            if desc not in want:
                for s in blk['m_Slots']:
                    self.drop(s['m_Id'])
                self.drop(blk['m_ObjectId'])
                self.g['m_Nodes'] = [n for n in self.g['m_Nodes'] if n['m_Id'] != blk['m_ObjectId']]
        order = []
        for desc in want:
            blk = blocks.get(desc)
            if blk is None:
                s = block_slot(desc)
                blk = {"m_SGVersion": 0, "m_Type": SG + 'BlockNode', "m_ObjectId": nid(), "m_Group": {"m_Id": ""},
                       "m_Name": desc, "m_DrawState": {"m_Expanded": True, "m_Position": {"serializedVersion": "2", "x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}},
                       "m_Slots": [{"m_Id": s['m_ObjectId']}], "synonyms": [], "m_Precision": 0, "m_PreviewExpanded": True,
                       "m_DismissedVersion": 0, "m_PreviewMode": 0, "m_CustomColors": {"m_SerializableColors": []},
                       "m_SerializedDescriptor": desc}
                self.add(s); self.add(blk); self.g['m_Nodes'].append({"m_Id": blk['m_ObjectId']})
            order.append(blk)
        self.g['m_FragmentContext']['m_Blocks'] = [{"m_Id": b['m_ObjectId']} for b in order]
        return {b['m_SerializedDescriptor'].split('.')[-1]: b for b in order}

    def vertex_blocks(self):
        return {self.byid[b['m_Id']]['m_SerializedDescriptor'].split('.')[-1]: self.byid[b['m_Id']]
                for b in self.g['m_VertexContext']['m_Blocks']}

    def finish(self):
        for o in self.objs:
            o.pop('_index', None)
        save(self.path, self.objs)


def velocity_block(G, cf):
    """HDRP 'custom velocity': the vertex function's Velocity output (object space, per frame) feeds the motion vectors."""
    G.data('SystemData')[0]['m_CustomVelocity'] = True
    s = vslot(3, 0, 'Velocity', 0, stage=1, out_name='CustomVelocity')
    s.update(m_HideConnector=False, m_CustomBinding="")
    desc = 'VertexDescription.CustomVelocity'
    blk = {"m_SGVersion": 0, "m_Type": SG + 'BlockNode', "m_ObjectId": nid(), "m_Group": {"m_Id": ""}, "m_Name": desc,
           "m_DrawState": {"m_Expanded": True, "m_Position": {"serializedVersion": "2", "x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}},
           "m_Slots": [{"m_Id": s['m_ObjectId']}], "synonyms": [], "m_Precision": 0, "m_PreviewExpanded": True,
           "m_DismissedVersion": 0, "m_PreviewMode": 0, "m_CustomColors": {"m_SerializableColors": []},
           "m_SerializedDescriptor": desc}
    G.add(s); G.add(blk); G.g['m_Nodes'].append({"m_Id": blk['m_ObjectId']})
    G.g['m_VertexContext']['m_Blocks'].append({"m_Id": blk['m_ObjectId']})
    G.edge(cf, cf['_index']['Velocity'], blk, 0)


def wire(G, cf, blocks, mapping):
    for out_name, block in mapping.items():
        G.edge(cf, cf['_index'][out_name], blocks[block], 0)


# ------------------------------------------------------------------------------------------ the four materials
# (2026-11-15: drawing the stocking double-sided was tried against a thin bare line under ankle sails: it did not remove
#  the line and halved the frame rate - the scene is bound by triangle count, 284k vertices per pass - so it stays
#  single-sided, back faces culled.)
def cloth_inputs(G, cloth_guid, velocity=True):
    """Cloth simulation textures of this leg (TightsSim sets them per submesh) + the vertex stage that applies the
    pulled fabric's displacement (SheerClothVertex_float in SheerCloth.hlsl). Returns the tension texture node.
    velocity: also feed the fabric's motion since the previous frame to HDRP's motion vectors."""
    disp = G.texture_prop('_ClothDisp', col=-1, default=1); nrm = G.texture_prop('_ClothNrm', col=-1, default=1)
    tens = G.texture_prop('_ClothTens', col=-1, default=0); dprev = G.texture_prop('_ClothDispPrev', col=-1, default=1)
    pos = G.vector('PositionNode', 'Position', 0, col=-1, sgver=1, m_PositionSource=0)
    nor = G.vector('NormalVectorNode', 'Normal Vector', 0, col=-1)
    tan = G.vector('TangentVectorNode', 'Tangent Vector', 0, col=-1)
    uv0 = G.uv(0, col=-1); uv1 = G.uv(1, col=-1); uv2 = G.uv(2, col=-1)
    cf = G.custom_function('SheerClothVertex', cloth_guid,
                           [(3, 'PositionOS'), (3, 'NormalOS'), (3, 'TangentOS'), (4, 'UV0'), (4, 'UV1'), (4, 'UV2'), ('tex', 'Disp'), ('tex', 'Nrm'),
                            ('tex', 'DispPrev')],
                           [(3, 'PositionOut'), (3, 'NormalOut'), (3, 'TangentOut'), (3, 'Velocity')], col=0)
    for n, name in ((pos, 'PositionOS'), (nor, 'NormalOS'), (tan, 'TangentOS'), (uv0, 'UV0'), (uv1, 'UV1'), (uv2, 'UV2'), (disp, 'Disp'), (nrm, 'Nrm'),
                    (dprev, 'DispPrev')):
        G.edge(n, 0, cf, cf['_index'][name])
    vb = G.vertex_blocks()
    for out_name, block in (('PositionOut', 'Position'), ('NormalOut', 'Normal'), ('TangentOut', 'Tangent')):
        G.edge(cf, cf['_index'][out_name], vb[block], 0)
    if velocity:
        velocity_block(G, cf)
    return tens, disp


def patch_tights(G, hlsl_guid, cloth_guid):
    sd = G.data('SystemData')[0]
    sd.update(m_SurfaceType=1, m_RenderingPass=4, m_BlendMode=0, m_ZWrite=False, m_TransparentDepthPrepass=True,
              m_TransparentDepthPostpass=True, m_TransparentCullMode=2, m_DoubleSidedMode=0)
    for bd in G.data('BuiltinData'):
        bd.update(m_TransparentDepthPrepass=True, m_TransparentDepthPostpass=True, m_TransparentWritesMotionVec=True)
    for ld in G.data('LightingData'):
        ld.update(m_NormalDropOffSpace=2, m_BlendPreserveSpecular=False)   # specular comes from the yarn: scaled by coverage
    G.data('StackLitData')[0].update(m_BaseParametrization=1, m_Anisotropy=True)
    for ref, v in TIGHTS_PROPS:
        G.float_prop(ref, v)
    G.vector4_prop('_YarnColor', YARN_COLOR)
    G.vector4_prop('_FrostColor', FROST_COLOR)
    dmg = G.texture_prop('_DamageTex'); dmgb = G.texture_prop('_DamageTexB', default=1); dmgc = G.texture_prop('_DamageTexC', default=1); weave = G.texture_prop('_WeaveMap')
    tens, disp = cloth_inputs(G, cloth_guid)
    uv = [G.uv(c) for c in range(4)]
    pos = G.vector('PositionNode', 'Position', 2, sgver=1, m_PositionSource=0)
    nrm = G.vector('NormalVectorNode', 'Normal Vector', 2)
    tan = G.vector('TangentVectorNode', 'Tangent Vector', 2)
    bit = G.vector('BitangentVectorNode', 'Bitangent Vector', 2)
    view = G.vector('ViewDirectionNode', 'View Direction', 2, sgver=1)
    ins = [(4, 'UV0'), (4, 'UV1'), (4, 'UV2'), (4, 'UV3'), (3, 'PositionWS'), (3, 'NormalWS'), (3, 'TangentWS'),
           (3, 'BitangentWS'), (3, 'ViewDirWS'), ('tex', 'DamageTex'), ('tex', 'DamageTexB'), ('tex', 'DamageTexC'), ('tex', 'WeaveTex'), ('tex', 'TensTex'), ('tex', 'DispTex'), ('smp', 'Sampler')]
    outs = [(3, 'BaseColor'), (3, 'SpecularColor'), (1, 'Smoothness'), (1, 'Anisotropy'), (3, 'NormalOut'), (3, 'TangentOut'), (1, 'Alpha')]
    cf = G.custom_function('SheerTights', hlsl_guid, ins, outs)
    for i, n in enumerate(uv):
        G.edge(n, 0, cf, i)
    for n, name in ((pos, 'PositionWS'), (nrm, 'NormalWS'), (tan, 'TangentWS'), (bit, 'BitangentWS'), (view, 'ViewDirWS')):
        G.edge(n, 0, cf, cf['_index'][name])
    G.edge(dmg, 0, cf, cf['_index']['DamageTex']); G.edge(weave, 0, cf, cf['_index']['WeaveTex'])
    G.edge(dmgb, 0, cf, cf['_index']['DamageTexB']); G.edge(dmgc, 0, cf, cf['_index']['DamageTexC'])
    G.edge(tens, 0, cf, cf['_index']['TensTex']); G.edge(disp, 0, cf, cf['_index']['DispTex'])
    blocks = G.set_fragment_blocks(['BaseColor', 'NormalWS', 'BentNormal', 'TangentWS', 'Anisotropy', 'Specular',
                                    'Smoothness', 'Emission', 'Occlusion', 'Alpha'])
    wire(G, cf, blocks, {'BaseColor': 'BaseColor', 'SpecularColor': 'Specular', 'Smoothness': 'Smoothness',
                         'Anisotropy': 'Anisotropy', 'NormalOut': 'NormalWS', 'TangentOut': 'TangentWS', 'Alpha': 'Alpha'})


def patch_tights_lit(G, hlsl_guid, cloth_guid):
    """Same nylon on HDRP Lit (transparent, specular-colour material type) - A/B against StackLit."""
    sd = G.data('SystemData')[0]
    sd.update(m_SurfaceType=1, m_RenderingPass=4, m_BlendMode=0, m_ZWrite=False, m_TransparentDepthPrepass=True,
              m_TransparentDepthPostpass=True, m_TransparentCullMode=2, m_DoubleSidedMode=0)
    for bd in G.data('BuiltinData'):
        bd.update(m_TransparentDepthPrepass=True, m_TransparentDepthPostpass=True, m_TransparentWritesMotionVec=True)
    for ld in G.data('LightingData'):
        ld.update(m_NormalDropOffSpace=2, m_BlendPreserveSpecular=False)
    G.data('HDLitData')[0].update(m_MaterialTypeMask=16)                 # LitSpecular (specular colour)
    for ref, v in TIGHTS_PROPS:
        G.float_prop(ref, v)
    G.vector4_prop('_YarnColor', YARN_COLOR)
    G.vector4_prop('_FrostColor', FROST_COLOR)
    dmg = G.texture_prop('_DamageTex'); dmgb = G.texture_prop('_DamageTexB', default=1); dmgc = G.texture_prop('_DamageTexC', default=1); weave = G.texture_prop('_WeaveMap')
    tens, disp = cloth_inputs(G, cloth_guid)
    uv = [G.uv(c) for c in range(4)]
    pos = G.vector('PositionNode', 'Position', 2, sgver=1, m_PositionSource=0)
    nrm = G.vector('NormalVectorNode', 'Normal Vector', 2)
    tan = G.vector('TangentVectorNode', 'Tangent Vector', 2)
    bit = G.vector('BitangentVectorNode', 'Bitangent Vector', 2)
    view = G.vector('ViewDirectionNode', 'View Direction', 2, sgver=1)
    ins = [(4, 'UV0'), (4, 'UV1'), (4, 'UV2'), (4, 'UV3'), (3, 'PositionWS'), (3, 'NormalWS'), (3, 'TangentWS'),
           (3, 'BitangentWS'), (3, 'ViewDirWS'), ('tex', 'DamageTex'), ('tex', 'DamageTexB'), ('tex', 'DamageTexC'), ('tex', 'WeaveTex'), ('tex', 'TensTex'), ('tex', 'DispTex'), ('smp', 'Sampler')]
    outs = [(3, 'BaseColor'), (3, 'SpecularColor'), (1, 'Smoothness'), (1, 'Anisotropy'), (3, 'NormalOut'), (3, 'TangentOut'), (1, 'Alpha')]
    cf = G.custom_function('SheerTights', hlsl_guid, ins, outs)
    for i, n in enumerate(uv):
        G.edge(n, 0, cf, i)
    for n, name in ((pos, 'PositionWS'), (nrm, 'NormalWS'), (tan, 'TangentWS'), (bit, 'BitangentWS'), (view, 'ViewDirWS')):
        G.edge(n, 0, cf, cf['_index'][name])
    G.edge(dmg, 0, cf, cf['_index']['DamageTex']); G.edge(weave, 0, cf, cf['_index']['WeaveTex'])
    G.edge(dmgb, 0, cf, cf['_index']['DamageTexB']); G.edge(dmgc, 0, cf, cf['_index']['DamageTexC'])
    G.edge(tens, 0, cf, cf['_index']['TensTex']); G.edge(disp, 0, cf, cf['_index']['DispTex'])
    blocks = G.set_fragment_blocks(['BaseColor', 'NormalWS', 'BentNormal', 'Specular', 'Smoothness', 'Emission', 'Occlusion', 'Alpha'])
    wire(G, cf, blocks, {'BaseColor': 'BaseColor', 'SpecularColor': 'Specular', 'Smoothness': 'Smoothness',
                         'NormalOut': 'NormalWS', 'Alpha': 'Alpha'})


def patch_tights_sheen(G, hlsl_guid, cloth_guid):
    """Fibre sheen of the nylon (Charlie lobe, HDRP Fabric cotton/wool) as an additive pass over the StackLit nylon:
    HDRP has no single master with diffuse + anisotropic GGX + sheen; the back-lit rim of the stockings is this lobe."""
    sd = G.data('SystemData')[0]
    sd.update(m_SurfaceType=1, m_RenderingPass=4, m_BlendMode=1, m_ZWrite=False, m_TransparentDepthPrepass=False,
              m_TransparentDepthPostpass=False, m_TransparentCullMode=2, m_DoubleSidedMode=0, m_SortPriority=1)
    for bd in G.data('BuiltinData'):
        bd.update(m_TransparentDepthPrepass=False, m_TransparentDepthPostpass=False, m_TransparentWritesMotionVec=False)
    for ld in G.data('LightingData'):
        ld.update(m_NormalDropOffSpace=2, m_BlendPreserveSpecular=False, m_ReceiveSSR=False, m_SpecularOcclusionMode=0)
    G.data('FabricData')[0].update(m_MaterialType=0, m_EnergyConservingSpecular=False)
    for ref, v in TIGHTS_PROPS:
        G.float_prop(ref, v)
    G.vector4_prop('_YarnColor', YARN_COLOR)
    G.vector4_prop('_FrostColor', FROST_COLOR)
    dmg = G.texture_prop('_DamageTex'); dmgb = G.texture_prop('_DamageTexB', default=1); dmgc = G.texture_prop('_DamageTexC', default=1); weave = G.texture_prop('_WeaveMap')
    tens, disp = cloth_inputs(G, cloth_guid, velocity=False)
    uv = [G.uv(c) for c in range(4)]
    pos = G.vector('PositionNode', 'Position', 2, sgver=1, m_PositionSource=0)
    nrm = G.vector('NormalVectorNode', 'Normal Vector', 2)
    tan = G.vector('TangentVectorNode', 'Tangent Vector', 2)
    bit = G.vector('BitangentVectorNode', 'Bitangent Vector', 2)
    view = G.vector('ViewDirectionNode', 'View Direction', 2, sgver=1)
    ins = [(4, 'UV0'), (4, 'UV1'), (4, 'UV2'), (4, 'UV3'), (3, 'PositionWS'), (3, 'NormalWS'), (3, 'TangentWS'),
           (3, 'BitangentWS'), (3, 'ViewDirWS'), ('tex', 'DamageTex'), ('tex', 'DamageTexB'), ('tex', 'DamageTexC'), ('tex', 'WeaveTex'), ('tex', 'TensTex'), ('tex', 'DispTex'), ('smp', 'Sampler')]
    outs = [(3, 'BaseColor'), (3, 'SheenColor'), (1, 'Smoothness'), (3, 'NormalOut'), (1, 'Alpha')]
    cf = G.custom_function('SheerTightsSheen', hlsl_guid, ins, outs)
    for i, n in enumerate(uv):
        G.edge(n, 0, cf, i)
    for n, name in ((pos, 'PositionWS'), (nrm, 'NormalWS'), (tan, 'TangentWS'), (bit, 'BitangentWS'), (view, 'ViewDirWS')):
        G.edge(n, 0, cf, cf['_index'][name])
    G.edge(dmg, 0, cf, cf['_index']['DamageTex']); G.edge(weave, 0, cf, cf['_index']['WeaveTex'])
    G.edge(dmgb, 0, cf, cf['_index']['DamageTexB']); G.edge(dmgc, 0, cf, cf['_index']['DamageTexC'])
    G.edge(tens, 0, cf, cf['_index']['TensTex']); G.edge(disp, 0, cf, cf['_index']['DispTex'])
    blocks = G.set_fragment_blocks(['BaseColor', 'NormalWS', 'BentNormal', 'Smoothness', 'Occlusion', 'Specular', 'Emission', 'Alpha'])
    wire(G, cf, blocks, {'BaseColor': 'BaseColor', 'SheenColor': 'Specular', 'Smoothness': 'Smoothness',
                         'NormalOut': 'NormalWS', 'Alpha': 'Alpha'})


def patch_lit_common(G, double_sided=0):
    for ld in G.data('LightingData'):
        ld.update(m_NormalDropOffSpace=2)
    G.data('SystemData')[0].update(m_DoubleSidedMode=double_sided)


def pose_vertex(G, cloth_guid):
    """Vertex stage of a posed, otherwise static mesh (the body): SheerPoseVertex_float in SheerCloth.hlsl."""
    pos = G.vector('PositionNode', 'Position', 0, col=-1, sgver=1, m_PositionSource=0)
    nor = G.vector('NormalVectorNode', 'Normal Vector', 0, col=-1)
    tan = G.vector('TangentVectorNode', 'Tangent Vector', 0, col=-1)
    cf = G.custom_function('SheerPoseVertex', cloth_guid, [(3, 'PositionOS'), (3, 'NormalOS'), (3, 'TangentOS')],
                           [(3, 'PositionOut'), (3, 'NormalOut'), (3, 'TangentOut'), (3, 'Velocity')], col=0)
    for n, name in ((pos, 'PositionOS'), (nor, 'NormalOS'), (tan, 'TangentOS')):
        G.edge(n, 0, cf, cf['_index'][name])
    vb = G.vertex_blocks()
    for out_name, block in (('PositionOut', 'Position'), ('NormalOut', 'Normal'), ('TangentOut', 'Tangent')):
        G.edge(cf, cf['_index'][out_name], vb[block], 0)
    velocity_block(G, cf)


def patch_skin(G, guid, cloth_guid):
    patch_lit_common(G)
    pose_vertex(G, cloth_guid)
    sss = os.environ.get('SHEER_SKIN_SSS', '1') == '1'
    G.data('HDLitData')[0].update(m_MaterialTypeMask=1 if sss else 2, m_SSSTransmission=False, m_ClearCoat=True)    # SSS + clear coat
    # light reaching the skin under the intact nylon (see SheerSkin_float): shadow by ~30% of the coverage, yarn tint
    G.float_prop('_SkinNylonShadow', SKIN_NYLON_SHADOW)
    G.float_prop('_FrostBodyCoverage', 0.829)
    G.float_prop('_SkinLiftShade', 0.4)                 # soft shadow of lifted nylon on the skin under it (also keeps a
    # sliver of skin that shows where a pulled fold turns its inside to the camera from reading as bare, lit skin)
    G.float_prop('_SkinRose', 1.0)                      # rosy knees / ankles (strength)
    G.float_prop('_SkinPale', 1.0)                      # pale, cool thigh and shin (strength)
    G.float_prop('_SkinMottle', 1.0)                    # faint mottling
    G.float_prop('_SkinRimShade', 1.0)                  # contact shadow of the torn edge inside a hole
    G.vector4_prop('_SkinNylonTint', SKIN_NYLON_TINT)
    dl = G.texture_prop('_DamageTexL'); dr = G.texture_prop('_DamageTexR')
    ll = G.texture_prop('_ClothDispL', default=1); lr = G.texture_prop('_ClothDispR', default=1)
    uv1 = G.uv(1); uv2 = G.uv(2); pos = G.vector('PositionNode', 'Position', 2, sgver=1, m_PositionSource=0)
    nrm = G.vector('NormalVectorNode', 'Normal Vector', 2)
    cf = G.custom_function('SheerSkin', guid, [(3, 'Rest'), (4, 'Leg'), (3, 'PositionWS'), (3, 'NormalWS'), ('tex', 'DamageL'), ('tex', 'DamageR'),
                                               ('tex', 'LiftL'), ('tex', 'LiftR')],
                           [(3, 'BaseColor'), (1, 'Smoothness'), (3, 'NormalOut'), (1, 'CoatMask')])
    G.edge(uv1, 0, cf, 0); G.edge(uv2, 0, cf, 1); G.edge(pos, 0, cf, 2); G.edge(nrm, 0, cf, 3); G.edge(dl, 0, cf, 4); G.edge(dr, 0, cf, 5)
    G.edge(ll, 0, cf, 6); G.edge(lr, 0, cf, 7)
    blocks = G.set_fragment_blocks(['BaseColor', 'NormalWS', 'BentNormal', 'Smoothness', 'Emission', 'Occlusion', 'Alpha',
                                    'SubsurfaceMask', 'DiffusionProfileHash', 'CoatMask'])
    wire(G, cf, blocks, {'BaseColor': 'BaseColor', 'Smoothness': 'Smoothness', 'NormalOut': 'NormalWS', 'CoatMask': 'CoatMask'})


def patch_skirt(G, guid):
    patch_lit_common(G, double_sided=2)                  # single-layer cloth: flipped normals on the back side
    uv0 = G.uv(0); uv1 = G.uv(1); pos = G.vector('PositionNode', 'Position', 2, sgver=1, m_PositionSource=0)
    nrm = G.vector('NormalVectorNode', 'Normal Vector', 2)
    cf = G.custom_function('SheerSkirt', guid, [(2, 'UV'), (3, 'Rest'), (3, 'PositionWS'), (3, 'NormalWS')],
                           [(3, 'BaseColor'), (1, 'Smoothness'), (3, 'NormalOut'), (3, 'SheenColor')])
    G.edge(uv0, 0, cf, 0); G.edge(uv1, 0, cf, 1); G.edge(pos, 0, cf, 2); G.edge(nrm, 0, cf, 3)
    blocks = G.set_fragment_blocks(['BaseColor', 'NormalWS', 'BentNormal', 'Metallic', 'Smoothness', 'Emission', 'Occlusion', 'Alpha'])
    wire(G, cf, blocks, {'BaseColor': 'BaseColor', 'Smoothness': 'Smoothness', 'NormalOut': 'NormalWS'})


def patch_floor(G, guid):
    patch_lit_common(G)
    pos_os = G.vector('PositionNode', 'Position', 0, sgver=1, m_PositionSource=0)
    pos = G.vector('PositionNode', 'Position', 2, sgver=1, m_PositionSource=0)
    nrm = G.vector('NormalVectorNode', 'Normal Vector', 2)
    cf = G.custom_function('SheerFloor', guid, [(3, 'PositionOS'), (3, 'PositionWS'), (3, 'NormalWS')],
                           [(3, 'BaseColor'), (1, 'Smoothness'), (3, 'NormalOut')])
    G.edge(pos_os, 0, cf, 0); G.edge(pos, 0, cf, 1); G.edge(nrm, 0, cf, 2)
    blocks = G.set_fragment_blocks(['BaseColor', 'NormalWS', 'BentNormal', 'Metallic', 'Smoothness', 'Emission', 'Occlusion', 'Alpha'])
    wire(G, cf, blocks, {'BaseColor': 'BaseColor', 'Smoothness': 'Smoothness', 'NormalOut': 'NormalWS'})


def patch_skirt_fabric(G, guid):
    patch_lit_common(G, double_sided=2)                  # single-layer cloth: flipped normals on the back side
    G.data('FabricData')[0].update(m_MaterialType=0)     # cotton / wool (sheen lobe)
    uv0 = G.uv(0); uv1 = G.uv(1); pos = G.vector('PositionNode', 'Position', 2, sgver=1, m_PositionSource=0)
    nrm = G.vector('NormalVectorNode', 'Normal Vector', 2)
    cf = G.custom_function('SheerSkirt', guid, [(2, 'UV'), (3, 'Rest'), (3, 'PositionWS'), (3, 'NormalWS')],
                           [(3, 'BaseColor'), (1, 'Smoothness'), (3, 'NormalOut'), (3, 'SheenColor')])
    G.edge(uv0, 0, cf, 0); G.edge(uv1, 0, cf, 1); G.edge(pos, 0, cf, 2); G.edge(nrm, 0, cf, 3)
    blocks = G.set_fragment_blocks(['BaseColor', 'NormalWS', 'BentNormal', 'Smoothness', 'Occlusion', 'Specular', 'Emission', 'Alpha'])
    wire(G, cf, blocks, {'BaseColor': 'BaseColor', 'Smoothness': 'Smoothness', 'NormalOut': 'NormalWS', 'SheenColor': 'Specular'})


def patch_backdrop(G, guid):
    G.data('SystemData')[0].update(m_DoubleSidedMode=0)
    sp = G.node('ScreenPositionNode', 'Screen Position', [vslot(4, 0, 'Out', 1)], col=0, m_ScreenSpaceType=0)
    cf = G.custom_function('SheerBackdrop', guid, [(4, 'ScreenPos')], [(3, 'Color')])
    G.edge(sp, 0, cf, 0)
    blocks = G.set_fragment_blocks(['BaseColor', 'Alpha'])
    wire(G, cf, blocks, {'Color': 'BaseColor'})


def main():
    gdir = sys.argv[1] if len(sys.argv) > 1 else 'unity/Assets/Sheer/Graphs'
    sdir = os.path.join(os.path.dirname(gdir.rstrip('/')), 'Shaders')
    tights_guid = meta_guid(os.path.join(sdir, 'SheerTights.hlsl'))
    surf_guid = meta_guid(os.path.join(sdir, 'SheerSurfaces.hlsl'))
    skin_guid = meta_guid(os.path.join(sdir, 'SheerSkin.hlsl'))
    cloth_guid = meta_guid(os.path.join(sdir, 'SheerCloth.hlsl'))
    jobs = [('SheerTights', patch_tights, tights_guid), ('SheerSkin', patch_skin, skin_guid),
            ('SheerSkirt', patch_skirt, surf_guid), ('SheerFloor', patch_floor, surf_guid),
            ('SheerBackdrop', patch_backdrop, surf_guid), ('SheerSkirtFabric', patch_skirt_fabric, surf_guid),
            ('SheerTightsLit', patch_tights_lit, tights_guid), ('SheerTightsSheen', patch_tights_sheen, tights_guid)]
    odir = os.path.join(os.path.dirname(gdir.rstrip('/')), 'GraphDefaults~')      # '~' = ignored by Unity's importer
    os.makedirs(odir, exist_ok=True)
    for name, fn, guid in jobs:
        path = os.path.join(gdir, name + '.shadergraph')
        orig = os.path.join(odir, name + '.shadergraph')
        if not os.path.exists(orig):
            shutil.copyfile(path, orig)                  # keep the pristine Unity-made default
        shutil.copyfile(orig, path)
        G = Graph(path)
        if fn in (patch_tights, patch_tights_lit, patch_tights_sheen, patch_skin):
            fn(G, guid, cloth_guid)
        else:
            fn(G, guid)
        G.finish()
        print('patched %s: %d objects, %d nodes, %d edges, %d properties' % (
            name, len(G.objs), len(G.g['m_Nodes']), len(G.g['m_Edges']), len(G.g['m_Properties'])))


if __name__ == '__main__':
    main()
