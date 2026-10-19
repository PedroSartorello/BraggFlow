# Data formats

BraggFlow reads interrogator exports and optical spectra, can mark gas events
from a small table, and writes processed CSVs with a JSON provenance file. The
web app also saves sensor setups, projects and figure styles as JSON. The
examples below are taken from the synthetic files in
[`examples/data/`](../examples/data/) (`python examples/make_synthetic_data.py`).

## 1. Interrogator export (time series)

The Bragg peak wavelength of each channel over time. Read by
`braggflow.io.reader.load_interrogator_file` (and by `OpticalPipeline.load_data`).

**Format detection is automatic**, whatever the extension (`.asc`, `.txt`,
`.csv`, `.dat`, `.tsv`, `.prn`, …):

| Aspect | Accepted |
|---|---|
| Encoding | UTF-8, UTF-8 with BOM, UTF-16 LE/BE, Latin-1 |
| Separator | tab, `;`, `,` or whitespace |
| Decimal mark | `.` or `,` |
| Preamble | instrument lines before the table are skipped |
| Header | optional |

| Column | Rule | Unit |
|---|---|---|
| Time | first column named `Time…`, `Tempo…`, `Timestamp…` or `Date…`; seconds or absolute timestamps (converted to seconds since the first sample) | s |
| Channels | columns whose name starts with `CH`; otherwise every other numeric column. The unit in brackets (`[nm]`) is kept | nm |

Values are kept as exported. A lost peak is usually written as `0`;
`mark_invalid_peaks` turns it (and out-of-band readings or peak jumps) into
NaN. Text-only descriptor files of the acquisition software (`.TSX`, `.TSM`)
are not data and are refused with an explanation.

Minimal example (tab-separated, decimal comma):

```
Time [s]	CH_1 Sensor_1 [nm]	CH_2 Sensor_1 [nm]	CH_3 Sensor_1 [nm]
0,000	1549,998810	1545,000589	1540,001505
0,100	1550,000367	1544,998512	1539,999075
```

## 2. Optical spectrum

Intensity against wavelength: an optical spectrum analyser (OSA) export or a
UV-VIS-NIR spectrometer (OceanView/SpectraSuite, e.g. lossy-mode-resonance
transmission). Read by `braggflow.io.reader.load_spectra`; `classify_file`
tells a spectrum (monotonic wavelength grid between 150 and 2500 nm spanning at
least 1 nm) from a time series. Two layouts are recognised:

| Layout | Columns |
|---|---|
| Wide | one wavelength column, then one column per trace |
| Long (OSA) | traces stacked one after the other, with a label column (`CH 1`, `Subset 2`, …), an index, the wavelength and the intensity; empty traces are dropped |

Descending sweeps are reordered. The intensity unit is whatever the file
holds (counts, %, linear or dBm); the peak/dip analysis has a "dB" mode for
dBm. A file whose name contains `Transmission` is taken as %.

**Spectrometer exports (OceanView/SpectraSuite)** are read with or without
their header. With it, the lines before `>>>>>Begin Spectral Data<<<<<` are
kept as metadata (`SpectrumSet.metadata`: spectrometer, integration time,
scans to average…):

```
Data from amostra_Transmission__01__09-30-15-250.txt Node

Date: Mon Mar 02 09:30:15 BRT 2026
Spectrometer: XXX0000
Integration Time (sec): 1,000000E-1
...
>>>>>Begin Spectral Data<<<<<
200,000	12,50000
200,800	12,51000
```

**Acquisition time** (`SpectrumSet.acquired`, used to order spectra in the
evolution analysis): the `Date:` line of the header (date and time to the
second; the time zone is ignored) and/or the time at the end of the file name,
`..._HH-MM-SS-mmm` (milliseconds, but no date). When both exist and agree to
the second, the milliseconds of the name complete the header. A file without
header and without a time in its name has no acquisition time; a file with
only the time in its name takes the date of the other files of the same day.

Minimal example (wide, `;`-separated, decimal comma):

```
Wavelength [nm];Reflection [dBm]
1535,00;-60,000
1535,01;-60,000
```

## 3. Gas event table

The instants at which the gas (or flow, or any condition) changes during a
test, read by `braggflow.visualization.publication.load_gas_table`, which accepts
three variants and always returns a `SEGUNDOS` column with the **absolute start
time** of each event, sorted.

| Variant | Columns | How the start time is obtained |
|---|---|---|
| Old | `GAS, SEGUNDOS` | `SEGUNDOS` itself |
| Indexed | `GAS, SM_INDEX, SEGUNDOS, OBSERVACOES` | `Time[SM_INDEX]` of the processed signal when `SM_INDEX` is filled, else `SEGUNDOS` (a row may have either or both) |
| Interval | `GAS, INTERVALO_LITERAL, SEGUNDOS_DURACAO, OBSERVACAO` | left side of `INTERVALO_LITERAL` (`"376-750"` → 376 s) |

