extends Node2D
## A jointed puppet assembled at runtime from rig.json and a directory of part images.
##
## Every part is a plain Node2D whose origin is the joint with its parent; a joint angle is that
## node's rotation (radians inside, degrees in the API; 0 = rest pose, positive = clockwise on
## screen). Because the child node lives inside the parent node at the joint point, the two parts
## of a joint always share that point: the puppet cannot come apart.
##
## All geometry comes from the rig file (every puppet may have its own proportions); a part's box
## is only the canvas of its image. Puppet space (the local space of this node) is the assembled
## rest pose in the rig's sheet pixels. Position and scale of this node only place the puppet on
## the stage (scale = wanted height / rig.body_height), so the motion is the same at any
## on-screen size. The animator moves HANDLES, the joints follow:
##   body handle    position + lean of the root part
##   angle handles  a goal angle that the part follows on a spring
##   IK handles     a target for the END part's joint; the two bones are solved in ik.gd,
##                  or the chain is "free" and hangs and swings (springs.gd)
## Everything advances in step(): fixed 1/60 s, no randomness, no dependence on frame rate.

const IK := preload("res://ik.gd")
const Springs := preload("res://springs.gd")
const Rivet := preload("res://rivet.gd")
const Frames := preload("res://frames.gd")

const DT := 1.0 / 60.0
const POLE_DOWN := 2.4            # how steeply down the elbow line goes (its slope: 2.4 = 67 degrees)


class Part:
	var name: String
	var parent: Part              # null for the root
	var node: Node2D              # origin = the joint with the parent
	var sprite: Sprite2D
	var pivot: Vector2            # that joint in sheet coords (joint.at; origin for the root)
	var rest: Vector2             # that joint in puppet space in the rest pose
	var z := 0
	var lo := -PI                 # limits, radians
	var hi := PI
	var angle := 0.0              # joint angle, radians
	var rest_angle := 0.0         # its angle in the puppet's rest stance (rig "rest"), radians
	var skins: Dictionary = {}    # second drawings: variant name -> { texture, position }; "" = the first one
	var wear: Texture2D           # head only: what stays on over a recorded face (scarf, hat, hair), with a hole
	var back: Texture2D           # ... and the shadow inside that hole
	var hat: Texture2D            # head only: a hat worn on top of a recorded head (then nothing else is painted)
	var skin := ""                # the one shown now
	var frames: Array = []        # FRAMES of the first drawing (rig "frames", frames.gd): textures, [0] = that drawing
	var fspec: Dictionary = {}    # ... their order and speed
	var ftime := 0.0              # ... seconds played (times the speed)
	var fspeed := 1.0             # ... 1 = as the rig says, 0 = stands still
	var fnow := 0                 # ... the frame shown, from 0
	var vel := 0.0                # its velocity, rad/s
	var goal := 0.0               # angle the spring pulls to (angle handles)
	var squeeze := 1.0            # its drawing's width (a hand seen EDGE ON is the flat hand squeezed across)
	var rigid := false            # goes straight to its goal, no swing of its own (a skirt whose cloth does the swinging)
	var idle := 0.0               # share of the idle sway this part gets
	var center: Vector2           # middle of the painted pixels seen from the joint: the weight
	var painted: Rect2            # painted pixels of the image, in the part's own frame
	var edge_l := PackedFloat32Array()   # head only: per row of the image, its leftmost / rightmost painted x
	var edge_r := PackedFloat32Array()   # (part frame); row y of the image is at sprite.position.y + y
	var axis := 0.0               # direction of `center`
	var length := 100.0           # pendulum length, px
	var chain: Chain              # the IK chain this part belongs to, or null
	var slot := -1                # 0, 1 = the two bones, 2 = the end part
	var rot := 0.0                # total rotation in puppet space
	var xf := Transform2D.IDENTITY   # transform in puppet space
	var p1: Vector2               # joint position one and two steps ago (for its acceleration)
	var p2: Vector2
	var r1 := 0.0                 # parent rotation one and two steps ago
	var r2 := 0.0


class Chain:
	var a: Part                   # bone 1 (upper arm, thigh)
	var b: Part                   # bone 2 (forearm, shin)
	var end: Part                 # hand, foot
	var l1 := 0.0                 # bone lengths
	var l2 := 0.0
	var dir1 := 0.0               # rest direction of each bone in its own frame
	var dir2 := 0.0
	var target: Vector2           # puppet space, for the end part's joint
	var free := true              # not solved: hangs and swings
	var arm := false              # an arm (its root above the body's): its elbow rule is a wedge, a leg's a line
	var grab := 1.0               # 0..1, eases a caught limb into the IK pose
	var bend_mode := "out"        # "out" | "front" | "back" | "fixed"
	var pole: Vector2             # "out": the middle joint prefers this direction (puppet space)
	var side := 1.0               # the side the middle joint is on (bend sign)
	var wrong := 0                # steps in a row the middle joint has been on the side it should not be on
	var bend := 1.0               # the same, smoothed: passes through 0 (straight) when it flips
	var end_mode := "follow"      # "follow": end angle relative to bone 2; "level": in puppet space
	var end_angle := 0.0
	var sol_a := 0.0              # last IK solution, joint angles
	var sol_b := 0.0


@export var auto_step := false          ## step() from _physics_process; off when a stage drives it
@export var facing := 1                 ## -1 / +1, used by "front" / "back" bend modes
@export var idle_enabled := true
@export var idle_period := 3.6          ## seconds per breath
@export var idle_rise := 2.5            ## px the body lifts on a breath
@export var idle_angle := 1.2           ## degrees of sway on the angle-handle parts
@export var rivet_radius := 7.0
@export var gravity := 9000.0           ## px/s^2 in puppet space: a 140 px limb swings in about 0.8 s
@export var flip_time := 0.18           ## seconds an elbow takes to swing over to the other side
@export var flip_slack := 0.25          ## ...which it does at once this close to straight (share of reach)
@export var wrong_steps := 6            ## ...and, folded, after this many steps on the wrong side: never left there
@export var grab_time := 0.15           ## seconds a caught limb takes to reach the IK pose
@export var min_pendulum := 60.0        ## px, keeps short parts (hands, feet) from buzzing
@export var max_accel := 60000.0        ## px/s^2, cap on the joint acceleration fed to the springs
@export var max_spin := 30.0            ## rad/s, cap on any joint velocity

