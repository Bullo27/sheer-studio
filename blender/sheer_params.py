# SHEER — the original's inspector ("TensionData: Pantyhose"), field by field, with the exact values
# shown in the video as defaults and the slider ranges read off the knob positions. These are the
# player-facing controls; internal() maps them to the shader's internal parameters. At the video's
# values the render matches the original — all calibration lives inside internal()/the shader.

SECTIONS = [
    ('', 'Weave', [
        ('normal_strength', 'Normal Strength', 1.0, 0.0, 2.0),
        ('weave_tiling', 'Weave Tiling', 12, 1, 64),
        ('weave_normal_strength', 'Weave Normal Strength', 0.845, 0.0, 1.0),
        ('weave_contrast', 'Weave Contrast', 0.025, 0.0, 1.0),
    ]),
    ('张力与褶皱', 'Tension & Wrinkles', [
        ('tension_mode', 'Tension Mode', 'STRETCH', None, None),
        ('wrinkle_strength', 'Wrinkle Strength', 9.0, 0.0, 50.0),
        ('tension_normal_boost', 'Tension Normal Boost', 1.5, 0.0, 4.0),
    ]),
    ('珠光与闪点', 'Pearl & Glints', [
        ('pearl_strength', 'Pearl Strength', 0.387, 0.0, 1.0),
        ('pearl_grain_scale', 'Pearl Grain Scale', 572.0, 0.0, 1000.0),
        ('pearl_randomness', 'Pearl Randomness', 0.435, 0.0, 1.0),
        ('pearl_specular_strength', 'Pearl Specular Strength', 0.64, 0.0, 4.0),
        ('pearl_edge_strength', 'Pearl Edge Strength', 0.128, 0.0, 1.0),
        ('pearl_edge_start', 'Pearl Edge Start', 0.0, 0.0, 1.0),
        ('pearl_edge_width_power', 'Pearl Edge Width Power', 0.54, 0.0, 5.0),
        ('pearl_pull_edge_width', 'Pearl Pull Edge Width', 0.0122, 0.001, 0.04),
        ('pearl_glint_strength', 'Pearl Glint Strength', 0.85, 0.0, 16.0),
        ('pearl_glint_density', 'Pearl Glint Density', 0.117, 0.0, 1.0),
    ]),
    ('雾面与透肤', 'Frost & Skin Show-through', [
        ('frost_body_coverage', 'Frost Body Coverage', 0.829, 0.0, 1.0),
        ('frost_foot_coverage', 'Frost Foot Coverage', 0.889, 0.0, 1.0),
        ('frost_clear_at_stretch', 'Frost Clear At Stretch', 1.0, 0.0, 1.0),
        ('frost_matte_smoothness', 'Frost Matte Smoothness', 0.837, 0.0, 1.0),
        ('frost_boundary_strength', 'Frost Boundary Strength', 1.0, 0.0, 1.0),
        ('frost_boundary_width_px', 'Frost Boundary Width (px)', 5.9, 0.0, 32.0),
    ]),
]
TENSION_MODES = [('STRETCH', 'Stretch', 'Tension from fabric stretch'),
                 ('COMPRESSION', 'Compression', 'Tension from compression'),
                 ('BOTH', 'Both', 'Stretch and compression')]


def defaults():
    return {k: v for _, _, fields in SECTIONS for (k, _, v, _, _) in fields}


def internal(insp):
    """Inspector values -> internal shader parameters (calibrated so the video's values reproduce
    the video's look)."""
    i = dict(defaults()); i.update(insp)
    return dict(
        # fixed material constants (not exposed in the original's inspector)
        fabric_color=(0.034, 0.026, 0.03), angle_falloff=0.7, threads=1.0, rung_spacing=0.0011,
        # weave
        normal_strength=i['normal_strength'], weave_tiling=float(i['weave_tiling']),
        weave_normal=i['weave_normal_strength'], weave_contrast=i['weave_contrast'],
        # tension & wrinkles
        tension_mode=i['tension_mode'], wrinkle_strength=i['wrinkle_strength'],
        tension_normal_boost=i['tension_normal_boost'],
        # pearl & glints
        pearl_strength=i['pearl_strength'], pearl_grain_scale=i['pearl_grain_scale'],
        pearl_randomness=i['pearl_randomness'], pearl_spec=i['pearl_specular_strength'],
        pearl_edge=i['pearl_edge_strength'], pearl_edge_start=i['pearl_edge_start'],
        pearl_edge_power=i['pearl_edge_width_power'], pull_edge=i['pearl_pull_edge_width'],
        glint_strength=i['pearl_glint_strength'], glint_density=i['pearl_glint_density'],
        # frost & skin show-through
        frost_body=i['frost_body_coverage'], frost_foot=i['frost_foot_coverage'],
        frost_clear=i['frost_clear_at_stretch'], frost_smooth=i['frost_matte_smoothness'],
        frost_bound=i['frost_boundary_strength'],
        boundary_width_m=i['frost_boundary_width_px'] * 0.0076,     # foot-mask texel ~7.6 mm of leg
    )
