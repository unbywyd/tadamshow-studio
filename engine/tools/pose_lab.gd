extends SceneTree
## THE EXPERIMENT BENCH (d:/skazki/docs/angles-experiment.md): every action of engine/pose/actions on every hero,
## played by the OLD engine (motion.gd, its action "old") and by the angles player, judged by ONE checker
## (pose/checker.gd), with pictures of both.
## usage: godot --path engine --script tools/pose_lab.gd -- --heroes=<puppet dir>,... --out=<dir> [--frames=5]
##        [--actions=a,b]   (not headless: it takes pictures)

const Puppet := preload("res://puppet.gd")
const Motion := preload("res://motion.gd")
const BodyPhysics := preload("res://body_physics.gd")
const Items := preload("res://items.gd")
const PosePlayer := preload("res://pose/pose_player.gd")
const Checker := preload("res://pose/checker.gd")
const SIZE := Vector2(720, 1280)
const FLOOR := 0.86
const HEIGHT := 0.34

var view: SubViewport
var frames := 5
var out_dir := ""
var _items: Variant = null


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	var args := {}
	for a in OS.get_cmdline_user_args():
		var kv := a.trim_prefix("--").split("=", true, 1)
		args[kv[0]] = kv[1] if kv.size() > 1 else "1"
	out_dir = args.get("out", ProjectSettings.globalize_path("res://out/pose_lab"))
	DirAccess.make_dir_recursive_absolute(out_dir)
	frames = int(args.get("frames", "5"))
	var heroes: Array = (args["heroes"] as String).split(",")
	var actions := {}
	var adir := ProjectSettings.globalize_path("res://pose/actions")
	for f in DirAccess.get_files_at(adir):
		if f.ends_with(".json"):
			var a: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(adir.path_join(f)))
			actions[a["id"]] = a
	if args.has("actions"):
		var keep := {}
		for id in (args["actions"] as String).split(","):
			keep[id] = actions[id]
		actions = keep
	var old_lib := {}
	var odir := ProjectSettings.globalize_path("res://actions")
	for f in DirAccess.get_files_at(odir):
		if f.ends_with(".json"):
			var a: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(odir.path_join(f)))
			old_lib[a["id"]] = a

	view = SubViewport.new()
	view.size = Vector2i(SIZE)
	view.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	root.add_child(view)
	var bg := ColorRect.new()
	bg.color = Color("efe8da")
	bg.size = SIZE
	view.add_child(bg)
	var ground := ColorRect.new()
	ground.color = Color("d8ccb4")
	ground.position = Vector2(0, SIZE.y * FLOOR)
	ground.size = Vector2(SIZE.x, SIZE.y * (1.0 - FLOOR))
	view.add_child(ground)

	var results := {}
	for hdir: String in heroes:
		var hero: String = _tag(hdir)
		results[hero] = {}
		for id: String in actions:
			var act: Dictionary = actions[id]
			var row := {}
			var old_id: String = act.get("old", "")
			if old_lib.has(old_id):
				row["old"] = await _run_old(hdir, hero, old_lib[old_id], act)
			row["new"] = await _run_new(hdir, hero, act)
			results[hero][id] = row
			print("LAB %s %s old=%s new=%s  (floor at: old %s, new %s)" % [hero, id, JSON.stringify(row.get("old", {}).get("faults", "-")), JSON.stringify(row["new"]["faults"]), row.get("old", {}).get("m", {}).get("floor_at", "-"), row["new"]["m"].get("floor_at", "-")])
			print("   jerk at: old %s, new %s; new length %d" % [row.get("old", {}).get("m", {}).get("jerk_at", "-"), row["new"]["m"].get("jerk_at", "-"), row["new"]["length"]])
	var f := FileAccess.open(out_dir.path_join("results.json"), FileAccess.WRITE)
	f.store_string(JSON.stringify(results, " ", false))
	f.close()
	quit()


static func _tag(dir: String) -> String:
	var parts := dir.trim_suffix("/").split("/")
	return parts[parts.size() - 2] if parts[parts.size() - 1] == "puppet" else parts[parts.size() - 1]


func _puppet(dir: String) -> Puppet:
	var p := Puppet.new()
	view.add_child(p)
	p.load_rig(dir.path_join("rig.json"), dir.path_join("parts"),
		{"foot_l": {"bend": "out", "end_mode": "level"}, "foot_r": {"bend": "out", "end_mode": "level"}})
	p.set_rivets_visible(false)
	p.scale = Vector2.ONE
	p.position = Vector2.ZERO
	p.reset_pose()
	var sole_y := -INF
	for ft: String in ["foot_l", "foot_r"]:
		sole_y = maxf(sole_y, p.point(p.rig["handles"][ft]["end"], "sole").y)
	var k: float = SIZE.y * HEIGHT / float(p.rig["body_height"])
	var root_x: float = p.body_position().x
	p.scale = Vector2.ONE * k
	p.position = Vector2(SIZE.x * 0.5 - root_x * k, SIZE.y * FLOOR - sole_y * k)
	p.reset_pose()
	return p


static func _touches(act: Dictionary) -> bool:
	if act.has("old") and false:
		return false
	var s := JSON.stringify(act.get("phases", []))
	return s.contains("\"contact\"")


# ----------------------------------------------------------------------------- the angles player

