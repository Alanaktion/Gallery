import argparse
import os
import sys

import bpy
from mathutils import Vector  # type: ignore[import-not-found]


def _parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('legacy_input', nargs='?')
    parser.add_argument('--input')
    parser.add_argument('--output', default='thumbnail.png')
    parser.add_argument('--size', type=int, default=512)
    parser.add_argument('--width', type=int)
    parser.add_argument('--height', type=int)
    parser.add_argument('--material', default='matcap.png')

    argv = sys.argv[1:]
    if '--' in argv:
        argv = argv[argv.index('--') + 1:]
    args = parser.parse_args(argv)
    args.input = args.input or args.legacy_input
    if not args.input:
        parser.error('an input file is required')
    return args


def _clear_scene():
    bpy.ops.wm.read_homefile(use_factory_startup=True)
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()


def _call_operator(module_name: str, operator_name: str, **kwargs):
    module = getattr(bpy.ops, module_name, None)
    if module is None:
        return False

    operator = getattr(module, operator_name, None)
    if operator is None:
        return False

    operator(**kwargs)
    return True


def _has_textures():
    return any(img.type == 'IMAGE' for img in bpy.data.images if img.users > 0)


def _set_render_engine(scene, preferred_engine: str,
                       fallback_engine: str | None = None):
    engine_items = scene.render.bl_rna.properties['engine'].enum_items
    if preferred_engine in engine_items:
        scene.render.engine = preferred_engine
    elif fallback_engine is not None and fallback_engine in engine_items:
        scene.render.engine = fallback_engine


def _configure_textured_render(scene):
    _set_render_engine(scene, 'BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE')
    bpy.ops.object.light_add(type='SUN')
    sun = bpy.context.object
    sun.data.energy = 2.5
    sun.rotation_euler = (0.78, 0.78, 0)


def create_matcap_material(matcap_path):
    mat = bpy.data.materials.new(name="MatCap_Material")
    # mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    # Nodes
    tex = nodes.new(type="ShaderNodeTexImage")
    tex.interpolation = 'Smart'
    try:
        tex.image = bpy.data.images.load(matcap_path)
    except Exception:
        tex.image = None

    tex.label = "MatCap Image"

    vec_transform = nodes.new(type="ShaderNodeVectorTransform")
    vec_transform.vector_type = 'NORMAL'
    vec_transform.convert_from = 'WORLD'
    vec_transform.convert_to = 'CAMERA'

    # Normalize node (Vector Math Normalize)
    normalize = nodes.new(type="ShaderNodeVectorMath")
    normalize.operation = 'NORMALIZE'

    # Map from -1..1 to 0..1: (N * 0.5) + 0.5
    scale = nodes.new(type="ShaderNodeVectorMath")
    scale.operation = 'MULTIPLY'
    scale.inputs[1].default_value = (0.5, 0.5, 0.5)

    offset = nodes.new(type="ShaderNodeVectorMath")
    offset.operation = 'ADD'
    offset.inputs[1].default_value = (0.5, 0.5, 0.5)

    # Emission shader to show matcap exactly; mix with Principled for subtle
    # lighting if desired
    emission = nodes.new(type="ShaderNodeEmission")
    emission.inputs['Strength'].default_value = 1.0

    output = nodes.new(type="ShaderNodeOutputMaterial")

    # Links: Geometry Normal -> VectorTransform (WORLD->CAMERA) -> Normalize
    # -> Scale -> Offset -> Image Texture Vector
    geom = nodes.new(type="ShaderNodeNewGeometry")
    links.new(geom.outputs['Normal'], vec_transform.inputs['Vector'])
    links.new(vec_transform.outputs['Vector'], normalize.inputs[0])
    links.new(normalize.outputs[0], scale.inputs[0])
    links.new(scale.outputs[0], offset.inputs[0])
    links.new(offset.outputs[0], tex.inputs['Vector'])
    links.new(tex.outputs['Color'], emission.inputs['Color'])
    links.new(emission.outputs['Emission'], output.inputs['Surface'])
    return mat


