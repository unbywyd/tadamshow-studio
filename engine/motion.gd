extends RefCounted
## Plays ACTIONS on one puppet: the motion layer between a scene's script and the puppet's handles.
##
## An action is data (engine/actions/<id>.json), never code, and every number in it is in the hero's OWN
## measures: arm lengths, leg lengths, degrees, seconds. So the same file moves a loaf and a knight.
##
##   { "id": "wave", "title": "помахать", "params": { "side": "right" },
##     "phases": [
##       { "time": 0.35, "arm_r": { "at": [0.44, -0.68] }, "head": 6 },
##       { "time": 1.6, "loop": true, "arm_r": { "wrist": { "base": 0, "amp": 24, "rate": 2.0 } } },
##       { "time": 0.4, "arm_r": "rest", "head": "rest" } ] }
##
## The body is split into CHANNELS: legs (drop, shift, feet, jump), body (lean, chest), head (tilt), arm_l,
## arm_r. An action takes the channels its phases mention; a new action takes them over and an older one keeps
## the rest, so a hero can walk and wave. A value not mentioned in a phase holds where it is.
##
## Values (any number may also be { "base": v, "amp": a, "rate": hz, "phase": cycles }, an oscillation):
##   legs  drop: leg lengths down (a squat)   shift: leg lengths to the side   jump: height in leg lengths (once)
##         foot_l / foot_r: [out, up] leg lengths from where the foot stands
##         walk: leg lengths to walk (forward in profile, to the right seen from the front; negative = back / left),
##               with "speed" in leg lengths a second; the phase lasts as long as the walk
##         seat: sit down on something this many leg lengths high (0 = the floor); "rest" stands up
##   body  lean: degrees (+ = to the action's side)   chest: degrees
##   head  a number = tilt in degrees, or { "tilt": ..., "drop": ... }: drop = the head drawn into the collar
##         (+, shares of its height, at most 0.25) or stretched up (-, at most 0.15)
##   (an arm's place may go round: { "base", "amp": [out, down], "rate", "circle": true })
##   arm_l / arm_r / arms (both):
##         at: [out, down] arm lengths from the shoulder, or { "to": landmark, "dx": .., "dy": .. } (see LANDMARKS)
##         wrist: degrees, outward   look: "palm" | "fist" | "back" | "edge" (the hand turned edge on) | "point"
##              (the index finger out) | "auto"
##         contact: true = may touch the body
##         shoulder: arm lengths the shoulder is raised (+, at most 0.16: a shrug) or dropped (-, at most 0.08)
##         elbow: "down" | "up" | "out" | "in": where the ELBOW points in this pose, said outright (by default the
##              engine chooses: under the hand for an arm held out or raised, to the side for one hanging)
##         aim: where the HAND points, degrees round the wrist (0 out, 90 down, -90 up, 180 in): the wrist turns to
##              it whatever the forearm does (a hand on the hip points down, a hand at the ear points up)
##   "rest" for a channel or a value = where this hero stands at rest.
## A phase: "time" seconds; "loop": true = lasts the param "duration" if given (or until released when it is
## the last phase); "ease": "inout" | "out" | "in" | "linear". Params of every action: side (right | left |
## both), energy (angles and swings), speed (times), duration (the loop), and its own.
##
## LAWS the motion obeys whatever an action asks (a script never has to think of them):
##   a joint bends only its own way (puppet.gd); hands move on arcs round the shoulder; a raised hand shows its
##   palm; a hand never goes into the body unless the action says contact; a hand never goes under the floor;
##   a planted foot never slides: the body drops instead when the legs cannot reach; a foot moved along the
##   floor is lifted on the way; on one foot the body moves over it; the body never leaves the stage.
## Everything that happens is measured (see `m`) so tools/action_check.gd can judge an action on every hero.
## With the environment variable MOTION_DEBUG set it also prints each step where a joint is on the wrong side,
## the sent hand path jumps, something goes under the floor or out of the picture.

const Puppet := preload("res://puppet.gd")
const BodyPhysics := preload("res://body_physics.gd")
const SoftSkirt := preload("res://soft_skirt.gd")
const DT := 1.0 / 60.0

const CHANNELS := ["legs", "body", "head", "arm_l", "arm_r"]
const CROSS_REACH := 0.86        # how far out a hand is while its elbow changes sides (arm lengths)
const CROSS_LINE := 1.176        # radians: the line out and steeply down from the shoulder where it changes (puppet.gd POLE_DOWN)
const RAMP := 0.2                # seconds an oscillation takes to grow to full size
const RELEASE_TIME := 0.45       # seconds back to rest when an action is let go without a return phase
const FLOOR_GAP := 0.12          # arm lengths a wrist stays above the floor
const REACH := 0.95              # share of its length a planted leg may be stretched to
const SKIN_OF := {"palm": "palm", "fist": "fist", "back": "", "edge": "edge", "point": "point"}   # (a hand without such a drawing keeps the one it shows; "edge" without one is the back squeezed across)
const EDGE_WIDTH := 0.42         # a hand seen edge on: the flat hand at this share of its width

## Places of the hero's own body a hand can be sent to. Measured from the drawing every step, so a hand on the
## chest lands on THIS hero's chest. [part, x, y, on what, elbow]: x, y are halves of the box from its middle
## (x outward on the hand's side); the box is the part's painted one, or for "face" the FACE (the hole of a worn
## piece, the recorded face, or the lower middle of a painted head: a hat is not a face); "edge" = at the height
## y of the face, on the very edge of the head's silhouette (hair, ears) on the hand's side, x = hand widths out. The elbow of a hand
## going there is "down" (to the chin, the chest: the arm comes up in front) or "out" (on the hips, at the ears).
const LANDMARKS := {
	"chest": ["chest", 0.0, -0.05, "box", "down"], "heart": ["chest", -0.18, -0.12, "box", "down"],
	"belly": ["pelvis", 0.0, -0.1, "box", "down"], "hip": ["pelvis", 1.0, -0.3, "box", "out"],
	"chin": ["head", 0.0, 1.1, "face", "down"], "mouth": ["head", 0.0, 0.6, "face", "down"],
	"face": ["head", 0.0, 0.0, "face", "down"], "forehead": ["head", 0.0, -0.7, "face", "down"],
	"ear": ["head", 0.45, -0.15, "edge", "out"], "crown": ["head", 0.3, -0.9, "box", "out"],
	"nape": ["head", 0.9, 0.6, "box", "out"],
}
const ELBOW_DIR := {"down": Vector2(0, 1), "up": Vector2(0, -1), "out": Vector2(1, 0), "in": Vector2(-1, 0)}
const HAND_SPEED := 8.0          # arm lengths a second at most
const HAND_ACCEL := 200.0        # arm lengths a second squared at most
const STIFF_SKIRT := 0.6         # leg lengths: a skirt shorter than this is stiff (a tutu), not cloth
const DEEP_SQUAT := 0.58         # leg lengths: the deepest a hero goes down to reach for something (crouching)
const LEFT_OUT := 0.15           # arm lengths out from the shoulder: a hand past this has left the front of the body
const GAP_RISE := 2.5            # arm lengths a second: how fast a hand is lifted when what it holds needs more room under it
const STOOP_HIPS := 30.0         # degrees: in profile, the furthest the pelvis tips forward to reach the floor...
const STOOP_BACK := 60.0         # ...and the back bends on top of that
const STRETCH_ACCEL := 150.0     # arm lengths a second squared: an arm straightening for its elbow, at most
const WALK_SPEED := 1.0          # leg lengths a second
const WALK_STEP := 0.7           # how far a foot travels in one step, leg lengths
const WALK_LIFT := 0.12          # how high it is lifted, leg lengths
const WALK_BOB := 0.02           # how much the body rises over the standing foot, leg lengths
const STRETCH_BACK := 0.25       # ...and to bend back again (slower: a quick release is a jerk)
const STRETCH_TIME := 0.1        # seconds an arm takes to straighten for its elbow to swing over
const WRIST_MAX := 80.0          # degrees a wrist turns at most
const MIN_REACH := 0.3           # arm lengths: the closest a hand comes to its own shoulder
const LINE_HOLD := 0.14          # radians either side of an elbow line where an arm is held straight
## In profile some places are elsewhere: the chest and the belly are in FRONT (the way the hero faces), the hip
## is the middle of the pelvis.
const LANDMARKS_SIDE := {
	"chest": ["chest", 0.75, -0.05, "box", "down"], "heart": ["chest", 0.7, -0.2, "box", "down"],
	"belly": ["pelvis", 0.8, -0.1, "box", "down"], "hip": ["pelvis", 0.0, -0.3, "box", "out"],
}
const PERCH := 0.7              # the highest a hero climbs onto a seat over its own hips, leg lengths
const BAND := 0.16               # ...and over this much more it bends back to what was asked


class Run:
	var id := ""
	var spec: Dictionary
	var phases: Array = []            # phases with the sides already resolved
	var owned: Array = []             # channels this run still has
	var i := -1                       # current phase
	var t := 0.0                      # seconds into it
	var length := 0.0                 # how long it lasts (INF = until released)
	var energy := 1.0
	var speed := 1.0
	var duration := -1.0
	var done := false
	var covers_face := false
	var side := "right"               # the side it was played on (its arms are mirrored for "left")
	var ease_time := 0.5              # seconds this phase's curves take (its time, or more: see HAND_SPEED)
	var walking := false              # its phase lasts as long as the walk it started
	var advance := 1.0                # (a walk) share of the way the body goes across; the rest is into the depth


class Chan:
	var owner: Run = null
	var now: Dictionary = {}          # key -> value as it is (with the swing)
	var from: Dictionary = {}         # key -> value at the start of the phase
	var goal: Dictionary = {}         # key -> spec of the phase (number, Vector2, Dictionary, "rest")
	var vel: Dictionary = {}          # key -> how fast it is changing (per second)
	var v0: Dictionary = {}           # key -> that speed when the phase began: carried on, then let die out
	var prev: Dictionary = {}


var puppet: Puppet
var phys: BodyPhysics
var floor_y := 1100.0
var stage := Vector2(720, 1280)
var arm := 100.0
var leg := 100.0
var hand_len: Dictionary = {}       # "arm_l" -> px from wrist to the middle of the hand
var shoulder: Dictionary = {}       # "arm_l" -> shoulder offset from the body at rest
var _waist := Vector2.ZERO          # the chest's joint, offset from the body at rest
var front := 0.0                    # px from the body's point to the front of its belly or chest, as it stands at rest
                                    # (in profile: where a thing carried in front of it must begin)
var hip: Dictionary = {}            # "foot_l" -> hip offset from the body at rest
var foot_home: Dictionary = {}      # "foot_l" -> where the ankle stands, world
var rest: Dictionary = {}           # channel -> {key: value} of this hero at rest
var chans: Dictionary = {}
var runs: Array[Run] = []
var view := "front"                 # "front" | "side" | "back": the rig's own view
var facing := 1.0                   # in profile: +1 faces right, -1 left (a mirrored puppet)
var holding: Dictionary = {}        # hand -> true: it holds something, so it stays a fist whatever an action says
var _gap_now: Dictionary = {}       # hand -> the floor gap it keeps now (it grows smoothly: GAP_RISE)
var hold_low: Dictionary = {}       # hand -> px a held thing hangs below the fist (items.gd): it stays above the floor too
var _on_knee: Dictionary = {}       # "arm_l" -> 0..1, how much a free hand rests on its knee (a deep squat)
var throw_at: Variant = null        # world point the next thrown thing is aimed at (the stage sets it: "throw at that hero")
var _edge_w: Dictionary = {}        # hand -> 0..1, how far it is turned edge on
var carry_spec: Dictionary = {}     # "arm_l" -> a place like { "to": "@crate", "carry": [0, 0.9] }: where this hand
                                    # holds a thing carried with both hands whenever no action moves the arm (items.gd)
var _carry_w: Dictionary = {}       # "arm_l" -> 0..1, how much the hand is there
var _carry_last: Dictionary = {}    # "arm_l" -> that place, from the shoulder (for letting go smoothly)
var points: Dictionary = {}         # "@name" -> func(ch, spec) -> world point: places in the scene a hand can go to
                                    # (an item's grip: items.gd), as { "to": "@name" }
var life := 1.0                     # the idle life: sway, breath, weight shift
var t := 0.0
var steps := 0
var events: Array = []              # [step, run id, "start" | "end" | "grab" | "release" | "throw" | "catch" | "foot"]
var m := {}                         # measurements, see _measure()

var _last: Dictionary = {}
var _aim: Dictionary = {}           # hand -> where it was SENT a step ago (relative to the body), and its speed
var _aim_vel: Dictionary = {}
var _still: Dictionary = {}         # hand -> steps its place has not moved
var _gait: Dictionary = {}          # a walk under way (see _walk_step)
var _home_off: Dictionary = {}      # foot -> where it stands across from the body (x, px), for the last step of a walk
var _walk_w := 0.0                  # 0..1, how much the arms swing with a walk
var _walk_u := 0.0
var _walk_side := "foot_r"
var _run_fist: Dictionary = {}     # hand -> closed for running
var _gait_look: Dictionary = {}     # the gait of the last walk (its arm swing and rocking die out after it)
var _balance := 0.0                 # px the body has moved over a standing foot
var _seated := false
var _landed := 0                    # steps since the feet last came down
var _elbow: Dictionary = {"arm_l": "out", "arm_r": "out"}
var _straight: Dictionary = {}      # "arm_l" -> the hand goes in a straight line this phase (to or off the body)
var _goal_was: Dictionary = {}      # "arm_l" -> [run, phase, goal a step ago]: a place in the scene moves (the path it needs grows)
var _bow: Dictionary = {}           # "arm_l" -> [run, phase, side]: which way this phase's straight line rounds the shoulder
var _hand_off: Dictionary = {}      # "arm_l" -> the hand's direction against its forearm at rest (radians, outward)
var cloth: Variant = null           # a skirt as cloth (soft_skirt.gd), if the hero wears one
var _floor_held: Dictionary = {}    # hand -> its place was under the floor and it was held above
var _under_run := 0
var _lift_fix := 0.0                # px the body rose so a pelvis lying turned stays on the floor
var _lean_fix := 0.0                # degrees the lean gave way so the body lies on the floor, not in it
var _under_was := Vector2(-INF, -INF)   # last step: how far the chest/head and the pelvis were under the floor
var _rest_body := Vector2.ZERO     # where the body stood when set up
var _limbs: Dictionary = {}         # names of the parts in arms and legs
var _over: Dictionary = {}          # "arm_l" -> [run, phase, side, done]: this phase takes the elbow over to that side,
                                    # half way, on a straightened arm
