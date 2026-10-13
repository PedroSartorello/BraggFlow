import pytest
import numpy as np
from braggflow.io.reader import (
	classify_file,
	describe_file,
	detect_text_format,
	file_fingerprint,
	load_interrogator_file,
	load_spectra,
	read_asc,
	sniff_format,
)

def test_read_asc_basic(tmp_path):
	content = """Time	CH1	CH2
0,0	1,0	2,0
0,1	3,0	4,0
"""
	p = tmp_path / "sample.asc"
	p.write_text(content, encoding='utf-8')

	time_array, signals_array, ch_cols = read_asc(str(p))

	np.testing.assert_allclose(time_array, np.array([0.0, 0.1]))
	assert signals_array.shape == (2, 2)
	np.testing.assert_allclose(signals_array, np.array([[1.0, 2.0], [3.0, 4.0]]))
	assert ch_cols == ['CH1', 'CH2']


def _write(tmp_path, content, name="data.asc"):
	p = tmp_path / name
	p.write_text(content, encoding="utf-8")
	return p


@pytest.mark.parametrize("content, expected", [
	("Time\tCH1\n0,0\t1550,1\n", ("\t", ",")),
	("Time;CH1\n0,0;1550,1\n", (";", ",")),
	("Time,CH1\n0.0,1550.1\n", (",", ".")),
	("Time\tCH1\n0.0\t1550.1\n", ("\t", ".")),
])
def test_sniff_format(tmp_path, content, expected):
	assert sniff_format(_write(tmp_path, content)) == expected


def test_units_parsed_and_lost_peaks_kept(tmp_path):
	"""Zeros are exported as-is; cleaning is a separate, explicit step."""
	p = _write(tmp_path, "Time [s]\tCH_1 Sensor_1 [nm]\tCH_2 Sensor_1 [nm]\n"
	                     "0,00\t1550,1\t1545,2\n0,01\t0\t0\n0,02\t1550,1\t1545,2\n")
	data = load_interrogator_file(p)
	assert data.units == ["nm", "nm"]
	assert data.signals.shape == (3, 2)
	assert data.signals[1, 0] == 0.0


def test_trailing_separator_does_not_shift_columns(tmp_path):
	"""Interrogator export with a tab at the end of every data row (CRLF,
	scientific notation): columns must stay aligned with the header."""
	rows = [
		["Time  1 - default sample rate [s]", "CH_1 Sensor_1 [nm]", "CH_2 Sensor_1 [nm]", "CH_3 Sensor_1 [nm]"],
		["0", "1537,762523", "1541,466355", "1540,96271", ""],
		["0,020000000949949", "1537,762232", "1541,46649", "1540,962767", ""],
		["4,00000018998981E-02", "1537,761871", "1541,466495", "1540,962635", ""],
	]
	p = tmp_path / "trailing.ASC"
	p.write_bytes("".join("\t".join(r) + "\r\n" for r in rows).encode())
	data = load_interrogator_file(p)
	assert data.channels == ["CH_1 Sensor_1 [nm]", "CH_2 Sensor_1 [nm]", "CH_3 Sensor_1 [nm]"]
	np.testing.assert_allclose(data.time, [0.0, 0.02, 0.04], atol=1e-8)
	np.testing.assert_allclose(data.signals[0], [1537.762523, 1541.466355, 1540.96271])


def test_text_entries_become_nan(tmp_path):
	p = _write(tmp_path, "Time\tCH1\n0,0\t1550,1\n0,1\tN/A\n0,2\t1550,3\n")
	data = load_interrogator_file(p)
	assert np.isnan(data.signals[1, 0])
	assert data.signals[2, 0] == pytest.approx(1550.3)


def test_absolute_timestamps(tmp_path):
	p = _write(tmp_path, "Timestamp;CH1\n"
	                     "16/09/2026 10:23:38,000;1550,1\n"
	                     "16/09/2026 10:23:38,500;1550,2\n"
	                     "16/09/2026 10:23:40,000;1550,3\n")
	data = load_interrogator_file(p)
	np.testing.assert_allclose(data.time, [0.0, 0.5, 2.0])
	assert data.time_origin == "2026-09-16T10:23:38"


def test_time_only_wraps_midnight(tmp_path):
	p = _write(tmp_path, "Time\tCH1\n23:59:59.5\t1550,1\n00:00:00.5\t1550,2\n")
	data = load_interrogator_file(p)
	np.testing.assert_allclose(data.time, [0.0, 1.0])


def test_channels_without_ch_prefix(tmp_path):
	p = _write(tmp_path, "Tempo,Grade A,Grade B,Obs\n0.0,1550.1,1545.2,ok\n0.1,1550.2,1545.3,ok\n")
	data = load_interrogator_file(p)
	assert data.channels == ["Grade A", "Grade B"]


