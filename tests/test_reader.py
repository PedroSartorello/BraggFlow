import pytest
import numpy as np
from src.io.reader import read_asc

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