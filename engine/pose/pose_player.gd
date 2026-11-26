extends RefCounted
## THE ANGLES PLAYER (experiment, docs: d:/skazki/docs/angles-experiment.md). What an action writes is what the
## screen shows: a pose is joint ANGLES, a move between poses eases them, and only four things are done for the
## author, each one visible in the data:
##   1. a CONTACT (a hand to a named place on THIS hero's body, or to a thing) is reached by two-bone IK, its elbow
##      on the side the contact names (chosen once, when the contact starts: never re-guessed);
##   2. planted FEET stay on their spots on the floor (two-bone IK on the legs, knees out);
##   3. nothing goes under the FLOOR: if it would, the whole body is lifted (that is how a hero sits on the floor);
##      a skirt hangs plumb (until the body lies down: then it goes with it);
##   4. every joint stays inside its LIMITS.
## The old puppet.gd only loads and draws the hero; it is never stepped.
##
## A contact's "else": another place for a body that cannot reach the first (a short arm and a high forehead).
## A contact's "elbow": "pose" (default: the side the arm's pose of that phase bends to, so a pose and its contact
## never disagree) or "out" | "in" | "down" | "up" (the candidate elbow lying most that way, chosen once).
##
## Angles (degrees, written for the RIGHT side; "side": "left" mirrors), the same numbers on every body:
##   arm_r / arm_l / arms: raise (0 hanging, 90 out level, 180 straight up, < 0 across the body), elbow (0 straight,
##                         + the forearm turns on the way the arm rises: up when the arm is out, - the other way),
##                         wrist, hand: "palm" | "fist" | "back" | "edge" | "point" (the drawing)
##   leg_r / leg_l / legs: hip (0 down, + out), knee (+ the shin turns further out, - back in) - only when the feet
##                         are not planted ("feet": "free"); a negative knee is a knee bent OUT
##   (arms are measured from the chest, legs from the pelvis: a body that tilts takes them along)
##   body: tilt (+ the top toward the action's side), chest, shift (leg lengths aside), drop (leg lengths down),
##         lift (leg lengths up)        head: a tilt, or {tilt, drop (shares of the head's height)}
##   shoulder_r / shoulders: arm lengths the shoulder is raised (a shrug)
## A phase: time, ease (inout | out | in | linear), pose {...} (unnamed joints hold), contact {hand_r: {to, dx, dy,
## elbow}, hand_l, hands; "free" lets go}, feet ("planted" | "free"), foot_r / foot_l: [aside, up] leg lengths
## from its spot, swing {"arm_r.elbow": {amp, rate}}, "pose": "rest" = everything back.

const Puppet := preload("res://puppet.gd")
const DT := 1.0 / 60.0
const HAND_REACH := 0.86        # (1) the share of a hand's length its palm centre sits from the wrist, for a contact
const SOFT := 0.985             # (2) a contact never pulls an arm fully straight: it stops at this share of its reach

var p: Puppet
var floor_y := 0.0
var s_body := Vector2.ZERO      # where the body stands at rest (its root, world)
var arm := 100.0                # px
var leg := 100.0
var k := 1.0                    # the puppet's scale
var rest := {}                  # key -> rest value
var now := {}                   # key -> value as shown
var from := {}
var goal := {}
var swing := {}
var contacts := {}              # "hand_r" -> {to, dx, dy, elbow, w, w0, w1, sign, grab}
var feet_planted := true
var feet_w := 1.0               # 1 = planted (IK to their spots), 0 = free (angles); eased between
var feet_w0 := 1.0
var feet_w1 := 1.0
var foot_off := {"foot_l": Vector2.ZERO, "foot_r": Vector2.ZERO}
var foot_from := {}
var foot_goal := {}
var spots := {}                 # foot -> its spot on the floor (world, the ankle)
var knee_sign := {}
var phases: Array = []
var i := -1
var t := 0.0
var done := true
var side := "right"
var covers_face := false
var item: Node2D = null         # a thing on the floor a contact may go to ("to": "item") and grab
var item_hand := ""


