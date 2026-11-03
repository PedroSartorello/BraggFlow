"""
Mensagens do BraggFlow em português (o padrão) e inglês.

Quem levanta um erro ou escreve um aviso usa ``tr(chave, **valores)``. O idioma
vale para o contexto atual: o web app o escolhe a cada pedido pelo cabeçalho
``Accept-Language``, que a página envia com o idioma da interface; fora de um
pedido (o comando ``braggflow``, scripts) vale o português.

Os rótulos das figuras não passam por aqui: seguem o idioma da figura
(``style.axes.language``), porque a figura vai para o artigo.
"""

from contextlib import contextmanager
from contextvars import ContextVar

LANGUAGES = ("pt", "en")
DEFAULT_LANGUAGE = "pt"

_language: ContextVar[str] = ContextVar("braggflow_language", default=DEFAULT_LANGUAGE)


def normalize_language(value) -> str:
    """``'pt-BR'``, ``'en-US'``… → ``'pt'`` ou ``'en'``; qualquer outro → português."""
    primeira = str(value or "").split("-")[0].strip().lower()
    return primeira if primeira in LANGUAGES else DEFAULT_LANGUAGE


def language() -> str:
    """Idioma das mensagens no contexto atual."""
    return _language.get()


def set_language(value):
    """Troca o idioma do contexto atual; devolve o token de ``reset_language``."""
    return _language.set(normalize_language(value))


def reset_language(token) -> None:
    _language.reset(token)


@contextmanager
def use_language(value):
    """``with use_language("en"): ...`` — o idioma só dentro do bloco."""
    token = set_language(value)
    try:
        yield
    finally:
        reset_language(token)


def tr(key: str, **values) -> str:
    """A mensagem ``key`` no idioma atual, com ``{nome}`` preenchido por ``values``."""
    entrada = MESSAGES[key]
    return entrada.get(language(), entrada["pt"]).format(**values)


def num(value: float, fmt: str = ".4g") -> str:
    """Número para as mensagens, com o separador decimal do idioma (2,5 ou 2.5)."""
    texto = format(value, fmt)
    return texto.replace(".", ",") if language() == "pt" else texto


def count(n: int) -> str:
    """Contagem com o separador de milhar do idioma (12.996 ou 12,996)."""
    texto = f"{int(n):,}"
    return texto.replace(",", ".") if language() == "pt" else texto


def field(label: str) -> str:
    """Nome de um campo das opções (os specs o escrevem em português)."""
    return FIELD_LABELS_EN.get(label, label) if language() == "en" else label


