extends RefCounted
## THINGS in a scene: they lie, fall, bounce and tip over; a hero takes one in a fist (or two), carries it, gives
## it to another hero, puts it down, throws it.
##
## An item is a picture and a card (engine/items/<id>.png and <id>.json, or a scene's own):
##   { "id": "mug", "title": "кружка", "size": 0.045, "hold": "keep", "grip": [0.92, 0.42], "bounce": 0.2 }
##     size   its longest side, share of the stage height (things do not grow with the hero who holds them)
##     grip   where a fist holds it, shares of the picture (x from the left, y from the top)
##     hold   how it is held:  "hand"  it goes on from the fist, turning with it (a shovel, a sword: the picture
##                                   is drawn upright, its working end at the top, and points where the fingers do)
##                             "keep"  it stays as it is drawn, whatever the arm does (a mug, a book, a lantern)
##                             "level" a long thing held lying (a sword held across, a plank)
##                             "both"  two fists on its sides, it hangs between them and tilts with them
##                                     (a crate, a log, a steering wheel: the hands turn it). "carry": [x, y] is
##                                     where it is carried, arm lengths from between the shoulders: the hands
##                                     stay on its sides there whenever no action moves them
##                             "palm"  too big and round for a fist (a ball): it lies in front of the open
##                                     hand, the hand behind it
##                             a number: degrees, the way it is drawn turned this much (an umbrella over the head)
##     hands  "edge": held with flat hands turned edge on (the sides of a crate), not with fists
##     bounce how much of its speed it keeps when it hits the floor (a ball 0.6, a crate 0.1)
##     heavy  true: lifted slowly, the hero strains (actions read it as the param "heavy")
##     fit    its size by the HERO who has it, not by the stage: its longest side is this many of the hero's arm
##            lengths ("fit_by": "shoulder": shares of the height of its shoulders over the floor). An instrument
##            is made for the hands of whoever plays it: a dwarf's guitar is smaller than a giant's.
##     spots  named points of the picture (shares) an action sends a hand to: { "to": "@guitar", "on": "strum" }
##     bellows [from, to]: shares of the picture's width that stretch and squeeze between the two hands (an
##            accordion); the ends keep their drawing
## INSTRUMENTS and other things WORN ("hold": "wear"): not in a hand, on the body. "wear" in the card says where:
##   { "on": "belly", "dx": -0.3, "dy": -0.2, "rot": 60, "over": "chest" }   its grip on that place of the body
##       (a landmark of motion.gd: chest, belly, mouth, ...; dx, dy halves of that place's box), turned "rot"
##       degrees from upright and with the body; drawn just over the part "over" (and under the arms)
##   { "on": "floor", "dx": 0.25, "rot": -8 }    standing on the floor beside the hero (a double bass): dx arm
##       lengths to the right of its body, its grip (the foot of it) on the floor
##   { "spots": { "strum": ["arm_l", 0.15, 0.75], "fret": ["arm_r", 0.5, 0.35] } }   BY TWO SPOTS: each spot of the
##       picture is put where that hand reaches, [out, down] arm lengths from its shoulder (or ["floor", dx]: on the
##       floor, dx arm lengths to the right of the body); its size and its slant follow. So a guitar fits a loaf
##       and a beanpole alike, and both hands always reach their places on it (sized once, as it is put on)
## The hands are free to play on it: wear_now(), and "to": "@id" with "on": a spot.
##
## A fist is painted closed, from outside: the item lies BEHIND it, so it looks as if it passes through.
## The motion layer knows items only as POINTS: an arm goes { "to": "@mug" } (motion.points), and a phase that
## ends with "grab": true in that arm takes what it went to; "release": true lets it go (it falls from there),
## "throw": [out, up] lets it go with the hand's speed plus this (arm lengths a second). Items reads those as
## events of the motions it watches; one item in two heroes' hands goes to whoever took it last (giving).
##
## DEPTH (a scene with a ground, engine/space.gd): every hero is drawn on its own canvas layer, shown smaller the
## deeper it stands. A thing on the floor has its own layer at its own depth (`z`); a thing in a hand is drawn on the
## layer of the hero that holds it (so it is sorted with the hand), and when it is let go it stays at that hero's
## depth. Its position is always in the frame of the layer it is on; `world` (the stage) moves points between them.

const GRAVITY := 2900.0       # stage px / s^2 (a hero 0.34 of the stage is about 1.5 m)
const BLEND := 0.12           # seconds a taken item takes to settle into the fist
const REST_SPEED := 30.0      # px/s: slower than this on the floor, it lies still
const WALL := 30.0            # px from the side of the stage