func setup(puppet: Puppet, floor_at: float) -> void:
	p = puppet
	floor_y = floor_at
	k = absf(p.scale.y)
	p.reset_pose()
	s_body = p.body_position()
	for sd: String in ["l", "r"]:
		var c: Variant = p.chains["hand_" + sd]
		arm = (c.l1 + c.l2) * k
		var f: Variant = p.chains["foot_" + sd]
		leg = (f.l1 + f.l2) * k
		spots["foot_" + sd] = p.joint_position(f.end.name)
		knee_sign["foot_" + sd] = 0.0
	# the rest stance in these angles
	for sd: String in ["l", "r"]:
		var s := _s(sd)
		var c: Variant = p.chains["hand_" + sd]
		var sh: Vector2 = p.joint_position(c.a.name)
		var el: Vector2 = p.joint_position(c.b.name)
		var wr: Vector2 = p.joint_position(c.end.name)
		var up: float = (el - sh).angle()
		var fo: float = (wr - el).angle()
		rest["arm_%s.raise" % sd] = rad_to_deg(_raise(up, s))
		rest["arm_%s.elbow" % sd] = rad_to_deg(wrapf((up - fo) * s, -PI, PI))
		rest["arm_%s.wrist" % sd] = 0.0
		rest["shoulder_" + sd] = 0.0
		var f: Variant = p.chains["foot_" + sd]
		var hp: Vector2 = p.joint_position(f.a.name)
		var kn: Vector2 = p.joint_position(f.b.name)
		var an: Vector2 = p.joint_position(f.end.name)
		var th: float = (kn - hp).angle()
		var sn: float = (an - kn).angle()
		rest["leg_%s.hip" % sd] = rad_to_deg(_raise(th, s))
		rest["leg_%s.knee" % sd] = rad_to_deg(wrapf((th - sn) * s, -PI, PI))
		knee_sign["foot_" + sd] = -s     # knees out (the same side as a negative knee angle)
	for key: String in ["body.tilt", "body.chest", "body.shift", "body.drop", "body.lift", "head.tilt", "head.drop"]:
		rest[key] = 0.0
	now = rest.duplicate()
	_apply()


static func _s(sd: String) -> float:
	return 1.0 if sd == "r" else -1.0


## A limb's direction (world angle, y down) as "raise": 0 straight down, + outward on side s.
static func _raise(dir: float, s: float) -> float:
	return wrapf((PI / 2.0 - dir) * s, -PI, PI)


static func _dir(raise: float, s: float) -> float:
	return PI / 2.0 - raise * s


# ----------------------------------------------------------------------------- playing

func play(action: Dictionary, params: Dictionary = {}) -> void:
	side = params.get("side", "right")
	covers_face = bool(action.get("covers_face", false))
	phases = []
	for ph: Dictionary in action.get("phases", []):
		phases.append(_mirror(ph) if side == "left" else ph)
	i = -1
	done = false
	_next()


func busy() -> bool:
	return not done


func _next() -> void:
	i += 1
	t = 0.0
	if i >= phases.size():
		done = true
		swing = {}
		return
	var ph: Dictionary = phases[i]
	from = now.duplicate()
	goal = now.duplicate()
	swing = {}
	var pose: Variant = ph.get("pose", {})
	if pose is String and pose == "rest":
		goal = rest.duplicate()
		for h: String in contacts.keys():
			_let_go(h)
		feet_planted = true
		feet_w0 = feet_w
		feet_w1 = 1.0
		for f: String in foot_off:
			foot_off[f] = Vector2.ZERO
	elif pose is Dictionary:
		for ch: String in pose:
			_set_goal(ch, pose[ch])
	for key: String in ph.get("swing", {}):
		swing[key] = ph["swing"][key]
	if ph.has("feet"):
		feet_planted = ph["feet"] == "planted"
		feet_w0 = feet_w
		feet_w1 = 1.0 if feet_planted else 0.0
	elif not (pose is String):
		feet_w0 = feet_w
	foot_from = foot_off.duplicate()
	foot_goal = foot_off.duplicate()
	for f: String in ["foot_l", "foot_r"]:
		if ph.has(f):
			var v: Array = ph[f]
			foot_goal[f] = Vector2(float(v[0]), float(v[1]))
	for h: String in contacts:                 # a contact goes on from where it is (its weight is not reset)
		contacts[h]["w0"] = contacts[h]["w"]
	for h: String in ph.get("contact", {}):
		var spec: Variant = ph["contact"][h]
		if spec is String and spec == "free":
			_let_go(h)
		else:
			var was: Dictionary = contacts.get(h, {})
			contacts[h] = {"to": spec["to"], "else": spec.get("else", ""), "prev": was.duplicate() if not was.is_empty() else {}, "u": 0.0, "dx": float(spec.get("dx", 0.0)), "dy": float(spec.get("dy", 0.0)),
				"elbow": spec.get("elbow", "pose"), "w": contacts.get(h, {}).get("w", 0.0), "w0": contacts.get(h, {}).get("w", 0.0),
				"w1": 1.0, "sign": 0.0, "grab": bool(spec.get("grab", false))}


