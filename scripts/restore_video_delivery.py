"""Restore reviewed MP4 bytes transported in smaller Git blobs, without re-encoding."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def restore(manifest: Path, *, check_only: bool = False, stage: bool = False) -> dict:
    folder = manifest.parent
    episode = folder.parent
    if folder.name != "transporte" or episode.parent != ROOT / "videos":
        raise ValueError("Manifesto fora da pasta de entrega de um episódio.")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if data.get("version") != 1 or data.get("filename") != "video.mp4":
        raise ValueError("Formato de manifesto desconhecido.")
    expected_sha = data["sha256"]
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
        raise ValueError("Hash final inválido.")
    metadata = json.loads((episode / "metadata.json").read_text(encoding="utf-8"))
    if metadata["video_sha256"] != expected_sha:
        raise ValueError("Manifesto não corresponde ao vídeo revisado nos metadados.")
    config = json.loads((ROOT / "config/channel.json").read_text(encoding="utf-8"))
    if not 0 < data["bytes"] < config["delivery"]["max_video_file_bytes"]:
        raise ValueError("Arquivo fora do tamanho de entrega configurado.")
    chunks = []
    paths = []
    for index, part in enumerate(data["parts"]):
        name = f"video.mp4.part{index:03d}"
        if part["filename"] != name:
            raise ValueError("Ordem ou nome das partes inválido.")
        path = folder / name
        if path.is_symlink():
            raise ValueError("Partes devem ser arquivos regulares.")
        content = path.read_bytes()
        if len(content) != part["bytes"] or hashlib.sha256(content).hexdigest() != part["sha256"]:
            raise ValueError(f"Parte incompleta ou alterada: {name}")
        chunks.append(content)
        paths.append(path)
    content = b"".join(chunks)
    if len(content) != data["bytes"] or hashlib.sha256(content).hexdigest() != expected_sha:
        raise ValueError("A recomposição não corresponde ao MP4 revisado.")
    output = episode / "video.mp4"
    if not check_only:
        output.write_bytes(content)
        if hashlib.sha256(output.read_bytes()).hexdigest() != expected_sha:
            raise ValueError("A gravação do MP4 não preservou os bytes verificados.")
        for path in paths:
            path.unlink()
        manifest.unlink()
        if not any(folder.iterdir()):
            folder.rmdir()
        if stage:
            tracked = [output, manifest, *paths]
            subprocess.run(["git", "add", "--", *(str(path.relative_to(ROOT)) for path in tracked)],
                           cwd=ROOT, check=True)
    return {"episode": episode.name, "bytes": len(content), "sha256": expected_sha,
            "verified": True, "restored": not check_only}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--stage", action="store_true")
    args = parser.parse_args()
    if args.check_only and args.stage:
        parser.error("--check-only e --stage são modos separados.")
    manifests = sorted((ROOT / "videos").glob("*/transporte/manifest.json"))
    for manifest in manifests:
        print(json.dumps(restore(manifest, check_only=args.check_only, stage=args.stage), ensure_ascii=False), flush=True)
    if not manifests:
        print("Nenhuma entrega em partes pendente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
