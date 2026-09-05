# Copyright (C) 2023  ETH Zurich, Manuel Kaufmann, Velko Vechev, Dario Mylonopoulos
import json
import os
import tempfile
from abc import ABC, abstractmethod

import numpy as np
from trimesh.transformations import rotation_matrix

from osim_viewer._rendering.configuration import CONFIG as C
from osim_viewer._rendering.renderables.lines import Lines
from osim_viewer._rendering.renderables.meshes import Meshes
from osim_viewer._rendering.renderables.rigid_bodies import RigidBodies
from osim_viewer._rendering.scene.camera_utils import (
    look_at,
    normalize,
    orthographic_projection,
    perspective_projection,
)
from osim_viewer._rendering.scene.node import Node
from osim_viewer._rendering.utils.decorators import hooked


def _transform_vector(transform, vector):
    """Apply affine transformation (4-by-4 matrix) to a 3D vector."""
    return (transform @ np.concatenate([vector, np.array([1])]))[:3]


def _transform_direction(transform, vector):
    """Apply affine transformation (4-by-4 matrix) to a 3D directon."""
    return (transform @ np.concatenate([vector, np.array([0])]))[:3]


class CameraInterface(ABC):
    """
    An abstract class which describes the interface expected by the viewer for using this object as a camera
    """

    def __init__(self):
        self.projection_matrix = None
        self.view_matrix = None
        self.view_projection_matrix = None

    def get_projection_matrix(self):
        if self.projection_matrix is None:
            raise ValueError(
                "update_matrices() must be called before to update the projection matrix"
            )
        return self.projection_matrix

    def get_view_matrix(self):
        if self.view_matrix is None:
            raise ValueError(
                "update_matrices() must be called before to update the view matrix"
            )
        return self.view_matrix

    def get_view_projection_matrix(self):
        if self.view_projection_matrix is None:
            raise ValueError(
                "update_matrices() must be called before to update the view-projection matrix"
            )
        return self.view_projection_matrix

    @abstractmethod
    def update_matrices(self, width, height):
        pass

    @property
    @abstractmethod
    def position(self):
        pass

    @property
    @abstractmethod
    def forward(self):
        pass

    @property
    @abstractmethod
    def up(self):
        pass

    @property
    @abstractmethod
    def right(self):
        pass

    def gui(self, imgui):
        pass


