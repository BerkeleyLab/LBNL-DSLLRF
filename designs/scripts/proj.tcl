#------------------------------------------------------------------------------
# Vivado Synthesis Script with Command Line Argument Parsing
#------------------------------------------------------------------------------

proc parse_args {argv} {
    # Initialize argument dictionary with defaults
    set args_dict [dict create \
        board_id    "" \
        proj_name   "" \
        bd_script   "" \
        proj_xdc    "" \
        rtl_files   {} \
        ip_scripts  {} \
        output_dir  "./_xilinx" \
        num_jobs    4 \
    ]

    set i 0
    set argc [llength $argv]

    while {$i < $argc} {
        set arg [lindex $argv $i]

        switch -exact -- $arg {
            "-board_id" {
                incr i
                if {$i >= $argc} {
                    error "Missing value for -board_id"
                }
                dict set args_dict board_id [lindex $argv $i]
            }
            "-proj_name" {
                incr i
                if {$i >= $argc} {
                    error "Missing value for -proj_name"
                }
                dict set args_dict proj_name [lindex $argv $i]
            }
            "-bd_script" {
                incr i
                if {$i >= $argc} {
                    error "Missing value for -bd_script"
                }
                dict set args_dict bd_script [lindex $argv $i]
            }
            "-proj_xdc" {
                incr i
                if {$i >= $argc} {
                    error "Missing value for -proj_xdc"
                }
                dict set args_dict proj_xdc [lindex $argv $i]
            }
            "-rtl_files" {
                incr i
                if {$i >= $argc} {
                    error "Missing value for -rtl_files"
                }
                # Parse comma-separated or space-separated list
                set file_list [split [lindex $argv $i] ","]
                set clean_list {}
                foreach f $file_list {
                    set f [string trim $f]
                    if {$f ne ""} {
                        lappend clean_list $f
                    }
                }
                dict set args_dict rtl_files $clean_list
            }
            "-ip_scripts" {
                incr i
                if {$i >= $argc} {
                    error "Missing value for -ip_scripts"
                }
                # Parse comma-separated or space-separated list (optional)
                set script_list [split [lindex $argv $i] ","]
                set clean_list {}
                foreach s $script_list {
                    set s [string trim $s]
                    if {$s ne ""} {
                        lappend clean_list $s
                    }
                }
                dict set args_dict ip_scripts $clean_list
            }
            "-output_dir" {
                incr i
                if {$i >= $argc} {
                    error "Missing value for -output_dir"
                }
                dict set args_dict output_dir [lindex $argv $i]
            }
            "-num_jobs" {
                incr i
                if {$i >= $argc} {
                    error "Missing value for -num_jobs"
                }
                dict set args_dict num_jobs [lindex $argv $i]
            }
            "-help" {
                print_usage
                exit 0
            }
            default {
                puts "WARNING: Unknown argument '$arg', ignoring."
            }
        }
        incr i
    }

    return $args_dict
}

#------------------------------------------------------------------------------
# Procedure: print_usage
# Description: Prints help message
#------------------------------------------------------------------------------
proc print_usage {} {
    puts ""
    puts "Usage: vivado -mode batch -source synth_script.tcl -tclargs \[options\]"
    puts ""
    puts "Required Arguments:"
    puts "  -board_id <id>        Target board/part identifier (e.g., xc7a100tcsg324-1)"
    puts "  -proj_name <name>     Project name"
    puts "  -bd_script <file>     Block design Tcl script path"
    puts "  -proj_xdc <file>      Constraints file (.xdc) path"
    puts "  -rtl_files <list>     Comma-separated list of RTL source files"
    puts ""
    puts "Optional Arguments:"
    puts "  -ip_scripts <list>    Comma-separated list of IP generation Tcl scripts"
    puts "  -output_dir <dir>     Output directory (default: ./output)"
    puts "  -num_jobs <n>         Number of parallel jobs (default: 4)"
    puts "  -help                 Print this help message"
    puts ""
    puts "Example:"
    puts "  vivado -mode batch -source synth_script.tcl -tclargs \\"
    puts "    -board_id zcu_208 \\"
    puts "    -proj_name my_project \\"
    puts "    -bd_script ./scripts/bd_design.tcl \\"
    puts "    -proj_xdc ./constraints/top.xdc \\"
    puts "    -rtl_files \"src/top.v,src/module_a.v,src/module_b.sv\" \\"
    puts "    -ip_scripts \"ip/clk_wiz.tcl,ip/fifo_gen.tcl\""
    puts ""
}

