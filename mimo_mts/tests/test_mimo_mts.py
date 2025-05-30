from mimo_mts.config import ol_configs


def test_tcs_exists():
    for k, v in ol_configs.items():
        for tcs, f in v['clk104_tcs'].items():
            assert f.exists()