## A hand let go of its contact goes on from where the contact held it (no pop): its angles become the pose.
func _let_go(h: String) -> void:
	if not contacts.has(h):
		return
	var sd: String = h.right(1)
	var c: Variant = p.chains[h]
	var s := _s(sd)
	var up: float = (p.joint_position(c.b.name) - p.joint_position(c.a.name)).angle() - c.a.parent.rot
	var fo: float = (p.joint_position(c.end.name) - p.joint_position(c.b.name)).angle() - c.a.parent.rot
	for key: String in ["arm_%s.raise" % sd, "arm_%s.elbow" % sd]:
		var v: float = rad_to_deg(_raise(up, s)) if key.ends_with("raise") else rad_to_deg(wrapf((up - fo) * s, -PI, PI))
		now[key] = v
		from[key] = v
		if goal.get(key, v) == from.get(key, v):
			goal[key] = v
	contacts.erase(h)


func _set_goal(ch: String, v: Variant) -> void:
	var targets: Array = [ch]
	if ch == "arms":
		targets = ["arm_l", "arm_r"]
	elif ch == "legs":
		targets = ["leg_l", "leg_r"]
	elif ch == "shoulders":
		targets = ["shoulder_l", "shoulder_r"]
	for c: String in targets:
		if v is String and v == "rest":
			for key: String in rest:
				if key.begins_with(c):
					goal[key] = rest[key]
		elif v is Dictionary:
			for kk: String in v:
				if kk == "hand":
					p.set_skin("hand_" + c.right(1), str(v[kk]))
				else:
					goal[c + "." + kk] = float(v[kk])
		elif c == "head":
			goal["head.tilt"] = float(v)
		else:
			goal[c] = float(v)


func _mirror(ph: Dictionary) -> Dictionary:
	var s := JSON.stringify(ph)
	s = s.replace("_r\"", "_TMP\"").replace("_l\"", "_r\"").replace("_TMP\"", "_l\"")
	s = s.replace("_r.", "_TMP.").replace("_l.", "_r.").replace("_TMP.", "_l.")
	var out: Dictionary = JSON.parse_string(s)
	for key: String in ["tilt", "chest", "shift"]:
		if out.get("pose", {}) is Dictionary and (out.get("pose", {}) as Dictionary).get("body", {}) is Dictionary and out["pose"].get("body", {}).has(key):
			out["pose"]["body"][key] = -float(out["pose"]["body"][key])
	if out.get("pose", {}) is Dictionary and out.get("pose", {}).has("head"):
		var hv: Variant = out["pose"]["head"]
		if hv is Dictionary and hv.has("tilt"):
			hv["tilt"] = -float(hv["tilt"])
		elif hv is float or hv is int:
			out["pose"]["head"] = -float(hv)
	return out


static func _ease(u: float, kind: String) -> float:
	match kind:
		"linear":
			return u
		"in":
			return u * u
		"out":
			return 1.0 - (1.0 - u) * (1.0 - u)
	return u * u * (3.0 - 2.0 * u)


func step() -> void:
	if not done:
		var ph: Dictionary = phases[i]
		var length: float = maxf(float(ph.get("time", 0.3)), 0.01)
		t += DT
		var u: float = _ease(clampf(t / length, 0.0, 1.0), str(ph.get("ease", "inout")))
		for key: String in goal:
			now[key] = lerpf(float(from.get(key, goal[key])), float(goal[key]), u)
		for key: String in swing:
			var sw: Dictionary = swing[key]
			var ramp: float = clampf(t / 0.2, 0.0, 1.0)
			now[key] = float(now.get(key, 0.0)) + float(sw.get("amp", 0.0)) * sin(TAU * float(sw.get("rate", 1.0)) * t) * ramp
		for f: String in foot_off:
			foot_off[f] = (foot_from[f] as Vector2).lerp(foot_goal[f], u)
		feet_w = lerpf(feet_w0, feet_w1, u)
		for h: String in contacts:
			var c: Dictionary = contacts[h]
			c["w"] = lerpf(float(c["w0"]), float(c["w1"]), u)
			c["u"] = u
		if t >= length:
			for h: String in contacts:
				if contacts[h]["grab"] and contacts[h]["to"] == "item" and item != null:
					item_hand = h
			_next()
	_apply()


