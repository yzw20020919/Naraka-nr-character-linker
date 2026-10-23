bl_info = {
    "name": "Naraka NR Character Linker",
    "author": "Codex",
    "version": (1, 2, 4),
    "blender": (3, 6, 0),
    "location": "3D View > Sidebar > Naraka NR",
    "description": "Import a Ninja Ripper capture, find the character group, link textures, and align it in Blender.",
    "category": "Import-Export",
}

import array
import glob
import hashlib
import math
import os
import re
import shutil
import struct
import subprocess
import sys
from collections import defaultdict

import bpy
import bmesh
from bpy.props import BoolProperty, IntProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup
from mathutils import Vector

try:
    from . import nrfile
except ImportError:
    import nrfile


_GROUP_RE = re.compile(r"^mesh_(\d+)_(\d+)\.nr$", re.IGNORECASE)
_CHAR_COLLECTION = "NR_Character"
_CAM_COLLECTION = "NR_Character_Cameras"
_HAIR_HINTS = {"hair", "strand", "cap", "fur"}
_HAIR_STEMS = {
    # Naraka captures seen in the supplied frame_0/frame_1 sets.
    "00000115A2146620", "000001157D255B20", "000001161EE4CD60",
    "000001A298B86460", "000001A29B25A220",
    "00000115CCFD1BA0", "00000116AE0D9620",
    # Hair card direction/opacity map from the 2026-10-22 Naraka capture.
    "000001F05F2A4FA0",
}
_HAIR_DIRECTION_CACHE = {}
_ALPHA_PROFILE_CACHE = {}
_FACE_STEMS = {"00000115CCFCDC60"}
_HEAD_STEMS = _HAIR_STEMS | {
    "00000115A23C79E0", "000001157D255860", "000001141AC534E0",
    "00000115CCFD31A0",
}


def _finite(value, fallback=0.0):
    try:
        value = float(value)
        return value if math.isfinite(value) else fallback
    except Exception:
        return fallback


def _normalize(value):
    length = math.sqrt(sum(v * v for v in value))
    if length <= 1.0e-12:
        return (0.0, 0.0, 0.0)
    return tuple(v / length for v in value)


def _texture_stem(entry):
    textures = entry.get("textures") or []
    return os.path.splitext(os.path.basename(textures[0] if textures else ""))[0].upper()


def _repair_detached_head_parts(entries):
    """Align head draw channels to the captured face when a transform is missing."""
    face_entries = [entry for entry in entries if _texture_stem(entry) in _FACE_STEMS]
    head_entries = [
        entry for entry in entries
        if _texture_stem(entry) in _HEAD_STEMS
        or any(hint in _texture_stem(entry).lower() for hint in _HAIR_HINTS)
    ]
    if not face_entries or not head_entries:
        return 0

    def center(entry):
        points = [_transform_position(point) for point in entry["positions"]]
        return tuple(sum(point[index] for point in points) / len(points) for index in range(3))

    face_center = center(face_entries[0])
    head_centers = [center(entry) for entry in head_entries]
    # The capture lost one common draw transform. Estimate that transform from
    # the group centroid so eyes, cap, and strands keep their relative layout.
    group_center = tuple(
        sum(value[index] for value in head_centers) / len(head_centers)
        for index in range(3)
    )
    repair_offset = tuple(face_center[index] - group_center[index] for index in range(3))
    repaired = 0
    for entry in head_entries:
        entry["repair_offset"] = repair_offset
        repaired += 1
    return repaired


def _attr_by_semantic(attrs, names, minimum=1):
    names = {name.lower() for name in names}
    for index in range(attrs.getAttribsCount()):
        attr = attrs.getAttr(index)
        if attr.semantic.lower() in names and attr.compCount >= minimum:
            return attr
    return None


def _read_attr(data, vertex_buffer, attr, index):
    offset = index * vertex_buffer.getVertexSize() + attr.offs
    return struct.unpack_from("<" + attr.getFormat(), data, offset)


def _uv_score(values):
    if not values:
        return -1.0
    sample = values[: min(len(values), 500)]
    if not sample:
        return -1.0
    inside = sum(0 <= u <= 1.05 and 0 <= v <= 1.05 for u, v in sample) / len(sample)
    span_u = max(u for u, _ in sample) - min(u for u, _ in sample)
    span_v = max(v for _, v in sample) - min(v for _, v in sample)
    if span_u < 1.0e-5 or span_v < 1.0e-5:
        return -1.0
    return inside * 10.0 + min(span_u, 2.0) * min(span_v, 2.0)