class Item:
	var id := ""
	var def: Dictionary = {}
	var node: Sprite2D
	var px := Vector2.ONE           # picture size, px of the texture
	var k := 1.0                    # texture px -> stage px
	var grip := Vector2(0.5, 0.5)   # share of the picture
	var pos := Vector2.ZERO         # world: where the grip point is
	var rot := 0.0
	var turn := 1.0                 # 1 = as drawn, -1 = mirrored about its grip (its bulk on the other side of the fist)
	var vel := Vector2.ZERO
	var spin := 0.0
	var holder: Object = null       # the motion (hero) that holds it
	var hands: Array = []           # "hand_r", ... (two for "both")
	var blend := 1.0                # 0 -> 1 while settling into the fist
	var from_pos := Vector2.ZERO
	var from_rot := 0.0
	var resting := false
	var last_fist := Vector2.ZERO   # for the hand's speed (throwing)
	var fist_vel := Vector2.ZERO
	var z_free := 70
	var z := 0.0                    # depth on the ground (frame px) while it is free
	var own: Node = null            # its own layer while it is free (a scene with depth)
	var wearer: Object = null       # the motion (hero) that wears it ("hold": "wear")
	var stretch := 1.0              # bellows: how far they are drawn out (1 = as drawn)
	var parts: Array = []           # bellows: the sprites of the stretching middle and of the far end
	var wear_k := 0.0               # worn by two spots: its size, worked out as it is put on


var items: Dictionary = {}           # id -> Item
var layer: Node
var floor_y := 1100.0
var stage_h := 1280.0
var stage_w := 720.0
var watched: Array = []              # [motion, events seen]
var m := {"grab_miss": 0.0, "under": 0.0, "grabs": 0, "throws": 0, "caught": 0}
var catching: Array = []             # [motion, hand, steps left]: hands open for a thing flying at them
var world: Object = null             # the stage, for depth: layer_of(mo), z_of(mo), item_layer(it), move_point(p, from, to)
const CATCH_REACH := 0.45            # arm lengths from the fist a flying thing is caught at


func _init(on: Node, floor_at: float, stage_height: float) -> void:
	layer = on
	floor_y = floor_at
	stage_h = stage_height
	stage_w = stage_height * 9.0 / 16.0


## Loads an item card and picture (a path without extension, or an id from engine/items) and puts it at `at`
## (world, where its grip is; it falls from there if it is in the air).
func add(id: String, card: String, at: Vector2, extra: Dictionary = {}) -> Item:
	var base: String = card if card.contains("/") else "res://items/" + card
	var def: Dictionary = {}
	if FileAccess.file_exists(base + ".json"):
		def = JSON.parse_string(FileAccess.get_file_as_string(base + ".json"))
	def.merge(extra, true)
	var img := Image.load_from_file(ProjectSettings.globalize_path(base + ".png"))
	var it := Item.new()
	it.id = id
	it.def = def
	it.px = Vector2(img.get_size())
	it.k = float(def.get("size", 0.06)) * stage_h / maxf(it.px.x, it.px.y)
	var g: Array = def.get("grip", [0.5, 0.5])
	it.grip = Vector2(g[0], g[1])
	it.node = Sprite2D.new()
	it.node.texture = ImageTexture.create_from_image(img)
	it.node.centered = false
	it.node.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
	it.node.scale = Vector2.ONE * it.k
	it.z_free = int(def.get("z", 70))
	it.node.z_index = it.z_free
	it.z = float(extra.get("ground_z", 0.0))
	if world != null:
		world.item_layer(it).add_child(it.node)
	else:
		layer.add_child(it.node)
	it.pos = at
	items[id] = it
	_draw(it)
	for w: Array in watched:                 # heroes already on the stage can reach for it too
		_point(w[0], id)
	return it


## Takes an item off the stage (out of a hand if it is held).
func remove(id: String) -> void:
	if not items.has(id):
		return
	var it: Item = items[id]
	if it.holder != null:
		_let_go(it)
	it.wearer = null
	it.node.queue_free()
	items.erase(id)
	for w: Array in watched:
		w[0].points.erase("@" + id)


## Lets a hero reach for items (its motion.points) and act on them (its events).
func watch(mo: Object) -> void:
	watched.append([mo, mo.events.size()])
	for id: String in items:
		_point(mo, id)


func _point(mo: Object, id: String) -> void:
	mo.points["@" + id] = func(ch: String, spec: Dictionary) -> Vector2: return grip_world(id, mo, ch, spec)


