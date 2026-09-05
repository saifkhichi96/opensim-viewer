"""Focused VTK XML PolyData reader (positions and polygon surfaces only)."""

import base64
import re
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path

import numpy as np

TYPES = dict(
    Float32="f4",
    Float64="f8",
    Int32="i4",
    UInt32="u4",
    Int64="i8",
    UInt64="u8",
    Int16="i2",
    UInt16="u2",
    Int8="i1",
    UInt8="u1",
)
LIMIT = 512 * 1024 * 1024


def decode64(value):
    """Decode independently padded VTK header and payload segments."""
    value = re.sub(rb"\s+", b"", value)
    result = bytearray()
    while value:
        pad = value.find(b"=")
        end = len(value) if pad < 0 else pad + 1
        while value[end : end + 1] == b"=":
            end += 1
        result.extend(base64.b64decode(value[:end], validate=True))
        value = value[end:]
    return bytes(result)


def payload(data, header, compressed):
    """Validate and unpack length-prefixed or zlib-blocked array data."""
    size = header.itemsize

    def ints(offset, count):
        if offset + count * size > len(data):
            raise ValueError("Truncated VTP header")
        return np.frombuffer(data, header, count, offset)

    if not compressed:
        length = int(ints(0, 1)[0])
        if length > LIMIT or size + length > len(data):
            raise ValueError("Invalid VTP payload length")
        return data[size : size + length]
    blocks, block_size, last_size = map(int, ints(0, 3))
    if (
        blocks > LIMIT // size
        or max(block_size, last_size, blocks * block_size) > LIMIT
    ):
        raise ValueError("VTP array exceeds size limit")
    lengths = ints(3 * size, blocks)
    offset = (3 + blocks) * size
    output = bytearray()
    for i, length in enumerate(lengths):
        length = int(length)
        expected = last_size if i == blocks - 1 else block_size
        decoder = zlib.decompressobj()
        block = decoder.decompress(data[offset : offset + length], expected + 1)
        if len(block) != expected or not decoder.eof:
            raise ValueError("Invalid compressed VTP block")
        output.extend(block)
        offset += length
    return bytes(output)


def triangulate(points, polygon):
    """Ear-clip planar polygons, including concave faces, preserving winding."""
    polygon = list(map(int, polygon))
    if len(polygon) > 3 and polygon[0] == polygon[-1]:
        polygon.pop()
    if len(polygon) < 3 or len(set(polygon)) != len(polygon):
        raise ValueError("Invalid polygon connectivity")
    if len(polygon) == 3:
        return [polygon]
    xyz = np.asarray(points[polygon], dtype=np.float64)
    xyz = xyz - xyz.mean(axis=0)
    normal = np.cross(xyz, np.roll(xyz, -1, axis=0)).sum(axis=0)
    xy = np.delete(xyz, np.argmax(np.abs(normal)), axis=1)

    def cross(a, b, c):
        u, v = b - a, c - a
        return u[0] * v[1] - u[1] * v[0]

    area = sum(cross(np.zeros(2), a, b) for a, b in zip(xy, np.roll(xy, -1, axis=0)))
    sign = 1 if area > 0 else -1
    eps = max(float(np.ptp(xy, axis=0).max()) ** 2 * 1e-12, 1e-20)
    remaining = list(range(len(polygon)))
    result = []
    while len(remaining) > 3:
        for j, b in enumerate(remaining):
            a, c = remaining[j - 1], remaining[(j + 1) % len(remaining)]
            if sign * cross(xy[a], xy[b], xy[c]) <= eps:
                continue
            if any(
                all(
                    sign * cross(xy[u], xy[v], xy[p]) >= -eps
                    for u, v in [(a, b), (b, c), (c, a)]
                )
                for p in remaining
                if p not in (a, b, c)
            ):
                continue
            result.append([polygon[a], polygon[b], polygon[c]])
            remaining.pop(j)
            break
        else:
            raise ValueError("Degenerate or non-simple VTP polygon")
    result.append([polygon[i] for i in remaining])
    return result