var _side_goal: Dictionary = {}     # "arm_l" -> the side its present POSE has (set at the phase that sent it there)
var side_log: Array = []            # [run id, phase, side of arm_l, side of arm_r] at every phase end (a check reads it)
var _stretched: Dictionary = {}     # "arm_l" -> 0..1, how straight it is held for its elbow
var _stretch_v: Dictionary = {}     # "arm_l" -> how fast that changes, a second
var _rest_side: Dictionary = {}     # "arm_l" -> the side its elbow is on at rest
var max_drop := 1.0                 # leg lengths the body may go down (a dress to the floor would go through it)
var _steady: Dictionary = {}        # "arm_l" -> the hand is going somewhere (not swinging): its path is counted
var _vel: Dictionary = {}
var _rest_low: Dictionary = {}
var _grounded := true


## The puppet must already stand on the floor at its place (as stage.gd puts it) with the physics set up.
func setup(p: Puppet, body: BodyPhysics, floor_at: float, stage_size: Vector2) -> void:
	puppet = p
	phys = body
	floor_y = floor_at
	stage = stage_size
	view = p.rig.get("view", "front")
	facing = signf(p.scale.x) if view == "side" else 1.0
	if view == "side":                       # knees forward, elbows back
		for f in ["foot_l", "foot_r"]:
			p.set_bend(f, "front")
		for h in ["hand_l", "hand_r"]:
			p.set_bend(h, "back")
	var k: float = absf(p.scale.y)
	var home := p.body_position()
	for side in ["l", "r"]:
		var c: Variant = p.chains["hand_" + side]
		arm = (c.l1 + c.l2) * k
		shoulder["arm_" + side] = p.joint_position(c.a.name) - home
		hand_len["arm_" + side] = (c.end.center as Vector2).length() * k
		var f: Variant = p.chains["foot_" + side]
		leg = (f.l1 + f.l2) * k
		hip["foot_" + side] = p.joint_position(f.a.name) - home
		foot_home["foot_" + side] = p.handle_position("foot_" + side)
		_home_off["foot_" + side] = foot_home["foot_" + side].x - home.x
	_waist = p.joint_position("chest") - home if p.parts.has("chest") else Vector2(0.0, -0.3 * leg)
	for part in ["chest", "pelvis", "belly"]:
		if p.parts.has(part):
			var box: Rect2 = _world_box(part)
			front = maxf(front, (box.end.x - home.x) if facing >= 0.0 else (home.x - box.position.x))
	for ch in CHANNELS:
		chans[ch] = Chan.new()
	rest["legs"] = {"drop": 0.0, "shift": 0.0, "foot_l": Vector2.ZERO, "foot_r": Vector2.ZERO}
	rest["body"] = {"lean": 0.0, "chest": 0.0}
	rest["head"] = {"tilt": 0.0, "drop": 0.0}
	for ch in ["arm_l", "arm_r"]:
		var h: String = "hand_" + ch.right(1)
		var s := _sign(ch)
		var w: Vector2 = (p.handle_position(h) - home - shoulder[ch]) / arm
		rest[ch] = {"at": _polar(Vector2(w.x * s, w.y)), "wrist": 0.0, "look": "auto", "contact": false, "aim": 90.0, "aim_w": 0.0, "shoulder": 0.0}
		# which way the hand points against its forearm as drawn: an aimed hand is turned from there
		var cc: Variant = p.chains[h]
		var fore: Vector2 = cc.end.node.global_position - cc.b.node.global_position
		var hand_dir: Vector2 = cc.end.node.to_global(cc.end.center) - cc.end.node.global_position
		_hand_off[ch] = wrapf(atan2(hand_dir.y, hand_dir.x * s) - atan2(fore.y, fore.x * s), -PI, PI)
	for ch in CHANNELS:
		chans[ch].now = rest[ch].duplicate()
	for ch in ["arm_l", "arm_r"]:
		_rest_side[ch] = p.chains["hand_" + ch.right(1)].side
		if view != "side":
			p.set_bend("hand_" + ch.right(1), _rest_side[ch])     # a side is SET, pose by pose (_pose_side)
	_rest_body = p.body_position()
	for c: Variant in p.chains.values():
		for part: Variant in [c.a, c.b, c.end]:
			_limbs[part.name] = true
	for part: String in p.parts:
		_rest_low[part] = _lowest(part)
	# a dress or a robe down to the floor: the body may only go down as far as its hem is above the floor
	var limbs := _limbs
	var hem := -INF                     # the lowest point of the trunk and what hangs from it (a skirt, a robe)
	for part: String in p.parts:
		if not limbs.has(part) and part != "skirt":
			hem = maxf(hem, _rest_low[part])
	max_drop = maxf((floor_y + 0.03 * leg - hem) / leg, 0.03)
	if p.parts.has("skirt"):
		# a skirt (cloth) gathers on the floor as the body goes down, to a third of its length at most
		var sk: Variant = p.parts["skirt"]
		var top_y: float = p.to_global(sk.xf.origin).y
		var length: float = (_rest_low["skirt"] - top_y)
		max_drop = minf(max_drop, maxf((floor_y - top_y - 0.38 * length) / leg, 0.03))
	phys.max_sink = max_drop * leg if max_drop < 0.3 else INF
	if p.parts.has("skirt"):
		# A LONG skirt is cloth: it hangs plumb, swings, gathers on the floor. A SHORT one (a tutu, a kilt: shorter
		# than STIFF_SKIRT of the leg) is stiff: it sits on the hips and leans with the body. Hung plumb like
		# cloth, it comes away from a leaning body and the body shows through the gap.
		var sk2: Variant = p.parts["skirt"]
		var long_skirt: bool = (_rest_low["skirt"] - p.to_global(sk2.xf.origin).y) >= STIFF_SKIRT * leg
		if long_skirt:
			cloth = p.get_meta("cloth") if p.has_meta("cloth") else SoftSkirt.make(p, sk2, view == "side")
		if cloth != null:
			p.set_meta("cloth", cloth)
			cloth.side = view == "side"
			cloth.reset()
		else:
			sk2.rigid = true
			sk2.goal = 0.0
	# the floor in front of a hand, where a thing is put down
	# (as low as the hand may go: what it holds just touches the floor)
	points["@floor"] = func(ch: String, spec: Dictionary) -> Vector2:
		var h: String = "hand_" + ch.right(1)
		var gap: float = maxf(maxf(FLOOR_GAP * arm, 1.9 * hand_len[ch]), 0.8 * hand_len[ch] + float(hold_low.get(h, 0.0)))
		return Vector2(_shoulder_at(ch, puppet.body_position()).x + 0.55 * arm * _sign(ch), floor_y - gap + 0.75 * hand_len[ch])
	reset_measures()


## Takes over the pose of the same hero in another view (a turn): every value is in the hero's own measures, so
## it means the same thing here. Running actions are not carried over; the pose holds until the next one.
func adopt(other: Variant) -> void:
	for ch in CHANNELS:
		var now: Dictionary = other.chans[ch].now.duplicate(true)
		for k in rest[ch]:
			if not now.has(k):
				now[k] = rest[ch][k]
		chans[ch].now = now
	life = other.life
	holding = other.holding.duplicate()
	carry_spec = other.carry_spec.duplicate(true)
	_side_goal = other._side_goal.duplicate()
	# what was playing plays on (a return to rest cut off by a turn would leave the pose standing for ever); a
	# walk does not: its feet were on the other picture
	runs = []
	for r in other.runs:
		if r.done:
			continue
		if r.walking:
			r.walking = false
			r.length = r.t
		runs.append(r)
	for ch in CHANNELS:
		var c: Chan = chans[ch]
		var o: Variant = other.chans[ch]
		c.owner = o.owner if runs.has(o.owner) else null
		c.goal = o.goal.duplicate(true)
		c.from = o.from.duplicate(true)
		c.v0 = o.v0.duplicate(true)
		c.vel = o.vel.duplicate(true)
		c.prev = o.prev.duplicate(true)
	_steady = other._steady.duplicate()
	_elbow = other._elbow.duplicate()
	_straight = other._straight.duplicate()
	# "Out" is not the same direction in every view: from the front it is sideways (out from the body, or IN across
	# it), in profile it is forward. A hand held at a place on the body (the chin, the chest) is put there again as
	# this view has it; a hand held IN across the body from the front is in front of it, so in profile it is forward.
	# (Carried as a bare number, "a hand in at the chin" became "a hand straight back" in profile.)
	if (view == "side") != (other.view == "side"):
		for ch in ["arm_l", "arm_r"]:
			var c: Chan = chans[ch]
			var spec_at: Variant = c.goal.get("at", null)
			if spec_at is Dictionary and spec_at.has("to") and not str(spec_at["to"]).begins_with("@"):
				c.now["at"] = _polar(_landmark(ch, spec_at, c.goal.get("aim", null)))
			elif view == "side" and c.now.get("at", null) is Vector2:
				var p: Vector2 = _cart(c.now["at"])
				if p.x < 0.0:
					c.now["at"] = _polar(Vector2(-p.x, p.y))
	for ch in ["arm_l", "arm_r"]:
		var h: String = "hand_" + ch.right(1)
		if _fist_held(h):
			puppet.set_skin(h, "fist")
		elif chans[ch].now.get("look", "auto") not in ["auto", ""]:
			puppet.set_skin(h, _skin_of(h, chans[ch].now["look"]))


## The drawing a hand shows for a "look": its own drawing of it if it has one, else the back of the hand.
func _skin_of(hand: String, look: String) -> String:
	var v: String = SKIN_OF.get(look, "")
	return v if puppet.parts.has(hand) and (puppet.parts[hand] as Object).skins.has(v) else ""


func reset_measures() -> void:
	m = {"steps": 0, "wrong": 0, "wrong_run": 0, "balance": -1.0, "slide": 0.0, "floor": 0.0, "inside": 0.0, "face": 0.0, "face_run": 0.0,
		"miss": 0.0, "travel": 0.0, "needed": 0.0, "accel": 0.0, "out": 0.0, "airborne": 0, "cross": 0.0}
	side_log.clear()
	_last.clear()
	_aim.clear()
	_aim_vel.clear()
	puppet.wrong_total = 0
	puppet.wrong_longest = 0


# ----------------------------------------------------------------------------- playing

## Starts an action. `params` override the action's own: side, energy, speed, duration and the action's own ones.
func play(action: Dictionary, params: Dictionary = {}) -> Run:
	var r := Run.new()
	r.id = action.get("id", "?")
	r.spec = action
	var prm: Dictionary = action.get("params", {}).duplicate()
	prm.merge(params, true)
	r.energy = float(prm.get("energy", 1.0))
	r.speed = maxf(float(prm.get("speed", 1.0)), 0.1)
	r.duration = float(prm.get("duration", -1.0))
	r.advance = float(prm.get("advance", 1.0))
	r.covers_face = bool(action.get("covers_face", false))
	var side: String = prm.get("side", "right")
	r.side = side
	# an action made for the profile, played by a hero that has none: its "front" phases if it has them (a simple
	# pose that reads from the front: sitting on the floor with the legs out to the sides), else as it is
	var phases: Array = action.get("phases", [])
	if action.get("view", "") == "side" and view != "side" and action.has("front"):
		phases = action["front"]
	for ph: Dictionary in phases:
		r.phases.append(_resolve(ph, side, prm))
	for ph: Dictionary in r.phases:
		for ch in CHANNELS:
			if ph.has(ch) and not r.owned.has(ch):
				r.owned.append(ch)
	# An action that loses an ARM to this one lets its other arm go too (to its own return, or to rest): half a clap,
	# one hand of "hands on hips" left playing beside a wave is nobody's intention. Legs, body and head are another
	# matter: a walk goes on under a wave.
	var broken: Array = []
	for ch: String in r.owned:
		var c: Chan = chans[ch]
		if c.owner != null and c.owner != r:
			c.owner.owned.erase(ch)
			if ch.begins_with("arm") and not broken.has(c.owner):
				broken.append(c.owner)
		c.owner = r
	for old: Run in broken:
		var keeps_arm := false
		for ch2: String in old.owned:
			keeps_arm = keeps_arm or ch2.begins_with("arm")
		if keeps_arm and not old.done:
			release(old)
	runs.append(r)
	events.append([steps, r.id, "start"])
	_next_phase(r)
	return r


## Lets an action go: to its phase named "return" if it has one, otherwise its channels go back to rest.
func release(r: Run) -> void:
	if r.done:
		return
	for i in range(r.i + 1, r.phases.size()):
		if r.phases[i].get("name", "") == "return":
			r.i = i - 1
			_next_phase(r)
			return
	var back := {"time": RELEASE_TIME}
	for ch: String in r.owned:
		back[ch] = "rest"
	r.phases = [back]
	r.i = -1
	_next_phase(r)


## Everything back to rest.
func rest_all(time := RELEASE_TIME) -> Run:
	var back := {"time": time}
	for ch in CHANNELS:
		back[ch] = "rest"
	return play({"id": "rest", "phases": [back]})


