"""Load Linko's existing generator with a scoped Windows locking adapter.

Older Linko checkouts import fcntl unconditionally. Only that module's import
is adapted; Python's global imports and the checkout's source stay untouched.
"""
from __future__ import annotations

import builtins
import copy
import errno
import importlib.util
import os
import sys
import time
from pathlib import Path, PurePath, PurePosixPath
from types import SimpleNamespace

WINDOWS = sys.platform == "win32"
LOCK_EX = 2
LOCK_UN = 8


def windows_flock(stream, operation: int) -> None:
    """Serialize catalogue builds with an exclusive lock on byte zero."""
    import msvcrt

    fd = stream if isinstance(stream, int) else stream.fileno()
    position = os.lseek(fd, 0, os.SEEK_CUR)
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        if operation == LOCK_UN:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        elif operation == LOCK_EX:
            while True:
                try:
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    break
                except OSError as exc:
                    if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                        raise
                    time.sleep(0.1)
        else:
            raise ValueError("The catalogue adapter supports exclusive lock and unlock only.")
    finally:
        os.lseek(fd, position, os.SEEK_SET)


_WINDOWS_FCNTL = SimpleNamespace(LOCK_EX=LOCK_EX, LOCK_UN=LOCK_UN, flock=windows_flock)


def _catalogue_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name == "fcntl" and level == 0:
        return _WINDOWS_FCNTL
    return builtins.__import__(name, globals, locals, fromlist, level)


def load_engine(root: Path):
    spec = importlib.util.spec_from_file_location("linko_catalogue", root / "catalogue.py")
    module = importlib.util.module_from_spec(spec)
    if WINDOWS:
        module.__builtins__ = {**vars(builtins), "__import__": _catalogue_import}
    spec.loader.exec_module(module)
    # The legacy generator uses str(MANIFEST) as a generated output key.
    # Keep that key portable even when native Path uses Windows separators.
    if isinstance(getattr(module, "MANIFEST", None), PurePath):
        module.MANIFEST = PurePosixPath(module.MANIFEST.as_posix())
    if not hasattr(module, "product_images") and all(hasattr(module, name) for name in ('validate', 'card', 'detail')):
        # Older checkouts can still save canonical arrays. Project only in
        # memory for their existing validator/renderers; JSON stays canonical.
        def legacy_product(product):
            if 'images' not in product:
                return product
            images = product['images']
            if 'image' in product or 'gallery' in product:
                raise ValueError('images: remove legacy image/gallery fields')
            if not isinstance(images, list) or not images:
                raise ValueError('images: requires at least one image')
            for n, image in enumerate(images):
                if not isinstance(image, dict) or image.get('secondary') is not None:
                    raise ValueError(f'images[{n}]: expected one image object')
                if image.get('presentation', 'cover') not in {'cover','cutout','illustration'}:
                    raise ValueError(f'images[{n}].presentation: invalid style')
                for dim in ('width', 'height'):
                    value = image.get(dim, 240)
                    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                        raise ValueError(f'images[{n}].{dim}: positive integer required')
            result = copy.deepcopy(product)
            result['image'] = {'width':240, 'height':240, **result.pop('images')[0]}
            result['gallery'] = copy.deepcopy(images[1:])
            return result

        original_validate, original_card, original_detail = module.validate, module.card, module.detail
        module.validate = lambda catalog, products: original_validate(catalog, {key:legacy_product(p) for key,p in products.items()})
        module.card = lambda product, *args, **kwargs: original_card(legacy_product(product), *args, **kwargs)
        module.detail = lambda product, *args, **kwargs: original_detail(legacy_product(product), *args, **kwargs)
    return module
