extends SceneTree
## The CLEAN SWITCH (motion.gd play_clean, the workshop): action A plays, then B is switched to cleanly at some
## moments of A; after the switch no channel may still be held by A (or by anything but B), and B must own exactly
## the channels its own phases name.
##
## usage: godot --headless --path engine --script tools/switch_check.gd -- --hero=<puppet folder>
##            [--pairs=wave>hips,think>clap] [--at=0.2,0.8] [--layered: play() instead, which must fail]
## prints SWITCH {"runs": n, "bad": [...]}

const Puppet := preload("res://puppet.gd")
const BodyPhysics := preload("res://body_physics.gd")
const Motion := preload("res://motion.gd")
const Stage := preload("res://stage.gd")
const SIZE := Vector2(720, 1280)
const PAIRS := ["wave>hips", "hips>wave", "think>clap", "dance_arms>point", "squat>facepalm", "laugh>bow", "shrug>wave"]


func _initialize() -> void:
	var args := {}
	for a in OS.get_cmdline_user_args():
		var kv := a.trim_prefix("--").split("=", true, 1)
		args[kv[0]] = kv[1] if kv.size() > 1 else "1"
	var pairs: Array = Array(str(args["pairs"]).split(",")) if args.has("pairs") else PAIRS
	var ats: Array = Array(str(args.get("at", "0.2,0.9")).split(",")).map(func(x): return float(x))
	var lib := Stage.actions()
	var dir: String = str(args["hero"])
	var bad: Array = []
	var n := 0
	for pair: String in pairs:
		var a: Dictionary = lib[pair.get_slice(">", 0)]
		var b: Dictionary = lib[pair.get_slice(">", 1)]
		for at: float in ats:
			var p := Puppet.new()
			root.add_child(p)
			p.load_rig(dir.path_join("rig.json"), dir.path_join("parts"),
				{"foot_l": {"bend": "out", "end_mode": "level"}, "foot_r": {"bend": "out", "end_mode": "level"}})
			var k: float = SIZE.y * 0.34 / float(p.rig["body_height"])
			p.scale = Vector2.ONE * k
			p.position = Vector2(SIZE.x * 0.5 - p.body_position().x * k, SIZE.y * 0.86 - 1500.0 * k)
			p.reset_pose()
			var phys := BodyPhysics.new()
			phys.puppet = p
			phys.floor_y = SIZE.y * 0.86
			phys.stage_width = SIZE.x
			phys.feet = ["foot_l", "foot_r"]
			phys.stand_here()
			var mo := Motion.new()
			mo.setup(p, phys, SIZE.y * 0.86, SIZE)
			mo.play(a, {"side": "right", "duration": 3.0})
			for i in int(at * 60.0):
				mo.step()
			if args.has("layered"):              # (the check's own check: the old way must fail it)
				mo.clean_run = mo.play(b, {"side": "right", "duration": 3.0})
			else:
				mo.play_clean(b, {"side": "right", "duration": 3.0})
			var waited := 0
			while mo.clean_run == null and waited < 600:
				mo.step()
				waited += 1
			for i in 20:
				mo.step()
			n += 1
			var want: Array = []
			for ph: Dictionary in b.get("phases", []):
				for ch: String in Motion.CHANNELS:
					if (ph.has(ch) or (ph.has("arms") and ch.begins_with("arm"))) and not want.has(ch):
						want.append(ch)
			for ch: String in Motion.CHANNELS:
				var owner: Variant = mo.chans[ch].owner
				var ok: bool = (owner == null and not want.has(ch)) or (owner != null and owner == mo.clean_run)
				if mo.clean_run != null and mo.clean_run.done and owner == null:
					ok = true                        # (B already finished: everything let go)
				if not ok or mo.clean_run == null:
					bad.append({"pair": pair, "at": at, "channel": ch, "owner": owner.id if owner != null else ""})
			p.queue_free()
	print("SWITCH " + JSON.stringify({"runs": n, "bad": bad}))
	quit(0)
