extends SceneTree
## Plays every action on every hero and measures it: the action x hero table of docs/framework-tz.md (4.7).
## Nothing is fitted to a hero: an action that fails on one hero is a fault of the action or of the engine.
##
## usage: godot --headless --path engine --script tools/action_check.gd -- [--heroes=a,b] [--actions=a,b]
##            [--out=<file.json>] [--puppets=<folder>]
##        --puppets: the folder the heroes are in (the studio kit passes a world's heroes/: a hero is then
##        <folder>/<name>/puppet); a hero named by an absolute path is that puppet folder itself.
##        without --headless and with --shots=<dir>: also saves 6 pictures of every action on every hero
##        (tools/action_report.py makes the storyboards and the table out of them).
##        --extra-actions=<folder>: a world's own actions (actions/*.json) beside the library (a library name wins)
##        --frames=<n>: how many pictures of every action with --shots (6)
##        --pairs[=b1,b2,..]: TRANSITIONS instead: every action A is interrupted by each action B (default: PAIRS)
##        --switch=0.3,1.0 seconds into A (mid-move and mid-hold); only B and the way back are measured.
## One-sided actions are played on both sides. Each run: the hero stands, the action plays (loops last 1.5 s),
## it holds 0.5 s, then everything goes back to rest and must arrive there.

const Puppet := preload("res://puppet.gd")
const BodyPhysics := preload("res://body_physics.gd")
const Motion := preload("res://motion.gd")
const Items := preload("res://items.gd")
const SIZE := Vector2(720, 1280)
const FLOOR := 0.86
const HEIGHT := 0.34          # as heroes stand in real scenes (0.30-0.43)
## Ten heroes chosen to differ as much as the archive allows: wide and narrow, a head two thirds of the body,
## skirts to the floor, short legs, a box robot, armour.
const HEROES := ["loaf", "hag", "granny_c", "dwarf", "sumo", "lanky", "ballerina_b", "robot", "pirate_c", "knight_b"]
## What counts as a fault (docs/framework-tz.md 4.7). wrong = the longest an elbow or knee stays on the wrong side,
## in steps (3 = 0.05 s: what the eye can see); then leg lengths, hand widths,
## arm lengths, arm lengths per second squared, seconds.
const LIMITS := {"wrong": 3, "slide": 0.03, "inside": 0.15, "floor": 0.005, "miss": 0.05, "path": 1.5,
	"accel": 450.0, "out": 0.0, "face": 0.5, "back": 0.08, "balance": 0.0,
	"grab": 0.12, "nograb": 0.0, "item_floor": 0.004, "cross": 0.25,
	"skirt": 0.25, "torn": 0.10, "jerk": 0.15}
var SHOTS := 6
## A hand broken off on its way carries its speed on and may have to straighten for its elbow: in a transition its
## path may be up to twice the straight line (a single action: 1.5, LIMITS.path).
const PATH_BREAK := 2.0
## The actions that interrupt every other one in --pairs: between them they send a hand up, to the body, to the
## face, to the head, throw the body into the air and bring everything back.
const PAIRS := ["rest", "wave", "hips", "facepalm", "head_grab", "jump"]