# ----------------------------------------------------------------------------- posing the puppet

func _apply() -> void:
	# the body: where it stands, its tilt; then the chest and the head
	var root := p.root
	var pos: Vector2 = s_body + Vector2(float(now["body.shift"]), float(now["body.drop"]) - float(now["body.lift"])) * leg
	_pose_body(pos)
	# the feet (planted: IK to their spots; else angles); the arms (angles, then contacts); the ground
	_place_limbs()
	for n: int in 4:                           # (lifting the body bends planted legs anew: look again)
		var low := _lowest(feet_w < 0.999)    # (planted feet stand on the floor by themselves)
		if low <= floor_y + 0.5:
			break
		pos.y -= low - floor_y
		_pose_body(pos)
		_place_limbs()
	if item != null and item_hand != "":
		item.global_position = p.point(item_hand, "grip")


func _pose_body(pos: Vector2) -> void:
	p.body_pos = p.to_local(pos)
	p.body_lean = deg_to_rad(float(now["body.tilt"]))
	p.root.angle = p.body_lean
	_put_angle(p.parts["chest"], deg_to_rad(float(now["body.chest"])))
	if p.parts.has("skirt"):                     # cloth hangs plumb from the waist whatever the body does
		_put_angle(p.parts["skirt"], -p.body_lean * (1.0 - smoothstep(0.44, 0.79, absf(p.body_lean))))
	if p.parts.has("head"):
		_put_angle(p.parts["head"], deg_to_rad(float(now["head.tilt"])))
		var hh: float = (p.parts["head"].painted as Rect2).size.y
		p.parts["head"].node.position = p.parts["head"].home + Vector2(0.0, float(now["head.drop"]) * hh)
	for sd: String in ["l", "r"]:
		var c: Variant = p.chains["hand_" + sd]
		c.a.node.position = c.a.home - Vector2(0.0, float(now["shoulder_" + sd]) * arm / k)
	p._pose(false)


func _put_angle(part: Variant, a: float) -> void:
	part.angle = clampf(wrapf(a, -PI, PI), part.lo, part.hi)


func _place_limbs() -> void:
	for sd: String in ["l", "r"]:
		var s := _s(sd)
		# legs
		var f: Variant = p.chains["foot_" + sd]
		_fk(f, float(now["leg_%s.hip" % sd]), float(now["leg_%s.knee" % sd]), s)
		if feet_w > 0.0:
			var fk_a: float = f.a.angle
			var fk_b: float = f.b.angle
			var off: Vector2 = foot_off["foot_" + sd]
			var target: Vector2 = spots["foot_" + sd] + Vector2(off.x * s, -off.y) * leg
			if feet_w1 > feet_w0:                # (a foot coming back to its spot steps there, it is not dragged)
				target.y -= 4.0 * feet_w * (1.0 - feet_w) * 0.15 * leg
			_ik(f, target, knee_sign["foot_" + sd])
			f.a.angle = lerp_angle(fk_a, f.a.angle, feet_w)
			f.b.angle = lerp_angle(fk_b, f.b.angle, feet_w)
			p._pose(false)
		_level_foot(f)
		# arms: angles, then a contact pulls the hand by its weight
		var c: Variant = p.chains["hand_" + sd]
		_fk(c, float(now["arm_%s.raise" % sd]), float(now["arm_%s.elbow" % sd]), s)
		var h := "hand_" + sd
		if contacts.has(h) and float(contacts[h]["w"]) > 0.0:
			var fk_up: float = c.a.angle
			var fk_fo: float = c.b.angle
			var target := _contact_point(h)
			var sign: float = contacts[h]["sign"]
			if sign == 0.0:
				sign = _side_of(h, c, target, sd, s)
				var has_else: bool = not (contacts[h]["else"] is String and contacts[h]["else"] == "")
				# can this body get there? try once; a palm that stays short of it takes the other place ("else")
				if has_else:
					var final: Dictionary = contacts[h].duplicate()
					final["u"] = 1.0
					final["prev"] = {}
					var at_end: Vector2 = _place(h, final)
					if _reach(c, at_end, sign, sd, s).distance_to(at_end) > 0.3 * _hand_len(c):
						var alt: Variant = contacts[h]["else"]       # a place name, or {to, dx, dy}
						contacts[h]["to"] = alt["to"] if alt is Dictionary else alt
						if alt is Dictionary:
							contacts[h]["dx"] = float(alt.get("dx", 0.0))
							contacts[h]["dy"] = float(alt.get("dy", 0.0))
						target = _contact_point(h)
						sign = _side_of(h, c, target, sd, s)
				contacts[h]["sign"] = sign
			_reach(c, target, sign, sd, s)
			var w: float = float(contacts[h]["w"])
			c.a.angle = lerp_angle(fk_up, c.a.angle, w)
			c.b.angle = lerp_angle(fk_fo, c.b.angle, w)
			p._pose(false)
		c.end.angle = clampf(-deg_to_rad(float(now.get("arm_%s.wrist" % sd, 0.0))) * s, c.end.lo, c.end.hi)
		p._pose(false)


