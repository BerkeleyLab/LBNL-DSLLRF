#-----------------------------------------------------------------------------
# Vivado TCL Script: Synthesize wave_gen and Report Utilization
#
# Usage:
#   vivado -mode batch -source synth.tcl
#   vivado -mode batch -source synth.tcl -tclargs -part xcvu9p-flga2104-2L-e
#   vivado -mode batch -source synth.tcl -tclargs -axi_width 512 -out_width 448
#
# Or in Vivado TCL console:
#   source synth.tcl
#-----------------------------------------------------------------------------

#-----------------------------------------------------------------------------
# Default Parameters
#-----------------------------------------------------------------------------

# Device
set part "xczu48dr-fsvg1517-2-e"

# Module parameters
set axi_data_width 256
set out_data_width 320
set granule 64
set bank_depth 4096
set read_latency 3
set ram_style "ultra"

# Project settings
set project_name "waveform_gen_synth"
set project_dir "./vivado_synth"
set source_file "wave_gen.v"
set wrapper_file "axi_wave_gen.v"
set top_module "wave_gen"

# Synthesis settings
set synth_strategy "Vivado Synthesis Defaults"
set synth_directive "Default"
set max_threads 8

#-----------------------------------------------------------------------------
# Parse Command Line Arguments
#-----------------------------------------------------------------------------

proc parse_args {} {
    global argc argv
    global part axi_data_width out_data_width granule bank_depth read_latency ram_style
    global project_name project_dir source_file wrapper_file

    for {set i 0} {$i < $argc} {incr i} {
        set arg [lindex $argv $i]
        switch -exact -- $arg {
            "-part" {
                incr i
                set part [lindex $argv $i]
            }
            "-axi_width" {
                incr i
                set axi_data_width [lindex $argv $i]
            }
            "-out_width" {
                incr i
                set out_data_width [lindex $argv $i]
            }
            "-granule" {
                incr i
                set granule [lindex $argv $i]
            }
            "-bank_depth" {
                incr i
                set bank_depth [lindex $argv $i]
            }
            "-read_latency" {
                incr i
                set read_latency [lindex $argv $i]
            }
            "-ram_style" {
                incr i
                set ram_style [lindex $argv $i]
            }
            "-project_name" {
                incr i
                set project_name [lindex $argv $i]
            }
            "-project_dir" {
                incr i
                set project_dir [lindex $argv $i]
            }
            "-source_file" {
                incr i
                set source_file [lindex $argv $i]
            }
            "-wrapper_file" {
                incr i
                set wrapper_file [lindex $argv $i]
            }
            "-help" {
                print_usage
                exit 0
            }
            default {
                puts "WARNING: Unknown argument: $arg"
            }
        }
    }
}

proc print_usage {} {
    puts ""
    puts "Usage: vivado -mode batch -source synth.tcl \[-tclargs options\]"
    puts ""
    puts "Options:"
    puts "  -part <device>        Target FPGA part (default: xczu48dr-fsvg1517-2-e)"
    puts "  -axi_width <bits>     AXI data width: 256 or 512 (default: 256)"
    puts "  -out_width <bits>     Output data width: 320, 448, etc (default: 320)"
    puts "  -granule <bits>       Granule size in bits (default: 64)"
    puts "  -bank_depth <depth>   Memory bank depth (default: 4096)"
    puts "  -read_latency <n>     Read pipeline latency (default: 2)"
    puts "  -ram_style <style>    RAM style: ultra or block (default: ultra)"
    puts "  -project_name <name>  Project name (default: waveform_gen_synth)"
    puts "  -project_dir <dir>    Project directory (default: ./vivado_synth)"
    puts "  -source_file <file>   Source Verilog file"
    puts "  -wrapper_file <file>  Wrapper Verilog file"
    puts "  -help                 Print this help message"
    puts ""
    puts "Examples:"
    puts "  # Default 256->320 configuration"
    puts "  vivado -mode batch -source synth.tcl"
    puts ""
    puts "  # 512->448 configuration on VU9P"
    puts "  vivado -mode batch -source synth.tcl -tclargs -part xcvu9p-flga2104-2L-e -axi_width 512 -out_width 448"
    puts ""
    puts "  # Test with Block RAM"
    puts "  vivado -mode batch -source synth.tcl -tclargs -ram_style block"
    puts ""
}