var shots_dir := ""
var hand_shots := false          # --hand-shots: also a close picture of both hands at every shot
const HAND_BOX := 150
var shot_side := "right"        # --shot-side=left: the pictures of the left-hand run
var view: SubViewport
var puppets_root := ""          # --puppets=<folder>


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	var args := {}
	for a in OS.get_cmdline_user_args():
		var kv := a.trim_prefix("--").split("=", true, 1)
		args[kv[0]] = kv[1] if kv.size() > 1 else "1"
	var heroes: Array = (args["heroes"] as String).split(",") if args.has("heroes") else HEROES
	if args.has("hands"):                     # --hands=drawn | stump | one | none: how the hands are drawn
		Puppet.hand_style = "" if args["hands"] == "drawn" else str(args["hands"])
	if args.has("gloves"):                    # --gloves=piying_red: another shared glove set
		Puppet.glove_set = str(args["gloves"])
	if args.has("leather"):                   # --leather=0.88: lit-through leather
		Puppet.leather = float(args["leather"])
	if args.has("pins"):                      # --pins=peg: the shared wooden peg on the bends
		Puppet.pin_style = str(args["pins"])
	shots_dir = args.get("shots", "")
	puppets_root = args.get("puppets", "")
	shot_side = args.get("shot-side", "right")
	hand_shots = args.has("hand-shots")
	var out: String = args.get("out", ProjectSettings.globalize_path("res://out/actions.json"))
	if args.has("frames"):
		SHOTS = clampi(int(args["frames"]), 1, 48)
	var actions := _library(args.get("extra-actions", ""))
	if args.has("actions"):
		var keep := {}
		for id in (args["actions"] as String).split(","):
			if actions.has(id):
				keep[id] = actions[id]
		actions = keep

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

	var results: Array = []
	var started := Time.get_ticks_msec()
	var pairs: Array = []
	var switches: Array = [0.3, 1.0]
	if args.has("pairs"):
		pairs = PAIRS if args["pairs"] == "1" else Array((args["pairs"] as String).split(","))
		if args.has("switch"):
			switches = Array((args["switch"] as String).split(",")).map(func(x): return float(x))
		var all := _library(args.get("extra-actions", ""))
		for hero: String in heroes:
			var p := _hero(hero)
			if p == null:
				continue
			var view: String = p.rig.get("view", "front")
			var alone := {}
			for id: String in actions:
				if actions[id].get("view", view) != view:
					continue
				for b: String in pairs:
					if not all.has(b) or b == id or all[b].get("view", view) != view:
						continue
					if not alone.has(b):                # the action by itself, from rest: what its elbows must be
						alone[b] = (await _play(p, all[b], "right", hero))["sides"]
					for sw: float in switches:
						var r: Dictionary = await _play(p, all[b], "right", hero, actions[id], sw)
						if r["sides"] != alone[b]:
							(r["faults"] as Array).append("elbow")
						r["hero"] = hero
						r["action"] = "%s>%s@%.1f" % [id, b, sw]
						r["side"] = "right"
						results.append(r)
			p.queue_free()
			await process_frame
	for hero: String in (heroes if pairs.is_empty() else []):
		var p := _hero(hero)
		if p == null:
			push_error("no hero " + hero)
			continue
		var view: String = p.rig.get("view", "front")
		for id: String in actions:
			var a: Dictionary = actions[id]
			if a.get("view", view) != view and not (a.get("view", "") == "side" and view == "front" and not _has_profile(hero)):
				continue        # an action for another view: the stage turns the hero first (one without it: as it is)
			if a.get("low_view", "") == "side" and view in ["front", "back"] and _has_profile(hero.get_slice("/", 0)):
				continue                            # (work at the floor: the stage turns a hero with a profile to it)
			if a.get("two", false):                 # needs a second hero (receive, catch): checked on the stage
				continue
			var sides: Array = ["right", "left"] if a.get("params", {}).has("side") else ["right"]
			for side: String in sides:
				var r: Dictionary = await _play(p, a, side, hero)
				r["hero"] = hero
				r["action"] = id
				r["side"] = side
				results.append(r)
		p.queue_free()
		await process_frame
	var bad := results.filter(func(r): return not (r["faults"] as Array).is_empty())
	print("ACTIONS %d runs, %d with faults, %.1f s" % [results.size(), bad.size(), (Time.get_ticks_msec() - started) / 1000.0])
	var f := FileAccess.open(out, FileAccess.WRITE)
	f.store_string(JSON.stringify({"limits": LIMITS, "heroes": heroes, "actions": actions.keys(), "runs": results}, " "))
	f.close()
	quit(0)


## The library (engine/actions) and, beside it, a world's own actions: a library name wins (a world action may not
## stand in for a core one; `tadam check` says so as action_name_taken).
static func _library(extra: String) -> Dictionary:
	var out := {}
	for dir: String in [ProjectSettings.globalize_path("res://actions"), extra]:
		if dir.is_empty() or not DirAccess.dir_exists_absolute(dir):
			continue
		for f in DirAccess.get_files_at(dir):
			if f.ends_with(".json") and not f.ends_with(".check.json"):
				var a: Variant = JSON.parse_string(FileAccess.get_file_as_string(dir.path_join(f)))
				if a is Dictionary and a.has("id") and not out.has(a["id"]):
					out[a["id"]] = a
	return out