## A CLEAN switch (the workshop, mechanics-tz 3.2): every action lets go, the hero goes back to rest, and only then
## `action` plays, so nothing of the action before still holds a channel. (A scene LAYERS actions instead: a walk
## goes on under a wave; that is play().) clean_run is the run it started, once it has.
func play_clean(action: Dictionary, params: Dictionary = {}, time := RELEASE_TIME) -> void:
	var back := rest_all(time)
	for r in runs:
		if r != back and not r.done:
			r.done = true
			r.owned.clear()
			events.append([steps, r.id, "end"])
	runs = runs.filter(func(r: Run) -> bool: return not r.done)
	_next = [action, params]
	clean_run = null


var _next: Array = []                # [action, params]: what play_clean plays once the hero is at rest
var clean_run: Run = null


func busy() -> bool:
	if not _next.is_empty():
		return true
	for r in runs:
		if not r.done:
			return true
	return false


## Mirrors an action written for the right side, and fills in its params ("$name" in a value).
func _resolve(ph: Dictionary, side: String, prm: Dictionary) -> Dictionary:
	var out := {}
	var mirror := side == "left"
	for key: String in ph:
		var v: Variant = _params(ph[key], prm)
		match key:
			"arms":
				out["arm_l"] = v
				out["arm_r"] = v
			"arm_r", "arm_l":
				if side == "both":
					out["arm_l"] = v
					out["arm_r"] = v
				else:
					out[("arm_l" if key == "arm_r" else "arm_r") if mirror else key] = v
			"legs":
				out[key] = _mirror_legs(v) if mirror else v
			# (in profile a lean is forward or back, the same for either hand: both reach the way the hero faces.
			# Mirrored there, an action for the left hand bent the body BACK, away from what it reached for)
			"body":
				out[key] = _flip(v, ["lean", "chest"]) if mirror and view != "side" else v
			"head":
				var hv: Variant = v if (v is Dictionary and not (v as Dictionary).has("base")) or v is String else {"tilt": v}
				out[key] = _flip(hv, ["tilt"]) if mirror and view != "side" else hv
			_:
				out[key] = v
	return out


func _params(v: Variant, prm: Dictionary) -> Variant:
	if v is String and (v as String).begins_with("$"):
		return prm.get((v as String).substr(1), 0.0)
	if v is Dictionary:
		var d := {}
		for k in v:
			d[k] = _params(v[k], prm)
		return d
	if v is Array:
		return (v as Array).map(func(x): return _params(x, prm))
	return v


func _flip(v: Variant, keys: Array) -> Variant:
	if not (v is Dictionary):
		return v
	var d: Dictionary = (v as Dictionary).duplicate(true)
	for k: String in keys:
		if d.has(k):
			d[k] = _negate(d[k])
	return d


func _negate(v: Variant) -> Variant:
	if v is float or v is int:
		return -float(v)
	if v is Dictionary:
		var d: Dictionary = (v as Dictionary).duplicate()
		for k in ["base", "amp"]:
			if d.has(k):
				d[k] = _negate(d[k])
		return d
	return v


func _mirror_legs(v: Variant) -> Variant:
	if not (v is Dictionary):
		return v
	var d: Dictionary = (v as Dictionary).duplicate(true)
	if d.has("shift"):
		d["shift"] = _negate(d["shift"])
	var l: Variant = d.get("foot_l", null)
	var r: Variant = d.get("foot_r", null)
	d.erase("foot_l")
	d.erase("foot_r")
	if r != null:
		d["foot_l"] = r
	if l != null:
		d["foot_r"] = l
	return d


func _next_phase(r: Run) -> void:
	# a phase that ran its time out does what it says at its end: take (grab), let go (release), throw
	var done_phase: Dictionary = {}
	if r.i >= 0 and r.i < r.phases.size() and r.t >= r.length - 1e-6:
		var ended: Dictionary = r.phases[r.i]
		done_phase = ended
		if view != "side":
			side_log.append([r.id, r.i, puppet.chains["hand_l"].side, puppet.chains["hand_r"].side])
		for ch in ["arm_l", "arm_r"]:
			var a: Variant = ended.get(ch, null)
			if not (a is Dictionary):
				continue
			if a.get("grab", false):
				var to: Variant = a.get("at", {}).get("to", "") if a.get("at", null) is Dictionary else ""
				events.append([steps, r.id, "grab", ch, to])
			if a.get("release", false):
				events.append([steps, r.id, "release", ch])
			if a.has("throw"):
				events.append([steps, r.id, "throw", ch, a["throw"]])
	r.i += 1
	r.t = 0.0
	if r.i >= r.phases.size():
		r.done = true
		for ch: String in r.owned:
			chans[ch].owner = null
			if ch.begins_with("arm") and not chans[ch].now.get("contact", false):
				_elbow[ch] = "out"            # (only how the next way off is drawn: straight from the body, or round)
		r.owned.clear()
		events.append([steps, r.id, "end"])
		return
	var ph: Dictionary = r.phases[r.i]
	r.length = float(ph.get("time", 0.5)) / r.speed
	r.ease_time = r.length
	for ch in ["arm_l", "arm_r"]:              # hands open to catch for as long as this phase lasts
		if ph.get(ch, null) is Dictionary and ph[ch].get("catch", false):
			events.append([steps, r.id, "catch", ch, r.length])
	var need := 0.0
	# reaching for a place low down: as far down as needed, and bent further where the legs cannot go lower
	var low := Vector3.ZERO
	if ph.get("legs", null) is Dictionary and ph["legs"].has("reach"):
		low = _reach(ph, str(ph["legs"]["reach"]))
	if ph.get("loop", false):
		if r.duration > 0.0:
			r.length = r.duration
		elif r.i == r.phases.size() - 1:
			r.length = INF
	for ch: String in r.owned:
		var c: Chan = chans[ch]
		c.from = c.now.duplicate()
		c.v0 = c.vel.duplicate()
		# The speed carried on (_carry) is for a value CUT OFF on its way. A phase that ran to its end on a curve
		# that ends at rest (inout, out) has brought its values to a stop: nothing to carry. (The speed measured a
		# step before the end is not zero yet, and carried over a long next phase it threw the hand a quarter turn
		# past where it was sent.) What swings on (an oscillation) or ends at speed (in, linear) is carried.
		if not done_phase.is_empty() and done_phase.get("ease", "inout") in ["inout", "out"]:
			var was: Variant = done_phase.get(ch, null)
			for key: String in c.v0.keys():
				var sp: Variant = was.get(key, null) if was is Dictionary else null
				if not (sp is Dictionary and sp.has("amp")):
					c.v0.erase(key)
		c.goal = {}
		if ch.begins_with("arm"):
			_still["hand_" + ch.right(1)] = 0       # (it has not arrived anywhere in this phase yet)
		if not ph.has(ch):
			continue
		if ch.begins_with("arm"):
			var at: Variant = ph[ch].get("at", null) if ph[ch] is Dictionary else "rest"
			if at != null:                      # no new place: the hand stays, and so does what it was doing
				_steady[ch] = not (at is Dictionary and at.has("amp"))
			if at != null and _steady[ch]:
				var goal: Vector2 = rest[ch]["at"] if at is String else (
						_polar(_landmark(ch, at, ph[ch].get("aim", null))) if at is Dictionary and at.has("to") else _polar(Vector2(at[0], at[1])) if at is Array else rest[ch]["at"])
				var way: float = _way(ch, c.now.get("at", rest[ch]["at"]), goal, _straight.get(ch, false) or
						(at is Dictionary and at.has("to") and _lm(at["to"])[4] == "down"))
				m["needed"] += way
				# a hand has a top speed and a top acceleration: a phase written for a hand starting from rest takes
				# longer when the hand starts far away (an action breaking into another one)
				# (a curve that starts fast, "out", accelerates about 3 times harder than an even one)
				var sharp: float = 20.0 if ph.get("ease", "inout") == "out" else 6.0
				need = maxf(need, maxf(1.5 * way / HAND_SPEED, sqrt(sharp * way / HAND_ACCEL)))
		var g: Variant = ph[ch]
		if g is String and g == "rest":
			c.goal = rest[ch].duplicate()
		elif ch.begins_with("arm") and g is Dictionary:
			c.goal = g
		elif g is Dictionary:
			c.goal = g
		if ch == "legs" and c.goal.has("jump"):
			phys.jump(float(c.goal["jump"]), float(c.goal.get("forward", 0.0)) * leg * (facing if view == "side" else 1.0))
		if ch == "legs" and c.goal.has("walk"):
			var gait: Dictionary = (c.goal.get("gait", {}) as Dictionary).duplicate() if c.goal.get("gait", {}) is Dictionary else {}
			if not gait.has("advance"):
				gait["advance"] = r.advance
			_start_walk(float(c.goal["walk"]) * leg, float(c.goal.get("speed", WALK_SPEED)) * r.speed * leg, gait)
			r.walking = true
			r.length = INF
		if ch == "legs" and c.goal.has("reach"):
			c.goal["drop"] = low.x
		if ch == "body" and low.y > 0.0 and c.goal.has("lean"):
			c.goal = c.goal.duplicate()
			var l0: float = float(c.goal["lean"]) if not (c.goal["lean"] is Dictionary) else 0.0
			c.goal["lean"] = (1.0 if l0 >= 0.0 else -1.0) * maxf(absf(l0), low.y)
			if low.z > 0.0:
				c.goal["chest"] = (1.0 if l0 >= 0.0 else -1.0) * low.z
		if ch == "legs" and c.goal.has("seat"):
			# down until the bottom of the pelvis is on the seat; the feet go forward to stand under the knees
			# what the hero sits on: the bottom of the pelvis, or the thighs where they hang lower (hip joints and
			# the thickness of a thigh under them)
			var seat_y: float = _rest_low.get("pelvis", floor_y)
			for f in hip:
				seat_y = maxf(seat_y, (_rest_body + hip[f]).y + 0.12 * leg)
			var hem: float = (floor_y - seat_y) / leg
			# a seat higher than the hips (a big armchair, a short hero): it gets up onto it, the body rises and the
			# legs hang off the edge, the feet off the floor (at most PERCH leg lengths up)
			var rise: float = clampf(float(c.goal["seat"]) - hem, 0.0, PERCH)
			c.goal["drop"] = maxf(hem - float(c.goal["seat"]), 0.0) - rise
			var back: float = -0.22 if view == "side" else 0.0      # (seen from the front a shift is a move ASIDE)
			if rise > 0.0:
				c.goal["shift"] = back
				for f in ["foot_l", "foot_r"]:
					if not c.goal.has(f):
						c.goal[f] = [0.32 + (0.05 if f == "foot_r" else 0.0), rise + 0.12]
			c.goal["shift"] = back
			# as far forward as the leg reaches from a hip this low (the body leans back by "shift")
			var hip_up: float = maxf(1.0 - float(c.goal["drop"]), 0.0)
			# (on the floor the legs lie out nearly straight: a bent knee there would lift the thigh past its joint)
			var floor_seat: bool = float(c.goal["seat"]) <= 0.15
			var long: float = 0.94 if floor_seat else 0.92
			var reach: float = sqrt(maxf(long * long - hip_up * hip_up, 0.0)) + float(c.goal["shift"])
			for f in ["foot_l", "foot_r"]:
				if not c.goal.has(f):
					var want: float = (reach if floor_seat else 0.55) + (0.05 if f == "foot_r" else 0.0)
					c.goal[f] = [minf(want, reach - (0.0 if f == "foot_r" else 0.05)), 0.0]
			_seated = true
		elif ch == "legs" and not c.goal.is_empty():
			_seated = bool(r.spec.get("seated", false))     # (a whole sit-down, on the way down and up too)
		if ch.begins_with("arm") and c.goal.has("aim"):
			c.goal["aim_w"] = 1.0
		elif ch.begins_with("arm") and c.goal.has("at"):
			c.goal["aim_w"] = 0.0
		if ch.begins_with("arm"):
			var look: String = c.goal.get("look", c.now.get("look", "auto"))
			var hand: String = "hand_" + ch.right(1)
			# a hand laid on the hero's OWN body (the face, the chest, the head: a landmark) has its palm on it, so it is
			# the BACK of the hand we see - whatever the action says, and not the palm the raised hand would show
			var goal_at: Variant = c.goal.get("at", null)
			var on_body: bool = goal_at is Dictionary and LANDMARKS.has(str((goal_at as Dictionary).get("to", "")))
			if on_body and look in ["palm", "auto"]:
				look = "back"
			if _fist_held(hand):
				puppet.set_skin(hand, "fist")
			elif look == "auto":
				puppet.release_skin(hand)
			else:
				puppet.set_skin(hand, _skin_of(hand, look))
			c.now["look"] = look
			# a hand leaving the body keeps its leave for the way off it: the law would throw it aside at once. Only for
			# THAT way: the phase after it starts from a place off the body (the leave carried on, a hand going from
			# "down" to "up" was drawn as a straight line in front of the body, bowed inward: across the face)
			# (left already: the phase before was the way off the body, and it took the hand out past the shoulder's
			# line; a hand still in front of the body goes on straight, as it left)
			var left_already: bool = bool(c.from.get("leaving", false)) and _cart(c.from.get("at", rest[ch]["at"])).x >= LEFT_OUT
			if left_already:
				_elbow[ch] = "out"            # (out in the open now: every way from here goes round the shoulder)
			var leaving: bool = bool(c.from.get("contact", false)) and not bool(c.goal.get("contact", false)) and not left_already
			c.now["contact"] = bool(c.goal.get("contact", false)) or leaving
			c.now["leaving"] = leaving
			var at_spec: Variant = c.goal.get("at", null)
			var was_front: bool = _elbow[ch] == "down" and not left_already   # leaving a place in front of the body (chin, chest)
			var to_body: bool = at_spec is Dictionary and at_spec.has("to")
			if to_body:
				_elbow[ch] = _lm(at_spec["to"])[4]
			elif not leaving and at_spec != null:
				_elbow[ch] = "out"
			# to the body and off it the hand goes straight, in front of the body; elsewhere round the shoulder
			# (only for places in front of the body: to the ears or the crown it goes round, outward, like any raised hand)
			# off a place in front of the body (wherever to) and onto one: straight, in front of the body; elsewhere
			# round the shoulder, outside
			_straight[ch] = (was_front and at_spec != null) or (_elbow[ch] == "down" and to_body and c.now["contact"])
			# THE ELBOW. Its side belongs to the pose: worked out here, once, from where the hand is sent (or said by
			# the action: "elbow"), never from what the arm did before. So a pose looks the same after any action.
			# If the arm has to change sides for it, it does so half way there, straightened (_arm_at).
			if view != "side":
				var e_want: Variant = c.goal.get("elbow", null)
				var new_place: bool = at_spec is String or at_spec is Array or (at_spec is Dictionary and
						(at_spec.has("to") or at_spec.get("base", null) is Array) and not at_spec.get("circle", false))
				if new_place or (e_want is String and ELBOW_DIR.has(e_want)):
					var g_at: Vector2 = c.now.get("at", rest[ch]["at"])
					if at_spec is String:
						g_at = rest[ch]["at"]
					elif at_spec is Dictionary and at_spec.has("to"):
						g_at = _polar(_landmark(ch, at_spec, c.goal.get("aim", null)))
					elif at_spec is Dictionary and at_spec.get("base", null) is Array:
						g_at = _polar(Vector2(at_spec["base"][0], at_spec["base"][1]))
					elif at_spec is Array:
						g_at = _polar(Vector2(at_spec[0], at_spec[1]))
					if not new_place:
						c.goal["at"] = g_at              # the elbow alone changes: the hand stays, the arm still swings over
					var side_goal: float = _pose_side(ch, at_spec, g_at, e_want if e_want is String else "")
					_side_goal[ch] = side_goal
					var chain: Variant = puppet.chains[hand]
					_over.erase(ch)
					if side_goal != chain.side:
						if float(c.now.get("at", rest[ch]["at"]).y) >= 0.9:
							puppet.set_bend(hand, side_goal)        # the arm is straight now: over at once, unseen
						else:
							_over[ch] = [r, r.i, side_goal, false]
							need = maxf(need, 0.3)                   # (time to unfold and fold)
							# (the way out to a straight arm and back is part of the way the hand has to go)
							m["needed"] += 2.0 * maxf(CROSS_REACH - 0.5 * (float(c.now.get("at", rest[ch]["at"]).y) + g_at.y), 0.0)
					else:
						puppet.set_bend(hand, side_goal)


	if need > r.ease_time and not r.walking:
		if r.length == r.ease_time:
			r.length = need
		r.ease_time = need