class Camera(Node, CameraInterface):
    """
    A base camera object that provides rendering of a camera mesh and visualization of the camera frustum and coordinate
    system. Subclasses of this class must implement the CameraInterface abstract methods.
    """

    def __init__(
        self,
        inactive_color=(0.5, 0.5, 0.5, 1),
        active_color=(0.6, 0.1, 0.1, 1),
        viewer=None,
        **kwargs,
    ):
        """Initializer
        :param inactive_color: Color that will be used for rendering this object when inactive
        :param active_color:   Color that will be used for rendering this object when active
        :param viewer: The current viewer, if not None the gui for this object will show a button for viewing from this
         camera in the viewer
        """
        super(Camera, self).__init__(icon="\x84", gui_material=False, **kwargs)
        vertices = np.array(
            [
                [0, 0, 0],
                [-1, -1, 1],
                [-1, 1, 1],
                [1, -1, 1],
                [1, 1, 1],
                [0.5, 1.1, 1],
                [-0.5, 1.1, 1],
                [0, 2, 1],
                [0.5, 1.1, 1],
                [-0.5, 1.1, 1],
                [0, 2, 1],
            ],
            dtype=np.float32,
        )
        vertices[:, 0] *= 0.05
        vertices[:, 1] *= 0.03
        vertices[:, 2] *= 0.15
        vertices[:, 2] -= vertices[1, 2] * 1.1
        vertices[:, 2] *= -1
        vertices[:, 0] *= -1
        faces = np.array(
            [
                [0, 1, 2],
                [0, 2, 4],
                [0, 4, 3],
                [0, 3, 1],
                [1, 3, 2],
                [4, 2, 3],
                [5, 6, 7],
                [8, 10, 9],
            ]
        )
        self._active = False
        self.active_color = active_color
        self.inactive_color = inactive_color
        self.mesh = Meshes(
            vertices,
            faces,
            cast_shadow=False,
            flat_shading=True,
            rotation=kwargs.get("rotation"),
            is_selectable=False,
        )
        self.mesh.color = self.inactive_color
        self.add(self.mesh, show_in_hierarchy=False)
        self.frustum = None
        self.origin = None
        self.path = None
        self.viewer = viewer

    @property
    def active(self):
        return self._active

    @active.setter
    def active(self, active):
        self._active = active
        if active:
            self.mesh.color = self.active_color
        else:
            self.mesh.color = self.inactive_color

    @Node.enabled.setter
    def enabled(self, enabled):
        super(Camera, self.__class__).enabled.fset(self, enabled)
        if self.path:
            self.path[0].enabled = enabled
            if self.path[1] is not None:
                self.path[1].enabled = enabled

    @property
    def bounds(self):
        return self.mesh.bounds

    @property
    def current_bounds(self):
        return self.mesh.current_bounds

    def hide_frustum(self):
        if self.frustum:
            self.remove(self.frustum)
            self.frustum = None
        if self.origin:
            self.remove(self.origin)
            self.origin = None

    def show_frustum(self, width, height, distance):
        self.hide_frustum()
        all_lines = np.zeros((self.n_frames, 24, 3), dtype=np.float32)
        frame_id = self.current_frame_id
        for i in range(self.n_frames):
            self.current_frame_id = i
            self.update_matrices(width, height)
            P = self.get_projection_matrix()
            ndc_from_view = P
            view_from_ndc = np.linalg.inv(ndc_from_view)

            def transform(x):
                v = view_from_ndc @ np.append(x, 1.0)
                return v[:3] / v[3]

            view_p = np.array([0.0, 0.0, -distance])
            ndc_p = ndc_from_view @ np.concatenate([view_p, np.array([1])])
            z = ndc_p[2] / ndc_p[3]
            lines = np.array(
                [
                    [-1, -1, -1],
                    [-1, 1, -1],
                    [-1, -1, z],
                    [-1, 1, z],
                    [1, -1, -1],
                    [1, 1, -1],
                    [1, -1, z],
                    [1, 1, z],
                    [-1, -1, -1],
                    [-1, -1, z],
                    [-1, 1, -1],
                    [-1, 1, z],
                    [1, -1, -1],
                    [1, -1, z],
                    [1, 1, -1],
                    [1, 1, z],
                    [-1, -1, -1],
                    [1, -1, -1],
                    [-1, -1, z],
                    [1, -1, z],
                    [-1, 1, -1],
                    [1, 1, -1],
                    [-1, 1, z],
                    [1, 1, z],
                ],
                dtype=np.float32,
            )
            lines = np.apply_along_axis(transform, 1, lines)
            all_lines[i] = lines
        self.frustum = Lines(
            all_lines,
            r_base=0.005,
            mode="lines",
            color=(0.1, 0.1, 0.1, 1),
            cast_shadow=False,
        )
        self.add(self.frustum, show_in_hierarchy=False)
        ori = np.eye(3, dtype=np.float)
        ori[:, 2] *= -1
        self.origin = RigidBodies(
            np.array([0.0, 0.0, 0.0])[np.newaxis], ori[np.newaxis]
        )
        self.add(self.origin, show_in_hierarchy=False)
        self.current_frame_id = frame_id

    def hide_path(self):
        if self.path is not None:
            self.parent.remove(self.path[0])
            if self.path[1] is not None:
                self.parent.remove(self.path[1])
            self.path = None

    def show_path(self):
        self.hide_path()
        all_points = np.zeros((self.n_frames, 3), dtype=np.float32)
        all_oris = np.zeros((self.n_frames, 3, 3), dtype=np.float32)
        frame_id = self.current_frame_id
        for i in range(self.n_frames):
            self.current_frame_id = i
            all_points[i] = self.position
            all_oris[i] = self.rotation @ np.array([[1, 0, 0], [0, 1, 0], [0, 0, -1]])
        path_spheres = RigidBodies(
            all_points, all_oris, radius=0.01, length=0.1, color=(0.92, 0.68, 0.2, 1.0)
        )
        if self.n_frames > 1:
            path_lines = Lines(
                all_points,
                color=(0, 0, 0, 1),
                r_base=0.003,
                mode="line_strip",
                cast_shadow=False,
            )
        else:
            path_lines = None
        assert (
            self.parent is not None
        ), "Camera node must be added to the scene before showing the camera path."
        self.parent.add(path_spheres, show_in_hierarchy=False, enabled=self.enabled)
        if path_lines is not None:
            self.parent.add(path_lines, show_in_hierarchy=False, enabled=self.enabled)
        self.path = (path_spheres, path_lines)
        self.current_frame_id = frame_id

    def render_outline(self, *args, **kwargs):
        self.mesh.render_outline(*args, **kwargs)

    def view_from_camera(self, viewport):
        """If the viewer is specified for this camera, change the current view to view from this camera"""
        if self.viewer:
            self.hide_path()
            self.hide_frustum()
            self.viewer.set_temp_camera(self, viewport)

    def gui(self, imgui):
        if self.viewer:
            if imgui.button("View from camera"):
                self.view_from_camera(self.viewer.viewports[0])
        u, show = imgui.checkbox("Show path", self.path is not None)
        if u:
            if show:
                self.show_path()
            else:
                self.hide_path()

    def gui_context_menu(self, imgui, x: int, y: int):
        if self.viewer:
            if imgui.menu_item(
                "View from camera", shortcut=None, selected=False, enabled=True
            )[1]:
                self.view_from_camera(self.viewer.get_viewport_at_position(x, y))
        u, show = imgui.checkbox("Show path", self.path is not None)
        if u:
            if show:
                self.show_path()
            else:
                self.hide_path()