func _run_new(dir: String, hero: String, act: Dictionary) -> Dictionary:
	var info := {}
	var length := 0
	for pass_i in 2:
		var p := _puppet(dir)
		var pl := PosePlayer.new()
		pl.setup(p, SIZE.y * FLOOR)
		var item: Node2D = null
		if act.has("item"):
			item = _mug(p.body_position().x + float(act["item"].get("out", 0.55)) * pl.leg)
			pl.item = item
		var ch := Checker.new()
		ch.setup(p, SIZE.y * FLOOR, pl.arm, pl.leg)
		ch.covers_face = bool(act.get("covers_face", false))
		ch.touches = _touches(act)
		pl.play(act, {"side": "right"})
		var at := _shot_steps(length) if pass_i == 1 else []
		var n := 0
		var miss := 0.0
		while (pl.busy() or n < length) and n < 900:
			pl.step()
			ch.sample()
			n += 1
			# a contact that holds should be where it was sent (judged once its weight is full)
			for h: String in pl.contacts:
				var c: Dictionary = pl.contacts[h]
				if float(c["w"]) >= 0.999:
					var palm: Vector2 = p.parts[h].node.to_global(p.parts[h].center)
					var want: Vector2 = pl._contact_point(h)
					miss = maxf(miss, palm.distance_to(want) / maxf(pl._hand_len(p.chains[h]) * 2.0, 1.0))
			if pass_i == 1 and at.has(n):
				await _shot(hero, act["id"], "new", at.find(n))
		ch.m["miss"] = miss
		if pass_i == 0:
			length = n + 20
			info = {"faults": ch.faults(), "m": ch.m.duplicate(), "length": n}
		p.queue_free()
		if item != null:
			item.queue_free()
		await process_frame
	return info


func _mug(x: float) -> Node2D:
	var n := Node2D.new()
	var body := Polygon2D.new()
	body.polygon = PackedVector2Array([Vector2(-14, -34), Vector2(14, -34), Vector2(12, 0), Vector2(-12, 0)])
	body.color = Color("b3362c")
	n.add_child(body)
	n.position = Vector2(x, SIZE.y * FLOOR)
	view.add_child(n)
	return n


# ----------------------------------------------------------------------------- the old engine

func _run_old(dir: String, hero: String, act_old: Dictionary, act_new: Dictionary) -> Dictionary:
	var info := {}
	var length := 0
	for pass_i in 2:
		var p := _puppet(dir)
		for ft: String in ["foot_l", "foot_r"]:
			p.set_target(ft, p.handle_position(ft))
		var phys := BodyPhysics.new()
		phys.puppet = p
		phys.floor_y = SIZE.y * FLOOR
		phys.stage_width = SIZE.x
		phys.feet = ["foot_l", "foot_r"]
		phys.stand_here()
		var mo := Motion.new()
		mo.setup(p, phys, SIZE.y * FLOOR, SIZE)
		_set_items(mo, act_old)
		for i in 40:
			_step(mo)
		var ch := Checker.new()
		ch.setup(p, SIZE.y * FLOOR, mo.arm, mo.leg)
		ch.covers_face = bool(act_old.get("covers_face", false))
		var s := JSON.stringify(act_old.get("phases", []))
		ch.touches = s.contains("\"contact\":true") or s.contains("\"to\"")
		var prm := {"side": "right", "duration": 1.5}
		prm.merge(act_old.get("test", {}), true)
		mo.play(act_old, prm)
		var at := _shot_steps(length) if pass_i == 1 else []
		var n := 0
		while (mo.busy() or n < length) and n < 900:
			_step(mo)
			ch.sample()
			n += 1
			if pass_i == 1 and at.has(n):
				await _shot(hero, act_new["id"], "old", at.find(n))
		if pass_i == 0:
			length = n + 20
			info = {"faults": ch.faults(), "m": ch.m.duplicate(), "length": n}
		p.queue_free()
		if _items != null:
			_items.free_all()
			_items = null
		await process_frame
	return info


func _step(mo: Variant) -> void:
	mo.step()
	if _items != null:
		_items.step(Motion.DT)


func _set_items(mo: Variant, action: Dictionary) -> void:
	var defs: Array = action.get("test_items", [])
	if defs.is_empty():
		return
	_items = Items.new(view, SIZE.y * FLOOR, SIZE.y)
	for d: Dictionary in defs:
		var at: Array = d.get("at", [0.6, 0.0])
		var out: float = mo.floor_reach_x("arm_r") if at[0] is String and at[0] == "reach" else float(at[0]) * mo.arm
		var x: float = mo.puppet.body_position().x + out * mo._sign("arm_r")
		_items.add(d["id"], d["card"], Vector2(x, SIZE.y * FLOOR - float(at[1]) * mo.leg - 30.0), d.get("def", {}))
		for i in 40:
			_items.step(Motion.DT)
	_items.watch(mo)
	for d: Dictionary in defs:
		if d.has("held"):
			var hand: String = d["held"]
			if hand == "wear":
				_items.wear_now(mo, d["id"])
				continue
			_items.hold_now(mo, "both" if hand == "both" else "hand_" + hand.left(1), d["id"])


# ----------------------------------------------------------------------------- pictures

func _shot_steps(length: int) -> Array:
	var at: Array = []
	for i in frames:
		at.append(int(round(float(i + 1) * length / (frames + 1))))
	return at


func _shot(hero: String, id: String, engine: String, i: int) -> void:
	await RenderingServer.frame_post_draw
	await RenderingServer.frame_post_draw
	var img := view.get_texture().get_image()
	img = img.get_region(Rect2i(0, int(SIZE.y * FLOOR - 900), 720, 940))
	img.resize(360, 470, Image.INTERPOLATE_BILINEAR)
	img.save_png(out_dir.path_join("%s__%s__%s__%d.png" % [id, hero, engine, i]))
