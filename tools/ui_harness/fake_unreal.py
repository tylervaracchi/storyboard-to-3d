# Harness-only stub of Unreal Engine's embedded 'unreal' Python module.
#
# Rich enough to import and construct the whole StoryboardTo3D UI outside
# the editor. Explicit, honest stubs only - NO MagicMock (silent Mock
# truthiness hides wiring bugs). Anything not explicitly defined is served
# by a cached permissive stub class via module-level __getattr__.

import os
import sys
import tempfile

# ---------------------------------------------------------------------------
# Logging (captured so the harness can inspect warnings/errors)
# ---------------------------------------------------------------------------

LOGS = []
WARNINGS = []
ERRORS = []


def log(msg):
    LOGS.append(str(msg))
    print(f"[UE LOG] {msg}")


def log_warning(msg):
    WARNINGS.append(str(msg))
    print(f"[UE WARN] {msg}")


def log_error(msg):
    ERRORS.append(str(msg))
    print(f"[UE ERROR] {msg}")


# ---------------------------------------------------------------------------
# Sandbox paths (Paths.* point into a temp sandbox so managers read/write
# real JSON there instead of a UE project)
# ---------------------------------------------------------------------------

_SANDBOX = os.environ.get("STORYBOARD_HARNESS_SANDBOX") or os.path.join(
    tempfile.gettempdir(), "storyboard_harness_sandbox")


def set_sandbox(path):
    global _SANDBOX
    _SANDBOX = str(path)
    os.makedirs(os.path.join(_SANDBOX, "Content"), exist_ok=True)
    os.makedirs(os.path.join(_SANDBOX, "Saved"), exist_ok=True)


set_sandbox(_SANDBOX)


class Paths:
    @staticmethod
    def project_content_dir():
        return os.path.join(_SANDBOX, "Content") + os.sep

    @staticmethod
    def project_saved_dir():
        return os.path.join(_SANDBOX, "Saved") + os.sep

    @staticmethod
    def project_dir():
        return _SANDBOX + os.sep

    @staticmethod
    def convert_relative_path_to_full(path):
        return os.path.abspath(path)


# ---------------------------------------------------------------------------
# Permissive stub machinery
# ---------------------------------------------------------------------------

class StubCallable:
    """Callable placeholder for an unreal API member.

    Returns honest defaults by name convention:
      is_/has_/does_/can_/was_  -> False
      get_all_/get_selected_/list_/find_ -> []
      everything else           -> None
    """

    def __init__(self, qualname):
        self.qualname = qualname
        self._name = qualname.rsplit(".", 1)[-1]

    def __call__(self, *args, **kwargs):
        n = self._name
        if n.startswith(("is_", "has_", "does_", "can_", "was_")):
            return False
        if n.startswith(("get_all_", "get_selected_", "list_", "find_")):
            return []
        return None

    def __repr__(self):
        return f"<stub {self.qualname}>"


class StubMeta(type):
    """Metaclass so *class-level* attribute access on stub classes also
    yields StubCallables (static methods, enum-ish members)."""

    def __getattr__(cls, name):
        if name.startswith("__"):
            raise AttributeError(name)
        val = StubCallable(f"{cls.__name__}.{name}")
        setattr(cls, name, val)  # cache; identity-stable
        return val


class StubBase(metaclass=StubMeta):
    """Base for permissive stub classes. Instances accept any constructor
    signature and serve StubCallables for unknown attributes."""

    def __init__(self, *args, **kwargs):
        self._stub_args = args
        for k, v in kwargs.items():
            setattr(self, k, v)

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return StubCallable(f"{type(self).__name__}.{name}")

    @classmethod
    def cast(cls, obj):
        return obj

    @classmethod
    def static_class(cls):
        return cls

    def get_name(self):
        return type(self).__name__

    def get_path_name(self):
        return f"/Harness/{type(self).__name__}.{type(self).__name__}"

    def __repr__(self):
        return f"<stub instance {type(self).__name__}>"


_STUB_CLASS_CACHE = {}


def _stub_class(name):
    """Create (once) a permissive stub class for an unknown unreal name."""
    cls = _STUB_CLASS_CACHE.get(name)
    if cls is None:
        cls = StubMeta(name, (StubBase,), {})
        _STUB_CLASS_CACHE[name] = cls
    return cls


def __getattr__(name):  # module-level: anything we didn't define explicitly
    if name.startswith("__"):
        raise AttributeError(name)
    cls = _stub_class(name)
    globals()[name] = cls  # cache so identity is stable
    return cls


# ---------------------------------------------------------------------------
# Simple math / value types
# ---------------------------------------------------------------------------

class Vector:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x, self.y, self.z = float(x), float(y), float(z)

    def __repr__(self):
        return f"Vector({self.x}, {self.y}, {self.z})"

    def __add__(self, o):
        return Vector(self.x + o.x, self.y + o.y, self.z + o.z)

    def __sub__(self, o):
        return Vector(self.x - o.x, self.y - o.y, self.z - o.z)

    def __mul__(self, s):
        return Vector(self.x * s, self.y * s, self.z * s)


class Rotator:
    def __init__(self, roll=0.0, pitch=0.0, yaw=0.0):
        self.roll, self.pitch, self.yaw = float(roll), float(pitch), float(yaw)

    def __repr__(self):
        return f"Rotator({self.roll}, {self.pitch}, {self.yaw})"


