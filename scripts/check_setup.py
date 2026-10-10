"""Validate the chosen production mode without contacting external services."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def inspect(config: dict) -> list[tuple[str, bool]]:
    def section(key: str) -> dict:
        value = config.get(key)
        return value if isinstance(value, dict) else {}

    video, voice = section("video"), section("voice")
    youtube, delivery = section("youtube"), section("delivery")
    execution, ai = section("execution"), section("ai")
    return [
        ("Nome e nicho definidos", all(isinstance(config.get(k), str) and config[k].strip() for k in ("name", "topic"))),
        ("Produção iniciada por mensagem no chat", config.get("mode") == "chat_command" and execution.get("trigger") == "user_message" and execution.get("production") == "interactive_workspace" and ai.get("auth_mode") == "chat_work"),
        ("Vídeo Full HD, 16:9 e 24 fps", video.get("width") == 1920 and video.get("height") == 1080 and video.get("aspect_ratio") == "16:9" and video.get("fps") == 24),
        ("Meta de oito minutos", video.get("duration_seconds") == 480),
        ("Voz Thalita brasileira definida", voice.get("engine") == "edge_tts" and voice.get("language") == "pt-BR" and voice.get("name") == "pt-BR-ThalitaMultilingualNeural"),
        ("Entrega no repositório de histórias", delivery.get("destination") == "github" and delivery.get("repository") == "emanoelb5-lgtm/Cala-YouTube-solo-de-hist-rias" and delivery.get("publication_by") == "user"),
        ("Legendas fora da tela por padrão", video.get("subtitle_mode") == "none"),
        ("Modelo de história definido", section("storytelling").get("default_kind") == "original_fiction" and set(section("storytelling").get("allowed_kinds", [])) == {"original_fiction", "historical", "real_account"}),
        ("Publicação manual pelo usuário", youtube.get("publication_mode") == "manual" and youtube.get("automatic_upload") is False),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Conferir configuração sem chamadas externas.")
    parser.add_argument("--config", type=Path, default=Path(__file__).resolve().parents[1] / "config/channel.json")
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            raise ValueError
    except (OSError, ValueError):
        print("Não foi possível ler uma configuração JSON válida.")
        return 1
    checks = inspect(config)
    lines = [f"# Configuração do {config['name']}", "", "| Item | Situação |", "|---|---|"]
    lines += [f"| {label} | {'Configurado' if ready else 'Pendente'} |" for label, ready in checks]
    lines += ["", "Conferência de configuração. A disponibilidade da voz e os arquivos de cada episódio são verificados durante a produção."]
    report = "\n".join(lines) + "\n"
    print(report)
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as output:
            output.write(report)
    return 0 if all(ready for _, ready in checks) else 2


if __name__ == "__main__":
    raise SystemExit(main())