MESSAGES = {
    # ── Leitura de arquivos ──────────────────────────────────────────────────
    "reader.nothingToJoin": {"pt": "Nenhum arquivo com amostras para juntar.",
                             "en": "No file with samples to join."},
    "reader.channelsDiffer": {"pt": "Só dá para juntar arquivos com os mesmos canais; diferem em: {channels}.",
                              "en": "Only files with the same channels can be joined; they differ in: {channels}."},
    "reader.columnOrder": {"pt": "ordem das colunas", "en": "column order"},
    "reader.emptyFile": {"pt": "Arquivo vazio.", "en": "Empty file."},
    "reader.noDataLines": {"pt": "Arquivo sem linhas de dados.", "en": "The file has no data lines."},
    "reader.noSeparator": {"pt": "Não foi possível identificar o separador de colunas.",
                           "en": "Could not identify the column separator."},
    "reader.noNumericLines": {"pt": "Não foi encontrada nenhuma linha de dados numéricos.",
                              "en": "No line of numeric data was found."},
    "reader.noData": {"pt": "Arquivo sem dados.", "en": "The file has no data."},
    "reader.badTimeColumn": {"pt": "A coluna de tempo não é numérica nem uma data reconhecível.",
                             "en": "The time column is neither numeric nor a recognisable date."},
    "reader.isSpectrum": {"pt": "{name} é um espectro (intensidade por comprimento de onda), não uma série de "
                                "picos no tempo. Use a aba Visualização, em 'Espectros', para abri-lo.",
                          "en": "{name} is a spectrum (intensity by wavelength), not a series of peaks over "
                                "time. Open it in the Spectra tab."},
    "reader.noTimeColumn": {"pt": "Nenhuma coluna de tempo encontrada (Time, Tempo, Timestamp ou Date).",
                            "en": "No time column found (Time, Tempo, Timestamp or Date)."},
    "reader.noChannelColumn": {"pt": "Nenhuma coluna de canal encontrada no arquivo.",
                               "en": "No channel column found in the file."},
    "reader.noSpectrumColumns": {"pt": "O arquivo não tem duas colunas numéricas (comprimento de onda e intensidade).",
                                 "en": "The file does not have two numeric columns (wavelength and intensity)."},
    "reader.noSpectrumTrace": {"pt": "Nenhum traço espectral válido encontrado no arquivo.",
                               "en": "No valid spectral trace found in the file."},
    "data.invalidPath": {"pt": "Arquivo inválido ou fora de data/: {path}",
                         "en": "Invalid file or outside data/: {path}"},

    # ── Opções vindas da interface ───────────────────────────────────────────
    "options.invalidNumber": {"pt": "{label}: número inválido ({value}).", "en": "{label}: invalid number ({value})."},
    "options.notInteger": {"pt": "{label}: use um número inteiro ({value}).", "en": "{label}: use a whole number ({value})."},
    "options.atLeast": {"pt": "≥ {low}", "en": "≥ {low}"},
    "options.between": {"pt": "entre {low} e {high}", "en": "between {low} and {high}"},
    "options.outOfRange": {"pt": "{label}: valor deve ser {limits} (recebido {value}).",
                           "en": "{label}: the value must be {limits} (got {value})."},
    "options.invalidChoice": {"pt": "{label}: opção inválida ({value}).", "en": "{label}: invalid option ({value})."},
    "options.invalidColor": {"pt": "{label}: cor inválida ({value}).", "en": "{label}: invalid color ({value})."},
    "options.invalid": {"pt": "Opções inválidas.", "en": "Invalid options."},
    "options.invalidIn": {"pt": "Opções inválidas em {prefix}.", "en": "Invalid options in {prefix}."},

    # ── Receita de processamento (recipe.py) ─────────────────────────────────
    "recipe.noFile": {"pt": "Nenhum arquivo selecionado.", "en": "No file selected."},
    "recipe.bandIncomplete": {"pt": "Banda incompleta no sensor '{name}': informe mínimo e máximo, ou deixe os dois vazios.",
                              "en": "Incomplete band on sensor '{name}': give the minimum and the maximum, or leave both empty."},
    "recipe.cleaning": {"pt": "Limpeza: {parts}", "en": "Cleaning: {parts}"},
    "recipe.cleaningNone": {"pt": "nenhuma leitura inválida", "en": "no invalid readings"},
    "recipe.joined": {"pt": "{n} arquivos juntos ({names}); emendas em {joins}",
                      "en": "{n} files joined ({names}); seams at {joins}"},
    "recipe.allHidden": {"pt": "Todas as colunas estão ocultas: mostre pelo menos uma no cartão Sensores.",
                         "en": "Every column is hidden: show at least one in the Sensors card."},
    "recipe.hiddenColumns": {"pt": "Colunas ocultas, fora do processamento: {names}",
                             "en": "Hidden columns, left out of the processing: {names}"},
    "recipe.timebaseMerged": {"pt": "Eixo de tempo: {n} amostra(s) com tempo repetido ou inválido unidas/descartadas",
                              "en": "Time axis: {n} sample(s) with a repeated or invalid time merged or discarded"},
    "recipe.resampled": {"pt": "Reamostrado a {fs} Hz ({n} amostras)", "en": "Resampled at {fs} Hz ({n} samples)"},
    "recipe.stepMovingAverage": {"pt": "média móvel", "en": "moving average"},
    "recipe.stepLowpass": {"pt": "passa-baixa", "en": "low-pass"},
    "recipe.stepHighpass": {"pt": "passa-alta", "en": "high-pass"},
    "recipe.gaps": {"pt": "{n} lacuna(s) no eixo de tempo; {steps} supõe(m) amostragem uniforme. Ative a reamostragem "
                          "no cartão 'Eixo de tempo' ou use estratégias que preservam as linhas.",
                    "en": "{n} gap(s) in the time axis; {steps} assume(s) uniform sampling. Turn on resampling "
                          "in the 'Time axis' card or use strategies that keep the rows."},
    "recipe.nanReachFilters": {"pt": "{n} leitura(s) inválida(s) chegam aos filtros e serão propagadas; ative 'Remoção de nulos'.",
                               "en": "{n} invalid reading(s) reach the filters and will spread; turn on 'Null removal'."},
    "recipe.savgolOdd": {"pt": "Savitzky-Golay: a janela precisa ser um número ímpar a partir de 3 (recebido {window}).",
                         "en": "Savitzky-Golay: the window must be an odd number, 3 or more (got {window})."},
    "recipe.savgolOrder": {"pt": "Savitzky-Golay: a janela ({window}) precisa ser maior que a ordem ({order}).",
                           "en": "Savitzky-Golay: the window ({window}) must be larger than the order ({order})."},
    "recipe.tempcompNeedsDelta": {"pt": "A compensação de temperatura subtrai deslocamentos (Δλs − k·Δλr): ative a etapa Δλ.",
                                  "en": "Temperature compensation subtracts shifts (Δλs − k·Δλr): turn on the Δλ step."},
    "recipe.referenceHidden": {"pt": "O canal de referência '{ref}' está oculto: mostre-o no cartão Sensores ou escolha outra referência.",
                               "en": "The reference channel '{ref}' is hidden: show it in the Sensors card or choose another reference."},
    "recipe.referenceMissing": {"pt": "Canal de referência '{ref}' não existe: {channels}.",
                                "en": "Reference channel '{ref}' does not exist: {channels}."},
    "recipe.referenceNeedsKt": {"pt": "Informe a sensibilidade térmica K_T da referência ({ref}) no cartão Sensores: "
                                      "os outros sensores têm K_T e k = K_T,s / K_T,r.",
                                "en": "Give the thermal sensitivity K_T of the reference ({ref}) in the Sensors card: "
                                      "the other sensors have K_T and k = K_T,s / K_T,r."},
    "recipe.kGiven": {"pt": "k informado", "en": "k given"},
    "recipe.tempcompReport": {"pt": "Compensação de temperatura pela referência {ref}: {parts}",
                              "en": "Temperature compensation by the reference {ref}: {parts}"},
    "recipe.rawShifted": {"pt": "Sinal bruto deslocado pela mediana para a escala do processado "
                                "(passa-alta ou compensação de temperatura tiram o nível DC)",
                          "en": "Raw signal shifted by the median to the processed scale "
                                "(high-pass or temperature compensation remove the DC level)"},
    "recipe.fsEstimated": {"pt": "fs estimado a partir do vetor de tempo: {fs} Hz",
                           "en": "fs estimated from the time vector: {fs} Hz"},

    # ── Estatísticas (analysis.py) ───────────────────────────────────────────
    "analysis.wholeSignal": {"pt": "todo o sinal", "en": "whole signal"},
    "analysis.beforeFirst": {"pt": "antes da 1ª marcação", "en": "before the 1st marker"},
    "analysis.marker": {"pt": "marcação {n}", "en": "marker {n}"},
    "analysis.endBeforeStart": {"pt": "O fim do trecho precisa ser maior que o início.",
                                "en": "The end of the stretch must be after its start."},
    "analysis.badReference": {"pt": "Referência inválida: {reference}. Use {options}.",
                              "en": "Invalid reference: {reference}. Use {options}."},
    "analysis.stepWindow": {"pt": "A janela do degrau deve ser maior que zero.",
                            "en": "The step window must be above zero."},
    "analysis.noValidTime": {"pt": "A curva não tem amostras com tempo válido.",
                             "en": "The curve has no samples with a valid time."},

    # ── Espectros e evolução (processing/spectra.py) ─────────────────────────
    "spectra.eventPrefix": {"pt": "[evento {n}] ", "en": "[event {n}] "},
    "spectra.invalidEvent": {"pt": "{prefix}Evento inválido.", "en": "{prefix}Invalid event."},
    "spectra.invalidTime": {"pt": "{prefix}Instante inválido: {value}.", "en": "{prefix}Invalid time: {value}."},
    "spectra.unknownSmoothing": {"pt": "Suavização desconhecida: {method}.", "en": "Unknown smoothing: {method}."},
    "spectra.unknownNormalization": {"pt": "Normalização desconhecida: {mode}.", "en": "Unknown normalization: {mode}."},
    "spectra.unknownOutput": {"pt": "Saída de transmissão desconhecida: {output}.", "en": "Unknown transmission output: {output}."},
    "spectra.lambdaOrder": {"pt": "λ mínimo do espectro deve ser menor que λ máximo.",
                            "en": "The spectrum's λ minimum must be below its λ maximum."},
    "spectra.cropTooNarrow": {"pt": "O recorte de comprimento de onda não deixou pontos suficientes.",
                              "en": "The wavelength crop left too few points."},
    "spectra.noValidPoints": {"pt": "O espectro não tem pontos válidos depois da conversão.",
                              "en": "The spectrum has no valid points after the conversion."},
    "spectra.unknownKind": {"pt": "Tipo de extremo desconhecido: {kind}.", "en": "Unknown extremum type: {kind}."},
    "spectra.unknownMode": {"pt": "Modo desconhecido: {mode}.", "en": "Unknown mode: {mode}."},
    "spectra.unknownLocate": {"pt": "Posição do extremo desconhecida: {locate}.", "en": "Unknown extremum position: {locate}."},
    "spectra.markReference": {"pt": "Marque o λ de referência: clique no vale no gráfico do espectro ou digite o valor.",
                              "en": "Mark λ ref: click the valley on the spectrum plot, or type the value."},
    "spectra.windowPositive": {"pt": "A janela de busca deve ser maior que zero (vazio = sem limite).",
                               "en": "The search window must be above zero (empty = no limit)."},
    "spectra.nothingToTrack": {"pt": "Nenhum espectro para acompanhar.", "en": "No spectra to track."},
    "spectra.firstHasNone": {"pt": "O primeiro arquivo não tem {kind}s para acompanhar: ajuste o recorte ou a proeminência.",
                             "en": "The first file has no {kind}s to track: adjust the crop or the prominence."},
    "spectra.valley": {"pt": "vale", "en": "valley"},
    "spectra.peak": {"pt": "pico", "en": "peak"},
    "spectra.trackNear": {"pt": "{kind} perto de {ref} nm", "en": "{kind} near {ref} nm"},
    "spectra.trackProminent": {"pt": "{kind} mais proeminente", "en": "most prominent {kind}"},
    "spectra.trackFollow": {"pt": "{kind} {i} (≈ {lam} nm no 1º)", "en": "{kind} {i} (≈ {lam} nm in the 1st)"},

    # ── Figura (visualization/figure.py) ─────────────────────────────────────
    "figure.fontMissing": {"pt": "Fonte não instalada: {family}.", "en": "Font not installed: {family}."},
    "figure.channelStyle": {"pt": "Estilo dos canais inválido.", "en": "Invalid channel style."},
    "figure.markerTime": {"pt": "Tempo inválido na marcação '{label}': {value}", "en": "Invalid time on marker '{label}': {value}"},
    "figure.markerColor": {"pt": "Cor inválida na marcação '{label}': {value}", "en": "Invalid color on marker '{label}': {value}"},
    "figure.noReferenceReading": {"pt": "Canal {channel}: nenhuma leitura válida na janela de referência.",
                                  "en": "Channel {channel}: no valid reading in the reference window."},
    "figure.unknownQuantity": {"pt": "Grandeza desconhecida: {quantity}.", "en": "Unknown quantity: {quantity}."},
    "figure.noCurve": {"pt": "Nenhuma curva selecionada.", "en": "No curve selected."},
    "figure.noX": {"pt": "Eixo X sem valores válidos.", "en": "The X axis has no valid values."},
    "figure.xOrder": {"pt": "X mínimo deve ser menor que X máximo.", "en": "X minimum must be below X maximum."},
    "figure.yOrder": {"pt": "Y mínimo deve ser menor que Y máximo.", "en": "Y minimum must be below Y maximum."},
    "figure.noChannel": {"pt": "Nenhum canal selecionado.", "en": "No channel selected."},
    "figure.missingChannels": {"pt": "Canais ausentes no CSV: {channels}.", "en": "Channels missing from the CSV: {channels}."},
    "figure.badFormat": {"pt": "Formato não suportado: {format}.", "en": "Unsupported format: {format}."},

    # ── Projetos (projects.py) ───────────────────────────────────────────────
    "project.invalidProcessing": {"pt": "Opções de processamento inválidas.", "en": "Invalid processing options."},
    "project.invalidStep": {"pt": "Opções inválidas na etapa '{section}'.", "en": "Invalid options in the '{section}' step."},
    "project.nameRequired": {"pt": "Informe um nome para o projeto.", "en": "Name the project."},
    "project.badSource": {"pt": "Fonte da figura inválida: {source}.", "en": "Invalid figure source: {source}."},
    "project.invalid": {"pt": "Projeto inválido.", "en": "Invalid project."},

    # ── Web app (webapp/app.py) ──────────────────────────────────────────────
    "app.traceNotFound": {"pt": "Traço '{trace}' não encontrado em {file}.", "en": "Trace '{trace}' not found in {file}."},
    "app.trace": {"pt": "Traço", "en": "Trace"},
    "app.traceNumber": {"pt": "Traço {n}", "en": "Trace {n}"},
    "app.channelMissing": {"pt": "Canal '{channel}' não existe em {file}.", "en": "Channel '{channel}' does not exist in {file}."},
    "app.noName": {"pt": "(sem nome)", "en": "(no name)"},
    "app.evolutionNeedsTwo": {"pt": "Escolha dois ou mais espectros para ver a evolução.",
                              "en": "Choose two or more spectra to see the evolution."},
    "app.couldNotRead": {"pt": " Não deu para ler: {files}", "en": " Could not read: {files}"},
    "app.skippedFiles": {"pt": "{n} arquivo(s) ignorado(s) por erro de leitura: {names}{more}.",
                         "en": "{n} file(s) skipped because of a read error: {names}{more}."},
    "app.andMore": {"pt": " e mais {n}", "en": " and {n} more"},
    "app.byFileOrder": {"pt": "Nem todos os arquivos têm o instante da aquisição (cabeçalho Date: ou hora no nome); "
                              "a evolução está na ordem dos arquivos.",
                        "en": "Not every file has the acquisition time (Date: header or time in the name); "
                              "the evolution is in file order."},
    "app.mixedTimes": {"pt": "Alguns instantes vêm do cabeçalho e outros só do nome do arquivo (sem data): "
                             "o tempo decorrido supõe que todos são do mesmo dia.",
                       "en": "Some times come from the header and others only from the file name (no date): "
                             "the elapsed time assumes they are all from the same day."},
    "app.mixedUnits": {"pt": "Os espectros estão em unidades diferentes ({units}): confira o preparo de cada arquivo.",
                       "en": "The spectra are in different units ({units}): check the preparation of each file."},
    "app.inWindow": {"pt": " na janela", "en": " in the window"},
    "app.noneFound": {"pt": "Nenhum {kind}{where} em {n} espectro(s): o ponto fica vazio.",
                      "en": "No {kind}{where} in {n} of the spectra: the point stays empty."},
    "app.methodFit": {"pt": "o ajuste no fundo", "en": "the fit at the bottom"},
    "app.methodCentroid": {"pt": "o centroide", "en": "the centroid"},
    "app.locateFallback": {"pt": "Sem {method} em {n} ponto(s): ficou o vértice de 3 pontos.",
                           "en": "No {method} at {n} point(s): the 3-point vertex was used."},
    "app.checkTrack": {"pt": "Marque pelo menos uma trilha da evolução.", "en": "Check at least one evolution track."},
    "app.selectSpectrum": {"pt": "Selecione pelo menos um espectro.", "en": "Select at least one spectrum."},
    "app.selectCurve": {"pt": "Selecione pelo menos uma curva.", "en": "Select at least one curve."},
    "app.styleNameRequired": {"pt": "Informe um nome para o estilo.", "en": "Name the style."},
    "app.setupNotFound": {"pt": "Setup não encontrado: {name}", "en": "Setup not found: {name}"},
    "app.setupInvalid": {"pt": "Setup inválido: {error}", "en": "Invalid setup: {error}"},
    "app.setupNameRequired": {"pt": "Informe um nome para o setup.", "en": "Name the setup."},
    "app.noSensors": {"pt": "Nenhum sensor para salvar.", "en": "No sensors to save."},
    "app.joinNeedsTwo": {"pt": "Escolha dois ou mais arquivos para juntar.", "en": "Choose two or more files to join."},
    "app.mixedRates": {"pt": "Os arquivos têm taxas de amostragem diferentes ({rates}); os filtros supõem amostragem "
                             "uniforme. Reamostre na etapa 'Eixo de tempo'.",
                       "en": "The files have different sampling rates ({rates}); the filters assume uniform "
                             "sampling. Resample in the 'Time axis' step."},
    "app.noFigureData": {"pt": "Requisição sem dados selecionados.", "en": "The request has no data selected."},
    "app.analysisSeriesOnly": {"pt": "A análise estatística é das séries no tempo, não dos espectros.",
                               "en": "The statistical analysis is for time series, not for spectra."},
    "app.checkCurve": {"pt": "Marque pelo menos uma curva.", "en": "Check at least one curve."},
    "app.styleNotFound": {"pt": "Estilo não encontrado ou inválido: {name}", "en": "Style not found or invalid: {name}"},
    "app.projectNotFound": {"pt": "Projeto não encontrado ou inválido: {name}", "en": "Project not found or invalid: {name}"},
    "app.projectInvalid": {"pt": "Projeto inválido: {error}", "en": "Invalid project: {error}"},
    "app.projectMissing": {"pt": "Projeto não encontrado: {name}", "en": "Project not found: {name}"},
    "app.descriptorOnly": {"pt": "{name} descreve o ensaio, mas não contém os dados. Envie {target}, "
                                 "que é o arquivo indicado dentro dele.",
                           "en": "{name} describes the test but does not contain the data. Upload {target}, "
                                 "the file named inside it."},
    "app.descriptorTarget": {"pt": "o arquivo .ASC ou .txt do ensaio", "en": "the test's .ASC or .txt file"},
    "app.badExtension": {"pt": "{name}: extensão não suportada ({suffix}). Aceito: {accepted}.",
                         "en": "{name}: unsupported extension ({suffix}). Accepted: {accepted}."},
    "app.noExtension": {"pt": "sem extensão", "en": "no extension"},
    "app.noUpload": {"pt": "Nenhum arquivo enviado.", "en": "No file was uploaded."},
    "app.noFileInRequest": {"pt": "Requisição sem arquivo selecionado.", "en": "The request has no file selected."},
    "app.csvNotSaved": {"pt": "CSV processado não foi salvo: {error}", "en": "The processed CSV was not saved: {error}"},
    "app.emptyStretch": {"pt": "Escolha um trecho com início e fim diferentes.",
                         "en": "Choose a stretch with different start and end."},
    "app.processFirst": {"pt": "Processe um arquivo antes de calcular as estatísticas.",
                         "en": "Process a file before calculating the statistics."},
}