class WeakPerspectiveCamera(Camera):
    """
    A sequence of weak perspective cameras.
    The camera is positioned at (0,0,1) axis aligned and looks towards the negative z direction following the OpenGL
    conventions.
    """

    def __init__(
        self, scale, translation, cols, rows, near=None, far=None, viewer=None, **kwargs
    ):
        """Initializer.
        :param scale: A np array of scale parameters [sx, sy] of shape (2) or a sequence of parameters of shape (N, 2)
        :param translation: A np array of translation parameters [tx, ty] of shape (2) or a sequence of parameters of
          shape (N, 2).
        :param cols: Number of columns in an image captured by this camera, used for computing the aspect ratio of
          the camera.
        :param rows: Number of rows in an image captured by this camera, used for computing the aspect ratio of
          the camera.
        :param near: Distance of the near plane from the camera.
        :param far: Distance of the far plane from the camera.
        :param viewer: the current viewer, if not None the gui for this object will show a button for viewing from
          this camera in the viewer.
        """
        if len(scale.shape) == 1:
            scale = scale[np.newaxis]
        if len(translation.shape) == 1:
            translation = translation[np.newaxis]
        assert (
            scale.shape[0] == translation.shape[0]
        ), "Number of frames in scale and translation must match"
        kwargs["gui_affine"] = False
        super(WeakPerspectiveCamera, self).__init__(
            n_frames=scale.shape[0], viewer=viewer, **kwargs
        )
        self.scale_factor = scale
        self.translation = translation
        self.cols = cols
        self.rows = rows
        self.near = near if near is not None else C.znear
        self.far = far if far is not None else C.zfar
        self.viewer = viewer
        self.position = np.array([0, 0, 1], dtype=np.float32)
        self._right = np.array([1, 0, 0], dtype=np.float32)
        self._up = np.array([0, 1, 0], dtype=np.float32)
        self._forward = -np.array([0, 0, 1], dtype=np.float32)

    @property
    def forward(self):
        return self._forward

    @property
    def up(self):
        return self._up

    @property
    def right(self):
        return self._right

    def update_matrices(self, width, height):
        sx, sy = self.scale_factor[self.current_frame_id]
        tx, ty = self.translation[self.current_frame_id]
        window_ar = width / height
        camera_ar = self.cols / self.rows
        ar = camera_ar / window_ar
        P = np.array(
            [
                [sx * ar, 0, 0, tx * sx * ar],
                [0, sy, 0, -ty * sy],
                [0, 0, -1, 0],
                [0, 0, 0, 1],
            ]
        )
        znear, zfar = (self.near, self.far)
        P[2][2] = 2.0 / (znear - zfar)
        P[2][3] = (zfar + znear) / (znear - zfar)
        V = look_at(self.position, self.forward, np.array([0, 1, 0]))
        self.projection_matrix = P.astype("f4")
        self.view_matrix = V.astype("f4")
        self.view_projection_matrix = np.matmul(P, V).astype("f4")

    @hooked
    def gui(self, imgui):
        u, show = imgui.checkbox("Show frustum", self.frustum is not None)
        if u:
            if show:
                self.show_frustum(self.cols, self.rows, self.far)
            else:
                self.hide_frustum()

    @hooked
    def gui_context_menu(self, imgui, x: int, y: int):
        u, show = imgui.checkbox("Show frustum", self.frustum is not None)
        if u:
            if show:
                self.show_frustum(self.cols, self.rows, self.far)
            else:
                self.hide_frustum()
        imgui.spacing()
        imgui.separator()
        imgui.spacing()
        super(Camera, self).gui_context_menu(imgui, x, y)


