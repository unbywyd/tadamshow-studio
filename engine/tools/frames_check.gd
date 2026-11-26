extends SceneTree
## Which frame is shown when (engine/frames.gd): for the kit's tests.
##
## usage: godot --headless --path engine --script tools/frames_check.gd -- [--puppet=<folder>] [--steps=120]
##            [--specs=<file.json>] [--speed=part:2,part2:0] [--restart=part:30]
##   --puppet  a puppet folder (rig.json and parts/): it is built and stepped, and the frame every framed part
##             shows after each step is written down (from 1)
##   --speed   set_frames_speed of those parts before the first step
##   --restart restart_frames of that part before that step
##   --specs   a JSON list of "frames" records: the frame each shows at every step by itself
## Prints one line: FRAMES {"parts": {"skirt": [1, 1, ...]}, "framed": [...], "specs": [[...], ...], "shown": true}
##   shown: after every step every framed part's sprite really had the texture of the frame it names

const Puppet := preload("res://puppet.gd")
const Frames := preload("res://frames.gd")


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	var args := {}
	for a in OS.get_cmdline_user_args():
		var kv := a.trim_prefix("--").split("=", true, 1)
		args[kv[0]] = kv[1] if kv.size() > 1 else "1"
	var steps: int = int(args.get("steps", "120"))
	var out := {"parts": {}, "framed": [], "specs": [], "shown": true}
	if args.has("specs"):
		var specs: Variant = JSON.parse_string(FileAccess.get_file_as_string(args["specs"]))
		for def: Variant in (specs if specs is Array else []):
			var sp: Dictionary = Frames.spec(def)
			var seq: Array = []
			for s in range(1, steps + 1):
				seq.append(0 if sp.is_empty() else Frames.at(sp, s / 60.0) + 1)
			out["specs"].append(seq)
	if args.has("puppet"):
		var dir: String = args["puppet"]
		var p := Puppet.new()
		root.add_child(p)
		if not p.load_rig(dir.path_join("rig.json"), dir.path_join("parts")):
			print("FRAMES_ERROR no puppet in %s" % dir)
			quit(1)
			return
		out["framed"] = p.framed_parts()
		for pair: String in str(args.get("speed", "")).split(",", false):
			p.set_frames_speed(pair.get_slice(":", 0), float(pair.get_slice(":", 1)))
		var again := {}
		for pair: String in str(args.get("restart", "")).split(",", false):
			again[int(pair.get_slice(":", 1))] = pair.get_slice(":", 0)
		for name: String in out["framed"]:
			out["parts"][name] = []
		for s in range(1, steps + 1):
			if again.has(s):
				p.restart_frames(again[s])
			p.step()
			for name: String in out["framed"]:
				out["parts"][name].append(p.frame_of(name))
				var part: Variant = p.parts[name]
				if part.sprite.texture != part.frames[p.frame_of(name) - 1]:
					out["shown"] = false
	print("FRAMES " + JSON.stringify(out))
	quit(0)
