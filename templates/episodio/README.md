# Modelo de história narrada

Este diretório é um modelo de preparação, sem vídeo ou áudio produzidos.
`new_episode.py` copia os arquivos, define o título e mantém o status de rascunho.

1. Defina `story_kind`: `original_fiction`, `historical` ou `real_account`.
2. Complete `roteiro.md`, `narracao.txt` e `personagens.json`.
3. Crie os assets e registre procedência/licença em `fontes.md`.
4. Gere ou trate a voz; ajuste os planos aos tempos reais.
5. Complete `storyboard.json` com os planos e a duração efetiva.
6. Informe capítulos reais e créditos em `metadata.json` antes de empacotar.

## Planos do storyboard

```json
{
  "duration_seconds": 480,
  "subtitle_mode": "none",
  "soundtrack": "assets/ambiente-e-trilha.wav",
  "soundtrack_gain_db": -22,
  "shots": [
    {"asset": "assets/cais.png", "kind": "image", "pixel_art": true,
     "duration_seconds": 5, "motion": "push_in"},
    {"asset": "assets/carta-animada.mp4", "kind": "video",
     "duration_seconds": 4, "label": "Ficção original"}
  ]
}
```

O exemplo de dois planos explica os campos; ele não cobre 480 segundos.
O arquivo-modelo começa com `shots: []` e não pode ser montado até ser preenchido.
Remova `soundtrack` se não houver essa faixa. `caption` e `label` são rótulos de
cena opcionais, não transcrições da fala.

Movimentos aceitos para imagens: `push_in`, `pull_out`, `pan_left`, `pan_right`,
`none`. Para pixel art animada, personagens e elementos são animados em clips
próprios, sem depender de zoom para simular toda a animação.
