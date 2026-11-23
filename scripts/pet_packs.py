"""Install a bundled companion through Codex's native pet directory."""

import argparse
import json
import os
from pathlib import Path
import re
import tempfile


CATALOG = Path(__file__).resolve().parents[1] / "assets" / "pets"
PACK_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def read_pack(pack_id):
    if not PACK_ID.fullmatch(pack_id):
        raise ValueError(f"Invalid pack ID: {pack_id}")
    folder = CATALOG / pack_id
    manifest_bytes = (folder / "pet.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get("id") != pack_id or not manifest.get("displayName"):
        raise ValueError(f"Invalid manifest for {pack_id}")
    image_name = manifest.get("spritesheetPath")
    if image_name not in {"spritesheet.webp", "spritesheet.png"}:
        raise ValueError(f"Unsupported sprite sheet filename for {pack_id}: {image_name}")
    return manifest, {"pet.json": manifest_bytes, image_name: (folder / image_name).read_bytes()}


def installed_copy_matches(target, files):
    return target.is_dir() and not target.is_symlink() and all(
        (target / name).is_file()
        and not (target / name).is_symlink()
        and (target / name).read_bytes() == data
        for name, data in files.items()
    )


def install(pack_id, home):
    manifest, files = read_pack(pack_id)
    pets = home / "pets"
    target = pets / pack_id
    if target.exists() or target.is_symlink():
        if installed_copy_matches(target, files):
            return manifest, target, "already-installed"
        raise FileExistsError(f"A different package is already present at {target}")

    pets.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".pet-pack-", dir=pets) as staging:
        ready = Path(staging) / pack_id
        ready.mkdir()
        for name, data in files.items():
            (ready / name).write_bytes(data)
        try:
            ready.rename(target)
        except OSError:
            if installed_copy_matches(target, files):
                return manifest, target, "already-installed"
            raise
    return manifest, target, "installed"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="List bundled pet packages")
    installer = commands.add_parser("install", help="Install a pet in the native pet directory")
    installer.add_argument("pack_id")
    installer.add_argument("--codex-home", type=Path, help="Override CODEX_HOME for this installation")
    args = parser.parse_args()

    try:
        if args.command == "list":
            pets = [read_pack(folder.name)[0] for folder in sorted(CATALOG.iterdir()) if folder.is_dir()]
            print(json.dumps(pets, ensure_ascii=True))
        else:
            home = args.codex_home or Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
            manifest, target, status = install(args.pack_id, home.expanduser().resolve())
            print(json.dumps({"status": status, "pet": manifest["displayName"], "path": str(target)}))
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
