# Copyright (C) 2023  ETH Zurich, Manuel Kaufmann, Velko Vechev, Dario Mylonopoulos
import moderngl
import numpy as np

from osim_viewer._rendering.configuration import CONFIG as C
from osim_viewer._rendering.renderables.coordinate_system import CoordinateSystem
from osim_viewer._rendering.renderables.lines import Lines2D
from osim_viewer._rendering.renderables.plane import ChessboardPlane
from osim_viewer._rendering.scene.camera import ViewerCamera
from osim_viewer._rendering.scene.light import Light
from osim_viewer._rendering.scene.node import Node
from osim_viewer._rendering.utils.utils import (
    compute_union_of_bounds,
    compute_union_of_current_bounds,
)


class Scene(Node):
    """Generic scene node"""

    def __init__(self, **kwargs):
        """Create a scene with a name."""
        kwargs["gui_material"] = False
        super(Scene, self).__init__(**kwargs)
        self.lights = []
        self.camera = None
        self.ctx = None
        self.backface_culling = True
        self.fps = C.scene_fps
        self.background_color = C.background_color
        self.lights.append(
            Light.facing_origin(
                light_color=(1.0, 1.0, 1.0),
                name="Back Light",
                position=(0.0, -15.0, 10.0) if C.z_up else (0.0, 10.0, -15.0),
                shadow_enabled=False,
            )
        )
        self.lights.append(
            Light.facing_origin(
                light_color=(1.0, 1.0, 1.0),
                name="Front Light",
                position=(0.0, 15.0, 10.0) if C.z_up else (0.0, 10.0, 15.0),
            )
        )
        self.add(*self.lights)
        self.ambient_strength = 2.0
        self.origin = CoordinateSystem(
            name="Origin", length=0.1, gui_affine=False, gui_material=False
        )
        self.add(self.origin)
        self.floor = ChessboardPlane(
            100.0,
            200,
            (0.9, 0.9, 0.9, 1.0),
            (0.82, 0.82, 0.82, 1.0),
            "xy" if C.z_up else "xz",
            name="Floor",
        )
        self.floor.material.diffuse = 0.1
        self.add(self.floor)
        self.camera_target = Lines2D(
            np.array(
                [[-1, 0, 0], [1, 0, 0], [0, -1, 0], [0, 1, 0], [0, 0, -1], [0, 0, 1]]
            ),
            color=(0.2, 0.2, 0.2, 1),
            mode="lines",
        )
        self.add(self.camera_target, show_in_hierarchy=False, enabled=False)
        N = 50
        t = np.empty(N * 2, dtype=np.float32)
        t[0::2] = np.linspace(0, 2.0 * np.pi, N)
        t[1::2] = np.roll(np.linspace(0, 2.0 * np.pi, N), 1)
        z = np.zeros_like(t)
        c = np.cos(t)
        s = np.sin(t)
        trackball_vertices = np.concatenate(
            (np.vstack((z, c, s)).T, np.vstack((c, z, s)).T, np.vstack((c, s, z)).T)
        )
        trackball_colors = np.concatenate(
            (
                np.tile((1, 0, 0, 1), (N, 1)),
                np.tile((0, 0.8, 0, 1), (N, 1)),
                np.tile((0, 0, 1, 1), (N, 1)),
            )
        )
        self.trackball = Lines2D(trackball_vertices, trackball_colors, mode="lines")
        self.add(self.trackball, show_in_hierarchy=False, enabled=False)
        self.custom_font = None
        self.properties_icon = "\x94"
        self.selected_object = None
        self.gui_selected_object = None
        self.expanded = True

    def render(self, **kwargs):
        camera = kwargs["camera"]
        if isinstance(camera, ViewerCamera):
            if camera.is_ortho:
                scale = camera.ortho_size * 0.8
            else:
                scale = (
                    np.radians(camera.fov)
                    * 0.4
                    * np.linalg.norm(camera.target - camera.position)
                )
            if self.camera_target.enabled:
                self.camera_target.position = camera.target
                self.camera_target.scale = scale * 0.05
            if self.trackball.enabled:
                self.trackball.position = camera.target
                self.trackball.scale = scale
        else:
            self.camera_target.scale = 0
            self.trackball.scale = 0
        rs = self.collect_nodes()
        transparent = []
        for r in rs:
            if not r.is_transparent():
                if self.backface_culling and r.backface_culling:
                    self.ctx.enable(moderngl.CULL_FACE)
                else:
                    self.ctx.disable(moderngl.CULL_FACE)
                self.safe_render(r, **kwargs)
            else:
                transparent.append(r)
        fbo = kwargs["fbo"]
        for r in sorted(
            transparent,
            key=lambda x: np.linalg.norm(x.position - camera.position),
            reverse=True,
        ):
            if self.backface_culling and r.backface_culling:
                self.ctx.enable(moderngl.CULL_FACE)
            else:
                self.ctx.disable(moderngl.CULL_FACE)
            self.ctx.depth_func = "<"
            fbo.color_mask = (False, False, False, False)
            self.safe_render_depth_prepass(r, **kwargs)
            fbo.color_mask = (True, True, True, True)
            self.ctx.depth_func = "<="
            self.safe_render(r, **kwargs)
        self.ctx.depth_func = "<"

    def safe_render_depth_prepass(self, r, **kwargs):
        if not r.is_renderable:
            r.make_renderable(self.ctx)
        r.render_depth_prepass(**kwargs)

    def safe_render(self, r, **kwargs):
        if not r.is_renderable:
            r.make_renderable(self.ctx)
        r.render(**kwargs)

    def make_renderable(self, ctx):
        self.ctx = ctx
        rs = self.collect_nodes(req_enabled=False)
        for r in rs:
            r.make_renderable(self.ctx)

    @property
    def bounds(self):
        return compute_union_of_bounds([n for n in self.nodes if n not in self.lights])

    @property
    def current_bounds(self):
        return compute_union_of_current_bounds(
            [
                n
                for n in self.nodes
                if n not in self.lights
                and n != self.camera_target
                and (n != self.trackball)
            ]
        )

    @property
    def bounds_without_floor(self):
        return compute_union_of_current_bounds(
            [n for n in self.nodes if n not in self.lights and n != self.floor]
        )

    def auto_set_floor(self):
        """Finds the minimum lower bound in the y coordinate from all the children bounds and uses that as the floor"""
        if self.floor is not None and len(self.nodes) > 0:
            axis = 2 if C.z_up else 1
            self.floor.position[axis] = self.current_bounds[axis, 0]
            self.floor.update_transform(parent_transform=self.model_matrix)

    def auto_set_camera_target(self):
        """Sets the camera target to the average of the center of all objects in the scene"""
        centers = []
        for n in self.nodes:
            if n not in self.lights:
                centers.append(n.current_center)
        if isinstance(self.camera, ViewerCamera) and len(centers) > 0:
            self.camera.target = np.array(centers).mean(0)

    @property
    def light_mode(self):
        return self._light_mode

    @light_mode.setter
    def light_mode(self, mode):
        if mode == "default":
            self._light_mode = mode
            self.ambient_strength = 2.0
            for l in self.lights:
                l.strength = 1.0
        elif mode == "dark":
            self._light_mode = mode
            self.ambient_strength = 0.4
            for l in self.lights:
                l.strength = 1.0
        elif mode == "diffuse":
            self._light_mode = mode
            self.ambient_strength = 1.0
            for l in self.lights:
                l.strength = 2.0
        else:
            raise ValueError(f"Invalid light mode: {mode}")

    def collect_nodes(self, req_enabled=True, obj_type=Node):
        nodes = []

        def rec_collect_nodes(nn):
            if not req_enabled or nn.enabled:
                if isinstance(nn, obj_type):
                    nodes.append(nn)
                for n_child in nn.nodes:
                    rec_collect_nodes(n_child)

        for n in self.nodes:
            rec_collect_nodes(n)
        return nodes

    def get_node_by_name(self, name):
        assert name != ""
        ns = self.collect_nodes()
        for n in ns:
            if n.name == name:
                return n
        return None

    def get_node_by_uid(self, uid):
        ns = self.collect_nodes()
        for n in ns:
            if n.uid == uid:
                return n
        return None

    def select(
        self, obj, selected_node=None, selected_instance=None, selected_tri_id=None
    ):
        """Set 'obj' as the selected object"""
        self.selected_object = obj
        if isinstance(obj, Node):
            self.selected_object.on_selection(
                selected_node, selected_instance, selected_tri_id
            )
        if obj is not None:
            self.gui_selected_object = obj

    def is_selected(self, obj):
        """Returns true if obj is currently selected"""
        return obj == self.selected_object

    def gui_selected(self, imgui):
        """GUI to edit the selected node"""
        if self.gui_selected_object:
            s = self.gui_selected_object
            imgui.indent(22)
            imgui.push_font(self.custom_font)
            imgui.text(f"{s.icon} {s.name}")
            imgui.pop_font()
            if hasattr(s, "gui_modes") and len(s.gui_modes) > 1:
                imgui.push_font(self.custom_font)
                imgui.spacing()
                for i, (gm_key, gm_val) in enumerate(s.gui_modes.items()):
                    if s.selected_mode == gm_key:
                        imgui.push_style_color(
                            imgui.COLOR_BUTTON, 0.26, 0.59, 0.98, 1.0
                        )
                    mode_clicked = imgui.button(f" {gm_val['icon']}{gm_val['title']} ")
                    if s.selected_mode == gm_key:
                        imgui.pop_style_color()
                    if mode_clicked:
                        s.selected_mode = gm_key
                    if i != len(s.gui_modes) - 1:
                        imgui.same_line()
                imgui.pop_font()
                imgui.spacing()
                if "fn" in s.gui_modes[s.selected_mode]:
                    s.gui_modes[s.selected_mode]["fn"](imgui)
            s.gui(imgui)
            imgui.unindent()
            if hasattr(s, "gui_controls"):
                imgui.spacing()
                imgui.spacing()
                imgui.spacing()
                for i, (gc_key, gc_val) in enumerate(s.gui_controls.items()):
                    if not gc_val["is_visible"]:
                        continue
                    imgui.begin_group()
                    imgui.push_font(self.custom_font)
                    imgui.text(f"{gc_val['icon']}")
                    imgui.pop_font()
                    imgui.end_group()
                    imgui.same_line(spacing=8)
                    imgui.begin_group()
                    gc_val["fn"](imgui)
                    imgui.end_group()
                    imgui.spacing()
                    imgui.spacing()
                    imgui.spacing()
            imgui.spacing()
            imgui.spacing()
            imgui.spacing()
            imgui.same_line(spacing=8)
            imgui.begin_group()
            if imgui.collapsing_header("Stats")[0]:
                s.gui_stats(imgui)
            imgui.end_group()

    def gui(self, imgui):
        imgui.text(f"FPS: {self.fps:.1f}")
        uc, color = imgui.color_edit4("Background", *self.background_color)
        if uc:
            self.background_color = color
        _, self.ambient_strength = imgui.drag_float(
            "Ambient strength",
            self.ambient_strength,
            0.01,
            min_value=0.0,
            max_value=10.0,
            format="%.2f",
        )

    def gui_editor(self, imgui, viewports, viewport_mode):
        """GUI to control scene settings."""
        self.gui_camera(imgui, viewports, viewport_mode)
        imgui.spacing()
        imgui.separator()
        imgui.spacing()
        self.gui_hierarchy(imgui, [self])
        imgui.spacing()
        imgui.separator()
        imgui.spacing()
        imgui.spacing()
        self.gui_selected(imgui)

    def gui_camera(self, imgui, viewports, viewport_mode):
        if viewport_mode == "single":
            suffixes = [""]
        elif viewport_mode == "split_v":
            suffixes = ["(left)", "(right)"]
        elif viewport_mode == "split_h":
            suffixes = ["(top)", "(bottom)"]
        else:
            suffixes = ["(top left)", "(top right)", "(bottom left)", "(bottom right)"]
        for suffix, v in zip(suffixes, viewports):
            camera = v.camera
            imgui.push_font(self.custom_font)
            imgui.push_style_var(imgui.STYLE_FRAME_PADDING, (0, 2))
            flags = imgui.TREE_NODE_LEAF | imgui.TREE_NODE_FRAME_PADDING
            if self.is_selected(camera):
                flags |= imgui.TREE_NODE_SELECTED
            if isinstance(camera, ViewerCamera):
                name = camera.name
            else:
                name = f"Camera: {camera.name}"
            camera_expanded = imgui.tree_node(
                f"{camera.icon}  {name}##tree_node_r_camera", flags
            )
            if imgui.is_item_clicked():
                self.select(camera)
            if suffix:
                imgui.same_line()
                pos = imgui.get_cursor_pos_x()
                avail = imgui.get_content_region_available()[0] - 3
                if avail > imgui.calc_text_size(suffix)[0]:
                    imgui.same_line()
                    avail -= imgui.calc_text_size(suffix)[0]
                    imgui.set_cursor_pos_x(pos + avail)
                    imgui.text(suffix)
                else:
                    imgui.text("")
            imgui.pop_style_var()
            imgui.pop_font()
            if camera_expanded:
                imgui.tree_pop()

    def gui_hierarchy(self, imgui, rs):
        for r in rs:
            if not r.show_in_hierarchy:
                continue
            curr_enabled = r.enabled
            if not curr_enabled:
                imgui.push_style_color(imgui.COLOR_TEXT, 1.0, 1.0, 1.0, 0.4)
            imgui.push_font(self.custom_font)
            imgui.push_style_var(imgui.STYLE_FRAME_PADDING, (0, 2))
            flags = imgui.TREE_NODE_OPEN_ON_ARROW | imgui.TREE_NODE_FRAME_PADDING
            if r.expanded:
                flags |= imgui.TREE_NODE_DEFAULT_OPEN
            if self.is_selected(r):
                flags |= imgui.TREE_NODE_SELECTED
            if not any((c.show_in_hierarchy for c in r.nodes)):
                flags |= imgui.TREE_NODE_LEAF
            r.expanded = imgui.tree_node(
                "{} {}##tree_node_{}".format(r.icon, r.name, r.unique_name), flags
            )
            if imgui.is_item_clicked():
                self.select(r)
            imgui.pop_style_var()
            imgui.pop_font()
            if r != self:
                imgui.same_line(position=imgui.get_window_content_region_max().x - 25)
                eu, enabled = imgui.checkbox(
                    "##enabled_r_{}".format(r.unique_name), r.enabled
                )
                if eu:
                    r.enabled = enabled
            if r.expanded:
                self.gui_hierarchy(imgui, r.nodes)
                imgui.tree_pop()
            if not curr_enabled:
                imgui.pop_style_color(1)

    def add_light(self, light):
        self.lights.append(light)

    @property
    def n_lights(self):
        return len(self.lights)

    @property
    def n_frames(self):
        n_frames = 1
        ns = self.collect_nodes(req_enabled=False)
        for n in ns:
            if n._enabled_frames is None:
                n_frames = max(n_frames, n.n_frames)
            else:
                n_frames = max(n_frames, n._enabled_frames.shape[0])
        return n_frames

    def render_outline(self, *args, **kwargs):
        return