## A hero's name in a picture's file name: a hero given by its folder is that folder's name (heroes/<slug>/puppet ->
## <slug>), so no drive letter or slash gets into a file name.
static func _tag(hero: String) -> String:
	if not hero.is_absolute_path():
		return hero.replace("/", "-")
	var d := hero.simplify_path().trim_suffix("/")
	return d.get_base_dir().get_file() if d.get_file() == "puppet" else d.get_file()


func _has_profile(name: String) -> bool:
	return FileAccess.file_exists(_hero_dir(name).path_join("side").path_join("rig.json"))


## A hero's puppet folder: <puppets>/<name> (or <puppets>/<name>/puppet in a world folder); an absolute path is the
## folder itself; without --puppets: ../puppets next to the engine.
func _hero_dir(name: String) -> String:
	if name.is_absolute_path():
		return name.simplify_path()
	var root_dir: String = puppets_root if not puppets_root.is_empty() else ProjectSettings.globalize_path("res://").path_join("../puppets")
	var d: String = root_dir.path_join(name)
	if FileAccess.file_exists(d.path_join("puppet").path_join("rig.json")):
		d = d.path_join("puppet")
	return d.simplify_path()


func _hero(name: String) -> Puppet:
	var dir: String = _hero_dir(name)
	var p := Puppet.new()
	view.add_child(p)
	if not p.load_rig(dir.path_join("rig.json"), dir.path_join("parts"),
			{"foot_l": {"bend": "out", "end_mode": "level"}, "foot_r": {"bend": "out", "end_mode": "level"}}):
		p.queue_free()
		return null
	p.set_rivets_visible(false)
	return p


var _items: Items = null


func _step(mo: Motion) -> void:
	mo.step()
	if _items != null:
		_items.step(Motion.DT)


## The items an action is checked with ("test_items" in its file): each { "id", "card" (engine/items),
## "at": [out, up] (arm lengths out on the action's side, leg lengths above the floor), or "held": "right" | "left"
## (in that hand from the start, the action's side mirrored) }.
func _set_items(mo: Motion, action: Dictionary, side: String) -> void:
	if _items != null:
		_items.free_all()
		_items = null
	var defs: Array = action.get("test_items", [])
	if defs.is_empty():
		return
	_items = Items.new(view, SIZE.y * FLOOR, SIZE.y)
	for d: Dictionary in defs:
		var at: Array = d.get("at", [0.6, 0.0])
		var ch: String = "arm_l" if side == "left" else "arm_r"
		# ("reach": where the hero would stand to it in a scene, stage.gd: under its shoulder as it bends down)
		var out: float = mo.floor_reach_x(ch) if at[0] is String and at[0] == "reach" else float(at[0]) * mo.arm
		var x: float = mo.puppet.body_position().x + out * mo._sign(ch)
		var it: Variant = _items.add(d["id"], d["card"], Vector2(x, SIZE.y * FLOOR - float(at[1]) * mo.leg - 30.0), d.get("def", {}))
		if mo.view == "side" and str(it.def.get("hold", "")) == "both":
			it.pos.x = mo.puppet.body_position().x + mo.facing * _items.carry_out(mo, it)   # (in front of it, not in it)
		for i in 40:                          # it falls and settles where it was put
			_items.step(Motion.DT)
	_items.watch(mo)
	for d: Dictionary in defs:
		if d.has("held"):
			var hand: String = d["held"]
			if hand == "wear":
				_items.wear_now(mo, d["id"])
				continue
			if side == "left":
				hand = "left" if hand == "right" else "right"
			_items.hold_now(mo, "both" if hand == "both" else "hand_" + hand.left(1), d["id"])


static func _grabs_wanted(action: Dictionary) -> int:
	var n := 0
	for ph: Dictionary in action.get("phases", []):
		for k in ["arm_l", "arm_r", "arms"]:
			if ph.get(k, null) is Dictionary and ph[k].get("grab", false):
				n += 2 if k == "arms" else 1
	return n


