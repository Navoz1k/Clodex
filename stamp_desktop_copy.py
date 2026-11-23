"""Stamp the rebuilt archive's digest into the detached Windows test build."""
import ctypes
import hashlib
import json
import struct
from ctypes import wintypes
RESOURCE_TYPE = 'Integrity'
RESOURCE_NAME = 'ElectronAsar'

kernel = ctypes.WinDLL('kernel32', use_last_error=True)


def win_call(name, result, *parameters):
    fn = getattr(kernel, name)
    fn.restype = result
    fn.argtypes = parameters
    return fn


def require(result):
    if not result:
        raise ctypes.WinError(ctypes.get_last_error())
    return result


def load_resource(exe):
    handle = wintypes.HANDLE
    enum_callback = ctypes.WINFUNCTYPE(wintypes.BOOL, handle, wintypes.LPCWSTR,
                                        wintypes.LPCWSTR, wintypes.WORD, wintypes.LPARAM)
    load_library = win_call('LoadLibraryExW', handle, wintypes.LPCWSTR, handle, wintypes.DWORD)
    enum_languages = win_call('EnumResourceLanguagesW', wintypes.BOOL, handle, wintypes.LPCWSTR,
                              wintypes.LPCWSTR, enum_callback, wintypes.LPARAM)
    find = win_call('FindResourceExW', handle, handle, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.WORD)
    size_of = win_call('SizeofResource', wintypes.DWORD, handle, handle)
    load = win_call('LoadResource', handle, handle, handle)
    lock = win_call('LockResource', ctypes.c_void_p, handle)
    free = win_call('FreeLibrary', wintypes.BOOL, handle)
    library = require(load_library(str(exe), None, 0x22))
    languages = []

    @enum_callback
    def collect(_handle, _kind, _name, language, _param):
        languages.append(language)
        return True

    try:
        require(enum_languages(library, RESOURCE_TYPE, RESOURCE_NAME, collect, 0))
        assert len(languages) == 1, f'Unexpected Integrity/ElectronAsar languages: {languages}'
        match = require(find(library, RESOURCE_TYPE, RESOURCE_NAME, languages[0]))
        pointer = require(lock(require(load(library, match))))
        return languages[0], ctypes.string_at(pointer, require(size_of(library, match)))
    finally:
        require(free(library))


def store_resource(exe, language, data):
    handle = wintypes.HANDLE
    begin = win_call('BeginUpdateResourceW', handle, wintypes.LPCWSTR, wintypes.BOOL)
    update = win_call('UpdateResourceW', wintypes.BOOL, handle, wintypes.LPCWSTR, wintypes.LPCWSTR,
                      wintypes.WORD, ctypes.c_void_p, wintypes.DWORD)
    end = win_call('EndUpdateResourceW', wintypes.BOOL, handle, wintypes.BOOL)
    transaction = require(begin(str(exe), False))
    buffer = ctypes.create_string_buffer(data)
    if not update(transaction, RESOURCE_TYPE, RESOURCE_NAME, language, buffer, len(data)):
        err = ctypes.WinError(ctypes.get_last_error())
        end(transaction, True)
        raise err
    require(end(transaction, False))


def stamp_archive(copy_dir):
    exe = copy_dir / 'ChatGPT.exe'
    asar = copy_dir / 'resources' / 'app.asar'
    assert exe.resolve().parent == copy_dir.resolve()
    assert asar.resolve().parent == (copy_dir / 'resources').resolve()
    assert copy_dir.name == 'desktop-copy'
    with asar.open('rb') as archive:
        _, _, _, json_size = struct.unpack('<4I', archive.read(16))
        digest = hashlib.sha256(archive.read(json_size)).hexdigest()
    language, raw = load_resource(exe)
    null_suffix = raw[len(raw.rstrip(b'\0')):]
    records = json.loads(raw.rstrip(b'\0').decode('utf8'))
    matches = [item for item in records if item['file'].replace('\\', '/').lower() == 'resources/app.asar']
    assert len(matches) == 1 and matches[0]['alg'].lower() == 'sha256'
    old = matches[0]['value']
    matches[0]['value'] = digest
    updated = json.dumps(records, separators=(',', ':')).encode('utf8') + null_suffix
    if old != digest:
        store_resource(exe, language, updated)
    assert json.loads(load_resource(exe)[1].rstrip(b'\0').decode('utf8')) == records
    print('Integrity verification kept enabled. Expected archive SHA-256:', digest)
