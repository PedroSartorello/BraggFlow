// Estado compartilhado entre as abas: arquivos do projeto e o que cada um
// guarda, mais as variáveis que mais de um módulo lê e altera (`shared`).

// Lido e alterado por mais de um módulo (um `let` importado não pode
// ser reatribuído por quem importa).
export const shared = {
  currentSetup: null,  // setup carregado de data/setups (ou null)
  currentSpectrumFile: null,
  figureOptions: null,  // estilo padrão, paletas e fontes do servidor
  lastChannels: [],
  markerClickTimer: null,
  rawFiles: [],  // arquivos brutos com o tipo detectado
  seriesCurves: {},  // chave da curva -> {file, channel}
  spectrumCurves: {},  // chave da curva -> {file, trace}
  vizPendingFile: null,  // CSV recém-gerado pelo processamento, ainda não visto
};

// ── Arquivos: estado próprio para cada um ────────────────────────────────────
export const seriesState = {};    // caminho -> {sensors, processing, include, processed}
export const seriesOrder = [];    // ordem dos arquivos na lista e na concatenação
export const spectraState = {};   // caminho -> {settings}

export const shortName = (path) => path.replace(/^data\//, "");
export const baseName = (path) => path.split("/").pop();

export function seriesStateFor(path) {
  if (!(path in seriesState)) seriesOrder.push(path);
  return (seriesState[path] ??= { sensors: null, processing: null, include: true, processed: null });
}

export function spectraStateFor(path) {
  return (spectraState[path] ??= { settings: { ...(shared.figureOptions?.spectrum_settings || {}) } });
}


// ── Tela inicial: abrir um projeto ou começar outro ──────────────────────────
export const projectSeriesPaths = () => seriesOrder.filter((path) => path in seriesState);
export const projectSpectraPaths = () => Object.keys(spectraState);
export const fileKind = (path) => shared.rawFiles.find((f) => f.path === path)?.kind;
