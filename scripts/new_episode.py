"""Create a draft episode from the narrated-story template."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]


def create(slug: str, title: str, story_kind: str) -> Path:
    if not re.fullmatch(r"ep-\d{3}-[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        raise ValueError("Use um identificador como ep-001-a-carta.")
    if not 1 <= len(title.strip()) <= 100:
        raise ValueError("O título deve ter de 1 a 100 caracteres.")
    config = json.loads((ROOT / "config/channel.json").read_text(encoding="utf-8"))
    if story_kind not in config["storytelling"]["allowed_kinds"]:
        raise ValueError("Tipo de história desconhecido.")
    episode = ROOT / config["delivery"]["episodes_directory"] / slug
    if episode.exists():
        raise ValueError("Essa pasta já existe; nenhum arquivo foi sobrescrito.")
    shutil.copytree(ROOT / "templates/episodio", episode)
    (episode / "assets").mkdir()
    metadata = json.loads((episode / "metadata.json").read_text(encoding="utf-8"))
    metadata.update(title=title.strip(), channel=config["name"], story_kind=story_kind)
    if story_kind != "original_fiction":
        metadata["fiction_notice"] = ""
    (episode / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return episode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--story-kind", default="original_fiction")
    args = parser.parse_args()
    try:
        episode = create(args.slug, args.title, args.story_kind)
    except (ValueError, OSError) as exc:
        print(f"Rascunho não criado: {exc}")
        return 1
    print(f"Rascunho criado em {episode.relative_to(ROOT)}. Complete roteiro e assets antes de produzir.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