func _side_of(h: String, c: Variant, target: Vector2, sd: String, s: float) -> float:
	if str(contacts[h]["elbow"]) == "pose":       # the side the arm's own pose bends to (no change of side)
		var e: float = float(goal.get("arm_%s.elbow" % sd, now["arm_%s.elbow" % sd]))
		return s * (signf(e) if absf(e) > 1.0 else 1.0)
	return _choose_side(c, target, str(contacts[h]["elbow"]), s)


## The arm put so its drawn palm is at `target` (as near as its joints allow); returns where the palm is.
func _reach(c: Variant, target: Vector2, sign: float, sd: String, s: float) -> Vector2:
	var fore: Vector2 = (target - p.joint_position(c.b.name)).normalized()
	var wrist_at: Vector2 = target - fore * _hand_len(c) * HAND_REACH   # (the wrist is a hand back from the palm)
	var palm := target
	for n: int in 3:                    # ...then corrected by where the drawn palm really landed
		_ik(c, wrist_at, sign)
		c.end.angle = clampf(-deg_to_rad(float(now.get("arm_%s.wrist" % sd, 0.0))) * s, c.end.lo, c.end.hi)
		p._pose(false)
		palm = c.end.node.to_global(c.end.center)
		wrist_at += target - palm
	return palm


func _hand_len(c: Variant) -> float:
	return (c.end.center as Vector2).length() * k


## Forward: the limb's two bones at these angles (degrees, on side s).
func _fk(c: Variant, raise: float, bend: float, s: float) -> void:
	var up: float = _dir(deg_to_rad(raise), s) + c.a.parent.rot    # (measured from the body: it tilts, they go with it)
	var fo := up - deg_to_rad(bend) * s
	_point_bones(c, up, fo)


func _point_bones(c: Variant, up: float, fo: float) -> void:
	var par_rot: float = c.a.parent.rot
	_put_angle(c.a, up - c.dir1 - par_rot)
	p._pose(false)
	_put_angle(c.b, fo - c.dir2 - c.a.rot)
	p._pose(false)


## Two-bone IK in world space, the middle joint on side `sign` (+1 / -1: which way round the shoulder-target line).
func _ik(c: Variant, target: Vector2, sign: float) -> void:
	var sh: Vector2 = p.joint_position(c.a.name)
	var l1: float = c.l1 * k
	var l2: float = c.l2 * k
	var d: Vector2 = target - sh
	var dist: float = clampf(d.length(), absf(l1 - l2) + 1.0, (l1 + l2) * SOFT)
	var base: float = d.angle()
	var cos_a: float = clampf((l1 * l1 + dist * dist - l2 * l2) / (2.0 * l1 * dist), -1.0, 1.0)
	var up: float = base + sign * acos(cos_a)
	var el: Vector2 = sh + Vector2.from_angle(up) * l1
	var fo: float = (sh + d.normalized() * dist - el).angle()
	_point_bones(c, up, fo)


