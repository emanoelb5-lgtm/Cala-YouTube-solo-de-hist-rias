# Fio de Lume

![Capa do Fio de Lume](docs/identidade/Capa_Fio_de_Lume_16x9.png)

**Histórias que continuam em você.**

Canal de Emanuel Bonfim para histórias narradas em português brasileiro:
mistérios, dramas humanos, encontros inesperados e reviravoltas. Cada história se divide em **3 ou 4 vídeos**, um por parte, com voz expressiva,
cenas em pixel art animada, movimento e desenho de som. A última parte fecha
o conflito; as anteriores avançam a narrativa e conduzem à próxima descoberta.

**Repositório oficial:** `emanoelb5-lgtm/Cala-YouTube-solo-de-hist-rias`.

## O canal

| Elemento | Definição |
| --- | --- |
| Nome | **Fio de Lume** |
| Frase | **Histórias que continuam em você.** |
| Linha principal | Ficção original de mistério, emoção, escolhas e reviravoltas |
| Outras séries | Relatos reais e históricos, com fontes e identificação |
| Voz | **Thalita**, a voz já aprovada; gravação de Emanuel quando enviada |
| Mascote | **Lume**, pequena lanterna voadora com asas verde água |
| Identidade | Azul de tinta, dourado antigo, pergaminho e ameixa |
| Vídeos | Um por parte; próximos de oito minutos, Full HD, horizontal **16:9**, **24 fps** |
| Legendas | Sem transcrição na tela por padrão; SRT separado e opcional |

[Descrição pronta para copiar](docs/descricao-do-canal.txt) ·
[Identidade e proposta](docs/canal.md) ·
[Como serão os vídeos](docs/como-serao-os-videos.md) ·
[Artes do canal](docs/identidade/README.md) ·
[Primeiras histórias](docs/pautas.md)

## Como pedir o próximo vídeo

> Faça o próximo vídeo do Fio de Lume, escolha uma história e entregue no
> repositório Cala-YouTube-solo-de-hist-rias com os materiais para publicar.

Também é possível indicar uma história, gênero ou narração gravada. O pedido
no chat inicia a produção completa. Emanuel faz a publicação no YouTube.

## Base copiada e adaptada

O projeto parte dos utilitários de narração, montagem, preparação e conferência
do Quase Infinito. A configuração, a identidade, os modelos e as regras foram
adaptados para narrativa. A origem está registrada em
[Procedência da cópia](docs/origem-da-copia.md).

## Preparação técnica

Python 3.12, FFmpeg/ffprobe e fonte DejaVu Sans são usados na montagem. A
narração usa edge-tts e precisa de internet. A disponibilidade da voz é
conferida durante cada produção; o roteiro é escrito no chat.

```bash
python -m pip install -r requirements-production.txt
python scripts/check_setup.py
python scripts/new_episode.py --slug h001-parte-01 --title "A carta que chegou quarenta anos atrasada"
```

Preencha roteiro, personagens, metadados e cenas no novo episódio; produza os
assets antes de montar. O modelo tem campos vazios para evitar tratar um
rascunho como uma entrega.

```bash
python scripts/generate_narration.py --text-file videos/h001-parte-01/narracao.txt --output-dir work/h001-parte-01
python scripts/assemble_video.py --episode videos/h001-parte-01 --work-dir work/h001-parte-01
python scripts/prepare_delivery.py --episode videos/h001-parte-01 --work-dir work/h001-parte-01
python scripts/package_episode.py --episode videos/h001-parte-01
```

A duração e os planos devem seguir os tempos reais da narração. O compositor
aceita imagens com movimento, clips animados e filmagens; animações de
personagens e parallax são preparados por cena e fornecidos como clips.

## Entrega por episódio

MP4 separado, miniatura PNG/JPG, título e descrição em TXT, metadados, roteiro,
narração, fontes/créditos, SRT quando disponível, relatório técnico e ZIP de
publicação. O pacote é criado somente depois de validar arquivos reais.
A conferência técnica não substitui assistir ao vídeo inteiro.

[Episódios](videos/README.md) · [Modelo de episódio](templates/episodio/README.md)

## Primeira história — quatro partes

**A carta que chegou quarenta anos atrasada.**

[**Baixar a parte 1 — MP4**](https://chatgpt.com/api/library/files/libfile_6a2d0605a9d48191bacdeb3f0018e67b/download) ·
[Miniatura](videos/h001-parte-01/miniatura.jpg) ·
[Materiais para publicar](https://chatgpt.com/api/library/files/libfile_4f42babf6ef8819180270b6790e31691/download) ·
[História e continuidade](historias/h001-a-carta/README.md)

As próximas três partes têm continuidade planejada; seus vídeos serão produzidos
nos próximos pedidos. [Diretrizes atualizadas](docs/diretrizes-do-canal.md).
