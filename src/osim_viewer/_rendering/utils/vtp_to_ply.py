# Copyright (C) 2024 Max Planck Institute for Intelligent Systems, Marilyn Keller, marilyn.keller@tuebingen.mpg.de
import argparse
import os
from pathlib import Path

import trimesh

from .vtp import read_vtp


def convert_meshes(src_folder, dst_folder):
    src = src_folder
    if src[-1] != "/":
        src += "/"
    if dst_folder is None:
        target = src + "../Geometry_ply/"
    else:
        target = dst_folder
        if target[-1] != "/":
            target += "/"
    os.makedirs(target, exist_ok=True)
    for filename in os.listdir(src):
        if os.path.exists(target + filename + ".ply"):
            continue
        ext = os.path.splitext(filename)[-1]
        if ext not in [".vtp", ".obj"]:
            print("Skipping " + filename)
            continue
        if ext == ".vtp":
            vertices, faces = read_vtp(Path(src) / filename)
            mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
        else:
            mesh = trimesh.load(Path(src) / filename, force="mesh", process=False)
        mesh.export(target + filename + ".ply")
        print("Converted mesh: " + target + filename + ".ply")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Convert a folder of vtp files to a folder of ply files"
    )
    parser.add_argument(
        "src_folder",
        help="folder containing the vtp files to convert",
        default="/home/kellerm/Dropbox/MPI/TML/Fullbody_TLModels_v2.0_OS4x/Geometry/",
        type=str,
    )
    parser.add_argument(
        "dst_folder", help="folder to save the ply files", default=None, type=str
    )
    args = parser.parse_args()
    src_folder = args.src_folder
    dst_folder = args.dst_folder