## Spring settings: stiffness, damping, gravity, inertia (see springs.gd).
var limp := Springs.Params.new(0.0, 2.2, 1.0, 0.8)        # bones of a free chain: pendulums
var limp_end := Springs.Params.new(60.0, 6.0, 1.0, 0.8)   # end part of a free chain: floppy
var held := Springs.Params.new(170.0, 9.0, 0.0, 0.35)     # everything else: wobbles, then settles

## HANDS made simple: "" (or "drawn" in a scene) = as painted (back, palm, fist, edge drawings); "one" = the painted hand only, the same in
## every pose; "stump" = the top third of the painted hand, rounded off (no fingers); "none" = no hand at all; "ball" = a round knob; "mitten" = a mitten with a thumb
## (these two drawn here); "glove" = THE SHARED GLOVES, the same drawings for every hero (_glove_hand). Drawn here, in the colour of the hero's own painted hand, ONE
## drawing for every pose: nothing is swapped, a fist and an open hand look the same, a thing held lies behind it.
static var hand_style := "stump"       # (the default since 21.11: wooden puppets need no fingers)
var rig: Dictionary = {}
var parts: Dictionary = {}       # name -> Part
var chains: Dictionary = {}      # handle name -> Chain
var order: Array[Part] = []      # parents before children, the root first
var root: Part
var body_pos := Vector2.ZERO     # body handle, puppet space
var body_lean := 0.0             # radians
var steps := 0                   # fixed steps since the last reset: the puppet's clock
var wrong_total := 0             # steps any held limb spent with its middle joint on the wrong side (a scene checks this)
var wrong_longest := 0           # the longest such run

var _idle_mix := 0.0
var _skin_held: Dictionary = {}  # part name -> true: its drawing was chosen by hand, not by the automatic rule
var _rivets: Array[Node2D] = []
var _framed: Array[Part] = []    # the parts whose drawing is frames


# ----------------------------------------------------------------------------- building

## Builds the puppet. `handle_overrides` adds settings to rig.handles (same shape as in rig.json):
##   "bend": "out" | "front" | "back" | -1 | 1     how the middle joint of an IK chain folds
##   "end_mode": "follow" | "level"                what the end part's angle is relative to
func load_rig(rig_path: String, skin_dir: String, handle_overrides: Dictionary = {}) -> bool:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(rig_path))
	if not (parsed is Dictionary and parsed.has("parts")):
		push_error("Puppet: cannot read rig '%s'" % rig_path)
		return false
	_clear()
	rig = parsed
	var defs: Dictionary = rig.get("handles", {})
	for h: String in handle_overrides:
		var def: Dictionary = defs.get(h, {})
		def.merge(handle_overrides[h], true)
		defs[h] = def
	rig["handles"] = defs
	for part_name: String in rig["parts"]:
		_build_part(part_name, skin_dir)
	# The rest stance: how this puppet stands when nothing moves it (arms a little away from the body).
	var stance: Dictionary = rig.get("rest", {})
	for part_name: String in stance:
		if parts.has(part_name):
			parts[part_name].rest_angle = deg_to_rad(stance[part_name])
	for h: String in defs:
		_build_handle(h, defs[h])
	reset_pose()
	return true


func _clear() -> void:
	for child in get_children():
		remove_child(child)
		child.queue_free()
	_unlink()
	parts.clear()
	chains.clear()
	order.clear()
	_rivets.clear()
	_framed.clear()
	root = null


## Parts and chains point at each other; cut that so they are freed with the puppet.
func _unlink() -> void:
	for p in order:
		p.chain = null


func _notification(what: int) -> void:
	if what == NOTIFICATION_PREDELETE:
		_unlink()


func _build_part(part_name: String, skin_dir: String) -> Part:
	if parts.has(part_name):
		return parts[part_name]
	var def: Dictionary = rig["parts"][part_name]
	var p := Part.new()
	p.name = part_name
	p.z = int(def.get("z", 0))
	p.node = Node2D.new()
	p.node.name = part_name
	if def.get("parent") == null:
		root = p
		p.pivot = _v2(def["origin"])
		p.rest = p.pivot
		add_child(p.node)
	else:
		p.parent = _build_part(def["parent"], skin_dir)
		var joint: Dictionary = def["joint"]
		p.pivot = _v2(joint["at"])
		# Where the joint sits in the parent's frame: parent_at seen from the parent's own pivot.
		p.node.position = _v2(joint["parent_at"]) - p.parent.pivot
		p.rest = p.parent.rest + p.node.position
		var limits: Array = def.get("limits", [-180.0, 180.0])
		p.lo = deg_to_rad(limits[0])
		p.hi = deg_to_rad(limits[1])
		p.parent.node.add_child(p.node)
	parts[part_name] = p
	order.append(p)

	# The image is the box grown by `pad`, so its pixel (0, 0) is sheet point (box.xy - pad).
	# Shift it so that the sheet point `pivot` lands on the node origin. The box is only the
	# canvas of the image: it may be much larger than the drawing and reach outside the sheet.
	var box: Array = def["box"]
	var pad: float = rig.get("pad", 0.0)
	p.sprite = Sprite2D.new()
	p.sprite.name = "skin"
	p.sprite.centered = false
	p.sprite.position = Vector2(box[0] - pad, box[1] - pad) - p.pivot
	p.sprite.z_index = p.z
	p.sprite.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
	p.sprite.self_modulate.a = leather
	p.node.add_child(p.sprite)

	# Secondary motion treats the part as a weight in the middle of what is painted (a uniform
	# rod of length L swings like a point weight at 2/3 L, i.e. 4/3 of the distance to its middle).
	p.painted = Rect2(p.sprite.position, Vector2(box[2] + 2.0 * pad, box[3] + 2.0 * pad))
	p.center = p.painted.get_center()
	var image := _load_image(skin_dir.path_join(part_name + ".png"))
	var simple: bool = hand_style != "" and part_name.begins_with("hand_")
	if image != null and simple and hand_style == "glove" and _glove_hand(p, def, image, part_name):
		return _finish_part(p, false)       # (no wooden pin at the wrist: the glove goes into the sleeve)
	if image != null and simple and hand_style in ["ball", "mitten"]:
		image = _simple_hand(image, -p.sprite.position, part_name)
	elif image != null and simple and hand_style == "stump":
		image = _stump_hand(image, -p.sprite.position)
	elif image != null and simple and hand_style == "none":
		image = Image.create(image.get_width(), image.get_height(), false, Image.FORMAT_RGBA8)   # (the arm ends at the wrist)
	# hand_style "one": the painted hand as it is, the same drawing in every pose (no palm, fist, edge)
	if image != null:
		var used := image.get_used_rect()
		p.painted = Rect2(p.sprite.position + Vector2(used.position), used.size)
		if part_name == "head":
			_measure_edges(p, image)
		p.center = p.sprite.position + _paint_center(image)
		image.generate_mipmaps()
		p.sprite.texture = ImageTexture.create_from_image(image)
	if def.has("hat"):
		var hat_image := _load_image(skin_dir.path_join(part_name + ".hat.png"))
		if hat_image != null:
			hat_image.generate_mipmaps()
			p.hat = ImageTexture.create_from_image(hat_image)
	if def.has("face"):
		for layer: String in ["wear", "back"]:
			var extra := _load_image(skin_dir.path_join("%s.%s.png" % [part_name, layer]))
			if extra != null:
				extra.generate_mipmaps()
				p.set(layer, ImageTexture.create_from_image(extra))
	# Second drawings of this part (rig "variants"): an image of its own, pinned by its own point `at`.
	p.skins[""] = {"texture": p.sprite.texture, "position": p.sprite.position}
	var variants: Dictionary = {} if simple else def.get("variants", {})
	for v: String in variants:
		var other := _load_image(skin_dir.path_join("%s.%s.png" % [part_name, v]))
		if other != null:
			other.generate_mipmaps()
			p.skins[v] = {"texture": ImageTexture.create_from_image(other),
				"position": Vector2(-pad, -pad) - _v2(variants[v]["at"])}
	# FRAMES of the first drawing (rig "frames"): <part>.f2.png ... on the same canvas, shown in turn. Not for the
	# head (a face and a mouth are put into it) and not for hands (drawn here by `hand_style`).
	if def.has("frames") and image != null and part_name != "head" and not part_name.begins_with("hand_"):
		_load_frames(p, def["frames"], skin_dir.path_join(part_name), image.get_size())
	return _finish_part(p)


