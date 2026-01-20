#------------------------------------------------------------------------------
# Vivado Synthesis Flow Procedure
# Usage: run_synthesis <config_dict>
#------------------------------------------------------------------------------

proc run_synthesis {config_dict} {
    # Default configuration
    set defaults [dict create \
        proj_name       ""              \
        output_dir      "./_xilinx"     \
        num_jobs        4               \
        synth_run       "synth_1"       \
        impl_run        "impl_1"        \
        gen_bitstream   true            \
        gen_reports     true            \
        gen_handoff     true            \
        copy_bitstream  true            \
        report_power    false           \
        open_project    true            \
        close_project   true            \
    ]

    # Merge user config with defaults
    set config [dict merge $defaults $config_dict]

    # Extract and validate proj_name (required)
    set proj_name [dict get $config proj_name]
    if {$proj_name eq ""} {
        error "run_synthesis: proj_name is required"
    }

    # Extract other parameters
    set output_dir     [dict get $config output_dir]
    set num_jobs       [dict get $config num_jobs]
    set synth_run      [dict get $config synth_run]
    set impl_run       [dict get $config impl_run]
    set gen_bitstream  [dict get $config gen_bitstream]
    set gen_reports    [dict get $config gen_reports]
    set gen_handoff    [dict get $config gen_handoff]
    set copy_bitstream [dict get $config copy_bitstream]
    set report_power   [dict get $config report_power]
    set do_open_proj   [dict get $config open_project]
    set do_close_proj  [dict get $config close_project]

    # Validate num_jobs
    if {![string is integer -strict $num_jobs] || $num_jobs < 1} {
        error "run_synthesis: num_jobs must be a positive integer, got '$num_jobs'"
    }

    # Construct project path
    set proj_path "$output_dir/$proj_name/$proj_name.xpr"

    puts "============================================================"
    puts "Vivado Synthesis Flow"
    puts "============================================================"
    puts "  Project:       $proj_name"
    puts "  Project Path:  $proj_path"
    puts "  Output Dir:    $output_dir"
    puts "  Parallel Jobs: $num_jobs"
    puts "  Synth Run:     $synth_run"
    puts "  Impl Run:      $impl_run"
    puts "  Gen Bitstream: $gen_bitstream"
    puts "  Gen Reports:   $gen_reports"
    puts "  Gen Handoff:   $gen_handoff"
    puts "============================================================"

    # Open project
    if {$do_open_proj} {
        if {![file exists $proj_path]} {
            error "run_synthesis: Project file not found: $proj_path"
        }
        puts "INFO: Opening project: $proj_path"
        open_project $proj_path
    }

    # Run synthesis
    puts "INFO: Running synthesis ($synth_run)..."
    reset_run $synth_run
    launch_runs $synth_run -jobs $num_jobs
    wait_on_run $synth_run

    # Check synthesis status
    set synth_status [get_property STATUS [get_runs $synth_run]]
    if {[string match "*ERROR*" $synth_status] || [string match "*FAILED*" $synth_status]} {
        puts "ERROR: Synthesis failed with status: $synth_status"
        if {$do_close_proj} { close_project }
        return -code error "Synthesis failed"
    }
    puts "INFO: Synthesis completed with status: $synth_status"

    # Run implementation
    puts "INFO: Running implementation ($impl_run)..."
    launch_runs $impl_run -jobs $num_jobs
    wait_on_run $impl_run

    # Check implementation status
    set impl_status [get_property STATUS [get_runs $impl_run]]
    if {[string match "*ERROR*" $impl_status] || [string match "*FAILED*" $impl_status]} {
        puts "ERROR: Implementation failed with status: $impl_status"
        if {$do_close_proj} { close_project }
        return -code error "Implementation failed"
    }
    puts "INFO: Implementation completed with status: $impl_status"

    # Generate bitstream
    if {$gen_bitstream} {
        puts "INFO: Generating bitstream..."
        launch_runs $impl_run -to_step write_bitstream -jobs $num_jobs
        wait_on_run $impl_run

        # Copy bitstream to output directory
        if {$copy_bitstream} {
            set bitstream_files [glob -nocomplain $output_dir/$proj_name/$proj_name.runs/$impl_run/*.bit]
            if {[llength $bitstream_files] > 0} {
                set src_bit [lindex $bitstream_files 0]
                set dst_bit "$output_dir/${proj_name}.bit"
                file copy -force $src_bit $dst_bit
                puts "INFO: Bitstream copied to: $dst_bit"
            } else {
                puts "WARNING: No bitstream file found"
            }
        }
    }

    # Generate hardware handoff files (XSA and HWH)
    if {$gen_handoff} {
        puts "INFO: Generating hardware handoff files..."
        # generate xsa
        set dst_xsa "$output_dir/${proj_name}.xsa"
        write_hw_platform -fixed -include_bit -force -file $dst_xsa
        validate_hw_platform $dst_xsa
        puts "INFO: XSA file wrote to $dst_xsa"

        set src_hwh "$output_dir/$proj_name/${proj_name}.gen/sources_1/bd/${proj_name}/hw_handoff/${proj_name}.hwh"
        set dst_hwh "$output_dir/${proj_name}.hwh"
        file copy -force $src_hwh $dst_hwh
        puts "INFO: HWH file copied to $dst_hwh"
    }

    # Generate reports
    if {$gen_reports} {
        puts "INFO: Generating reports..."
        open_run $impl_run

        report_utilization -file "$output_dir/${proj_name}_utilization.rpt"
        puts "INFO: Utilization report: $output_dir/${proj_name}_utilization.rpt"

        report_timing_summary -file "$output_dir/${proj_name}_timing.rpt"
        puts "INFO: Timing report: $output_dir/${proj_name}_timing.rpt"

        if {$report_power} {
            report_power -file "$output_dir/${proj_name}_power.rpt"
            puts "INFO: Power report: $output_dir/${proj_name}_power.rpt"
        }
    }

    # Close project
    if {$do_close_proj} {
        close_project
    }

    puts "============================================================"
    puts "Synthesis flow completed successfully!"
    puts "  Project:   $proj_name"
    if {$gen_bitstream} {
        puts "  Bitstream: $output_dir/${proj_name}.bit"
    }
    if {$gen_handoff} {
        puts "  XSA File:  $output_dir/${proj_name}.xsa"
        puts "  HWH File:  $output_dir/${proj_name}.hwh"
    }
    puts "============================================================"

    return 0
}

#------------------------------------------------------------------------------
# Helper: Parse command line arguments into dict
#------------------------------------------------------------------------------
proc parse_synth_args {argv} {
    set config [dict create]

    set i 0
    set argc [llength $argv]

    while {$i < $argc} {
        set arg [lindex $argv $i]

        switch -exact -- $arg {
            "-proj_name" - "-project" {
                incr i
                dict set config proj_name [lindex $argv $i]
            }
            "-output_dir" - "-out" {
                incr i
                dict set config output_dir [lindex $argv $i]
            }
            "-num_jobs" - "-jobs" {
                incr i
                dict set config num_jobs [lindex $argv $i]
            }
            "-synth_run" {
                incr i
                dict set config synth_run [lindex $argv $i]
            }
            "-impl_run" {
                incr i
                dict set config impl_run [lindex $argv $i]
            }
            "-no_bitstream" {
                dict set config gen_bitstream false
            }
            "-no_reports" {
                dict set config gen_reports false
            }
            "-handoff" {
                dict set config gen_handoff true
            }
            "-power_report" {
                dict set config report_power true
            }
            "-help" {
                puts "Usage: vivado -mode batch -source synth.tcl -tclargs \[options\]"
                puts ""
                puts "Options:"
                puts "  -proj_name <name>    Project name (required)"
                puts "  -output_dir <dir>    Output directory (default: ./_xilinx)"
                puts "  -num_jobs <n>        Parallel jobs (default: 4)"
                puts "  -synth_run <run>     Synthesis run name (default: synth_1)"
                puts "  -impl_run <run>      Implementation run name (default: impl_1)"
                puts "  -no_bitstream        Skip bitstream generation"
                puts "  -no_reports          Skip report generation"
                puts "  -handoff             Generate XSA and HWH handoff files"
                puts "  -power_report        Generate power report"
                puts "  -help                Show this help"
                exit 0
            }
            default {
                # Support positional argument for proj_name (backward compatibility)
                if {![dict exists $config proj_name]} {
                    dict set config proj_name $arg
                } else {
                    puts "WARNING: Unknown argument: $arg"
                }
            }
        }
        incr i
    }

    return $config
}

#------------------------------------------------------------------------------
# Main Entry Point
#------------------------------------------------------------------------------
if {[info exists argv] && [llength $argv] > 0} {
    # Parse command line arguments
    set config [parse_synth_args $argv]

    # Run synthesis
    if {[catch {run_synthesis $config} result]} {
        puts "ERROR: $result"
        exit 1
    }

    exit 0
}