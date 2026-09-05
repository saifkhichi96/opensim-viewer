# Copyright (C) 2023  ETH Zurich, Manuel Kaufmann, Velko Vechev, Dario Mylonopoulos
import functools

from moderngl_window import resources
from moderngl_window.meta import ProgramDescription


def load_program(name, defines: dict = None):
    return resources.programs.load(ProgramDescription(path=name, defines=defines))


@functools.lru_cache()
def get_lit_program(vs, smooth_shading, texture, face_color, instanced=0):
    defines = {
        "SMOOTH_SHADING": smooth_shading,
        "TEXTURE": texture,
        "FACE_COLOR": face_color,
        "INSTANCED": instanced,
    }
    return resources.programs.load(
        ProgramDescription(
            vertex_shader=vs,
            geometry_shader="lit_with_edges.glsl",
            fragment_shader="lit_with_edges.glsl",
            defines=defines,
        )
    )


def get_smooth_lit_with_edges_program(vs, instanced=0):
    return get_lit_program(
        vs, smooth_shading=1, texture=0, face_color=0, instanced=instanced
    )


def get_smooth_lit_with_edges_face_color_program(vs, instanced=0):
    return get_lit_program(
        vs, smooth_shading=1, texture=0, face_color=1, instanced=instanced
    )


def get_flat_lit_with_edges_face_color_program(vs, instanced=0):
    return get_lit_program(
        vs, smooth_shading=0, texture=0, face_color=1, instanced=instanced
    )


def get_flat_lit_with_edges_program(vs, instanced=0):
    return get_lit_program(
        vs, smooth_shading=0, texture=0, face_color=0, instanced=instanced
    )


def get_smooth_lit_texturized_program(vs, instanced=0):
    return get_lit_program(
        vs, smooth_shading=1, texture=1, face_color=0, instanced=instanced
    )


def get_sphere_instanced_program():
    return get_smooth_lit_with_edges_program("sphere_instanced.vs.glsl")


def get_lines_instanced_program():
    return get_smooth_lit_with_edges_program("lines_instanced.vs.glsl")


@functools.lru_cache()
def get_outline_program(vs_path, instanced=0):
    defines = {"INSTANCED": instanced}
    return resources.programs.load(
        ProgramDescription(
            vertex_shader=vs_path,
            fragment_shader="outline/outline_prepare.fs.glsl",
            defines=defines,
        )
    )


@functools.lru_cache()
def get_fragmap_program(vs_path, instanced=0):
    defines = {"INSTANCED": instanced}
    return resources.programs.load(
        ProgramDescription(
            vertex_shader=vs_path,
            fragment_shader="fragment_picking/frag_map.fs.glsl",
            defines=defines,
        )
    )


@functools.lru_cache()
def get_depth_only_program(vs_path, instanced=0):
    defines = {"INSTANCED": instanced}
    return resources.programs.load(
        ProgramDescription(
            vertex_shader=vs_path,
            fragment_shader="shadow_mapping/depth_only.fs.glsl",
            defines=defines,
        )
    )


@functools.lru_cache()
def get_simple_unlit_program():
    return load_program("simple_unlit.glsl")


@functools.lru_cache()
def get_cylinder_program():
    return load_program("cylinder.glsl")


@functools.lru_cache()
def get_screen_texture_program():
    return load_program("screen_texture.glsl")


@functools.lru_cache()
def get_chessboard_program():
    return load_program("chessboard.glsl")


def clear_shader_cache():
    """Clear all cached shaders."""
    funcs = [
        get_lit_program,
        get_outline_program,
        get_fragmap_program,
        get_depth_only_program,
        get_simple_unlit_program,
        get_cylinder_program,
        get_screen_texture_program,
        get_chessboard_program,
    ]
    for f in funcs:
        f.cache_clear()