func _load_frames(p: Part, def: Variant, stem: String, size: Vector2i) -> void:
	var sp: Dictionary = Frames.spec(def)
	if sp.is_empty():
		return
	var texs: Array = [p.sprite.texture]
	for k in range(2, int(sp["count"]) + 1):
		var im := _load_image("%s.f%d.png" % [stem, k])
		if im == null or im.get_size() != size:
			# (half a round would look broken: the part stays one drawing)
			push_warning("Puppet: frame %d of '%s' is missing or not the size of the first one" % [k, p.name])
			return
		im.generate_mipmaps()
		texs.append(ImageTexture.create_from_image(im))
	p.frames = texs
	p.fspec = sp
	_framed.append(p)
	_show_frame(p)


func _finish_part(p: Part, pin := true) -> Part:
	p.axis = p.center.angle()
	p.length = maxf(p.center.length() * 4.0 / 3.0, min_pendulum)

	if p.parent != null and pin:
		var rivet := Rivet.new()
		rivet.name = "rivet"
		rivet.radius = rivet_radius
		if pin_style == "peg" and not (p.name in PEG_SKIP):
			# THE SHARED WOODEN PEG on every bend (shoulders, elbows, hips, knees, ankles, the waist), as big as the
			# joint: the same picture on every hero, so the hinge reads at once
			if _peg == null:
				var pim := _load_image(PEG_FILE)
				if pim != null:
					pim.generate_mipmaps()
					_peg = ImageTexture.create_from_image(pim)
			rivet.texture = _peg
			rivet.radius = PEG_K * float(rig.get("joint_radius", 30.0))      # (one size on every bend of a hero)
		elif pin_style == "knot" and p.name != "head":
			rivet.radius = KNOT_K * float(rig.get("joint_radius", 30.0))
			rivet.fill = Color("5a3a22")
			rivet.rim = Color("24160c")
			rivet.always = true
		rivet.z_index = maxi(p.z, p.parent.z)   # on top of both parts it joins, under whatever is in front
		p.node.add_child(rivet)
		_rivets.append(rivet)
	return p


## THE SHARED GLOVES (hand_style "glove", engine/hands/glove, tools/gen_gloves.py): one set of drawings for every
## hero - the back of the hand (the first drawing), "palm", "fist", "point", "edge" - sized so that the glove is as
## long as the hero's own painted hand. Drawn for the hand on the right of the picture; hand_l is their mirror. The
## hand's helper points follow the gloves: "grip" from the fist (that is what holds), "tip" from the open hand.
## which set (a folder in engine/hands): scene "gloves": "piying_red" ("glove" = the black leather ones)
static var glove_set := "glove"
static var _gloves: Dictionary = {}
## PINS on the joints: "dot" = a small drawn disc (rivet_radius); "peg" = the shared wooden peg (engine/hands/peg.png)
## on every bend but the neck (the head sits on its stick) and the wrists (the glove goes into the sleeve)
## "knot" = the small dark knot of a shadow-theatre puppet (the thread that ties the leather pieces), shown always
static var pin_style := "dot"
const KNOT_K := 0.2               # the knot's radius: this share of the joint's
## LEATHER (scene "leather": 0.85): the skin's opacity. Below 1 the pieces are lit through like the dyed leather of a
## shadow theatre: where two overlap at a joint the overlap shows darker, and the screen's light comes through
static var leather := 1.0
const PEG_FILE := "res://hands/peg.png"
const PEG_K := 0.75               # the peg's radius: this share of the joint's
const PEG_SKIP := ["head", "hand_l", "hand_r"]
static var _peg: Texture2D = null
static var _glove_meta: Dictionary = {}
const GLOVE_FIT := 0.78           # the cuff's width: this share of the sleeve's at the wrist
const GLOVE_LEN := 1.75           # the glove's length (wrist to fingertips): at most this many sleeve widths


