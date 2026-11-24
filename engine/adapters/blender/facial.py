"""Pure frame scheduling plus Blender-only mesh/rig operations.

No orchestration dependencies are imported inside Blender.
"""
import math


def performance_keys(timeline, start_seconds, fps, smoothing_seconds=.04):
    if not all(math.isfinite(v) for v in (start_seconds, fps, smoothing_seconds)) or start_seconds < 0 or fps <= 0 or smoothing_seconds < 0:
        raise ValueError('Invalid facial timing parameters')
    keys = [(1.0 + start_seconds * fps, 'X')]
    for index, cue in enumerate(timeline['cues']):
        start, end = cue['start'], cue['end']
        ramp = min(smoothing_seconds, (end - start) / 2)
        # Continuous subframes avoid cumulative integer rounding. Linear bounded ramps.
        keys.append((1.0 + (start_seconds + start + ramp) * fps, cue['value']))
        keys.append((1.0 + (start_seconds + end - ramp) * fps, cue['value']))
        next_cue = timeline['cues'][index + 1] if index + 1 < len(timeline['cues']) else None
        if cue['value'] == 'X' or next_cue is None or next_cue['value'] == 'X':
            keys.append((1.0 + (start_seconds + end) * fps, 'X'))
    keys.append((1.0 + (start_seconds + timeline['duration_seconds']) * fps, 'X'))
    return keys


def _linear(animation_data):
    if not animation_data or not animation_data.action:
        return
    action = animation_data.action
    if hasattr(action, 'fcurves'):
        curves = action.fcurves
    else:
        curves = [curve for layer in action.layers for strip in layer.strips
                  for bag in strip.channelbags for curve in bag.fcurves]
    for curve in curves:
        for key in curve.keyframe_points:
            key.interpolation = 'LINEAR'


def apply_performance(root, spec: dict, fps: float) -> None:
    """Animate explicit controls on root/descendants; host validates full schema."""
    objects = [root, *root.children_recursive]
    controls = spec.get('controls')
    if not controls:
        if spec.get('profile', 'atlas-face-1') != 'atlas-face-1':
            raise ValueError('Unsupported facial profile')
        mouths = [obj for obj in objects if obj.get('atlas_mouth')]
        if len(mouths) != 1:
            raise ValueError('Actor requires exactly one atlas-face-1 mouth or explicit controls')
        controls = {'kind': 'shape_keys', 'object': mouths[0].name, 'mapping': {c: c for c in 'ABCDEFGH'}}
    target = next((obj for obj in objects if obj.name == controls['object']), None)
    if target is None:
        raise ValueError('Facial control object is not part of this actor')
    keys = performance_keys(spec['timeline'], spec.get('start_seconds', 0), fps, spec.get('smoothing_seconds', .04))
    if controls['kind'] == 'shape_keys':
        mapping = controls['mapping']
        shape_keys = getattr(target.data, 'shape_keys', None)
        if set(mapping) != set('ABCDEFGH') or shape_keys is None or any(name not in shape_keys.key_blocks for name in mapping.values()):
            raise ValueError('Missing required shape-key controls A-H')
        for frame, value in keys:
            for cue, name in mapping.items():
                block = shape_keys.key_blocks[name]
                block.value = float(cue == value)
                block.keyframe_insert(data_path='value', frame=frame)
        _linear(shape_keys.animation_data)
    elif controls['kind'] == 'jaw_bone':
        if target.type != 'ARMATURE' or controls['bone'] not in target.pose.bones:
            raise ValueError('Missing required jaw bone')
        angles = controls['angles']
        if set(angles) != set('ABCDEFGHX') or angles['X'] != 0:
            raise ValueError('Jaw angles must map A-H/X and reset X to zero')
        bone = target.pose.bones[controls['bone']]
        axis = 'XYZ'.index(controls.get('axis', 'X'))
        bone.rotation_mode = 'XYZ'
        for frame, value in keys:
            bone.rotation_euler[axis] = angles[value]
            bone.keyframe_insert(data_path='rotation_euler', index=axis, frame=frame)
        _linear(target.animation_data)
    else:
        raise ValueError('Unsupported facial control kind')
    root['atlas_facial_profile'] = spec.get('profile', 'atlas-face-1')


def build_talking_head(spec: dict):
    """Create ATLAS's original stylized teal robot bust, facing local -Y."""
    import bpy
    root = bpy.data.objects.new(spec['id'], None)
    bpy.context.scene.collection.objects.link(root)
    root['atlas_character'] = 'atlas-face-1'

    def material(name, color, metallic=0):
        mat = bpy.data.materials.new(f'{root.name}_{name}')
        mat.diffuse_color = (*color, 1)
        mat.use_nodes = True
        shader = mat.node_tree.nodes.get('Principled BSDF')
        shader.inputs['Base Color'].default_value = (*color, 1)
        shader.inputs['Metallic'].default_value = metallic
        shader.inputs['Roughness'].default_value = .35
        return mat

    teal = material('teal', (.035, .35, .36), .15)
    gold = material('gold', (.95, .52, .12), .35)
    white = material('eyes', (.92, .97, 1))
    dark = material('dark', (.008, .015, .027))

    def sphere(name, location, scale, mat):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=1)
        obj = bpy.context.object
        obj.name = f'{root.name}_{name}'
        obj.location, obj.scale, obj.parent = location, scale, root
        obj.data.materials.append(mat)
        for poly in obj.data.polygons:
            poly.use_smooth = True
        return obj

    sphere('head', (0, 0, 1.7), (.8, .7, 1), teal)
    sphere('shoulders', (0, .10, .35), (.85, .48, .35), teal)
    sphere('neck', (0, 0, .72), (.28, .28, .32), gold)
    for side in (-1, 1):
        sphere(f'ear_{side}', (side * .78, 0, 1.72), (.13, .24, .31), gold)
        sphere(f'eye_{side}', (side * .29, -.63, 1.97), (.20, .12, .23), white)
        sphere(f'pupil_{side}', (side * .29, -.745, 1.97), (.08, .045, .105), dark)
        sphere(f'brow_{side}', (side * .30, -.61, 2.27), (.22, .065, .055), gold)
    sphere('nose', (0, -.73, 1.69), (.10, .14, .14), gold)
    count = 32

    def mouth_vertices(width, height):
        return [(math.cos(i * 2 * math.pi / count) * (width + rim), -.755,
                 1.34 + math.sin(i * 2 * math.pi / count) * (height + rim))
                for rim in (0, .035) for i in range(count)]

    faces = [tuple(range(count))] + [(i, (i+1) % count, (i+1) % count+count, i+count) for i in range(count)]
    mesh = bpy.data.meshes.new(f'{root.name}_mouth_mesh')
    mesh.from_pydata(mouth_vertices(.29, .025), [], faces)
    mesh.materials.append(dark)
    mesh.materials.append(gold)
    for polygon in mesh.polygons[1:]:
        polygon.material_index = 1
    mouth = bpy.data.objects.new(f'{root.name}_mouth', mesh)
    bpy.context.scene.collection.objects.link(mouth)
    mouth.parent = root
    mouth['atlas_mouth'] = True
    mouth.shape_key_add(name='Basis')
    dimensions = {'A': (.28, .012), 'B': (.30, .065), 'C': (.30, .14), 'D': (.28, .25),
                  'E': (.20, .13), 'F': (.12, .12), 'G': (.28, .045), 'H': (.27, .17)}
    for cue, (width, height) in dimensions.items():
        key = mouth.shape_key_add(name=cue)
        for point, co in zip(key.data, mouth_vertices(width, height)):
            point.co = co
    return root