def _choose_uv_attr(attrs, vertex_buffer, raw_vertices):
    candidates = []
    for index in range(attrs.getAttribsCount()):
        attr = attrs.getAttr(index)
        if attr.semantic.lower() not in {"texcoord", "tex_coord"} or attr.compCount != 2:
            continue
        values = []
        for vertex_index in range(min(vertex_buffer.getVertexCount(), 500)):
            uv = _read_attr(raw_vertices, vertex_buffer, attr, vertex_index)
            values.append((_finite(uv[0]), _finite(uv[1])))
        candidates.append((_uv_score(values), attr))
    if candidates:
        return max(candidates, key=lambda item: item[0])[1]
    for index in range(attrs.getAttribsCount()):
        attr = attrs.getAttr(index)
        if attr.compCount >= 2 and attr.semantic.lower() not in {"position", "normal", "normals"}:
            return attr
    return None


def _load_mesh(path):
    parsed = nrfile.NRFile()
    if not parsed.parse(path):
        return None
    for mesh_index in range(parsed.getMeshCount()):
        mesh = parsed.getMesh(mesh_index)
        if mesh.getShaderStage() != nrfile.ShaderStage.PreVs:
            continue
        if mesh.getPrimitiveTopology() != nrfile.PrimitiveTopology.TriangleList:
            continue
        attrs = mesh.getVertexAttributes(0)
        vertices = mesh.getVertexes(0)
        indices = mesh.getIndexes(0)
        if not attrs or not vertices or not indices:
            continue
        position_attr = _attr_by_semantic(attrs, {"position"}, 3) or attrs.getAttr(0)
        normal_attr = _attr_by_semantic(attrs, {"normal", "normals"}, 3)
        raw_vertices = vertices.read()
        uv_attr = _choose_uv_attr(attrs, vertices, raw_vertices)
        positions = []
        normals = []
        uvs = []
        for vertex_index in range(vertices.getVertexCount()):
            position = _read_attr(raw_vertices, vertices, position_attr, vertex_index)
            positions.append(tuple(_finite(v) for v in position[:3]))
            if normal_attr:
                normal = _read_attr(raw_vertices, vertices, normal_attr, vertex_index)
                normals.append(tuple(_finite(v) for v in normal[:3]))
            if uv_attr:
                uv = _read_attr(raw_vertices, vertices, uv_attr, vertex_index)
                uvs.append((_finite(uv[0]), 1.0 - _finite(uv[1])))
        raw_indices = indices.read()
        index_values = [
            struct.unpack_from("<I", raw_indices, index * 4)[0]
            for index in range(indices.getIndexCount())
        ]
        faces = []
        for index in range(0, len(index_values) - 2, 3):
            a, b, c = index_values[index : index + 3]
            if max(a, b, c) < len(positions) and len({a, b, c}) == 3:
                faces.append((a, b, c))
        geometry_digest = hashlib.sha1()
        for position in positions:
            geometry_digest.update(("%.5f,%.5f,%.5f;" % position).encode("ascii"))
        for face in faces:
            geometry_digest.update(("%d,%d,%d;" % face).encode("ascii"))
        textures = []
        texture_list = mesh.getTextures()
        if texture_list:
            textures = [
                texture_list.getTexture(i).fileName
                for i in range(texture_list.getTexturesCount())
                if texture_list.getTexture(i).fileName
            ]
        return {
            "source": os.path.basename(path),
            "mesh_index": mesh_index,
            "positions": positions,
            "normals": normals,
            "uvs": uvs,
            "faces": faces,
            "textures": textures,
            "index_hash": hashlib.sha1(raw_indices).hexdigest()[:16],
            "geometry_hash": geometry_digest.hexdigest(),
        }
    return None


def _scan_groups(folder, group_hint=""):
    groups = defaultdict(list)
    paths_by_group = defaultdict(list)
    for path in glob.glob(os.path.join(folder, "mesh_*.nr")):
        match = _GROUP_RE.match(os.path.basename(path))
        if match and (not group_hint or match.group(1) == group_hint):
            paths_by_group[match.group(1)].append(path)

    # Groups are encountered in capture order by their numeric ID. Small groups
    # cannot contain a complete character, so skip parsing their NR files. For the
    # usual Naraka captures, stop once the first clean, fully textured body group is
    # found; this avoids parsing thousands of repeated scene draw captures.
    for group_id in sorted(paths_by_group, key=int):
        group_paths = paths_by_group[group_id]
        if not group_hint and len(group_paths) < 8:
            continue
        for path in group_paths:
            entry = _load_mesh(path)
            if entry and len(entry["positions"]) >= 12 and len(entry["faces"]) >= 4:
                groups[group_id].append(entry)
        if not group_hint and _is_complete_character_group(groups[group_id]):
            break
    return groups