## How wide the forearm (the sleeve) is just above the wrist, sheet px; 0 when it cannot be measured.
func _width_at_wrist(p: Part) -> float:
	if p.parent == null or p.parent.sprite.texture == null:
		return 0.0
	var im: Image = p.parent.sprite.texture.get_image()
	if im == null:
		return 0.0
	var r: float = float(rig["parts"][p.name]["joint"].get("radius", 20.0))
	var w: Vector2 = p.node.position - p.parent.sprite.position - Vector2(0.0, 0.6 * r)
	var y := clampi(int(w.y), 0, im.get_height() - 1)
	var x0 := clampi(int(w.x), 0, im.get_width() - 1)
	if im.get_pixel(x0, y).a < 0.5:
		return 0.0
	var lo := x0
	while lo > 0 and im.get_pixel(lo - 1, y).a >= 0.5:
		lo -= 1
	var hi := x0
	while hi < im.get_width() - 1 and im.get_pixel(hi + 1, y).a >= 0.5:
		hi += 1
	return float(hi - lo + 1)


func _glove_hand(p: Part, def: Dictionary, own: Image, part_name: String) -> bool:
	if _gloves.is_empty():
		var meta: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://hands".path_join(glove_set).path_join("hands.json")))
		if not (meta is Dictionary):
			return false
		_glove_meta = meta
		for look: String in meta:
			var im := _load_image("res://hands".path_join(glove_set).path_join(look + ".png"))
			if im != null:
				_gloves[look] = {"image": im, "at": _v2(meta[look]["at"]), "grip": _v2(meta[look]["grip"]), "tip": _v2(meta[look]["tip"])}
	if not _gloves.has("back"):
		return false
	# the hero's own hand: from the wrist to the fingertips (the rig's "tip", or the painted hand's lowest point)
	var used := own.get_used_rect()
	var own_len: float = (_v2(def["tip"]) - p.pivot).length() if def.has("tip") else float(used.end.y) + p.sprite.position.y
	var back: Dictionary = _gloves["back"]
	var k: float = maxf(own_len, 10.0) / maxf((back["tip"] as Vector2).y - (back["at"] as Vector2).y, 1.0)
	# better: the cuff as wide as the sleeve (or the bare arm) at the wrist, so that it goes INTO it
	var sleeve := _width_at_wrist(p)
	if sleeve > 4.0:
		k = GLOVE_FIT * sleeve / float(_glove_meta["back"]["cuff"])
		# ...but never longer than GLOVE_LEN sleeve widths, wrist to fingertips: a set drawn with long fingers is made
		# smaller as a whole (the cuff then goes deeper into the sleeve) - long hands read as a monkey's
		var glove_len: float = (back["tip"] as Vector2).y - (back["at"] as Vector2).y
		k = minf(k, GLOVE_LEN * sleeve / maxf(glove_len, 1.0))
	# the sleeve comes down OVER the cuff: the hand under its forearm (still over the body)
	if p.parent != null:
		p.z = p.parent.z - 1
		p.sprite.z_index = p.z
	var mirror: bool = part_name.ends_with("_l")
	p.skins.clear()
	for look: String in _gloves:
		var g: Dictionary = _gloves[look]
		var im: Image = (g["image"] as Image).duplicate()
		im.resize(maxi(int(im.get_width() * k), 2), maxi(int(im.get_height() * k), 2), Image.INTERPOLATE_LANCZOS)
		var at: Vector2 = g["at"]
		if mirror:
			im.flip_x()
			at.x = float((g["image"] as Image).get_width()) - at.x
		im.generate_mipmaps()
		var skin := "" if look == "back" else look
		p.skins[skin] = {"texture": ImageTexture.create_from_image(im), "position": -at * k}
		if look == "back":
			p.sprite.texture = p.skins[""]["texture"]
			p.sprite.position = p.skins[""]["position"]
			var u := im.get_used_rect()
			p.painted = Rect2(p.sprite.position + Vector2(u.position), u.size)
			p.center = p.sprite.position + _paint_center(im)
	# the helper points in the rig follow the gloves (sheet px: from the joint)
	for key: String in ["grip", "tip"]:
		var g: Dictionary = _gloves["fist" if key == "grip" and _gloves.has("fist") else "back"]
		var off: Vector2 = ((g[key] as Vector2) - (g["at"] as Vector2)) * k
		if mirror:
			off.x = -off.x
		rig["parts"][part_name][key] = [p.pivot.x + off.x, p.pivot.y + off.y]
	return true


## Reads a part image from a file on disk or from inside the app. Inside the app the same PNG is stored as
## "<name>.png.bin", so that Godot does not convert it on export (see tools/bundle_puppets.py).
func _load_image(path: String) -> Image:
	var file := path if FileAccess.file_exists(path) else path + ".bin"
	if not FileAccess.file_exists(file):
		push_warning("Puppet: no image '%s'" % path)
		return null
	var image := Image.new()
	if image.load_png_from_buffer(FileAccess.get_file_as_bytes(file)) != OK or image.is_empty():
		return null
	image.convert(Image.FORMAT_RGBA8)
	image.fix_alpha_edges()      # no dark fringe when the part is rotated or scaled
	return image


## Middle of the painted pixels (alpha-weighted), in image pixels. Measured on a copy shrunk
## 8 times: plenty for a weight estimate and only a few thousand pixels to visit.
## The silhouette of a part row by row: where a hand at the side of the head should be.
static func _measure_edges(p: Part, image: Image) -> void:
	var im := image.duplicate() as Image
	im.convert(Image.FORMAT_RGBA8)
	var w := im.get_width()
	var h := im.get_height()
	var data := im.get_data()
	p.edge_l.resize(h)
	p.edge_r.resize(h)
	for y in h:
		var row := y * w * 4
		var l := -1
		var r := -1
		for x in w:
			if data[row + x * 4 + 3] > 128:
				l = x
				break
		for x in range(w - 1, -1, -1):
			if data[row + x * 4 + 3] > 128:
				r = x
				break
		p.edge_l[y] = p.sprite.position.x + (l if l >= 0 else w * 0.5)
		p.edge_r[y] = p.sprite.position.x + (r if r >= 0 else w * 0.5)


static func _paint_center(image: Image) -> Vector2:
	var small: Image = image.duplicate()
	var k := 1.0
	while k < 8.0 and mini(small.get_width(), small.get_height()) >= 16:
		small.shrink_x2()
		k *= 2.0
	var sum := Vector2.ZERO
	var weight := 0.0
	for y in small.get_height():
		for x in small.get_width():
			var a: float = small.get_pixel(x, y).a
			sum += Vector2(x + 0.5, y + 0.5) * a
			weight += a
	if weight <= 0.0:
		return Vector2(image.get_size()) * 0.5
	return sum / weight * k


