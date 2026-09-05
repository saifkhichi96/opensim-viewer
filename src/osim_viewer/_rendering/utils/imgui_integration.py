# Copyright (C) 2023  ETH Zurich, Manuel Kaufmann, Velko Vechev, Dario Mylonopoulos
import ctypes

import imgui
import moderngl
from moderngl_window.integrations.imgui import ModernglWindowRenderer

from osim_viewer._rendering.configuration import CONFIG as C


class ImGuiRenderer(ModernglWindowRenderer):
    def resize(self, width, height):
        scale = float(C.ui_scale)
        if not 0.5 <= scale <= 3.0:
            raise ValueError("ui_scale must be between 0.5 and 3.0")
        w, h = self.wnd.size
        bw, bh = self.wnd.buffer_size
        if w > 0 and h > 0:
            self.io.display_size = (w / scale, h / scale)
            self.io.display_fb_scale = (bw / w * scale, bh / h * scale)

    def _mouse_pos_viewport(self, x, y):
        x, y = super()._mouse_pos_viewport(x, y)
        return x / C.ui_scale, y / C.ui_scale

    def __init__(self, window, window_type):
        self.window_type = window_type
        super().__init__(window)

    def render(self, draw_data):
        self.io.key_alt = self.wnd.modifiers.alt
        self.io.key_ctrl = self.wnd.modifiers.ctrl
        self.io.key_shift = self.wnd.modifiers.shift
        io = self.io
        display_width, display_height = io.display_size
        fb_width = int(display_width * io.display_fb_scale[0])
        fb_height = int(display_height * io.display_fb_scale[1])
        if fb_width == 0 or fb_height == 0:
            return
        self.projMat.value = (
            2.0 / display_width,
            0.0,
            0.0,
            0.0,
            0.0,
            2.0 / -display_height,
            0.0,
            0.0,
            0.0,
            0.0,
            -1.0,
            0.0,
            -1.0,
            1.0,
            0.0,
            1.0,
        )
        draw_data.scale_clip_rects(*io.display_fb_scale)
        self.ctx.enable_only(moderngl.BLEND)
        self.ctx.blend_equation = moderngl.FUNC_ADD
        self.ctx.blend_func = (
            moderngl.SRC_ALPHA,
            moderngl.ONE_MINUS_SRC_ALPHA,
            moderngl.ONE,
            moderngl.ONE,
        )
        self._font_texture.use()
        for commands in draw_data.commands_lists:
            vtx_type = ctypes.c_byte * commands.vtx_buffer_size * imgui.VERTEX_SIZE
            idx_type = ctypes.c_byte * commands.idx_buffer_size * imgui.INDEX_SIZE
            vtx_arr = vtx_type.from_address(commands.vtx_buffer_data)
            idx_arr = idx_type.from_address(commands.idx_buffer_data)
            self._vertex_buffer.write(vtx_arr)
            self._index_buffer.write(idx_arr)
            idx_pos = 0
            for command in commands.commands:
                texture = self._textures.get(command.texture_id)
                if texture is None:
                    raise ValueError(
                        "Texture {} is not registered. Please add to renderer using register_texture(..). Current textures: {}".format(
                            command.texture_id, list(self._textures)
                        )
                    )
                texture.use(0)
                x, y, z, w = command.clip_rect
                self.ctx.scissor = (int(x), int(fb_height - w), int(z - x), int(w - y))
                self._vao.render(
                    moderngl.TRIANGLES, vertices=command.elem_count, first=idx_pos
                )
                idx_pos += command.elem_count
        self.ctx.scissor = None