static func _ease(u: float, kind: String) -> float:
	u = clampf(u, 0.0, 1.0)
	match kind:
		"linear":
			return u
		"out":                        # fast, but from standing still
			return 1.0 - pow(1.0 - u, 4.0) * (1.0 + 4.0 * u)
		"in":
			return u * u * u
	return u * u * (3.0 - 2.0 * u)


## Value of one key in a phase: eased from where it was to the base, plus the swing.
func _value(r: Run, c: Chan, key: String, spec: Variant, rest_v: Variant, scale_by_energy: bool) -> Variant:
	var e: float = r.energy if scale_by_energy else 1.0
	var base: Variant = spec
	var amp: Variant = null
	var rate := 0.0
	var ph0 := 0.0
	var given := true
	if spec is Dictionary:
		given = spec.has("base")
		base = spec.get("base", c.from.get(key, rest_v))
		amp = spec.get("amp", null)
		rate = float(spec.get("rate", 1.0)) * r.speed
		ph0 = float(spec.get("phase", 0.0))
	if base is String and base == "rest":
		base = rest_v
	if base is Array:
		base = Vector2(base[0], base[1])
	if (base is float or base is int) and scale_by_energy and given:
		base = float(rest_v) + (float(base) - float(rest_v)) * e
	var ph: Dictionary = r.phases[r.i]
	var u: float = _ease(r.t / minf(r.length, r.ease_time), ph.get("ease", "inout"))
	var from: Variant = c.from.get(key, rest_v)
	var v: Variant
	if base is Vector2:
		v = (from as Vector2).lerp(base, u) if from is Vector2 else base
	else:
		v = lerpf(float(from), float(base), u)
	v = _carry(r, c, key, v)
	if amp != null:
		var env: float = smoothstep(0.0, minf(RAMP, 0.5 / maxf(rate, 0.1)), r.t)
		var s: float = sin(TAU * (rate * r.t + ph0)) * env * e
		if amp is Array:
			v = (v as Vector2) + Vector2(amp[0], amp[1]) * s
		else:
			v = float(v) + float(amp) * s
	return v


# ----------------------------------------------------------------------------- one step

func step() -> void:
	steps += 1
	t += DT
	for r in runs:
		if r.done:
			continue
		r.t += DT
		if r.walking and _gait.is_empty():
			r.walking = false
			r.length = r.t
		if r.t >= r.length:
			_advance_values(r)
			_check_reached(r)
			_next_phase(r)
		else:
			_advance_values(r)
	runs = runs.filter(func(r: Run) -> bool: return not r.done)
	if not _next.is_empty() and runs.is_empty():
		var n: Array = _next
		_next = []
		clean_run = play(n[0], n[1])
	for ch in CHANNELS:                      # how fast every value moves: a new phase carries it on (_carry)
		var c: Chan = chans[ch]
		for key: String in c.now:
			var v: Variant = c.now[key]
			if c.prev.has(key) and (v is float or v is Vector2) and typeof(v) == typeof(c.prev[key]):
				var d: Variant = v - c.prev[key]
				if key == "at":
					d = Vector2(wrapf((d as Vector2).x, -PI, PI), (d as Vector2).y)
				c.vel[key] = d / DT
			c.prev[key] = v
	_apply()
	_measure()


## At the end of a phase that held a hand still for a while, the hand must be where it was sent.
func _check_reached(r: Run) -> void:
	var ph: Dictionary = r.phases[r.i]
	if r.length < 0.4:
		return
	for ch: String in ["arm_l", "arm_r"]:
		# (only where the place has stood still a moment: a hand following a moving head is behind it by design)
		if r.owned.has(ch) and _steady.get(ch, false) and _still.get("hand_" + ch.right(1), 0) >= 12 				and not _floor_held.get("hand_" + ch.right(1), false):   # (a hand held up by the floor is not a miss)
			m["miss"] = maxf(m["miss"], hand_miss(ch))


func _advance_values(r: Run) -> void:
	for ch: String in r.owned:
		var c: Chan = chans[ch]
		for key: String in c.goal:
			if key in ["look", "contact", "jump", "forward", "walk", "speed", "seat", "grab", "release", "throw", "reach", "catch", "gait", "elbow"]:
				continue
			var spec: Variant = c.goal[key]
			if ch.begins_with("arm") and key == "at":
				c.now["at"] = _arm_at(r, c, ch, spec)
			else:
				c.now[key] = _value(r, c, key, spec, rest[ch].get(key, 0.0), key in ["lean", "chest", "tilt", "wrist"])
				# a foot moved along the floor is lifted on the way, never dragged (law)
				if ch == "legs" and key.begins_with("foot") and c.from.get(key) is Vector2:
					var f0: Vector2 = c.from[key]
					var g: Variant = spec.get("base", spec) if spec is Dictionary else spec
					var g1: Vector2 = Vector2(g[0], g[1]) if g is Array else (rest[ch][key] if g is String else f0)
					var dx: float = absf(g1.x - f0.x)
					if dx > 0.01:
						var ph: Dictionary = r.phases[r.i]
						var u: float = clampf(r.t / minf(r.length, r.ease_time), 0.0, 1.0)
						c.now[key] = (c.now[key] as Vector2) + Vector2(0.0, minf(0.12, dx * 0.6) * sin(PI * u))


## A hand's place, eased round the shoulder by the short way (polar: angle, distance), reaching out only when its
## elbow has to change sides on the way (the old _swing rule of stage.gd, now on a timed curve).
func _arm_at(r: Run, c: Chan, ch: String, spec: Variant) -> Vector2:
	var goal: Vector2
	var swing := Vector2.ZERO
	if spec is Dictionary and spec.get("circle", false):
		# a circle round its centre ("base"), full size from the start: the phase before puts the hand on it
		# (at base + [amp out, 0] for phase 0); growing from nothing it would pass through the shoulder
		var cr: float = float(spec.get("rate", 1.0)) * r.speed
		var ramp: float = 0.35                      # it gets up to speed (no jerk as it starts)
		var turns: float = cr * (r.t * r.t / (2.0 * ramp) if r.t < ramp else r.t - ramp * 0.5)
		var cw: float = TAU * (turns + float(spec.get("phase", 0.0)))
		var ca: Array = spec["amp"]
		var cb: Array = spec.get("base", [0.0, 0.0])
		return _polar(Vector2(cb[0], cb[1]) + Vector2(ca[0] * cos(cw), ca[1] * sin(cw)) * r.energy)
	if spec is Dictionary and spec.has("amp"):
		var rate: float = float(spec.get("rate", 1.0)) * r.speed
		var env: float = smoothstep(0.0, minf(RAMP, 0.5 / maxf(rate, 0.1)), r.t)
		var a: Array = spec["amp"]
		var w: float = TAU * (rate * r.t + float(spec.get("phase", 0.0)))
		if spec.get("circle", false):                  # round and round (a windmill arm), not to and fro
			swing = Vector2(a[0] * cos(w), a[1] * sin(w)) * env * r.energy
		else:
			swing = Vector2(a[0], a[1]) * sin(w) * env * r.energy
	if spec is Dictionary and (spec as Dictionary).has("to"):
		goal = _polar(_landmark(ch, spec, c.goal.get("aim", null)))
		if str(spec["to"]).begins_with("@"):
			# a thing in the scene moves against the shoulder as the body goes down to it: the way the hand has to
			# go grows by as much (the path measure would call the chase a detour)
			var gw: Array = _goal_was.get(ch, [])
			if not gw.is_empty() and gw[0] == r and gw[1] == r.i:
				m["needed"] += _cart(goal).distance_to(gw[2])
			_goal_was[ch] = [r, r.i, _cart(goal)]
	elif spec is String and spec == "rest":
		goal = rest[ch]["at"]
	elif spec is Vector2:                       # already (angle, distance): the rest place
		goal = spec
	else:
		var b: Variant = spec.get("base", null) if spec is Dictionary else spec
		goal = rest[ch]["at"] if b == null else _polar(Vector2(b[0], b[1]))
	var ph: Dictionary = r.phases[r.i]
	var u: float = _ease(r.t / minf(r.length, r.ease_time), ph.get("ease", "inout"))
	var from: Vector2 = c.from.get("at", rest[ch]["at"])
	# a phase that takes the elbow over to its other side: the arm reaches out towards the middle of the way, the
	# elbow goes over there (on a straight arm, the only place it can), and the arm folds again
	var unfold := 0.0
	var fl: Array = _over.get(ch, [])
	if not fl.is_empty() and fl[0] == r and fl[1] == r.i:
		unfold = smoothstep(0.0, 1.0, clampf(1.0 - (absf(u - 0.5) - 0.12) / 0.33, 0.0, 1.0))
		if u >= 0.5 and not fl[3]:
			fl[3] = true
			puppet.set_bend("hand_" + ch.right(1), float(fl[2]))
	if _straight.get(ch, false):
		var a: Vector2 = _cart(from)
		var b: Vector2 = _cart(goal)
		var line: Vector2 = a.lerp(b, u)
		# the line must keep clear of the shoulder (where an arm folds up and its direction is undefined): bowed
		# away from it as a smooth curve when it would come too close
		var ab: Vector2 = b - a
		var k: float = clampf(-a.dot(ab) / maxf(ab.length_squared(), 1e-6), 0.0, 1.0)
		var close: Vector2 = a + ab * k
		var clear: float = 1.4 * MIN_REACH
		var n: Vector2 = Vector2(-ab.y, ab.x).normalized()
		# which way round is decided ONCE, as the phase starts: the goal (a face, a hip) moves with the body, and a
		# side chosen anew every step would throw the hand from one side of the shoulder to the other
		var bow: Array = _bow.get(ch, [])
		if bow.is_empty() or bow[0] != r or bow[1] != r.i:
			var way := 0.0
			var front := Vector2(1.0 if view == "side" else -1.0, 0.0)  # in profile the front is forward
			# only a line that passes the shoulder on its way: one that merely ends near it (a hand going to a hip
			# high on a short body) cannot be helped by a detour
			if close.length() < clear and ab.length() > 0.05 and close.dot(front) < clear and k > 0.1 and k < 0.9:
				# round the front of the body (inward of the shoulder), where a hand goes from the face to the hip;
				# a line across the body (above or under the shoulder) rounds it on the side it already passes
				way = 1.0 if n.dot(front) >= 0.0 else -1.0
				if absf(n.dot(front)) < 0.5 and absf(close.dot(n)) > 0.02:
					way = signf(close.dot(n))
			bow = [r, r.i, way]
			_bow[ch] = bow
		if bow[2] != 0.0:
			n *= float(bow[2])
			var side: float = close.dot(n)                 # how far the line already is on that side
			var ctrl: Vector2 = (a + b) * 0.5 + n * 2.0 * maxf(clear - side, 0.0)
			line = a * (1.0 - u) * (1.0 - u) + ctrl * 2.0 * u * (1.0 - u) + b * u * u
		var on_line: Vector2 = _polar(line + swing) if swing != Vector2.ZERO else _polar(line)
		on_line.y = lerpf(on_line.y, maxf(on_line.y, CROSS_REACH), unfold)
		return _carry(r, c, "at", on_line)
	var dd: float = wrapf(goal.x - from.x, -PI, PI)
	# (a hand that may touch the body and only trembles across that line - fingers on a pipe at the chin, a strum -
	# is not crossing the body: sent round the outside, it flew out to the side and back every time)
	var small_on_body: bool = absf(dd) < 0.35 and bool(c.now.get("contact", false))
	if absf(dd) > 0.05 and not small_on_body and _sweeps(from.x, from.x + dd, PI):
		dd -= signf(dd) * TAU              # the short way would cross the body: round the outside
	var to: float = from.x + dd
	var ang: float = lerpf(from.x, to, u)
	var dist: float = lerpf(from.y, goal.y, u)
	dist = lerpf(dist, maxf(dist, CROSS_REACH), unfold)
	var here: Vector2 = _carry(r, c, "at", Vector2(ang, dist))
	if OS.get_environment("MOTION_ARM") == ch and steps % 6 == 0:
		print("ARM %d ph=%d t=%.2f u=%.2f from=%s goal=%s ang/dist=(%.2f, %.2f) here=%s swing=%s v0=%s len=%.2f ease=%.2f" % [steps, r.i, r.t, u, str(from), str(goal), ang, dist,
			str(here), str(swing), str(c.v0.get("at")), r.length, r.ease_time])
	if swing != Vector2.ZERO:
		return _polar(_cart(here) + swing)
	return here


