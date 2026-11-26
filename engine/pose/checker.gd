extends RefCounted
## ONE fault table for both engines (experiment): it looks only at the drawn puppet, frame by frame, never at how
## the pose was made. So the old engine and the angles player are judged by the same eyes.
##   flip     an elbow or a knee swung to its other side in a few frames while bent (a pop)
##   floor    something painted went under the floor (leg lengths)
##   face     seconds a hand or a forearm lay over the face, the action not saying it covers the face
##   inside   a hand's middle inside the chest or the pelvis (shares of a hand), the action not touching the body
##   miss     a declared contact did not reach its place (shares of a hand) - angles player only
##   slide    a foot standing on the floor moved along it (leg lengths)
##   jerk     the hardest change of a hand's speed (arm lengths / s^2)

const PosePlayer := preload("res://pose/pose_player.gd")
const LIMITS := {"flip": 0, "floor": 0.01, "face": 0.3, "inside": 0.15, "miss": 0.15, "slide": 0.03, "jerk": 450.0}
const DT := 1.0 / 60.0

var p: Variant
var floor_y := 0.0
var arm := 100.0
var leg := 100.0
var covers_face := false
var touches := false               # the action touches the body (a hand inside it is meant)
var m := {}
var _bent := {}                    # chain -> [sign, frames since it was last clearly bent]
var _hand_prev := {}
var _hand_vel := {}
var _foot_at := {}
var _low_part := ""
var _n := 0                 # foot -> x where it came to stand


func setup(puppet: Variant, floor_at: float, arm_len: float, leg_len: float) -> void:
	p = puppet
	floor_y = floor_at
	arm = arm_len
	leg = leg_len
	m = {"flip": 0, "floor": 0.0, "face": 0.0, "inside": 0.0, "miss": 0.0, "slide": 0.0, "jerk": 0.0}
	_bent.clear()
	_hand_prev.clear()
	_hand_vel.clear()
	_foot_at.clear()


func sample() -> void:
	var body: Vector2 = p.body_position()
	for h: String in ["hand_l", "hand_r", "foot_l", "foot_r"]:
		var c: Variant = p.chains[h]
		var a: Vector2 = p.joint_position(c.a.name)
		var b: Vector2 = p.joint_position(c.b.name)
		var e: Vector2 = p.joint_position(c.end.name)
		var cross: float = (b - a).cross(e - b) / maxf((b - a).length() * (e - b).length(), 1.0)
		var st: Array = _bent.get(h, [0.0, 999])
		if absf(cross) > 0.25:                     # clearly bent (more than ~15 degrees)
			var sg: float = signf(cross)
			if st[0] != 0.0 and sg != st[0] and st[1] <= 8:
				m["flip"] += 1
			_bent[h] = [sg, 0]
		else:
			_bent[h] = [st[0], st[1] + 1]
	# under the floor
	var low := -INF
	for name: String in p.parts:
		if name.begins_with("foot"):
			continue                               # (a foot is judged by its sole, below)
		var part: Variant = p.parts[name]
		var r: Rect2 = part.painted
		for corner in [r.position, Vector2(r.end.x, r.position.y), r.end, Vector2(r.position.x, r.end.y)]:
			var y: float = part.node.to_global(corner * 0.92 + r.get_center() * 0.08).y
			if y > low:
				low = y
				_low_part = name
	for ft: String in ["foot_l", "foot_r"]:
		var sy: float = p.point(p.chains[ft].end.name, "sole").y
		if sy > low:
			low = sy
			_low_part = ft + ".sole"
	if (low - floor_y) / leg > m["floor"]:
		m["floor"] = (low - floor_y) / leg
		m["floor_at"] = "%s@%d" % [_low_part, _n]
	_n += 1
	# the face, the body
	var head: Variant = p.parts["head"]
	var face: Rect2 = PosePlayer.face_of(p, head)
	face = face.grow_individual(-0.15 * face.size.x, -0.1 * face.size.y, -0.15 * face.size.x, -0.1 * face.size.y)
	var over := false
	for sd: String in ["l", "r"]:
		var hand: Variant = p.parts["hand_" + sd]
		var mid: Vector2 = hand.node.to_global(hand.center)
		var fore: Variant = p.parts["forearm_" + sd]
		var el: Vector2 = fore.node.global_position
		for q: Vector2 in [mid, el.lerp(hand.node.global_position, 0.5), el.lerp(hand.node.global_position, 0.8)]:
			if face.has_point(head.node.to_local(q)):
				over = true
		if not touches:
			for name: String in ["chest", "pelvis"]:
				var part: Variant = p.parts[name]
				var local: Vector2 = part.node.to_local(mid)
				var box: Rect2 = part.painted
				if box.has_point(local):
					var hl: float = (hand.center as Vector2).length() * absf(p.scale.x)
					var depth: float = minf(local.x - box.position.x, box.end.x - local.x) * absf(p.scale.x)
					m["inside"] = maxf(m["inside"], depth / maxf(hl * 2.0, 1.0))
		# jerk: the hand against the body
		var rel: Vector2 = mid - body
		var h := "hand_" + sd
		if _hand_prev.has(h):
			var v: Vector2 = (rel - _hand_prev[h]) / DT
			if _hand_vel.has(h):
				var jk: float = (v - _hand_vel[h]).length() / DT / arm
				if jk > m["jerk"]:
					m["jerk"] = jk
					m["jerk_at"] = "%s@%d" % [h, _n]
			_hand_vel[h] = v
		_hand_prev[h] = rel
	if over and not covers_face:
		m["face"] += DT
	# a standing foot that moves along the floor (a body standing up: lying or falling, feet go where they go)
	var upright: bool = absf(wrapf(p.root.node.global_rotation, -PI, PI)) < 0.35
	for sd: String in ["l", "r"]:
		if not upright:
			_foot_at.clear()
			break
		var f := "foot_" + sd
		var sole: Vector2 = p.point(p.chains[f].end.name, "sole")
		if absf(sole.y - floor_y) < 0.02 * leg:
			if not _foot_at.has(f):
				_foot_at[f] = sole.x
			m["slide"] = maxf(m["slide"], absf(sole.x - _foot_at[f]) / leg)
		else:
			_foot_at.erase(f)


func faults() -> Dictionary:
	var out := {}
	for key: String in LIMITS:
		var v: float = float(m.get(key, 0.0))
		if v > float(LIMITS[key]):
			out[key] = snappedf(v, 0.01)
	return out
