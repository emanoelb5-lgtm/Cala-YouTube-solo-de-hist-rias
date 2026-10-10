# Fio de Lume

![Capa do Fio de Lume](docs/identidade/Capa_Fio_de_Lume_16x9.png)

**Histórias que continuam em você.**

Canal de Emanuel Bonfim para histórias narradas em português brasileiro:
mistérios, dramas humanos, encontros inesperados e reviravoltas. Cada episódio
conta uma história completa, com voz expressiva, cenas em pixel art, movimento
e desenho de som.

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
| Vídeos | Próximos de oito minutos, Full HD, horizontal **16:9**, **24 fps** |
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
python scripts/new_episode.py --slug ep-001-a-carta --title "A carta que chegou quarenta anos atrasada"
```

Preencha roteiro, personagens, metadados e cenas no novo episódio; produza os
assets antes de montar. O modelo tem campos vazios para evitar tratar um
rascunho como uma entrega.

```bash
python scripts/generate_narration.py --text-file videos/ep-001-a-carta/narracao.txt --output-dir work/ep-001-a-carta
python scripts/assemble_video.py --episode videos/ep-001-a-carta --work-dir work/ep-001-a-carta
python scripts/prepare_delivery.py --episode videos/ep-001-a-carta --work-dir work/ep-001-a-carta
python scripts/package_episode.py --episode videos/ep-001-a-carta
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

O repositório está preparado para o primeiro episódio. A miniatura de referência
mostra o estilo proposto; ela não anuncia um vídeo já produzido.