class OpenCVCamera(Camera):
    """A camera described by extrinsics and intrinsics in the format used by OpenCV"""

    def __init__(
        self,
        K,
        Rt,
        cols,
        rows,
        dist_coeffs=None,
        near=None,
        far=None,
        viewer=None,
        **kwargs,
    ):
        """Initializer.
        :param K:  A np array of camera intrinsics in the format used by OpenCV (3, 3) or (N, 3, 3), one for each frame.
        :param Rt: A np array of camera extrinsics in the format used by OpenCV (3, 4) or (N, 3, 4), one for each frame.
        :param dist_coeffs: Lens distortion coefficients in the format used by OpenCV (5).
        :param cols: Width  of the image in pixels, matching the size of the image expected by the intrinsics matrix.
        :param rows: Height of the image in pixels, matching the size of the image expected by the intrinsics matrix.
        :param near: Distance of the near plane from the camera.
        :param far: Distance of the far plane from the camera.
        :param viewer: The current viewer, if not None the gui for this object will show a button for viewing from this
          camera in the viewer.
        """
        self.K = K if len(K.shape) == 3 else K[np.newaxis]
        self.Rt = Rt if len(Rt.shape) == 3 else Rt[np.newaxis]
        assert len(self.Rt.shape) == 3
        assert len(self.K.shape) == 3
        assert (
            self.K.shape[0] == 1
            or self.Rt.shape[0] == 1
            or self.K.shape[0] == self.Rt.shape[0]
        ), f"extrinsics and intrinsics array shape mismatch: {self.Rt.shape} and {self.K.shape}"
        kwargs["gui_affine"] = False
        super(OpenCVCamera, self).__init__(
            viewer=viewer, n_frames=max(self.K.shape[0], self.Rt.shape[0]), **kwargs
        )
        self.position = self.current_position
        self.rotation = self.current_rotation
        self.dist_coeffs = dist_coeffs
        self.cols = cols
        self.rows = rows
        self.near = near if near is not None else C.znear
        self.far = far if far is not None else C.zfar

    def on_frame_update(self):
        self.position = self.current_position
        self.rotation = self.current_rotation

    @property
    def current_position(self):
        Rt = self.current_Rt
        pos = -Rt[:, 0:3].T @ Rt[:, 3]
        return pos

    @property
    def current_rotation(self):
        Rt = self.current_Rt
        rot = np.copy(Rt[:, 0:3].T)
        rot[:, 1:] *= -1.0
        return rot

    @property
    def current_K(self):
        K = self.K[0] if self.K.shape[0] == 1 else self.K[self.current_frame_id]
        return K

    @property
    def current_Rt(self):
        Rt = self.Rt[0] if self.Rt.shape[0] == 1 else self.Rt[self.current_frame_id]
        return Rt

    @property
    def forward(self):
        return self.current_Rt[2, :3]

    @property
    def up(self):
        return -self.current_Rt[1, :3]

    @property
    def right(self):
        return self.current_Rt[0, :3]

    def compute_opengl_view_projection(self, width, height):
        lookat = np.copy(self.current_Rt)
        lookat[1:3, :] *= -1.0
        V = np.vstack((lookat, np.array([0, 0, 0, 1])))
        K = self.current_K
        rows, cols = (self.rows, self.cols)
        near, far = (self.near, self.far)
        window_cols = width / height * rows
        x_offset = (window_cols - cols) * 0.5
        Kgl = np.array(
            [
                [-K[0, 0], 0, -(cols - K[0, 2]) - x_offset, 0],
                [0, -K[1, 1], rows - K[1, 2], 0],
                [0, 0, -(near + far), -(near * far)],
                [0, 0, -1, 0],
            ]
        )
        NDC = np.array(
            [
                [-2 / window_cols, 0, 0, 1],
                [0, -2 / rows, 0, -1],
                [0, 0, 2 / (far - near), -(far + near) / (far - near)],
                [0, 0, 0, 1],
            ]
        )
        P = NDC @ Kgl
        return (V, P)

    def update_matrices(self, width, height):
        V, P = self.compute_opengl_view_projection(width, height)
        self.projection_matrix = P.astype("f4")
        self.view_matrix = V.astype("f4")
        self.view_projection_matrix = np.matmul(P, V).astype("f4")

    def to_pinhole_camera(self, target_distance=5, **kwargs) -> "PinholeCamera":
        """
        Returns a PinholeCamera object with positions and targets computed from this camera.
        :param target_distance: distance from the camera at which the target of the PinholeCamera is placed.

        Remarks:
         The Pinhole camera does not currently support skew, offset from the center and non vertical up vectors.
         Also the fov from the first intrinsic matrix is used for all frames because the PinholeCamera does not
         support sequences of fov values.
        """
        current_frame_id = self.current_frame_id
        positions = np.zeros((self.n_frames, 3))
        targets = np.zeros((self.n_frames, 3))
        for i in range(self.n_frames):
            self.current_frame_id = i
            positions[i] = self.position
            targets[i] = self.position + self.forward * target_distance
        self.current_frame_id = current_frame_id
        fov = np.rad2deg(2 * np.arctan(self.K[0, 1, 2] / self.K[0, 1, 1]))
        return PinholeCamera(
            positions,
            targets,
            self.cols,
            self.rows,
            fov=fov,
            near=self.near,
            far=self.far,
            viewer=self.viewer,
            **kwargs,
        )

    @hooked
    def gui(self, imgui):
        u, show = imgui.checkbox("Show frustum", self.frustum is not None)
        if u:
            if show:
                self.show_frustum(self.cols, self.rows, self.far)
            else:
                self.hide_frustum()

    @hooked
    def gui_context_menu(self, imgui, x: int, y: int):
        u, show = imgui.checkbox("Show frustum", self.frustum is not None)
        if u:
            if show:
                self.show_frustum(self.cols, self.rows, self.far)
            else:
                self.hide_frustum()
        imgui.spacing()
        imgui.separator()
        imgui.spacing()
        super(Camera, self).gui_context_menu(imgui, x, y)