## Where a hand of this hero takes the item: its grip, or for an item held with both hands the side towards
## that hand (and for a wheel, "turn" degrees round its rim).
func grip_world(id: String, mo: Object, ch: String, spec: Dictionary = {}) -> Vector2:
	var it: Item = items[id]
	if spec.has("on"):
		# a named spot of it (or [x, y] shares of its picture): where a hand plays on an instrument
		var on: Variant = spec["on"]
		var share: Variant = it.def.get("spots", {}).get(on, null) if on is String else on
		if share is Array:
			return _to(mo, it, _local_to_world(it, Vector2(share[0], share[1])))
	if it.holder != null and it.holder != mo:
		# held out by another hero: taken by its middle (or the far end of a long thing), not out of its fist
		return _to(mo, it, _local_to_world(it, Vector2(0.5, 0.5) if str(it.def.get("hold", "keep")) != "hand" else Vector2(0.5, 0.25)))
	if str(it.def.get("hold", "keep")) != "both":
		return _to(mo, it, _local_to_world(it, it.grip))
	var body: Vector2 = mo.puppet.body_position()
	var shoulder: Vector2 = mo._shoulder_at(ch, body)
	var centre: Vector2 = _to(mo, it, _local_to_world(it, Vector2(0.5, it.grip.y)))
	var rot: float = it.rot
	if spec.has("carry"):
		# where the action wants the ITEM (arm lengths from between the shoulders): the hands go to its sides there
		var c: Array = spec["carry"]
		var mid: Vector2 = (mo._shoulder_at("arm_l", body) + mo._shoulder_at("arm_r", body)) * 0.5
		centre = mid + Vector2(float(c[0]) * (mo.facing if mo.view == "side" else 1.0), float(c[1])) * mo.arm
		rot = 0.0
	if mo.view == "side":
		# in profile both hands are on its near side, one over the other: the near one in front of it, the far
		# one behind it (_z); carried, it is in front of the belly, not in it
		if spec.has("carry"):
			centre.x = mo.puppet.body_position().x + mo.facing * maxf(float(spec["carry"][0]) * mo.arm, carry_out(mo, it))
		return centre
	var half: float = 0.5 * it.px.x * it.k * float(it.def.get("span", 0.9))
	var side: float = signf(shoulder.x - centre.x)
	if side == 0.0:
		side = 1.0 if ch == "arm_l" else -1.0
	var off := Vector2(side * half, 0.0).rotated(rot + deg_to_rad(float(spec.get("turn", 0.0))))
	return centre + off


func step(dt: float) -> void:
	for w: Array in watched:
		var mo: Object = w[0]
		var ev: Array = mo.events
		for i in range(w[1], ev.size()):
			var e: Array = ev[i]
			if e.size() >= 4:
				_event(mo, e)
		w[1] = ev.size()
	for c: Array in catching:
		c[2] -= 1
	catching = catching.filter(func(c: Array) -> bool: return c[2] > 0)
	for it: Item in items.values():
		if it.holder == null and not it.resting and it.vel.length() > 300.0:     # (only a thing flying through the air)
			for c: Array in catching:
				var mo: Object = c[0]
				if mo.holding.has(c[1]):
					continue
				var centre: Vector2 = _to(mo, it, _local_to_world(it, Vector2(0.5, 0.5)))
				if _fist(mo, c[1]).distance_to(centre) < CATCH_REACH * mo.arm:
					_event(mo, [0, "catch", "grab", "arm_" + c[1].right(1), "@" + it.id])
					m["caught"] += 1
					break
	for it: Item in items.values():
		if it.wearer != null:
			_worn(it)
		elif it.holder != null:
			_held(it, dt)
		else:
			_fall(it, dt)
	_apart()
	for it: Item in items.values():
		_draw(it)
		if it.wearer != null and _stands(it):
			continue                    # (a double bass stands on its spike; the corners of its picture are air)
		var low: float = _lowest(it)
		if low > floor_y + 2.0:
			m["under"] = maxf(m["under"], (low - floor_y) / stage_h)


func _event(mo: Object, e: Array) -> void:
	var kind: String = e[2]
	var ch: String = e[3]
	var hand: String = "hand_" + ch.right(1)
	match kind:
		"grab":
			var target: String = str(e[4])
			if not target.begins_with("@") or not items.has(target.substr(1)):
				return
			var it: Item = items[target.substr(1)]
			var fist: Vector2 = _fist(mo, hand)
			m["grab_miss"] = maxf(m["grab_miss"], fist.distance_to(grip_world(it.id, mo, ch)) / mo.arm)
			m["grabs"] += 1
			if it.holder != null and it.holder != mo:
				_let_go(it)                         # given: the other hero opens its hand
			if it.holder != mo:
				_move(it, mo)                       # onto the layer of the hero that takes it
			if it.holder == mo:
				if not it.hands.has(hand):
					it.hands.append(hand)
			else:
				it.holder = mo
				it.hands = [hand]
				it.from_pos = it.pos
				it.from_rot = it.rot
				it.blend = 0.0
				it.last_fist = fist
				it.fist_vel = Vector2.ZERO
			_close_hand(mo, hand, it)
			it.node.z_index = _z(mo, hand, it)
			_carry(it)
		"catch":
			catching.append([mo, hand, int(float(e[4]) * 60.0) + 20])
		"release", "throw":
			for it: Item in items.values():
				if it.holder == mo and it.hands.has(hand):
					var v: Vector2 = it.fist_vel
					if kind == "throw":
						var add: Array = e[4] if e.size() > 4 and e[4] is Array else [0.0, 0.0]
						v += Vector2(float(add[0]) * mo._sign(ch), -float(add[1])) * mo.arm
						m["throws"] += 1
						if mo.throw_at is Vector2:
							v = _ballistic(it.pos, mo.throw_at)    # at someone: it flies there on an arc
							mo.throw_at = null
					_let_go(it)
					it.vel = v
					it.spin = clampf(v.x * 0.004, -12.0, 12.0)