## Stands the hero on the floor exactly as stage.gd does, with fresh physics and motion.
func _stand(p: Puppet) -> Motion:
	p.scale = Vector2.ONE
	p.position = Vector2.ZERO
	p.reset_pose()
	var sole_y := -INF
	for f: String in ["foot_l", "foot_r"]:
		sole_y = maxf(sole_y, p.point(p.rig["handles"][f]["end"], "sole").y)
	var floor_y := SIZE.y * FLOOR
	var k: float = SIZE.y * HEIGHT / float(p.rig["body_height"])
	var root_x: float = p.body_position().x
	p.scale = Vector2.ONE * k
	p.position = Vector2(SIZE.x * 0.5 - root_x * k, floor_y - sole_y * k)
	p.reset_pose()
	for f: String in ["foot_l", "foot_r"]:
		p.set_target(f, p.handle_position(f))
	var phys := BodyPhysics.new()
	phys.puppet = p
	phys.floor_y = floor_y
	phys.stage_width = SIZE.x
	phys.feet = ["foot_l", "foot_r"]
	phys.stand_here()
	var mo := Motion.new()
	mo.setup(p, phys, floor_y, SIZE)
	return mo


## One run: the hero stands, (the action `first` plays for `switch` seconds,) `action` plays and is measured.
func _play(p: Puppet, action: Dictionary, side: String, hero: String, first: Dictionary = {}, switch := 0.0) -> Dictionary:
	var mo := _stand(p)
	_set_items(mo, action, side)
	for i in 40:
		_step(mo)
	var home := {}
	for h in ["hand_l", "hand_r"]:
		home[h] = p.handle_position(h) - p.body_position()
	var body_y := p.body_position().y
	if not first.is_empty():
		mo.play(first, {"side": "right", "duration": 1.5})
		for i in int(switch * 60.0):
			_step(mo)
	mo.reset_measures()
	var run: Variant = mo.play(action, _test_params(action, side))
	var length := 0
	var frames: Array = []
	while mo.busy() and length < 600:
		_step(mo)
		length += 1
		frames.append(length)
	for i in 30:                                  # it holds a moment: a pose must stay put
		_step(mo)
	var m: Dictionary = mo.m.duplicate()
	# (only the arms the action moves: the other one keeps whatever pose the action before left it in)
	var moves_l := false
	var moves_r := false
	for ph: Dictionary in action.get("phases", []):
		moves_l = moves_l or ph.has("arms") or ph.has("arm_l" if side != "left" else "arm_r")
		moves_r = moves_r or ph.has("arms") or ph.has("arm_r" if side != "left" else "arm_l")
	var mo_sides: Array = []
	for e: Array in mo.side_log:
		if e[0] == action.get("id", "?"):
			mo_sides.append([e[1], e[2] if moves_l else 0.0, e[3] if moves_r else 0.0])
	var im: Dictionary = _items.m.duplicate() if _items != null else {"grab_miss": 0.0, "under": 0.0, "grabs": 0}
	# shots: replay is not needed, the run is deterministic; take them on a second pass
	var shots: Array = []
	if not shots_dir.is_empty() and side == shot_side:
		shots = await _shots(p, action, hero, length, first, switch)
	mo = mo if shots.is_empty() else _replay_end(p, action, length, first, switch)
	mo.rest_all(0.5)
	for i in 72:
		_step(mo)
	var back := 0.0
	for h in ["hand_l", "hand_r"]:
		back = maxf(back, (p.handle_position(h) - p.body_position()).distance_to(home[h]) / mo.arm)
	back = maxf(back, absf(p.body_position().y - body_y) / mo.leg)
	if _items != null and not mo.holding.is_empty():
		back = 0.0                                # (with a thing in its hands a hero does not let its arms hang)
	var steps: int = maxi(int(m["steps"]), 1)
	var path: float = m["travel"] / m["needed"] if m["needed"] > 0.3 else 1.0
	var got := {"wrong": float(m["wrong_run"]), "wrong_share": float(m["wrong"]) / steps, "slide": m["slide"], "inside": m["inside"], "floor": m["floor"],
		"miss": m["miss"], "path": path, "balance": m["balance"], "accel": m["accel"], "out": m["out"], "face": m["face"], "back": back,
		"cross": m.get("cross", 0.0), "skirt": m.get("skirt", 0.0), "torn": m.get("torn", 0.0), "jerk": m.get("jerk", 0.0), "grab": im["grab_miss"], "nograb": float(maxi(_grabs_wanted(action) - int(im["grabs"]), 0)), "item_floor": im["under"]}
	var faults: Array = []
	for k: String in LIMITS:
		var limit: float = float(LIMITS[k])
		if k == "path" and not first.is_empty():
			limit = PATH_BREAK
		if float(got[k]) > limit + 1e-6:
			faults.append(k)
	# the elbows' sides at the end of every phase of the action: the same action must give the same, whatever came
	# before it (the caller compares)
	got["sides"] = str(mo_sides)
	got["faults"] = faults
	got["seconds"] = length / 60.0
	got["shots"] = shots
	return got