#-----------------------------------------------------------------------------
# Main Synthesis Flow
#-----------------------------------------------------------------------------

proc run_synthesis {} {
    global part axi_data_width out_data_width granule bank_depth read_latency ram_style
    global project_name project_dir source_file wrapper_file top_module
    global synth_strategy synth_directive max_threads

    set start_time [clock seconds]

    puts ""
    puts "=============================================================================="
    puts " Waveform Generator Synthesis"
    puts "=============================================================================="
    puts " Part:           $part"
    puts " AXI Width:      $axi_data_width bits"
    puts " Output Width:   $out_data_width bits"
    puts " Granule:        $granule bits"
    puts " Bank Depth:     $bank_depth"
    puts " Read Latency:   $read_latency"
    puts " RAM Style:      $ram_style"
    puts " Project Dir:    $project_dir"
    puts "=============================================================================="
    puts ""

    # Calculate derived parameters for display
    set num_banks [expr {$out_data_width / $granule}]
    set axi_granules [expr {$axi_data_width / $granule}]
    set out_granules [expr {$out_data_width / $granule}]
    set acc_granules [expr {$axi_granules + $out_granules}]
    set acc_width [expr {$acc_granules * $granule}]

    puts "Derived Parameters:"
    puts "  Number of Banks:    $num_banks x ${granule}-bit"
    puts "  AXI Granules:       $axi_granules"
    puts "  Output Granules:    $out_granules"
    puts "  Accumulator Width:  $acc_width bits ($acc_granules granules)"
    puts ""

    # Clean up previous project
    if {[file exists $project_dir]} {
        puts "INFO: Removing existing project directory..."
        file delete -force $project_dir
    }

    # Create project directory
    file mkdir $project_dir

    # Check if source file exists
    if {![file exists $source_file]} {
        puts "ERROR: Source file not found: $source_file"
        exit 1
    }
    if {![file exists $wrapper_file]} {
        puts "ERROR: Source file not found: $wrapper_file"
        exit 1
    }
    # Create project
    puts "INFO: Creating Vivado project..."
    create_project $project_name $project_dir -part $part -force

    # Set project properties
    set_property target_language Verilog [current_project]
    set_property default_lib work [current_project]

    # Add source files
    puts "INFO: Adding source files..."
    add_files -norecurse $source_file
    add_files -norecurse $wrapper_file

    # Set top module to wrapper
    set_property top axi_wave_gen [current_fileset]

    # Update compile order
    update_compile_order -fileset sources_1

    # Configure synthesis settings
    puts "INFO: Configuring synthesis settings..."
    set_property -name {STEPS.SYNTH_DESIGN.ARGS.MORE OPTIONS} -value {-mode out_of_context} -objects [get_runs synth_1]

    # Set number of threads
    set_param general.maxThreads $max_threads

    # Run synthesis
    puts "INFO: Running synthesis..."
    puts "      This may take several minutes..."
    puts ""

    reset_run synth_1
    launch_runs synth_1 -jobs $max_threads
    wait_on_run synth_1

    # Check synthesis status
    set synth_status [get_property STATUS [get_runs synth_1]]
    set synth_progress [get_property PROGRESS [get_runs synth_1]]

    puts ""
    puts "INFO: Synthesis Status: $synth_status ($synth_progress)"

    if {$synth_status != "synth_design Complete!"} {
        puts "ERROR: Synthesis failed!"
        puts "       Check the log files in $project_dir for details."
        exit 1
    }

    # Open synthesized design
    puts "INFO: Opening synthesized design..."
    open_run synth_1 -name synth_1

    # Generate reports
    puts "INFO: Generating utilization reports..."
    puts ""

    set report_dir "${project_dir}/reports"
    file mkdir $report_dir

    # Utilization report
    set util_file "${report_dir}/utilization.rpt"
    report_utilization -file $util_file

    # Hierarchical utilization
    set hier_util_file "${report_dir}/utilization_hierarchical.rpt"
    report_utilization -hierarchical -file $hier_util_file

    # RAM utilization
    set ram_util_file "${report_dir}/ram_utilization.rpt"
    report_utilization -cells [get_cells -hierarchical -filter {PRIMITIVE_TYPE =~ BLOCKRAM.*}] -file $ram_util_file

    # Timing summary (unconstrained)
    set timing_file "${report_dir}/timing_summary.rpt"
    report_timing_summary -file $timing_file

    # Design analysis
    set analysis_file "${report_dir}/design_analysis.rpt"
    report_design_analysis -file $analysis_file

    # Print utilization summary to console
    puts "=============================================================================="
    puts " UTILIZATION SUMMARY"
    puts "=============================================================================="
    report_utilization

    puts ""
    puts "=============================================================================="
    puts " MEMORY UTILIZATION"
    puts "=============================================================================="

    # Count URAM and BRAM
    set uram_count 0
    set bram_count 0

    set uram_cells [get_cells -hierarchical -filter {REF_NAME =~ URAM*} -quiet]
    set bram_cells [get_cells -hierarchical -filter {REF_NAME =~ RAMB*} -quiet]

    if {[llength $uram_cells] > 0} {
        set uram_count [llength $uram_cells]
    }
    if {[llength $bram_cells] > 0} {
        set bram_count [llength $bram_cells]
    }

    puts "  UltraRAM (URAM288):  $uram_count"
    puts "  Block RAM (RAMB36): $bram_count"
    puts ""

    # Print timing estimate
    puts "=============================================================================="
    puts " TIMING ESTIMATE (Unconstrained)"
    puts "=============================================================================="

    set wns [get_property SLACK [get_timing_paths -max_paths 1 -nworst 1 -setup]]
    if {$wns != ""} {
        puts "  Worst Negative Slack: $wns ns"
        if {$wns > 0} {
            set fmax [expr {1000.0 / (10.0 - $wns)}]
            puts "  Estimated Fmax:       [format "%.2f" $fmax] MHz (assuming 100 MHz constraint)"
        }
    } else {
        puts "  No timing paths found (unconstrained synthesis)"
    }
    puts ""

    # Calculate elapsed time
    set end_time [clock seconds]
    set elapsed [expr {$end_time - $start_time}]
    set minutes [expr {$elapsed / 60}]
    set seconds [expr {$elapsed % 60}]

    puts "=============================================================================="
    puts " SYNTHESIS COMPLETE"
    puts "=============================================================================="
    puts "  Elapsed Time: ${minutes}m ${seconds}s"
    puts ""
    puts "  Reports saved to: $report_dir"
    puts "    - utilization.rpt"
    puts "    - utilization_hierarchical.rpt"
    puts "    - ram_utilization.rpt"
    puts "    - timing_summary.rpt"
    puts "    - design_analysis.rpt"
    puts ""
    puts "=============================================================================="

    # Return summary data
    return [list $uram_count $bram_count]
}

