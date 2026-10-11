# Fio de Lume — produção por pedido no chat

O usuário autorizou uma cópia adaptada do Quase Infinito para histórias narradas,
com nome, descrição, artes e regras próprios.

## Destino deste projeto

Use **emanoelb5-lgtm/Cala-YouTube-solo-de-hist-rias**. Este canal se chama
**Fio de Lume** e tem a frase **Histórias que continuam em você.** Leia
`config/channel.json`, `docs/canal.md` e `docs/como-serao-os-videos.md`.

A origem técnica é `emanoelb5-lgtm/Projeto-criador-solo-`; ela está registrada
apenas como procedência. Não escreva novas entregas deste canal na origem.

## Produção

1. Escolha uma história inédita ou siga o tema indicado. A linha principal é
   ficção original de mistério, emoção, escolhas e reviravoltas. Histórias reais
   ou históricas são séries próprias, identificadas e pesquisadas.
2. Cada história deve ter 3 ou 4 partes, um vídeo por parte. Planeje a história
   completa, com personagem, desejo, conflito, pistas, decisão e desfecho na
   última parte. Numere títulos, miniaturas e encerramentos e preserve continuidade. A narração conta a história, sem virar uma lista de
   curiosidades ou uma explicação das regras de produção.
3. Identifique ficção na descrição. Em relatos factuais, registre fontes
   primárias, incertezas e o que é reconstituição. Não apresente diálogos,
   pensamentos ou personagens inventados como documentação histórica.
4. Use a voz **Thalita** (`pt-BR-ThalitaMultilingualNeural`). Interpretação
   íntima e expressiva, com pausas naturais. Se Emanuel enviar a gravação,
   use-a. Se a voz estiver indisponível, informe e não anuncie vídeo pronto.
5. Todas as imagens geradas, miniaturas e cenas são **16:9**. Use imagegen
   para artes raster. Planeje personagens consistentes, iluminação narrativa,
   planos variados, parallax e movimentos dos elementos; zoom sozinho não
   cumpre a proposta de pixel art animada.
6. O Lume é uma pequena lanterna voadora com asas verde água. Use aparições
   breves na abertura, passagens e encerramento. Não sobreponha personagens,
   objetos importantes ou momentos de tensão. Mantenha moldura fina dourada.
7. Produza MP4 Full HD, 1920 × 1080, 24 fps, perto de oito minutos. Por padrão,
   `subtitle_mode: none`: sem transcrição desenhada nem faixa de legenda
   embutida no MP4. SRT separado é opcional. Uma orientação nova do usuário
   pode escolher outro modo; nunca duplique legendas.
8. Voz em primeiro plano; trilha e ambientes a serviço da história. Confira
   pronúncia, cortes, clímax e resolução do conflito. Não estique a duração
   com repetição, silêncios artificiais ou quadros congelados.
9. Prepare a entrega com os utilitários de `scripts/`. Execute a conferência
   técnica e assista ao vídeo inteiro. A revisão visual é uma ação real,
   nunca uma declaração automática produzida pelo código.
10. Disponibilize MP4, miniatura, título, descrição, metadados, roteiro,
    créditos, transcrição opcional e pacote no repositório; confira os bytes
    e links remotos antes de anunciar entrega. Preserve alterações de outros
    colaboradores e não faça force push.

Emanuel publica no YouTube. Não envie vídeos ao canal, não peça OAuth e não
configure publicação automática sem instrução nova. GitHub Actions verifica
o projeto e pode recompor uma entrega em partes; não produz histórias por cron.

Modelos e pautas são preparação: não os anuncie como episódios produzidos.
Nenhum arquivo ou pacote pode conter credenciais.
