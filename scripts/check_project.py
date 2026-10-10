"""Check story templates, branding files and local documentation links."""
from __future__ import annotations

import json
from pathlib import Path
import re
import struct

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    errors = []
    for path in sorted(ROOT.rglob("*.json")):
        if any(part in (".git", "work") for part in path.relative_to(ROOT).parts):
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            errors.append(f"JSON inválido: {path.relative_to(ROOT)} ({type(exc).__name__})")
    config = json.loads((ROOT / "config/channel.json").read_text(encoding="utf-8"))
    description = (ROOT / "docs/descricao-do-canal.txt").read_text(encoding="utf-8").strip()
    if description != config["branding"]["channel_description"].strip():
        errors.append("A descrição do canal difere da configuração.")
    for name in config["branding"]["assets"].values():
        path = ROOT / name
        if not path.is_file():
            errors.append(f"Arte ausente: {name}")
            continue
        with path.open("rb") as stream:
            header = stream.read(24)
        if header[:8] != b"\x89PNG\r\n\x1a\n":
            errors.append(f"Arte deve ser PNG: {name}")
            continue
        width, height = struct.unpack(">II", header[16:24])
        if width * 9 != height * 16:
            errors.append(f"Arte deve ter 16:9 exato: {name}")
    template = json.loads((ROOT / "templates/episodio/metadata.json").read_text(encoding="utf-8"))
    if template.get("channel") != config["name"] or template.get("status") != "draft":
        errors.append("O modelo não está marcado como rascunho do canal atual.")
    for path in sorted(ROOT.rglob("*.md")):
        if any(part in (".git", "work") for part in path.relative_to(ROOT).parts):
            continue
        for name in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            if re.match(r"[a-z]+://|#", name):
                continue
            target = name.split("#", 1)[0]
            if target and not (path.parent / target).exists():
                errors.append(f"Link local ausente em {path.relative_to(ROOT)}: {target}")
    if errors:
        print("\n".join(errors))
        return 1
    print("Projeto conferido: JSON, descrição, artes 16:9, modelos e links locais válidos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