## Puts an item straight into a hero's fist (a scene that starts with it held).
func hold_now(mo: Object, hand: String, id: String) -> void:
	var it: Item = items[id]
	if it.holder != null:
		_let_go(it)
	it.wearer = null
	_fit(it, mo)
	_move(it, mo)
	it.holder = mo
	it.hands = ["hand_l", "hand_r"] if hand == "both" or str(it.def.get("hold", "")) == "both" else [hand]
	for h2: String in it.hands:
		_close_hand(mo, h2, it)
	_carry(it)
	it.blend = 1.0
	it.last_fist = _fist(mo, it.hands[0])
	it.node.z_index = _z(mo, it.hands[0], it)
	_held(it, 1.0 / 60.0)
	_draw(it)


## Puts an item ON a hero ("hold": "wear": an instrument on its strap, a pipe at the mouth, a double bass beside it).
## The hands stay free to play on it.
func wear_now(mo: Object, id: String) -> void:
	var it: Item = items[id]
	if it.holder != null:
		_let_go(it)
	_fit(it, mo)
	_move(it, mo)
	it.wearer = mo
	it.wear_k = 0.0
	it.resting = false
	it.vel = Vector2.ZERO
	it.node.z_index = _wear_z(mo, it)
	_worn(it)
	_draw(it)


## What this hero wears (an item id), or "".
func worn_by(mo: Object) -> String:
	for it: Item in items.values():
		if it.wearer == mo:
			return it.id
	return ""


## Its size by the hero who has it ("fit" in the card).
func _fit(it: Item, mo: Object) -> void:
	if not it.def.has("fit"):
		return
	var unit: float = mo.arm
	if it.def.get("fit_by", "arm") == "shoulder":
		unit = maxf(float(mo.floor_y) - mo._shoulder_at("arm_r", mo.puppet.body_position()).y, mo.arm)
	it.k = float(it.def["fit"]) * unit / maxf(it.px.x, it.px.y)


## Just over the part the card says (the chest: in front of the body), under the arms that play on it.
func _wear_z(mo: Object, it: Item) -> int:
	var w: Dictionary = it.def.get("wear", {})
	var part: Object = mo.puppet.parts.get(str(w.get("over", "chest")))
	return (part.z if part != null else 40) + 1


## A worn thing that stands on the floor by the hero (one of its spots is put on the floor: a double bass).
func _stands(it: Item) -> bool:
	var w: Dictionary = it.def.get("wear", {})
	if str(w.get("on", "")) == "floor":
		return true
	for t: Variant in w.get("spots", {}).values():
		if t is Array and str(t[0]) == "floor":
			return true
	return false


## Where a spot of a worn thing goes: [arm, out, down] arm lengths from that arm's shoulder, or ["floor", dx].
func _wear_target(mo: Object, t: Array) -> Vector2:
	var body: Vector2 = mo.puppet.body_position()
	if str(t[0]) == "floor":
		return Vector2(body.x + float(t[1]) * mo.arm, float(mo.floor_y))
	var ch: String = str(t[0])
	return mo._shoulder_at(ch, body) + Vector2(float(t[1]) * mo._sign(ch), float(t[2])) * mo.arm


## Worn: on its place of the body, turned with it (or standing on the floor beside the hero).
func _worn(it: Item) -> void:
	var mo: Object = it.wearer
	var w: Dictionary = it.def.get("wear", {})
	var on: String = str(w.get("on", "belly"))
	var flip: float = signf(mo.puppet.scale.x) if mo.puppet.scale.x != 0.0 else 1.0
	if w.has("spots"):
		var names: Array = w["spots"].keys()
		var at: Array = []
		var pic: Array = []
		for n: String in names:
			at.append(_wear_target(mo, w["spots"][n]))
			var sp: Array = it.def.get("spots", {}).get(n, [0.5, 0.5]) if n != "grip" else [it.grip.x, it.grip.y]
			pic.append(Vector2((float(sp[0]) - it.grip.x) * it.px.x, (float(sp[1]) - it.grip.y) * it.px.y))
		var d_pic: Vector2 = pic[1] - pic[0]
		var d_at: Vector2 = at[1] - at[0]
		if it.wear_k <= 0.0:
			it.wear_k = d_at.length() / maxf(d_pic.length(), 1.0)
			# (but not past "fit": [least, most] arm lengths its longest side may be - a wide loaf's guitar is not
			# a sofa, a thin hero's not a toy)
			var fr: Variant = w.get("fit", null)
			if fr is Array:
				var longest: float = maxf(it.px.x, it.px.y)
				it.wear_k = clampf(it.wear_k * longest, float(fr[0]) * mo.arm, float(fr[1]) * mo.arm) / longest
		it.k = it.wear_k
		# its slant: from one spot to the other, or as the card says ("rot": a drum stays level)
		it.rot = d_at.angle() - d_pic.angle() if not w.has("rot") else deg_to_rad(float(w["rot"]))
		# where it is: as near both places as it can be at that size and slant
		it.pos = (at[0] - (pic[0] * it.k).rotated(it.rot) + at[1] - (pic[1] * it.k).rotated(it.rot)) * 0.5
		# hung on the body, it never goes into the floor (a drum on a dwarf): it rides up, and the hands with it
		if not _stands(it):
			_draw(it)
			it.pos.y -= maxf(_lowest(it) - (float(mo.floor_y) - 2.0), 0.0)
		it.turn = 1.0
		it.vel = Vector2.ZERO
		return
	if on == "floor":
		var body: Vector2 = mo.puppet.body_position()
		it.pos = Vector2(body.x + float(w.get("dx", 0.0)) * mo.arm * flip, float(mo.floor_y))
		it.rot = deg_to_rad(float(w.get("rot", 0.0))) * flip
	else:
		var lm: Array = mo._lm(on)
		var part: Object = mo.puppet.parts[lm[0]]
		var box: Rect2 = mo._face(part) if lm[3] in ["face", "edge"] else part.painted
		var local: Vector2 = box.get_center() + Vector2((float(lm[1]) + float(w.get("dx", 0.0))) * box.size.x * 0.5,
				(float(lm[2]) + float(w.get("dy", 0.0))) * box.size.y * 0.5)
		it.pos = part.node.to_global(local)
		if OS.has_environment("WEAR_DEBUG"):
			print("WEAR %s on=%s part=%s box=%s local=%s pos=%s k=%.3f px=%s" % [it.id, on, lm[0], str(box), str(local), str(it.pos), it.k, str(it.px)])
		it.rot = part.node.global_rotation * flip + deg_to_rad(float(w.get("rot", 0.0))) * flip
	it.turn = flip
	it.vel = Vector2.ZERO


