#------------------------------------------------------------------------------
# GT Wizard Ultrascale IP Generation
#------------------------------------------------------------------------------

proc create_gtwizard_ultrascale {config_dict} {
    # Default configuration
    set defaults [dict create \
        refclk_freq     156.25 \
        module_name     "evr_gt" \
        cpll_fbdiv      16 \
        cpll_refclk_div 1 \
        txout_div       10 \
        freerun_freq    100 \
        rx_refclk_src   "X0Y4 clk1+2" \
        tx_refclk_src   "X0Y4 clk1+2" \
    ]

    # Merge user config with defaults
    set config [dict merge $defaults $config_dict]

    # Extract values
    set refclk_freq [dict get $config refclk_freq]
    set module_name [dict get $config module_name]

    # Validate
    if {$refclk_freq eq ""} {
        error "refclk_freq is required in config dict"
    }
    if {![string is double -strict $refclk_freq]} {
        error "refclk_freq must be numeric, got '$refclk_freq'"
    }

    # Calculate derived values
    set cpll_fbdiv      [dict get $config cpll_fbdiv]
    set cpll_refclk_div [dict get $config cpll_refclk_div]
    set txout_div       [dict get $config txout_div]

    set LINE_RATE_MHz  [expr {($refclk_freq * $cpll_fbdiv / $cpll_refclk_div) / $txout_div}]
    set LINE_RATE_Gbps [expr {$LINE_RATE_MHz * 10.0 / 1000.0}]
    set TXPROG_FREQ    [expr {$LINE_RATE_MHz / 2.0}]

    puts "----------------------------------------"
    puts "GT Wizard: $module_name"
    puts "  Refclk:    ${refclk_freq} MHz"
    puts "  Line Rate: ${LINE_RATE_Gbps} Gbps"
    puts "----------------------------------------"

    create_ip -name gtwizard_ultrascale -vendor xilinx.com -library ip -version 1.7 -module_name $module_name

    set_property -dict [list \
        CONFIG.TX_LINE_RATE             $LINE_RATE_Gbps \
        CONFIG.TX_PLL_TYPE              CPLL \
        CONFIG.TX_REFCLK_FREQUENCY      $refclk_freq \
        CONFIG.TX_DATA_ENCODING         8B10B \
        CONFIG.TX_USER_DATA_WIDTH       16 \
        CONFIG.TX_INT_DATA_WIDTH        20 \
        CONFIG.RX_LINE_RATE             $LINE_RATE_Gbps \
        CONFIG.RX_PLL_TYPE              CPLL \
        CONFIG.RX_REFCLK_FREQUENCY      $refclk_freq \
        CONFIG.RX_DATA_DECODING         8B10B \
        CONFIG.RX_USER_DATA_WIDTH       16 \
        CONFIG.RX_INT_DATA_WIDTH        20 \
        CONFIG.RX_BUFFER_MODE           0 \
        CONFIG.RX_JTOL_FC               1.4997001 \
        CONFIG.RX_REFCLK_SOURCE         [dict get $config rx_refclk_src] \
        CONFIG.TX_REFCLK_SOURCE         [dict get $config tx_refclk_src] \
        CONFIG.LOCATE_TX_USER_CLOCKING  CORE \
        CONFIG.LOCATE_RX_USER_CLOCKING  CORE \
        CONFIG.TXPROGDIV_FREQ_SOURCE    CPLL \
        CONFIG.TXPROGDIV_FREQ_VAL       $TXPROG_FREQ \
        CONFIG.FREERUN_FREQUENCY        [dict get $config freerun_freq] \
        CONFIG.ENABLE_OPTIONAL_PORTS    cplllock_out \
    ] [get_ips $module_name]

    generate_target all [get_files ${module_name}.xci]
}

#------------------------------------------------------------------------------
# GT Wizard (7-Series) IP Generation Procedure
# Usage: create_gtwizard <config_dict>
#------------------------------------------------------------------------------