class PinholeCamera(Camera):
    """
    Your classic pinhole camera.
    """

    def __init__(
        self,
        position,
        target,
        cols,
        rows,
        fov=45,
        world_up=None,
        near=None,
        far=None,
        viewer=None,
        **kwargs,
    ):
        positions = position if len(position.shape) == 2 else position[np.newaxis]
        targets = target if len(target.shape) == 2 else target[np.newaxis]
        assert (
            positions.shape[0] == 1
            or targets.shape[0] == 1
            or positions.shape[0] == targets.shape[0]
        ), f"position and target array shape mismatch: {positions.shape} and {targets.shape}"
        if world_up:
            self._world_up = world_up
        else:
            self._world_up = (
                np.array([0.0, 0.0, 1.0]) if C.z_up else np.array([0.0, 1.0, 0.0])
            )
        self._targets = targets
        super(PinholeCamera, self).__init__(
            position=position, n_frames=targets.shape[0], viewer=viewer, **kwargs
        )
        self.cols = cols
        self.rows = rows
        self.near = near if near is not None else C.znear
        self.far = far if far is not None else C.zfar
        self.fov = fov

    @property
    def forward(self):
        forward = self.current_target - self.position
        forward = forward / np.linalg.norm(forward)
        return forward / np.linalg.norm(forward)

    @property
    def up(self):
        up = np.cross(self.forward, self.right)
        return up

    @property
    def right(self):
        right = np.cross(self._world_up, self.forward)
        return right / np.linalg.norm(right)

    @property
    def current_target(self):
        return (
            self._targets[0]
            if self._targets.shape[0] == 1
            else self._targets[self.current_frame_id]
        )

    @property
    def rotation(self):
        return np.array([-self.right, self.up, -self.forward]).T

    def update_matrices(self, width, height):
        P = perspective_projection(
            np.deg2rad(self.fov), width / height, self.near, self.far
        )
        V = look_at(self.position, self.current_target, self._world_up)
        self.projection_matrix = P.astype("f4")
        self.view_matrix = V.astype("f4")
        self.view_projection_matrix = np.matmul(P, V).astype("f4")

    def to_opencv_camera(self, **kwargs) -> OpenCVCamera:
        """
        Returns a OpenCVCamera object with extrinsics and intrinsics computed from this camera.
        """
        current_frame_id = self.current_frame_id
        cols, rows = (self.cols, self.rows)
        Rts = np.zeros((self.n_frames, 3, 4))
        for i in range(self.n_frames):
            self.current_frame_id = i
            self.update_matrices(cols, rows)
            Rts[i] = self.get_view_matrix()[:3]
        self.current_frame_id = current_frame_id
        Rts[:, 1:3, :] *= -1.0
        f = 1.0 / np.tan(np.radians(self.fov / 2))
        c0 = np.array([cols / 2.0, rows / 2.0])
        K = np.array(
            [
                [f * 0.5 * rows, 0.0, c0[0]],
                [0.0, f * 0.5 * rows, c0[1]],
                [0.0, 0.0, 1.0],
            ]
        )
        return OpenCVCamera(
            K,
            Rts,
            cols,
            rows,
            near=self.near,
            far=self.far,
            viewer=self.viewer,
            **kwargs,
        )

    def gui_affine(self, imgui):
        """Render GUI for affine transformations"""
        u, pos = imgui.drag_float3(
            "Position##pos{}".format(self.unique_name),
            *self.position,
            0.1,
            format="%.2f",
        )
        if u:
            self.position = pos

    @hooked
    def gui(self, imgui):
        u, show = imgui.checkbox("Show frustum", self.frustum is not None)
        if u:
            if show:
                self.show_frustum(self.cols, self.rows, self.far)
            else:
                self.hide_frustum()

    @hooked
    def gui_context_menu(self, imgui, x: int, y: int):
        u, show = imgui.checkbox("Show frustum", self.frustum is not None)
        if u:
            if show:
                self.show_frustum(self.cols, self.rows, self.far)
            else:
                self.hide_frustum()
        imgui.spacing()
        imgui.separator()
        imgui.spacing()
        super(Camera, self).gui_context_menu(imgui, x, y)