## Where a landmark of this hero's body is, as [out, down] arm lengths from the hand's shoulder. The WRIST goes a
## hand's length short of it, so the hand itself lands on the place.
func _landmark(ch: String, spec: Dictionary, aim: Variant = null) -> Vector2:
	if str(spec["to"]).begins_with("@"):
		return _scene_point(ch, spec, aim)
	var lm: Array = _lm(spec["to"])
	var part: Variant = puppet.parts.get(lm[0])
	var s := _sign(ch)
	var ls := _lsign(ch)
	var box: Rect2 = _face(part) if lm[3] in ["face", "edge"] else part.painted
	var local := box.get_center() + Vector2((float(lm[1]) + float(spec.get("dx", 0.0))) * ls * box.size.x * 0.5,
			(float(lm[2]) + float(spec.get("dy", 0.0))) * box.size.y * 0.5)
	if lm[3] == "edge" and part.edge_r.size() > 0:
		var row: int = clampi(int(local.y - part.sprite.position.y), 0, part.edge_r.size() - 1)
		var vh: Node = part.node.get_node_or_null("video_head")
		var side: float = part.edge_r[row] if ls > 0.0 else part.edge_l[row]
		if vh != null:                       # a recorded head: its own width
			side = box.get_center().x + ls * box.size.x * 0.62
		local.x = side + ls * (float(lm[1]) + float(spec.get("dx", 0.0))) * hand_len[ch] / absf(puppet.scale.x)
	var world: Vector2 = part.node.to_global(local)
	var sh: Vector2 = _shoulder_at(ch, puppet.body_position())
	# the hand lies along the forearm, so the wrist is a hand's length back along it: from the shoulder for an arm
	# that reaches out, from an elbow held low (half an arm under the shoulder) for an arm that comes up in front
	var elbow: Vector2 = sh + (Vector2(0.1 * arm * s, 0.5 * arm) if lm[4] == "down" else Vector2.ZERO)
	var along: Vector2 = (world - elbow).normalized()
	if aim != null:                          # the hand points this way: the wrist is a hand's length behind it
		along = Vector2(cos(deg_to_rad(float(aim))) * s, sin(deg_to_rad(float(aim))))
	var wrist: Vector2 = world - along * hand_len[ch] * 0.9
	var d: Vector2 = wrist - sh
	return Vector2(d.x * s, d.y) / arm


## How far down (leg lengths) the body must go for the arm the phase sends to `to` to reach it, with the lean the
## phase asks for (a thing on the floor: squat and bend; on a table: not at all); and if the legs cannot go that
## low (a long skirt, short legs), how far the body must bend instead: x = the squat, y = the lean (degrees, 0 = the
## phase's own lean will do), z = the chest bent on top of it (profile only).
## In profile a stoop is the pelvis tipped forward a little (STOOP_HIPS at most) and the BACK bent the rest of the
## way: tipped further, a squatting thigh met the belly at its limit and the foot was pushed off its place. Seen
## from the front a lean is a bend aside, and that is soon over the feet.
func _reach(ph: Dictionary, to: String) -> Vector3:
	var limit: float = minf(max_drop, DEEP_SQUAT)
	var lean0: float = absf(float(ph.get("body", {}).get("lean", 0.0))) if ph.get("body", null) is Dictionary and not (ph["body"].get("lean", 0.0) is Dictionary) else 0.0
	var d: float = _reach_drop(ph, to, lean0, 0.0)
	# (a fist that comes within a few px of the handle closes on it; only a skirt that stops the squat makes the
	# body bend further: a sideways bend that deep moves the hips off the feet)
	if d < limit + 0.08:
		return Vector3(minf(d, limit), 0.0, 0.0)
	var lean: float = lean0
	var chest := 0.0
	var lim: float = limit
	if view == "side":
		var bend: float = lean0
		while bend < STOOP_HIPS + STOOP_BACK:
			bend = minf(bend + 5.0, STOOP_HIPS + STOOP_BACK)
			lean = minf(bend, maxf(STOOP_HIPS, lean0))
			chest = bend - lean
			d = _reach_drop(ph, to, lean, chest)
			if d < lim + 0.08:
				break
	else:
		var most: float = 35.0 if max_drop < DEEP_SQUAT else 25.0
		if ph.has("arms"):
			most = lean0          # (a thing in both hands seen from the front: straight down, never a bend aside)
		# leaning, one hip goes down by its distance from the middle: the squat is that much less, or the knee on
		# that side would have to fold past its limit (the foot is pushed off its place)
		var hip_x: float = absf((hip.values()[0] as Vector2).x) if not hip.is_empty() else 0.0
		while lean < most:
			lean = minf(lean + 5.0, most)
			lim = limit - 1.6 * hip_x * sin(deg_to_rad(lean)) / leg
			d = _reach_drop(ph, to, lean, 0.0)
			if d < lim + 0.08:
				break
	if OS.has_environment("REACH_DEBUG"):
		print("REACH %s view=%s max_drop=%.2f limit=%.2f need=%.2f lim=%.2f lean=%.0f chest=%.0f arm/leg=%.2f" % [puppet.name, view, max_drop, limit, d, lim, lean, chest, arm / leg])
	return Vector3(minf(d, lim), lean, chest)


func _reach_drop(ph: Dictionary, to: String, lean_deg: float, chest_deg: float) -> float:
	var f: Variant = points.get(to, null)
	if f == null:
		return 0.0
	var ch := "arm_r"
	for a in ["arm_l", "arm_r"]:
		var spec: Variant = ph.get(a, null)
		if spec is Dictionary and spec.get("at", null) is Dictionary and spec["at"].get("to", "") == to:
			ch = a
	var target: Vector2 = (f as Callable).call(ch, {})
	var lean: float = deg_to_rad(lean_deg)
	var off: Vector2 = shoulder[ch]
	var sh: Vector2 = _rest_body + off
	var way: float = signf(target.x - sh.x)
	if view == "side":
		# the pelvis turns round the body's point, the chest round the waist on top of it (as _apply bends them:
		# the chest's own angle is its bend and half the lean)
		var c_world: float = deg_to_rad(lean_deg + clampf(chest_deg + 0.5 * lean_deg, -25.0, 100.0))
		sh = _rest_body + _waist.rotated(lean * way) + (off - _waist).rotated(c_world * way)
		sh.x -= (0.45 * sin(lean) + 0.35 * sin(deg_to_rad(chest_deg))) * leg * way   # (the hips go back: _apply)
	else:
		var r: float = off.length()
		sh.y += r * (1.0 - cos(lean))
		sh.x += r * sin(lean) * way
		sh.x -= 0.45 * sin(lean) * leg * way          # (the hips go back as far as the law in _apply sends them)
	var reach: float = 0.99 * arm + 0.75 * hand_len[ch]       # a straight arm: picking a thing up, it is
	var dx: float = absf(target.x - sh.x)
	var v: float = sqrt(maxf(reach * reach - dx * dx, 0.09 * reach * reach))
	return maxf((target.y - v - sh.y) / leg, 0.0)


## How far from the body's point (px, out on the side of this arm; in profile, in front) a thing lying on the floor
## is best put for this arm to pick it up: under its shoulder as the body bends down to it (the lean _reach would
## end with), never closer than the feet allow. A fixed share of the arm left the shoulder of a short-armed hero
## far to the side of it, and it could not reach.
func floor_reach_x(ch: String) -> float:
	var off: Vector2 = shoulder[ch]
	var way: float = _sign(ch)
	var x: float
	if view == "side":
		var lean: float = deg_to_rad(STOOP_HIPS)
		var chest := 30.0
		var c_world: float = deg_to_rad(STOOP_HIPS + clampf(chest + 0.5 * STOOP_HIPS, -25.0, 100.0))
		var sh: Vector2 = _waist.rotated(lean * way) + (off - _waist).rotated(c_world * way)
		x = sh.x * way - (0.45 * sin(lean) + 0.35 * sin(deg_to_rad(chest))) * leg
	else:
		var lean: float = deg_to_rad(35.0 if max_drop < DEEP_SQUAT else 25.0)
		x = off.x * way + off.length() * sin(lean) - 0.45 * sin(lean) * leg
	return maxf(x, 0.3 * arm)


## Whether this hand is closed round what it holds (a thing on the open palm is held without a fist).
func _fist_held(h: String) -> bool:
	return holding.has(h) and not (holding[h] is String and holding[h] in ["open", "edge"])


## A place in the scene (an item's grip): the middle of the fist goes there, the wrist a fist's length back along
## the way the arm reaches. Unknown, the hand stays where it hangs.
func _scene_point(ch: String, spec: Dictionary, aim: Variant) -> Vector2:
	var s := _sign(ch)
	var sh: Vector2 = _shoulder_at(ch, puppet.body_position())
	var f: Variant = points.get(spec["to"], null)
	if f == null:
		return rest[ch]["at"] if rest.has(ch) else Vector2(0.0, 0.9)
	var world: Vector2 = (f as Callable).call(ch, spec) + Vector2(float(spec.get("dx", 0.0)) * s, float(spec.get("dy", 0.0))) * arm
	var along: Vector2 = (world - sh).normalized()
	if aim != null:
		along = Vector2(cos(deg_to_rad(float(aim))) * s, sin(deg_to_rad(float(aim))))
	var wrist: Vector2 = world - along * hand_len[ch] * 0.75
	var d: Vector2 = (wrist - sh).limit_length(0.995 * arm)      # out of reach: as far as the arm goes, that way
	return Vector2(d.x * s, d.y) / arm


## The FACE of the head, in the head's own frame: the recorded one when worn, the hole of a worn piece, or else
## the lower middle of the painted head (above it there may be a hat, hair, a crown).
func _face(part: Variant) -> Rect2:
	var vh: Node = part.node.get_node_or_null("video_head")
	if vh != null:
		var q: float = vh.rect.size.y
		var chin: float = vh.rect.position.y + 0.882 * q
		var h: float = 0.588 * q
		return Rect2(Vector2(vh.rect.get_center().x - 0.5 * h * 0.8, chin - h), Vector2(h * 0.8, h))
	var hole: Dictionary = puppet.rig["parts"]["head"].get("face", {})
	if not hole.is_empty():
		var size := Vector2(hole["size"][0], hole["size"][1])
		return Rect2(Vector2(hole["center"][0], hole["center"][1]) - part.pivot - size * 0.5, size)
	var b: Rect2 = part.painted
	return Rect2(b.position + Vector2(0.18 * b.size.x, 0.38 * b.size.y), Vector2(0.64 * b.size.x, 0.56 * b.size.y))