#------------------------------------------------------------------------------
# Procedure: validate_args
# Description: Validates required arguments and file existence
#------------------------------------------------------------------------------
proc validate_args {args_dict} {
    set required_args {board_id proj_name bd_script proj_xdc rtl_files}

    # Define valid board IDs
    set valid_board_ids {zcu208 lbl208 zcu216}
    foreach arg $required_args {
        set val [dict get $args_dict $arg]
        if {$val eq "" || ($arg eq "rtl_files" && [llength $val] == 0)} {
            puts "ERROR: Required argument '-$arg' is missing or empty."
            print_usage
            exit 1
        }
    }

    # Validate board_id against allowed list
    set board_id [dict get $args_dict board_id]
    if {[lsearch -exact $valid_board_ids $board_id] == -1} {
        puts "ERROR: Invalid board_id '$board_id'."
        puts "       Valid options are: [join $valid_board_ids {, }]"
        exit 1
    }

    # Validate file existence
    set bd_script [dict get $args_dict bd_script]
    if {![file exists $bd_script]} {
        puts "ERROR: Block design script not found: $bd_script"
        exit 1
    }

    set proj_xdc [dict get $args_dict proj_xdc]
    if {![file exists $proj_xdc]} {
        puts "ERROR: Constraints file not found: $proj_xdc"
        exit 1
    }

    foreach rtl_file [dict get $args_dict rtl_files] {
        if {![file exists $rtl_file]} {
            puts "ERROR: RTL source file not found: $rtl_file"
            exit 1
        }
    }

    foreach ip_script [dict get $args_dict ip_scripts] {
        if {![file exists $ip_script]} {
            puts "ERROR: IP script file not found: $ip_script"
            exit 1
        }
    }

    puts "INFO: All arguments validated successfully."
}

