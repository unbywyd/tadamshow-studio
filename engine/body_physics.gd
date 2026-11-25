extends RefCounted
## Gravity for the puppet as a whole: it stands on its legs, falls when it is let go in the air, lands with the
## knees giving way, and jumps. The limbs already have weight (springs.gd); this is the weight of the body.
##
## Our own maths in the same fixed 1/60 s step as everything else: no physics engine, no randomness, so the same
## input always gives the same motion.
##
## The body is one point (the body handle) with a velocity.
##   on the ground   the legs are a spring that holds the body at its standing height: pushed down (a landing, a
##                   squat let go) it comes back up with one small bounce;
##   in the air      nothing holds it: it falls; the feet let go of the floor and the legs hang;
##   touchdown       when the body is back at standing height, moving down: the feet are put on the floor under
##                   the hips and the fall is taken by the knees.
## While the animator holds the body nothing of this acts, but the body's speed is measured, so a puppet that is
## thrown keeps flying.

const Puppet := preload("res://puppet.gd")
const DT := Puppet.DT

const STIFF := 420.0          # 1/s^2: the legs as a spring, about 3 bounces a second
const DAMP := 16.0            # 1/s: one visible bounce, then still
const LIFT := 4.0             # px above standing height at which the feet leave the floor
const SQUAT := 0.45           # deepest squat, in leg lengths
const CROUCH := 0.16          # how deep a jump winds up, in leg lengths
const CROUCH_STEPS := 9
const JUMP := 0.55            # default jump height, in leg lengths
const WALL := 70.0            # px from the side of the stage the body may not pass

var puppet: Puppet
var floor_y := 0.0
var stage_width := 720.0:
	set(v):
		stage_width = v
		walls = Vector2(WALL, v - WALL)
## where the body may go across, frame px (stage.gd moves them for a hero deep in the scene: the picture is wider there)
var walls := Vector2(WALL, 720.0 - WALL)
var feet: Array[String] = []

var pos := Vector2.ZERO        # the body handle, stage px
var vel := Vector2.ZERO
var airborne := false
var stand_y := 0.0             # the body's height when it stands
var leg := 100.0               # leg length, stage px
var g := 6000.0                # stage px / s^2
var _foot: Dictionary = {}     # foot handle -> where its ankle stands, relative to (body x, floor)
var _wind := -1                # steps into the wind-up of a jump, -1 = no jump coming
var _jump := JUMP
var _crouch := 0.0
var _forward := 0.0              # px a jump carries the body sideways
var max_sink := INF              # px the body may go below standing at all (a long dress must not sink into the floor)
var squat := 0.0                # px the legs are asked to fold while standing (motion.gd: legs.drop)


## Takes the puppet's present pose as "standing": call it when the puppet has been stood on the floor.
func stand_here() -> void:
	pos = puppet.body_position()
	vel = Vector2.ZERO
	airborne = false
	stand_y = pos.y
	_wind = -1
	_crouch = 0.0
	var c: Variant = puppet.chains.get(feet[0])
	leg = (c.l1 + c.l2) * absf(puppet.scale.y)
	g = puppet.gravity * absf(puppet.scale.y)
	for f in feet:
		var ankle := puppet.handle_position(f)
		_foot[f] = Vector2(ankle.x - pos.x, ankle.y - floor_y)


## Jumps on the spot: winds up, pushes off, flies and lands. `height` is in leg lengths.
func jump(height := JUMP, forward := 0.0) -> void:
	if not airborne and _wind < 0:
		_wind = 0
		_jump = height
		_forward = forward


## One step. `held` = the animator has the body; `at` = where the body is then. Returns where the body is now.
func step(held: bool, at: Vector2) -> Vector2:
	if held:
		vel = ((at - pos) / DT).limit_length(3000.0)
		pos = at
		_wind = -1
		_crouch = 0.0
		if not airborne and pos.y < stand_y - LIFT:
			_take_off()
		elif airborne and pos.y >= stand_y:
			_touch_down()
		return pos

	if _wind >= 0:                       # the wind-up before a jump: down first, then off
		_wind += 1
		_crouch = minf(CROUCH * leg, max_sink) * minf(float(_wind) / CROUCH_STEPS, 1.0)
		if _wind > CROUCH_STEPS + 2:
			_wind = -1
			_crouch = 0.0
			# fast enough to rise `_jump` leg lengths above STANDING height, from however deep the wind-up got
			vel = Vector2(0.0, -sqrt(2.0 * g * (_jump * leg + maxf(pos.y - stand_y, 0.0))))
			vel.x = _forward / maxf(2.0 * -vel.y / g, 0.05)        # over the whole flight, up and down
			_take_off()

	if airborne:
		vel.y += g * DT
		pos += vel * DT
		if pos.x < walls.x or pos.x > walls.y:
			pos.x = clampf(pos.x, walls.x, walls.y)
			vel.x = -0.3 * vel.x
		if pos.y >= stand_y and vel.y > 0.0:
			_touch_down()
	else:
		vel.x = 0.0
		vel.y += (-STIFF * (pos.y - (stand_y + _crouch + squat)) - DAMP * vel.y) * DT
		pos.y += vel.y * DT
		var deepest: float = minf(maxf(SQUAT * leg, squat + 0.05 * leg), max_sink)
		if pos.y > stand_y + deepest:          # the legs fold no further
			pos.y = stand_y + deepest
			vel.y = minf(vel.y, 0.0)
	return pos


func _take_off() -> void:
	airborne = true
	for f in feet:
		puppet.set_free(f, true)


func _touch_down() -> void:
	airborne = false
	vel.x = 0.0
	for f in feet:
		var s: Vector2 = _foot[f]
		puppet.set_target(f, Vector2(pos.x + s.x, floor_y + s.y))