func _apply() -> void:
	var p := puppet
	var lg: Dictionary = chans["legs"].now
	var bd: Dictionary = chans["body"].now
	var hd: Dictionary = chans["head"].now
	phys.squat = (float(lg["drop"]) if _seated else minf(float(lg["drop"]), max_drop)) * leg
	phys.max_sink = INF if _seated or max_drop >= 0.3 else max_drop * leg     # seated, the cloth folds on the lap
	if not _gait.is_empty():
		var gu: float = clampf(_gait["t"] / _gait["dur"], 0.0, 1.0)
		phys.squat -= (float(_gait.get("bob", WALK_BOB)) + float(_gait.get("hop", 0.0))) * leg * sin(PI * gu)   # up over the standing foot
	var body := phys.step(false, phys.pos)
	if not _gait.is_empty() and not phys.airborne:
		body = _walk_step(body)
	# the swing of the arms grows as a walk starts and dies out after it, never cut
	if not _gait.is_empty():
		_walk_u = clampf(_gait["t"] / _gait["dur"], 0.0, 1.0)
		_walk_side = _gait["swing"]
	_walk_w = move_toward(_walk_w, 1.0 if not _gait.is_empty() and not _gait["stopping"] else 0.0, DT / 0.3)
	var tt := float(steps)
	var w: float = life * 0.035 * leg * sin(tt * TAU / 600.0)     # weight from foot to foot, every 10 s
	body.x += float(lg["shift"]) * leg * (facing if view == "side" else 1.0) + w
	# leaning or bending, the hips go the other way so the weight stays over the feet (law)
	if not _seated and not phys.airborne:
		var over_w: float = sin(deg_to_rad(float(bd["lean"]))) * 0.45 + sin(deg_to_rad(float(bd["chest"]))) * 0.35
		body.x -= over_w * leg * (facing if view == "side" else 1.0)     # (lean + is forward in profile)
	# on one foot the body moves over it (law): half way, smoothly
	var standing: Array = []
	for f: String in foot_home:
		var g: Variant = chans["legs"].goal.get(f, null)          # (a foot about to rise counts as risen: the
		var going_up: bool = g is Array and float(g[1]) > 0.01     # weight goes over before it leaves the floor)
		if (lg[f] as Vector2).y <= 0.01 and not going_up and _gait.get("swing", "") != f:
			standing.append(f)
	var over := 0.0
	if standing.size() == 1 and _gait.is_empty() and not phys.airborne:
		# where the weight really is (every painted part, a step ago) goes over the middle of that foot
		var foot_mid: float = _world_box(standing[0]).get_center().x
		over = _balance + (foot_mid - _weight_x())
	_balance = move_toward(_balance, over, 4.0 * leg * DT)
	body.x += _balance
	body.x = clampf(body.x, phys.walls.x, phys.walls.y)
	var lean: float = float(bd["lean"]) + life * 1.2 * sin(tt * 0.045) + _lean_fix
	if _walk_w > 0.0 and not _gait_look.is_empty():
		# a waddle rocks over the standing foot; a drunk's lean wanders
		var foot_sign: float = 1.0 if _walk_side == "foot_r" else -1.0
		lean += float(_gait_look.get("sway", 0.0)) * foot_sign * sin(PI * _walk_u) * _walk_w
		lean += float(_gait_look.get("wobble", 0.0)) * 9.0 * sin(t * 1.7) * sin(t * 0.63 + 1.0) * _walk_w
	if phys.airborne:
		_grounded = false
	else:
		if not _grounded:                       # landed: the feet stand where they came down
			for f: String in foot_home:
				foot_home[f] = p.target_position(f)
			_grounded = true
		# a planted leg is never stretched past its length: the body comes down instead (law). The hip joint is
		# where the leaning pelvis takes it (folded forward in a stoop it goes back and up a long way: counted at
		# rest, the leg could not reach its foot and the foot slid off its place)
		var turn: float = deg_to_rad(lean) * signf(p.scale.x)
		for f: String in foot_home:
			var lift: Vector2 = lg[f]
			if lift.y > 0.01 or _gait.get("swing", "") == f:
				continue
			var ankle: Vector2 = foot_home[f]
			var reach: float = REACH * leg
			var hip_at: Vector2 = (hip[f] as Vector2).rotated(turn)
			# (the hips sent back by a deep stoop stop where the leg still reaches its foot)
			var off_x: float = ankle.x - (body.x + hip_at.x)
			if absf(off_x) > 0.85 * reach:
				body.x += off_x - signf(off_x) * 0.85 * reach
			var hp: Vector2 = body + hip_at
			var dx: float = ankle.x - hp.x
			if absf(dx) < reach:
				body.y = maxf(body.y, ankle.y - sqrt(reach * reach - dx * dx) - hip_at.y)
	body.y -= _lift_fix
	p.set_body(body, lean)
	# a skirt or a robe hangs plumb from the waist whatever the body does (on its spring, so it sways after)
	var skirt: Variant = p.parts.get("skirt")
	if skirt != null:
		# (seated, the cloth lies on the raised thighs by itself: soft_skirt.gd)
		# (a stiff one: with the hips. And seen from the front, a body that lies down takes its skirt with it:
		# from 25 to 45 degrees of lean the skirt stops hanging plumb and goes with the body, along the legs.
		# Held plumb on a lying body it points into the floor and has to be squashed to a strip.)
		var plumb: float = 1.0 if view == "side" else 1.0 - smoothstep(25.0, 45.0, absf(lean))
		skirt.goal = clampf(-deg_to_rad(lean) * plumb, skirt.lo, skirt.hi) if cloth != null else 0.0
	p.set_handle_angle("chest", float(bd["chest"]) + 0.5 * float(bd["lean"]))
	p.set_handle_angle("head", float(hd["tilt"]) + life * 2.5 * sin(tt * 0.07))
	# the head drawn into the collar (+) or stretched up (-), in shares of its height; the shoulders raised (+) or
	# dropped (-) in arm lengths, capped so the arm never leaves its socket by more than a puppet's joint allows
	var kk: float = maxf(absf(p.scale.y), 0.001)
	if p.parts.has("head"):
		var hh: float = (p.parts["head"].painted as Rect2).size.y
		p.set_shift("head", Vector2(0.0, clampf(float(hd.get("drop", 0.0)), -0.15, 0.25) * hh))
	for ch2 in ["arm_l", "arm_r"]:
		var up: float = clampf(float(chans[ch2].now.get("shoulder", 0.0)), -0.08, 0.16)
		p.set_shift(p.chains["hand_" + ch2.right(1)].a.name, Vector2(0.0, -up * arm / kk))
	if not phys.airborne:
		for f: String in foot_home:
			var lift: Vector2 = lg[f]
			var s := _sign(f)
			p.set_target(f, (foot_home[f] as Vector2) + Vector2(lift.x * s, -lift.y) * leg)
	for ch in ["arm_l", "arm_r"]:
		var c: Chan = chans[ch]
		var h: String = "hand_" + ch.right(1)
		var s := _sign(ch)
		var where: Vector2 = _cart(_fold_limit(_stretch(ch, c.now["at"])))
		if _walk_w > 0.0 and c.owner == null:        # arms swing against the legs while walking
			var same: float = 1.0 if _walk_side.right(1) == ch.right(1) else -1.0
			var phase: float = -same * cos(PI * _walk_u) * _walk_w      # the arm on the swinging leg's side goes back
			var size: float = float(_gait_look.get("arms", 1.0))
			var bend: float = float(_gait_look.get("bend", 0.0)) * _walk_w
			if bend > 0.0:                                    # a run: the elbows bent, the fists pump (forward and up)
				where = where.lerp(Vector2(0.05 if view == "side" else 0.44, 0.45), bend)   # (seen from the front the fists pump beside the body, never into it)
				where.y -= 0.12 * bend * phase
			if view == "side":
				where.x += 0.22 * size * phase
			else:
				where.y -= 0.03 * size * absf(phase)
		var target: Vector2 = _shoulder_at(ch, body) + Vector2(where.x * s, where.y) * arm
		if not c.now.get("contact", false) and view != "side":     # in profile arms pass before and behind the body
			target = _out_of_body(target, s, ch)
		# a thing carried with both hands is HELD: hands no action moves stay on its sides, where it is carried
		# (law). Without it the arms hang and the crate floats between them.
		var carrying: bool = c.owner == null and carry_spec.has(ch)
		_carry_w[ch] = move_toward(_carry_w.get(ch, 0.0), 1.0 if carrying else 0.0, DT / 0.35)
		if carrying:
			var lm: Vector2 = _landmark(ch, carry_spec[ch])
			_carry_last[ch] = Vector2(lm.x * s, lm.y) * arm
		if _carry_w[ch] > 0.0 and _carry_last.has(ch):
			target = target.lerp(_shoulder_at(ch, body) + _carry_last[ch], smoothstep(0.0, 1.0, _carry_w[ch]))
		# THE ELBOW of an arm no action moves. A law that takes such an arm somewhere (running: bent, pumping; a
		# deep squat: on the knee; a thing in both hands: on its side) gives it the side of THAT place; when the law
		# lets go, the side of the arm's own pose again. Never just whatever the last action left: a run after a
		# clap had its arms crossed, a run from rest had not.
		if view != "side":
			var law_side: Variant = null
			if _carry_w.get(ch, 0.0) > 0.5 and carry_spec.has(ch) and _carry_last.has(ch):
				law_side = _pose_side(ch, carry_spec[ch], _polar(Vector2(_carry_last[ch].x * s, _carry_last[ch].y) / arm), "")
			elif _on_knee.get(ch, 0.0) > 0.5:
				law_side = _rest_side[ch]
			elif c.owner == null and _walk_w > 0.5 and float(_gait_look.get("bend", 0.0)) > 0.3:
				law_side = _rest_side[ch]
			var want_side: float = law_side if law_side != null else float(_side_goal.get(ch, _rest_side[ch]))
			var ov: Array = _over.get(ch, [])
			var planned: bool = not ov.is_empty() and not ov[3] and ov[0] == c.owner     # (it goes over half way: _arm_at)
			if not planned and want_side != p.chains[h].side:
				p.set_bend(h, want_side)             # (the arm straightens while it swings over: _stretch)
		# squatting deep, a hand nothing is done with rests on its knee (law)
		# (it goes there and back over a third of a second: an action letting go of the hand must not throw it there)
		var free_hand: bool = c.owner == null and not holding.has(h) and not _seated and not phys.airborne and _gait.is_empty()
		var kw_want: float = smoothstep(0.03, 0.16, phys.squat / leg) if free_hand else 0.0
		_on_knee[ch] = move_toward(_on_knee.get(ch, 0.0), kw_want, DT / 0.35)
		var thigh: Variant = p.parts.get("thigh_" + ch.right(1))
		if _on_knee[ch] > 0.0 and thigh != null:
			var knee: Vector2 = p.to_global(thigh.xf * (thigh.center * 2.0))
			target = target.lerp(knee + Vector2(0.15 * hand_len[ch] * s, -0.7 * hand_len[ch]), smoothstep(0.0, 1.0, _on_knee[ch]))
		var gap: float = maxf(FLOOR_GAP * arm, 1.9 * hand_len[ch])     # the whole hand stays above the floor
		gap = maxf(gap, 0.8 * hand_len[ch] + float(hold_low.get(h, 0.0)))   # ...and what it holds (a mug under the fist)
		# (a thing just taken hold of from the floor raises the limit at once; the hand goes up to it smoothly, not
		# in one step: it was a jump of a seventh of an arm the moment a crate was gripped)
		var g0: float = _gap_now.get(h, gap)
		gap = gap if gap <= g0 else move_toward(g0, gap, GAP_RISE * arm * DT)
		_gap_now[h] = gap
		_floor_held[h] = target.y > floor_y - gap
		# it slows down as it comes to the floor instead of stopping dead on it (a hard stop is a jerk): over the
		# last `band` px the way down is squeezed smoothly, so it never quite gets to the limit
		var band: float = 0.5 * gap
		var y0: float = floor_y - gap - band
		if target.y > y0:
			target.y = y0 + band * (1.0 - exp(-(target.y - y0) / band))
		p.set_target(h, target)
		if OS.get_environment("MOTION_TRACE") == ch and steps % 3 == 0:
			print("TRACE %d at=(%.0f deg, %.2f) where=%s straight=%s elbow=%s contact=%s stretch=%.2f" % [steps, rad_to_deg(c.now["at"].x), c.now["at"].y,
				str(where.snapped(Vector2(0.01, 0.01))), str(_straight.get(ch)), _elbow[ch], str(c.now.get("contact")), _stretched.get(ch, 0.0)]
				+ " side=%.0f mode=%s flip=%s" % [p.chains[h].side, p.chains[h].bend_mode, str(_over.has(ch))])
		var wrist: float = float(c.now.get("wrist", 0.0))
		var aim_w: float = float(c.now.get("aim_w", 0.0))
		if aim_w > 0.0:
			var chain: Variant = p.chains[h]
			var fore: Vector2 = chain.end.node.global_position - chain.b.node.global_position
			var want: float = rad_to_deg(wrapf(deg_to_rad(float(c.now.get("aim", 90.0))) - atan2(fore.y, fore.x * s) - _hand_off[ch], -PI, PI))
			wrist = lerpf(wrist, clampf(want, -WRIST_MAX, WRIST_MAX), aim_w)
		p.set_end_angle(h, wrist * s)
		# a hand turned EDGE ON ("look": "edge", or holding a thing by its sides with flat hands): squeezed across
		var edge_on: bool = c.now.get("look", "auto") == "edge" or (holding.get(h, null) is String and holding[h] == "edge")
		_edge_w[h] = move_toward(_edge_w.get(h, 0.0), 1.0 if edge_on else 0.0, DT / 0.12)
		var drawn_edge: bool = p.parts.has(h) and (p.parts[h] as Object).skins.has("edge")
		p.set_squeeze(h, 1.0 if drawn_edge else lerpf(1.0, EDGE_WIDTH, smoothstep(0.0, 1.0, _edge_w[h])))
		# how sharply the hand is SENT (the action's own curve, not the springs' answer to a landing)
		var aim: Vector2 = target - _shoulder_at(ch, body)          # sent, from its shoulder
		if _aim.has(h) and _steady.get(ch, false) and c.owner != null:     # (what a law does after the action is not its path)
			m["travel"] += aim.distance_to(_aim[h]) / arm
		if _aim.has(h):
			var v: Vector2 = (aim - _aim[h]) / DT
			_still[h] = 0 if (aim - _aim[h]).length() > 0.004 * arm else _still.get(h, 0) + 1
			if _aim_vel.has(h):
				m["accel"] = maxf(m["accel"], (v - _aim_vel[h]).length() / DT / arm)
				if OS.has_environment("ACCEL_DEBUG") and (v - _aim_vel[h]).length() / DT / arm > 300.0:
					print("ACCEL %d %s %.0f aim=%s target=%s holding=%s body=%s lean=%.1f chest=%.1f" % [steps, h, (v - _aim_vel[h]).length() / DT / arm, str((aim / arm).snapped(Vector2(0.01, 0.01))), str(target.round()), str(holding.get(h, null)), str(body.round()), float(chans["body"].now["lean"]), float(chans["body"].now["chest"])])
				if OS.has_environment("MOTION_DEBUG") and (v - _aim_vel[h]).length() / DT / arm > 600.0:
					var r0: Run = chans[ch].owner
					print("JERK %d %s a=%.0f at=%s phase=%d t=%.2f contact=%s straight=%s elbow=%s" % [steps, ch, (v - _aim_vel[h]).length() / DT / arm,
						str(c.now["at"]), r0.i if r0 else -1, r0.t if r0 else -1.0, str(c.now.get("contact")), str(_straight.get(ch)), _elbow[ch]])
			_aim_vel[h] = v
		_aim[h] = aim
	# running, the free hands are fists
	for ch in ["arm_l", "arm_r"]:
		var h: String = "hand_" + ch.right(1)
		var run_fist: bool = _walk_w > 0.3 and bool(_gait_look.get("fists", false)) and chans[ch].owner == null and not holding.has(h)
		if run_fist:
			p.set_skin(h, "fist")
			_run_fist[h] = true
		elif _run_fist.has(h):
			_run_fist.erase(h)
			if not holding.has(h):
				p.release_skin(h)
				p.set_skin(h, "", false)
	p.step()
	# lying or bending to the floor, the chest and the head stop ON it: the lean gives way just enough (law)
	var under := -INF
	var lever := 0.3 * leg
	for part in ["chest", "head"]:
		if p.parts.has(part):
			var box: Rect2 = _world_box(part)
			if box.end.y - floor_y > under:
				under = box.end.y - floor_y
				lever = maxf(absf(box.get_center().x - p.body_position().x), 0.3 * leg)
	# ...and the pelvis lying turned on the floor lifts the body out of it
	var hips_under: float = _world_box("pelvis").end.y - floor_y if p.parts.has("pelvis") else -INF
	# falling, the body comes down faster every step: the law answers where it WILL be next step (as fast as it
	# came this one), not where it was, or it is always a step late and the body sinks in at the moment it lands
	var hips_next: float = hips_under + maxf(hips_under - _under_was.y, 0.0) if _under_was.y > -INF else hips_under
	var next: float = under + maxf(under - _under_was.x, 0.0) if _under_was.x > -INF else under
	_under_was = Vector2(under, hips_under)
	if hips_next > 0.0:
		_lift_fix += minf(hips_next, 0.1 * leg)
	elif hips_under < -0.03 * leg:
		_lift_fix = move_toward(_lift_fix, 0.0, 0.5 * leg * DT)
	var lean_now: float = float(bd["lean"])
	if next > 0.0 and absf(lean_now) > 20.0:
		# the lean turns round the hips: a part this far from them rises this much a degree
		_lean_fix += signf(-lean_now) * minf(rad_to_deg(next / lever), 12.0)
	elif under < -0.03 * leg:
		_lean_fix = move_toward(_lean_fix, 0.0, 20.0 * DT)
	if cloth != null:
		if measuring:
			cloth.step(DT, floor_y)
			var ex: Vector2 = cloth.exposed()
			m["skirt"] = maxf(float(m.get("skirt", 0.0)), ex.x)
			m["torn"] = maxf(float(m.get("torn", 0.0)), ex.y)
			m["jerk"] = maxf(float(m.get("jerk", 0.0)), cloth.jerk)
			cloth.jerk = 0.0
		else:
			# the stage is folding the puppet over (a turn): squeezed to a sliver, its own space is torn about and
			# the cloth would fly; it hangs as it is until the turn is over
			cloth.reset()


