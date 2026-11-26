extends SceneTree
## An arm said in ANGLES is drawn at those angles: plays one-pose actions {"raise", "elbow"} on a hero and reads the
## angles back from the drawn joints. Prints ANGLES {"worst": degrees, "rows": [[raise, elbow, got_raise, got_elbow]..]}.
## usage: godot --headless --path engine --script tools/angle_check.gd -- --hero=<puppet dir>

const Puppet := preload("res://puppet.gd")
const Motion := preload("res://motion.gd")
const BodyPhysics := preload("res://body_physics.gd")
const SIZE := Vector2(720, 1280)
const POSES := [[30, 0], [90, 0], [140, 35], [22, 80], [45, -70], [90, 90], [90, -90], [160, -20], [60, 120], [25, -100]]


func _initialize() -> void:
	var dir := ""
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--hero="):
			dir = a.trim_prefix("--hero=")
	var rows: Array = []
	var worst := 0.0
	for pose: Array in POSES:
		for ch: String in ["arm_r", "arm_l"]:
			var p := Puppet.new()
			root.add_child(p)
			p.load_rig(dir.path_join("rig.json"), dir.path_join("parts"),
				{"foot_l": {"bend": "out", "end_mode": "level"}, "foot_r": {"bend": "out", "end_mode": "level"}})
			p.reset_pose()
			var sole := -INF
			for f: String in ["foot_l", "foot_r"]:
				sole = maxf(sole, p.point(p.rig["handles"][f]["end"], "sole").y)
			var k: float = SIZE.y * 0.34 / float(p.rig["body_height"])
			p.scale = Vector2.ONE * k
			p.position = Vector2(SIZE.x * 0.5 - p.body_position().x * k, SIZE.y * 0.86 - sole * k)
			p.reset_pose()
			for f: String in ["foot_l", "foot_r"]:
				p.set_target(f, p.handle_position(f))
			var phys := BodyPhysics.new()
			phys.puppet = p
			phys.floor_y = SIZE.y * 0.86
			phys.stage_width = SIZE.x
			phys.feet = ["foot_l", "foot_r"]
			phys.stand_here()
			var mo := Motion.new()
			mo.setup(p, phys, SIZE.y * 0.86, SIZE)
			mo.life = 0.0
			for i in 30:
				mo.step()
			mo.play({"id": "_angles", "phases": [{"time": 0.5, ch: {"raise": pose[0], "elbow": pose[1]}}, {"time": 4.0}]})
			for i in 150:
				mo.step()
			var c: Variant = p.chains["hand_" + ch.right(1)]
			var s: float = 1.0 if ch == "arm_r" else -1.0
			var up: float = (p.joint_position(c.b.name) - p.joint_position(c.a.name)).angle()
			var fo: float = (p.joint_position(c.end.name) - p.joint_position(c.b.name)).angle()
			var got_r: float = rad_to_deg(wrapf((PI / 2.0 - up) * s, -PI, PI))
			var got_e: float = rad_to_deg(wrapf((up - fo) * s, -PI, PI))
			var err: float = maxf(absf(wrapf(got_r - pose[0], -180.0, 180.0)), absf(wrapf(got_e - pose[1], -180.0, 180.0)))
			worst = maxf(worst, err)
			rows.append([ch, pose[0], pose[1], snappedf(got_r, 0.1), snappedf(got_e, 0.1)])
			p.queue_free()
	print("ANGLES " + JSON.stringify({"worst": snappedf(worst, 0.1), "rows": rows}))
	quit()
