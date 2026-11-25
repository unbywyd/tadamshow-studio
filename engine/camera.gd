extends RefCounted
## The CAMERA of a scene: which window of the world the picture shows, and how that window moves.
##
## The world is the scene's frame (stage.gd: 720 x 1280 by default, or the whole background picture with
## "world": "picture"). The picture (the window of the player or the film) may have any shape: 9:16, 1:1, 16:9 are
## the same scene through a differently shaped window. The camera never shows past the edge of the world: the
## window is at least as small as fits inside it (no bars), and it is kept inside.
##
## Script lines (stage.gd):
##   { "camera": "wide" }                            the whole stage, as much as the window shape allows
##   { "camera": "full", "on": "loaf" }              the hero head to feet
##   { "camera": "medium", "on": "loaf" }            the hero from the head to the thighs
##   { "camera": "close", "on": "loaf" }             the face
##   { "camera": "two", "on": ["loaf", "granny"] }   both heroes in the picture
##   "time": 0.8   seconds the move takes (a slow push in: 3; 0 = a cut). The camera stays on a hero that walks.
##   "x", "y" (shares of the world), "zoom" (times the widest): an exact window instead of a hero
##   "roll": degrees the camera is tilted (an uneasy moment)
##   { "camera": "shake", "power": 1.0, "time": 0.4 }   a jolt (a blow, a fright), on top of whatever it shows

var world := Vector2(720, 1280)      # world px
var screen := Vector2(720, 1280)     # the picture, its own px (the viewport's visible size)
var on := true                       # false: the world is shown 1:1 from its corner (the viewer)

var center := Vector2(360, 640)      # world point in the middle of the picture
var zoom := 1.0                      # picture px per world px
var roll := 0.0                      # radians

var _from := {}                      # the camera when the move began: {center, zoom, roll}
var _t := 0.0
var _dur := 0.0
var _shake := 0.0                    # strength left (share of the picture's height)
var _shake_time := 0.0
var _shake_t := 0.0
var started := false

const CLOSEST := 2.6                 # the closest the camera goes, times the widest (the painted world is ~1.2x the
                                     # picture: past this its strokes show)
var back_scale := 1.0               # (stage.gd: the background's depth scale when the scene has parallax)
var closest := CLOSEST              # (a scene with focus: the background is soft anyway, closer is fine)
const FOLLOW := 0.18                 # seconds the camera lags behind a hero that moves (after its move is over)


## The smallest zoom that leaves no bars: the window as big as fits in the world.
func widest() -> float:
	return maxf(screen.x / world.x, screen.y / world.y)


## A new framing: from what it shows now to `goal` over `time` seconds (0 = a cut).
func move(time: float) -> void:
	_from = {"center": center, "zoom": zoom, "roll": roll}
	_t = 0.0
	_dur = maxf(time, 0.0)


func shake(power: float, time: float) -> void:
	_shake = 0.012 * power
	_shake_time = maxf(time, 0.05)
	_shake_t = 0.0


## One step towards the goal [center, zoom, roll] (world px, picture px per world px, radians).
func step(dt: float, goal: Array) -> void:
	var g := _clamp(goal[0], goal[1])
	var want_c: Vector2 = g[0]
	var want_z: float = g[1]
	var want_r: float = goal[2]
	if not started:
		started = true
		center = want_c
		zoom = want_z
		roll = want_r
		return
	_t += dt
	if _dur > 0.0 and _t < _dur and not _from.is_empty():
		# on its way: an even curve from where it was to where the goal is NOW (a hero walking is caught up with)
		var u: float = smoothstep(0.0, 1.0, _t / _dur)
		zoom = exp(lerpf(log(float(_from["zoom"])), log(want_z), u))
		center = (_from["center"] as Vector2).lerp(want_c, u)
		roll = lerpf(float(_from["roll"]), want_r, u)
	elif _dur <= 0.0 and _t <= dt * 1.5:
		center = want_c                                 # a cut
		zoom = want_z
		roll = want_r
	else:
		# there: it follows the goal softly (a hero walking in the picture is kept in it without a jerk)
		var k: float = 1.0 - exp(-dt / FOLLOW)
		zoom = exp(lerpf(log(zoom), log(want_z), k))
		center = center.lerp(want_c, k)
		roll = lerpf(roll, want_r, k)
	var c := _clamp(center, zoom)
	center = c[0]
	zoom = c[1]
	if _shake > 0.0:
		_shake_t += dt
		if _shake_t >= _shake_time:
			_shake = 0.0