# Nomes dos campos das opções (specs de processing/spectra.py e
# visualization/figure.py), para os erros em inglês
FIELD_LABELS_EN = {
    "Espectro da fonte": "Source spectrum",
    "Ruído de fundo": "Background noise",
    "Saída da transmissão": "Transmission output",
    "λ mínimo do espectro": "Spectrum λ minimum",
    "λ máximo do espectro": "Spectrum λ maximum",
    "Tipo de suavização": "Smoothing type",
    "Suavização (pontos)": "Smoothing (points)",
    "Ordem da suavização": "Smoothing order",
    "Remover tendência (grau do polinômio)": "Remove trend (polynomial degree)",
    "Normalização": "Normalization",
    "Deslocamento vertical": "Vertical offset",
    "Detectar máximos": "Detect maxima",
    "Detectar mínimos": "Detect minima",
    "Escala da intensidade": "Intensity scale",
    "Proeminência mínima": "Minimum prominence",
    "Distância mínima entre extremos": "Minimum distance between extrema",
    "Máximo de extremos por tipo": "Maximum extrema per type",
    "Acompanhar": "Track",
    "Modo": "Mode",
    "λ de referência": "λ ref",
    "Janela de busca": "Search window",
    "Seguir a deriva": "Follow the drift",
    "Salto máximo": "Maximum jump",
    "Posição do extremo": "Extremum position",
    "Eixo y": "Y axis",
    "Eixo x": "X axis",
    "Instante do evento": "Event time",
    "Legenda do evento": "Event label",
    "Cor do evento": "Event color",
    "Legenda do canal": "Channel legend",
    "Cor do canal": "Channel color",
    "Estilo da linha do canal": "Channel line style",
    "Marcador do canal": "Channel marker",
    "Espessura da linha do canal": "Channel line thickness",
    "Layout": "Layout",
    "Unidade do tamanho": "Size unit",
    "Largura da figura": "Figure width",
    "Altura da figura": "Figure height",
    "Fonte": "Font",
    "Tamanho base da fonte": "Base font size",
    "Título": "Title",
    "Tamanho do título": "Title size",
    "Título em negrito": "Bold title",
    "Cor de fundo": "Background color",
    "Espaço entre painéis": "Space between panels",
    "Mesma escala Y nos painéis": "Same Y scale in the panels",
    "Rótulo Y único": "Single Y label",
    "Letras dos painéis": "Panel letters",
    "Formato das letras": "Letter format",
    "Unidade do tempo": "Time unit",
    "t = 0 na primeira marcação": "t = 0 at the first marker",
    "Converter nm → pm": "Convert nm → pm",
    "Δ relativo ao início": "Δ relative to the start",
    "Janela da referência": "Reference window",
    "Unidade da intensidade": "Intensity unit",
    "X mínimo": "X minimum",
    "X máximo": "X maximum",
    "Y mínimo": "Y minimum",
    "Y máximo": "Y maximum",
    "Rótulo X": "X label",
    "Rótulo Y": "Y label",
    "Idioma dos rótulos automáticos": "Language of automatic labels",
    "Tamanho dos rótulos": "Label size",
    "Espessura dos eixos": "Axes thickness",
    "Borda superior": "Top border",
    "Borda direita": "Right border",
    "Grade principal": "Major grid",
    "Grade secundária": "Minor grid",
    "Estilo da grade": "Grid style",
    "Cor da grade": "Grid color",
    "Opacidade da grade": "Grid opacity",
    "Espessura da grade": "Grid thickness",
    "Direção dos ticks": "Tick direction",
    "Comprimento dos ticks": "Tick length",
    "Espessura dos ticks": "Tick thickness",
    "Tamanho do texto dos ticks": "Tick text size",
    "Ticks secundários": "Minor ticks",
    "Ticks no topo e à direita": "Ticks on top and right",
    "Separador decimal": "Decimal separator",
    "Notação de offset": "Offset notation",
    "Passo dos ticks X": "X tick step",
    "Nº de divisões X": "Number of X divisions",
    "Casas decimais X": "X decimal places",
    "Rotação dos ticks X": "X tick rotation",
    "Passo dos ticks Y": "Y tick step",
    "Nº de divisões Y": "Number of Y divisions",
    "Casas decimais Y": "Y decimal places",
    "Espessura das curvas": "Curve thickness",
    "Marcadores nas curvas": "Markers on the curves",
    "Tamanho dos marcadores": "Marker size",
    "Marcadores por curva": "Markers per curve",
    "Mostrar legenda": "Show legend",
    "Posição da legenda": "Legend position",
    "Colunas da legenda": "Legend columns",
    "Tamanho da legenda": "Legend size",
    "Moldura da legenda": "Legend frame",
    "Título da legenda": "Legend title",
    "Estilo das marcações": "Marker style",
    "Espessura das marcações": "Marker thickness",
    "Tamanho dos rótulos das marcações": "Marker label size",
    "Rotação dos rótulos": "Label rotation",
    "Posição dos rótulos": "Label position",
    "Marcações em preto": "Black markers",
    "Faixas alternadas": "Alternating bands",
    "Cor da faixa 1": "Band color 1",
    "Cor da faixa 2": "Band color 2",
    "Opacidade das faixas": "Band opacity",
    "Formato": "Format",
    "Resolução (dpi)": "Resolution (dpi)",
    "Resolução da pré-visualização": "Preview resolution",
    "Fundo transparente": "Transparent background",
    "Recortar margens": "Crop margins",
}