## The params an action is checked with: its side, loops of 1.5 s, and what the action itself asks for in "test"
## (a walk is kept short enough to stay in the picture).
static func _test_params(action: Dictionary, side: String) -> Dictionary:
	var prm := {"side": side, "duration": 1.5}
	prm.merge(action.get("test", {}), true)
	return prm


## The same run again from the start, stopping where the measured one stopped (to go on to the return to rest).
func _replay_end(p: Puppet, action: Dictionary, length: int, first: Dictionary = {}, switch := 0.0) -> Motion:
	var mo := _stand(p)
	_set_items(mo, action, "right")
	for i in 40:
		_step(mo)
	if not first.is_empty():
		mo.play(first, {"side": "right", "duration": 1.5})
		for i in int(switch * 60.0):
			_step(mo)
	mo.play(action, _test_params(action, "right"))
	for i in length + 30:
		_step(mo)
	return mo


## Six pictures spread over the action, cut round the hero.
func _shots(p: Puppet, action: Dictionary, hero: String, length: int, first: Dictionary = {}, switch := 0.0) -> Array:
	var mo := _stand(p)
	_set_items(mo, action, shot_side)
	for i in 40:
		_step(mo)
	if not first.is_empty():
		mo.play(first, {"side": shot_side, "duration": 1.5})
		for i in int(switch * 60.0):
			_step(mo)
	mo.play(action, _test_params(action, shot_side))
	var at: Array = []
	for i in SHOTS:
		at.append(int(round(float(i + 1) * length / (SHOTS + 1))))
	var done := 0
	var files: Array = []
	for s in length:
		_step(mo)
		if done < at.size() and s + 1 == at[done]:
			await RenderingServer.frame_post_draw
			await RenderingServer.frame_post_draw
			var img := view.get_texture().get_image()
			if hand_shots:            # --hand-shots: both hands close (left of the picture, right), for the eye
				var pair := Image.create(2 * HAND_BOX, HAND_BOX, false, img.get_format())
				for k in 2:
					var c: Vector2 = p.point("hand_" + "lr"[k], "grip")
					var r := Rect2i(Vector2i(c) - Vector2i(HAND_BOX / 2, HAND_BOX / 2), Vector2i(HAND_BOX, HAND_BOX))
					r = r.intersection(Rect2i(Vector2i.ZERO, Vector2i(SIZE)))
					pair.blit_rect(img, r, Vector2i(k * HAND_BOX, 0))
				var tag_h: String = action["id"] if first.is_empty() else "%s-%s-%d" % [first["id"], action["id"], int(switch * 10)]
				pair.save_png(shots_dir.path_join("%s__%s__hand%d.png" % [tag_h, _tag(hero), done]))
			var floor_y := SIZE.y * FLOOR
			img = img.get_region(Rect2i(0, int(floor_y - 900), 720, 940))   # the whole width: thrown things too
			var tag: String = action["id"] if first.is_empty() else "%s-%s-%d" % [first["id"], action["id"], int(switch * 10)]
			var path := shots_dir.path_join("%s__%s__%d.png" % [tag, _tag(hero), done])
			img.save_png(path)
			files.append(path)
			done += 1
	return files