## The world -> picture transform now.
func transform() -> Transform2D:
	if not on:
		return Transform2D.IDENTITY
	var jolt := Vector2.ZERO
	var z := zoom
	var c := center
	if _shake > 0.0:
		var fade: float = 1.0 - _shake_t / _shake_time
		var sh: float = _shake * fade * fade
		var a: float = _shake_t * 60.0
		jolt = Vector2(sin(a * 1.7) + 0.5 * sin(a * 3.1), cos(a * 1.3) + 0.5 * sin(a * 2.3)) * sh * screen.y
		# a little closer while it shakes, and kept in by the jolt's reach: the edge of the world never shows
		z = zoom * (1.0 + 3.0 * sh)
		var half: Vector2 = screen / z * 0.5 + Vector2.ONE * 1.5 * sh * screen.y / z
		c = Vector2(clampf(c.x, half.x, world.x - half.x), clampf(c.y, half.y, world.y - half.y))
	var basis := Transform2D(roll, Vector2(z, z), 0.0, Vector2.ZERO)
	return Transform2D(roll, Vector2(z, z), 0.0, screen * 0.5 + jolt - basis * c)


# ----------------------------------------------------------------------------- framings: [center, zoom]

## The whole stage: as much of the world as the window shape allows, the ground low in the picture, centred on
## `focus_x` (the middle of the heroes) where the world is wider than the window.
## `heroes`: all of them (world px): when the window is lower than the stage (a wide picture of a tall world) it
## follows them, heads first, rather than the front edge of the ground.
func wide(floor_y: float, focus_x: float, heroes := Rect2()) -> Array:
	var z: float = widest()
	var win: Vector2 = screen / z
	var bottom: float = minf(world.y, floor_y + 0.16 * win.y)
	var cy: float = bottom - 0.5 * win.y
	if heroes.size.y > 0.0 and (heroes.position.y < cy - 0.46 * win.y or heroes.end.y < cy - 0.2 * win.y):
		if heroes.size.y <= 0.88 * win.y:
			cy = heroes.get_center().y + 0.03 * win.y
		else:
			cy = heroes.position.y - 0.06 * win.y + 0.5 * win.y
	return [Vector2(focus_x, cy), z]


## A box (world px) filling `fill` of the picture's height, its top `top` of the way down the picture.
## `need_w`: the box's width must fit too.
func frame(box: Rect2, fill: float, top: float) -> Array:
	var z: float = screen.y * fill / maxf(box.size.y, 1.0)
	z = minf(z, screen.x * 0.9 / maxf(box.size.x, 1.0))
	z = maxf(z, widest())
	var win: Vector2 = screen / z
	var cy: float = box.position.y - top * win.y + 0.5 * win.y
	return [Vector2(box.get_center().x, cy), z]


## Kept inside the world: never zoomed out past the widest, never in past CLOSEST (the background would blur),
## never past an edge.
func _clamp(c: Vector2, z: float) -> Array:
	z = clampf(z, widest(), widest() * closest)
	var half: Vector2 = screen / z * 0.5
	# with parallax the background (depth scale back_scale < 1) slides along with the camera: the window shows its
	# point mid + back_scale (c - mid), so the camera may go 1 / back_scale times further before its edge shows
	var mid: Vector2 = world * 0.5
	var room: Vector2 = (mid - half).max(Vector2.ZERO) / clampf(back_scale, 0.1, 1.0)
	return [Vector2(clampf(c.x, mid.x - room.x, mid.x + room.x), clampf(c.y, mid.y - room.y, mid.y + room.y)), z]