proc create_gtwizard {config_dict} {
    # Default configuration
    set defaults [dict create \
        refclk_freq      156.25        \
        module_name      "evr_gt"      \
        cpll_fbdiv       4             \
        cpll_fbdiv_45    5             \
        cpll_refclk_div  1             \
        txout_div        2             \
        rxout_div        2             \
        drp_clock        125           \
        rx_refclk        "REFCLK0_Q0"  \
        tx_refclk        "REFCLK0_Q0"  \
        rx_data_width    16            \
        tx_data_width    20            \
        rx_int_datawidth 20            \
        tx_int_datawidth 20            \
        gt_column        "right_column" \
        gt_row           "bottom_row"  \
        gt_type          "GTX"         \
        no_rx            false         \
        no_tx            true          \
        rxbuf_en         false         \
        txbuf_en         true          \
        decoding         "8B/10B"      \
        dfe_mode         "LPM-Auto"    \
        rxslide_mode     "PCS"         \
        comma_preset     "K28.5"       \
        ppm_offset       100           \
        gt0_val          false         \
        gt2_val          true          \
    ]

    # Merge user config with defaults
    set config [dict merge $defaults $config_dict]

    # Extract and validate refclk_freq (required)
    set refclk_freq [dict get $config refclk_freq]
    if {$refclk_freq eq ""} {
        error "create_gtwizard: refclk_freq is required"
    }
    if {![string is double -strict $refclk_freq]} {
        error "create_gtwizard: refclk_freq must be a numeric value in MHz, got '$refclk_freq'"
    }
    set refclk_freq [format "%.3f" $refclk_freq]

    # Extract other parameters
    set module_name      [dict get $config module_name]
    set cpll_fbdiv       [dict get $config cpll_fbdiv]
    set cpll_fbdiv_45    [dict get $config cpll_fbdiv_45]
    set cpll_refclk_div  [dict get $config cpll_refclk_div]
    set txout_div        [dict get $config txout_div]
    set rxout_div        [dict get $config rxout_div]
    set drp_clock        [dict get $config drp_clock]
    set rx_refclk        [dict get $config rx_refclk]
    set tx_refclk        [dict get $config tx_refclk]
    set rx_data_width    [dict get $config rx_data_width]
    set tx_data_width    [dict get $config tx_data_width]
    set rx_int_datawidth [dict get $config rx_int_datawidth]
    set tx_int_datawidth [dict get $config tx_int_datawidth]
    set gt_column        [dict get $config gt_column]
    set gt_row           [dict get $config gt_row]
    set gt_type          [dict get $config gt_type]
    set no_rx            [dict get $config no_rx]
    set no_tx            [dict get $config no_tx]
    set rxbuf_en         [dict get $config rxbuf_en]
    set txbuf_en         [dict get $config txbuf_en]
    set decoding         [dict get $config decoding]
    set dfe_mode         [dict get $config dfe_mode]
    set rxslide_mode     [dict get $config rxslide_mode]
    set comma_preset     [dict get $config comma_preset]
    set ppm_offset       [dict get $config ppm_offset]
    set gt0_val          [dict get $config gt0_val]
    set gt2_val          [dict get $config gt2_val]

    # Calculate line rate
    set LINE_RATE_MHz  [expr {($refclk_freq * $cpll_fbdiv / $cpll_refclk_div) / $txout_div}]
    set LINE_RATE_Gbps [expr {$LINE_RATE_MHz * 10.0 / 1000.0}]

    puts "----------------------------------------"
    puts "GT Wizard (7-Series) Auto Config:"
    puts "  Module:       $module_name"
    puts "  Refclk:       ${refclk_freq} MHz"
    puts "  CPLL_FBDIV:   $cpll_fbdiv"
    puts "  TXOUT_DIV:    $txout_div"
    puts "  Line Rate:    ${LINE_RATE_Gbps} Gbps ($decoding)"
    puts "  GT Type:      $gt_type"
    puts "  GT Location:  $gt_column / $gt_row"
    puts "  RX Enabled:   [expr {!$no_rx}]"
    puts "  TX Enabled:   [expr {!$no_tx}]"
    puts "----------------------------------------"

    create_ip -name gtwizard -vendor xilinx.com -library ip -version 3.6 -module_name $module_name

    set_property -dict [list \
        CONFIG.advanced_clocking                   false \
        CONFIG.example_chipscope                   0 \
        CONFIG.gt0_pll0_fbdiv                      1 \
        CONFIG.gt0_pll0_fbdiv_45                   4 \
        CONFIG.gt0_pll0_refclk_div                 1 \
        CONFIG.gt0_pll0_rxout_div                  1 \
        CONFIG.gt0_pll0_txout_div                  1 \
        CONFIG.gt0_pll1_fbdiv                      1 \
        CONFIG.gt0_pll1_fbdiv_45                   4 \
        CONFIG.gt0_pll1_refclk_div                 1 \
        CONFIG.gt0_pll1_rxout_div                  1 \
        CONFIG.gt0_pll1_txout_div                  1 \
        CONFIG.gt0_uselabtools                     false \
        CONFIG.gt0_usesharedlogic                  0 \
        CONFIG.gt0_val                             $gt0_val \
        CONFIG.gt0_val_agc_mode                    Auto \
        CONFIG.gt0_val_align_comma_double          false \
        CONFIG.gt0_val_align_comma_enable          1111111111 \
        CONFIG.gt0_val_align_comma_word            Two_Byte_Boundaries \
        CONFIG.gt0_val_align_mcomma_det            true \
        CONFIG.gt0_val_align_mcomma_value          1010000011 \
        CONFIG.gt0_val_align_pcomma_det            true \
        CONFIG.gt0_val_align_pcomma_value          0101111100 \
        CONFIG.gt0_val_cb                          false \
        CONFIG.gt0_val_cc                          false \
        CONFIG.gt0_val_cc_seq_periodicity          5000 \
        CONFIG.gt0_val_clk_cor_seq_1_1             00000000 \
        CONFIG.gt0_val_clk_cor_seq_1_2             00000000 \
        CONFIG.gt0_val_clk_cor_seq_1_3             00000000 \
        CONFIG.gt0_val_clk_cor_seq_1_4             00000000 \
        CONFIG.gt0_val_clk_cor_seq_2_1             00000000 \
        CONFIG.gt0_val_clk_cor_seq_2_2             00000000 \
        CONFIG.gt0_val_clk_cor_seq_2_3             00000000 \
        CONFIG.gt0_val_clk_cor_seq_2_4             00000000 \
        CONFIG.gt0_val_clk_cor_seq_len             1 \
        CONFIG.gt0_val_comma_preset                $comma_preset \
        CONFIG.gt0_val_cpll_fbdiv                  $cpll_fbdiv \
        CONFIG.gt0_val_cpll_fbdiv_45               $cpll_fbdiv_45 \
        CONFIG.gt0_val_cpll_refclk_div             $cpll_refclk_div \
        CONFIG.gt0_val_cpll_rxout_div              $rxout_div \
        CONFIG.gt0_val_cpll_txout_div              $txout_div \
        CONFIG.gt0_val_dec_mcomma_detect           true \
        CONFIG.gt0_val_dec_pcomma_detect           true \
        CONFIG.gt0_val_dec_valid_comma_only        true \
        CONFIG.gt0_val_decoding                    $decoding \
        CONFIG.gt0_val_dfe_mode                    $dfe_mode \
        CONFIG.gt0_val_drp                         true \
        CONFIG.gt0_val_drp_clock                   $drp_clock \
        CONFIG.gt0_val_max_cb_level                7 \
        CONFIG.gt0_val_no_rx                       $no_rx \
        CONFIG.gt0_val_no_tx                       $no_tx \
        CONFIG.gt0_val_oob                         false \
        CONFIG.gt0_val_port_rxcharisk              true \
        CONFIG.gt0_val_port_rxdfereset             true \
        CONFIG.gt0_val_port_rxelecidle             true \
        CONFIG.gt0_val_port_rxoutclk               true \
        CONFIG.gt0_val_port_rxpmareset             true \
        CONFIG.gt0_val_port_rxslide                true \
        CONFIG.gt0_val_port_txoutclk               true \
        CONFIG.gt0_val_ppm_offset                  $ppm_offset \
        CONFIG.gt0_val_prbs_detector               false \
        CONFIG.gt0_val_protocol_file               Start_from_scratch \
        CONFIG.gt0_val_qpll_fbdiv                  16 \
        CONFIG.gt0_val_qpll_refclk_div             1 \
        CONFIG.gt0_val_rx_buffer_bypass_mode       Auto \
        CONFIG.gt0_val_rx_cm_trim                  800 \
        CONFIG.gt0_val_rx_data_width               $rx_data_width \
        CONFIG.gt0_val_rx_equalizer                false \
        CONFIG.gt0_val_rx_int_datawidth            $rx_int_datawidth \
        CONFIG.gt0_val_rx_line_rate                $LINE_RATE_Gbps \
        CONFIG.gt0_val_rx_refclk                   $rx_refclk \
        CONFIG.gt0_val_rx_reference_clock          $refclk_freq \
        CONFIG.gt0_val_rx_termination_voltage      Programmable \
        CONFIG.gt0_val_rxbuf_en                    $rxbuf_en \
        CONFIG.gt0_val_rxcomma_deten               true \
        CONFIG.gt0_val_rxoutclk_source             false \
        CONFIG.gt0_val_rxprbs_err_loopback         false \
        CONFIG.gt0_val_rxslide_mode                $rxslide_mode \
        CONFIG.gt0_val_rxusrclk                    RXOUTCLK \
        CONFIG.gt0_val_sata_e_idle_val             4 \
        CONFIG.gt0_val_sata_rx_burst_val           4 \
        CONFIG.gt0_val_tx_buffer_bypass_mode       Auto \
        CONFIG.gt0_val_tx_data_width               $tx_data_width \
        CONFIG.gt0_val_tx_int_datawidth            $tx_int_datawidth \
        CONFIG.gt0_val_tx_line_rate                $LINE_RATE_Gbps \
        CONFIG.gt0_val_tx_refclk                   $tx_refclk \
        CONFIG.gt0_val_tx_reference_clock          $refclk_freq \
        CONFIG.gt0_val_txbuf_en                    $txbuf_en \
        CONFIG.gt0_val_txdiff_emph_mode            Custom \
        CONFIG.gt0_val_txdiffctrl                  false \
        CONFIG.gt0_val_txmaincursor                false \
        CONFIG.gt0_val_txoutclk_source             false \
        CONFIG.gt0_val_txpostcursor                false \
        CONFIG.gt0_val_txprecursor                 false \
        CONFIG.gt0_val_txusrclk                    TXOUTCLK \
        CONFIG.gt2_val                             $gt2_val \
        CONFIG.gt2_val_rx_refclk                   $rx_refclk \
        CONFIG.gt2_val_tx_refclk                   $tx_refclk \
        CONFIG.gt_column                           $gt_column \
        CONFIG.gt_row                              $gt_row \
        CONFIG.gt_type                             $gt_type \
        CONFIG.gt_val_drp                          false \
        CONFIG.gt_val_drp_clock                    60 \
        CONFIG.gt_val_extended_timeout             false \
        CONFIG.gt_val_rx_pll                       CPLL \
        CONFIG.gt_val_tx_pll                       CPLL \
        CONFIG.gtz0_val_data_width                 160 \
        CONFIG.identical_config                    true \
        CONFIG.identical_protocol_file             Start_from_scratch \
        CONFIG.identical_val_no_rx                 $no_rx \
        CONFIG.identical_val_no_tx                 $no_tx \
        CONFIG.identical_val_rx_line_rate          $LINE_RATE_Gbps \
        CONFIG.identical_val_rx_reference_clock    $refclk_freq \
        CONFIG.identical_val_tx_line_rate          $LINE_RATE_Gbps \
        CONFIG.identical_val_tx_reference_clock    $refclk_freq \
    ] [get_ips $module_name]

    generate_target all [get_files ${module_name}.xci]

    puts "INFO: GT Wizard IP '$module_name' created successfully."
    return $module_name
}