func _build_handle(handle: String, def: Dictionary) -> void:
	if not def.has("ik"):
		var p: Part = parts.get(def.get("part", ""))
		if p != null and p != root:
			p.idle = 1.0 if p.parent == root else -0.6   # the upper part sways back a little
		return
	var bones: Array = def["ik"]
	var c := Chain.new()
	c.a = parts.get(bones[0])
	c.b = parts.get(bones[1]) if bones.size() == 2 else null
	c.end = parts.get(def.get("end", ""))
	if c.a == null or c.b == null or c.end == null or c.b.parent != c.a or c.end.parent != c.b:
		push_error("Puppet: handle '%s' is not a chain of two bones and an end part" % handle)
		return
	# A child node's position is its joint in the parent's frame, i.e. the bone vector.
	c.l1 = c.b.node.position.length()
	c.dir1 = c.b.node.position.angle()
	c.l2 = c.end.node.position.length()
	c.dir2 = c.end.node.position.angle()
	if c.l1 < 1.0 or c.l2 < 1.0:
		push_error("Puppet: handle '%s' has a bone of zero length" % handle)
		return
	var bend: Variant = def.get("bend", "out")
	if bend is String:
		c.bend_mode = bend
	else:
		c.bend_mode = "fixed"
		c.side = signf(float(bend))
	# "out": the middle joint hangs down like on a real rod puppet, leaning a little (10 deg)
	# away from the body's middle line - so an arm folded along the body puts its elbow outward.
	# Where the middle joint belongs: OUTWARD from the body, a little down. An elbow or a knee that folds
	# inward, across the body, is the one thing a limb never does.
	# ARMS (a chain whose root is above the body's root): the ray an elbow changes sides on goes out from the shoulder
	# and steeply DOWN (67 degrees under the level). A hand above it has its elbow under the shoulder-to-hand line,
	# hanging, as an arm does: held out, spread low, raised. Only an arm hanging almost straight down (at rest) has
	# its elbow on the outer side, and it gets there while nearly straight, unseen. (It used to be 17 degrees under
	# the level: every hand held out and a little down had its elbow ABOVE it, the forearm hanging from it: an arm
	# turned inside out.) The other edge of that zone is far inside above the head (IK.side_wedge).
	# LEGS keep the old line: a knee belongs outward.
	c.arm = c.a.rest.y < root.rest.y
	c.pole = Vector2(-1.0 if c.a.rest.x < root.rest.x else 1.0, POLE_DOWN if c.arm else 0.3)
	c.end_mode = def.get("end_mode", "follow")
	for i in 3:
		var p: Part = [c.a, c.b, c.end][i]
		p.chain = c
		p.slot = i
	chains[handle] = c


static func _v2(a: Array) -> Vector2:
	return Vector2(a[0], a[1])


# ----------------------------------------------------------------------------- pose (FK)

## Forward kinematics: sets one joint angle directly, clamped to the part's limits.
## (A held IK chain or a spring goal takes over again on the next step.)
func set_angle(part: String, degrees: float) -> void:
	var p: Part = parts.get(part)
	if p == null:
		return
	if p == root:
		body_lean = deg_to_rad(degrees)
	p.angle = clampf(deg_to_rad(degrees), p.lo, p.hi)
	p.goal = p.angle
	p.vel = 0.0
	_pose(false)


func get_angle(part: String) -> float:
	var p: Part = parts.get(part)
	return rad_to_deg(p.angle) if p != null else 0.0


## Rest pose: all joint angles 0, the body at the rig's origin, every target on its rest point.
func reset_pose() -> void:
	steps = 0
	_idle_mix = 0.0
	body_pos = root.pivot
	body_lean = 0.0
	for p in order:
		p.angle = p.rest_angle
		p.vel = 0.0
		p.goal = p.rest_angle
	_pose(true)
	for c: Chain in chains.values():
		c.target = c.end.xf.origin          # where the end joint is in the rest stance
		c.end_angle = 0.0
		c.grab = 1.0
		c.side = _pick_side(c, c.end.xf.origin - c.a.xf.origin, Transform2D.IDENTITY)
		c.bend = c.side


## Pushes the angles to the nodes and refreshes the puppet-space transforms.
## `still` also forgets the motion history, so a teleport does not throw the limbs.
func _pose(still: bool) -> void:
	root.angle = body_lean
	for p in order:
		var par := p.parent
		if par == null:
			p.node.position = body_pos
			p.rot = p.angle
			p.xf = Transform2D(p.angle, body_pos)
		else:
			p.rot = par.rot + p.angle
			p.xf = par.xf * Transform2D(p.angle, p.node.position)
			if still:
				p.p1 = par.xf * p.node.position
				p.p2 = p.p1
				p.r1 = par.rot
				p.r2 = par.rot
		p.node.rotation = p.angle


# ----------------------------------------------------------------------------- handles

## "body", "angle" or "ik"; "" if the rig has no such handle.
func handle_kind(handle: String) -> String:
	if chains.has(handle):
		return "ik"
	var def: Dictionary = rig.get("handles", {}).get(handle, {})
	var p: Part = parts.get(def.get("part", ""))
	if p == null:
		return ""
	return "body" if p == root else "angle"


## Body handle: world position of the root joint and the lean of the root part.
func set_body(global_pos: Vector2, lean_degrees: float) -> void:
	body_pos = to_local(global_pos)
	body_lean = deg_to_rad(lean_degrees)


func body_position() -> Vector2:
	return to_global(body_pos)


## Angle handle (chest, head): the part follows this angle on its spring.
func set_handle_angle(handle: String, degrees: float) -> void:
	var p := _handle_part(handle)
	if p != null:
		p.goal = clampf(deg_to_rad(degrees), p.lo, p.hi)


func get_handle_angle(handle: String) -> float:
	var p := _handle_part(handle)
	return rad_to_deg(p.goal) if p != null else 0.0


## Angle handle, the other way round: the angle at which the part points at a world position.
func angle_toward(handle: String, global_pos: Vector2) -> float:
	var p := _handle_part(handle)
	if p == null or p.parent == null:
		return 0.0
	var dir: float = (global_pos - p.node.global_position).angle()
	return rad_to_deg(wrapf(dir - p.axis - p.parent.node.global_rotation, -PI, PI))


