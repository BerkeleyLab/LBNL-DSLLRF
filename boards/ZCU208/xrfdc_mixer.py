import xrfdc

"""Handy utility functions for xrfdc mixer-related settings decoding"""

attrs = {}
for name in dir(xrfdc):
    if name.startswith('_'):
        continue
    if name.isupper():
        prefix = name.split('_')[0]
        if prefix == "MIXER":
            prefix = '_'.join(name.split('_')[:2])
        ll = attrs.get(prefix, None)
        val = getattr(xrfdc, name)
        if ll is None:
            attrs[prefix] = {val: name}
        else:
            attrs[prefix][val] = name

for prefix, consts in attrs.items():
    print(prefix)
    for val, name in consts.items():
        print("  {} = {}".format(name, val))

def _digital_data_path_status(val, isadc=True):
    fields = {}
    fields["FIFO status"] = val & 0xf
    if isadc:
        fields["Decimation factor"] = (val >> 4) & 0xf
        fields["Adder status"] = (val >> 8) & 0xf
        fields["Mixer mode"] = (val >> 12) & 0xf
    else:
        fields["Interpolation factor"] = (val >> 4) & 0xf
        fields["Mixer mode"] = (val >> 8) & 0xf
    return ", ".join(["{}=0x{:x}".format(field, val) for field, val in fields.items()])

def _analog_data_path_status(val, isadc=True):
    if isadc:
        if val & 1:
            return "Converter Enabled"
        else:
            return "Converter Disabled"
    fields = {}
    fields["Inverse Sinc Enable"] = val & 0xf
    fields["Decoder mode"] = (val >> 4) & 0xf
    return ", ".join(["{}=0x{:x}".format(field, val) for field, val in fields.items()])

adc_block_status_map = {
    'SamplingFreq': lambda x: "{:.3f} GHz".format(x),
    'AnalogDataPathStatus': lambda x: _analog_data_path_status(x, True),
    'DigitalDataPathStatus': lambda x: _digital_data_path_status(x, True),
    'DataPathClocksStatus': lambda x: "All clocks enabled" if x else "Some clock disabled",
    'IsFIFOFlagsEnabled': lambda x: "Enabled" if x else "Disabled",
    'IsFIFOFlagsAsserted': lambda x: "Asserted" if x else "Deasserted",
}

dac_block_status_map = {
    'SamplingFreq': lambda x: "{:.3f} GHz".format(x),
    'AnalogDataPathStatus': lambda x: _analog_data_path_status(x, False),
    'DigitalDataPathStatus': lambda x: _digital_data_path_status(x, False),
    'DataPathClocksStatus': lambda x: "All clocks enabled" if x else "Some clock disabled",
    'IsFIFOFlagsEnabled': lambda x: "Enabled" if x else "Disabled",
    'IsFIFOFlagsAsserted': lambda x: "Asserted" if x else "Deasserted",
}

mixer_settings_map = {
    'Freq': lambda x: "{:.3f} MHz".format(x),
    'PhaseOffset': float,
    'EventSource': lambda x: attrs["EVNT"].get(x, int(x)),
    'CoarseMixFreq': lambda x: attrs["COARSE"].get(x, int(x)),
    'MixerMode': lambda x: attrs["MIXER_MODE"].get(x, int(x)),
    'FineMixerScale': lambda x: attrs["MIXER_SCALE"].get(x, int(x)),
    'MixerType': lambda x: attrs["MIXER_TYPE"].get(x, int(x))
}

def print_mixer_settings(block, isadc=True):
    print("Mixer Settings:")
    for key, val in block.MixerSettings.items():
        fn = mixer_settings_map.get(key)
        if fn is not None:
            print("  {}: {}".format(key, fn(val)))
        else:
            print("  {}: {}".format(key, val))

def print_block_status(block, isadc=True):
    print("Block Status:")
    for key, val in block.BlockStatus.items():
        if isadc:
            _map = adc_block_status_map
        else:
            _map = dac_block_status_map
        fn = _map.get(key)
        if fn is not None:
            print("  {}: {}".format(key, fn(val)))
        else:
            print("  {}: {}".format(key, val))

def print_mixer(block, isadc=True):
    print_mixer_settings(block, isadc)
    print_block_status(block, isadc)

def stream_data_rate_Hz(block):
    f_sample_ghz = float(block.BlockStatus["SamplingFreq"])
    decim_interp = getattr(block, "DecimationFactor", None)
    if decim_interp is None:
        decim_interp = getattr(block, "InterpolationFactor", None)
    decim_interp = int(decim_interp)
    return 1.0e9*f_sample_ghz/decim_interp

def __test():
    print(_digital_data_path_status(0x1234, True))
    print(_digital_data_path_status(0x1234, False))
    print(_analog_data_path_status(0x1234, True))
    print(_analog_data_path_status(0x1234, False))

if __name__ == "__main__":
    __test()



