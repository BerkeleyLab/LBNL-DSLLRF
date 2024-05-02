# Definitional proc to organize widgets for parameters.
proc init_gui { IPINST } {
  ipgui::add_param $IPINST -name "Component_Name"
  #Adding Page
  set Page_0 [ipgui::add_page $IPINST -name "Page 0"]
  ipgui::add_param $IPINST -name "C_S_AXI_DATA_WIDTH" -parent ${Page_0} -widget comboBox
  ipgui::add_param $IPINST -name "C_S_AXI_ADDR_WIDTH" -parent ${Page_0}
  ipgui::add_param $IPINST -name "C_S_AXI_BASEADDR" -parent ${Page_0}
  ipgui::add_param $IPINST -name "C_S_AXI_HIGHADDR" -parent ${Page_0}

  set CW [ipgui::add_param $IPINST -name "CW"]
  set_property tooltip {Width of pulse duration counter} ${CW}
  set STREAM_SAMPLES [ipgui::add_param $IPINST -name "STREAM_SAMPLES"]
  set_property tooltip {Number of samples in the AXI-4 Stream to the DAC} ${STREAM_SAMPLES}
  set MODE_IQ [ipgui::add_param $IPINST -name "MODE_IQ"]
  set_property tooltip {Enable interleaved I/Q samples instead of real-only (I-only) samples} ${MODE_IQ}
  set MODULATED [ipgui::add_param $IPINST -name "MODULATED"]
  set_property tooltip {Set to True to generate a sinusoidal output. False generates a square pulse.} ${MODULATED}

}

proc update_PARAM_VALUE.CW { PARAM_VALUE.CW } {
	# Procedure called to update CW when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.CW { PARAM_VALUE.CW } {
	# Procedure called to validate CW
	return true
}

proc update_PARAM_VALUE.MODE_IQ { PARAM_VALUE.MODE_IQ } {
	# Procedure called to update MODE_IQ when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.MODE_IQ { PARAM_VALUE.MODE_IQ } {
	# Procedure called to validate MODE_IQ
	return true
}

proc update_PARAM_VALUE.MODULATED { PARAM_VALUE.MODULATED } {
	# Procedure called to update MODULATED when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.MODULATED { PARAM_VALUE.MODULATED } {
	# Procedure called to validate MODULATED
	return true
}

proc update_PARAM_VALUE.STREAM_SAMPLES { PARAM_VALUE.STREAM_SAMPLES } {
	# Procedure called to update STREAM_SAMPLES when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.STREAM_SAMPLES { PARAM_VALUE.STREAM_SAMPLES } {
	# Procedure called to validate STREAM_SAMPLES
	return true
}

proc update_PARAM_VALUE.C_S_AXI_DATA_WIDTH { PARAM_VALUE.C_S_AXI_DATA_WIDTH } {
	# Procedure called to update C_S_AXI_DATA_WIDTH when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.C_S_AXI_DATA_WIDTH { PARAM_VALUE.C_S_AXI_DATA_WIDTH } {
	# Procedure called to validate C_S_AXI_DATA_WIDTH
	return true
}

proc update_PARAM_VALUE.C_S_AXI_ADDR_WIDTH { PARAM_VALUE.C_S_AXI_ADDR_WIDTH } {
	# Procedure called to update C_S_AXI_ADDR_WIDTH when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.C_S_AXI_ADDR_WIDTH { PARAM_VALUE.C_S_AXI_ADDR_WIDTH } {
	# Procedure called to validate C_S_AXI_ADDR_WIDTH
	return true
}

proc update_PARAM_VALUE.C_S_AXI_BASEADDR { PARAM_VALUE.C_S_AXI_BASEADDR } {
	# Procedure called to update C_S_AXI_BASEADDR when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.C_S_AXI_BASEADDR { PARAM_VALUE.C_S_AXI_BASEADDR } {
	# Procedure called to validate C_S_AXI_BASEADDR
	return true
}

proc update_PARAM_VALUE.C_S_AXI_HIGHADDR { PARAM_VALUE.C_S_AXI_HIGHADDR } {
	# Procedure called to update C_S_AXI_HIGHADDR when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.C_S_AXI_HIGHADDR { PARAM_VALUE.C_S_AXI_HIGHADDR } {
	# Procedure called to validate C_S_AXI_HIGHADDR
	return true
}


proc update_MODELPARAM_VALUE.C_S_AXI_DATA_WIDTH { MODELPARAM_VALUE.C_S_AXI_DATA_WIDTH PARAM_VALUE.C_S_AXI_DATA_WIDTH } {
	# Procedure called to set VHDL generic/Verilog parameter value(s) based on TCL parameter value
	set_property value [get_property value ${PARAM_VALUE.C_S_AXI_DATA_WIDTH}] ${MODELPARAM_VALUE.C_S_AXI_DATA_WIDTH}
}

proc update_MODELPARAM_VALUE.C_S_AXI_ADDR_WIDTH { MODELPARAM_VALUE.C_S_AXI_ADDR_WIDTH PARAM_VALUE.C_S_AXI_ADDR_WIDTH } {
	# Procedure called to set VHDL generic/Verilog parameter value(s) based on TCL parameter value
	set_property value [get_property value ${PARAM_VALUE.C_S_AXI_ADDR_WIDTH}] ${MODELPARAM_VALUE.C_S_AXI_ADDR_WIDTH}
}

proc update_MODELPARAM_VALUE.CW { MODELPARAM_VALUE.CW PARAM_VALUE.CW } {
	# Procedure called to set VHDL generic/Verilog parameter value(s) based on TCL parameter value
	set_property value [get_property value ${PARAM_VALUE.CW}] ${MODELPARAM_VALUE.CW}
}

proc update_MODELPARAM_VALUE.STREAM_SAMPLES { MODELPARAM_VALUE.STREAM_SAMPLES PARAM_VALUE.STREAM_SAMPLES } {
	# Procedure called to set VHDL generic/Verilog parameter value(s) based on TCL parameter value
	set_property value [get_property value ${PARAM_VALUE.STREAM_SAMPLES}] ${MODELPARAM_VALUE.STREAM_SAMPLES}
}

proc update_MODELPARAM_VALUE.MODE_IQ { MODELPARAM_VALUE.MODE_IQ PARAM_VALUE.MODE_IQ } {
	# Procedure called to set VHDL generic/Verilog parameter value(s) based on TCL parameter value
	set_property value [get_property value ${PARAM_VALUE.MODE_IQ}] ${MODELPARAM_VALUE.MODE_IQ}
}

proc update_MODELPARAM_VALUE.MODULATED { MODELPARAM_VALUE.MODULATED PARAM_VALUE.MODULATED } {
	# Procedure called to set VHDL generic/Verilog parameter value(s) based on TCL parameter value
	set_property value [get_property value ${PARAM_VALUE.MODULATED}] ${MODELPARAM_VALUE.MODULATED}
}