#------------------------------------------------------------------------------
# Procedure: make_project
# Description: Main synthesis flow
#------------------------------------------------------------------------------
proc make_project {args_dict} {
    # Extract arguments
    set board_id   [dict get $args_dict board_id]
    set proj_name  [dict get $args_dict proj_name]
    set bd_script  [dict get $args_dict bd_script]
    set proj_xdc   [dict get $args_dict proj_xdc]
    set rtl_files  [dict get $args_dict rtl_files]
    set ip_scripts [dict get $args_dict ip_scripts]
    set output_dir [dict get $args_dict output_dir]
    set num_jobs   [dict get $args_dict num_jobs]

    puts "============================================================"
    puts "Starting Vivado Synthesis Flow"
    puts "============================================================"
    puts "Board/Part:    $board_id"
    puts "Project Name:  $proj_name"
    puts "BD Script:     $bd_script"
    puts "XDC File:      $proj_xdc"
    puts "RTL Files:     $rtl_files"
    puts "IP Scripts:    $ip_scripts"
    puts "Output Dir:    $output_dir"
    puts "Parallel Jobs: $num_jobs"
    puts "============================================================"

    # Create output directory
    file mkdir $output_dir

set bd_name $proj_name.bd
set wrapper_name ${proj_name}_wrapper
# Get IP repos from the environment
set ip_repo_path $::env(XILINX_IP_REPO_PATH)

# UG895
set board_repo_path $::env(XILINX_BOARD_REPO_PATH)
set_param board.repoPaths [list $board_repo_path]

################################################################
# Check supported platforms
################################################################
switch $board_id {
  "zcu208" {
    set board_part "xilinx.com:zcu208:part0:2.0"
    set project_part "xczu48dr-fsvg1517-2-e"
    # set project_part [get_property PART_NAME [current_board_part]]
  }
  "zcu216" {
    set board_part "xilinx.com:zcu216:part0:2.0"
    set project_part "xczu29dr-ffvf1760-2-e"
    # set project_part [get_property PART_NAME [current_board_part]]
  }
  "lbl208" {
    set board_part "lbl.gov:lbl208:part0:2.0"
    set project_part "xczu47dr-ffvg1517-1-e"
  }
}

################################################################
# START
################################################################

# Create project
create_project ${proj_name} ${output_dir}/${proj_name} -part $project_part

# Set the directory path for the new project
set proj_dir [get_property directory [current_project]]

# Set project properties
set obj [current_project]
set_property -name "board_part" -value $board_part -objects $obj
set_property -name "default_lib" -value "xil_defaultlib" -objects $obj
set_property -name "enable_resource_estimation" -value "0" -objects $obj
set_property -name "enable_vhdl_2008" -value "1" -objects $obj
set_property -name "ip_cache_permissions" -value "read write" -objects $obj
set_property -name "ip_output_repo" -value "$proj_dir/${proj_name}.cache/ip" -objects $obj
set_property -name "mem.enable_memory_map_generation" -value "1" -objects $obj
set_property -name "platform.board_id" -value $board_id -objects $obj
set_property -name "revised_directory_structure" -value "1" -objects $obj
set_property -name "sim.central_dir" -value "$proj_dir/${proj_name}.ip_user_files" -objects $obj
set_property -name "sim.ip.auto_export_scripts" -value "1" -objects $obj
set_property -name "simulator_language" -value "Mixed" -objects $obj
set_property -name "target_language" -value "Verilog" -objects $obj
set_property -name "xpm_libraries" -value "XPM_CDC XPM_FIFO XPM_MEMORY" -objects $obj

# Create 'sources_1' fileset (if not found)
if {[string equal [get_filesets -quiet sources_1] ""]} {
  create_fileset -srcset sources_1
}

# Set IP repository paths
set obj [get_filesets sources_1]
if { $obj != {} } {
   set_property "ip_repo_paths" "[file normalize "$ip_repo_path"]" $obj
   # Rebuild user ip_repo's index before adding any source files
   update_ip_catalog -rebuild
}

set files [list]
foreach src $rtl_files {
  lappend files [file normalize $src]
}
set obj [get_filesets sources_1]
add_files -norecurse -fileset $obj $files

# Set 'sources_1' fileset properties
# Set 'top' module without auto_set in fileset properties
set obj [get_filesets sources_1]
set_property -name "top" -value "$wrapper_name" -objects $obj
set_property -name "top_auto_set" -value "0" -objects $obj

# Create 'constrs_1' fileset (if not found)
if {[string equal [get_filesets -quiet constrs_1] ""]} {
  create_fileset -constrset constrs_1
}

# Set 'constrs_1' fileset object
set obj [get_filesets constrs_1]

# Add/Import constrs file and set constrs file properties
set file "[file normalize "$proj_xdc"]"
add_files -norecurse -fileset $obj [list $file]
set_property -name "file_type" -value "XDC" -objects [get_files $file]

## UG903: allow IP cores which create clocks to be used in user xdc
# set_property PROCESSING_ORDER LATE [get_files $file]

# Create 'sim_1' fileset (if not found)
if {[string equal [get_filesets -quiet sim_1] ""]} {
  create_fileset -simset sim_1
}

################################################################
# START
################################################################
  # Source IP generation scripts (if any)
  if {[llength $ip_scripts] > 0} {
      puts "INFO: Generating IPs from scripts..."
      foreach ip_script $ip_scripts {
          puts "INFO:   Sourcing: $ip_script"
          source $ip_script
      }
  }

puts "Sourcing block design script: $bd_script"
source -quiet $bd_script
################################################################
# END
################################################################
set_property REGISTERED_WITH_MANAGER "1" [get_files $bd_name]
set_property SYNTH_CHECKPOINT_MODE "Hierarchical" [get_files $bd_name]

# Generate block design output products
set bd_name [get_bd_designs]
if {$bd_name ne ""} {
    puts "INFO: Generating block design output products..."
    generate_target all [get_files *.bd]
    make_wrapper -files [get_files -norecurse $bd_name] -top

    # Add the wrapper to the project
    set bd_wrapper_file [glob -nocomplain $output_dir/$proj_name/$proj_name.gen/sources_1/bd/$proj_name/hdl/${proj_name}_wrapper.v]
    if {[llength $bd_wrapper_file] > 0} {
        add_files -norecurse [lindex $bd_wrapper_file 0]
    }
}
set_property top ${proj_name}_wrapper [current_fileset]

update_compile_order -fileset sources_1

set idrFlowPropertiesConstraints ""
catch {
 set idrFlowPropertiesConstraints [get_param runs.disableIDRFlowPropertyConstraints]
 set_param runs.disableIDRFlowPropertyConstraints 1
}

# Create 'synth_1' run (if not found)
if {[string equal [get_runs -quiet synth_1] ""]} {
    create_run -name synth_1 -part $project_part -flow {Vivado Synthesis 2022} -strategy "Vivado Synthesis Defaults" -report_strategy {No Reports} -constrset constrs_1
} else {
  set_property strategy "Vivado Synthesis Defaults" [get_runs synth_1]
  set_property flow "Vivado Synthesis 2022" [get_runs synth_1]
}
set obj [get_runs synth_1]
set_property set_report_strategy_name 1 $obj
set_property report_strategy {Vivado Synthesis Default Reports} $obj
set_property set_report_strategy_name 0 $obj
# Create 'synth_1_synth_report_utilization_0' report (if not found)
if { [ string equal [get_report_configs -of_objects [get_runs synth_1] synth_1_synth_report_utilization_0] "" ] } {
  create_report_config -report_name synth_1_synth_report_utilization_0 -report_type report_utilization:1.0 -steps synth_design -runs synth_1
}
set obj [get_report_configs -of_objects [get_runs synth_1] synth_1_synth_report_utilization_0]
if { $obj != "" } {

}

# set the current synth run
current_run -synthesis [get_runs synth_1]

# Create 'impl_1' run (if not found)
if {[string equal [get_runs -quiet impl_1] ""]} {
    create_run -name impl_1 -part $project_part -flow {Vivado Implementation 2022} -strategy "Vivado Implementation Defaults" -report_strategy {No Reports} -constrset constrs_1 -parent_run synth_1
} else {
  set_property strategy "Vivado Implementation Defaults" [get_runs impl_1]
  set_property flow "Vivado Implementation 2022" [get_runs impl_1]
}
set obj [get_runs impl_1]
set_property set_report_strategy_name 1 $obj
set_property report_strategy {Vivado Implementation Default Reports} $obj
set_property set_report_strategy_name 0 $obj
# Create 'impl_1_init_report_timing_summary_0' report (if not found)
if { [ string equal [get_report_configs -of_objects [get_runs impl_1] impl_1_init_report_timing_summary_0] "" ] } {
  create_report_config -report_name impl_1_init_report_timing_summary_0 -report_type report_timing_summary:1.0 -steps init_design -runs impl_1
}
set obj [get_report_configs -of_objects [get_runs impl_1] impl_1_init_report_timing_summary_0]
if { $obj != "" } {
set_property -name "is_enabled" -value "0" -objects $obj
set_property -name "options.max_paths" -value "10" -objects $obj
set_property -name "options.report_unconstrained" -value "1" -objects $obj

}
# Create 'impl_1_opt_report_drc_0' report (if not found)
if { [ string equal [get_report_configs -of_objects [get_runs impl_1] impl_1_opt_report_drc_0] "" ] } {
  create_report_config -report_name impl_1_opt_report_drc_0 -report_type report_drc:1.0 -steps opt_design -runs impl_1
}
set obj [get_report_configs -of_objects [get_runs impl_1] impl_1_opt_report_drc_0]
if { $obj != "" } {

}
# Create 'impl_1_opt_report_timing_summary_0' report (if not found)
if { [ string equal [get_report_configs -of_objects [get_runs impl_1] impl_1_opt_report_timing_summary_0] "" ] } {
  create_report_config -report_name impl_1_opt_report_timing_summary_0 -report_type report_timing_summary:1.0 -steps opt_design -runs impl_1
}
set obj [get_report_configs -of_objects [get_runs impl_1] impl_1_opt_report_timing_summary_0]
if { $obj != "" } {
set_property -name "is_enabled" -value "0" -objects $obj
set_property -name "options.max_paths" -value "10" -objects $obj
set_property -name "options.report_unconstrained" -value "1" -objects $obj

}
# Create 'impl_1_power_opt_report_timing_summary_0' report (if not found)
if { [ string equal [get_report_configs -of_objects [get_runs impl_1] impl_1_power_opt_report_timing_summary_0] "" ] } {
  create_report_config -report_name impl_1_power_opt_report_timing_summary_0 -report_type report_timing_summary:1.0 -steps power_opt_design -runs impl_1
}
set obj [get_report_configs -of_objects [get_runs impl_1] impl_1_power_opt_report_timing_summary_0]
if { $obj != "" } {
set_property -name "is_enabled" -value "0" -objects $obj
set_property -name "options.max_paths" -value "10" -objects $obj
set_property -name "options.report_unconstrained" -value "1" -objects $obj

}
# Create 'impl_1_place_report_io_0' report (if not found)
if { [ string equal [get_report_configs -of_objects [get_runs impl_1] impl_1_place_report_io_0] "" ] } {
  create_report_config -report_name impl_1_place_report_io_0 -report_type report_io:1.0 -steps place_design -runs impl_1
}
set obj [get_report_configs -of_objects [get_runs impl_1] impl_1_place_report_io_0]
if { $obj != "" } {

}
# Create 'impl_1_place_report_utilization_0' report (if not found)
if { [ string equal [get_report_configs -of_objects [get_runs impl_1] impl_1_place_report_utilization_0] "" ] } {
  create_report_config -report_name impl_1_place_report_utilization_0 -report_type report_utilization:1.0 -steps place_design -runs impl_1
}
set obj [get_report_configs -of_objects [get_runs impl_1] impl_1_place_report_utilization_0]
if { $obj != "" } {

}
# Create 'impl_1_place_report_control_sets_0' report (if not found)
if { [ string equal [get_report_configs -of_objects [get_runs impl_1] impl_1_place_report_control_sets_0] "" ] } {
  create_report_config -report_name impl_1_place_report_control_sets_0 -report_type report_control_sets:1.0 -steps place_design -runs impl_1
}
set obj [get_report_configs -of_objects [get_runs impl_1] impl_1_place_report_control_sets_0]
if { $obj != "" } {
set_property -name "options.verbose" -value "1" -objects $obj

}
# Create 'impl_1_place_report_incremental_reuse_0' report (if not found)
if { [ string equal [get_report_configs -of_objects [get_runs impl_1] impl_1_place_report_incremental_reuse_0] "" ] } {
  create_report_config -report_name impl_1_place_report_incremental_reuse_0 -report_type report_incremental_reuse:1.0 -steps place_design -runs impl_1
}
set obj [get_report_configs -of_objects [get_runs impl_1] impl_1_place_report_incremental_reuse_0]
if { $obj != "" } {
set_property -name "is_enabled" -value "0" -objects $obj

}
# Create 'impl_1_place_report_incremental_reuse_1' report (if not found)
if { [ string equal [get_report_configs -of_objects [get_runs impl_1] impl_1_place_report_incremental_reuse_1] "" ] } {
  create_report_config -report_name impl_1_place_report_incremental_reuse_1 -report_type report_incremental_reuse:1.0 -steps place_design -runs impl_1
}
set obj [get_report_configs -of_objects [get_runs impl_1] impl_1_place_report_incremental_reuse_1]
if { $obj != "" } {
set_property -name "is_enabled" -value "0" -objects $obj

}
# Create 'impl_1_place_report_timing_summary_0' report (if not found)
if { [ string equal [get_report_configs -of_objects [get_runs impl_1] impl_1_place_report_timing_summary_0] "" ] } {
  create_report_config -report_name impl_1_place_report_timing_summary_0 -report_type report_timing_summary:1.0 -steps place_design -runs impl_1
}
set obj [get_report_configs -of_objects [get_runs impl_1] impl_1_place_report_timing_summary_0]
if { $obj != "" } {
set_property -name "is_enabled" -value "0" -objects $obj
set_property -name "options.max_paths" -value "10" -objects $obj
set_property -name "options.report_unconstrained" -value "1" -objects $obj

}
# Create 'impl_1_post_place_power_opt_report_timing_summary_0' report (if not found)
if { [ string equal [get_report_configs -of_objects [get_runs impl_1] impl_1_post_place_power_opt_report_timing_summary_0] "" ] } {
  create_report_config -report_name impl_1_post_place_power_opt_report_timing_summary_0 -report_type report_timing_summary:1.0 -steps post_place_power_opt_design -runs impl_1
}
set obj [get_report_configs -of_objects [get_runs impl_1] impl_1_post_place_power_opt_report_timing_summary_0]
if { $obj != "" } {
set_property -name "is_enabled" -value "0" -objects $obj
set_property -name "options.max_paths" -value "10" -objects $obj
set_property -name "options.report_unconstrained" -value "1" -objects $obj

}
# Create 'impl_1_phys_opt_report_timing_summary_0' report (if not found)
if { [ string equal [get_report_configs -of_objects [get_runs impl_1] impl_1_phys_opt_report_timing_summary_0] "" ] } {
  create_report_config -report_name impl_1_phys_opt_report_timing_summary_0 -report_type report_timing_summary:1.0 -steps phys_opt_design -runs impl_1
}
set obj [get_report_configs -of_objects [get_runs impl_1] impl_1_phys_opt_report_timing_summary_0]
if { $obj != "" } {
set_property -name "is_enabled" -value "0" -objects $obj
set_property -name "options.max_paths" -value "10" -objects $obj
set_property -name "options.report_unconstrained" -value "1" -objects $obj

}
# Create 'impl_1_route_report_drc_0' report (if not found)
if { [ string equal [get_report_configs -of_objects [get_runs impl_1] impl_1_route_report_drc_0] "" ] } {
  create_report_config -report_name impl_1_route_report_drc_0 -report_type report_drc:1.0 -steps route_design -runs impl_1
}
set obj [get_report_configs -of_objects [get_runs impl_1] impl_1_route_report_drc_0]
if { $obj != "" } {

}
# Create 'impl_1_route_report_methodology_0' report (if not found)
if { [ string equal [get_report_configs -of_objects [get_runs impl_1] impl_1_route_report_methodology_0] "" ] } {
  create_report_config -report_name impl_1_route_report_methodology_0 -report_type report_methodology:1.0 -steps route_design -runs impl_1
}
set obj [get_report_configs -of_objects [get_runs impl_1] impl_1_route_report_methodology_0]
if { $obj != "" } {

}
# Create 'impl_1_route_report_power_0' report (if not found)
if { [ string equal [get_report_configs -of_objects [get_runs impl_1] impl_1_route_report_power_0] "" ] } {
  create_report_config -report_name impl_1_route_report_power_0 -report_type report_power:1.0 -steps route_design -runs impl_1
}
set obj [get_report_configs -of_objects [get_runs impl_1] impl_1_route_report_power_0]
if { $obj != "" } {

}
# Create 'impl_1_route_report_route_status_0' report (if not found)
if { [ string equal [get_report_configs -of_objects [get_runs impl_1] impl_1_route_report_route_status_0] "" ] } {
  create_report_config -report_name impl_1_route_report_route_status_0 -report_type report_route_status:1.0 -steps route_design -runs impl_1
}
set obj [get_report_configs -of_objects [get_runs impl_1] impl_1_route_report_route_status_0]
if { $obj != "" } {

}
# Create 'impl_1_route_report_timing_summary_0' report (if not found)
if { [ string equal [get_report_configs -of_objects [get_runs impl_1] impl_1_route_report_timing_summary_0] "" ] } {
  create_report_config -report_name impl_1_route_report_timing_summary_0 -report_type report_timing_summary:1.0 -steps route_design -runs impl_1
}
set obj [get_report_configs -of_objects [get_runs impl_1] impl_1_route_report_timing_summary_0]
if { $obj != "" } {
set_property -name "options.max_paths" -value "10" -objects $obj
set_property -name "options.report_unconstrained" -value "1" -objects $obj

}
# Create 'impl_1_route_report_incremental_reuse_0' report (if not found)
if { [ string equal [get_report_configs -of_objects [get_runs impl_1] impl_1_route_report_incremental_reuse_0] "" ] } {
  create_report_config -report_name impl_1_route_report_incremental_reuse_0 -report_type report_incremental_reuse:1.0 -steps route_design -runs impl_1
}
set obj [get_report_configs -of_objects [get_runs impl_1] impl_1_route_report_incremental_reuse_0]
if { $obj != "" } {

}
# Create 'impl_1_route_report_clock_utilization_0' report (if not found)
if { [ string equal [get_report_configs -of_objects [get_runs impl_1] impl_1_route_report_clock_utilization_0] "" ] } {
  create_report_config -report_name impl_1_route_report_clock_utilization_0 -report_type report_clock_utilization:1.0 -steps route_design -runs impl_1
}
set obj [get_report_configs -of_objects [get_runs impl_1] impl_1_route_report_clock_utilization_0]
if { $obj != "" } {

}
# Create 'impl_1_route_report_bus_skew_0' report (if not found)
if { [ string equal [get_report_configs -of_objects [get_runs impl_1] impl_1_route_report_bus_skew_0] "" ] } {
  create_report_config -report_name impl_1_route_report_bus_skew_0 -report_type report_bus_skew:1.1 -steps route_design -runs impl_1
}
set obj [get_report_configs -of_objects [get_runs impl_1] impl_1_route_report_bus_skew_0]
if { $obj != "" } {
set_property -name "options.warn_on_violation" -value "1" -objects $obj

}
# Create 'impl_1_route_report_datasheet_0' report (if not found)
if { [ string equal [get_report_configs -of_objects [get_runs impl_1] impl_1_route_report_datasheet_0] "" ] } {
  create_report_config -report_name impl_1_route_report_datasheet_0 -report_type report_datasheet -steps route_design -runs impl_1
}
set obj [get_report_configs -of_objects [get_runs impl_1] impl_1_route_report_datasheet_0]
if { $obj != "" } {

}
# Create 'impl_1_post_route_phys_opt_report_timing_summary_0' report (if not found)
if { [ string equal [get_report_configs -of_objects [get_runs impl_1] impl_1_post_route_phys_opt_report_timing_summary_0] "" ] } {
  create_report_config -report_name impl_1_post_route_phys_opt_report_timing_summary_0 -report_type report_timing_summary:1.0 -steps post_route_phys_opt_design -runs impl_1
}
set obj [get_report_configs -of_objects [get_runs impl_1] impl_1_post_route_phys_opt_report_timing_summary_0]
if { $obj != "" } {
set_property -name "options.max_paths" -value "10" -objects $obj
set_property -name "options.report_unconstrained" -value "1" -objects $obj
set_property -name "options.warn_on_violation" -value "1" -objects $obj

}
# Create 'impl_1_post_route_phys_opt_report_bus_skew_0' report (if not found)
if { [ string equal [get_report_configs -of_objects [get_runs impl_1] impl_1_post_route_phys_opt_report_bus_skew_0] "" ] } {
  create_report_config -report_name impl_1_post_route_phys_opt_report_bus_skew_0 -report_type report_bus_skew:1.1 -steps post_route_phys_opt_design -runs impl_1
}
set obj [get_report_configs -of_objects [get_runs impl_1] impl_1_post_route_phys_opt_report_bus_skew_0]
if { $obj != "" } {
set_property -name "options.warn_on_violation" -value "1" -objects $obj

}
set obj [get_runs impl_1]
set_property -name "needs_refresh" -value "1" -objects $obj
set_property -name "strategy" -value "Vivado Implementation Defaults" -objects $obj
set_property -name "steps.write_bitstream.args.readback_file" -value "0" -objects $obj
set_property -name "steps.write_bitstream.args.verbose" -value "0" -objects $obj

# set the current impl run
current_run -implementation [get_runs impl_1]
catch {
 if { $idrFlowPropertiesConstraints != {} } {
   set_param runs.disableIDRFlowPropertyConstraints $idrFlowPropertiesConstraints
 }
}

puts "INFO: Project created:${proj_name}"
# Create 'drc_1' gadget (if not found)
if {[string equal [get_dashboard_gadgets  [ list "drc_1" ] ] ""]} {
create_dashboard_gadget -name {drc_1} -type drc
}
set obj [get_dashboard_gadgets [ list "drc_1" ] ]
set_property -name "reports" -value "impl_1#impl_1_route_report_drc_0" -objects $obj

# Create 'methodology_1' gadget (if not found)
if {[string equal [get_dashboard_gadgets  [ list "methodology_1" ] ] ""]} {
create_dashboard_gadget -name {methodology_1} -type methodology
}
set obj [get_dashboard_gadgets [ list "methodology_1" ] ]
set_property -name "reports" -value "impl_1#impl_1_route_report_methodology_0" -objects $obj

# Create 'power_1' gadget (if not found)
if {[string equal [get_dashboard_gadgets  [ list "power_1" ] ] ""]} {
create_dashboard_gadget -name {power_1} -type power
}
set obj [get_dashboard_gadgets [ list "power_1" ] ]
set_property -name "reports" -value "impl_1#impl_1_route_report_power_0" -objects $obj

# Create 'timing_1' gadget (if not found)
if {[string equal [get_dashboard_gadgets  [ list "timing_1" ] ] ""]} {
create_dashboard_gadget -name {timing_1} -type timing
}
set obj [get_dashboard_gadgets [ list "timing_1" ] ]
set_property -name "reports" -value "impl_1#impl_1_route_report_timing_summary_0" -objects $obj

# Create 'utilization_1' gadget (if not found)
if {[string equal [get_dashboard_gadgets  [ list "utilization_1" ] ] ""]} {
create_dashboard_gadget -name {utilization_1} -type utilization
}
set obj [get_dashboard_gadgets [ list "utilization_1" ] ]
set_property -name "reports" -value "synth_1#synth_1_synth_report_utilization_0" -objects $obj
set_property -name "run.step" -value "synth_design" -objects $obj
set_property -name "run.type" -value "synthesis" -objects $obj

# Create 'utilization_2' gadget (if not found)
if {[string equal [get_dashboard_gadgets  [ list "utilization_2" ] ] ""]} {
create_dashboard_gadget -name {utilization_2} -type utilization
}
set obj [get_dashboard_gadgets [ list "utilization_2" ] ]
set_property -name "reports" -value "impl_1#impl_1_place_report_utilization_0" -objects $obj

move_dashboard_gadget -name {utilization_1} -row 0 -col 0
move_dashboard_gadget -name {power_1} -row 1 -col 0
move_dashboard_gadget -name {drc_1} -row 2 -col 0
move_dashboard_gadget -name {timing_1} -row 0 -col 1
move_dashboard_gadget -name {utilization_2} -row 1 -col 1
move_dashboard_gadget -name {methodology_1} -row 2 -col 1
}