def read_vtp(path):
    """Read ASCII, binary or appended PolyData; support zlib and both byte orders."""
    raw = Path(path).read_bytes()
    appended, encoding = None, None
    match = re.search(rb"<AppendedData\b[^>]*>", raw)
    if match:
        end = raw.rfind(b"</AppendedData>")
        if end < match.end():
            raise ValueError("Unclosed AppendedData")
        tag = ET.fromstring(match.group() + b"</AppendedData>")
        encoding = tag.get("encoding", "base64")
        content = raw[match.end() : end].lstrip()
        if not content.startswith(b"_"):
            raise ValueError("Missing appended data sentinel")
        appended = content[1:]
        raw = raw[: match.end()] + b"_" + raw[end:]
    root = ET.fromstring(raw)
    if root.tag != "VTKFile" or root.get("type") != "PolyData":
        raise ValueError("Expected VTK PolyData")
    compressor = root.get("compressor")
    if compressor not in (None, "vtkZLibDataCompressor"):
        raise ValueError("Unsupported VTP compressor")
    try:
        endian = {"LittleEndian": "<", "BigEndian": ">"}[
            root.get("byte_order", "LittleEndian")
        ]
        header = np.dtype(
            endian + {"UInt32": "u4", "UInt64": "u8"}[root.get("header_type", "UInt32")]
        )
    except KeyError as exc:
        raise ValueError("Unsupported VTP byte order or header type") from exc

    def array(node):
        if node is None or node.get("type") not in TYPES:
            raise ValueError("Missing or unsupported VTP DataArray")
        dtype = np.dtype(endian + TYPES[node.get("type")])
        fmt = node.get("format", "ascii")
        if fmt == "ascii":
            return np.array((node.text or "").split(), dtype=dtype)
        if fmt == "binary":
            data = decode64((node.text or "").encode())
        elif fmt == "appended" and appended is not None:
            offset = int(node.get("offset", "-1"))
            if not 0 <= offset < len(appended):
                raise ValueError("Invalid appended offset")
            if encoding not in ("base64", "raw"):
                raise ValueError("Unsupported appended encoding")
            data = (
                decode64(appended[offset:])
                if encoding == "base64"
                else appended[offset:]
            )
        else:
            raise ValueError("Unsupported VTP array format")
        return np.frombuffer(payload(data, header, compressor is not None), dtype=dtype)

    vertices, faces, vertex_offset = [], [], 0
    for piece in root.findall("./PolyData/Piece"):
        points = array(piece.find("./Points/DataArray")).reshape(-1, 3)
        if (
            len(points) != int(piece.get("NumberOfPoints", "-1"))
            or not np.isfinite(points).all()
        ):
            raise ValueError("Invalid VTP points")
        for kind in ("Polys", "Strips"):
            cells = piece.find(kind)
            if cells is None:
                continue
            conn = array(cells.find("DataArray[@Name='connectivity']"))
            offsets = array(cells.find("DataArray[@Name='offsets']"))
            if conn.dtype.kind not in "iu" or offsets.dtype.kind not in "iu":
                raise ValueError("Non-integer VTP topology")
            if len(conn) and (conn.min() < 0 or conn.max() >= len(points)):
                raise ValueError("VTP vertex index out of bounds")
            start = 0
            for end in offsets:
                end = int(end)
                if not start < end <= len(conn):
                    raise ValueError("Invalid VTP cell offsets")
                polygon = conn[start:end]
                triangles = (
                    triangulate(points, polygon)
                    if kind == "Polys"
                    else [
                        list(polygon[i : i + 3])
                        if i % 2 == 0
                        else [polygon[i + 1], polygon[i], polygon[i + 2]]
                        for i in range(len(polygon) - 2)
                    ]
                )
                faces.extend(np.asarray(triangles, dtype=np.int64) + vertex_offset)
                start = end
            if start != len(conn):
                raise ValueError("Unconsumed VTP connectivity")
        vertices.append(points)
        vertex_offset += len(points)
    if not vertices or not faces:
        raise ValueError("VTP contains no polygon surface")
    return np.concatenate(vertices), np.asarray(faces, dtype=np.int64)