def assign_material_to_meshes(mat):
    for obj in bpy.context.scene.objects:
        if obj.type == 'MESH':
            # ensure object has material slots
            if not obj.data.materials:
                obj.data.materials.append(mat)
            else:
                # replace all slots with mat
                for i in range(len(obj.data.materials)):
                    obj.data.materials[i] = mat


def _import_model(input_file: str):
    ext = os.path.splitext(input_file)[1].lower()
    candidates = {
        '.3mf': [('wm', 'three_mf_import'), ('import_mesh', 'three_mf_import'),
                 ('import_mesh', 'three_mf')],
        '.stl': [('wm', 'stl_import'), ('import_mesh', 'stl')],
        '.obj': [('wm', 'obj_import'), ('import_scene', 'obj'),
                 ('import_mesh', 'obj')],
        '.fbx': [('import_scene', 'fbx')],
        '.gltf': [('import_scene', 'gltf')],
        '.glb': [('import_scene', 'gltf')],
    }.get(ext)

    if not candidates:
        raise RuntimeError(f'unsupported format: {ext}')

    last_error = None
    for module_name, operator_name in candidates:
        try:
            if _call_operator(module_name, operator_name, filepath=input_file):
                return
        except Exception as error:
            last_error = error

    if last_error is not None:
        raise RuntimeError(
            f'failed to import {input_file}: {last_error}') from last_error
    raise RuntimeError(f'no Blender importer is available for {ext}')


def _scene_bounds():
    corners = []
    for obj in bpy.context.scene.objects:
        if obj.type in {'CAMERA', 'LIGHT'}:
            continue
        try:
            corners.extend(obj.matrix_world @ Vector(corner)
                           for corner in obj.bound_box)
        except Exception:
            continue

    if not corners:
        return Vector((0.0, 0.0, 0.0)), Vector((1.0, 1.0, 1.0))

    min_corner = Vector((min(c.x for c in corners),
                         min(c.y for c in corners),
                         min(c.z for c in corners)))
    max_corner = Vector((max(c.x for c in corners),
                         max(c.y for c in corners),
                         max(c.z for c in corners)))
    return min_corner, max_corner


def _frame_camera(camera, min_corner, max_corner, width, height):
    center = (min_corner + max_corner) / 2
    extent = max(max_corner.x - min_corner.x, max_corner.y -
                 min_corner.y, max_corner.z - min_corner.z, 1.0)
    direction = Vector((1.0, -1.25, 1.0)).normalized()

    camera.location = center + direction * (extent * 2.5)
    camera.rotation_euler = (
        center - camera.location).to_track_quat('-Z', 'Y').to_euler()
    camera.data.type = 'ORTHO'
    camera.data.ortho_scale = max(1.0, extent * 1.4)
    camera.data.clip_start = 0.01
    camera.data.clip_end = max(100.0, extent * 100.0)
    bpy.context.scene.render.resolution_x = max(1, width)
    bpy.context.scene.render.resolution_y = max(1, height)


def main():
    args = _parse_args()
    output_file = os.path.abspath(args.output)
    output_dir = os.path.dirname(output_file)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    _clear_scene()

    scene = bpy.context.scene
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    scene.render.image_settings.color_depth = '8'

    _import_model(os.path.abspath(args.input))

    _configure_textured_render(scene)
    if not _has_textures():
        matcap_mat = create_matcap_material(args.material)
        assign_material_to_meshes(matcap_mat)

    bpy.ops.object.camera_add()
    camera = bpy.context.object
    scene.camera = camera

    min_corner, max_corner = _scene_bounds()
    render_width = args.width if args.width is not None else args.size
    render_height = args.height if args.height is not None else args.size
    _frame_camera(camera, min_corner, max_corner, render_width, render_height)
    scene.render.filepath = os.path.splitext(output_file)[0]

    bpy.ops.render.render(write_still=True, use_viewport=True)

    rendered_output = os.path.splitext(output_file)[0] + '.png'
    if rendered_output != output_file and os.path.exists(rendered_output):
        if os.path.exists(output_file):
            os.unlink(output_file)
        os.replace(rendered_output, output_file)


if __name__ == '__main__':
    main()