## A point of the item's frame (the layer it is on) in the frame of hero `mo` (the same unless they stand at
## different depths).
func _to(mo: Object, it: Item, p: Vector2) -> Vector2:
	if world == null:
		return p
	return world.move_point(p, it.node.get_parent(), world.layer_of(mo))


## The item goes over onto the layer of hero `mo` (its numbers into that frame: it does not move on the screen).
func _move(it: Item, mo: Object) -> void:
	if world != null:
		_move_to(it, world.layer_of(mo))


func _move_to(it: Item, to: Node) -> void:
	var from: Node = it.node.get_parent()
	if to == null or from == to:
		return
	it.pos = world.move_point(it.pos, from, to)
	it.from_pos = world.move_point(it.from_pos, from, to)
	it.last_fist = world.move_point(it.last_fist, from, to)
	it.node.reparent(to, false)


func free_all() -> void:
	for it: Item in items.values():
		it.node.queue_free()
	items.clear()


## The speed that sends a thing from `a` to `b` on an arc (a higher arc the farther it goes).
func _ballistic(a: Vector2, b: Vector2) -> Vector2:
	var t: float = clampf(0.45 + absf(b.x - a.x) / 1400.0, 0.45, 1.1)
	return Vector2((b.x - a.x) / t, (b.y - a.y - 0.5 * GRAVITY * t * t) / t)


## Moves what one motion of a hero held over to its new motion (the hero turned: another view, another puppet).
func rebind(old: Object, mo: Object) -> void:
	for it: Item in items.values():
		if it.wearer == old:
			it.wearer = mo
			it.node.z_index = _wear_z(mo, it)
		if it.holder == old:
			it.holder = mo
			for hand: String in it.hands:
				_close_hand(mo, hand, it)
			it.node.z_index = _z(mo, it.hands[0], it)
			_carry(it)
	for c: Array in catching:
		if c[0] == old:
			c[0] = mo
	watch(mo)


## Which hand of this hero holds something ("hand_r" / "hand_l"), or "".
func held_by(mo: Object) -> String:
	for it: Item in items.values():
		if it.holder == mo:
			return it.hands[0]
	return ""


func _let_go(it: Item) -> void:
	var mo: Object = it.holder
	for hand: String in it.hands:
		mo.holding.erase(hand)
		mo.hold_low.erase(hand)
		mo.carry_spec.erase("arm_" + hand.right(1))
		mo.puppet.release_skin(hand)
		var ch: String = "arm_" + hand.right(1)
		var look: String = mo.chans[ch].now.get("look", "auto")
		if look == "auto" or look == "fist":
			mo.puppet.set_skin(hand, "", false)
	it.holder = null
	it.hands = []
	it.resting = false
	it.node.z_index = it.z_free
	if world != null:
		# it stays where it was let go: at that hero's depth, on its own layer again
		it.z = world.z_of(mo)
		_move_to(it, world.item_layer(it))