## The elbow side a contact names, turned into a sign ONCE: the candidate whose elbow lies most that way.
func _choose_side(c: Variant, target: Vector2, want: String, s: float) -> float:
	var sh: Vector2 = p.joint_position(c.a.name)
	var dirs := {"out": Vector2(s, 0.0), "in": Vector2(-s, 0.0), "down": Vector2(0.0, 1.0), "up": Vector2(0.0, -1.0)}
	var way: Vector2 = dirs.get(want, Vector2(s, 0.0))
	var l1: float = c.l1 * k
	var l2: float = c.l2 * k
	var d: Vector2 = target - sh
	var dist: float = clampf(d.length(), absf(l1 - l2) + 1.0, (l1 + l2) * SOFT)
	var a: float = acos(clampf((l1 * l1 + dist * dist - l2 * l2) / (2.0 * l1 * dist), -1.0, 1.0))
	var e1: Vector2 = Vector2.from_angle(d.angle() + a)
	var e2: Vector2 = Vector2.from_angle(d.angle() - a)
	return 1.0 if e1.dot(way) >= e2.dot(way) else -1.0


func _level_foot(f: Variant) -> void:
	f.end.angle = clampf(-f.b.rot - f.end.parent.rot * 0.0 + 0.0, f.end.lo, f.end.hi)
	p._pose(false)


# ----------------------------------------------------------------------------- places on the body

## A named place on this hero's body (world): the part's painted box, x outward on the hand's side.
const PLACES := {
	"forehead": ["head", 0.0, -0.25, "face"], "face": ["head", 0.0, 0.1, "face"], "cheek": ["head", 0.55, 0.25, "face"],
	"chin": ["head", 0.0, 0.75, "face"], "ear": ["head", 1.0, 0.0, "face"], "crown": ["head", 0.4, -0.95, "box"],
	"chest": ["chest", 0.0, -0.1, "box"], "heart": ["chest", -0.25, -0.2, "box"], "belly": ["pelvis", 0.0, -0.3, "box"],
	"hip": ["pelvis", 1.0, -0.2, "box"], "waist": ["chest", 1.0, 0.75, "box"], "front": ["chest", 0.0, 0.2, "box"],
}


## Where a contact's hand goes now: a contact moved to another place (hands apart, then together) slides from the
## old place to the new one over its phase, never jumps.
func _contact_point(h: String) -> Vector2:
	var c: Dictionary = contacts[h]
	var to := _place(h, c)
	var prev: Dictionary = c.get("prev", {})
	if not prev.is_empty() and float(c.get("u", 1.0)) < 1.0:
		return _place(h, prev).lerp(to, float(c["u"]))
	return to


func _place(h: String, c: Dictionary) -> Vector2:
	var s := _s(h.right(1))
	if str(c["to"]) == "item" and item != null:
		return item.global_position
	var pl: Array = PLACES.get(str(c["to"]), PLACES["chest"])
	var part: Variant = p.parts[pl[0]]
	var box: Rect2 = face_box(part) if pl[3] == "face" else part.painted
	var local: Vector2 = box.get_center() + Vector2((float(pl[1]) + float(c["dx"])) * s * signf(p.scale.x) * box.size.x * 0.5,
			(float(pl[2]) + float(c["dy"])) * box.size.y * 0.5)
	return part.node.to_global(local)


## The face on a head, exactly as the old engine finds it (motion.gd _face): the hole of a worn piece, else the
## lower middle of the painted head (a hat is not a face).
func face_box(head: Variant) -> Rect2:
	return face_of(p, head)


static func face_of(puppet: Variant, head: Variant) -> Rect2:
	var hole: Dictionary = puppet.rig["parts"]["head"].get("face", {})
	if not hole.is_empty():
		var size := Vector2(hole["size"][0], hole["size"][1])
		return Rect2(Vector2(hole["center"][0], hole["center"][1]) - head.pivot - size * 0.5, size)
	var b: Rect2 = head.painted
	return Rect2(b.position + Vector2(0.18 * b.size.x, 0.38 * b.size.y), Vector2(0.64 * b.size.x, 0.56 * b.size.y))


## The lowest painted point of the whole hero (world y).
func _lowest(with_feet := true) -> float:
	var low := -INF
	for name: String in p.parts:
		if name.begins_with("foot"):
			if with_feet:                          # (a foot stands on its sole)
				low = maxf(low, p.point(name, "sole").y)
			continue
		var part: Variant = p.parts[name]
		var r: Rect2 = part.painted
		for corner in [r.position, Vector2(r.end.x, r.position.y), r.end, Vector2(r.position.x, r.end.y)]:
			low = maxf(low, part.node.to_global(corner * 0.92 + r.get_center() * 0.08).y)
	return low