## A wrist that would put the hand into the chest or the pelvis is moved out to the side of its own shoulder.
func _out_of_body(target: Vector2, s: float, ch: String) -> Vector2:
	for name in ["chest", "pelvis"]:
		var part: Variant = puppet.parts.get(name)
		if part == null:
			continue
		var box: Rect2 = part.painted
		var local: Vector2 = part.node.to_local(target)
		var margin: float = 0.35 * hand_len[ch] / absf(puppet.scale.x)
		var inner := box.grow_individual(-0.08 * box.size.x, 0.0, -0.08 * box.size.x, 0.0)
		# a hand coming at the box from above or below (a body squatting onto its hanging hands) is moved aside
		# on its way, starting a little before it gets there, so it slides past instead of jumping aside
		var band: float = 0.25 * box.size.y
		var depth: float = minf(local.y - inner.position.y, inner.end.y - local.y)     # < 0: above or below it
		if local.x > inner.position.x and local.x < inner.end.x and depth > -band:
			var out_x: float = (box.end.x + margin) if s * signf(puppet.scale.x) > 0.0 else (box.position.x - margin)
			var w: float = smoothstep(-band, 0.0, depth)
			local.x = lerpf(local.x, out_x, w)
			target = part.node.to_global(local)
	return target


# ----------------------------------------------------------------------------- measuring

var measuring := true                # off while the stage folds the puppet over in a turn (its feet move on the picture)


func _measure() -> void:
	if not measuring:
		return
	var p := puppet
	m["steps"] += 1
	if OS.has_environment("MOTION_DEBUG") and p.wrong_total > int(m["wrong"]):
		for ch in ["arm_l", "arm_r"]:
			var c: Variant = p.chains["hand_" + ch.right(1)]
			var at: Vector2 = chans[ch].now["at"]
			print("WRONG %d %s wrong=%d side=%.0f ang=%.0f dist=%.2f lean=%.1f" % [steps, ch, c.wrong, c.side, rad_to_deg(at.x), at.y, rad_to_deg(p.body_lean)])
	m["wrong"] = p.wrong_total
	m["wrong_run"] = p.wrong_longest
	if phys.airborne:
		m["airborne"] += 1
	var body := p.body_position()
	# a planted foot that is not where it was put has slid
	_landed = 0 if phys.airborne else _landed + 1
	if _landed > 20:                        # a foot that has just come down is still being caught
		for f: String in foot_home:
			if (chans["legs"].now[f] as Vector2).y <= 0.01 and _gait.get("swing", "") != f:
				var sl: float = p.handle_position(f).distance_to(p.target_position(f)) / leg
				if OS.has_environment("MOTION_DEBUG") and sl > 0.03 and steps % 4 == 0:
					var cf: Variant = p.chains[f]
					print("SLIDE %d %s %.3f actual=%s target=%s body=%s now=%s lean=%.0f a=%.0f[%.0f,%.0f] b=%.0f[%.0f,%.0f]" % [steps, f, sl, str(p.handle_position(f).round()),
						str(p.target_position(f).round()), str(p.body_position().round()), str(chans["legs"].now[f]), rad_to_deg(p.body_lean),
						rad_to_deg(cf.a.angle), rad_to_deg(cf.a.lo), rad_to_deg(cf.a.hi), rad_to_deg(cf.b.angle), rad_to_deg(cf.b.lo), rad_to_deg(cf.b.hi)])
				m["slide"] = maxf(m["slide"], sl)
	for ch in ["arm_l", "arm_r"]:
		var h: String = "hand_" + ch.right(1)
		var hand: Variant = p.parts[h]
		var mid: Vector2 = hand.node.to_global(hand.center)
		var tip: Vector2 = hand.node.to_global(hand.center * 1.6)
		# into the body without leave
		if not chans[ch].now.get("contact", false) and view != "side" and _on_knee.get(ch, 0.0) < 0.3:
			for name in ["chest", "pelvis"]:
				var part: Variant = p.parts.get(name)
				var local: Vector2 = part.node.to_local(mid)
				var box: Rect2 = part.painted
				if box.has_point(local):
					var depth: float = minf(local.x - box.position.x, box.end.x - local.x)
					m["inside"] = maxf(m["inside"], depth * absf(p.scale.x) / maxf(hand_len[ch] * 2.0, 1.0))
					if OS.has_environment("MOTION_DEBUG") and depth * absf(p.scale.x) / maxf(hand_len[ch] * 2.0, 1.0) > 0.15 and steps % 3 == 0:
						var r0: Run = chans[ch].owner
						print("INSIDE %d %s in %s %.2f owner=%s knee=%.2f squat=%.2f" % [steps, ch, name, depth * absf(p.scale.x) / maxf(hand_len[ch] * 2.0, 1.0),
							r0.id if r0 else "-", _on_knee.get(ch, 0.0), phys.squat / leg])
		# a raised hand with its elbow INSIDE the shoulder: the arm is folded across the chest (two of them cross)
		if view != "side":
			var chain: Variant = p.chains[h]
			var sh_w: Vector2 = chain.a.node.global_position
			var el_w: Vector2 = chain.b.node.global_position
			var hd_w: Vector2 = hand.node.global_position
			# (only a hand that has arrived at a place away from the body: a hand at the face has its elbow in front
			# of the chest by design, and one on its way there or back passes through it)
			if hd_w.y < sh_w.y - 0.1 * arm and _elbow.get(ch, "out") == "out" and _still.get(h, 0) >= 10:
				var inward: float = -(el_w.x - sh_w.x) * _sign(ch) / arm
				if OS.has_environment("MOTION_DEBUG") and inward > 0.25 and steps % 4 == 0:
					print("CROSS %d %s elbow %.2f inside; side=%.0f bend=%s rule=%s" % [steps, ch, inward, chain.side, chain.bend_mode, _elbow.get(ch)])
				m["cross"] = maxf(m.get("cross", 0.0), inward)
		# over the face
		var head: Variant = p.parts["head"]
		var face: Rect2 = _face(head)
		face = face.grow_individual(-0.25 * face.size.x, -0.2 * face.size.y, -0.25 * face.size.x, -0.2 * face.size.y)
		if (face.has_point(head.node.to_local(mid)) or face.has_point(head.node.to_local(tip))) and not _covering_allowed():
			m["face_run"] += DT
			m["face"] = maxf(m["face"], m["face_run"])
	if not _covering_hand():
		m["face_run"] = 0.0
	# the centre of weight (painted area of every part) over what it stands on
	if not phys.airborne and not _seated and _landed > 20 and _gait.is_empty():
		var sum := Vector2.ZERO
		var mass := 0.0
		var lo := INF
		var hi := -INF
		for part: String in p.parts:
			var pp: Variant = p.parts[part]
			var a: float = pp.painted.size.x * pp.painted.size.y
			sum += pp.node.to_global(pp.center) * a
			mass += a
			if part.begins_with("foot") and (chans["legs"].now[part] as Vector2).y <= 0.01:
				var r := _world_box(part)
				lo = minf(lo, r.position.x)
				hi = maxf(hi, r.end.x)
		if mass > 0.0 and lo < hi:
			var cx: float = sum.x / mass
			m["balance"] = maxf(m["balance"], maxf(lo - cx, cx - hi) / leg)
	var under_now := 0.0
	# below the floor, out of the picture
	for part: String in p.parts:
		if part.begins_with("foot"):
			continue
		var low := _lowest(part)
		var allowed: float = maxf(floor_y, _rest_low[part]) + 0.04 * leg
		if not phys.airborne:
			if low - allowed > 0.0:
				under_now = maxf(under_now, (low - allowed) / leg)
			if OS.has_environment("MOTION_DEBUG") and low - allowed > 0.0:
				print("FLOOR %d %s %.3f rest_low=%.0f low=%.0f floor=%.0f" % [steps, part, (low - allowed) / leg, _rest_low[part], low, floor_y])
			pass
	# only what lasts is counted (4 steps and more): a step of overlap at the moment of a fall is not seen
	_under_run = _under_run + 1 if under_now > 0.0 else 0
	if _under_run >= 4:
		m["floor"] = maxf(m["floor"], under_now)
	var all := Rect2()
	var first := true
	for part: String in p.parts:
		var r := _world_box(part)
		all = r if first else all.merge(r)
		first = false
	var out: float = maxf(maxf(-all.position.x, all.end.x - stage.x), -all.position.y)
	if out > 0.0 and OS.has_environment("MOTION_DEBUG"):
		for part: String in p.parts:
			var r := _world_box(part)
			if r.position.x < 0 or r.end.x > stage.x or r.position.y < 0:
				print("OUT ", steps, " ", part, " ", r, " skin ", p.parts[part].skin, " painted ", p.parts[part].painted)
	m["out"] = maxf(m["out"], out / leg)


func _covering_allowed() -> bool:
	for r in runs:
		if r.covers_face and not r.done:
			return true
	return false


func _covering_hand() -> bool:
	var head: Variant = puppet.parts["head"]
	var face: Rect2 = _face(head)
	face = face.grow_individual(-0.25 * face.size.x, -0.2 * face.size.y, -0.25 * face.size.x, -0.2 * face.size.y)
	for h in ["hand_l", "hand_r"]:
		var hand: Variant = puppet.parts[h]
		if face.has_point(head.node.to_local(hand.node.to_global(hand.center))) or \
				face.has_point(head.node.to_local(hand.node.to_global(hand.center * 1.6))):
			return true
	return false


## The lowest point of a part. A limb is measured along its bone (its joint and its far end): the box round a
## tilted shin dips its corner under the floor while the painted shin does not.
func _lowest(part: String) -> float:
	var p: Variant = puppet.parts[part]
	if part == "skirt" and cloth != null:
		return cloth.lowest_world()
	if _limbs.has(part):
		return maxf(p.node.global_position.y, p.node.to_global(p.center * 2.0).y)
	return _world_box(part).end.y


func _world_box(part: String) -> Rect2:
	var p: Variant = puppet.parts[part]
	var b: Rect2 = p.painted
	var xf: Transform2D = p.node.get_global_transform()
	var pts := [xf * b.position, xf * Vector2(b.end.x, b.position.y), xf * b.end, xf * Vector2(b.position.x, b.end.y)]
	var r := Rect2(pts[0], Vector2.ZERO)
	for q: Vector2 in pts:
		r = r.expand(q)
	return r


## The hand's place right now as [out, down] arm lengths from its shoulder, and where it was asked to be.
func hand_miss(ch: String) -> float:
	var h: String = "hand_" + ch.right(1)
	return puppet.handle_position(h).distance_to(puppet.target_position(h)) / arm


## The side of the elbow for a POSE: a hand sent to `goal` (angle, distance round the shoulder). From the pose alone:
##   "rest"                          the side the arm hangs with
##   the action says ("elbow")       that way: down, up, out, in
##   a place on the body             as that place is made for: the elbow DOWN for a hand at the face, the chest, the
##                                   belly; OUT for one on the hip, at the ear, on the crown
##   a place in the air, in the scene  the zone the arm points into (IK.side_wedge): hanging under the hand for an arm
##                                   held out, spread, raised; on the outer side for one let down
func _pose_side(ch: String, at_spec: Variant, goal: Vector2, say: String) -> float:
	if at_spec is String and say == "":
		return _rest_side[ch]
	var chain: Variant = puppet.chains["hand_" + ch.right(1)]
	var s := _sign(ch)
	var world: Vector2 = _shoulder_at(ch, puppet.body_position()) + Vector2(_cart(goal).x * s, _cart(goal).y) * arm
	var where: String = say
	if where == "" and at_spec is Dictionary and at_spec.has("to") and not str(at_spec["to"]).begins_with("@"):
		where = _lm(at_spec["to"])[4]
	if ELBOW_DIR.has(where):
		return _side_for(ch, world, where)
	var t: Vector2 = world - chain.a.node.global_position
	t.x *= signf(puppet.scale.x)
	var pole_sign: float = signf((chain.pole as Vector2).x)
	return Puppet.IK.side_wedge(t, chain.pole, -pole_sign, pole_sign)      # (on an edge of the zone: hanging)