## Held: in the fist (behind it), turned the way it is held.
func _held(it: Item, dt: float) -> void:
	var mo: Object = it.holder
	var hold: Variant = it.def.get("hold", "keep")
	var fist: Vector2 = _fist(mo, it.hands[0])
	it.fist_vel = (fist - it.last_fist) / dt
	it.last_fist = fist
	var want_pos := fist
	var want_rot := 0.0
	var outward: float = signf(fist.x - mo.puppet.body_position().x)
	if mo.view == "side":
		outward = mo.facing
	if outward == 0.0:
		outward = 1.0
	if hold is String and hold == "both" and it.hands.size() >= 2:
		var other: Vector2 = _fist(mo, it.hands[1])
		var d: Vector2 = other - fist
		if d.x < 0.0:
			d = -d
		# (in profile the two fists are on one spot, one over the other: the line between them says nothing)
		want_rot = atan2(d.y, d.x) if mo.view != "side" else 0.0
		if it.def.has("bellows") and mo.view != "side":
			# the bellows take up the distance between the hands (the ends keep their size)
			var bw: Array = it.def["bellows"]
			var drawn: float = it.px.x * it.k * float(it.def.get("span", 0.9))
			var mid_w: float = (float(bw[1]) - float(bw[0])) * it.px.x * it.k
			it.stretch = clampf(1.0 + (d.length() - drawn) / maxf(mid_w, 1.0), 0.45, 2.2)
		# the grip line's middle is between the fists
		want_pos = (fist + other) * 0.5
		var mid := Vector2(0.5, it.grip.y)
		want_pos -= (Vector2((mid.x - it.grip.x) * it.px.x, (mid.y - it.grip.y) * it.px.y) * it.k).rotated(want_rot)
	elif hold is String and hold == "palm":
		var palm: Object = mo.puppet.parts[it.hands[0]]
		want_pos = palm.node.to_global(palm.center * 1.15)       # on the middle of the open hand
	elif hold is String and hold == "hand":
		var hand: Object = mo.puppet.parts[it.hands[0]]
		var fingers: Vector2 = (hand.node.global_transform.basis_xform(Vector2(0.0, 1.0))).normalized()
		want_rot = atan2(fingers.x, -fingers.y)
	elif hold is String and hold == "level":
		want_rot = PI * 0.5 * outward
	elif hold is float or hold is int:
		want_rot = deg_to_rad(float(hold)) * outward
	# the bulk of a thing held at its edge (a mug by its handle) is on the hand's outer side, off the body
	# ...but brought to the face (the hand above the shoulders: drinking, a phone at the ear) it turns its bulk
	# TO the head: the mug is between the fist and the mouth, not on the far side of the fist. It turns over in the
	# hand (through edge on), it does not jump.
	var shoulder_y: float = mo._shoulder_at("arm_" + (it.hands[0] as String).right(1), mo.puppet.body_position()).y
	var bulk_to: float = -outward if fist.y < shoulder_y - 0.05 * mo.arm else outward
	var mirrored: bool = (it.grip.x - 0.5) * bulk_to > 0.0 and not (hold is String and hold in ["hand", "level", "palm"])
	# (just taken, still on its way into the fist, it is simply the right way round at once: turning over through
	# edge on there squeezed a mug lying the other way into a thin strip under the hand)
	it.turn = (-1.0 if mirrored else 1.0) if it.blend < 1.0 else move_toward(it.turn, -1.0 if mirrored else 1.0, dt / 0.09)
	# what is held does not go into the floor either: a long thing (a sword, a shovel hanging from the hand) turns
	# up about the fist as its end meets the floor; a thing hanging under the fist (a mug) holds the hand up
	if hold is String and hold == "hand":
		want_rot = _off_floor(it, want_pos, want_rot, outward)
	else:
		var low := 0.0
		for c: Vector2 in _corners_at(it, want_pos, want_rot):
			low = maxf(low, c.y - fist.y)
		for hand: String in it.hands:
			mo.hold_low[hand] = low
	if it.blend < 1.0:
		it.blend = minf(it.blend + dt / BLEND, 1.0)
		var u: float = smoothstep(0.0, 1.0, it.blend)
		it.pos = it.from_pos.lerp(want_pos, u)
		it.rot = lerp_angle(it.from_rot, want_rot, u)
	else:
		it.pos = want_pos
		it.rot = want_rot
	# held, it is never drawn in the floor (a fist a pixel low as it closes on a crate standing there)
	if hold is not String or hold != "hand":
		var under: float = 0.0
		for c: Vector2 in _corners_at(it, it.pos, it.rot):
			under = maxf(under, c.y - floor_y)
		it.pos.y -= under
	it.vel = it.fist_vel