## IK handle: a world target for the END part's joint (wrist, ankle). Catches a free chain.
func set_target(handle: String, global_pos: Vector2) -> void:
	var c: Chain = chains.get(handle)
	if c == null:
		return
	if c.free:
		_catch(c)
	c.target = to_local(global_pos)


## Free = not solved by IK: the chain hangs and swings. Un-freeing holds it where it is now.
func set_free(handle: String, free: bool) -> void:
	var c: Chain = chains.get(handle)
	if c == null or c.free == free:
		return
	if free:
		c.free = true
	else:
		_catch(c)
		c.target = c.end.xf.origin


## A free chain becomes held: ease into the IK pose and keep the middle joint on the side
## it happens to hang on.
func _catch(c: Chain) -> void:
	c.free = false
	c.grab = 0.0
	var bend_now: float = c.b.angle + c.dir2 - c.dir1
	if absf(bend_now) > 0.2:
		c.side = signf(bend_now)
		c.bend = c.side


func is_free(handle: String) -> bool:
	var c: Chain = chains.get(handle)
	return c == null or c.free


## Angle of the end part (hand, foot) in degrees: relative to bone 2 in "follow" mode,
## relative to the stage in "level" mode (0 = as in the rest pose, i.e. a foot flat on the floor).
func set_end_angle(handle: String, degrees: float) -> void:
	var c: Chain = chains.get(handle)
	if c != null:
		c.end_angle = deg_to_rad(degrees)


## Overrides how a chain folds: "out", "front", "back", or a fixed sign -1 / +1.
## A fixed sign is obeyed at once (the joint swings over through straight, wherever the limb is).
func set_bend(handle: String, bend: Variant) -> void:
	var c: Chain = chains.get(handle)
	if c == null:
		return
	if bend is String:
		c.bend_mode = bend
	else:
		c.bend_mode = "fixed"
		c.side = signf(float(bend))


## Where a handle is right now, in world coords: the root joint, the centre of an angle part,
## or the end part's joint of a chain (the actual one, not the target).
func handle_position(handle: String) -> Vector2:
	var c: Chain = chains.get(handle)
	if c != null:
		return c.end.node.global_position
	var p := _handle_part(handle)
	if p == null:
		return global_position
	return p.node.global_position if p == root else p.node.to_global(p.center)


func target_position(handle: String) -> Vector2:
	var c: Chain = chains.get(handle)
	return to_global(c.target) if c != null else handle_position(handle)


## World position of a part's joint with its parent.
func joint_position(part: String) -> Vector2:
	var p: Part = parts.get(part)
	return p.node.global_position if p != null else global_position


## World position of a helper point of a part: "grip", "tip", "sole", "face.center"...
func point(part: String, key: String) -> Vector2:
	var p: Part = parts.get(part)
	return p.node.to_global(point_offset(part, key)) if p != null else global_position


## The same helper point seen from the part's own joint, in sheet px, for the part at angle 0.
func point_offset(part: String, key: String) -> Vector2:
	var p: Part = parts.get(part)
	if p == null:
		return Vector2.ZERO
	var value: Variant = rig["parts"][part]
	for k in key.split("."):
		value = value.get(k) if value is Dictionary else null
	return _v2(value) - p.pivot if value is Array else Vector2.ZERO


## What is actually painted, as a rectangle in puppet space for the REST pose. Use it (not the
## boxes of the rig, which are only canvases) to frame the puppet.
func painted_rect() -> Rect2:
	var rect := Rect2(root.rest, Vector2.ZERO)
	for p in order:
		rect = rect.merge(Rect2(p.rest + p.painted.position, p.painted.size))
	return rect


func set_rivets_visible(on: bool) -> void:
	for r in _rivets:
		r.visible = on or r.get("texture") != null or r.get("always")   # (pegs and knots are part of the look)


func _handle_part(handle: String) -> Part:
	var def: Dictionary = rig.get("handles", {}).get(handle, {})
	return parts.get(def.get("part", ""))


# ----------------------------------------------------------------------------- simulation

func _physics_process(_delta: float) -> void:
	if auto_step:
		step()


## One fixed step of 1/60 s: body -> every joint, parents first.
func step() -> void:
	if root == null:
		return
	steps += 1
	# Idle layer: a breath lifts the body a little and sways the angle-handle parts.
	_idle_mix = move_toward(_idle_mix, 1.0 if idle_enabled else 0.0, DT / 0.5)
	var phase: float = TAU * steps * DT / idle_period
	var breath: float = _idle_mix * 0.5 * (1.0 - cos(phase))
	var sway: float = _idle_mix * deg_to_rad(idle_angle) * sin(phase)

	var pos := body_pos + Vector2(0.0, -idle_rise * breath)
	root.angle = body_lean
	root.rot = body_lean
	root.xf = Transform2D(body_lean, pos)
	root.node.position = pos
	root.node.rotation = body_lean
	for i in range(1, order.size()):
		_step_part(order[i], sway)
	_auto_skins()
	for p: Part in _framed:
		p.ftime += DT * p.fspeed
		_show_frame(p)