class Transform:
    def __init__(self, location=None, rotation=None, scale=None):
        self.location = location or Vector()
        self.rotation = rotation or Rotator()
        self.scale = scale or Vector(1, 1, 1)


class LinearColor:
    def __init__(self, r=0.0, g=0.0, b=0.0, a=1.0):
        self.r, self.g, self.b, self.a = r, g, b, a


class FrameNumber:
    def __init__(self, value=0):
        self.value = int(value)


class FrameRate:
    def __init__(self, numerator=24, denominator=1):
        self.numerator, self.denominator = numerator, denominator


class Name(str):
    pass


class TopLevelAssetPath:
    def __init__(self, package_name="", asset_name=""):
        self.package_name, self.asset_name = str(package_name), str(asset_name)


class SoftObjectPath:
    def __init__(self, path=""):
        self.path = str(path)


# ---------------------------------------------------------------------------
# Asset-like classes (real classes so isinstance checks are meaningful;
# used by build_entry_from_asset tests)
# ---------------------------------------------------------------------------

class Object(StubBase):
    def __init__(self, name="Object", path=None, **kwargs):
        super().__init__(**kwargs)
        self._name = str(name)
        self._path = path or f"/Game/Harness/{name}.{name}"

    def get_name(self):
        return self._name

    def get_path_name(self):
        return self._path


class Actor(Object):
    pass


class StaticMesh(Object):
    pass


class SkeletalMesh(Object):
    pass


class Blueprint(Object):
    pass


class World(Object):
    pass


class Texture2D(Object):
    pass


class StaticMeshActor(Actor):
    pass


class SkeletalMeshActor(Actor):
    pass


class CineCameraActor(Actor):
    pass


class PointLight(Actor):
    pass


class LevelSequence(Object):
    pass


# ---------------------------------------------------------------------------
# Editor libraries / subsystems the UI touches at construction time
# ---------------------------------------------------------------------------

class EditorUtilityLibrary(StubBase):
    @staticmethod
    def get_selected_assets():
        return []


class SystemLibrary(StubBase):
    @staticmethod
    def execute_console_command(world, command):
        log(f"(stub) console command: {command}")
        return None

    @staticmethod
    def get_engine_version():
        return "5.8.0-harness"


class EditorLevelLibrary(StubBase):
    @staticmethod
    def get_editor_world():
        return World("HarnessWorld", "/Game/Harness/HarnessWorld.HarnessWorld")

    @staticmethod
    def get_all_level_actors():
        return []

    @staticmethod
    def spawn_actor_from_class(cls, location=None, rotation=None):
        return None

    @staticmethod
    def load_level(path):
        return False


class EditorAssetLibrary(StubBase):
    @staticmethod
    def does_asset_exist(path):
        return False

    @staticmethod
    def load_asset(path):
        return None

    @staticmethod
    def list_assets(path, recursive=True, include_folder=False):
        return []


class StoryboardThumbnailLibrary(StubBase):
    @staticmethod
    def export_asset_thumbnail(*args, **kwargs):
        return False


class EditorAssetSubsystem(StubBase):
    def sync_browser_to_objects(self, objects):
        return None


class LevelEditorSubsystem(StubBase):
    def editor_play_simulate(self):
        return None


class UnrealEditorSubsystem(StubBase):
    def get_editor_world(self):
        return EditorLevelLibrary.get_editor_world()


class EditorActorSubsystem(StubBase):
    def get_all_level_actors(self):
        return []

    def spawn_actor_from_class(self, cls, location=None, rotation=None):
        return None


_SUBSYSTEM_CACHE = {}


def get_editor_subsystem(subsystem_class):
    key = getattr(subsystem_class, "__name__", str(subsystem_class))
    if key not in _SUBSYSTEM_CACHE:
        _SUBSYSTEM_CACHE[key] = subsystem_class()
    return _SUBSYSTEM_CACHE[key]


# ---------------------------------------------------------------------------
# Misc top-level API
# ---------------------------------------------------------------------------

class ScopedEditorTransaction:
    def __init__(self, description=""):
        self.description = description

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False  # never swallow exceptions

    def cancel(self):  # real UE API has this
        return None


def load_asset(path):
    return None


def load_object(outer, name):
    return None


_TICK_CALLBACKS = {}
_TICK_HANDLE = [0]


def register_slate_post_tick_callback(callback):
    _TICK_HANDLE[0] += 1
    _TICK_CALLBACKS[_TICK_HANDLE[0]] = callback
    return _TICK_HANDLE[0]


def unregister_slate_post_tick_callback(handle):
    _TICK_CALLBACKS.pop(handle, None)


def pump_slate_ticks(delta=0.016, count=1):
    """Harness helper: fire registered slate tick callbacks."""
    for _ in range(count):
        for cb in list(_TICK_CALLBACKS.values()):
            cb(delta)


class AssetToolsHelpers(StubBase):
    @staticmethod
    def get_asset_tools():
        return _stub_class("AssetTools")()


class AssetRegistry(StubBase):
    def get_assets_by_path(self, path, recursive=False):
        return []

    def get_assets(self, ar_filter=None):
        return []

    def get_assets_by_class(self, class_path, search_sub_classes=False):
        return []


class AssetRegistryHelpers(StubBase):
    @staticmethod
    def get_asset_registry():
        return AssetRegistry()