## The side that points the elbow `where` ("down", "up", "out", "in") for a hand at `target` (world). Where that
## cannot tell the two sides apart (the arm points the same way itself), the next best: out, or down.
func _side_for(ch: String, target: Vector2, where: String) -> float:
	var chain: Variant = puppet.chains["hand_" + ch.right(1)]
	var t: Vector2 = target - chain.a.node.global_position
	t.x *= signf(puppet.scale.x)
	for way: String in [where, "out" if where in ["down", "up"] else "down"]:
		var d: Vector2 = ELBOW_DIR[way]
		d.x *= signf((chain.pole as Vector2).x)          # "out" = this arm's own side of the body
		var cross: float = t.normalized().cross(d.normalized())
		if absf(cross) >= 0.2:
			return -signf(cross)
	return chain.side


## The first edge of the elbow's zone (the pole's ray, or the zone's other edge WEDGE further on) that a hand
## going round the shoulder from angle a to angle b passes; INF if none.
func _edge_between(ch: String, a: float, b: float) -> float:
	var lo: float = minf(a, b)
	var hi: float = maxf(a, b)
	var best := INF
	for edge: float in [_line(ch), _line(ch) + Puppet.IK.WEDGE]:
		var e: float = edge + ceilf((lo - edge) / TAU) * TAU
		if e < hi:
			best = minf(best, e)
	return best


## The line (as an angle round the shoulder, outward coordinates) along which this arm's elbow cannot choose a
## side: the elbow rule's pole, turned with the chest.
func _line(ch: String) -> float:
	var base: float = CROSS_LINE
	var c: Variant = puppet.chains["hand_" + ch.right(1)]
	var turn: float = c.a.parent.node.global_rotation if c.a.parent != null else 0.0
	return base + turn * _sign(ch)


## A hand never comes closer to its own shoulder than a folded arm lets it: there the arm's direction is
## undefined and the elbow would spin. Soft: nothing changes beyond twice the limit.
func _fold_limit(at: Vector2) -> Vector2:
	if at.y < 2.0 * MIN_REACH:
		at.y = MIN_REACH + at.y * at.y / (4.0 * MIN_REACH)
	return at


## An arm whose elbow has to swing over (or is swinging) is kept straight until it is done: an elbow folded on
## the wrong side, or jumping over while bent, is what the eye sees as a broken arm. The arm straightens and
## bends back smoothly (STRETCH_TIME), whatever sent the hand there.
func _stretch(ch: String, at: Vector2) -> Vector2:
	var c: Variant = puppet.chains["hand_" + ch.right(1)]
	var need: bool = c.wrong > 0 or absf(c.bend - c.side) > 0.15
	# straightening speeds up and slows down (a top acceleration that does it in STRETCH_TIME from rest): changing
	# its mind halfway, the arm turns round smoothly instead of jerking the hand
	var x: float = _stretched.get(ch, 0.0)
	var v: float = _stretch_v.get(ch, 0.0)
	var goal: float = 1.0 if need else 0.0
	var acc: float = minf(4.0 / pow(STRETCH_TIME if need else STRETCH_BACK, 2.0),
			STRETCH_ACCEL / maxf(CROSS_REACH - at.y, 0.05))       # a long reach out takes a little longer
	var want: float = signf(goal - x) * sqrt(2.0 * acc * absf(goal - x))
	v = move_toward(v, want, acc * DT)
	x += v * DT
	if x <= 0.0 or x >= 1.0:
		x = clampf(x, 0.0, 1.0)
		v = 0.0
	_stretched[ch] = x
	_stretch_v[ch] = v
	if x > 0.0:
		at.y = lerpf(at.y, maxf(at.y, CROSS_REACH), x)
	return at


## A bent arm reaches out as it comes near its elbow line (either end of it) and is nearly straight on it, so
## the elbow swings over there at once, unseen, instead of jumping over while bent. Continuous: no jump in the
## hand's place, however the hand comes and goes. (The IK keeps the elbow's side within ~7 degrees of the line,
## so the arm is kept straight a little past that.)
func _off_line(ch: String, at: Vector2) -> Vector2:
	if at.y >= CROSS_REACH or _elbow.get(ch, "out") != "out":
		return at
	for k in 2:
		var d: float = absf(wrapf(at.x - (_line(ch) + PI * k), -PI, PI))
		var near: float = smoothstep(0.0, 1.0, clampf(1.0 - (d - LINE_HOLD) / BAND, 0.0, 1.0))
		at.y = lerpf(at.y, CROSS_REACH, near)
	return at


## How long the way from one place to another is, as the hand should go: straight in front of the body, round
## the shoulder elsewhere (a straight line from under the shoulder to the ear would go through the shoulder), and
## reaching out where it passes its elbow line (the elbow swings over only on a straight arm): as _arm_at sends it.
func _way(ch: String, a: Vector2, b: Vector2, straight: bool) -> float:
	if straight:
		return _cart(a).distance_to(_cart(b))
	var dd: float = wrapf(b.x - a.x, -PI, PI)
	if absf(dd) > 0.05 and _sweeps(a.x, a.x + dd, PI):
		dd -= signf(dd) * TAU                 # round the outside, as the hand is sent
	var to: float = a.x + dd
	var crossing: float = _edge_between(ch, a.x, to)
	var crosses: bool = view != "side" and crossing < maxf(a.x, to) and absf(to - a.x) > deg_to_rad(4.0)
	var length := 0.0
	var last := _cart(a)
	for i in range(1, 33):
		var u := i / 32.0
		var ang: float = lerpf(a.x, to, u)
		var dist: float = lerpf(a.y, b.y, u)
		if crosses:
			var near: float = clampf(1.0 - (absf(ang - crossing) - deg_to_rad(8.0)) / deg_to_rad(40.0), 0.0, 1.0)
			dist = lerpf(dist, maxf(dist, CROSS_REACH), near)
		var q := _cart(Vector2(ang, dist))
		length += q.distance_to(last)
		last = q
	return length


## Starts a walk of `dist` px (signed: forward in profile, rightward from the front) at `speed` px a second.
## The GAIT (all optional, leg lengths and degrees): step (how far a foot goes, 0.7), lift (how high, 0.12),
## bob (the body up over the standing foot, 0.02), hop (up again mid-step, a run or a skip: 0), swing (the free
## arms' swing, 1), bend (free arms bent at the elbow, a run: 0..1), sway (degrees the body rocks to the
## standing foot, a waddle: 0), wobble (0..1: uneven steps and a wandering lean, a drunk: 0),
## advance (0..1: the share of the way the body really goes across, 1; a hero walking INTO the depth of the scene
## goes there by the stage's depth, not across: it steps on the spot, 0, or slants, between).
func _start_walk(dist: float, speed: float, gait: Dictionary = {}) -> void:
	if absf(dist) < 1.0:
		return
	# a walk still under way for another action is over now: that action goes on to its next phase (its return)
	for other in runs:
		if other.walking:
			other.walking = false
			other.length = other.t
	var dir: float = signf(dist) * (facing if view == "side" else 1.0)
	var v: float = maxf(absf(speed), 0.1 * leg)
	var k: float = float(gait.get("step", WALK_STEP))
	var step: float = k * leg if view == "side" else k * 0.45 * leg   # sideways steps are short
	_gait = {"left": absf(dist), "dir": dir, "v": v, "step": step, "dur": step / (2.0 * v), "t": 0.0,
		"stopping": false, "swing": "", "n": 0,
		"lift": float(gait.get("lift", WALK_LIFT)), "bob": float(gait.get("bob", WALK_BOB)),
		"hop": float(gait.get("hop", 0.0)), "arms": float(gait.get("swing", 1.0)), "bend": float(gait.get("bend", 0.0)),
		"sway": float(gait.get("sway", 0.0)), "wobble": float(gait.get("wobble", 0.0)), "fists": bool(gait.get("fists", false)),
		"advance": clampf(float(gait.get("advance", 1.0)), 0.0, 1.0), "total": absf(dist)}
	_gait_look = _gait.duplicate()
	_next_swing(puppet.body_position())


## How much of the walk under way is done, 0..1 (1 when there is none): the stage moves a hero into the depth with it.
func walk_done() -> float:
	if _gait.is_empty():
		return 1.0
	return 1.0 - float(_gait["left"]) / maxf(float(_gait.get("total", 1.0)), 1.0)


## Picks the next foot to swing and where it lands; ends the walk when the feet stand together again.
func _next_swing(body: Vector2) -> void:
	var g := _gait
	if g["swing"] != "":
		events.append([steps, "walk", "foot", g["swing"]])      # (the foot that swung is down: a step is heard)
	var other: String = "foot_l" if g["swing"] == "foot_r" else "foot_r"
	if g["swing"] == "":                    # the first step: the foot that is behind, or the near one
		other = "foot_r"
	var stance: float = body.x + _home_off[other] * (1.0 if view != "side" else 0.0)
	var to: float
	if g["stopping"]:
		to = body.x + _home_off[other]       # the last step: next to the other foot
		if absf((foot_home[other] as Vector2).x - to) < 0.04 * leg:
			_gait = {}
			return
	else:
		var uneven: float = 1.0 + 0.45 * float(g.get("wobble", 0.0)) * sin(float(g.get("n", 0)) * 2.39)
		to = stance + g["dir"] * (g["v"] * g["dur"] + g["step"] * 0.25) * uneven * float(g.get("advance", 1.0))
	g["n"] = int(g.get("n", 0)) + 1
	g["swing"] = other
	g["from"] = foot_home[other]
	g["to"] = Vector2(to, (foot_home[other] as Vector2).y)
	g["t"] = 0.0


## One step of a walk: the body goes on at an even speed, one foot swings forward on a low arc, then the other.
func _walk_step(body: Vector2) -> Vector2:
	var g := _gait
	if not g["stopping"]:
		var move: float = minf(g["v"] * DT, g["left"])
		phys.pos.x += g["dir"] * move * float(g.get("advance", 1.0))
		body.x += g["dir"] * move * float(g.get("advance", 1.0))
		g["left"] -= move
		if g["left"] <= 0.0:
			g["stopping"] = true
	g["t"] += DT
	var u: float = clampf(g["t"] / g["dur"], 0.0, 1.0)
	var f: String = g["swing"]
	var at: Vector2 = (g["from"] as Vector2).lerp(g["to"], smoothstep(0.0, 1.0, u))
	# (a short step lifts the foot less; a step on the spot, walking into the depth, lifts it as a whole step would)
	var stride: float = absf((g["to"] as Vector2).x - (g["from"] as Vector2).x) / maxf(float(g.get("advance", 1.0)), 0.05)
	at.y -= float(g.get("lift", WALK_LIFT)) * leg * sin(PI * u) * clampf(stride / (0.3 * leg), 0.3, 1.0)
	foot_home[f] = at
	if u >= 1.0:
		foot_home[f] = g["to"]
		_next_swing(body)
	return body


## A value moving when its phase began goes on moving at first and turns smoothly towards where it is sent
## (the Hermite curve: the speed it had, dying out over the phase). Without it a hand interrupted on its way stops
## dead and sets off again: a jerk.
func _carry(r: Run, c: Chan, key: String, v: Variant) -> Variant:
	if not c.v0.has(key):
		return v
	var ph: Dictionary = r.phases[r.i]
	var dur: float = minf(r.length, r.ease_time)
	if dur <= 0.0 or r.t >= dur:
		return v
	var tau: float = r.t / dur
	var h: float = tau * (1.0 - tau) * (1.0 - tau) * dur
	var v0: Variant = c.v0[key]
	if v is float and v0 is float:
		return v + v0 * h
	if v is Vector2 and v0 is Vector2:
		return v + v0 * h
	return v


## Whether going from angle a to angle b (the way given) passes the direction x.
static func _sweeps(a: float, b: float, x: float) -> bool:
	var lo: float = minf(a, b)
	var hi: float = maxf(a, b)
	var n: float = ceilf((lo - x) / TAU)
	return x + n * TAU < hi - 0.01 and x + n * TAU > lo + 0.01


## A landmark as this view has it.
func _lm(name: String) -> Array:
	if name.begins_with("@"):
		return ["@", 0.0, 0.0, "point", "out"]
	if view == "side" and LANDMARKS_SIDE.has(name):
		return LANDMARKS_SIDE[name]
	return LANDMARKS.get(name, LANDMARKS["chest"])


## The centre of weight across: every part weighs as much as it has painted area.
func _weight_x() -> float:
	var sum := 0.0
	var mass := 0.0
	for part: String in puppet.parts:
		var pp: Variant = puppet.parts[part]
		var a: float = pp.painted.size.x * pp.painted.size.y
		sum += pp.node.to_global(pp.center).x * a
		mass += a
	return sum / maxf(mass, 1.0)


## Where the shoulder of this arm is for a body at `body`: where it is on the body now (a hero lying down, bowing
## or leaning has it far from where it is standing), carried along with the body.
func _shoulder_at(ch: String, body: Vector2) -> Vector2:
	var c: Variant = puppet.chains["hand_" + ch.right(1)]
	return body + (c.a.node.global_position - puppet.root.node.global_position)


## Which way is "outward" for this arm or leg, on the screen: its own side seen from the front or the back; in
## profile both arms and legs reach FORWARD, the way the hero faces.
func _sign(ch: String) -> float:
	if view == "side":
		return facing
	return -1.0 if ch.ends_with("l") else 1.0


## The same in a part's own frame (a hero facing left is a mirrored puppet).
func _lsign(ch: String) -> float:
	return _sign(ch) * signf(puppet.scale.x)


static func _polar(p: Vector2) -> Vector2:
	return Vector2(atan2(p.y, p.x), p.length())


static func _cart(a: Vector2) -> Vector2:
	return Vector2(cos(a.x), sin(a.x)) * a.y