## Free: falls, hits the floor, bounces, slides to a stop, tips over onto a side.
func _fall(it: Item, dt: float) -> void:
	if it.resting:
		return
	it.vel.y += GRAVITY * dt
	it.pos += it.vel * dt
	it.rot += it.spin * dt
	# the sides of the stage are walls: a thing bounces back off them instead of flying out of the picture
	var centre_x: float = _local_to_world(it, Vector2(0.5, 0.5)).x
	if (centre_x < WALL and it.vel.x < 0.0) or (centre_x > stage_w - WALL and it.vel.x > 0.0):
		it.vel.x = -it.vel.x * 0.5
	var corners: Array = _corners(it)
	var low := -INF
	var at := Vector2.ZERO
	for c: Vector2 in corners:
		if c.y > low:
			low = c.y
			at = c
	if low < floor_y:
		return
	it.pos.y -= low - floor_y
	var bounce: float = float(it.def.get("bounce", 0.2))
	if it.vel.y > 0.0:
		it.vel.y = -it.vel.y * bounce if it.vel.y > 200.0 else 0.0
	var round_thing: bool = bool(it.def.get("round", false))
	if round_thing:
		# rolls, and the floor slows it down
		it.vel.x *= 0.985
		it.spin = it.vel.x / maxf(0.5 * it.px.x * it.k, 1.0)
		if absf(it.vel.x) < REST_SPEED and absf(it.vel.y) < REST_SPEED:
			_settle(it, false)
		return
	it.vel.x *= 0.85
	# what it stands on: every corner down at the floor. Two of them (it stands on a side): it is still. One: it
	# tips about that corner the way its middle hangs, and falls onto the nearest side
	var support: Array = []
	for c: Vector2 in _corners(it):
		if c.y >= low - 1.5:
			support.append(c)
	var flat: float = snappedf(it.rot, PI * 0.5)
	if support.size() >= 2 or absf(flat - it.rot) < 0.01:
		it.spin = 0.0
		it.rot = flat
		if absf(it.vel.x) < REST_SPEED and absf(it.vel.y) < REST_SPEED:
			_settle(it, true)
		return
	var centre: Vector2 = _local_to_world(it, Vector2(0.5, 0.5))
	var r: float = maxf(centre.distance_to(at), 1.0)
	# gravity's turn about the corner, and the air and the floor taking some of it
	it.spin += GRAVITY * (centre.x - at.x) / (r * r) * dt
	it.spin *= 0.97


## Lies still where it is (flat on a side, or a round thing anywhere), exactly on the floor.
func _settle(it: Item, square: bool) -> void:
	if square:
		it.rot = snappedf(it.rot, PI * 0.5)
	it.vel = Vector2.ZERO
	it.spin = 0.0
	it.resting = true
	_draw(it)
	it.pos.y -= _lowest(it) - floor_y
	_draw(it)


## Things on the floor do not go into each other: two that overlap are pushed apart along the floor (the moving
## one gives way, and a rolling ball bounces off).
func _apart() -> void:
	var free: Array = items.values().filter(func(i: Item) -> bool: return i.holder == null and i.wearer == null)
	for a in range(free.size()):
		for b in range(a + 1, free.size()):
			var p: Item = free[a]
			var q: Item = free[b]
			if absf(p.z - q.z) > 6.0:         # one behind the other in depth: they do not meet
				continue
			var rp: Rect2 = _box(p)
			var rq: Rect2 = _box(q)
			if not rp.intersects(rq):
				continue
			var over: float = minf(rp.end.x, rq.end.x) - maxf(rp.position.x, rq.position.x)
			var dir: float = 1.0 if rq.get_center().x >= rp.get_center().x else -1.0
			var wp: float = 0.0 if p.resting and not q.resting else (1.0 if q.resting and not p.resting else 0.5)
			p.pos.x -= dir * over * wp
			q.pos.x += dir * over * (1.0 - wp)
			for it: Item in [p, q]:
				if absf(it.vel.x) > REST_SPEED:
					it.vel.x = -it.vel.x * 0.5
				_draw(it)


## The item's outline on the stage, shrunk a little (pictures have soft edges).
func _box(it: Item) -> Rect2:
	var c: Array = _corners(it)
	var r := Rect2(c[0], Vector2.ZERO)
	for v: Vector2 in c:
		r = r.expand(v)
	return r.grow(-0.08 * minf(r.size.x, r.size.y))


func _draw(it: Item) -> void:
	# (mirrored about its grip by a negative width; passing through edge on as it turns over)
	it.node.offset = -Vector2(it.grip.x * it.px.x, it.grip.y * it.px.y)
	var wide: float = signf(it.turn) * maxf(absf(it.turn), 0.06) if it.turn != 0.0 else 0.06
	it.node.scale = Vector2(it.k * wide, it.k)
	it.node.position = it.pos
	it.node.rotation = it.rot
	if it.def.has("bellows"):
		_draw_bellows(it)


## An accordion: its left end as drawn, the bellows drawn out (or squeezed) `stretch` times, its right end moved
## over by as much; all of it about the middle, where it is held.
func _draw_bellows(it: Item) -> void:
	var bw: Array = it.def["bellows"]
	var w: float = it.px.x
	var h: float = it.px.y
	var l: float = float(bw[0]) * w
	var m: float = (float(bw[1]) - float(bw[0])) * w
	var r: float = w - l - m
	if it.parts.is_empty():
		for i in 2:
			var sp := Sprite2D.new()
			sp.texture = it.node.texture
			sp.centered = false
			sp.region_enabled = true
			sp.texture_filter = it.node.texture_filter
			it.node.add_child(sp)
			it.parts.append(sp)
		it.node.region_enabled = true
	var grow: float = m * (it.stretch - 1.0)
	var top_left: Vector2 = -Vector2(it.grip.x * w + grow * 0.5, it.grip.y * h)
	it.node.region_rect = Rect2(0.0, 0.0, l, h)
	it.node.offset = top_left
	var mid: Sprite2D = it.parts[0]
	mid.region_rect = Rect2(l, 0.0, m, h)
	mid.position = top_left + Vector2(l, 0.0)
	mid.scale = Vector2(it.stretch, 1.0)
	var end: Sprite2D = it.parts[1]
	end.region_rect = Rect2(l + m, 0.0, r, h)
	end.position = top_left + Vector2(l + m * it.stretch, 0.0)