#-----------------------------------------------------------------------------
# Multi-Configuration Test
#-----------------------------------------------------------------------------

proc run_multi_config_test {} {
    global part project_dir

    puts ""
    puts "=============================================================================="
    puts " MULTI-CONFIGURATION SYNTHESIS TEST"
    puts "=============================================================================="
    puts ""

    # Define test configurations
    set configs {
        {256 320 ultra "256b AXI -> 320b Out (UltraRAM)"}
        {256 448 ultra "256b AXI -> 448b Out (UltraRAM)"}
        {512 320 ultra "512b AXI -> 320b Out (UltraRAM)"}
        {512 448 ultra "512b AXI -> 448b Out (UltraRAM)"}
        {256 320 block "256b AXI -> 320b Out (BlockRAM)"}
        {256 448 block "256b AXI -> 448b Out (BlockRAM)"}
    }

    set results {}

    foreach config $configs {
        set axi_w [lindex $config 0]
        set out_w [lindex $config 1]
        set ram_s [lindex $config 2]
        set desc [lindex $config 3]

        puts ""
        puts "----------------------------------------------------------------------"
        puts " Testing: $desc"
        puts "----------------------------------------------------------------------"

        # Set global parameters
        global axi_data_width out_data_width ram_style project_name
        set axi_data_width $axi_w
        set out_data_width $out_w
        set ram_style $ram_s
        set project_name "wfg_${axi_w}_${out_w}_${ram_s}"

        # Run synthesis
        set result [run_synthesis]

        # Store results
        lappend results [list $desc $axi_w $out_w $ram_s [lindex $result 0] [lindex $result 1]]

        # Close project
        close_project
    }

    # Print summary table
    puts ""
    puts "=============================================================================="
    puts " MULTI-CONFIGURATION RESULTS SUMMARY"
    puts "=============================================================================="
    puts ""
    puts [format "%-40s %8s %8s %10s %10s" "Configuration" "AXI" "Output" "URAM" "BRAM"]
    puts [format "%-40s %8s %8s %10s %10s" "-------------" "---" "------" "----" "----"]

    foreach result $results {
        set desc [lindex $result 0]
        set axi_w [lindex $result 1]
        set out_w [lindex $result 2]
        set uram [lindex $result 4]
        set bram [lindex $result 5]
        puts [format "%-40s %8d %8d %10d %10d" $desc $axi_w $out_w $uram $bram]
    }

    puts ""
    puts "=============================================================================="
}

