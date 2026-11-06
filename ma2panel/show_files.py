"""Bounded, opaque MA2 gzip transport. Never extract or rewrite show contents."""
import gzip
import hashlib
import os
import stat
import uuid
import zlib
from pathlib import Path

MAX_FILE = 512 * 1024 * 1024
MAX_EXPANDED = 2 * 1024 * 1024 * 1024
CHUNK = 128 * 1024


def fingerprint(st):
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def regular(path):
    st = Path(path).lstat()
    if not stat.S_ISREG(st.st_mode) or not 0 < st.st_size <= MAX_FILE:
        raise ValueError('нужен обычный непустой файл шоу до 512 МиБ, без симлинков')
    return fingerprint(st)


def validate(path):
    before = regular(path)
    total = 0
    try:
        with gzip.open(path, 'rb') as stream:
            while block := stream.read(CHUNK):
                total += len(block)
                if total > MAX_EXPANDED:
                    raise ValueError('распакованный поток превышает 2 ГиБ')
    except (EOFError, gzip.BadGzipFile, zlib.error) as exc:
        raise ValueError('повреждён gzip-контейнер шоу') from exc
    if not total or regular(path) != before:
        raise ValueError('файл пуст или изменился во время проверки')
    return before


def snapshot(source, target):
    """Exclusive verified copy; source must stay unchanged throughout the read."""
    source, target = Path(source), Path(target)
    before = regular(source)
    created = False
    digest = hashlib.sha256()
    try:
        flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
        with os.fdopen(os.open(source, flags), 'rb') as src:
            if fingerprint(os.fstat(src.fileno())) != before:
                raise ValueError('файл изменился перед чтением')
            with target.open('xb') as dest:
                created = True
                size = 0
                while block := src.read(CHUNK):
                    size += len(block)
                    if size > MAX_FILE:
                        raise ValueError('файл превышает 512 МиБ')
                    dest.write(block)
                    digest.update(block)
                dest.flush()
                os.fsync(dest.fileno())
            if fingerprint(os.fstat(src.fileno())) != before or regular(source) != before:
                raise ValueError('файл изменился во время копирования')
        validate(target)
        return {'size': size, 'sha256': digest.hexdigest(), 'mtime': before[3] / 1e9, 'fingerprint': before}
    except BaseException:
        if created:
            target.unlink(missing_ok=True)
        raise


def publish(source, folder, name):
    """Publish complete file atomically without replacing any existing directory entry."""
    folder = Path(folder)
    target = folder / (name + '.show.gz')
    temp = folder / ('.panel-' + uuid.uuid4().hex + '.part')
    try:
        snapshot(source, temp)
        os.link(temp, target)  # exclusive even for dangling symlinks; NTFS supports hardlinks
    finally:
        temp.unlink(missing_ok=True)
    return target