## A hand with no fingers, in the painted hand's own colour (`hand_style`): it hangs from the wrist `wrist` (image
## px) the way the painted hand did, as wide as it was.
func _simple_hand(src: Image, wrist: Vector2, part_name: String) -> Image:
	src.convert(Image.FORMAT_RGBA8)
	var used := src.get_used_rect()
	var cols: Array = []
	for y in range(used.position.y, used.end.y, 2):
		for x in range(used.position.x, used.end.x, 2):
			var c := src.get_pixel(x, y)
			if c.a > 0.9:
				cols.append(c)
	if cols.is_empty():
		return src
	# the median colour, channel by channel (the ink of the outline and the highlights do not count)
	var med := Color(0, 0, 0, 1)
	for ch in 3:
		var vals: Array = cols.map(func(c: Color) -> float: return c[ch])
		vals.sort()
		med[ch] = vals[vals.size() / 2]
	var mid: Vector2 = Vector2(used.get_center())
	var d: Vector2 = (mid - wrist).normalized() if mid.distance_to(wrist) > 1.0 else Vector2(0, 1)
	var long: float = maxf(used.size.x, used.size.y)
	var wide: float = minf(used.size.x, used.size.y)
	var out := Image.create(src.get_width(), src.get_height(), false, Image.FORMAT_RGBA8)
	var side: float = 1.0 if part_name.ends_with("l") else -1.0       # the thumb towards the body (seen from the front)
	var n := Vector2(-d.y, d.x) * side
	for y in src.get_height():
		for x in src.get_width():
			var q := Vector2(x + 0.5, y + 0.5)
			var dist: float
			if hand_style == "mitten":
				var r: float = wide * 0.46
				var a: Vector2 = wrist + d * r * 0.8
				var b: Vector2 = wrist + d * maxf(long * 0.72 - r, r * 0.9)
				var t: float = clampf((q - a).dot(b - a) / maxf((b - a).length_squared(), 1e-6), 0.0, 1.0)
				dist = q.distance_to(a + (b - a) * t) - r
				var thumb: Vector2 = wrist + d * r * 1.1 + n * r * 0.95
				dist = minf(dist, q.distance_to(thumb) - r * 0.42)
			else:
				var rb: float = wide * 0.5
				dist = q.distance_to(wrist + d * rb * 0.9) - rb
			var alpha: float = clampf(0.5 - dist, 0.0, 1.0)
			if alpha > 0.0:
				out.set_pixel(x, y, Color(med.r, med.g, med.b, alpha))
	return out


## A STUMP: the top of the hero's own painted hand, from the wrist about a third of its length, the end rounded off.
## Its colours, texture and ink stay the hero's; no fingers. (A sleeve with nothing out of it, where the painted
## forearm is all sleeve, gets its wrist this way too.)
func _stump_hand(src: Image, wrist: Vector2) -> Image:
	src.convert(Image.FORMAT_RGBA8)
	var used := src.get_used_rect()
	var mid: Vector2 = Vector2(used.get_center())
	var d: Vector2 = (mid - wrist).normalized() if mid.distance_to(wrist) > 1.0 else Vector2(0, 1)
	var long: float = maxf(used.size.x, used.size.y)
	var wide: float = minf(used.size.x, used.size.y)
	var r: float = wide * 0.42
	var cut: float = maxf(long * 0.3, r * 1.35)
	var cap: Vector2 = wrist + d * (cut - r)
	var out := Image.create(src.get_width(), src.get_height(), false, Image.FORMAT_RGBA8)
	for y in src.get_height():
		for x in src.get_width():
			var c := src.get_pixel(x, y)
			if c.a <= 0.0:
				continue
			var q := Vector2(x + 0.5, y + 0.5)
			var along: float = (q - wrist).dot(d)
			var keep := 1.0
			if along > cut - r:
				keep = clampf(r + 0.5 - q.distance_to(cap), 0.0, 1.0)     # the rounded end
			if keep > 0.0:
				out.set_pixel(x, y, Color(c.r, c.g, c.b, c.a * keep))
	return out


## Shows the drawing `variant` of a part ("" = the first one). With `hold` the automatic choice leaves it alone
## until set_skin(part, "", false) or release_skin(part).
func set_skin(part: String, variant: String, hold := true) -> void:
	var p: Part = parts.get(part)
	if p == null or not p.skins.has(variant):
		return
	if hold:
		_skin_held[part] = true
	if p.skin != variant:
		p.skin = variant
		p.sprite.texture = p.skins[variant]["texture"]
		p.sprite.position = p.skins[variant]["position"]
		_apply_squeeze(p)


## Squeezes a part's drawing across (1 = as drawn), about its joint: a flat hand at 0.4 of its width reads as a
## hand turned edge on (clapping, pressed to the side of a box). No drawing of its own is needed.
func set_squeeze(part: String, k: float) -> void:
	var p: Part = parts.get(part)
	if p == null or is_equal_approx(p.squeeze, k):
		return
	p.squeeze = k
	_apply_squeeze(p)


func _apply_squeeze(p: Part) -> void:
	p.sprite.scale.x = p.squeeze
	p.sprite.position.x = (p.skins[p.skin]["position"] as Vector2).x * p.squeeze


func release_skin(part: String) -> void:
	_skin_held.erase(part)


# ----------------------------------------------------------------------------- frames

## The frame of a part's first drawing that its time asks for. While the part shows another drawing (a variant)
## the frames go on unseen: it comes back to the frame of that moment.
func _show_frame(p: Part) -> void:
	var i: int = Frames.at(p.fspec, p.ftime)
	if i == p.fnow:
		return
	p.fnow = i
	p.skins[""]["texture"] = p.frames[i]
	if p.skin == "":
		p.sprite.texture = p.frames[i]


## The parts whose drawing is frames (rig "frames"), parents first.
func framed_parts() -> Array[String]:
	var out: Array[String] = []
	for p: Part in _framed:
		out.append(p.name)
	return out


## The frame a part shows now, from 1 (0: its drawing is one picture).
func frame_of(part: String) -> int:
	var p: Part = parts.get(part)
	return 0 if p == null or p.frames.is_empty() else p.fnow + 1


## How fast a part's frames go: 1 = as its rig says, 0 = they stand still, 2 = twice as fast.
func set_frames_speed(part: String, k: float) -> void:
	var p: Part = parts.get(part)
	if p != null and not p.frames.is_empty():
		p.fspeed = clampf(k, 0.0, 8.0)


## The frames' clock of every part another puppet of the same hero has too (a turn puts in the drawing of another
## view: its frames go on from where the old view's were, at the same speed).
func take_frames(from: Variant) -> void:
	if from == null or from == self:
		return
	for q: Part in _framed:
		var o: Part = from.parts.get(q.name)
		if o != null and not o.frames.is_empty():
			q.ftime = o.ftime
			q.fspeed = o.fspeed
			_show_frame(q)


## A part's frames from the first one again (a "once" round plays once more).
func restart_frames(part: String) -> void:
	var p: Part = parts.get(part)
	if p != null and not p.frames.is_empty():
		p.ftime = 0.0
		_show_frame(p)


