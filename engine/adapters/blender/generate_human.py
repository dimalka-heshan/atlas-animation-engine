"""Package-owned, Blender-only MPFB generator for approved local source assets."""
import json
from pathlib import Path
import random
import sys
import time

import addon_utils
import bpy
from mathutils import Quaternion, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from human_controls import HUMAN_KEYS

WARDROBE = {"casual": "male_casualsuit01", "formal": "male_elegantsuit01", "worker": "male_worksuit01",
            "casual-female": "female_casualsuit01", "formal-female": "female_elegantsuit01"}


def set_surface_opacity(obj, transparent):
    for material in obj.data.materials:
        material.surface_render_method = "DITHERED"
        if transparent:
            continue
        for node in material.node_tree.nodes:
            if node.type == "BSDF_PRINCIPLED":
                alpha = node.inputs["Alpha"]
                for link in list(alpha.links):
                    material.node_tree.links.remove(link)
                alpha.default_value = 1


def author_motion(rig):
    """Create reusable source-native lowered-arm idle and presentation actions."""
    scene = bpy.context.scene
    scene.render.fps = 30
    rig.animation_data_create()
    for clip in ("HumanIdle", "HumanPresent"):
        action = bpy.data.actions.new(clip)
        rig.animation_data.action = action
        for frame, motion in ((0, 0), (24, .65), (51, 1), (75, .4), (90, 0)):
            for side, sign in (("l", 1), ("r", -1)):
                upper = rig.pose.bones[f"upperarm_{side}"]
                axis = upper.bone.matrix_local.to_quaternion()
                direction = (upper.bone.tail_local - upper.bone.head_local).normalized()
                amount = .22 + .10 * motion if clip == "HumanPresent" and side == "r" else .18
                lowered = Vector((sign * amount, -(.22 + .35 * motion) if side == "r" else -.11, -1)).normalized()
                upper.rotation_mode = "QUATERNION"
                upper.rotation_quaternion = axis.inverted() @ direction.rotation_difference(lowered) @ axis
                upper.keyframe_insert(data_path="rotation_quaternion", frame=frame, group=upper.name)
            for name, angle in (("head", .06 * motion), ("spine_03", -.025 * motion)):
                bone = rig.pose.bones[name]
                axis = bone.bone.matrix_local.to_quaternion().inverted() @ Vector((0, 0, 1))
                bone.rotation_mode = "QUATERNION"
                bone.rotation_quaternion = Quaternion(axis, angle)
                bone.keyframe_insert(data_path="rotation_quaternion", frame=frame, group=name)
        slot = rig.animation_data.action_slot
        track = rig.animation_data.nla_tracks.new()
        track.name = clip
        strip = track.strips.new(clip, 0, action)
        strip.action_slot = slot
        track.mute = True
        rig.animation_data.action = None
    for bone in rig.pose.bones:
        bone.matrix_basis.identity()
    scene.frame_set(0)


def main():
    output = Path(sys.argv[sys.argv.index("--") + 1]).resolve()
    spec = json.loads((output / "spec.json").read_text(encoding="utf-8"))
    start = time.perf_counter()
    random.seed(spec["seed"])
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if addon_utils.enable("bl_ext.user_default.mpfb", default_set=True) is None:
        raise ValueError("MPFB extension is not installed in the isolated Blender profile")
    from bl_ext.user_default import mpfb
    from bl_ext.user_default.mpfb.services.humanservice import HumanService
    from bl_ext.user_default.mpfb.services.targetservice import TargetService
    from bl_ext.user_default.mpfb.services.faceservice import FaceService
    from bl_ext.user_default.mpfb.services.assetservice import AssetService
    from bl_ext.user_default.mpfb.services.exportservice import ExportService
    if mpfb.VERSION != (2, 0, 18):
        raise ValueError(f"Unexpected MPFB version: {mpfb.VERSION}")
    macro = TargetService.get_default_macro_info_dict()
    for key in ("gender", "age", "height", "proportions"):
        macro[key] = spec[key]
    ancestry = spec["ancestry"]
    if ancestry != "mixed":
        macro["race"] = {key: float(key == ancestry) for key in macro["race"]}
    macro["weight"], macro["muscle"] = spec["build"], spec["muscularity"]
    human = HumanService.create_human(macro_detail_dict=macro)
    human.name = "AtlasHumanBody"
    # Bake the identity before loading facial targets so they deform the
    # customized neutral basis rather than overwriting the macro shapes.
    TargetService.bake_targets(human)
    rig = HumanService.add_builtin_rig(human, "game_engine")
    rig.name = "AtlasHumanRig"
    assets = [("eyes", "high-poly", "Eyes"), ("eyebrows", "eyebrow001", "Eyebrows"),
              ("eyelashes", "eyelashes01", "Eyelashes"), ("tongue", "tongue01", "Tongue"),
              ("teeth", "teeth_base", "Teeth"), ("hair", spec["hair"], "Hair"),
              ("clothes", WARDROBE[spec["wardrobe"]], "Clothes"), ("clothes", "shoes01", "Clothes")]

    def find(name, directory):
        path = AssetService.find_asset_absolute_path(name, asset_subdir=directory)
        if path is None:
            raise ValueError(f"Missing official MPFB asset: {directory}/{name}")
        return path

    HumanService.set_character_skin(find(spec["skin"] + ".mhmat", "skins"), human, skin_type="GAMEENGINE")
    set_surface_opacity(human, False)
    for directory, item, asset_type in assets:
        obj = HumanService.add_mhclo_asset(find(item + ".mhclo", directory), human,
                                          asset_type=asset_type, subdiv_levels=0, material_type="GAMEENGINE")
        set_surface_opacity(obj, directory in {"hair", "eyes", "eyebrows", "eyelashes"})
    FaceService.load_targets(human, load_microsoft_visemes=False, load_meta_visemes=True, load_arkit_faceunits=True)
    keys = human.data.shape_keys.key_blocks
    if not HUMAN_KEYS.issubset(keys.keys()):
        raise ValueError(f"Missing CC0 face targets: {sorted(HUMAN_KEYS - set(keys.keys()))}")
    for key in list(keys)[1:]:
        if key.name not in HUMAN_KEYS:
            human.shape_key_remove(key)
    FaceService.interpolate_targets(human)
    ExportService.bake_modifiers_remove_helpers(human, bake_masks=True, bake_subdiv=False, also_proxy=False)
    bpy.ops.object.select_all(action="DESELECT")
    for obj in rig.children_recursive:
        if obj.type == "MESH" and any(mod.type == "ARMATURE" and mod.object == rig for mod in obj.modifiers):
            obj.select_set(True)
            for face in obj.data.polygons:
                face.use_smooth = True
    rig.select_set(True)
    author_motion(rig)
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "source.blend"))
    result = bpy.ops.export_scene.gltf(filepath=str(output / "human.glb"), export_format="GLB",
        use_selection=True,
        export_morph=True, export_try_sparse_sk=False, export_morph_normal=False, export_morph_tangent=False,
        export_animations=True, export_animation_mode="NLA_TRACKS", export_force_sampling=True)
    if "FINISHED" not in result:
        raise ValueError(f"MPFB GLB export failed: {result}")
    report = {"mpfb_version": ".".join(map(str, mpfb.VERSION)), "blender_version": bpy.app.version_string,
              "rig": "game_engine", "bones": len(rig.data.bones), "body_vertices": len(human.data.vertices),
              "face_keys": sorted(HUMAN_KEYS), "dependencies": assets, "motions": ["HumanIdle", "HumanPresent"],
              "generation_seconds": time.perf_counter() - start}
    (output / "worker.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
