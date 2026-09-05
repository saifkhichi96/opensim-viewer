"""Logical UI coordinates remain independent of framebuffer density."""

from types import SimpleNamespace

import pytest

from osim_viewer._rendering.utils import imgui_integration as integration


@pytest.mark.parametrize("density,scale", [(1, 1), (2, 1), (2, 1.5)])
def test_display_scaling(monkeypatch, density, scale):
    monkeypatch.setattr(integration, "C", SimpleNamespace(ui_scale=scale))
    window = SimpleNamespace(
        size=(800, 600),
        buffer_size=(800 * density, 600 * density),
        width=800,
        height=600,
        viewport_width=800 * density,
        viewport_height=600 * density,
        pixel_ratio=density,
    )
    renderer = SimpleNamespace(wnd=window, io=SimpleNamespace())
    integration.ImGuiRenderer.resize(renderer, *window.buffer_size)
    assert renderer.io.display_size == (800 / scale, 600 / scale)
    assert renderer.io.display_fb_scale == (density * scale, density * scale)


def test_invalid_scale(monkeypatch):
    monkeypatch.setattr(integration, "C", SimpleNamespace(ui_scale=0))
    with pytest.raises(ValueError, match="ui_scale"):
        integration.ImGuiRenderer.resize(SimpleNamespace(), 800, 600)
