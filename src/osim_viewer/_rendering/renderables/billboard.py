# Copyright (C) 2023  ETH Zurich, Manuel Kaufmann, Velko Vechev, Dario Mylonopoulos
import pickle
from typing import List, Union

import cv2
import moderngl
import numpy as np
from moderngl_window.opengl.vao import VAO
from trimesh.triangles import points_to_barycentric

from osim_viewer._rendering.scene.camera import Camera, OpenCVCamera
from osim_viewer._rendering.scene.node import Node
from osim_viewer._rendering.shaders import (
    get_fragmap_program,
    get_outline_program,
    get_screen_texture_program,
)
from osim_viewer._rendering.utils.decorators import hooked


class Billboard(Node):
    """A billboard for displaying a sequence of images as an object in the world"""

    def __init__(self, vertices, textures, img_process_fn=None, icon="\x96", **kwargs):
        """Initializer.
        :param vertices:
            A np array of 4 billboard vertices in world space coordinates of shape (4, 3)
            or an array of shape (N, 4, 3) containing 4 vertices for each frame of the sequence
        :param texture: A list of length N containing paths to the textures as image files
            or a numpy array or PIL Image of shape (N, H, W, C) containing N images of image data with C channels.
        :param img_process_fn: A function with signature f(img, current_frame_id) -> img. This function is called
            once per image before it is displayed so it can be used to process the image in any way.
        """
        super(Billboard, self).__init__(n_frames=len(textures), icon=icon, **kwargs)
        if len(vertices.shape) == 2:
            vertices = vertices[np.newaxis]
        else:
            assert (
                vertices.shape[0] == 1 or vertices.shape[0] == len(textures)
            ), "the length of the sequence of vertices must be 1 or match the number of textures"
        center = np.mean(vertices, axis=(0, 1))
        self.vertices = vertices - center
        self.position = center
        self.img_process_fn = (
            (lambda img, _: img) if img_process_fn is None else img_process_fn
        )
        self._need_redraw = False
        self.uvs = np.repeat(
            np.array([[[0.0, 1.0], [0.0, 0.0], [1.0, 1.0], [1.0, 0.0]]], np.float32),
            self.vertices.shape[0],
            axis=0,
        )
        self.textures = textures
        self.texture = None
        self.texture_alpha = 1.0
        self._current_texture_id = None
        self.backface_culling = False
        self.fragmap = True
        self.outline = True

    @classmethod
    def from_images(cls, textures, scale=1.0, **kwargs):
        """
        Initialize Billboards at default location with the given textures.
        """
        if isinstance(textures, list) and isinstance(textures[0], str):
            img = cv2.imread(textures[0])
        else:
            img = textures[0]
            if not isinstance(img, np.ndarray):
                img = np.asarray(img)
        ar = img.shape[1] / img.shape[0]
        corners = (
            np.array(
                [[1 * ar, 1, 0], [1 * ar, -1, 0], [-1 * ar, 1, 0], [-1 * ar, -1, 0]]
            )
            * scale
        )
        return cls(corners, textures, **kwargs)

    @classmethod
    def from_camera_and_distance(
        cls,
        camera: Camera,
        distance: float,
        cols: int,
        rows: int,
        textures: Union[List[str], np.ndarray],
        image_process_fn=None,
        **kwargs,
    ):
        """
        Initialize a Billboard from a camera object, a distance from the camera, the size of the image in
        pixels and the set of images. `image_process_fn` can be used to apply a function to each image.
        """
        frames = camera.n_frames
        frame_id = camera.current_frame_id
        all_corners = np.zeros((frames, 4, 3))
        for i in range(frames):
            camera.current_frame_id = i
            camera.update_matrices(cols, rows)
            V = camera.get_view_matrix()
            P = camera.get_projection_matrix()
            ndc_from_world = P @ V
            world_p = camera.position + camera.forward * distance
            ndc_p = ndc_from_world @ np.append(world_p, 1.0)
            z = ndc_p[2] / ndc_p[3]
            corners = np.array([[1, 1, z], [1, -1, z], [-1, 1, z], [-1, -1, z]])
            world_from_ndc = np.linalg.inv(ndc_from_world)

            def transform(x):
                v = world_from_ndc @ np.append(x, 1.0)
                v = v[:3] / v[3]
                return v

            corners = np.apply_along_axis(transform, 1, corners)
            all_corners[i] = corners
        camera.current_frame_id = frame_id
        if image_process_fn is None:
            if isinstance(camera, OpenCVCamera) and camera.dist_coeffs is not None:

                def undistort(img, current_frame_id):
                    return cv2.undistort(img, camera.current_K, camera.dist_coeffs)

                image_process_fn = undistort
        return cls(all_corners, textures, image_process_fn, **kwargs)

    @Node.once
    def make_renderable(self, ctx):
        self.prog = get_screen_texture_program()
        vs_path = "mesh_positions.vs.glsl"
        self.outline_program = get_outline_program(vs_path)
        self.fragmap_program = get_fragmap_program(vs_path)
        self.vbo_vertices = ctx.buffer(self.vertices.astype("f4").tobytes())
        self.vbo_uvs = ctx.buffer(self.uvs.astype("f4").tobytes())
        self.vao = ctx.vertex_array(
            self.prog,
            [
                (self.vbo_vertices, "3f4 /v", "in_position"),
                (self.vbo_uvs, "2f4 /v", "in_texcoord_0"),
            ],
        )
        self.positions_vao = VAO("{}:positions".format(self.unique_name))
        self.positions_vao.buffer(self.vbo_vertices, "3f", ["in_position"])
        self.ctx = ctx

    def redraw(self, **kwargs):
        self._need_redraw = True

    def render(self, camera, **kwargs):
        if self.current_frame_id != self._current_texture_id or self._need_redraw:
            self._need_redraw = False
            if self.texture:
                self.texture.release()
            if isinstance(self.textures, list) and isinstance(self.textures[0], str):
                path = self.textures[self.current_frame_id]
                if path.endswith((".pickle", "pkl")):
                    img = pickle.load(open(path, "rb"))
                else:
                    img = cv2.cvtColor(cv2.imread(path), cv2.COLOR_BGR2RGB)
            else:
                img = self.textures[self.current_frame_id]
                if not isinstance(img, np.ndarray):
                    img = np.asarray(img)
                img = img.copy()
            img = self.img_process_fn(img, self.current_frame_id)
            self.texture = self.ctx.texture(
                (img.shape[1], img.shape[0]),
                img.shape[2] if len(img.shape) > 2 else 1,
                img.tobytes(),
            )
            self._current_texture_id = self.current_frame_id
        self.prog["transparency"] = self.texture_alpha
        self.prog["texture0"].value = 0
        self.texture.use(0)
        mvp = camera.get_view_projection_matrix() @ self.model_matrix
        self.prog["mvp"].write(mvp.T.astype("f4").tobytes())
        first = 4 * self.current_frame_id if self.vertices.shape[0] > 1 else 0
        self.vao.render(moderngl.TRIANGLE_STRIP, vertices=4, first=first)

    def render_positions(self, prog):
        if self.is_renderable:
            first = 4 * self.current_frame_id if self.vertices.shape[0] > 1 else 0
            self.positions_vao.render(
                prog, mode=moderngl.TRIANGLE_STRIP, vertices=4, first=first
            )

    @hooked
    def release(self):
        if self.is_renderable:
            self.vao.release()
            self.positions_vao.release(buffer=False)
            self.vbo_vertices.release()
            self.vbo_uvs.release()
            if self.texture:
                self.texture.release()

    @property
    def current_vertices(self):
        return (
            self.vertices[0]
            if self.vertices.shape[0] <= 1
            else self.vertices[self.current_frame_id]
        )

    @property
    def bounds(self):
        return self.get_bounds(self.vertices)

    @property
    def current_bounds(self):
        return self.get_bounds(self.current_vertices)

    def is_transparent(self):
        return self.texture_alpha < 1.0

    def closest_vertex_in_triangle(self, tri_id, point):
        return np.linalg.norm(self.current_vertices - point, axis=-1).argmin()

    def get_bc_coords_from_points(self, tri_id, points):
        indices = np.array([[0, 1, 2], [1, 2, 3]])
        return points_to_barycentric(self.current_vertices[indices[[tri_id]]], points)[
            0
        ]

    def gui_material(self, imgui, show_advanced=True):
        _, self.texture_alpha = imgui.slider_float(
            "Texture alpha##texture_alpha{}".format(self.unique_name),
            self.texture_alpha,
            0.0,
            1.0,
            "%.2f",
        )
