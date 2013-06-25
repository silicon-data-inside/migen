# This file is Copyright (c) 2013 Florent Kermarrec <florent@enjoy-digital.fr>
# License: GPLv3

import os, subprocess

from mibuild.generic_platform import *
from mibuild.crg import SimpleCRG
from mibuild import tools

def _add_period_constraint(platform, clk, period):
	platform.add_platform_command("""set_global_assignment -name DUTY_CYCLE 50 -section_id {clk}""", clk=clk)
	platform.add_platform_command("""set_global_assignment -name FMAX_REQUIREMENT "{freq} MHz" -section_id {clk}\n""".format(freq=str(float(1/period)*1000), clk="{clk}"), clk=clk)

class CRG_SE(SimpleCRG):
	def __init__(self, platform, clk_name, rst_name, period, rst_invert=False):
		SimpleCRG.__init__(self, platform, clk_name, rst_name, rst_invert)
		_add_period_constraint(platform, self.cd_sys.clk, period)

def _format_constraint(c):
	if isinstance(c, Pins):
		return "set_location_assignment PIN_" + c.identifiers[0]
	elif isinstance(c, IOStandard):
		return "set_instance_assignment -name IO_STANDARD " + "\"" + c.name + "\"" 
	elif isinstance(c, Misc):
		return c.misc

def _format_qsf(signame, pin, others, resname):
	fmt_c = [_format_constraint(c) for c in ([Pins(pin)] + others)]
	fmt_r = resname[0] + ":" + str(resname[1])
	if resname[2] is not None:
		fmt_r += "." + resname[2]
	r = ""
	for c in fmt_c:
		r += c + " -to " + signame + " # " + fmt_r + "\n"
	return r

def _build_qsf(named_sc, named_pc):
	r = ""
	for sig, pins, others, resname in named_sc:
		if len(pins) > 1:
			for i, p in enumerate(pins):
				r += _format_qsf(sig + "[" + str(i) + "]", p, others, resname)
		else:
			r += _format_qsf(sig, pins[0], others, resname)
	if named_pc:
		r += "\n" + "\n\n".join(named_pc)
	return r

def _build_files(device, sources, named_sc, named_pc, build_name):
	qsf_contents = ""
	for filename, language in sources:
		qsf_contents += "set_global_assignment -name "+language.upper()+"_FILE " + filename.replace("\\","/") + "\n"

	qsf_contents += _build_qsf(named_sc, named_pc)
	qsf_contents += "set_global_assignment -name DEVICE " + device
	tools.write_to_file(build_name + ".qsf", qsf_contents)

def _run_quartus(build_name, quartus_path):
	build_script_contents = """# Autogenerated by mibuild

quartus_map {build_name}.qpf
quartus_fit {build_name}.qpf
quartus_asm {build_name}.qpf
quartus_sta {build_name}.qpf

""".format(build_name=build_name)
	build_script_file = "build_" + build_name + ".sh"
	tools.write_to_file(build_script_file, build_script_contents)

	r = subprocess.call(["bash", build_script_file])
	if r != 0:
		raise OSError("Subprocess failed")

class AlteraQuartusPlatform(GenericPlatform):
	def build(self, fragment, build_dir="build", build_name="top",
			quartus_path="/opt/Altera", run=True):
		self.finalize(fragment)
		tools.mkdir_noerror(build_dir)
		os.chdir(build_dir)

		v_src, named_sc, named_pc = self.get_verilog(fragment)
		v_file = build_name + ".v"
		tools.write_to_file(v_file, v_src)
		sources = self.sources + [(v_file, "verilog")]
		_build_files(self.device, sources, named_sc, named_pc, build_name)
		if run:
			_run_quartus(build_name, quartus_path)
		
		os.chdir("..")

	def build_arg_ns(self, ns, *args, **kwargs):
		for n in ["build_dir", "build_name", "quartus_path"]:
			kwargs[n] = getattr(ns, n)
		kwargs["run"] = not ns.no_run
		self.build(*args, **kwargs)

	def add_arguments(self, parser):
		parser.add_argument("--build-dir", default="build", help="Set the directory in which to generate files and run Quartus")
		parser.add_argument("--build-name", default="top", help="Base name for the generated files")
		parser.add_argument("--quartus-path", default="/opt/Altera", help="Quartus installation path (without version directory)")
		parser.add_argument("--no-run", action="store_true", help="Only generate files, do not run Quartus")
