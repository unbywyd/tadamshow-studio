extends RefCounted
## FRAMES: a drawing that is several drawings shown in turn (docs: mechanics-tz 6b). The same record for a puppet's
## part (rig.json parts.<name>), a set piece (set.json pieces[i]) and an item (its card):
##   "frames": {"count": 4, "fps": 8, "mode": "loop", "offset": 0.25}
##     count   2..16 frames. Frame 1 is the drawing itself (skirt.png); the others lie beside it: skirt.f2.png ...
##             skirt.f4.png, every one THE SAME SIZE as the first, so they share its joint and nothing jumps
##     fps     frames a second (0.5..30, default 8): every drawing has its own
##     mode    "loop" 1 2 3 4 1 2 ... (default) · "pingpong" 1 2 3 4 3 2 1 ... · "once" up to the last and stays
##     offset  the share of the round it starts at (0..1), so that two drawings do not tick together
##     order   instead of mode: its own order with holds, e.g. a blink [1, 1, 1, 1, 1, 1, 1, 2, 3, 2]
## Nothing is random and nothing depends on the frame rate: the frame shown is a function of the time played
## (steps of 1/60 s, times the speed), so a scene films the same frame for frame and a seek lands on the same one.

const MAX := 16
const MAX_ORDER := 64


## The record made ready: {"seq": [frame indices from 0], "fps", "once", "start" (a place in seq)}, or {} when it
## asks for nothing (fewer than 2 frames).
static func spec(def: Variant) -> Dictionary:
	if not (def is Dictionary):
		return {}
	var n: int = clampi(int(def.get("count", 0)), 0, MAX)
	if n < 2:
		return {}
	var seq := PackedInt32Array()
	var mode: String = str(def.get("mode", "loop"))
	if def.get("order") is Array and not (def["order"] as Array).is_empty():
		for v: Variant in (def["order"] as Array).slice(0, MAX_ORDER):
			seq.append(clampi(int(v) - 1, 0, n - 1))
	else:
		for i in n:
			seq.append(i)
		if mode == "pingpong":
			for i in range(n - 2, 0, -1):
				seq.append(i)
	return {"count": n, "seq": seq, "fps": clampf(float(def.get("fps", 8.0)), 0.5, 30.0), "once": mode == "once",
		"start": clampf(float(def.get("offset", 0.0)), 0.0, 1.0) * seq.size()}


## The frame (from 0) after `t` seconds of play.
static func at(sp: Dictionary, t: float) -> int:
	return Reel.index(sp, t)


## The files of frames 2..count beside the first one: "dir/skirt.png" -> ["dir/skirt.f2.png", ...].
static func files(first: String, count: int) -> PackedStringArray:
	var out := PackedStringArray()
	var stem: String = first.get_basename()
	var ext: String = first.get_extension()
	for k in range(2, count + 1):
		out.append("%s.f%d.%s" % [stem, k, ext])
	return out


## Frames 2..count as images, each checked against the first one's size. A frame that is missing or of another
## size takes the whole record away (the drawing stays one picture) and says why: half a round would look broken.
static func load_images(first: String, size: Vector2i, count: int) -> Array:
	var out: Array = []
	for f: String in files(first, count):
		var path: String = ProjectSettings.globalize_path(f) if f.begins_with("res://") else f
		if not FileAccess.file_exists(path):
			push_warning("frames: no %s, the drawing stays one picture" % f)
			return []
		var im := Image.load_from_file(path)
		if im == null or im.get_size() != size:
			push_warning("frames: %s is not %dx%d as the first frame, the drawing stays one picture" % [f, size.x, size.y])
			return []
		if im.get_format() != Image.FORMAT_RGBA8:
			im.convert(Image.FORMAT_RGBA8)
		out.append(im)
	return out


## A sprite that plays its frames by itself (a set piece, an item): stepped once a stage step.
class Reel:
	var sprite: Sprite2D
	var textures: Array = []      # [0] = the first drawing
	var sp: Dictionary = {}
	var time := 0.0               # seconds played (times the speed)
	var speed := 1.0              # 1 = as its record says, 0 = stands still
	var now := 0                  # the frame shown, from 0

	func step(dt: float) -> void:
		time += dt * speed
		show()

	## (the sum lives here: a class inside a script cannot call the script's own functions)
	static func index(of: Dictionary, t: float) -> int:
		var seq: PackedInt32Array = of["seq"]
		# (a hair over, so that a frame's border falling exactly on a step does not depend on float rounding)
		var pos: int = int(floor(float(of["start"]) + maxf(t, 0.0) * float(of["fps"]) + 1e-4))
		if of["once"]:
			return seq[mini(pos, seq.size() - 1)]
		return seq[pos % seq.size()]

	func show() -> void:
		var i: int = index(sp, time)
		if i != now:
			now = i
			sprite.texture = textures[i]

	func restart() -> void:
		time = 0.0
		show()


## A reel for `sprite`, which shows the first drawing (`first`, read from the file `path`), by the record `def`;
## null when the record asks for nothing or a frame cannot be used.
static func reel(sprite: Sprite2D, path: String, first: Image, def: Variant) -> Reel:
	var sp: Dictionary = spec(def)
	if sp.is_empty() or first == null:
		return null
	var images: Array = load_images(path, first.get_size(), int(sp["count"]))
	if images.is_empty():
		return null
	var r := Reel.new()
	r.sprite = sprite
	r.sp = sp
	r.textures = [sprite.texture]
	for im: Image in images:
		r.textures.append(ImageTexture.create_from_image(im))
	r.show()
	return r
