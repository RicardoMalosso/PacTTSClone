"""Keep the updater available when launching older application overlays."""
import importlib.abc
import importlib.machinery
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).parent


class AppLoader(importlib.abc.Loader):
    def __init__(self, original):
        self.original = original

    def create_module(self, spec):
        return self.original.create_module(spec)

    def exec_module(self, module):
        self.original.exec_module(module)
        from pacttsclone import updater
        from pacttsclone.domain import GenerationSettings

        if "kitten" not in GenerationSettings.model_fields:
            original_validate = GenerationSettings.model_validate.__func__

            @classmethod
            def validate(cls, value, **kwargs):
                if isinstance(value, dict):
                    value = {k: v for k, v in value.items() if k in cls.model_fields}
                return original_validate(cls, value, **kwargs)

            GenerationSettings.model_validate = validate
        original = module.create_app

        def create_app(*args, **kwargs):
            app = original(*args, **kwargs)
            updater.attach_manager(app, updater.ACTIVE_INSTANCE)
            setup = app.state.runtime_setup
            actual = getattr(app.state.service.settings, "engine_id", "omnivoice")
            if setup.state.get("active_engine", "omnivoice") != actual:
                setup.update(active_engine=actual, engine_enabled=False)
            return app

        module.create_app = create_app


class ControllerFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "pacttsclone.updater":
            return importlib.util.spec_from_file_location(fullname, ROOT / "updater.py")
        if fullname == "pacttsclone.app":
            spec = importlib.machinery.PathFinder.find_spec(fullname, path)
            if spec and spec.loader:
                spec.loader = AppLoader(spec.loader)
            return spec
        return None


def install():
    if not any(type(f).__name__ == "ControllerFinder" for f in sys.meta_path):
        sys.meta_path.insert(0, ControllerFinder())