################################################################
# Check if script is running in correct Vivado version.
################################################################
proc validate_vivado_version {required_version {mode "exact"}} {
    set current_version [version -short]

    # Extract major.minor from current version
    if {![regexp {^(\d+)\.(\d+)} $current_version match curr_major curr_minor]} {
        puts "ERROR: Unable to parse Vivado version: $current_version"
        exit 1
    }

    # Extract major.minor from required version
    if {![regexp {^(\d+)\.(\d+)} $required_version match req_major req_minor]} {
        puts "ERROR: Invalid required version format: $required_version"
        exit 1
    }

    set version_ok 0

    switch -exact -- $mode {
        "exact" {
            if {$curr_major == $req_major && $curr_minor == $req_minor} {
                set version_ok 1
            }
        }
        "minimum" {
            if {$curr_major > $req_major} {
                set version_ok 1
            } elseif {$curr_major == $req_major && $curr_minor >= $req_minor} {
                set version_ok 1
            }
        }
        default {
            puts "ERROR: Invalid version check mode: $mode (use 'exact' or 'minimum')"
            exit 1
        }
    }

    if {!$version_ok} {
        puts "============================================================"
        puts "ERROR: Vivado version mismatch!"
        if {$mode eq "exact"} {
            puts "       Required version: $required_version (exact)"
        } else {
            puts "       Minimum version:  $required_version"
        }
        puts "       Current version:  $current_version"
        puts "============================================================"
        exit 1
    }

    puts "INFO: Vivado version $current_version verified (required: $required_version, mode: $mode)"
}

validate_vivado_version "2022.1"

#------------------------------------------------------------------------------
# Main Entry Point
#------------------------------------------------------------------------------
puts "INFO: Vivado Synthesis Script Started"
puts "INFO: Vivado Version: [version -short]"

# Parse command line arguments
set args_dict [parse_args $argv]

# Validate arguments
validate_args $args_dict

# Make a vivado project
make_project $args_dict

puts "INFO: Script completed."
exit 0