| Optional column | Meaning |
|---|---|
| `VAZAO_L_MIN` | flow of the plateau (L/min) |
| `TEMP_FLUKE_C` | temperature read on the reference thermometer at the event (°C) |

`GAS` is trimmed and upper-cased. `SM_INDEX` refers to rows of the processed
signal, so it needs the processed CSV to be resolved.

Minimal example:

```
GAS,SM_INDEX,SEGUNDOS,OBSERVACOES,VAZAO_L_MIN,TEMP_FLUKE_C
AR,0,0.0,inicio,0.0,25.00
N2,1200,120.0,troca para N2,0.5,25.67
CO2,3000,300.0,troca para CO2,0.5,26.38
```

## 4. Processed CSV and its JSON provenance

Written by `OpticalPipeline.save_processed_data("x.csv")` (and by
`braggflow process` and the web app). Read back by
`braggflow.io.processed.read_processed_csv`, which returns the table with bare
column names, the unit of each channel and the JSON content.

**`x.csv`** — comma-separated, decimal point, full precision (scientific notation), one row per sample:

| Column | Content |
|---|---|
| `Time [s]` | time in seconds |
| `<sensor> [<unit>]` | one column per sensor, named after the sensor setup (unit as exported, normally `nm`; after `to_delta_lambda` the values are shifts, still in `nm`, and the JSON marks them as `wavelength_shift`) |

**`x.json`** — how the CSV was produced:

| Key | Content |
|---|---|
| `software` | `name` and `version` of BraggFlow |
| `created` | creation time (ISO 8601) |
| `source` | source file name, `size_bytes`, `modified`, `sha256`; a list when several files were joined |
| `joins` | join instants (s) when several files were concatenated |
| `time_origin` | absolute time of the first sample, when the export carries timestamps |
| `setup` | the sensor setup applied (see §5) |
| `sampling` | `n_samples`, `interval_median_s`, `interval_max_s`, `fs_estimated_hz`, `uniform` |
| `channels` | for each channel: `name`, `source_channel`, `unit`, `quantity` (`wavelength` or `wavelength_shift`) |
| `steps` | every step in order: `step` (function), `kind` (`setup`, `preprocess`, `filter`, …), `params`, and for steps that can change the samples `samples_before`/`samples_after` and the invalid (NaN) counts per channel `nan_before`/`nan_after` |

Minimal example:

```
Time [s],EFBG1 [nm],EFBG2 [nm],FBG [nm]
0.000000000000000000e+00,1.549999997965475359e+03,1.545000051322118452e+03,1.539999409350381939e+03
```

```json
{
  "software": {"name": "BraggFlow", "version": "0.1.0"},
  "source": {"file": "synthetic_interrogator.asc", "sha256": "…"},
  "channels": [{"name": "EFBG1", "source_channel": "CH_1 Sensor_1 [nm]", "unit": "nm", "quantity": "wavelength"}],
  "steps": [{"step": "mark_invalid_peaks", "kind": "preprocess",
             "params": {"zero_as_missing": true},
             "samples_before": 9001, "samples_after": 9001,
             "nan_before": {"EFBG1": 0}, "nan_after": {"EFBG1": 20}}]
}
```

## 5. Sensor setup

What is connected to each interrogator channel. Saved by the web app in
`data/setups/` and accepted by `braggflow process --setup`
(`SensorSetup.save` / `SensorSetup.load`).

| Key | Content |
|---|---|
| `name`, `description` | identification |
| `sensors[].channel` | column name in the interrogator export |
| `sensors[].name` | name used in the processed CSV and in the figures |
| `sensors[].nominal_wavelength` | nominal Bragg wavelength (nm), optional |
| `sensors[].band` | `[min, max]` allowed band (nm), optional; readings outside it are invalid |
| `sensors[].hidden` | `true` leaves the column out of the processing, as if the file did not have it (default `false`) |
| `sensors[].temp_sensitivity` | thermal sensitivity K_T (pm/°C) from a temperature calibration, optional; the temperature compensation uses `k = K_T,s / K_T,r` |

```json
{"name": "bancada", "description": "",
 "sensors": [{"channel": "CH_1 Sensor_1 [nm]", "name": "EFBG1",
              "nominal_wavelength": null, "band": [1548.0, 1552.0],
              "temp_sensitivity": 12.4}]}
```

## 6. Other files of the web app

| Folder | File | Content |
|---|---|---|
| `data/projects/` | `<name>.json` | a whole analysis: files with their own sensors and steps, concatenation, markers, spectra settings, selected curves and figure style (`braggflow.projects.Project`) |
| `data/styles/` | `<name>.json` | a figure style of the Figura tab (`braggflow.visualization.figure.resolve_style`) |

Paths inside projects are written as `data/<subfolder>/<file>`; `data` stands
for whatever data folder the app was started with.