## The automatic choice of drawings. One rule so far: a hand held clearly higher than its elbow shows its palm,
## and turns back when it is clearly lower (two thresholds, so it does not flicker at the border).
func _auto_skins() -> void:
	for c: Chain in chains.values():
		var hand := c.end
		if not hand.skins.has("palm") or _skin_held.has(hand.name):
			continue
		var arm: Vector2 = hand.xf.origin - c.b.xf.origin      # elbow -> wrist, puppet space
		if arm.length() < 1.0:
			continue
		var up: float = -arm.y / arm.length()
		if up > 0.35:
			set_skin(hand.name, "palm", false)
		elif up < 0.15:
			set_skin(hand.name, "", false)


func _step_part(p: Part, sway: float) -> void:
	var par := p.parent
	# How the joint and the parent moved: accelerations by finite differences over the last steps.
	var joint: Vector2 = par.xf * p.node.position
	var acc: Vector2 = ((joint - p.p1 * 2.0 + p.p2) / (DT * DT)).limit_length(max_accel)
	var rot_acc: float = (par.rot - p.r1 * 2.0 + p.r2) / (DT * DT)
	p.p2 = p.p1
	p.p1 = joint
	p.r2 = p.r1
	p.r1 = par.rot

	var c := p.chain
	if c != null and not c.free:
		# Held chain: the joints go where the IK solution says.
		if p.slot == 0:
			_solve(c, par.xf, joint)
		var want: float = c.sol_a
		if p.slot == 1:
			want = c.sol_b
		elif p.slot == 2:
			want = c.end_angle if c.end_mode == "follow" else _nearest(c.end_angle - par.rot, p)
		var before: float = p.angle
		p.angle += (want - p.angle) * c.grab
		p.vel = wrapf(p.angle - before, -PI, PI) / DT   # so a released limb keeps its swing
	else:
		# Free chain: pendulum. Anything else: a spring to its goal that the body's motion shakes.
		var prm: Springs.Params = held
		var pull := Vector2(0.0, gravity)
		if c != null:
			prm = limp_end if p.slot == 2 else limp
			# A free limb hangs the way the rest stance holds it, not straight down: "down" is turned by the
			# rest angle of the chain's first bone, so a let-go arm settles a little away from the body.
			pull = pull.rotated(c.a.rest_angle)
		if p.rigid:
			p.angle = p.goal
			p.vel = 0.0
		else:
			var s: Vector2 = Springs.step(p.angle, p.vel, p.goal + sway * p.idle, prm,
					par.rot + p.angle + p.axis, p.length, acc, rot_acc, pull, DT)
			p.angle = s.x
			p.vel = s.y

	# Limits always hold; a part that hits its stop loses most of its speed.
	if p.angle < p.lo or p.angle > p.hi:
		p.angle = clampf(p.angle, p.lo, p.hi)
		p.vel *= -0.2
	p.vel = clampf(p.vel, -max_spin, max_spin)
	p.node.rotation = p.angle
	p.rot = par.rot + p.angle
	p.xf = par.xf * Transform2D(p.angle, p.node.position)


## Two-bone IK for a held chain. `parent_xf` is the frame the first bone hangs in,
## `shoulder` the chain's root joint in puppet space.
func _solve(c: Chain, parent_xf: Transform2D, shoulder: Vector2) -> void:
	c.grab = minf(c.grab + DT / grab_time, 1.0)
	# Target relative to the root joint, in the parent's frame (where bone 1's angle is measured).
	var t: Vector2 = parent_xf.basis_xform_inv(c.target - shoulder)
	# Like a real hinge, the middle joint can get to the other side only through "straight".
	# That throws the end past its target by (l1 + l2 - d), so it is done only while that is
	# small; a folded limb keeps its side until it is stretched out again.
	var reach: float = c.l1 + c.l2
	var wish: float = _pick_side(c, t, parent_xf)
	if wish == c.side:
		c.wrong = 0
	else:
		# Nearly straight, the joint swings over at once. Folded, it is given a moment (the hand may be on its
		# way through), and then it swings over all the same: a joint is never LEFT on the wrong side, whatever
		# moved the hand there. Hands that travel on arcs around the shoulder never get this far.
		if reach - t.length() <= flip_slack * reach:      # nearly straight: over at once, as meant
			c.side = wish
			c.wrong = 0
		else:
			c.wrong += 1
			wrong_total += 1
			wrong_longest = maxi(wrong_longest, c.wrong)
			if c.wrong > wrong_steps:
				c.side = wish
				c.wrong = 0
	c.bend = move_toward(c.bend, c.side, 2.0 * DT / flip_time)
	# bend = angle between the bone directions; the joint angle differs by the rest angle between them.
	var twist: float = c.dir2 - c.dir1
	var s: Vector2 = IK.solve(t, c.l1, c.l2, c.bend, c.b.lo + twist, c.b.hi + twist)
	c.sol_a = _nearest(s.x - c.dir1, c.a)
	c.sol_b = clampf(s.y - twist, c.b.lo, c.b.hi)


## Which way the middle joint should fold for a target `t` (relative to the chain's root
## joint, in the frame `parent_xf` of the chain's parent).
func _pick_side(c: Chain, t: Vector2, parent_xf: Transform2D) -> float:
	var rest_aim: Vector2 = c.end.rest - c.a.rest
	match c.bend_mode:
		"out":    # re-picked while moving: the outer of the two places the joint could be
			if c.arm:
				return IK.side_wedge(t, parent_xf.basis_xform_inv(c.pole), c.side, signf(c.pole.x))
			return IK.side_toward(t, parent_xf.basis_xform_inv(c.pole), c.side, 0.12)
		"down":   # ...the lower of them: a hand at its own chin, chest or face has its elbow down, not up like a wing
			return IK.side_toward(t, parent_xf.basis_xform_inv(Vector2(0.0, 1.0)), c.side, 0.12)
		"front":  # the middle joint points where the puppet faces (decided on the rest pose)
			return IK.side_toward(rest_aim, Vector2(facing, 0.0), c.side)
		"back":   # ...or the opposite way
			return IK.side_toward(rest_aim, Vector2(-facing, 0.0), c.side)
	return c.side


## The same direction as `angle` (any multiple of 360 deg away) that is closest to where the
## part is now and inside its limits. Keeps joints from spinning the long way round.
func _nearest(angle: float, p: Part) -> float:
	var a: float = p.angle + wrapf(angle - p.angle, -PI, PI)
	if a > p.hi and a - TAU >= p.lo:
		a -= TAU
	elif a < p.lo and a + TAU <= p.hi:
		a += TAU
	return clampf(a, p.lo, p.hi)
