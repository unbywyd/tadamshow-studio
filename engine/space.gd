extends RefCounted
## The GROUND of a scene: how deep it goes, and how big and how high a hero standing at some depth looks.
##
## Every hero, every thing and every set piece lives in ONE frame: the stage as it is at the front edge (depth 0),
## where the floor is at `near_y` and a hero has the size the scene gave it. What depth does is only how that frame is
## SHOWN: a hero standing z px deep is drawn smaller (`scale_at`) and higher up (`floor_at`), drawn towards the
## vanishing point. So walking, hands, things in hands work exactly as at the front; depth is a picture transform of
## the hero's own canvas layer (stage.gd), never a change to its body.
##
## scene.json:
##   "floor": 0.86                       the front edge of the ground (depth 0), share of the stage height
##   "ground": { "far": 0.66,            the deepest line a hero can stand on, share of the stage height
##               "far_scale": 0.65,      how big a hero is there, against the front (perspective: the horizon follows)
##               "tilt": 0.7,            how flat the ground is seen: walking 1 px deeper moves 0.7 px up the screen
##                                       at the front (sets how long walking into depth takes: less = longer)
##               "vanish": 0.5 }         where the lines of the ground meet, share of the stage width
## Without "ground" there is no depth: everyone stands at the front edge, as before.
##
## Perspective done right: on a flat ground a thing's size on the screen is in proportion to how far its foot is
## below the horizon. So `far` and `far_scale` give the horizon; `tilt` gives how far the eye is (cam_d).

var size := Vector2(720, 1280)
var near_y := 1100.0          # floor at depth 0, stage px
var far_y := 1100.0
var far_scale := 1.0
var horizon := -INF
var cam_d := 1.0              # the eye's distance to the front edge along the ground, frame px
var depth := 0.0              # how deep the ground goes (z of the far line), frame px
var vx := 360.0               # the vanishing point across


func setup(spec: Dictionary, stage_size: Vector2, floor_y: float) -> void:
	size = stage_size
	near_y = floor_y
	far_y = floor_y
	vx = size.x * 0.5
	var g: Dictionary = spec.get("ground", {})
	if g.is_empty():
		return
	far_y = size.y * float(g.get("far", spec.get("floor", 0.86) - 0.15))
	far_scale = clampf(float(g.get("far_scale", 0.65)), 0.2, 0.98)
	if far_y >= near_y - 1.0:
		far_y = near_y
		return
	horizon = (far_y - far_scale * near_y) / (1.0 - far_scale)
	cam_d = (near_y - horizon) / maxf(float(g.get("tilt", 0.7)), 0.05)
	depth = cam_d * (1.0 / far_scale - 1.0)
	vx = size.x * float(g.get("vanish", 0.5))


func has_depth() -> bool:
	return depth > 0.0


## How big a thing at depth z is drawn, against the front edge.
func scale_at(z: float) -> float:
	if depth <= 0.0:
		return 1.0
	return cam_d / (cam_d + maxf(z, -0.65 * cam_d))   # (up to ~2.9 times nearer: "near" in stage.gd)


## Where the floor is on the screen at depth z.
func floor_at(z: float) -> float:
	if depth <= 0.0:
		return near_y
	return horizon + (near_y - horizon) * scale_at(z)


## The frame of everything standing at depth z, on the screen: a point (x, y) of the frame goes to
## (vx + (x - vx) * s, floor_at(z) + (y - near_y) * s).
func transform_at(z: float) -> Transform2D:
	var s: float = scale_at(z)
	return Transform2D(0.0, Vector2(s, s), 0.0, Vector2(vx - vx * s, floor_at(z) - near_y * s))


## A point ON THE GROUND of the screen (a foot, a mark on the background) -> [x in the frame, depth z].
## Above the far line or below the front edge it is held to them.
func ground_of(screen: Vector2) -> Vector2:
	if depth <= 0.0:
		return Vector2(screen.x, 0.0)
	var y: float = clampf(screen.y, far_y, near_y)
	var s: float = (y - horizon) / (near_y - horizon)
	var z: float = cam_d * (1.0 / s - 1.0)
	return Vector2(vx + (screen.x - vx) / s, z)


## x on the screen at depth z -> x in the frame (where a hero at that depth must stand to be seen there).
func frame_x(screen_x: float, z: float) -> float:
	return vx + (screen_x - vx) / scale_at(z)


## Depth as a share of the ground (0 the front edge, 1 the far line) -> z.
func z_of_share(share: float) -> float:
	return clampf(share, 0.0, 1.0) * depth