def _entry_geometry_key(entry):
    return entry.get("geometry_hash") or (
        len(entry["positions"]), len(entry["faces"]), entry.get("index_hash", "")
    )


def _unique_entries(entries):
    """Collapse exact duplicate draw captures while keeping the most useful material record."""
    by_geometry = {}
    for entry in entries:
        key = _entry_geometry_key(entry)
        previous = by_geometry.get(key)
        if previous is None:
            by_geometry[key] = entry
            continue
        # Texture lists in NR captures can contain repeated shader bindings. Prefer a
        # compact, populated record over an unusually long binding list.
        def material_quality(candidate):
            count = len(candidate["textures"])
            return (bool(count), min(count, 2), -max(0, count - 2))
        if material_quality(entry) > material_quality(previous):
            by_geometry[key] = entry
    return list(by_geometry.values())


def _is_complete_character_group(entries):
    unique = _unique_entries(entries)
    object_count = len(unique)
    if not 17 <= object_count <= 20 or len(entries) != object_count:
        return False
    vertex_count = sum(len(entry["positions"]) for entry in unique)
    textured_count = sum(bool(entry["textures"]) for entry in unique)
    texture_slots = sum(len(entry["textures"]) for entry in unique)
    return (
        35000 <= vertex_count <= 100000
        and textured_count >= object_count - 1
        and texture_slots <= object_count + 6
    )


def _choose_group(groups):
    if not groups:
        raise RuntimeError("No Pre-VS triangle mesh groups were found in this folder.")
    candidates = []
    for group_id, entries in groups.items():
        unique = _unique_entries(entries)
        vertex_count = sum(len(entry["positions"]) for entry in unique)
        face_count = sum(len(entry["faces"]) for entry in unique)
        texture_objects = sum(bool(entry["textures"]) for entry in unique)
        texture_slots = sum(min(len(entry["textures"]), 2) for entry in unique)
        excessive_slots = sum(max(0, len(entry["textures"]) - 2) for entry in unique)
        duplicate_count = len(entries) - len(unique)
        if len(unique) >= 8 and 20000 <= vertex_count <= 250000:
            # Naraka captures commonly contain 18–20 body parts. Repeated draw
            # channels and bloated texture-binding lists are common false positives.
            score = (
                10000
                - abs(len(unique) - 19) * 1500
                + min(vertex_count, 100000) / 50.0
                + min(face_count, 150000) / 250.0
                + texture_objects * 100
                + texture_slots * 20
                - excessive_slots * 5
                - duplicate_count * 500
            )
            candidates.append((score, -int(group_id), group_id, unique))
    if not candidates:
        group_id, entries = max(groups.items(), key=lambda item: sum(len(e["positions"]) for e in item[1]))
        return group_id, _unique_entries(entries)
    _, _, group_id, entries = max(candidates)
    return group_id, entries


def _transform_position(position):
    return (-position[2], -position[1], -position[0])


def _transform_normal(normal):
    return _normalize(_transform_position(normal))


def _collection(name):
    collection = bpy.data.collections.get(name)
    if collection is None:
        collection = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(collection)
    return collection


