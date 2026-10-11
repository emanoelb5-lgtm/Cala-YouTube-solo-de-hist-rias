"""Validate real deliverables and create the manual YouTube publishing package."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def stamp(seconds: float) -> str:
    value = int(seconds)
    minutes, seconds = divmod(value, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"


def read_srt(text: str) -> list[tuple[float, float]]:
    def seconds(value: str) -> float:
        h, m, remainder = value.split(":")
        return int(h) * 3600 + int(m) * 60 + float(remainder.replace(",", "."))
    result = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = block.splitlines()
        if len(lines) < 3:
            raise ValueError("SRT inválido.")
        start, end = lines[1].split(" --> ")
        result.append((seconds(start), seconds(end)))
    return result


def package(episode: Path, config: dict) -> dict:
    from PIL import Image
    required = ("video.mp4", "miniatura.png", "miniatura.jpg", "narracao.txt", "roteiro.md", "fontes.md", "metadata.json", "narracao.json")
    for name in required:
        if not (episode / name).is_file() or not (episode / name).stat().st_size:
            raise ValueError(f"Arquivo de entrega ausente: {name}.")
    if (episode / "video.mp4").stat().st_size >= config["delivery"]["max_video_file_bytes"]:
        raise ValueError("Prepare o MP4 para o limite de envio antes de validar a entrega.")
    metadata = json.loads((episode / "metadata.json").read_text(encoding="utf-8"))
    if metadata.get("status") == "draft":
        raise ValueError("O episódio ainda está marcado como rascunho.")
    if metadata.get("channel") != config["name"]:
        raise ValueError("O episódio pertence a outro canal.")
    kind = metadata.get("story_kind")
    if kind not in config["storytelling"]["allowed_kinds"]:
        raise ValueError("Tipo de história ausente ou desconhecido.")
    if kind == "original_fiction" and not metadata.get("fiction_notice", "").strip():
        raise ValueError("A ficção precisa ser identificada na descrição.")
    if kind != "original_fiction" and not metadata.get("sources"):
        raise ValueError("Relatos reais e históricos exigem fontes.")
    if not metadata.get("summary", "").strip() or not metadata.get("credits", "").strip():
        raise ValueError("Complete a apresentação do episódio e os créditos.")
    title = metadata.get("title", "")
    if not isinstance(title, str) or not (1 <= len(title) <= 100):
        raise ValueError("O título deve ter entre 1 e 100 caracteres.")
    tags = metadata.get("tags", [])
    if not isinstance(tags, list) or not all(isinstance(tag, str) and tag for tag in tags) or sum(len(tag) + 1 for tag in tags) > 500:
        raise ValueError("Tags inválidas ou extensas demais.")
    probe = json.loads(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(episode / "video.mp4")], text=True))
    video = next(s for s in probe["streams"] if s["codec_type"] == "video")
    audio = next(s for s in probe["streams"] if s["codec_type"] == "audio")
    subtitle_mode = metadata.get("subtitle_mode", config["video"].get("subtitle_mode", "none"))
    embedded_subtitles = sum(s["codec_type"] == "subtitle" for s in probe["streams"])
    if subtitle_mode not in ("external", "burned_in", "none"):
        raise ValueError("Modo de legenda desconhecido.")
    if subtitle_mode in ("burned_in", "none") and embedded_subtitles:
        raise ValueError("O modo de legenda definido exige um MP4 sem faixa de legenda embutida.")
    duration = float(probe["format"]["duration"])
    target = config["video"]
    fraction = video["avg_frame_rate"].split("/")
    fps = int(fraction[0]) / int(fraction[1])
    if video["width"] != target["width"] or video["height"] != target["height"] or abs(fps - target["fps"]) > 0.01:
        raise ValueError("Formato do vídeo diferente da configuração.")
    video_duration = float(video.get("duration") or int(video["nb_frames"]) / fps)
    audio_duration = float(audio.get("duration") or duration)
    if abs(video_duration - duration) > max(0.15, 2 / fps) or abs(audio_duration - duration) > 0.2:
        raise ValueError("Imagem e áudio precisam cobrir toda a duração; uma faixa está incompleta.")
    if video.get("nb_frames") and abs(int(video["nb_frames"]) / fps - duration) > 0.15:
        raise ValueError("O número de quadros não cobre toda a duração do episódio.")
    if abs(duration - target["duration_seconds"]) > target["duration_tolerance_seconds"]:
        raise ValueError("Duração fora da meta do canal.")
    with Image.open(episode / "miniatura.png") as thumbnail:
        thumbnail_size = thumbnail.size
        if abs(thumbnail.width / thumbnail.height - 16 / 9) > 0.002:
            raise ValueError("A miniatura deve ser em 16:9.")
    with Image.open(episode / "miniatura.jpg") as thumbnail_jpg:
        if thumbnail_jpg.size != thumbnail_size or (episode / "miniatura.jpg").stat().st_size >= 2 * 1024 * 1024:
            raise ValueError("A miniatura JPG deve ter a mesma resolução e menos de 2 MB.")
    narration = json.loads((episode / "narracao.json").read_text(encoding="utf-8"))
    text_sha = hashlib.sha256((episode / "narracao.txt").read_text(encoding="utf-8").strip().encode()).hexdigest()
    configured_voice = narration.get("voice") == config["voice"]["name"] and narration.get("engine") == config["voice"]["engine"]
    recorded_voice = narration.get("engine") == "user_recording" and config["voice"].get("allow_user_recording", False)
    if narration.get("text_sha256") != text_sha or not (configured_voice or recorded_voice):
        raise ValueError("Narração diferente do roteiro ou da voz definida.")
    cues = []
    subtitle_file = episode / "legendas.srt"
    if subtitle_mode != "none" and not subtitle_file.is_file():
        raise ValueError("O modo de legenda escolhido exige um SRT.")
    if subtitle_file.is_file():
        subtitles = subtitle_file.read_text(encoding="utf-8")
        if any(len(block.splitlines()[2:]) > 2 for block in re.split(r"\n\s*\n", subtitles.strip())):
            raise ValueError("As legendas devem ter até duas linhas.")
        cues = read_srt(subtitles)
        if not cues or any(start >= end or start < 0 or end > duration + 0.1 for start, end in cues) or any(a[1] > b[0] + 0.025 for a, b in zip(cues, cues[1:])):
            raise ValueError("As legendas contêm tempos inválidos.")
    chapters = metadata.get("chapters", [])
    if not chapters or chapters[0].get("start_seconds") != 0:
        raise ValueError("Capítulos devem começar em 00:00.")
    starts = [chapter["start_seconds"] for chapter in chapters] + [duration]
    if any(b - a < 10 for a, b in zip(starts, starts[1:])):
        raise ValueError("Os capítulos devem durar pelo menos dez segundos.")
    description = metadata["summary"].strip() + "\n\nCAPÍTULOS\n"
    description += "\n".join(f"{stamp(c['start_seconds'])} {c['title']}" for c in chapters)
    if kind == "original_fiction":
        description += "\n\n" + metadata["fiction_notice"].strip()
    if metadata.get("sources"):
        description += "\n\nFONTES E LEITURA\n" + "\n".join(f"{s['name']}\n{s['url']}" for s in metadata["sources"])
    description += "\n\nCRÉDITOS\n" + metadata["credits"].strip()
    description += "\n\n" + " ".join(metadata.get("hashtags", [])) + "\n"
    if len(description) > 5000:
        raise ValueError("Descrição acima do limite de 5.000 caracteres.")
    metadata.update({"description": description, "duration_seconds": duration, "publication_mode": "manual", "status": "technically_validated", "video_sha256": hashlib.sha256((episode / "video.mp4").read_bytes()).hexdigest()})
    (episode / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (episode / "descricao.txt").write_text(description, encoding="utf-8")
    (episode / "titulo.txt").write_text(title + "\n\nALTERNATIVAS\n" + "\n".join(metadata.get("alternative_titles", [])) + "\n", encoding="utf-8")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-xerror", "-i", str(episode / "video.mp4"), "-f", "null", "-"], check=True, stdout=subprocess.DEVNULL)
    report = {"status": "technically_validated", "video": {"width": video["width"], "height": video["height"], "fps": fps,
              "duration_seconds": duration, "stream_duration_seconds": video_duration,
              "frames": int(video["nb_frames"]) if video.get("nb_frames") else None,
              "codec": video["codec_name"], "size_bytes": (episode / "video.mp4").stat().st_size},
              "audio": {"codec": audio["codec_name"], "sample_rate": int(audio["sample_rate"]), "channels": audio["channels"]},
              "voice": narration["voice"], "thumbnail_size": list(thumbnail_size),
              "subtitle_cues": len(cues), "chapters": len(chapters), "full_decode": "passed",
              "subtitle_mode": subtitle_mode, "embedded_subtitle_streams": embedded_subtitles,
              "youtube_upload": "manual", "visual_review": "required_separately", "story_kind": kind}
    (episode / "qa.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if subtitle_mode == "none":
        subtitle_step = "Este episódio não usa legendas na tela."
        if subtitle_file.is_file():
            subtitle_step += " [legendas.srt](legendas.srt) está disponível como transcrição opcional."
    elif subtitle_mode == "burned_in":
        subtitle_step = "O vídeo já tem legendas fixas. Guarde [legendas.srt](legendas.srt) como transcrição; uma faixa de legenda adicional pode duplicar o texto na tela."
    else:
        subtitle_step = "Envie [legendas.srt](legendas.srt) como legenda em português."
    review_note = (
        "A revisão por planos está registrada em [revisao.json](revisao.json).\n"
        "Assista ao vídeo antes de publicar e escolha a visibilidade no canal."
        if (episode / "revisao.json").is_file()
        else "Assista ao vídeo inteiro e registre a revisão visual e de som antes de publicar."
    )
    guide = f"""# Materiais para publicar — {config['name']}