def test_missing_time_column_raises(tmp_path):
	p = _write(tmp_path, "Index\tCH1\n0\t1550,1\n")
	with pytest.raises(ValueError, match="coluna de tempo"):
		load_interrogator_file(p)


def test_file_fingerprint(tmp_path):
	p = _write(tmp_path, "Time\tCH1\n0,0\t1,0\n")
	fp = file_fingerprint(p)
	assert fp["file"] == "data.asc"
	assert fp["size_bytes"] == p.stat().st_size
	assert len(fp["sha256"]) == 64


# ── espectros e detecção de formato ───────────────────────────────────────────

def _osa_file(tmp_path, name="espectro.dat", n=400, encoding="utf-16", empty_trace=True):
	"""Exportação de OSA: UTF-16, sem cabeçalho, traços empilhados, vírgula decimal."""
	lines = []
	for i in range(n):
		lam = 1510 + i * 0.02
		lines.append(f"CH 1\t{i + 1}\t{lam:.3f}\t{60 + (i % 7):.5f}".replace(".", ","))
	if empty_trace:
		for i in range(n):
			lines.append(f"Subset 2\t{i + 1}\t\t")
	path = tmp_path / name
	path.write_bytes(("\r\n".join(lines) + "\r\n").encode(encoding))
	return path


def test_detects_utf16_osa_export(tmp_path):
	path = _osa_file(tmp_path)
	fmt = detect_text_format(path)
	assert fmt.encoding.startswith("utf-16") and fmt.sep == "\t"
	assert fmt.decimal == "," and not fmt.has_header
	assert classify_file(path) == "spectrum"


def test_load_spectra_drops_empty_traces(tmp_path):
	spectra = load_spectra(_osa_file(tmp_path))
	assert spectra.names == ["CH 1"], "o traço vazio 'Subset 2' é descartado"
	spectrum = spectra.spectra[0]
	assert spectrum.n_points == 400
	np.testing.assert_allclose(spectrum.wavelength[:2], [1510.0, 1510.02])


def test_spectrum_is_not_read_as_time_series(tmp_path):
	with pytest.raises(ValueError, match="espectro"):
		load_interrogator_file(_osa_file(tmp_path))


def test_wide_spectrum_with_header(tmp_path):
	rows = ["Wavelength [nm];Ar;Alcool"]
	rows += [f"{1530 + i * 0.01:.3f};{10 + i % 5};{12 + i % 3}".replace(".", ",") for i in range(300)]
	path = tmp_path / "espectros.csv"
	path.write_text("\n".join(rows), encoding="utf-8")

	spectra = load_spectra(path)
	assert spectra.names == ["Ar", "Alcool"]
	assert spectra.spectra[0].n_points == 300


def test_descending_wavelength_is_reordered(tmp_path):
	rows = [f"{1590 - i * 0.05:.3f}\t{20 + i % 4}" for i in range(300)]
	path = tmp_path / "desc.txt"
	path.write_text("\n".join(rows), encoding="utf-8")
	spectrum = load_spectra(path).spectra[0]
	assert spectrum.wavelength[0] < spectrum.wavelength[-1]


def test_preamble_lines_before_the_header(tmp_path):
	content = ("# Instrumento XYZ\n# 2026-10-07\n"
	           "Time [s];CH_1 [nm];CH_2 [nm]\n"
	           "0;1550,1;1545,2\n0,01;1550,2;1545,3\n0,02;1550,1;1545,2\n")
	path = tmp_path / "com_preambulo.prn"
	path.write_text(content, encoding="utf-8")

	fmt = detect_text_format(path)
	assert fmt.sep == ";" and fmt.has_header and fmt.skiprows == 2
	data = load_interrogator_file(path)
	assert data.channels == ["CH_1 [nm]", "CH_2 [nm]"]
	np.testing.assert_allclose(data.time, [0.0, 0.01, 0.02])


def test_whitespace_separated_file(tmp_path):
	content = "Time CH_1 CH_2\n0 1550.1 1545.2\n0.01 1550.2 1545.3\n0.02 1550.3 1545.4\n"
	path = tmp_path / "espacos.txt"
	path.write_text(content, encoding="utf-8")
	data = load_interrogator_file(path)
	assert data.channels == ["CH_1", "CH_2"]
	assert len(data.time) == 3


def test_latin1_file_with_accented_header(tmp_path):
	path = tmp_path / "latin.txt"
	path.write_bytes("Tempo [s]\tCanal Óptico [nm]\n0\t1550,1\n1\t1550,2\n".encode("latin-1"))
	data = load_interrogator_file(path)
	assert data.channels == ["Canal Óptico [nm]"]


def test_describe_file_reports_format_and_content(tmp_path):
	info = describe_file(_osa_file(tmp_path))
	assert info["kind"] == "spectrum"
	assert info["traces"] == ["CH 1"]
	assert info["wavelength_range"][0] == 1510.0
	assert "utf-16" in info["format"] and "tabulação" in info["format"]