#-----------------------------------------------------------------------------
# Timing Constraint Generation
#-----------------------------------------------------------------------------

proc generate_constraints {filename target_freq} {
    set fp [open $filename w]

    set period [expr {1000.0 / $target_freq}]

    puts $fp "# Auto-generated timing constraints"
    puts $fp "# Target frequency: $target_freq MHz"
    puts $fp ""
    puts $fp "create_clock -period $period -name clk \[get_ports clk\]"
    puts $fp ""
    puts $fp "# Input delays (adjust based on system)"
    puts $fp "set_input_delay -clock clk -max [expr {$period * 0.3}] \[get_ports -filter {DIRECTION == IN && NAME != clk}\]"
    puts $fp "set_input_delay -clock clk -min 0.0 \[get_ports -filter {DIRECTION == IN && NAME != clk}\]"
    puts $fp ""
    puts $fp "# Output delays (adjust based on system)"
    puts $fp "set_output_delay -clock clk -max [expr {$period * 0.3}] \[get_ports -filter {DIRECTION == OUT}\]"
    puts $fp "set_output_delay -clock clk -min 0.0 \[get_ports -filter {DIRECTION == OUT}\]"
    puts $fp ""
    puts $fp "# False paths for async signals if any"
    puts $fp "# set_false_path -from \[get_ports rst_n\]"
    puts $fp ""

    close $fp

    puts "INFO: Generated constraints file: $filename"
    puts "      Target frequency: $target_freq MHz (period: $period ns)"
}

#-----------------------------------------------------------------------------
# Implementation Flow (Optional)
#-----------------------------------------------------------------------------

proc run_implementation {target_freq} {
    global project_dir

    puts ""
    puts "=============================================================================="
    puts " RUNNING IMPLEMENTATION"
    puts "=============================================================================="
    puts ""

    # Generate and add constraints
    set xdc_file "${project_dir}/timing.xdc"
    generate_constraints $xdc_file $target_freq
    add_files -fileset constrs_1 -norecurse $xdc_file

    # Run implementation
    puts "INFO: Launching implementation..."
    launch_runs impl_1 -jobs 8
    wait_on_run impl_1

    # Check status
    set impl_status [get_property STATUS [get_runs impl_1]]
    puts "INFO: Implementation Status: $impl_status"

    if {$impl_status == "route_design Complete!"} {
        open_run impl_1

        set report_dir "${project_dir}/reports"

        # Post-implementation reports
        report_timing_summary -file "${report_dir}/timing_impl.rpt"
        report_utilization -file "${report_dir}/utilization_impl.rpt"
        report_power -file "${report_dir}/power.rpt"

        puts ""
        puts "=============================================================================="
        puts " IMPLEMENTATION TIMING SUMMARY"
        puts "=============================================================================="
        report_timing_summary -brief
    }
}

#-----------------------------------------------------------------------------
# Entry Point
#-----------------------------------------------------------------------------

# Parse command line arguments
parse_args

# Check for multi-config test mode
set multi_test 0
foreach arg $argv {
    if {$arg == "-multi_test"} {
        set multi_test 1
    }
}

if {$multi_test} {
    run_multi_config_test
} else {
    run_synthesis
}

puts ""
puts "Script completed successfully."
puts ""