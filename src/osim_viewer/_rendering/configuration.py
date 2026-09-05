# Copyright (C) 2023  ETH Zurich, Manuel Kaufmann, Velko Vechev, Dario Mylonopoulos
import os

import toml


class Configuration(object):
    class __Configuration:
        def next_gui_id(self):
            self._gui_counter += 1
            return self._gui_counter

        def __init__(self):
            self._conf = toml.load(
                os.path.join(os.path.dirname(__file__), "viewer.toml")
            )
            if os.environ.get("OSIM_VIEWER_CONFIG", None) is not None:
                env_conf = os.environ["OSIM_VIEWER_CONFIG"]
                if os.path.isdir(env_conf):
                    conf = toml.load(os.path.join(env_conf, "viewer.toml"))
                else:
                    conf = toml.load(env_conf)
                self.update_conf(conf)
            local_conf = os.path.join(os.getcwd(), "osim-viewer.toml")
            if os.path.exists(local_conf):
                self.update_conf(local_conf)
            self._gui_counter = 0

        def update_conf(self, conf_obj):
            """Merge a flat TOML settings file or dictionary into current defaults."""
            if isinstance(conf_obj, str):
                conf_obj = toml.load(conf_obj)
            else:
                if not isinstance(conf_obj, dict):
                    raise TypeError("Expected settings dictionary or TOML path")
            unknown = set(conf_obj) - set(self._conf)
            if unknown:
                raise ValueError(f"Unknown viewer settings: {sorted(unknown)}")
            self._conf.update(conf_obj)

        def __getattr__(self, item):
            try:
                return self._conf[item]
            except KeyError as exc:
                raise AttributeError(item) from exc

    instance = None

    def __new__(cls, *args, **kwargs):
        if not Configuration.instance:
            Configuration.instance = Configuration.__Configuration()
        return Configuration.instance

    def __getattr__(self, item):
        return getattr(self.instance, item)

    def __setattr__(self, key, value):
        return setattr(self.instance, key, value)


CONFIG = Configuration()