def _remove_collection(name):
    collection = bpy.data.collections.get(name)
    if collection is None:
        return
    for obj in list(collection.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.collections.remove(collection)


def _remove_default_cube():
    cube = bpy.data.objects.get("Cube")
    if cube and cube.type == "MESH" and tuple(round(value, 5) for value in cube.dimensions) == (2.0, 2.0, 2.0) and tuple(round(value, 5) for value in cube.location) == (0.0, 0.0, 0.0):
        bpy.data.objects.remove(cube, do_unlink=True)


def _find_ffmpeg():
    configured = bpy.context.scene.nr_character.ffmpeg_path
    if configured and os.path.isfile(bpy.path.abspath(configured)):
        return bpy.path.abspath(configured)
    return shutil.which("ffmpeg")


def _convert_texture(source, output_dir, ffmpeg):
    if not source or not os.path.isfile(source):
        return None
    os.makedirs(output_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(source))[0]
    destination = os.path.join(output_dir, stem + ".png")
    if os.path.isfile(destination) and os.path.getmtime(destination) >= os.path.getmtime(source):
        return destination
    if ffmpeg:
        try:
            proc = subprocess.run(
                [ffmpeg, "-y", "-loglevel", "error", "-i", source, "-frames:v", "1", destination],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if proc.returncode == 0 and os.path.isfile(destination):
                return destination
        except Exception:
            pass
    return source


def _convert_hair_texture(source, output_dir, ffmpeg, tint=(23, 20, 33)):
    """Tint hair direction maps while preserving their captured alpha."""
    if not source or not os.path.isfile(source):
        return None
    os.makedirs(output_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(source))[0]
    tint = tuple(max(0, min(255, int(value))) for value in tint)
    destination = os.path.join(output_dir, stem + "_hair_%02X%02X%02X.png" % tint)
    if os.path.isfile(destination):
        return destination
    if ffmpeg:
        try:
            proc = subprocess.run(
                [
                    ffmpeg, "-y", "-loglevel", "error", "-i", source,
                    "-vf", "format=rgba,lutrgb=r=%d:g=%d:b=%d" % tint,
                    "-frames:v", "1", destination,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if proc.returncode == 0 and os.path.isfile(destination):
                return destination
        except Exception:
            pass
    return _convert_texture(source, output_dir, ffmpeg)


def _looks_like_hair_direction_map(image):
    """Identify tinted directional hair cards without relying on capture IDs."""
    cache_key = (image.filepath or image.name_full, tuple(image.size))
    cached = _HAIR_DIRECTION_CACHE.get(cache_key)
    if cached is not None:
        return cached
    try:
        width, height = (int(image.size[0]), int(image.size[1]))
        channels = int(image.channels)
        if channels < 4 or max(width, height) > 1024 or width * height < 64:
            _HAIR_DIRECTION_CACHE[cache_key] = False
            return False
        pixels = array.array("f", [0.0]) * (width * height * channels)
        image.pixels.foreach_get(pixels)
        grid_x, grid_y = min(24, width), min(24, height)
        sums = [0.0, 0.0, 0.0, 0.0]
        transparent = 0
        opaque = 0
        count = 0
        for gy in range(grid_y):
            y = int(round(gy * (height - 1) / max(1, grid_y - 1)))
            for gx in range(grid_x):
                x = int(round(gx * (width - 1) / max(1, grid_x - 1)))
                offset = (y * width + x) * channels
                sample = [float(pixels[offset + channel]) for channel in range(4)]
                for channel, value in enumerate(sample):
                    sums[channel] += value
                transparent += sample[3] <= 0.05
                opaque += sample[3] >= 0.95
                count += 1
        if not count:
            _HAIR_DIRECTION_CACHE[cache_key] = False
            return False
        means = [value / count for value in sums]
        transparent_ratio = transparent / count
        opaque_ratio = opaque / count
        result = (
            0.08 <= means[0] <= 0.32
            and 0.08 <= means[1] <= 0.30
            and 0.14 <= means[2] <= 0.38
            and means[2] - means[1] >= 0.025
            and means[3] <= 0.38
            and transparent_ratio >= 0.45
            and opaque_ratio >= 0.02
        )
        _HAIR_DIRECTION_CACHE[cache_key] = result
        return result
    except Exception:
        _HAIR_DIRECTION_CACHE[cache_key] = False
        return False


def _image_node(nodes, links, shader, source, base_dir, colorspace, label, y):
    if not source:
        return None
    full_path = source if os.path.isabs(source) else os.path.join(base_dir, source)
    if not os.path.isfile(full_path):
        return None
    try:
        image = bpy.data.images.load(full_path, check_existing=True)
    except Exception:
        return None
    try:
        image.colorspace_settings.name = colorspace
    except Exception:
        pass
    node = nodes.new("ShaderNodeTexImage")
    node.name = label
    node.label = label
    node.image = image
    node.location = (-360, y)
    if max(image.size) <= 128:
        node.interpolation = "Closest"
    return node


def _set_alpha_mode(material):
    try:
        material.surface_render_method = "DITHERED"
    except Exception:
        pass
    try:
        material.blend_method = "HASHED"
    except Exception:
        pass
    try:
        material.use_transparency_overlap = False
    except Exception:
        pass


def _looks_like_tangent_normal(image):
    """Recognize conventional RGB tangent normals, not packed material masks.

    Ninja Ripper captures texture bindings without their shader slot names.
    The second binding is often a packed mask, so only connect it as a normal
    when sampled RGB values have the blue-dominant signature of a tangent map.
    """
    try:
        width, height = (int(image.size[0]), int(image.size[1]))
        if width < 2 or height < 2 or image.channels < 3:
            return False
        pixels = image.pixels
        grid_x = min(16, width)
        grid_y = min(16, height)
        sums = [0.0, 0.0, 0.0]
        positive_z = 0
        count = 0
        for gy in range(grid_y):
            y = int(round(gy * (height - 1) / max(1, grid_y - 1)))
            for gx in range(grid_x):
                x = int(round(gx * (width - 1) / max(1, grid_x - 1)))
                offset = (y * width + x) * image.channels
                red = float(pixels[offset])
                green = float(pixels[offset + 1])
                blue = float(pixels[offset + 2])
                sums[0] += red
                sums[1] += green
                sums[2] += blue
                positive_z += blue > 0.5
                count += 1
        if not count:
            return False
        means = [value / count for value in sums]
        return (
            means[2] >= 0.68
            and 0.2 <= means[0] <= 0.8
            and 0.2 <= means[1] <= 0.8
            and positive_z / count >= 0.75
        )
    except Exception:
        return False


def _alpha_profile(image):
    """Sample clear, opaque, and blended alpha coverage without loading a pixel copy."""
    try:
        width, height = (int(image.size[0]), int(image.size[1]))
        channels = int(image.channels)
        if width < 2 or height < 2 or channels < 4:
            return None
        cache_key = (image.filepath or image.name_full, tuple(image.size))
        if cache_key in _ALPHA_PROFILE_CACHE:
            return _ALPHA_PROFILE_CACHE[cache_key]
        pixels = image.pixels
        grid_x = min(32, width)
        grid_y = min(32, height)
        transparent = 0
        opaque = 0
        count = 0
        for gy in range(grid_y):
            y = int(round(gy * (height - 1) / max(1, grid_y - 1)))
            for gx in range(grid_x):
                x = int(round(gx * (width - 1) / max(1, grid_x - 1)))
                alpha = float(pixels[(y * width + x) * channels + 3])
                transparent += alpha <= 0.05
                opaque += alpha >= 0.95
                count += 1
        profile = (
            transparent / count,
            opaque / count,
            1.0 - (transparent + opaque) / count,
        ) if count else None
        _ALPHA_PROFILE_CACHE[cache_key] = profile
        return profile
    except Exception:
        return None


def _has_hair_cutout_alpha(image):
    """Detect sparse hair/eyelash cutouts that need crisp binary coverage."""
    profile = _alpha_profile(image)
    return bool(profile and profile[0] >= 0.45 and profile[1] >= 0.02)


def _has_blended_opacity_alpha(image):
    """Recognize diffuse maps with both clear holes and broad soft opacity."""
    profile = _alpha_profile(image)
    if not profile:
        return False
    transparent, opaque, intermediate = profile
    return (
        0.08 <= transparent <= 0.40
        and opaque >= 0.18
        and intermediate >= 0.25
    )


def _material_for(texture_source, normal_source, source_dir, texture_dir, ffmpeg, material_cache):
    if texture_source and not os.path.isabs(texture_source):
        texture_source = os.path.join(source_dir, texture_source)
    if normal_source and not os.path.isabs(normal_source):
        normal_source = os.path.join(source_dir, normal_source)
    texture_stem = os.path.splitext(os.path.basename(texture_source or ""))[0]
    explicit_hair = texture_stem in _HAIR_STEMS or any(hint in texture_stem.lower() for hint in _HAIR_HINTS)
    candidate_source = _convert_texture(texture_source, texture_dir, ffmpeg)
    candidate_image = None
    if candidate_source:
        try:
            candidate_image = bpy.data.images.load(candidate_source, check_existing=True)
        except Exception:
            pass
    detected_direction_map = bool(candidate_image and _looks_like_hair_direction_map(candidate_image))
    is_hair = explicit_hair or detected_direction_map
    if explicit_hair:
        base_source = _convert_hair_texture(texture_source, texture_dir, ffmpeg)
    elif detected_direction_map:
        base_source = _convert_hair_texture(texture_source, texture_dir, ffmpeg, tint=(58, 39, 28))
    else:
        base_source = candidate_source
    normal_source = _convert_texture(normal_source, texture_dir, ffmpeg)
    key = (base_source, normal_source)
    if key in material_cache:
        return material_cache[key]
    stem = os.path.splitext(os.path.basename(texture_source or "no_texture"))[0]
    material = bpy.data.materials.new("NR_" + stem)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (500, 0)
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.location = (160, 0)
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    shader.inputs["Roughness"].default_value = 0.52 if is_hair else 0.42
    base = _image_node(nodes, links, shader, base_source, source_dir, "sRGB", "NR_BaseColor", 100)
    if base:
        links.new(base.outputs["Color"], shader.inputs["Base Color"])
        if is_hair or _has_hair_cutout_alpha(base.image):
            alpha_cutout = nodes.new("ShaderNodeMath")
            alpha_cutout.name = "NR_AlphaCutout"
            alpha_cutout.label = "Alpha cutout (0.5)"
            alpha_cutout.operation = "GREATER_THAN"
            alpha_cutout.inputs[1].default_value = 0.5
            alpha_cutout.location = (-80, 160)
            links.new(base.outputs["Alpha"], alpha_cutout.inputs[0])
            links.new(alpha_cutout.outputs[0], shader.inputs["Alpha"])
            _set_alpha_mode(material)
            material["NR_alpha_cutout_threshold"] = 0.5
            material["NR_alpha_mode"] = "CUTOUT"
        elif _has_blended_opacity_alpha(base.image):
            links.new(base.outputs["Alpha"], shader.inputs["Alpha"])
            _set_alpha_mode(material)
            material["NR_alpha_mode"] = "BLENDED"
    if is_hair:
        material["NR_hair_map"] = True
        if detected_direction_map and not explicit_hair:
            material["NR_auto_hair_direction_map"] = True
    normal = _image_node(nodes, links, shader, normal_source, source_dir, "Non-Color", "NR_Normal_Candidate", -120)
    if normal and _looks_like_tangent_normal(normal.image):
        normal.name = "NR_Normal"
        normal.label = "NR_Normal"
        normal_map = nodes.new("ShaderNodeNormalMap")
        normal_map.location = (-20, -90)
        links.new(normal.outputs["Color"], normal_map.inputs["Color"])
        links.new(normal_map.outputs["Normal"], shader.inputs["Normal"])
    elif normal:
        material["NR_unlinked_texture_slot_1"] = os.path.basename(normal_source or "")
        nodes.remove(normal)
    material_cache[key] = material
    return material


def _create_object(entry, object_index, vertices, offset, collection, materials, source_dir, texture_dir, ffmpeg):
    final_vertices = []
    final_normals = []
    for position in entry["positions"]:
        transformed = _transform_position(position)
        repair = entry.get("repair_offset", (0.0, 0.0, 0.0))
        final_vertices.append((
            transformed[0] + offset[0] + repair[0],
            transformed[1] + offset[1] + repair[1],
            transformed[2] + offset[2] + repair[2],
        ))
    for normal in entry["normals"]:
        final_normals.append(_transform_normal(normal))
    mesh = bpy.data.meshes.new("NR_" + os.path.splitext(entry["source"])[0])
    mesh.from_pydata(final_vertices, [], entry["faces"])
    mesh.update()
    mesh.validate(clean_customdata=True)
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    if entry["uvs"] and len(entry["uvs"]) == len(final_vertices):
        uv_layer = mesh.uv_layers.new(name="UVMap")
        for polygon in mesh.polygons:
            for loop_index in polygon.loop_indices:
                vertex_index = mesh.loops[loop_index].vertex_index
                uv_layer.data[loop_index].uv = entry["uvs"][vertex_index]
    obj = bpy.data.objects.new(os.path.splitext(entry["source"])[0], mesh)
    collection.objects.link(obj)
    material = _material_for(
        entry["textures"][0] if entry["textures"] else None,
        entry["textures"][1] if len(entry["textures"]) > 1 else None,
        source_dir,
        texture_dir,
        ffmpeg,
        materials,
    )
    obj.data.materials.append(material)
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    if bpy.context.scene.nr_character.subdivision_level > 0 and not entry.get("repair_offset"):
        modifier = obj.modifiers.new("NR Geometry Refinement", "SUBSURF")
        modifier.subdivision_type = "CATMULL_CLARK"
        modifier.levels = bpy.context.scene.nr_character.subdivision_level
        modifier.render_levels = bpy.context.scene.nr_character.subdivision_level
        try:
            modifier.uv_smooth = "PRESERVE_CORNERS"
        except Exception:
            pass
    obj["NR_source_file"] = entry["source"]
    obj["NR_source_texture"] = entry["textures"][0] if entry["textures"] else ""
    obj["NR_repair_offset"] = tuple(round(value, 6) for value in entry.get("repair_offset", (0.0, 0.0, 0.0)))
    obj["NR_normals_recalculated"] = True
    obj["NR_subdivision_level"] = int(bpy.context.scene.nr_character.subdivision_level if not entry.get("repair_offset") else 0)
    return obj


def _look_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def _add_area_light(name, location, energy, size, target):
    light_data = bpy.data.lights.get(name) or bpy.data.lights.new(name, "AREA")
    light_data.energy = energy
    light_data.shape = "DISK"
    light_data.size = size
    light_obj = bpy.data.objects.get(name) or bpy.data.objects.new(name, light_data)
    if light_obj.name not in _collection(_CAM_COLLECTION).objects:
        _collection(_CAM_COLLECTION).objects.link(light_obj)
    light_obj.location = location
    _look_at(light_obj, target)


def _make_cameras(height):
    collection = _collection(_CAM_COLLECTION)
    target = (0.0, 0.0, height * 0.52)
    for name, location in (("NR_Front_View", (0.0, -3.2, height * 0.53)), ("NR_Back_View", (0.0, 3.2, height * 0.53))):
        camera_data = bpy.data.cameras.get(name) or bpy.data.cameras.new(name)
        camera = bpy.data.objects.get(name) or bpy.data.objects.new(name, camera_data)
        if camera.name not in collection.objects:
            collection.objects.link(camera)
        camera.location = location
        camera_data.lens = 58
        _look_at(camera, target)
    bpy.context.scene.camera = bpy.data.objects.get("NR_Front_View")
    _add_area_light("NR_Key_Light", (2.4, -3.2, height * 1.6), 900, 2.2, target)
    _add_area_light("NR_Fill_Light", (-2.5, -1.2, height * 0.9), 450, 2.8, target)
    _add_area_light("NR_Rim_Light", (0.0, 2.8, height * 1.3), 700, 2.0, target)
    scene = bpy.context.scene
    scene.render.resolution_x = 512
    scene.render.resolution_y = 768
    scene.render.resolution_percentage = 100
    scene.world.color = (0.045, 0.055, 0.075)


def import_capture(folder, group_hint=""):
    folder = os.path.abspath(bpy.path.abspath(folder))
    if not os.path.isdir(folder):
        raise RuntimeError("Capture folder does not exist: " + folder)
    groups = _scan_groups(folder, group_hint.strip())
    group_id, entries = _choose_group(groups)
    repaired_parts = _repair_detached_head_parts(entries) if bpy.context.scene.nr_character.repair_detached_parts else 0
    _remove_collection(_CHAR_COLLECTION)
    collection = _collection(_CHAR_COLLECTION)
    transformed = []
    for entry in entries:
        repair = entry.get("repair_offset", (0.0, 0.0, 0.0))
        transformed.extend(
            tuple(value + repair[index] for index, value in enumerate(_transform_position(position)))
            for position in entry["positions"]
        )
    min_x = min(position[0] for position in transformed)
    max_x = max(position[0] for position in transformed)
    min_y = min(position[1] for position in transformed)
    max_y = max(position[1] for position in transformed)
    min_z = min(position[2] for position in transformed)
    max_z = max(position[2] for position in transformed)
    offset = (-(min_x + max_x) * 0.5, -(min_y + max_y) * 0.5, -min_z)
    configured_output = bpy.context.scene.nr_character.output_dir.strip()
    if configured_output:
        output_root = bpy.path.abspath(configured_output)
    elif bpy.data.filepath:
        output_root = os.path.join(os.path.dirname(bpy.data.filepath), "nr_blender_output", os.path.basename(folder))
    else:
        output_root = os.path.join(os.path.expanduser("~"), "Naraka_NR_Output", os.path.basename(folder))
    texture_dir = os.path.join(output_root, "textures")
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        native_converters = {".dds": "DDS", ".png": "PNG", ".tga": "TARGA", ".jpg": "JPEG", ".jpeg": "JPEG", ".tif": "TIFF", ".tiff": "TIFF", ".bmp": "BMP", ".exr": "OPEN_EXR"}
        exts = sorted({os.path.splitext(tex)[1].lower() for entry in entries for tex in entry["textures"]})
        if any(ext not in native_converters for ext in exts):
            raise RuntimeError("Set FFmpeg path: Blender cannot convert all captured texture formats: " + ", ".join(exts))
        for entry in entries:
            converted = []
            for source_name in entry["textures"]:
                source_path = os.path.join(folder, source_name)
                output_path = _convert_texture(source_path, texture_dir, None)
                converted.append(output_path or source_name)
            entry["textures"] = converted
    materials = {}
    objects = []
    _remove_default_cube()
    os.makedirs(output_root, exist_ok=True)
    for object_index, entry in enumerate(entries):
        objects.append(_create_object(entry, object_index, folder, offset, collection, materials, folder, texture_dir, ffmpeg))
    root = bpy.data.objects.new("NR_Character_Root", None)
    collection.objects.link(root)
    for obj in objects:
        obj.parent = root
    _make_cameras(max_z - min_z)
    scene = bpy.context.scene
    scene["NR_capture_folder"] = folder
    scene["NR_group_id"] = group_id
    scene["NR_character_height"] = max_z - min_z
    scene["NR_repaired_head_hair_parts"] = repaired_parts
    return group_id, len(entries), sum(len(entry["positions"]) for entry in entries), sum(len(entry["faces"]) for entry in entries)


class NRCharacterProperties(PropertyGroup):
    capture_dir: StringProperty(name="Capture folder", subtype="DIR_PATH")
    output_dir: StringProperty(name="Output folder", subtype="DIR_PATH")
    group_hint: StringProperty(name="Group ID", description="Optional mesh group number, for example 1007", default="")
    # Keep the public plugin portable. Users can set a custom executable in the
    # panel; when this is empty, the importer searches the system PATH.
    ffmpeg_path: StringProperty(name="FFmpeg path", subtype="FILE_PATH", default="")
    repair_detached_parts: BoolProperty(
        name="Repair detached face and hair",
        description="Align captured hair, eyes, and face cards when their draw transform is missing",
        default=True,
    )
    subdivision_level: IntProperty(
        name="Geometry refinement",
        description="Subdivision Surface level for solid body meshes; hair cards and repaired parts are excluded",
        min=0,
        max=2,
        default=0,
    )
    last_report: StringProperty(name="Last report", default="")


class NR_OT_SelectFolder(Operator):
    bl_idname = "nr_character.select_folder"
    bl_label = "Choose frame folder"
    directory: StringProperty(subtype="DIR_PATH")

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        context.scene.nr_character.capture_dir = self.directory
        return {"FINISHED"}


class NR_OT_ImportCharacter(Operator):
    bl_idname = "nr_character.import_capture"
    bl_label = "Import and link character"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.nr_character
        try:
            group_id, object_count, vertex_count, face_count = import_capture(props.capture_dir, props.group_hint)
            props.last_report = "Group %s: %d objects, %d vertices, %d faces" % (group_id, object_count, vertex_count, face_count)
            self.report({"INFO"}, props.last_report)
            return {"FINISHED"}
        except Exception as exc:
            props.last_report = "Error: " + str(exc)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class NR_PT_CharacterLinker(Panel):
    bl_label = "Naraka NR Character"
    bl_idname = "NR_PT_character_linker"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Naraka NR"

    def draw(self, context):
        layout = self.layout
        props = context.scene.nr_character
        layout.prop(props, "capture_dir")
        layout.operator("nr_character.select_folder", icon="FILE_FOLDER")
        layout.prop(props, "output_dir")
        layout.prop(props, "group_hint")
        layout.prop(props, "ffmpeg_path")
        layout.prop(props, "repair_detached_parts")
        layout.prop(props, "subdivision_level")
        layout.operator("nr_character.import_capture", icon="IMPORT")
        if props.last_report:
            layout.label(text=props.last_report)
        layout.label(text="Face points toward Blender -Y; feet are placed at Z=0.")
        layout.label(text="Set FFmpeg path if DDS textures are not converted automatically.")


classes = (NRCharacterProperties, NR_OT_SelectFolder, NR_OT_ImportCharacter, NR_PT_CharacterLinker)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.nr_character = bpy.props.PointerProperty(type=NRCharacterProperties)


def unregister():
    del bpy.types.Scene.nr_character
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
