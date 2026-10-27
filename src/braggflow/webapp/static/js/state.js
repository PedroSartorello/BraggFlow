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
  evolutionCurves: {},  // chave da trilha da evolução -> trilha
  vizPendingFile: null,  // CSV recém-gerado pelo processamento, ainda não visto
};

// ── Arquivos: estado próprio para cada um ────────────────────────────────────
export const seriesState = {};    // caminho -> {sensors, processing, include, processed}
export const seriesOrder = [];    // ordem dos arquivos na lista e na concatenação
export const spectraState = {};   // caminho -> {settings, exclude}
// Mesmo preparo para todos os espectros (o padrão): o formulário edita
// `settings`, e o preparo de cada arquivo fica guardado sem uso
export const spectraCommon = { on: true, settings: null };

export const shortName = (path) => path.replace(/^data\//, "");
export const baseName = (path) => path.split("/").pop();
export const folderOf = (path) => path.split("/").slice(0, -1).join("/");

export function seriesStateFor(path) {
  if (!(path in seriesState)) seriesOrder.push(path);
  return (seriesState[path] ??= { sensors: null, processing: null, include: true, processed: null });
}

export const defaultSpectrumSettings = () => ({ ...(shared.figureOptions?.spectrum_settings || {}) });

export function spectraStateFor(path) {
  if (!path) return { settings: defaultSpectrumSettings(), exclude: false };   // nunca cria "null"
  return (spectraState[path] ??= { settings: defaultSpectrumSettings(), exclude: false });
}

export function commonSpectrumSettings() {
  return (spectraCommon.settings ??= defaultSpectrumSettings());
}

// O preparo que o formulário mostra e edita
export function editedSpectrumSettings(path) {
  return spectraCommon.on ? commonSpectrumSettings() : spectraStateFor(path).settings;
}

// O preparo usado para ler e analisar um arquivo. No preparo comum, a fonte
// e o fundo aparecem como estão: dividir a fonte por ela mesma não mostra nada.
export function spectrumSettingsFor(path) {
  if (!spectraCommon.on) return spectraState[path]?.settings || defaultSpectrumSettings();
  const s = commonSpectrumSettings();
  return path && (path === s.reference_file || path === s.dark_file)
    ? { ...s, reference_file: "", dark_file: "" } : s;
}

// Arquivos usados como fonte ou fundo (ficam fora da evolução)
export function referenceSpectra() {
  const usados = new Set();
  const marcar = (s) => {
    if (s?.reference_file) usados.add(s.reference_file);
    if (s?.dark_file) usados.add(s.dark_file);
  };
  if (spectraCommon.on) marcar(commonSpectrumSettings());
  else Object.values(spectraState).forEach((st) => marcar(st.settings));
  return usados;
}


// ── Tela inicial: abrir um projeto ou começar outro ──────────────────────────
export const projectSeriesPaths = () => seriesOrder.filter((path) => path in seriesState);
export const porNome = new Intl.Collator("pt-BR", { numeric: true }).compare;   // 01, 02… 10
export const projectSpectraPaths = () => Object.keys(spectraState).sort(porNome);
export const fileKind = (path) => shared.rawFiles.find((f) => f.path === path)?.kind;