A conferência técnica foi concluída. {review_note}

**Título:** {title}

1. Baixe [video.mp4](video.mp4). Na página do arquivo no GitHub, use o botão de download do arquivo bruto.
2. Abra o YouTube Studio e envie o vídeo.
3. Use o título principal de [titulo.txt](titulo.txt) e copie [descricao.txt](descricao.txt) no campo de descrição.
4. Envie [miniatura.jpg](miniatura.jpg) como miniatura. A versão [PNG](miniatura.png) também está disponível. {subtitle_step}
5. Consulte [metadata.json](metadata.json) para tags e categoria. Defina público, visibilidade e horário no seu canal.

Confira a origem das imagens e as reconstituições nos créditos. Responda às
opções de conteúdo alterado ou sintético conforme o material e as orientações
exibidas no YouTube Studio.

[Verificação técnica](qa.json) · [Roteiro](roteiro.md) · [Fontes e créditos](fontes.md)
"""
    (episode / "PUBLICAR.md").write_text(guide, encoding="utf-8")
    deliverables = list(required) + ["descricao.txt", "titulo.txt", "qa.json", "PUBLICAR.md"]
    if subtitle_file.is_file():
        deliverables.append("legendas.srt")
    deliverables += [name for name in ("narracao.mp3", "storyboard.json", "personagens.json", "revisao.json",
                                      "plano_cenas.json", "prompts.json", "palavras.json") if (episode / name).is_file()]
    production = episode / "producao"
    if production.is_dir():
        deliverables += [str(path.relative_to(episode)) for path in sorted(production.rglob("*"))
                         if path.is_file() and not path.is_symlink()
                         and not any(part.startswith(".") or part == "__pycache__" for part in path.relative_to(production).parts)
                         and path.suffix != ".pyc"]
    hashes = []
    for name in sorted(deliverables):
        digest = hashlib.sha256()
        with (episode / name).open("rb") as stream:
            while block := stream.read(1024 * 1024):
                digest.update(block)
        hashes.append(f"{digest.hexdigest()}  {name}")
    (episode / "checksums.sha256").write_text("\n".join(hashes) + "\n", encoding="utf-8")
    archive = episode / "publicacao.partial.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name in sorted(set(deliverables + ["checksums.sha256"]) - {"video.mp4"}):
            bundle.write(episode / name, name)
        for path in sorted((episode / "assets").rglob("*")):
            if path.is_file() and not path.is_symlink() and not any(p.startswith(".") for p in path.relative_to(episode).parts):
                bundle.write(path, path.relative_to(episode))
        bundle.write(ROOT / "config/channel.json", "producao/channel.json")
        for path in sorted((ROOT / "scripts").glob("*.py")):
            bundle.write(path, "producao/scripts/" + path.name)
        bundle.write(ROOT / "requirements-production.txt", "producao/requirements-production.txt")
    with zipfile.ZipFile(archive) as bundle:
        if bundle.testzip() is not None:
            raise ValueError("O pacote ZIP não passou na conferência de integridade.")
    archive.replace(episode / "publicacao.zip")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads((ROOT / "config/channel.json").read_text(encoding="utf-8"))
    try:
        report = package(args.episode.resolve(), config)
    except (ValueError, KeyError, OSError, StopIteration, subprocess.CalledProcessError) as exc:
        print(f"A entrega não foi validada: {exc}")
        return 1
    print(f"Pacote validado: {report['video']['duration_seconds']:.2f} s, {report['subtitle_cues']} legendas, {report['chapters']} capítulos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