## A point of the picture (shares) in the world, as the item lies now.
func _local_to_world(it: Item, share: Vector2) -> Vector2:
	var side: float = -1.0 if it.turn < 0.0 else 1.0
	return it.pos + (Vector2((share.x - it.grip.x) * it.px.x * side, (share.y - it.grip.y) * it.px.y) * it.k).rotated(it.rot)


## The turn nearest to `rot` at which no corner is under the floor, turning the far end up and outward.
func _off_floor(it: Item, at: Vector2, rot: float, outward: float) -> float:
	var r := rot
	for i in 36:
		var low := -INF
		for c: Vector2 in _corners_at(it, at, r):
			low = maxf(low, c.y)
		if low <= floor_y - 2.0:
			return r
		r += deg_to_rad(5.0) * outward * signf(cos(r) + 1e-3)
	return r


func _corners_at(it: Item, at: Vector2, rot: float) -> Array:
	var keep_pos := it.pos
	var keep_rot := it.rot
	it.pos = at
	it.rot = rot
	var c: Array = _corners(it)
	it.pos = keep_pos
	it.rot = keep_rot
	return c


func _corners(it: Item) -> Array:
	return [_local_to_world(it, Vector2(0, 0)), _local_to_world(it, Vector2(1, 0)),
			_local_to_world(it, Vector2(1, 1)), _local_to_world(it, Vector2(0, 1))]


func _lowest(it: Item) -> float:
	var low := -INF
	for c: Vector2 in _corners(it):
		low = maxf(low, c.y)
	return low


## The middle of a closed fist, world (or of the open hand if it has no fist drawing).
func _fist(mo: Object, hand: String) -> Vector2:
	var p: Object = mo.puppet.parts[hand]
	var sk: Dictionary = p.skins.get("fist", {})
	if sk.is_empty():
		return p.node.to_global(p.center)
	var tex: Texture2D = sk["texture"]
	return p.node.to_global(sk["position"] + tex.get_size() * Vector2(0.5, 0.55))


## Behind the fist and its forearm, in front of the body; a thing on the palm: in front of the hand. A thing in both
## hands in profile: behind the NEAR arm (the far one is behind it).
func _z(mo: Object, hand: String, it: Item = null) -> int:
	if it != null and it.def.get("hold", "") is String and it.def.get("hold", "") == "palm":
		return mo.puppet.parts[hand].z + 1
	if it != null and mo.view == "side" and it.def.get("hold", "") is String and it.def.get("hold", "") == "both":
		var near := -1000
		for s2 in ["l", "r"]:
			var f2: Object = mo.puppet.parts.get("forearm_" + s2)
			if f2 != null:
				near = maxi(near, f2.z)
		if near > -1000:
			return near - 1
	var fore: Object = mo.puppet.parts.get("forearm_" + hand.right(1))
	return (fore.z if fore != null else mo.puppet.parts[hand].z) - 1


## How far in front of the body's point a thing held in both hands is carried in profile (to its middle): clear of
## the belly by a little, and its own half width.
func carry_out(mo: Object, it: Item) -> float:
	return float(mo.front) + 0.5 * it.px.x * it.k + 0.04 * mo.arm


## The hand takes hold: a fist round a handle, an open hand behind a thing held on the palm.
func _close_hand(mo: Object, hand: String, it: Item) -> void:
	if it.def.get("hold", "") is String and it.def.get("hold", "") == "palm":
		mo.holding[hand] = "open"
		mo.puppet.release_skin(hand)
		mo.puppet.set_skin(hand, "", false)
	elif it.def.get("hands", "") == "edge":
		mo.holding[hand] = "edge"                # flat hands on its sides (a crate), turned edge on
		mo.puppet.set_skin(hand, "")
	else:
		mo.holding[hand] = true
		mo.puppet.set_skin(hand, "fist")


## A thing held with both hands: the hero's free hands stay on its sides where it is carried.
func _carry(it: Item) -> void:
	if it.holder == null or not (it.def.get("hold", "") is String and it.def.get("hold", "") == "both") or it.hands.size() < 2:
		return
	var place: Array = it.def.get("carry", [0.0, 0.9])
	for hand: String in it.hands:
		it.holder.carry_spec["arm_" + hand.right(1)] = {"to": "@" + it.id, "carry": place}