class ViewerCamera(CameraInterface):
    """
    The camera used by the Viewer. It can be either a Pinhole or Orthographic camera.
    This camera also supports orbiting, panning and generating camera rays.
    """

    def __init__(self, fov=45, orthographic=None, znear=None, zfar=None):
        super(ViewerCamera, self).__init__()
        self.fov = fov
        self.is_ortho = orthographic is not None
        self.ortho_size = 1.0 if orthographic is None else orthographic
        self._position = (
            np.array([0.0, 2.5, 0.0]) if C.z_up else np.array([0.0, 0.0, 2.5])
        )
        self._target = np.array([0.0, 0.0, 0.0])
        self._up = np.array([0.0, 0.0, 1.0]) if C.z_up else np.array([0.0, 1.0, 0.0])
        self.ZOOM_FACTOR = 4
        self.ROT_FACTOR = 0.0025
        self.PAN_FACTOR = 0.01
        self.near = znear if znear is not None else C.znear
        self.far = zfar if zfar is not None else C.zfar
        self.constant_speed = 1.0
        self._control_modes = ["turntable", "trackball", "first_person"]
        self._control_mode = "turntable"
        self._trackball_start_view_inverse = None
        self._trackball_start_hit = None
        self._trackball_start_position = None
        self._trackball_start_up = None
        self.name = "Camera"
        self.icon = "\x84"
        self.animating = False
        self._animation_t = 0.0
        self._animation_time = 0.0
        self._animation_start_position = None
        self._animation_end_position = None
        self._animation_start_target = None
        self._animation_end_target = None

    @property
    def control_mode(self):
        return self._control_mode

    @control_mode.setter
    def control_mode(self, mode):
        if mode not in self._control_modes:
            raise ValueError(f"Invalid camera mode: {mode}")
        if mode == "first_person" or mode == "turntable":
            self.up = (0, 0, 1) if C.z_up else (0, 1, 0)
        self._control_mode = mode

    def copy(self):
        camera = ViewerCamera(self.fov, self.ortho_size, self.near, self.far)
        camera.is_ortho = self.is_ortho
        camera.position = self.position
        camera.target = self.target
        camera.up = self.up
        camera.constant_speed = self.constant_speed
        camera.control_mode = self.control_mode
        return camera

    @property
    def position(self):
        return self._position

    @position.setter
    def position(self, position):
        self._position = np.array(position, dtype=np.float32).copy()

    @property
    def forward(self):
        return normalize(self.target - self.position)

    @property
    def up(self):
        return self._up

    @up.setter
    def up(self, up):
        self._up = np.array(up, dtype=np.float32).copy()

    @property
    def right(self):
        return normalize(np.cross(self.up, self.forward))

    @property
    def target(self):
        return self._target

    @target.setter
    def target(self, t):
        self._target = np.array(t, np.float32).copy()

    def save_cam(self):
        """Saves the current camera parameters"""
        cam_dir = C.export_dir + "/camera_params/"
        if not os.path.exists(cam_dir):
            os.makedirs(cam_dir)
        cam_dict = {}
        cam_dict["position"] = self.position
        cam_dict["target"] = self.target
        cam_dict["up"] = self.up
        cam_dict["ZOOM_FACTOR"] = self.ZOOM_FACTOR
        cam_dict["ROT_FACTOR"] = self.ROT_FACTOR
        cam_dict["PAN_FACTOR"] = self.PAN_FACTOR
        cam_dict["near"] = self.near
        cam_dict["far"] = self.far
        cam_dict = {key: np.asarray(value).tolist() for key, value in cam_dict.items()}
        data = json.dumps({"version": 1, "camera": cam_dict}, allow_nan=False)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=cam_dir, delete=False
        ) as file:
            temporary = file.name
            file.write(data)
        try:
            os.replace(temporary, cam_dir + "cam_params.json")
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def load_cam(self):
        """Loads the camera parameters"""
        cam_dir = C.export_dir + "/camera_params/"
        if not os.path.exists(cam_dir + "cam_params.json"):
            print(
                "No saved JSON camera settings. Legacy pickle files are not loaded; save the camera again."
            )
        else:
            with open(cam_dir + "cam_params.json", encoding="utf-8") as file:
                saved = json.load(file)
            if saved.get("version") != 1:
                raise ValueError("Unsupported camera settings version")
            cam_dict = saved["camera"]
            for key in ("position", "target", "up"):
                cam_dict[key] = np.asarray(cam_dict[key], dtype=float)
                if cam_dict[key].shape != (3,) or not np.isfinite(cam_dict[key]).all():
                    raise ValueError("Invalid camera vector")
            for key in ("ZOOM_FACTOR", "ROT_FACTOR", "PAN_FACTOR", "near", "far"):
                value = cam_dict[key]
                if (
                    not np.isscalar(value)
                    or not np.isfinite(float(value))
                    or float(value) <= 0
                ):
                    raise ValueError("Invalid camera scalar")
            if cam_dict["near"] >= cam_dict["far"]:
                raise ValueError("Invalid camera clipping range")
            if np.linalg.norm(cam_dict["up"]) == 0 or np.array_equal(
                cam_dict["position"], cam_dict["target"]
            ):
                raise ValueError("Invalid camera orientation")
            self.position = cam_dict["position"]
            self.target = cam_dict["target"]
            self.up = cam_dict["up"]
            self.ZOOM_FACTOR = cam_dict["ZOOM_FACTOR"]
            self.ROT_FACTOR = cam_dict["ROT_FACTOR"]
            self.PAN_FACTOR = cam_dict["PAN_FACTOR"]
            self.near = cam_dict["near"]
            self.far = cam_dict["far"]

    def update_matrices(self, width, height):
        if self.is_ortho:
            yscale = self.ortho_size
            xscale = width / height * yscale
            P = orthographic_projection(xscale, yscale, self.near, self.far)
        else:
            P = perspective_projection(
                np.deg2rad(self.fov), width / height, self.near, self.far
            )
        V = look_at(self.position, self.target, self.up)
        self.projection_matrix = P.astype("f4")
        self.view_matrix = V.astype("f4")
        self.view_projection_matrix = np.matmul(P, V).astype("f4")

    def dolly_zoom(self, speed, move_target=False, constant_speed=False):
        """
        Zoom by moving the camera along its view direction.
        If move_target is true the camera target will also move rigidly with the camera.
        """
        self.ortho_size -= 0.1 * np.sign(speed)
        self.ortho_size = max(0.0001, self.ortho_size)
        norm = max(np.linalg.norm(self.position - self.target), 2)
        fwd = self.forward
        speed *= C.camera_zoom_speed
        if move_target or constant_speed:
            if constant_speed:
                norm = self.constant_speed * 20
            self.position += fwd * speed * norm
            self.target += fwd * speed * norm
        else:
            movement_length = speed * norm
            max_movement_length = max(
                np.linalg.norm(self.target - self.position) - 0.01, 0.0
            )
            self.position += fwd * min(movement_length, max_movement_length)

    def pan(self, mouse_dx, mouse_dy):
        """Move the camera in the image plane."""
        sideways = normalize(np.cross(self.forward, self.up))
        up = np.cross(sideways, self.forward)
        speed = max(np.linalg.norm(self.target - self.position) * 0.1, 0.1)
        speed_x = mouse_dx * self.PAN_FACTOR * speed
        speed_y = mouse_dy * self.PAN_FACTOR * speed
        self.position -= sideways * speed_x
        self.target -= sideways * speed_x
        self.position += up * speed_y
        self.target += up * speed_y

    def rotate_azimuth(self, angle):
        """Rotate around camera's up-axis by given angle (in radians)."""
        if np.abs(angle) < 1e-08:
            return
        cam_pose = np.linalg.inv(self.view_matrix)
        up_axis = cam_pose[:3, 1]
        rot = rotation_matrix(angle, up_axis, self.target)
        self.position = _transform_vector(rot, self.position)

    def _rotation_from_mouse_delta(self, mouse_dx: int, mouse_dy: int):
        z_axis = -self.forward
        dot = np.dot(z_axis, self.up)
        rot = np.eye(4)
        if not (mouse_dy > 0 and dot > 0 and (1 - dot < 0.001)) and (
            not (mouse_dy < 0 and dot < 0 and (1 + dot < 0.001))
        ):
            x_axis = -self.right
            rot_x = rotation_matrix(self.ROT_FACTOR * -mouse_dy, x_axis, self.target)
            rot = rot_x @ rot
        y_axis = np.cross(self.forward, self.right)
        x_speed = self.ROT_FACTOR / 10 if 1 - np.abs(dot) < 0.01 else self.ROT_FACTOR
        rot = rotation_matrix(x_speed * -mouse_dx, y_axis, self.target) @ rot
        return rot

    def rotate_azimuth_elevation(self, mouse_dx: int, mouse_dy: int):
        """Rotate the camera position left-right and up-down orbiting around the target (roll is not allowed)."""
        rot = self._rotation_from_mouse_delta(mouse_dx, mouse_dy)
        self.position = _transform_vector(rot, self.position)

    def rotate_first_person(self, mouse_dx: int, mouse_dy: int):
        """Rotate the camera target left-right and up-down (roll is not allowed)."""
        rot = self._rotation_from_mouse_delta(mouse_dx, mouse_dy)
        self.target = (
            _transform_direction(rot, self.target - self.position) + self.position
        )

    def intersect_trackball(self, x: int, y: int, width: int, height: int):
        """
        Return intersection of a line passing through the mouse position at pixel coordinates x, y
        and the trackball as a point in world coordinates.
        """
        nx = 2 * (x + 0.5) / width - 1
        ny = 1 - 2 * (y + 0.5) / height
        if width > height:
            nx *= width / height
        else:
            ny *= height / width
        s = nx * nx + ny * ny
        if s <= 0.5:
            nz = np.sqrt(1 - s)
        else:
            nz = 1 / (2 * np.sqrt(s))
        return self._trackball_start_view_inverse @ np.array((nx, ny, nz))

    def rotate_trackball(self, x: int, y: int, width: int, height: int):
        """Rotate the camera with trackball controls. Must be called after rotate_start()."""
        start = self._trackball_start_hit
        current = self.intersect_trackball(x, y, width, height)
        dist = np.linalg.norm(current - start)
        if dist < 1e-06:
            return
        axis = normalize(np.cross(current, start))
        angle = max(np.arccos(np.dot(normalize(current), normalize(start))), dist)
        rot = rotation_matrix(angle, axis, self.target)
        self.position = _transform_vector(rot, self._trackball_start_position)
        self.up = _transform_direction(rot, self._trackball_start_up)

    def rotate_start(self, x: int, y: int, width: int, height: int):
        """Start rotating the camera. Called on mouse button press."""
        if self.control_mode == "trackball":
            self._trackball_start_view_inverse = look_at(
                self.position, self.target, self.up
            )[:3, :3].T
            self._trackball_start_hit = self.intersect_trackball(x, y, width, height)
            self._trackball_start_position = self.position
            self._trackball_start_up = self.up

    def rotate(
        self, x: int, y: int, mouse_dx: int, mouse_dy: int, width: int, height: int
    ):
        """Rotate the camera. Called on mouse movement."""
        if self.control_mode == "turntable":
            self.rotate_azimuth_elevation(mouse_dx, mouse_dy)
        elif self.control_mode == "trackball":
            self.rotate_trackball(x, y, width, height)
        elif self.control_mode == "first_person":
            self.rotate_first_person(mouse_dx, mouse_dy)

    def get_ray(self, x, y, width, height):
        """Construct a ray going through the middle of the given pixel."""
        w, h = (width, height)
        screen_x = 2 * (x + 0.5) / w - 1
        screen_y = 1 - 2 * (y + 0.5) / h
        scale = self.ortho_size if self.is_ortho else np.tan(np.deg2rad(self.fov) / 2)
        screen_x *= scale * w / h
        screen_y *= scale
        pixel_2d = np.array([screen_x, screen_y, 0 if self.is_ortho else -1])
        cam2world = np.linalg.inv(self.view_matrix)
        pixel_3d = _transform_vector(cam2world, pixel_2d)
        if self.is_ortho:
            ray_origin = pixel_3d
            ray_dir = self.forward
        else:
            eye_origin = np.zeros(3)
            ray_origin = _transform_vector(cam2world, eye_origin)
            ray_dir = pixel_3d - ray_origin
        ray_dir = ray_dir / np.linalg.norm(ray_dir)
        return (ray_origin, ray_dir)

    def move_with_animation(self, end_position, end_target, time=0.25):
        self._animation_start_position = self.position.copy()
        self._animation_end_position = np.array(end_position)
        self._animation_start_target = self.target.copy()
        self._animation_end_target = np.array(end_target)
        self._animation_total_time = time
        self._animation_t = 0.0
        self.animating = True

    def update_animation(self, dt):
        if not self.animating:
            return
        self._animation_t += dt
        if self._animation_t >= self._animation_total_time:
            self.position = self._animation_end_position
            self.target = self._animation_end_target
            self.animating = False
        else:
            t = self._animation_t / self._animation_total_time
            t = t * t * t * (t * (t * 6 - 15) + 10)
            self.position = (
                self._animation_start_position * (1 - t)
                + self._animation_end_position * t
            )
            self.target = (
                self._animation_start_target * (1 - t) + self._animation_end_target * t
            )

    def gui(self, imgui):
        _, self.is_ortho = imgui.checkbox("Orthographic Camera", self.is_ortho)
        _, self.fov = imgui.slider_float(
            "Camera FOV##fov", self.fov, 0.1, 180.0, "%.1f"
        )
        _, self.position = imgui.drag_float3("Position", *self.position)
        _, self.target = imgui.drag_float3("Target", *self.target)
        _, self.up = imgui.drag_float3("Up", *self.up)
        imgui.spacing()
        control_modes_labels = ["Turntable", "Trackball", "First Person"]
        u, idx = imgui.combo(
            "Control mode",
            self._control_modes.index(self.control_mode),
            control_modes_labels,
        )
        if u and idx >= 0 and (idx <= len(self._control_modes)):
            self.control_mode = self._control_modes[idx]
